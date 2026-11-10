"""Isolamento de credenciais, operação real no cofre da sessão e sanitização de logs.

Regras de segurança inegociáveis do BrisaSync:
- Tokens OAuth, client_secret ou chaves de configuração NUNCA são persistidos em
  SQLite, repositório, argumentos de linha de comando (`argv`) ou arquivos de log.
- O diagnóstico distingue explicitamente "utilitário de cofre instalado" de
  "cofre acessível e operação de armazenamento validada" executando um ciclo real
  de escrita, leitura, verificação e remoção de um segredo descartável.
- Se o cofre estiver bloqueado ou indisponível, levanta `VaultUnavailableError`
  com mensagem clara e recuperável, sem fallback silencioso inseguro.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import threading
from typing import Any, Iterator
import uuid

from brisasync.platform_compat import (
    get_data_dir,
    is_windows,
    lock_file,
    unlock_file,
    win_cred_delete,
    win_cred_read,
    win_cred_write,
)

_SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r'("(?:access_token|refresh_token|client_secret|token|password|id_token|rclone_config_key)"\s*:\s*)"[^"]*"',
        re.IGNORECASE,
    ),
    re.compile(
        r"((?:access_token|refresh_token|client_secret|token|password|authorization|rclone_config_pass)\s*[=:]\s*)(\S+)",
        re.IGNORECASE,
    ),
    re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
    re.compile(r"(ya29\.[A-Za-z0-9._~+/=-]+)"),
    re.compile(r"(1//[A-Za-z0-9._~+/=-]+)"),
)

FORBIDDEN_SETTING_KEYS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "client_secret",
        "oauth_token",
        "password",
        "secret",
        "credentials",
        "rclone_config_key",
        "rclone_config_pass",
    }
)


class VaultUnavailableError(RuntimeError):
    """Levantada quando o cofre de segredos da sessão não está acessível ou falhou na validação."""


class VaultLockedError(VaultUnavailableError):
    """Levantada quando o cofre de segredos está bloqueado na sessão do usuário."""


class CredentialSyncBackError(VaultUnavailableError):
    """Levantada quando tokens renovados no arquivo cifrado não puderam ser devolvidos ao cofre."""


def redact_secrets(text: str) -> str:
    """Remove qualquer token ou segredo potencial antes de registrar em logs ou histórico."""
    if not text:
        return text
    sanitized = text
    sanitized = _SENSITIVE_PATTERNS[0].sub(r'\1"[REDACTED]"', sanitized)
    sanitized = _SENSITIVE_PATTERNS[1].sub(r"\1[REDACTED]", sanitized)
    sanitized = _SENSITIVE_PATTERNS[2].sub(r"\1[REDACTED]", sanitized)
    sanitized = _SENSITIVE_PATTERNS[3].sub("[REDACTED_GOOGLE_TOKEN]", sanitized)
    sanitized = _SENSITIVE_PATTERNS[4].sub("[REDACTED_REFRESH_TOKEN]", sanitized)
    return sanitized


def is_forbidden_secret_key(key: str) -> bool:
    """Verifica se uma chave de configuração tenta armazenar um segredo proibido no banco."""
    normalized = key.strip().lower()
    return any(token_word in normalized for token_word in FORBIDDEN_SETTING_KEYS)


def default_credentials_lock_path() -> Path:
    return get_data_dir() / "credentials.lock"


@dataclass(frozen=True)
class OAuthCredentials:
    """Credenciais OAuth 2.0 armazenadas exclusivamente no cofre de segredos da sessão."""

    client_id: str
    client_secret: str
    access_token: str
    refresh_token: str
    token_type: str
    expiry: str  # RFC3339 / ISO-8601 UTC string (compatível com rclone token JSON)
    scope: str
    account_email: str
    updated_at: str = ""

    @property
    def has_drive_scope(self) -> bool:
        """Retorna True somente se o escopo https://www.googleapis.com/auth/drive foi concedido."""
        return "https://www.googleapis.com/auth/drive" in set(self.scope.split())

    def to_rclone_token_json(self) -> str:
        """Serializa o objeto de token no formato exato esperado pelo backend drive do rclone."""
        payload = {
            "access_token": self.access_token,
            "token_type": self.token_type or "Bearer",
            "refresh_token": self.refresh_token,
            "expiry": self.expiry,
        }
        return json.dumps(payload, separators=(",", ":"))

    def is_expired_or_near_expiry(self, margin_seconds: int = 90) -> bool:
        """Verifica se o access_token já expirou ou vai expirar nos próximos `margin_seconds`."""
        if not self.expiry:
            return True
        try:
            normalized = self.expiry.replace("Z", "+00:00")
            exp_dt = datetime.fromisoformat(normalized)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            now_dt = datetime.now(timezone.utc)
            return (exp_dt - now_dt).total_seconds() <= margin_seconds
        except ValueError:
            return True

    def to_json(self) -> str:
        data = asdict(self)
        if not data.get("updated_at"):
            data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> OAuthCredentials:
        data: dict[str, Any] = json.loads(raw)
        return cls(
            client_id=str(data["client_id"]),
            client_secret=str(data.get("client_secret", "")),
            access_token=str(data["access_token"]),
            refresh_token=str(data["refresh_token"]),
            token_type=str(data.get("token_type", "Bearer")),
            expiry=str(data["expiry"]),
            scope=str(data.get("scope", "https://www.googleapis.com/auth/drive")),
            account_email=str(data.get("account_email", "")),
            updated_at=str(data.get("updated_at", "")),
        )


@dataclass(frozen=True)
class CredentialCapabilities:
    """Estado real dos utilitários e da validação operacional do cofre na sessão Linux."""

    has_secret_tool: bool
    secret_tool_path: str | None
    has_kwallet_query: bool
    kwallet_query_path: str | None
    vault_accessible: bool = False
    vault_verified: bool = False
    active_backend: str | None = None
    verification_message: str = ""

    @property
    def utility_installed(self) -> bool:
        if self.active_backend == "Windows Credential Manager" or is_windows():
            return True
        return self.has_secret_tool or self.has_kwallet_query

    @property
    def is_available(self) -> bool:
        return self.utility_installed and self.vault_accessible and self.vault_verified

    @property
    def provider_summary(self) -> str:
        if self.active_backend == "Windows Credential Manager" or is_windows():
            if self.vault_verified:
                return (
                    f"Windows Credential Manager | "
                    f"Cofre acessível e validado: {self.verification_message}"
                )
            return f"Windows Credential Manager | {self.verification_message}"
        if not self.utility_installed:
            return (
                "Utilitário de cofre ausente (instale 'libsecret' / 'secret-tool' "
                "ou 'kwallet')"
            )
        installed_list: list[str] = []
        if self.has_secret_tool:
            installed_list.append(f"secret-tool ({self.secret_tool_path})")
        if self.has_kwallet_query:
            installed_list.append(f"kwallet-query ({self.kwallet_query_path})")
        installed_str = ", ".join(installed_list)
        if self.vault_verified:
            return (
                f"Utilitário instalado ({installed_str}) | "
                f"Cofre acessível e validado via {self.active_backend}: {self.verification_message}"
            )
        return (
            f"Utilitário instalado ({installed_str}), mas cofre inacessível/bloqueado: "
            f"{self.verification_message}"
        )


class CredentialStore:
    """Armazenamento seguro de credenciais no serviço de segredos da sessão Linux."""

    SERVICE_NAME = "org.brisasync.oauth"
    OAUTH_ACCOUNT_KEY = "google_drive_primary"
    RCLONE_KEY_ACCOUNT = "rclone_config_encryption_key"
    KWALLET_FOLDER = "BrisaSync"

    def __init__(
        self,
        lock_path: Path | str | None = None,
        oauth_account_key: str | None = None,
        rclone_key_account: str | None = None,
    ) -> None:
        self.lock_path = (
            Path(lock_path)
            if lock_path is not None
            else default_credentials_lock_path()
        )
        self.OAUTH_ACCOUNT_KEY = (
            oauth_account_key
            or os.environ.get("BRISASYNC_VAULT_ACCOUNT_KEY")
            or self.__class__.OAUTH_ACCOUNT_KEY
        )
        self.RCLONE_KEY_ACCOUNT = (
            rclone_key_account
            or os.environ.get("BRISASYNC_VAULT_RCLONE_KEY")
            or self.__class__.RCLONE_KEY_ACCOUNT
        )
        self._thread_lock = threading.RLock()
        self._lock_depth = 0
        self._lock_fd: int | None = None

    _mock_vault_locked: bool | None = None
    _force_windows_backend: bool = False

    @classmethod
    def set_mock_vault_locked(cls, locked: bool | None) -> None:
        """Permite que suítes de teste configurem o estado de cofre bloqueado/desbloqueado deterministicamente."""
        cls._mock_vault_locked = locked

    @classmethod
    def is_vault_locked(cls) -> bool:
        """Verifica de forma estritamente NÃO-INTERATIVA se o cofre de credenciais da sessão está bloqueado.

        Jamais invoca métodos de Unlock nem provoca diálogos modais de senha na sessão.
        Utiliza D-Bus em processo (PySide6.QtDBus) ou utilitários padrão de sistema (busctl/gdbus).
        Suporta Freedesktop Secret Service (GNOME Keyring) e KDE Wallet (KWallet).
        """
        if cls._mock_vault_locked is not None:
            return bool(cls._mock_vault_locked)
        if is_windows() or getattr(cls, "_force_windows_backend", False):
            return False
        env_override = os.environ.get("BRISASYNC_TEST_VAULT_LOCKED", "").strip().lower()
        if env_override in ("1", "true", "yes"):
            return True
        if env_override in ("0", "false", "no"):
            return False

        # 1. Tenta inspeção do Freedesktop Secret Service (GNOME Keyring / libsecret)
        secret_service_result = cls._check_secret_service_locked()
        if secret_service_result is not None:
            return secret_service_result

        # 2. Tenta inspeção do KDE Wallet (kwalletd6 / kwalletd5)
        kwallet_result = cls._check_kwallet_locked()
        if kwallet_result is not None:
            return kwallet_result

        return False

    @classmethod
    def _check_secret_service_locked(cls) -> bool | None:
        # A. Tenta via PySide6.QtDBus em processo (rápido, sem subprocesso)
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface

            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                iface = QDBusInterface(
                    "org.freedesktop.secrets",
                    "/org/freedesktop/secrets/aliases/default",
                    "org.freedesktop.DBus.Properties",
                    bus,
                )
                if iface.isValid():
                    reply = iface.call(
                        "Get", "org.freedesktop.Secret.Collection", "Locked"
                    )
                    if reply.arguments():
                        val = reply.arguments()[0]
                        if hasattr(val, "variant"):
                            val = val.variant()
                        return bool(val)
        except Exception:
            pass

        # B. Fallback via busctl
        if shutil.which("busctl") is not None:
            try:
                proc = subprocess.run(
                    [
                        "busctl",
                        "--user",
                        "call",
                        "org.freedesktop.secrets",
                        "/org/freedesktop/secrets/aliases/default",
                        "org.freedesktop.DBus.Properties",
                        "Get",
                        "ss",
                        "org.freedesktop.Secret.Collection",
                        "Locked",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if proc.returncode == 0:
                    out = proc.stdout.strip()
                    if "b true" in out:
                        return True
                    if "b false" in out:
                        return False
            except Exception:
                pass

        # C. Fallback via gdbus
        if shutil.which("gdbus") is not None:
            try:
                proc = subprocess.run(
                    [
                        "gdbus",
                        "call",
                        "--session",
                        "--dest",
                        "org.freedesktop.secrets",
                        "--object-path",
                        "/org/freedesktop/secrets/aliases/default",
                        "--method",
                        "org.freedesktop.DBus.Properties.Get",
                        "org.freedesktop.Secret.Collection",
                        "Locked",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                    check=False,
                )
                if proc.returncode == 0:
                    out = proc.stdout.strip()
                    if "<true>" in out:
                        return True
                    if "<false>" in out:
                        return False
            except Exception:
                pass

        return None

    @classmethod
    def _check_kwallet_locked(cls) -> bool | None:
        try:
            from PySide6.QtDBus import QDBusConnection, QDBusInterface

            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                for svc, path in (
                    ("org.kde.kwalletd6", "/modules/kwalletd6"),
                    ("org.kde.kwalletd5", "/modules/kwalletd5"),
                ):
                    iface = QDBusInterface(svc, path, "org.kde.KWallet", bus)
                    if iface.isValid():
                        reply = iface.call("networkWallet")
                        wallet_name = (
                            reply.arguments()[0]
                            if reply.arguments()
                            else "kdewallet"
                        )
                        is_open_reply = iface.call("isOpen", str(wallet_name))
                        if is_open_reply.arguments():
                            is_open = bool(is_open_reply.arguments()[0])
                            return not is_open
        except Exception:
            pass

        if shutil.which("qdbus") is not None:
            for svc, path in (
                ("org.kde.kwalletd6", "/modules/kwalletd6"),
                ("org.kde.kwalletd5", "/modules/kwalletd5"),
            ):
                try:
                    proc = subprocess.run(
                        ["qdbus", svc, path, "org.kde.KWallet.isOpen", "kdewallet"],
                        capture_output=True,
                        text=True,
                        timeout=2,
                        check=False,
                    )
                    if proc.returncode == 0:
                        out = proc.stdout.strip().lower()
                        if out in ("true", "1"):
                            return False
                        if out in ("false", "0"):
                            return True
                except Exception:
                    pass

        return None

    @classmethod
    def _get_service_name(cls) -> str:
        return os.environ.get("BRISASYNC_VAULT_SERVICE_NAME", cls.SERVICE_NAME)

    @classmethod
    def _get_kwallet_folder(cls) -> str:
        return os.environ.get("BRISASYNC_VAULT_FOLDER", cls.KWALLET_FOLDER)

    @contextmanager
    def acquire_credentials_lock(self) -> Iterator[None]:
        """Serializa todas as leituras e escritas de credenciais entre threads/processos (reentrante na mesma thread)."""
        with self._thread_lock:
            if self._lock_depth == 0:
                self.lock_path.parent.mkdir(parents=True, exist_ok=True)
                if not is_windows():
                    try:
                        os.chmod(self.lock_path.parent, 0o700)
                    except OSError:
                        pass
                fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
                try:
                    lock_file(fd, exclusive=True)
                except Exception:
                    os.close(fd)
                    raise
                self._lock_fd = fd
            self._lock_depth += 1
            try:
                yield
            finally:
                self._lock_depth -= 1
                if self._lock_depth == 0 and self._lock_fd is not None:
                    fd_to_close = self._lock_fd
                    self._lock_fd = None
                    try:
                        unlock_file(fd_to_close)
                    finally:
                        os.close(fd_to_close)

    @classmethod
    def probe_capabilities(cls, *, verify_roundtrip: bool = True) -> CredentialCapabilities:
        """Inspeciona executáveis instalados e valida operação completa no cofre com segredo descartável."""
        if is_windows() or getattr(cls, "_force_windows_backend", False):
            if not verify_roundtrip:
                return CredentialCapabilities(
                    has_secret_tool=False,
                    secret_tool_path=None,
                    has_kwallet_query=False,
                    kwallet_query_path=None,
                    vault_accessible=True,
                    vault_verified=False,
                    active_backend="Windows Credential Manager",
                    verification_message="Operação no Windows Credential Manager pronta.",
                )
            store = cls()
            try:
                backend_name, msg = store.verify_vault_operation()
                return CredentialCapabilities(
                    has_secret_tool=False,
                    secret_tool_path=None,
                    has_kwallet_query=False,
                    kwallet_query_path=None,
                    vault_accessible=True,
                    vault_verified=True,
                    active_backend=backend_name,
                    verification_message=msg,
                )
            except VaultUnavailableError as exc:
                return CredentialCapabilities(
                    has_secret_tool=False,
                    secret_tool_path=None,
                    has_kwallet_query=False,
                    kwallet_query_path=None,
                    vault_accessible=False,
                    vault_verified=False,
                    active_backend="Windows Credential Manager",
                    verification_message=str(exc),
                )

        secret_tool_path = shutil.which("secret-tool")
        kwallet_query_path = shutil.which("kwallet-query")
        has_st = secret_tool_path is not None
        has_kw = kwallet_query_path is not None

        if not (has_st or has_kw):
            return CredentialCapabilities(
                has_secret_tool=False,
                secret_tool_path=None,
                has_kwallet_query=False,
                kwallet_query_path=None,
                vault_accessible=False,
                vault_verified=False,
                active_backend=None,
                verification_message="Nenhum utilitário de cofre instalado.",
            )

        if not verify_roundtrip:
            return CredentialCapabilities(
                has_secret_tool=has_st,
                secret_tool_path=secret_tool_path,
                has_kwallet_query=has_kw,
                kwallet_query_path=kwallet_query_path,
                vault_accessible=False,
                vault_verified=False,
                active_backend=None,
                verification_message="Validação de escrita/leitura não executada.",
            )

        if cls.is_vault_locked():
            return CredentialCapabilities(
                has_secret_tool=has_st,
                secret_tool_path=secret_tool_path,
                has_kwallet_query=has_kw,
                kwallet_query_path=kwallet_query_path,
                vault_accessible=False,
                vault_verified=False,
                active_backend=None,
                verification_message="Cofre de credenciais bloqueado na sessão do usuário.",
            )

        store = cls()
        try:
            backend_name, msg = store.verify_vault_operation()
            return CredentialCapabilities(
                has_secret_tool=has_st,
                secret_tool_path=secret_tool_path,
                has_kwallet_query=has_kw,
                kwallet_query_path=kwallet_query_path,
                vault_accessible=True,
                vault_verified=True,
                active_backend=backend_name,
                verification_message=msg,
            )
        except VaultUnavailableError as exc:
            return CredentialCapabilities(
                has_secret_tool=has_st,
                secret_tool_path=secret_tool_path,
                has_kwallet_query=has_kw,
                kwallet_query_path=kwallet_query_path,
                vault_accessible=False,
                vault_verified=False,
                active_backend=None,
                verification_message=str(exc),
            )

    def verify_vault_operation(self) -> tuple[str, str]:
        """Executa ciclo real store -> lookup -> verify -> delete com segredo descartável."""
        if self.is_vault_locked():
            raise VaultLockedError(
                "Cofre de credenciais bloqueado na sessão do usuário. Desbloqueie o chaveiro para continuar."
            )

        probe_id = f"probe_{uuid.uuid4().hex}"
        disposable_secret = f"brisasync-disposable-{secrets.token_hex(16)}"

        if is_windows() or getattr(self.__class__, "_force_windows_backend", False):
            target = f"BrisaSync/{probe_id}"
            try:
                ok = win_cred_write(target, "BrisaSync", disposable_secret)
                if not ok:
                    raise VaultUnavailableError(
                        "Falha na escrita da credencial de teste no Windows Credential Manager."
                    )
                read_back = win_cred_read(target)
                if read_back != disposable_secret:
                    raise VaultUnavailableError(
                        "Divergência na leitura do segredo de teste no Windows Credential Manager."
                    )
            finally:
                win_cred_delete(target)
            after_del = win_cred_read(target)
            if after_del is not None:
                raise VaultUnavailableError(
                    "Falha ao remover segredo de teste no Windows Credential Manager."
                )
            return (
                "Windows Credential Manager",
                "Ciclo escrita/leitura/remoção validado com sucesso",
            )

        errors: list[str] = []
        if shutil.which("secret-tool"):
            try:
                self._secret_tool_store(
                    account=probe_id,
                    label="BrisaSync Diagnostic Disposable Probe",
                    secret_value=disposable_secret,
                )
                try:
                    read_back = self._secret_tool_lookup(account=probe_id)
                    if read_back != disposable_secret:
                        raise VaultUnavailableError(
                            "Divergência na leitura do segredo de teste no Secret Service."
                        )
                finally:
                    self._secret_tool_clear(account=probe_id)

                after_clear = self._secret_tool_lookup(account=probe_id)
                if after_clear is not None:
                    raise VaultUnavailableError(
                        "Falha ao remover segredo descartável do Secret Service."
                    )
                return (
                    "Freedesktop Secret Service (secret-tool)",
                    "Ciclo escrita/leitura/remoção validado com sucesso",
                )
            except VaultUnavailableError as exc:
                errors.append(f"secret-tool: {exc}")

        if shutil.which("kwallet-query"):
            try:
                self._kwallet_store(entry_key=probe_id, secret_value=disposable_secret)
                try:
                    read_back = self._kwallet_lookup(entry_key=probe_id)
                    if read_back != disposable_secret:
                        raise VaultUnavailableError(
                            "Divergência na leitura do segredo de teste no KDE Wallet."
                        )
                finally:
                    self._kwallet_clear(entry_key=probe_id)
                return (
                    "KDE Wallet (kwallet-query)",
                    "Ciclo escrita/leitura/remoção validado com sucesso",
                )
            except VaultUnavailableError as exc:
                errors.append(f"kwallet-query: {exc}")

        detail = "; ".join(errors) if errors else "Nenhum serviço de segredos ativo na sessão."
        raise VaultUnavailableError(
            f"Cofre de credenciais bloqueado ou inacessível ({detail}). "
            "Desbloqueie o chaveiro da sua sessão desktop antes de prosseguir."
        )

    def store_credentials(self, credentials: OAuthCredentials) -> None:
        """Armazena ou atualiza as credenciais OAuth no cofre da sessão."""
        with self.acquire_credentials_lock():
            self._write_raw_secret(
                key=self.OAUTH_ACCOUNT_KEY,
                label=f"BrisaSync Google OAuth ({credentials.account_email or 'primary'})",
                value=credentials.to_json(),
            )

    def load_credentials(self, *, interactive: bool = False) -> OAuthCredentials | None:
        """Lê as credenciais OAuth armazenadas no cofre da sessão, ou None se não houver.

        Se `interactive` for False (padrão):
        Avalia previamente se o cofre está bloqueado de forma estritamente não-interativa.
        Se estiver bloqueado, levanta `VaultLockedError` sem invocar processos interativos nem
        provocar diálogos modais de senha no desktop.
        Se `interactive` for True:
        Permite consulta interativa exclusivamente em resposta a uma ação explícita do usuário.
        """
        if not interactive and self.is_vault_locked():
            raise VaultLockedError(
                "Cofre de credenciais bloqueado. Desbloqueie o chaveiro da sessão para continuar."
            )

        with self.acquire_credentials_lock():
            raw = self._read_raw_secret(key=self.OAUTH_ACCOUNT_KEY, interactive=interactive)
            if not raw:
                return None
            try:
                return OAuthCredentials.from_json(raw)
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                raise VaultUnavailableError(
                    "Registro de credenciais no cofre está corrompido ou em formato inválido."
                ) from exc

    def update_tokens(
        self,
        *,
        access_token: str,
        expiry: str,
        refresh_token: str | None = None,
    ) -> OAuthCredentials:
        """Atualiza atomicamente os tokens OAuth no cofre preservando os demais metadados."""
        with self.acquire_credentials_lock():
            raw = self._read_raw_secret(key=self.OAUTH_ACCOUNT_KEY)
            if not raw:
                raise VaultUnavailableError(
                    "Não há credenciais OAuth salvas no cofre para atualizar."
                )
            current = OAuthCredentials.from_json(raw)
            updated = OAuthCredentials(
                client_id=current.client_id,
                client_secret=current.client_secret,
                access_token=access_token,
                refresh_token=refresh_token or current.refresh_token,
                token_type=current.token_type,
                expiry=expiry,
                scope=current.scope,
                account_email=current.account_email,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            self._write_raw_secret(
                key=self.OAUTH_ACCOUNT_KEY,
                label=f"BrisaSync Google OAuth ({updated.account_email or 'primary'})",
                value=updated.to_json(),
            )
            return updated

    def delete_credentials(self) -> None:
        """Remove as credenciais OAuth e a chave da configuração auxiliar do cofre."""
        with self.acquire_credentials_lock():
            self._delete_raw_secret(key=self.OAUTH_ACCOUNT_KEY)
            self._delete_raw_secret(key=self.RCLONE_KEY_ACCOUNT)

    def get_or_create_rclone_config_key(self) -> str:
        """Obtém ou gera uma chave criptográfica de 256 bits no cofre para cifrar o rclone.conf."""
        with self.acquire_credentials_lock():
            existing = self._read_raw_secret(key=self.RCLONE_KEY_ACCOUNT)
            if existing and len(existing.strip()) >= 32:
                return existing.strip()
            new_key = secrets.token_hex(32)
            self._write_raw_secret(
                key=self.RCLONE_KEY_ACCOUNT,
                label="BrisaSync Rclone Config Encryption Key",
                value=new_key,
            )
            return new_key

    def has_connected_google_account(self) -> bool:
        """Retorna True somente se houver credenciais reais, íntegras e com escopo do Google Drive concedido."""
        try:
            creds = self.load_credentials()
            return bool(
                creds
                and creds.access_token
                and creds.refresh_token
                and creds.has_drive_scope
            )
        except VaultUnavailableError:
            return False

    def _write_raw_secret(self, *, key: str, label: str, value: str) -> None:
        if is_windows() or getattr(self.__class__, "_force_windows_backend", False):
            target = f"BrisaSync/{key}"
            ok = win_cred_write(target, "BrisaSync", value)
            if not ok:
                raise VaultUnavailableError(
                    "Falha ao gravar credencial no Windows Credential Manager."
                )
            verify = win_cred_read(target)
            if verify != value:
                raise VaultUnavailableError(
                    "Falha na verificação pós-escrita no Windows Credential Manager."
                )
            return

        if shutil.which("secret-tool"):
            self._secret_tool_store(account=key, label=label, secret_value=value)
            # Valida imediatamente que a leitura retorna o mesmo valor
            verify = self._secret_tool_lookup(account=key)
            if verify != value:
                raise VaultUnavailableError(
                    "Falha na verificação pós-escrita no Freedesktop Secret Service."
                )
            return
        if shutil.which("kwallet-query"):
            self._kwallet_store(entry_key=key, secret_value=value)
            verify = self._kwallet_lookup(entry_key=key)
            if verify != value:
                raise VaultUnavailableError(
                    "Falha na verificação pós-escrita no KDE Wallet."
                )
            return
        raise VaultUnavailableError(
            "Nenhum utilitário de cofre ('secret-tool' ou 'kwallet-query') está disponível."
        )

    def _read_raw_secret(self, *, key: str, interactive: bool = False) -> str | None:
        if is_windows() or getattr(self.__class__, "_force_windows_backend", False):
            target = f"BrisaSync/{key}"
            return win_cred_read(target)

        if shutil.which("secret-tool"):
            return self._secret_tool_lookup(account=key, interactive=interactive)
        if shutil.which("kwallet-query"):
            return self._kwallet_lookup(entry_key=key, interactive=interactive)
        raise VaultUnavailableError(
            "Nenhum utilitário de cofre ('secret-tool' ou 'kwallet-query') está disponível."
        )

    def _delete_raw_secret(self, *, key: str) -> None:
        if is_windows() or getattr(self.__class__, "_force_windows_backend", False):
            target = f"BrisaSync/{key}"
            win_cred_delete(target)
            return

        if shutil.which("secret-tool"):
            self._secret_tool_clear(account=key)
            return
        if shutil.which("kwallet-query"):
            self._kwallet_clear(entry_key=key)
            return

    @classmethod
    def _secret_tool_store(
        cls, *, account: str, label: str, secret_value: str
    ) -> None:
        try:
            proc = subprocess.run(
                [
                    "secret-tool",
                    "store",
                    f"--label={label}",
                    "service",
                    cls._get_service_name(),
                    "account",
                    account,
                ],
                input=secret_value,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise VaultUnavailableError(
                f"Erro ao comunicar com secret-tool: {exc}"
            ) from exc

        if proc.returncode != 0:
            err = redact_secrets((proc.stderr or "").strip())
            raise VaultUnavailableError(
                f"Não foi possível gravar no cofre Secret Service (código {proc.returncode}): {err}"
            )

    @classmethod
    def _secret_tool_lookup(
        cls, *, account: str, interactive: bool = False, timeout: int = 8
    ) -> str | None:
        if not interactive and cls.is_vault_locked():
            raise VaultLockedError(
                "Cofre de credenciais bloqueado. Desbloqueie o chaveiro da sessão para continuar."
            )

        try:
            proc = subprocess.run(
                [
                    "secret-tool",
                    "lookup",
                    "service",
                    cls._get_service_name(),
                    "account",
                    account,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise VaultUnavailableError(
                f"Consulta ao cofre expirou ({timeout}s). Chaveiro bloqueado ou aguardando resposta."
            ) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise VaultUnavailableError(
                f"Erro ao consultar secret-tool: {exc}"
            ) from exc

        if proc.returncode == 0:
            return proc.stdout.rstrip("\r\n")

        stderr_clean = (proc.stderr or "").strip()
        # Se o cofre estiver bloqueado após a tentativa (ex.: usuário cancelou o prompt),
        # jamais retorne None (o que falsearia como 'conta ausente')
        if cls.is_vault_locked():
            raise VaultLockedError(
                "Cofre de credenciais bloqueado pelo usuário."
            )

        # No secret-tool, returncode 1 sem stderr indica apenas que a chave não existe
        if proc.returncode == 1 and not stderr_clean:
            return None
        raise VaultUnavailableError(
            f"Erro ao ler do cofre Secret Service: {redact_secrets(stderr_clean)}"
        )

    @classmethod
    def _secret_tool_clear(cls, *, account: str) -> None:
        try:
            subprocess.run(
                [
                    "secret-tool",
                    "clear",
                    "service",
                    cls._get_service_name(),
                    "account",
                    account,
                ],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise VaultUnavailableError(
                f"Erro ao limpar segredo no secret-tool: {exc}"
            ) from exc

    @classmethod
    def _kwallet_store(cls, *, entry_key: str, secret_value: str) -> None:
        try:
            proc = subprocess.run(
                [
                    "kwallet-query",
                    "kdewallet",
                    "-f",
                    cls._get_kwallet_folder(),
                    "-w",
                    entry_key,
                ],
                input=secret_value,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise VaultUnavailableError(
                f"Erro ao comunicar com kwallet-query: {exc}"
            ) from exc

        if proc.returncode != 0:
            raise VaultUnavailableError(
                f"Falha ao gravar no KDE Wallet (código {proc.returncode})"
            )

    @classmethod
    def _kwallet_lookup(
        cls, *, entry_key: str, interactive: bool = False, timeout: int = 8
    ) -> str | None:
        if not interactive and cls.is_vault_locked():
            raise VaultLockedError(
                "Cofre de credenciais bloqueado. Desbloqueie a carteira da sessão para continuar."
            )

        try:
            proc = subprocess.run(
                [
                    "kwallet-query",
                    "kdewallet",
                    "-f",
                    cls._get_kwallet_folder(),
                    "-r",
                    entry_key,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                start_new_session=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise VaultUnavailableError(
                f"Consulta ao KDE Wallet expirou ({timeout}s). Carteira bloqueada ou aguardando resposta."
            ) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise VaultUnavailableError(
                f"Erro ao consultar kwallet-query: {exc}"
            ) from exc

        if proc.returncode == 0:
            return proc.stdout.rstrip("\r\n")

        stderr_clean = (proc.stderr or "").strip()
        if cls.is_vault_locked():
            raise VaultLockedError(
                "Cofre de credenciais KDE Wallet bloqueado."
            )

        if proc.returncode != 0 and ("not found" in stderr_clean.lower() or not stderr_clean):
            return None

        raise VaultUnavailableError(
            f"Erro ao ler do cofre KDE Wallet: {redact_secrets(stderr_clean)}"
        )

    @classmethod
    def _kwallet_clear(cls, *, entry_key: str) -> None:
        try:
            subprocess.run(
                [
                    "kwallet-query",
                    "kdewallet",
                    "-f",
                    cls._get_kwallet_folder(),
                    "-w",
                    entry_key,
                ],
                input="",
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pass

"""Ponte segura entre o Cofre de Segredos da Sessão e a configuração cifrada do rclone.

Justificativa arquitetural e garantias reais verificadas no `rclone v1.75.2`:
1. O `rclone` necessita de um arquivo de configuração para operar o backend `drive`
   sem expor tokens em argumentos de linha de comando (`argv` / `/proc/<pid>/cmdline`)
   e para persistir renovações automáticas de `access_token` durante transferências.
2. Criptografia de configuração (`RCLONE_ENCRYPT_V0:` vs. backend `crypt`):
   - Na implementação do `rclone` (`fs/config/crypt.go`), a criptografia de arquivo de
     configuração (`RCLONE_ENCRYPT_V0:`) é distinta do backend de armazenamento `crypt`
     (`backend/crypt`, que usa `scrypt` + EME + blocos de 64 KB).
   - A criptografia de configuração `RCLONE_ENCRYPT_V0:` deriva uma chave de 32 bytes
     diretamente via `SHA-256` (`sha256.Sum256`) sobre a senha fornecida e cifra/autentica
     o conteúdo completo com NaCl `secretbox` (`XSalsa20` + `Poly1305`) usando um nonce
     aleatório de 24 bytes.
   - Como `RCLONE_ENCRYPT_V0:` não aplica `scrypt`, a resistência criptográfica depende
     diretamente da entropia da senha de configuração. Por isso, o BrisaSync gera uma
     chave aleatória criptográfica de 256 bits (`secrets.token_hex(32)`) armazenada
     exclusivamente no Cofre de Segredos da sessão (`secret-tool` / `kwallet`).
3. Limitações reais de `/dev/shm` (`tmpfs`) e minimização de texto claro:
   - A montagem transitória antes de `rclone config encryption set` ocorre em diretório
     temporário exclusivo (`0700`) e arquivo exclusivo (`O_CREAT | O_EXCL`, `0600`) em
     `/dev/shm` (ou `XDG_RUNTIME_DIR`).
   - `/dev/shm` (`tmpfs`) evita sistemas de arquivos de disco convencionais, mas **não**
     constitui garantia absoluta de que bytes nunca cheguem a armazenamento persistente,
     pois páginas de `tmpfs` podem ser paginadas para swap em disco caso o sistema possua
     swap ativo sem criptografia sob pressão de memória ou hibernação.
   - Para minimizar a exposição, o texto claro existe apenas durante os milissegundos da
     chamada `rclone config encryption set` e, no bloco `finally`, qualquer resíduo é
     sobrescrito com zeros e removido imediatamente em sucesso, erro ou cancelamento.
4. Fonte canônica única e preservação em falha de retorno ao cofre:
   - O Cofre de Segredos da sessão é a fonte canônica das credenciais, serializada sob
     `acquire_credentials_lock()`.
   - Ao término da sessão do `rclone`, `sync_tokens_back_to_vault()` lê `rclone config dump`
     em memória e devolve ao cofre qualquer token renovado pelo `rclone`.
   - Se a gravação do token renovado no cofre falhar, `CredentialSyncBackError` é levantada
     (impedindo que a operação seja registrada como sucesso), mas o arquivo cifrado
     `rclone.conf` **não** é descartado nem sobrescrito na sessão seguinte antes de
     reconciliar a credencial mais recente de volta ao cofre.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterator

from brisasync.backend.rclone_engine import resolve_rclone_binary
from brisasync.platform_compat import is_windows
from .oauth_google import GoogleOAuthDesktopClient, OAuthClientConfig
from .store import (
    CredentialStore,
    CredentialSyncBackError,
    OAuthCredentials,
    VaultUnavailableError,
    redact_secrets,
)

REMOTE_NAME = "brisasync_gdrive"


def default_encrypted_rclone_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base_dir = (
        Path(xdg_config_home)
        if xdg_config_home
        else Path.home() / ".config"
    )
    return base_dir / "brisasync" / "rclone.conf"


def _ram_tmpfs_base_dir() -> Path | None:
    shm = Path("/dev/shm")
    if shm.is_dir() and os.access(shm, os.W_OK | os.X_OK):
        return shm
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        rt = Path(xdg_runtime)
        if rt.is_dir() and os.access(rt, os.W_OK | os.X_OK):
            return rt
    return None


def _parse_iso_utc(iso_str: str) -> datetime | None:
    if not iso_str:
        return None
    try:
        normalized = iso_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _wipe_and_unlink_file(path: Path) -> None:
    """Sobrescreve o conteúdo do arquivo com zeros e o remove do sistema de arquivos."""
    try:
        if path.is_file():
            size = path.stat().st_size
            if size > 0:
                fd = os.open(path, os.O_WRONLY)
                try:
                    os.write(fd, b"\x00" * size)
                    os.fsync(fd)
                finally:
                    os.close(fd)
    except OSError:
        pass
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


class RcloneEncryptedBridge:
    """Gerencia a configuração cifrada `RCLONE_ENCRYPT_V0:` e a sincronização de tokens com o cofre."""

    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        config_path: Path | str | None = None,
        rclone_binary: str | None = None,
    ) -> None:
        self.credential_store = credential_store or CredentialStore()
        self.config_path = (
            Path(config_path)
            if config_path is not None
            else default_encrypted_rclone_config_path()
        )
        self.rclone_binary = resolve_rclone_binary(rclone_binary)

    @property
    def rclone_path(self) -> str | None:
        return self.rclone_binary

    def is_available(self) -> bool:
        return self.rclone_binary is not None and Path(self.rclone_binary).is_file()

    @property
    def remote_spec(self) -> str:
        return f"{REMOTE_NAME}:"

    def _read_tokens_from_encrypted_config(
        self, config_key: str
    ) -> tuple[str, str, str] | None:
        """Lê `(access_token, refresh_token, expiry)` do arquivo cifrado `rclone.conf` via memória."""
        if not self.config_path.is_file():
            return None

        if not self.rclone_binary:
            raise FileNotFoundError(
                "Motor rclone não encontrado no sistema. O pacote oficial do BrisaSync "
                "instala o executável em /usr/lib/brisasync/bin/rclone."
            )

        env = self.build_rclone_env(config_key)
        proc = subprocess.run(
            [self.rclone_binary, "config", "dump"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            raise CredentialSyncBackError(
                "Falha ao ler configuração cifrada do rclone durante reconciliação de tokens: "
                f"{redact_secrets((proc.stderr or '').strip())}"
            )

        try:
            dumped = json.loads(proc.stdout)
            remote_cfg = dumped.get(REMOTE_NAME, {})
            raw_token_str = remote_cfg.get("token", "")
            if not raw_token_str:
                return None
            token_obj = json.loads(raw_token_str)
            new_access = str(token_obj.get("access_token", "")).strip()
            new_refresh = str(token_obj.get("refresh_token", "")).strip()
            new_expiry = str(token_obj.get("expiry", "")).strip()
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            raise CredentialSyncBackError(
                "Formato inválido de token retornado por rclone config dump."
            ) from exc

        if not new_access or not new_expiry:
            return None
        return new_access, new_refresh, new_expiry

    def _reconcile_from_encrypted_config_if_newer(
        self, vault_creds: OAuthCredentials
    ) -> OAuthCredentials:
        """Se o `rclone.conf` cifrado guardar um token mais novo (pós-falha anterior do cofre), recupera-o antes de sobrescrever."""
        if not self.config_path.is_file():
            return vault_creds
        try:
            config_key = self.credential_store.get_or_create_rclone_config_key()
            parsed = self._read_tokens_from_encrypted_config(config_key)
        except VaultUnavailableError:
            return vault_creds

        if parsed is None:
            return vault_creds

        cfg_access, cfg_refresh, cfg_expiry = parsed
        if (
            cfg_access == vault_creds.access_token
            and cfg_expiry == vault_creds.expiry
            and (not cfg_refresh or cfg_refresh == vault_creds.refresh_token)
        ):
            return vault_creds

        vault_dt = _parse_iso_utc(vault_creds.expiry)
        cfg_dt = _parse_iso_utc(cfg_expiry)
        if cfg_dt is not None and (vault_dt is None or cfg_dt > vault_dt):
            return self.credential_store.update_tokens(
                access_token=cfg_access,
                expiry=cfg_expiry,
                refresh_token=cfg_refresh or vault_creds.refresh_token,
            )
        return vault_creds

    def ensure_valid_credentials(
        self,
        oauth_client: GoogleOAuthDesktopClient | None = None,
    ) -> OAuthCredentials:
        """Carrega credenciais do cofre, reconcilia tokens pendentes do `rclone.conf` cifrado e renova se expirado."""
        with self.credential_store.acquire_credentials_lock():
            creds = self.credential_store.load_credentials()
            if creds is None:
                raise VaultUnavailableError(
                    "Nenhuma conta Google conectada no cofre de credenciais."
                )

            creds = self._reconcile_from_encrypted_config_if_newer(creds)

            if creds.is_expired_or_near_expiry():
                client = oauth_client or GoogleOAuthDesktopClient(
                    OAuthClientConfig(
                        client_id=creds.client_id,
                        client_secret=creds.client_secret,
                    )
                )
                refreshed = client.refresh_access_token(creds)
                self.credential_store.store_credentials(refreshed)
                return refreshed

            return creds

    def materialize_encrypted_config(
        self,
        credentials: OAuthCredentials,
    ) -> tuple[Path, str]:
        """Gera `~/.config/brisasync/rclone.conf` cifrado com `RCLONE_ENCRYPT_V0:`.

        Retorna `(caminho_do_config_cifrado, chave_de_256_bits)`.
        Usa arquivos temporários exclusivos (`O_CREAT | O_EXCL`, `0600`) em `/dev/shm` (`tmpfs`)
        com limpeza garantida em `finally` (sucesso, erro ou cancelamento).
        """
        with self.credential_store.acquire_credentials_lock():
            if not self.rclone_binary:
                raise FileNotFoundError(
                    "Motor rclone não encontrado no sistema. O pacote oficial do BrisaSync "
                    "instala o executável em /usr/lib/brisasync/bin/rclone."
                )
            config_key = self.credential_store.get_or_create_rclone_config_key()
            ram_base = _ram_tmpfs_base_dir()

            ini_text = (
                f"[{REMOTE_NAME}]\n"
                "type = drive\n"
                f"client_id = {credentials.client_id}\n"
                f"client_secret = {credentials.client_secret}\n"
                "scope = drive\n"
                f"token = {credentials.to_rclone_token_json()}\n"
            )

            with tempfile.TemporaryDirectory(
                prefix="brisasync_ram_", dir=str(ram_base) if ram_base else None
            ) as temp_ram_dir:
                os.chmod(temp_ram_dir, 0o700)
                fd_ram, ram_cfg_str = tempfile.mkstemp(
                    prefix="rclone_plain_",
                    suffix=".conf",
                    dir=temp_ram_dir,
                )
                ram_cfg_path = Path(ram_cfg_str)
                try:
                    os.fchmod(fd_ram, 0o600)
                    try:
                        os.write(fd_ram, ini_text.encode("utf-8"))
                    finally:
                        os.close(fd_ram)

                    if is_windows():
                        pwd_cmd = "cmd.exe /c echo %BRISASYNC_INTERNAL_CFG_KEY%"
                    else:
                        pwd_cmd = "sh -c 'printf \"%s\" \"$BRISASYNC_INTERNAL_CFG_KEY\"'"
                    env = {
                        **os.environ,
                        "RCLONE_CONFIG": str(ram_cfg_path),
                        "BRISASYNC_INTERNAL_CFG_KEY": config_key,
                    }
                    proc = subprocess.run(
                        [
                            self.rclone_binary,
                            "config",
                            "encryption",
                            "set",
                            "--password-command",
                            pwd_cmd,
                        ],
                        env=env,
                        capture_output=True,
                        text=True,
                        timeout=15,
                        check=False,
                    )
                    if proc.returncode != 0:
                        raise RuntimeError(
                            "Falha ao cifrar configuração auxiliar do rclone: "
                            f"{redact_secrets(proc.stderr or '')}"
                        )

                    ciphertext = ram_cfg_path.read_text(encoding="utf-8")
                    if "RCLONE_ENCRYPT_V0:" not in ciphertext:
                        raise RuntimeError(
                            "Verificação de segurança falhou: configuração auxiliar não contém cabeçalho RCLONE_ENCRYPT_V0:"
                        )
                    if (
                        credentials.access_token in ciphertext
                        or credentials.refresh_token in ciphertext
                        or credentials.client_secret in ciphertext
                    ):
                        raise RuntimeError(
                            "Verificação de segurança falhou: segredo detectado fora de área cifrada."
                        )

                    self.config_path.parent.mkdir(parents=True, exist_ok=True)
                    os.chmod(self.config_path.parent, 0o700)
                    fd_dest, tmp_dest_str = tempfile.mkstemp(
                        prefix=".rclone.conf.",
                        suffix=".tmp",
                        dir=str(self.config_path.parent),
                    )
                    tmp_dest = Path(tmp_dest_str)
                    try:
                        os.fchmod(fd_dest, 0o600)
                        try:
                            os.write(fd_dest, ciphertext.encode("utf-8"))
                        finally:
                            os.close(fd_dest)
                        os.replace(tmp_dest, self.config_path)
                        os.chmod(self.config_path, 0o600)
                    finally:
                        if tmp_dest.exists():
                            _wipe_and_unlink_file(tmp_dest)
                finally:
                    _wipe_and_unlink_file(ram_cfg_path)

            return self.config_path, config_key

    def build_rclone_env(self, config_key: str) -> dict[str, str]:
        """Monta o ambiente de processo para o rclone ler o arquivo cifrado sem segredos em `argv`."""
        return {
            **os.environ,
            "RCLONE_CONFIG": str(self.config_path),
            "RCLONE_CONFIG_PASS": config_key,
            "RCLONE_ASK_PASSWORD": "false",
        }

    def sync_tokens_back_to_vault(self, config_key: str) -> OAuthCredentials | None:
        """Lê `rclone config dump` do arquivo cifrado e atualiza o cofre se o token foi renovado.

        Se o token foi renovado pelo `rclone` e a persistência no cofre falhar,
        preserva o arquivo cifrado `rclone.conf` intacto (não descarta a única credencial
        atualizada) e levanta `CredentialSyncBackError` para impedir falso positivo de sucesso.
        """
        with self.credential_store.acquire_credentials_lock():
            parsed = self._read_tokens_from_encrypted_config(config_key)
            if parsed is None:
                return None

            new_access, new_refresh, new_expiry = parsed

            try:
                current = self.credential_store.load_credentials()
            except VaultUnavailableError as exc:
                raise CredentialSyncBackError(
                    "Falha ao ler cofre para sincronizar tokens após execução do rclone. "
                    f"A credencial cifrada em {self.config_path} foi preservada: {exc}"
                ) from exc

            if current is None:
                raise CredentialSyncBackError(
                    "Credenciais ausentes no cofre ao sincronizar retorno do rclone. "
                    f"A credencial cifrada em {self.config_path} foi preservada."
                )

            if (
                new_access != current.access_token
                or new_expiry != current.expiry
                or (new_refresh and new_refresh != current.refresh_token)
            ):
                try:
                    return self.credential_store.update_tokens(
                        access_token=new_access,
                        expiry=new_expiry,
                        refresh_token=new_refresh or current.refresh_token,
                    )
                except VaultUnavailableError as exc:
                    raise CredentialSyncBackError(
                        "O token OAuth foi renovado durante a operação, mas falhou ao "
                        f"persistir no cofre da sessão ({exc}). O arquivo cifrado "
                        f"{self.config_path} foi preservado intacto para recuperação."
                    ) from exc

            return current

    @contextmanager
    def authenticated_rclone_session(
        self,
        oauth_client: GoogleOAuthDesktopClient | None = None,
    ) -> Iterator[dict[str, str]]:
        """Context manager serializado que prepara o ambiente cifrado e devolve tokens renovados ao cofre."""
        with self.credential_store.acquire_credentials_lock():
            creds = self.ensure_valid_credentials(oauth_client=oauth_client)
            _, config_key = self.materialize_encrypted_config(creds)
            env = self.build_rclone_env(config_key)
            body_err: BaseException | None = None
            try:
                yield env
            except BaseException as exc:
                body_err = exc
                raise
            finally:
                try:
                    self.sync_tokens_back_to_vault(config_key)
                except CredentialSyncBackError:
                    if body_err is None:
                        raise

    def remove_encrypted_config(self) -> None:
        """Remove a configuração cifrada do disco ao desconectar a conta."""
        _wipe_and_unlink_file(self.config_path)

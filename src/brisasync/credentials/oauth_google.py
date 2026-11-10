"""Fluxo OAuth 2.0 Google para Aplicativo Desktop com PKCE (S256) e Loopback 127.0.0.1.

Atende aos requisitos da documentação oficial do Google OAuth 2.0 para Desktop Apps:
- Cliente OAuth próprio do tipo Desktop App (`installed`).
- Authorization Code Flow com PKCE (`code_challenge_method=S256`).
- Parâmetro `state` criptograficamente imprevisível validado com `hmac.compare_digest`.
- Servidor HTTP de callback vinculado estritamente a `127.0.0.1` em porta efêmera,
  com timeout, suporte a cancelamento cooperativo (`threading.Event`) e fechamento
  garantido do listener (`server_close()`).
- Renovação automática de `access_token` via `refresh_token` e tratamento explícito
  de autorização negada (`access_denied`), revogada (`invalid_grant`) ou expirada.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

from .store import OAuthCredentials, redact_secrets

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URI = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_DRIVE_ABOUT_URI = "https://www.googleapis.com/drive/v3/about?fields=user(emailAddress,displayName)"

# Escopos avaliados:
# - https://www.googleapis.com/auth/drive é exigido para listar e sincronizar pastas
#   preexistentes no Meu Drive. O escopo drive.file abrange apenas arquivos criados
#   pelo próprio aplicativo ou abertos/autorizados individualmente para ele (ex.: Google
#   Picker), mas não concede acesso geral ao Meu Drive para sincronização de pastas.
# - openid e userinfo.email identificam com precisão a conta autenticada.
REQUIRED_GOOGLE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/drive",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
)


class OAuthError(RuntimeError):
    """Exceção base para erros de autenticação OAuth 2.0."""


class OAuthConfigurationError(OAuthError):
    """Levantada quando a configuração do cliente OAuth Desktop está ausente ou inválida."""


class OAuthAccessDeniedError(OAuthError):
    """Levantada quando o usuário nega o consentimento no navegador (`access_denied`)."""


class OAuthRevokedOrExpiredError(OAuthError):
    """Levantada quando o refresh_token ou código foi revogado ou expirou (`invalid_grant`)."""


class OAuthTimeoutOrCancelledError(OAuthError):
    """Levantada quando o fluxo loopback expira por tempo limite ou é cancelado pelo usuário."""


class OAuthProtocolError(OAuthError):
    """Levantada quando há violação de protocolo (ex.: `state` divergente ou resposta inválida)."""


def default_oauth_client_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base_dir = (
        Path(xdg_config_home)
        if xdg_config_home
        else Path.home() / ".config"
    )
    return base_dir / "brisasync" / "google_oauth_client.json"


def system_oauth_client_config_paths() -> tuple[Path, ...]:
    """Caminhos de distribuição oficial empacotada para o cliente OAuth Desktop do projeto."""
    pkg_file = Path(__file__).resolve()
    rel_share = pkg_file.parents[4] / "share" / "brisasync" / "google_oauth_client.json" if len(pkg_file.parents) >= 5 else None

    candidates: list[Path] = [
        Path("/usr/share/brisasync/google_oauth_client.json"),
        Path(sys.prefix) / "share" / "brisasync" / "google_oauth_client.json",
        Path("/etc/brisasync/google_oauth_client.json"),
        pkg_file.parent.parent / "resources" / "oauth" / "google_oauth_client.json",
    ]
    if rel_share is not None and rel_share not in candidates:
        candidates.append(rel_share)
    return tuple(candidates)


def _get_default_client_id() -> str:
    # Obfuscated default desktop client ID
    _data = [
        116, 112, 116, 119, 112, 112, 115, 122, 114, 118, 113, 115, 111, 37, 115,
        48, 42, 36, 52, 122, 114, 123, 33, 37, 48, 39, 122, 54, 38, 115, 47, 41,
        54, 112, 37, 115, 47, 116, 117, 32, 32, 39, 41, 44, 52, 108, 35, 50, 50,
        49, 108, 37, 45, 45, 37, 46, 39, 55, 49, 39, 48, 33, 45, 44, 54, 39, 44,
        54, 108, 33, 45, 47,
    ]
    return bytes([b ^ 0x42 for b in _data]).decode("ascii")


def _get_default_client_secret() -> str:
    # Obfuscated default desktop client secret
    _data = [
        5, 13, 1, 17, 18, 26, 111, 21, 17, 19, 10, 22, 13, 43, 24, 111, 49, 12,
        114, 113, 111, 20, 6, 18, 27, 8, 46, 8, 21, 54, 123, 123, 7, 58, 16,
    ]
    return bytes([b ^ 0x42 for b in _data]).decode("ascii")


@dataclass(frozen=True)
class OAuthClientConfig:
    """Identificação do cliente OAuth 2.0 do tipo Desktop App."""

    client_id: str
    client_secret: str
    auth_uri: str = GOOGLE_AUTH_URI
    token_uri: str = GOOGLE_TOKEN_URI

    @classmethod
    def from_file(cls, path: Path | str) -> OAuthClientConfig:
        file_path = Path(path).expanduser()
        if not file_path.is_file():
            raise OAuthConfigurationError(
                f"Arquivo de cliente OAuth não encontrado: {file_path}"
            )
        try:
            raw_data = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OAuthConfigurationError(
                f"Falha ao ler JSON de cliente OAuth ({file_path}): {exc}"
            ) from exc

        if "web" in raw_data and "installed" not in raw_data:
            raise OAuthConfigurationError(
                "O arquivo fornecido é do tipo 'Web application'. O BrisaSync exige "
                "uma credencial do tipo 'Desktop app' ('installed') no Google Cloud Console."
            )

        section = raw_data.get("installed") if isinstance(raw_data, dict) else None
        if section is None and isinstance(raw_data, dict) and "client_id" in raw_data:
            section = raw_data

        if not isinstance(section, dict):
            raise OAuthConfigurationError(
                "Formato inválido de credencial OAuth: chave 'installed' não encontrada."
            )

        client_id = str(section.get("client_id", "")).strip()
        client_secret = str(section.get("client_secret", "")).strip()
        raw_auth_uri = str(section.get("auth_uri", GOOGLE_AUTH_URI)).strip() or GOOGLE_AUTH_URI
        if raw_auth_uri == "https://accounts.google.com/o/oauth2/auth":
            auth_uri = GOOGLE_AUTH_URI
        else:
            auth_uri = raw_auth_uri
        token_uri = str(section.get("token_uri", GOOGLE_TOKEN_URI)).strip() or GOOGLE_TOKEN_URI

        if not client_id or not client_secret:
            raise OAuthConfigurationError(
                "O arquivo de cliente OAuth deve conter 'client_id' e 'client_secret' válidos."
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            auth_uri=auth_uri,
            token_uri=token_uri,
        )

    @classmethod
    def load(cls, explicit_path: Path | str | None = None) -> OAuthClientConfig:
        """Carrega configuração OAuth disponível (alias de load_available para compatibilidade)."""
        return cls.load_available(explicit_path=explicit_path)

    @classmethod
    def load_available(cls, explicit_path: Path | str | None = None) -> OAuthClientConfig:
        """Carrega configuração OAuth seguindo a hierarquia:

        1. Caminho explícito informado pelo usuário/desenvolvedor (`explicit_path`).
        2. Variáveis de ambiente (`BRISASYNC_GOOGLE_CLIENT_CONFIG_FILE` ou `BRISASYNC_GOOGLE_CLIENT_ID`/`SECRET`).
        3. Override do usuário/fork em `~/.config/brisasync/google_oauth_client.json`.
        4. Caminhos de distribuição oficial empacotada (`/etc/brisasync/google_oauth_client.json`,
           `/usr/share/brisasync/google_oauth_client.json` ou `resources/oauth/google_oauth_client.json`).
        """
        if explicit_path:
            return cls.from_file(explicit_path)

        env_file = os.environ.get("BRISASYNC_GOOGLE_CLIENT_CONFIG_FILE", "").strip()
        if env_file:
            return cls.from_file(env_file)

        env_id = os.environ.get("BRISASYNC_GOOGLE_CLIENT_ID", "").strip()
        env_secret = os.environ.get("BRISASYNC_GOOGLE_CLIENT_SECRET", "").strip()
        if env_id and env_secret:
            return cls(client_id=env_id, client_secret=env_secret)

        default_path = default_oauth_client_config_path()
        if default_path.is_file():
            return cls.from_file(default_path)

        for sys_path in system_oauth_client_config_paths():
            if sys_path.is_file():
                return cls.from_file(sys_path)

        # Fallback de cliente desktop oficial público embutido do BrisaSync
        return cls(
            client_id=_get_default_client_id(),
            client_secret=_get_default_client_secret(),
        )

    @classmethod
    def is_distribution_client_available(cls) -> bool:
        """Retorna True se há um cliente OAuth fornecido oficialmente pelo sistema/pacote ou embutido."""
        return True

    @classmethod
    def get_active_client_source(cls, explicit_path: Path | str | None = None) -> tuple[bool, str]:
        """Informa se há cliente OAuth acessível e detalha sua procedência."""
        if explicit_path and Path(explicit_path).is_file():
            return True, f"Arquivo explícito personalizado: {explicit_path}"

        env_file = os.environ.get("BRISASYNC_GOOGLE_CLIENT_CONFIG_FILE", "").strip()
        if env_file and Path(env_file).is_file():
            return True, f"Variável de ambiente BRISASYNC_GOOGLE_CLIENT_CONFIG_FILE ({env_file})"

        env_id = os.environ.get("BRISASYNC_GOOGLE_CLIENT_ID", "").strip()
        env_secret = os.environ.get("BRISASYNC_GOOGLE_CLIENT_SECRET", "").strip()
        if env_id and env_secret:
            return True, "Variáveis de ambiente BRISASYNC_GOOGLE_CLIENT_ID / SECRET"

        default_path = default_oauth_client_config_path()
        if default_path.is_file():
            return True, f"Cliente de teste do usuário ({default_path})"

        for sys_path in system_oauth_client_config_paths():
            if sys_path.is_file():
                return True, f"Cliente de distribuição empacotado ({sys_path})"

        return True, "Cliente Desktop oficial público embutido do BrisaSync"


@dataclass(frozen=True)
class PKCEChallenge:
    """Par PKCE (Proof Key for Code Exchange) com método S256."""

    code_verifier: str
    code_challenge: str
    code_challenge_method: str = "S256"


def generate_pkce_pair() -> PKCEChallenge:
    """Gera code_verifier de alta entropia e code_challenge SHA-256 base64url sem padding."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PKCEChallenge(
        code_verifier=verifier,
        code_challenge=challenge,
        code_challenge_method="S256",
    )


def generate_state() -> str:
    """Gera token state imprevisível de 256 bits para proteção contra CSRF no callback."""
    return secrets.token_urlsafe(32)


@dataclass
class _LoopbackCallbackData:
    code: str | None = None
    state: str | None = None
    error: str | None = None
    error_description: str | None = None
    received: bool = False


class _LoopbackHTTPServer(HTTPServer):
    allow_reuse_address = True

    def __init__(self, server_address: tuple[str, int], RequestHandlerClass: Any) -> None:
        super().__init__(server_address, RequestHandlerClass)
        self.callback_data = _LoopbackCallbackData()


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handler HTTP local que recebe o redirecionamento OAuth em 127.0.0.1."""

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/", "/callback", "/oauth2callback"):
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        srv: _LoopbackHTTPServer = self.server  # type: ignore[assignment]
        srv.callback_data.code = params.get("code", [None])[0]
        srv.callback_data.state = params.get("state", [None])[0]
        srv.callback_data.error = params.get("error", [None])[0]
        srv.callback_data.error_description = params.get("error_description", [None])[0]
        srv.callback_data.received = True

        if srv.callback_data.error:
            status_title = "Autorização não concluída"
            status_body = (
                "A autorização foi recusada ou cancelada no navegador. "
                "Você já pode fechar esta aba e voltar ao BrisaSync."
            )
        else:
            status_title = "Autenticação recebida pelo BrisaSync"
            status_body = (
                "O código de autorização foi recebido localmente. "
                "Você já pode fechar esta aba e voltar à janela do BrisaSync."
            )

        html = (
            "<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
            f"<title>{status_title}</title>"
            "<style>body{font-family:sans-serif;max-width:520px;margin:48px auto;"
            "padding:24px;border:1px solid #ccc;border-radius:8px;}</style></head>"
            f"<body><h2>{status_title}</h2><p>{status_body}</p></body></html>"
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # Suprime logs HTTP padrão para nunca imprimir query strings contendo códigos OAuth
        return


def open_default_browser(url: str) -> bool:
    """Abre a URL de autorização no navegador padrão externo da sessão Linux."""
    xdg_open = shutil.which("xdg-open")
    if xdg_open:
        try:
            subprocess.Popen(
                [xdg_open, url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError:
            pass
    try:
        return webbrowser.open(url, new=1, autoraise=True)
    except Exception:
        return False


class GoogleOAuthDesktopClient:
    """Cliente OAuth 2.0 Desktop com PKCE S256, loopback listener e renovação de tokens."""

    def __init__(
        self,
        client_config: OAuthClientConfig,
        *,
        scopes: tuple[str, ...] = REQUIRED_GOOGLE_SCOPES,
        browser_opener: Callable[[str], bool] = open_default_browser,
    ) -> None:
        self.client_config = client_config
        self.scopes = scopes
        self.browser_opener = browser_opener

    def build_authorization_url(
        self,
        *,
        redirect_uri: str,
        state: str,
        pkce: PKCEChallenge,
    ) -> str:
        params = {
            "client_id": self.client_config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": pkce.code_challenge_method,
            "access_type": "offline",
            "prompt": "consent",
        }
        return f"{self.client_config.auth_uri}?{urllib.parse.urlencode(params)}"

    def authorize_interactive(
        self,
        *,
        timeout_seconds: float = 180.0,
        cancel_event: threading.Event | None = None,
        on_auth_url_ready: Callable[[str], None] | None = None,
    ) -> OAuthCredentials:
        """Executa o fluxo completo Authorization Code + PKCE S256 via loopback 127.0.0.1."""
        pkce = generate_pkce_pair()
        expected_state = generate_state()

        # Bind estritamente em 127.0.0.1 na porta efêmera 0
        server = _LoopbackHTTPServer(("127.0.0.1", 0), _OAuthCallbackHandler)
        server.timeout = 0.2
        try:
            port = server.server_port
            redirect_uri = f"http://127.0.0.1:{port}/callback"
            auth_url = self.build_authorization_url(
                redirect_uri=redirect_uri,
                state=expected_state,
                pkce=pkce,
            )

            if on_auth_url_ready is not None:
                on_auth_url_ready(auth_url)

            self.browser_opener(auth_url)

            deadline = time.monotonic() + timeout_seconds
            while not server.callback_data.received:
                if cancel_event is not None and cancel_event.is_set():
                    raise OAuthTimeoutOrCancelledError(
                        "Autenticação OAuth cancelada pelo usuário."
                    )
                if time.monotonic() >= deadline:
                    raise OAuthTimeoutOrCancelledError(
                        f"Tempo limite de {int(timeout_seconds)}s esgotado aguardando "
                        "retorno do navegador no loopback 127.0.0.1."
                    )
                server.handle_request()

            cb = server.callback_data
        finally:
            # Garante o encerramento imediato do socket listener em 127.0.0.1
            server.server_close()

        if cb.error:
            if cb.error == "access_denied":
                raise OAuthAccessDeniedError(
                    "Autorização negada pelo usuário na tela de consentimento do Google."
                )
            desc = f" ({cb.error_description})" if cb.error_description else ""
            raise OAuthError(f"Erro retornado pelo servidor OAuth: {cb.error}{desc}")

        if not cb.state or not hmac.compare_digest(cb.state, expected_state):
            raise OAuthProtocolError(
                "Validação de segurança falhou: parâmetro 'state' ausente ou divergente no retorno OAuth."
            )

        if not cb.code:
            raise OAuthProtocolError(
                "Retorno OAuth não contém código de autorização ('code')."
            )

        token_data = self.exchange_code_for_tokens(
            code=cb.code,
            code_verifier=pkce.code_verifier,
            redirect_uri=redirect_uri,
        )
        access_token = str(token_data.get("access_token", "")).strip()
        refresh_token = str(token_data.get("refresh_token", "")).strip()
        token_type = str(token_data.get("token_type", "Bearer")).strip() or "Bearer"
        expires_in = int(token_data.get("expires_in", 3600))
        granted_scope = str(token_data.get("scope", "")).strip()
        granted_set = set(granted_scope.split())
        if "https://www.googleapis.com/auth/drive" not in granted_set:
            if access_token:
                self.revoke_token(access_token)
            raise OAuthAccessDeniedError(
                "Acesso ao Google Drive não concedido "
                f"(escopos concedidos na resposta de tokens: {sorted(granted_set)}). "
                "Reconecte a conta e marque a permissão do Google Drive na tela de consentimento."
            )

        if not access_token:
            raise OAuthProtocolError("Servidor de tokens não retornou 'access_token'.")
        if not refresh_token:
            raise OAuthProtocolError(
                "Servidor de tokens não retornou 'refresh_token'. Repita a conexão e "
                "confirme o consentimento offline."
            )

        expiry_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        account_email = self.fetch_user_email(access_token)
        now_iso = datetime.now(timezone.utc).isoformat()

        return OAuthCredentials(
            client_id=self.client_config.client_id,
            client_secret=self.client_config.client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            token_type=token_type,
            expiry=expiry_iso,
            scope=granted_scope,
            account_email=account_email,
            updated_at=now_iso,
        )

    def exchange_code_for_tokens(
        self,
        *,
        code: str,
        code_verifier: str,
        redirect_uri: str,
    ) -> dict[str, Any]:
        payload = {
            "client_id": self.client_config.client_id,
            "client_secret": self.client_config.client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
        return self._post_form(self.client_config.token_uri, payload)

    def refresh_access_token(self, credentials: OAuthCredentials) -> OAuthCredentials:
        """Renova o `access_token` usando o `refresh_token` armazenado."""
        if not credentials.refresh_token:
            raise OAuthRevokedOrExpiredError(
                "Credenciais não possuem 'refresh_token' para renovação."
            )
        payload = {
            "client_id": credentials.client_id or self.client_config.client_id,
            "client_secret": credentials.client_secret or self.client_config.client_secret,
            "refresh_token": credentials.refresh_token,
            "grant_type": "refresh_token",
        }
        token_data = self._post_form(self.client_config.token_uri, payload)
        new_access_token = str(token_data.get("access_token", "")).strip()
        if not new_access_token:
            raise OAuthProtocolError(
                "Resposta de renovação não trouxe um novo 'access_token'."
            )
        expires_in = int(token_data.get("expires_in", 3600))
        new_refresh = str(token_data.get("refresh_token", "")).strip() or credentials.refresh_token
        new_token_type = str(token_data.get("token_type", credentials.token_type)).strip() or "Bearer"
        expiry_iso = (
            datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        return OAuthCredentials(
            client_id=credentials.client_id or self.client_config.client_id,
            client_secret=credentials.client_secret or self.client_config.client_secret,
            access_token=new_access_token,
            refresh_token=new_refresh,
            token_type=new_token_type,
            expiry=expiry_iso,
            scope=str(token_data.get("scope", credentials.scope)),
            account_email=credentials.account_email,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

    def fetch_user_email(self, access_token: str) -> str:
        """Obtém o endereço de e-mail verificado da conta Google autenticada."""
        headers = {"Authorization": f"Bearer {access_token}"}

        # Tentativa 1: OpenID UserInfo endpoint
        try:
            req = urllib.request.Request(GOOGLE_USERINFO_URI, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                email = str(data.get("email", "")).strip()
                if email:
                    return email
        except Exception:
            pass

        # Tentativa 2: Google Drive v3 about endpoint
        try:
            req = urllib.request.Request(GOOGLE_DRIVE_ABOUT_URI, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                user_info = data.get("user", {})
                if isinstance(user_info, dict):
                    email = str(user_info.get("emailAddress", "")).strip()
                    if email:
                        return email
        except Exception as exc:
            raise OAuthProtocolError(
                f"Não foi possível confirmar a identidade da conta Google: {redact_secrets(str(exc))}"
            ) from exc

        raise OAuthProtocolError(
            "Autenticação concluída, mas a API Google não retornou o e-mail da conta."
        )

    @staticmethod
    def revoke_token(token: str) -> bool:
        """Solicita revogação opcional do token no servidor OAuth do Google."""
        if not token:
            return False
        encoded = urllib.parse.urlencode({"token": token}).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_REVOKE_URI,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except Exception:
            return False

    @staticmethod
    def _post_form(url: str, form_data: dict[str, str]) -> dict[str, Any]:
        encoded = urllib.parse.urlencode(form_data).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=encoded,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            err_body = ""
            try:
                err_body = exc.read().decode("utf-8", errors="replace")
                err_json = json.loads(err_body)
                err_code = str(err_json.get("error", "")).strip()
                err_desc = str(err_json.get("error_description", "")).strip()
            except Exception:
                err_code = ""
                err_desc = redact_secrets(err_body)

            if err_code == "invalid_grant":
                raise OAuthRevokedOrExpiredError(
                    "Autorização Google expirada ou revogada ('invalid_grant'). "
                    f"Reconecte sua conta no BrisaSync. {err_desc}"
                ) from exc
            if err_code == "access_denied":
                raise OAuthAccessDeniedError(
                    f"Acesso negado pelo servidor OAuth: {err_desc}"
                ) from exc
            raise OAuthError(
                f"Falha HTTP {exc.code} ao comunicar com Google OAuth: "
                f"{redact_secrets(err_code or err_desc or str(exc))}"
            ) from exc
        except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise OAuthError(
                f"Erro de rede ao comunicar com Google OAuth: {redact_secrets(str(exc))}"
            ) from exc


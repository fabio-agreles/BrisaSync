"""Testes do Cofre de Segredos, Fluxo OAuth 2.0 Google Desktop (PKCE S256) e Ponte Cifrada rclone."""

from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
from typing import Any
import urllib.parse
import urllib.request

import pytest

from brisasync.backend.rclone_engine import RcloneBisyncEngine
from brisasync.credentials.oauth_google import (
    GoogleOAuthDesktopClient,
    OAuthAccessDeniedError,
    OAuthClientConfig,
    OAuthConfigurationError,
    OAuthProtocolError,
    OAuthRevokedOrExpiredError,
    OAuthTimeoutOrCancelledError,
    generate_pkce_pair,
)
from brisasync.credentials.rclone_bridge import RcloneEncryptedBridge
from brisasync.credentials.store import (
    CredentialStore,
    CredentialSyncBackError,
    OAuthCredentials,
    VaultUnavailableError,
)
from brisasync.orchestrator.diagnostics import collect_system_diagnostics
from brisasync.orchestrator.sync_coordinator import SyncCoordinator
from brisasync.storage.database import BrisaDatabase


class _IsolatedTestCredentialStore(CredentialStore):
    """Subclasse de CredentialStore que usa chaves isoladas de teste no cofre real da sessão."""

    OAUTH_ACCOUNT_KEY = "pytest_isolated_google_oauth"
    RCLONE_KEY_ACCOUNT = "pytest_isolated_rclone_cfg_key"


def test_pkce_s256_cryptographic_challenge() -> None:
    """Valida matematicamente o par PKCE code_verifier e code_challenge (S256)."""
    pkce = generate_pkce_pair()
    assert pkce.code_challenge_method == "S256"
    assert len(pkce.code_verifier) >= 64
    assert "=" not in pkce.code_challenge

    expected_digest = hashlib.sha256(pkce.code_verifier.encode("ascii")).digest()
    expected_challenge = (
        base64.urlsafe_b64encode(expected_digest).rstrip(b"=").decode("ascii")
    )
    assert pkce.code_challenge == expected_challenge


def test_real_session_vault_crud_and_diagnostics(tmp_path: Path) -> None:
    """Testa armazenamento, leitura, atualização e remoção reais no cofre da sessão Linux."""
    store = _IsolatedTestCredentialStore(lock_path=tmp_path / "cred.lock")
    try:
        # 1. Verifica roundtrip com segredo descartável
        backend_name, msg = store.verify_vault_operation()
        assert "validado com sucesso" in msg.lower()
        assert backend_name

        # 2. Diagnóstico distingue instalado vs acessível e validado
        diag = collect_system_diagnostics()
        keyring_items = [
            i for i in diag.items if "Cofre de Credenciais" in i.component
        ]
        assert len(keyring_items) == 1
        assert "[OK — VALIDADO]" in keyring_items[0].status_label

        # 3. CRUD completo no cofre
        creds = OAuthCredentials(
            client_id="12345-test.apps.googleusercontent.com",
            client_secret="GOCSPX-test-secret",
            access_token="ya29.initial_access_token",
            refresh_token="1//initial_refresh_token",
            token_type="Bearer",
            expiry="2099-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="teste.brisasync@example.com",
        )
        store.store_credentials(creds)
        loaded = store.load_credentials()
        assert loaded is not None
        assert loaded.account_email == "teste.brisasync@example.com"
        assert loaded.access_token == "ya29.initial_access_token"
        assert loaded.refresh_token == "1//initial_refresh_token"

        # 4. Atualização de tokens
        updated = store.update_tokens(
            access_token="ya29.renewed_access_token",
            expiry="2099-06-01T00:00:00Z",
        )
        assert updated.access_token == "ya29.renewed_access_token"
        assert store.load_credentials().access_token == "ya29.renewed_access_token"
    finally:
        store.delete_credentials()

    assert store.load_credentials() is None


def test_vault_unavailable_raises_clear_recoverable_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Garante que cofre ausente ou bloqueado levanta VaultUnavailableError sem fallback inseguro."""
    monkeypatch.setattr("shutil.which", lambda _name: None)
    store = _IsolatedTestCredentialStore(lock_path=tmp_path / "cred.lock")
    caps = store.probe_capabilities(verify_roundtrip=True)
    assert not caps.utility_installed
    assert not caps.is_available

    with pytest.raises(VaultUnavailableError):
        store.verify_vault_operation()


def test_rclone_encrypted_bridge_and_token_sync_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida criptografia real RCLONE_ENCRYPT_V0:, temporários exclusivos, permissões, limpeza e falha ao devolver tokens ao cofre (com token sintético)."""
    store = _IsolatedTestCredentialStore(lock_path=tmp_path / "cred.lock")
    enc_cfg_path = tmp_path / "cfg_dir" / "rclone_encrypted.conf"
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=enc_cfg_path,
    )

    try:
        creds = OAuthCredentials(
            client_id="cid-bridge-test",
            client_secret="csec-bridge-secret-999",
            access_token="ya29.secret_access_v1",
            refresh_token="1//secret_refresh_v1",
            token_type="Bearer",
            expiry="2099-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="bridge@example.com",
        )
        store.store_credentials(creds)

        cfg_file, cfg_key = bridge.materialize_encrypted_config(creds)
        assert cfg_file.is_file()
        # Verifica permissões restritas: diretório 0700 e arquivo 0600
        assert (cfg_file.parent.stat().st_mode & 0o777) == 0o700
        assert (cfg_file.stat().st_mode & 0o777) == 0o600
        # Verifica limpeza total de arquivos temporários .tmp no diretório de destino
        assert list(cfg_file.parent.glob("*.tmp")) == []

        raw_disk_text = cfg_file.read_text(encoding="utf-8")

        # Verifica cabeçalho de criptografia real RCLONE_ENCRYPT_V0: e ausência total de texto claro
        assert "# Encrypted rclone configuration File" in raw_disk_text
        assert "RCLONE_ENCRYPT_V0:" in raw_disk_text
        assert "ya29.secret_access_v1" not in raw_disk_text
        assert "1//secret_refresh_v1" not in raw_disk_text
        assert "csec-bridge-secret-999" not in raw_disk_text

        # Verifica que em caso de erro ao cifrar (ex.: binário inválido), nenhum temporário resta
        bad_bridge = RcloneEncryptedBridge(
            credential_store=store,
            config_path=tmp_path / "cfg_dir_err" / "rclone.conf",
            rclone_binary="/bin/false",
        )
        with pytest.raises(RuntimeError, match="Falha ao cifrar"):
            bad_bridge.materialize_encrypted_config(creds)
        assert not (tmp_path / "cfg_dir_err" / "rclone.conf").exists()

        # Simula o rclone renovando o token durante uma operação (atualizando o arquivo cifrado)
        renewed_creds = OAuthCredentials(
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            access_token="ya29.rclone_auto_renewed_v2",
            refresh_token="1//secret_refresh_v1",
            token_type="Bearer",
            expiry="2099-06-01T00:00:00Z",
            scope=creds.scope,
            account_email=creds.account_email,
        )
        bridge.materialize_encrypted_config(renewed_creds)
        store.store_credentials(creds)
        assert store.load_credentials().access_token == "ya29.secret_access_v1"

        # Ao sincronizar de volta do rclone.conf cifrado para o cofre, o cofre recebe o token v2!
        synced = bridge.sync_tokens_back_to_vault(cfg_key)
        assert synced is not None
        assert synced.access_token == "ya29.rclone_auto_renewed_v2"
        assert store.load_credentials().access_token == "ya29.rclone_auto_renewed_v2"

        # Cenário Crítico: Falha ao devolver token renovado ao cofre (CredentialSyncBackError).
        # 1. O rclone renova o token para v3 durante a sessão (atualizando rclone.conf cifrado).
        # 2. O cofre falha no momento de persistir (update_tokens levanta VaultUnavailableError).
        # 3. A sessão DEVE levantar CredentialSyncBackError (não registrar sucesso!),
        #    NÃO pode descartar o rclone.conf cifrado que guarda a única cópia de v3,
        #    e na sessão seguinte (quando o cofre volta) DEVE recuperar v3 antes de sobrescrever!
        renewed_v3 = OAuthCredentials(
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            access_token="ya29.renewed_during_vault_outage_v3",
            refresh_token="1//secret_refresh_v3",
            token_type="Bearer",
            expiry="2099-12-31T23:59:59Z",
            scope=creds.scope,
            account_email=creds.account_email,
        )

        orig_update_tokens = store.update_tokens

        def _failing_update_tokens(**_kwargs: Any) -> OAuthCredentials:
            raise VaultUnavailableError("Cofre bloqueado temporariamente durante retorno do token")

        with pytest.raises(CredentialSyncBackError, match="preservado intacto"):
            with bridge.authenticated_rclone_session() as session_env:
                assert "RCLONE_CONFIG" in session_env
                # Simula o rclone gravando o token v3 renovado no arquivo cifrado durante a execução
                bridge.materialize_encrypted_config(renewed_v3)
                # Agora simula falha do cofre exatamente na devolução ao sair do bloco with
                monkeypatch.setattr(store, "update_tokens", _failing_update_tokens)

        # Confirma que o arquivo cifrado rclone.conf NÃO foi descartado e ainda guarda v3
        assert enc_cfg_path.is_file()
        # O cofre ainda tinha v2 porque a gravação de v3 falhou
        assert store.load_credentials().access_token == "ya29.rclone_auto_renewed_v2"

        # Restaura a operação normal do cofre e verifica que a próxima sessão reconcilia v3
        # a partir do rclone.conf cifrado ANTES de sobrescrevê-lo!
        monkeypatch.setattr(store, "update_tokens", orig_update_tokens)
        reconciled = bridge.ensure_valid_credentials()
        assert reconciled.access_token == "ya29.renewed_during_vault_outage_v3"
        assert reconciled.refresh_token == "1//secret_refresh_v3"
        assert store.load_credentials().access_token == "ya29.renewed_during_vault_outage_v3"

        # Verifica também que o SyncCoordinator registra FAILED_CREDENTIAL_PERSISTENCE no SQLite
        # e nunca registra sucesso se a persistência de credenciais falhar
        db = BrisaDatabase(db_path=tmp_path / "sync_cred_fail.db")
        coord = SyncCoordinator(database=db, engine=RcloneBisyncEngine(), bridge=bridge)
        monkeypatch.setattr(
            coord.engine,
            "resolve_remote_directory_by_id",
            lambda *_a, **_kw: (_ for _ in ()).throw(
                CredentialSyncBackError("Falha simulada ao persistir token renovado")
            ),
        )
        with pytest.raises(CredentialSyncBackError):
            coord.synchronize_google_drive_pair(
                local_folder=tmp_path / "empty_local",
                remote_folder_id="folder_123",
            )
        runs = db.list_recent_sync_runs()
        assert len(runs) == 1
        assert runs[0].status == "FAILED_CREDENTIAL_PERSISTENCE"
    finally:
        bridge.remove_encrypted_config()
        store.delete_credentials()


def test_oauth_desktop_loopback_pkce_flow_and_error_handling(tmp_path: Path) -> None:
    """Valida o fluxo OAuth 2.0 Desktop completo contra servidor local simulado (tokens sintéticos, distinto de renovação real contra Google): PKCE S256, state, loopback, refresh e erros."""
    captured_token_requests: list[dict[str, str]] = []

    class _MockGoogleOAuthHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8")
            params = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
            captured_token_requests.append(params)

            if params.get("grant_type") == "authorization_code":
                assert "code_verifier" in params and len(params["code_verifier"]) >= 64
                resp = {
                    "access_token": "ya29.mock_access_ok",
                    "refresh_token": "1//mock_refresh_ok",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "scope": "https://www.googleapis.com/auth/drive openid email",
                }
                self._send_json(200, resp)
            elif params.get("grant_type") == "refresh_token":
                if params.get("refresh_token") == "1//revoked":
                    self._send_json(
                        400,
                        {
                            "error": "invalid_grant",
                            "error_description": "Token has been expired or revoked.",
                        },
                    )
                else:
                    self._send_json(
                        200,
                        {
                            "access_token": "ya29.mock_refreshed_token",
                            "token_type": "Bearer",
                            "expires_in": 3600,
                        },
                    )

        def _send_json(self, status: int, data: dict[str, Any]) -> None:
            raw = json.dumps(data).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return

    mock_google_srv = HTTPServer(("127.0.0.1", 0), _MockGoogleOAuthHandler)
    srv_thread = threading.Thread(target=mock_google_srv.serve_forever, daemon=True)
    srv_thread.start()

    try:
        token_uri = f"http://127.0.0.1:{mock_google_srv.server_port}/token"
        client_cfg = OAuthClientConfig(
            client_id="desktop-cid.apps.googleusercontent.com",
            client_secret="desktop-csec",
            token_uri=token_uri,
        )

        # 1. Fluxo de sucesso via loopback 127.0.0.1 com validação de PKCE e state
        def _simulate_browser_consent(auth_url: str) -> bool:
            parsed = urllib.parse.urlparse(auth_url)
            q = urllib.parse.parse_qs(parsed.query)
            redirect_uri = q["redirect_uri"][0]
            state = q["state"][0]
            assert q["code_challenge_method"][0] == "S256"
            assert redirect_uri.startswith("http://127.0.0.1:")

            def _fire_callback() -> None:
                cb_url = f"{redirect_uri}?code=auth_code_xyz&state={ urllib.parse.quote(state) }"
                urllib.request.urlopen(cb_url, timeout=5).read()

            threading.Thread(target=_fire_callback, daemon=True).start()
            return True

        oauth_client = GoogleOAuthDesktopClient(
            client_cfg,
            browser_opener=_simulate_browser_consent,
        )
        oauth_client.fetch_user_email = lambda _tok: "authed.user@example.com"  # type: ignore[method-assign]

        creds = oauth_client.authorize_interactive(timeout_seconds=10.0)
        assert creds.access_token == "ya29.mock_access_ok"
        assert creds.refresh_token == "1//mock_refresh_ok"
        assert creds.account_email == "authed.user@example.com"

        # 2. Renovação de token com sucesso
        refreshed = oauth_client.refresh_access_token(creds)
        assert refreshed.access_token == "ya29.mock_refreshed_token"
        assert refreshed.refresh_token == "1//mock_refresh_ok"

        # 3. Tratamento de token revogado (invalid_grant)
        revoked_creds = OAuthCredentials(
            client_id=creds.client_id,
            client_secret=creds.client_secret,
            access_token="ya29.old",
            refresh_token="1//revoked",
            token_type="Bearer",
            expiry="2020-01-01T00:00:00Z",
            scope=creds.scope,
            account_email=creds.account_email,
        )
        with pytest.raises(OAuthRevokedOrExpiredError, match="invalid_grant"):
            oauth_client.refresh_access_token(revoked_creds)

        # 4. Tratamento de autorização negada pelo usuário (access_denied)
        def _simulate_browser_deny(auth_url: str) -> bool:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
            redirect_uri = q["redirect_uri"][0]
            state = q["state"][0]
            threading.Thread(
                target=lambda: urllib.request.urlopen(
                    f"{redirect_uri}?error=access_denied&state={state}", timeout=5
                ).read(),
                daemon=True,
            ).start()
            return True

        deny_client = GoogleOAuthDesktopClient(
            client_cfg, browser_opener=_simulate_browser_deny
        )
        with pytest.raises(OAuthAccessDeniedError):
            deny_client.authorize_interactive(timeout_seconds=5.0)

        # 5. Rejeição de state inválido/adulterado
        def _simulate_tampered_state(auth_url: str) -> bool:
            q = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
            redirect_uri = q["redirect_uri"][0]
            threading.Thread(
                target=lambda: urllib.request.urlopen(
                    f"{redirect_uri}?code=abc&state=tampered_wrong_state", timeout=5
                ).read(),
                daemon=True,
            ).start()
            return True

        tampered_client = GoogleOAuthDesktopClient(
            client_cfg, browser_opener=_simulate_tampered_state
        )
        with pytest.raises(OAuthProtocolError, match="state"):
            tampered_client.authorize_interactive(timeout_seconds=5.0)

        # 6. Rejeição quando escopo do Google Drive não é concedido na resposta de tokens
        class _PartialScopeHandler(_MockGoogleOAuthHandler):
            def do_POST(self) -> None:  # noqa: N802
                self._send_json(
                    200,
                    {
                        "access_token": "ya29.partial_only_email",
                        "refresh_token": "1//partial_refresh",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                        "scope": "openid https://www.googleapis.com/auth/userinfo.email",
                    },
                )

        partial_srv = HTTPServer(("127.0.0.1", 0), _PartialScopeHandler)
        partial_thread = threading.Thread(target=partial_srv.serve_forever, daemon=True)
        partial_thread.start()
        try:
            partial_cfg = OAuthClientConfig(
                client_id="desktop-cid.apps.googleusercontent.com",
                client_secret="desktop-csec",
                token_uri=f"http://127.0.0.1:{partial_srv.server_port}/token",
            )
            partial_client = GoogleOAuthDesktopClient(
                partial_cfg, browser_opener=_simulate_browser_consent
            )
            with pytest.raises(
                OAuthAccessDeniedError,
                match="Acesso ao Google Drive não concedido",
            ):
                partial_client.authorize_interactive(timeout_seconds=5.0)
        finally:
            partial_srv.shutdown()
            partial_srv.server_close()

        # 7. Cancelamento imediato do listener loopback
        cancel_ev = threading.Event()
        cancel_ev.set()
        noop_client = GoogleOAuthDesktopClient(
            client_cfg, browser_opener=lambda _u: True
        )
        with pytest.raises(OAuthTimeoutOrCancelledError, match="cancelada"):
            noop_client.authorize_interactive(
                timeout_seconds=10.0, cancel_event=cancel_ev
            )
    finally:
        mock_google_srv.shutdown()
        mock_google_srv.server_close()


def test_oauth_client_config_rejects_web_client_json(tmp_path: Path) -> None:
    """Garante que apenas credenciais do tipo Desktop App ('installed') são aceitas."""
    web_json = tmp_path / "web_client.json"
    web_json.write_text(
        json.dumps({"web": {"client_id": "abc", "client_secret": "def"}}),
        encoding="utf-8",
    )
    with pytest.raises(OAuthConfigurationError, match="Desktop app"):
        OAuthClientConfig.from_file(web_json)


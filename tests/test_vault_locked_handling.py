"""Testes de tratamento de cofre bloqueado (GNOME Keyring / KDE Wallet) no BrisaSync.

Garante que:
1. O cofre bloqueado é detectado de forma não interativa (via D-Bus no Secret Service / KWallet).
2. Nenhuma consulta interativa nem subprocessos repetidos ocorrem no loop da UI ou do daemon.
3. A interface apresenta claramente o estado 'Cofre bloqueado', botão 'Desbloquear cofre' e nunca 'Tudo em dia'.
4. Cancelar a senha mantém a interface responsiva e estável sem loops.
5. Desbloqueio externo (ex.: Seahorse) é detectado de forma não interativa e retoma o fluxo sem reautorização no Google.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from brisasync.credentials.rclone_bridge import RcloneEncryptedBridge
from brisasync.credentials.store import (
    CredentialStore,
    OAuthCredentials,
    VaultLockedError,
    VaultUnavailableError,
)
from brisasync.service.daemon import BrisaSessionServiceDaemon
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.service.protocol import (
    ATTENTION_VAULT_LOCKED,
    STATE_ATTENTION_REQUIRED,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.workers import UnlockVaultWorker


class _LockedTestingCredentialStore(CredentialStore):
    OAUTH_ACCOUNT_KEY = "pytest_vault_locked_test_oauth"
    RCLONE_KEY_ACCOUNT = "pytest_vault_locked_test_rclone"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture(autouse=True)
def clean_mock_vault_locked():
    """Garante que o override de teste do mock do cofre seja limpo após cada teste."""
    CredentialStore.set_mock_vault_locked(None)
    yield
    CredentialStore.set_mock_vault_locked(None)


def test_vault_locked_detection_and_non_interactive_guard(tmp_path: Path) -> None:
    """Verifica detecção não interativa e proteção contra subprocessos quando bloqueado."""
    CredentialStore.set_mock_vault_locked(True)
    store = _LockedTestingCredentialStore(lock_path=tmp_path / "cred.lock")

    # 1. is_vault_locked() retorna True
    assert store.is_vault_locked() is True

    # 2. Tentativa não interativa de carregar credenciais deve falhar imediatamente sem invocar comandos
    with patch("subprocess.Popen") as mock_popen, patch("subprocess.run") as mock_run:
        with pytest.raises(VaultLockedError) as exc_info:
            store.load_credentials(interactive=False)
        assert "bloqueado" in str(exc_info.value).lower()
        # Nenhum subprocesso deve ser criado!
        assert mock_popen.call_count == 0
        assert mock_run.call_count == 0

    # 3. verify_vault_operation falha com VaultLockedError sem teste descartável
    with patch.object(store, "_write_raw_secret") as mock_write:
        with pytest.raises(VaultLockedError):
            store.verify_vault_operation()
        assert mock_write.call_count == 0

    # 4. probe_capabilities() reporta inacessível e informa bloqueio
    caps = store.probe_capabilities(verify_roundtrip=True)
    assert caps.vault_accessible is False
    assert "bloqueado" in caps.verification_message.lower()


def test_ui_presentation_and_button_when_vault_locked(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida apresentação estável no Hero Banner, botão principal e Ajustes com cofre bloqueado."""
    CredentialStore.set_mock_vault_locked(True)

    db = BrisaDatabase(db_path=tmp_path / "locked_test.db")
    db.set_local_sync_folder("/home/user/LocalFolder")
    db.set_remote_sync_folder(folder_name="RemoteFolder", folder_id="folder_id_xyz")

    store = _LockedTestingCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone_locked.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_locked.sock"),
    )
    window.show()
    qapp.processEvents()

    # 1. Estado da conta avaliado como VAULT_LOCKED de forma não interativa
    state, creds, detail = window._get_account_operational_state(interactive=False)
    assert state == "VAULT_LOCKED"
    assert creds is None

    # 2. Hero Banner em modo Atenção por cofre bloqueado
    assert window.hero_banner.property("heroState") == "attention"
    assert window.hero_title_label.text() == "Cofre bloqueado"
    assert "✕ Cofre bloqueado" in window.global_status_pill.text()
    assert "Tudo em dia" not in window.hero_title_label.text()

    # 3. Botão principal do Hero oferece 'Desbloquear cofre'
    assert window.hero_sync_now_btn.text() == "Desbloquear cofre"
    assert window.hero_sync_now_btn.isEnabled()
    assert window.hero_pause_btn.text() == "Desbloquear"

    # 4. Banner de atenção acionável visível
    assert window.attention_banner_frame.isVisible()
    assert "Cofre bloqueado" in window.attention_explanation_label.text()

    # 5. Na página de Ajustes, o botão permite desbloquear sob demanda
    window.set_current_page(3)
    qapp.processEvents()
    window._refresh_account_state_from_vault()
    assert window.connect_google_button.text() == "Desbloquear Cofre"
    assert window.connect_google_button.isEnabled()
    assert window.connect_google_button.isVisible()

    window.close()


def test_ui_snapshot_ticks_do_not_prompt_or_spawn_subprocesses(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Verifica que ticks periódicos de snapshot não chamam lookups nem geram chamadas interativas."""
    CredentialStore.set_mock_vault_locked(True)

    db = BrisaDatabase(db_path=tmp_path / "locked_timer.db")
    db.set_local_sync_folder("/home/user/LocalFolder")
    db.set_remote_sync_folder(folder_name="RemoteFolder", folder_id="folder_id_xyz")

    store = _LockedTestingCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone_locked.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_locked.sock"),
    )
    window.show()
    qapp.processEvents()

    snapshot = ServiceStatusSnapshot.from_dict(
        {
            "service_pid": 1234,
            "state": STATE_ATTENTION_REQUIRED,
            "state_label": "Atenção",
            "detail_message": "Cofre bloqueado",
            "is_cycle_active": False,
            "attention_category": ATTENTION_VAULT_LOCKED,
            "attention_title": "Cofre Bloqueado",
            "attention_explanation": "O chaveiro da sessão está bloqueado.",
            "configured_pair_ready": True,
        }
    )

    with patch.object(store, "_secret_tool_lookup") as mock_st, patch.object(
        store, "_kwallet_lookup"
    ) as mock_kw:
        # Simula 5 atualizações periódicas consecutivas do timer da interface
        for _ in range(5):
            window._apply_service_snapshot(snapshot)
            qapp.processEvents()

        # NENHUMA tentativa de lookup interativo pelo secret-tool ou kwallet deve ocorrer
        assert mock_st.call_count == 0
        assert mock_kw.call_count == 0

    assert window.hero_title_label.text() == "Cofre bloqueado"
    assert window.hero_sync_now_btn.text() == "Desbloquear cofre"
    window.close()


def test_ui_unlock_worker_and_cancel_preserves_stability(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Verifica que o cancelamento do desbloqueio deixa a interface estável sem loops."""
    CredentialStore.set_mock_vault_locked(True)

    db = BrisaDatabase(db_path=tmp_path / "locked_cancel.db")
    store = _LockedTestingCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone_locked.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_locked.sock"),
    )
    window.show()
    qapp.processEvents()

    # Dispara a tentativa de desbloqueio pelo botão do Hero
    with patch.object(UnlockVaultWorker, "run") as mock_run:
        window._on_sync_now_clicked()
        assert window._unlock_worker is not None

    # Simula emissão do sinal failed (usuário cancelou no diálogo do desktop)
    window._on_vault_unlock_failed("Operação cancelada pelo usuário.")
    window._on_vault_unlock_finished()
    qapp.processEvents()

    assert window._unlock_worker is None
    assert "Cofre permanece bloqueado" in window.statusBar().currentMessage()
    assert window.hero_sync_now_btn.isEnabled()
    assert window.hero_sync_now_btn.text() == "Desbloquear cofre"

    window.close()


def test_ui_external_unlock_detection_and_automatic_recovery(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida recuperação não interativa quando o cofre é desbloqueado externamente (ex.: Seahorse)."""
    # 1. Configura ambiente com credenciais válidas e rclone configurado
    CredentialStore.set_mock_vault_locked(False)
    store = _LockedTestingCredentialStore()
    fake_creds = OAuthCredentials(
        client_id="cid-external.apps.googleusercontent.com",
        client_secret="csec-external",
        access_token="ya29.valid_external",
        refresh_token="1//valid_refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="externo.desbloqueado@example.com",
    )
    store.store_credentials(fake_creds)

    conf_file = tmp_path / "test_rclone_ext.conf"
    conf_file.write_text("[brisasync_gdrive]\ntype = drive\n")
    bridge = RcloneEncryptedBridge(credential_store=store, config_path=conf_file)

    db = BrisaDatabase(db_path=tmp_path / "locked_recovery.db")
    db.set_local_sync_folder("/home/user/LocalFolder")
    db.set_remote_sync_folder(folder_name="RemoteFolder", folder_id="folder_id_ext")

    # 2. Bloqueia o cofre antes de iniciar a interface
    CredentialStore.set_mock_vault_locked(True)

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_locked.sock"),
    )
    window.show()
    qapp.processEvents()

    assert window.hero_sync_now_btn.text() == "Desbloquear cofre"
    assert window.hero_title_label.text() == "Cofre bloqueado"

    # 3. Usuário desbloqueia o chaveiro externamente pelo Seahorse / Senhas e Chaves
    CredentialStore.set_mock_vault_locked(False)

    # 4. Próxima avaliação (ex.: tick de snapshot da sessão)
    snapshot = ServiceStatusSnapshot.from_dict(
        {
            "service_pid": 1234,
            "state": STATE_WAITING,
            "state_label": "Aguardando",
            "detail_message": "Pronto para sincronizar",
            "is_cycle_active": False,
            "configured_pair_ready": True,
        }
    )
    window._apply_service_snapshot(snapshot)
    qapp.processEvents()

    # 5. O BrisaSync detectou o desbloqueio não interativamente e transitou para pronto para sincronizar
    state, creds, _ = window._get_account_operational_state(interactive=False)
    assert state == "READY"
    assert creds is not None
    assert creds.account_email == "externo.desbloqueado@example.com"
    assert window.hero_sync_now_btn.text() == "Sincronizar agora"

    window.close()


def test_daemon_preconditions_and_attention_when_vault_locked(tmp_path: Path) -> None:
    """Verifica que o daemon não executa ciclos com cofre bloqueado e emite ATTENTION_VAULT_LOCKED."""
    CredentialStore.set_mock_vault_locked(True)

    db = BrisaDatabase(db_path=tmp_path / "daemon_locked.db")
    db.set_local_sync_folder("/tmp/local_test")
    db.set_remote_sync_folder(folder_name="RemoteTest", folder_id="id_test")

    store = _LockedTestingCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "daemon_rclone.conf",
    )

    daemon = BrisaSessionServiceDaemon(
        database=db,
        socket_path=tmp_path / "daemon_locked.sock",
        credential_store=store,
        bridge=bridge,
    )

    # Verifica pré-condições do ciclo
    can_run, new_state, reason = daemon._check_preconditions_before_cycle()
    assert can_run is False
    assert new_state == STATE_ATTENTION_REQUIRED
    assert "bloqueado" in reason.lower()

    # O snapshot deve carregar categoria ATTENTION_VAULT_LOCKED
    snap = daemon.get_status_snapshot()
    assert snap.attention_category == ATTENTION_VAULT_LOCKED
    assert "Cofre de Credenciais Bloqueado" in snap.attention_title

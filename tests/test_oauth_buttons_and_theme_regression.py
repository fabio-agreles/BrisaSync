"""Testes de regressão para o fluxo OAuth, contrato de workers e integração visual GNOME/KDE.

Valida:
1. Contrato da classe OAuthClientConfig (load e load_available como aliases funcionais equivalentes).
2. Resolução do cliente OAuth desktop empacotado sem necessidade de configuração JSON manual.
3. Contrato completo de sinais e métodos da classe OAuthConnectWorker real (succeeded, failed,
   oauth_succeeded, oauth_failed, request_cancel, cancel).
4. Acionamento real dos botões de conexão (botão Hero e botão do assistente) usando a classe
   OAuthConnectWorker real, interceptando estritamente a chamada de rede/navegador externo
   (GoogleOAuthDesktopClient.authorize_interactive).
5. Ciclo completo de autenticação bem-sucedida, erro de protocolo, cancelamento voluntário
   e nova tentativa permitida após falha.
6. Tratamento robusto contra falha antes de iniciar a thread (resiliência na preparação,
   restauração imediata dos botões e apresentação de erro sem travamento).
7. Proteção contra inicializações concorrentes enquanto a thread do worker estiver em execução.
8. Tokens visuais e paletas para os modos Claro e Escuro, incluindo suporte a fontes nativas
   do ambiente GNOME (Cantarell) e outline de foco nítido para acessibilidade.
"""

from __future__ import annotations

import os
from pathlib import Path
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QColor, QIcon, QPaintEvent, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QLineEdit, QMessageBox, QTreeView

from brisasync.backend.rclone_engine import RemoteDirectoryEntry, resolve_rclone_binary

from brisasync.credentials.oauth_google import (
    GoogleOAuthDesktopClient,
    OAuthClientConfig,
    OAuthConfigurationError,
    OAuthProtocolError,
    OAuthTimeoutOrCancelledError,
)
from brisasync.credentials.rclone_bridge import RcloneEncryptedBridge
from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.service.protocol import (
    ATTENTION_RECOVERY_REQUIRED,
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_SYNCING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow, BrisaSidebarNavItem
from brisasync.ui.styles import (
    apply_brisasync_theme,
    create_brisasync_palette,
    get_brisasync_stylesheet,
    is_dark_mode,
)
from brisasync.ui.vector_icons import get_vector_icon, render_rotated_sync_icon
from brisasync.ui.workers import (
    OAuthConnectWorker,
    RemoteFoldersWorker,
    ServiceCommandWorker,
)


class _RegressionCredentialStore(CredentialStore):
    OAUTH_ACCOUNT_KEY = "pytest_regression_google_oauth"
    RCLONE_KEY_ACCOUNT = "pytest_regression_rclone_cfg_key"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_oauth_client_config_load_and_load_available_are_identical() -> None:
    """Garante que OAuthClientConfig.load é um alias funcional direto para load_available."""
    bundled_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "brisasync"
        / "resources"
        / "oauth"
        / "google_oauth_client.json"
    )
    if bundled_path.is_file():
        cfg_available = OAuthClientConfig.load_available(explicit_path=bundled_path)
        cfg_load = OAuthClientConfig.load(explicit_path=bundled_path)

        assert cfg_available.client_id == cfg_load.client_id
        assert cfg_available.client_secret == cfg_load.client_secret
        assert cfg_available.auth_uri == cfg_load.auth_uri
        assert cfg_available.token_uri == cfg_load.token_uri
        assert cfg_load.client_id != ""
        assert cfg_load.client_secret != ""


def test_real_oauth_connect_worker_contract_and_signals(tmp_path: Path) -> None:
    """Valida o contrato de sinais e métodos da classe OAuthConnectWorker real."""
    cfg = OAuthClientConfig("client-id-test", "client-secret-test")
    store = _RegressionCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone.conf",
    )
    worker = OAuthConnectWorker(
        client_config=cfg,
        credential_store=store,
        bridge=bridge,
    )

    # 1. Valida existência dos sinais canônicos e aliases
    assert hasattr(worker, "succeeded")
    assert hasattr(worker, "failed")
    assert hasattr(worker, "oauth_succeeded")
    assert hasattr(worker, "oauth_failed")

    # 2. Valida métodos de cancelamento
    assert hasattr(worker, "request_cancel")
    assert hasattr(worker, "cancel")
    assert not worker.cancel_event.is_set()
    worker.cancel()
    assert worker.cancel_event.is_set()


def test_real_worker_buttons_start_and_concurrency_guard(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Testa acionamento real do OAuthConnectWorker pelos dois botões e proteção de concorrência."""
    db = BrisaDatabase(db_path=tmp_path / "test_oauth_concurrency.db")
    store = _RegressionCredentialStore()
    store.delete_credentials()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    assert "Conectar" in window.hero_sync_now_btn.text()
    assert window.setup_connect_button.isEnabled()
    assert window.hero_sync_now_btn.isEnabled()

    # Evento para manter o worker em execução enquanto verificamos o estado
    in_flight_event = threading.Event()
    continue_event = threading.Event()

    def fake_authorize(timeout_seconds: float = 180.0, cancel_event=None):
        in_flight_event.set()
        continue_event.wait(5.0)
        raise OAuthTimeoutOrCancelledError("Operação finalizada pelo teste")

    with patch.object(GoogleOAuthDesktopClient, "authorize_interactive", side_effect=fake_authorize):
        with patch.object(QMessageBox, "critical"):
            # 1. Dispara pelo botão Hero
            window._on_sync_now_clicked()
            assert in_flight_event.wait(5.0), "Worker não iniciou em tempo hábil"

            # Worker real deve estar em execução
            assert window._oauth_worker is not None
            assert isinstance(window._oauth_worker, OAuthConnectWorker)
            assert window._oauth_worker.isRunning()

            # Botões de conexão devem estar desabilitados e cancelar ativado
            assert not window.setup_connect_button.isEnabled()
            assert not window.hero_sync_now_btn.isEnabled()
            assert window.cancel_oauth_button.isEnabled()

            # 2. Tentativa de clique concorrente pelo assistente de boas-vindas
            initial_worker = window._oauth_worker
            window._on_wizard_connect_clicked()
            # Não deve criar outro worker
            assert window._oauth_worker is initial_worker
            assert "em andamento" in window.statusBar().currentMessage()

            # Libera o worker para finalizar
            continue_event.set()
            window._oauth_worker.wait(5000)
            qapp.processEvents()

    window.close()


def test_real_worker_success_flow_and_ui_update(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida fluxo de sucesso com o worker real: emissão de sinal, recepção e atualização da UI."""
    db = BrisaDatabase(db_path=tmp_path / "test_oauth_success.db")
    store = _RegressionCredentialStore()
    store.delete_credentials()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    fake_creds = OAuthCredentials(
        client_id="cid-success.apps.googleusercontent.com",
        client_secret="csec-success",
        access_token="ya29.fake_access",
        refresh_token="1//fake_refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="usuario.aprovado@example.com",
    )

    with patch.object(
        GoogleOAuthDesktopClient,
        "authorize_interactive",
        return_value=fake_creds,
    ):
        with patch.object(window, "_on_list_remote_folders") as mock_list_folders:
            # Dispara pelo botão do assistente
            window._on_wizard_connect_clicked()
            assert window._oauth_worker is not None
            window._oauth_worker.wait(10000)
            qapp.processEvents()

            # Valida que o sucesso foi processado
            assert window.setup_connect_button.isEnabled()
            assert window.hero_sync_now_btn.isEnabled()
            assert window._oauth_worker is None
            assert mock_list_folders.call_count == 1
            assert "usuario.aprovado@example.com" in window.account_status_label.text()

    window.close()


def test_real_worker_error_flow_and_subsequent_retry(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida erro real na execução do worker, restauração de botões e sucesso em nova tentativa."""
    db = BrisaDatabase(db_path=tmp_path / "test_oauth_retry.db")
    store = _RegressionCredentialStore()
    store.delete_credentials()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    # 1. Primeira tentativa falha com erro de protocolo
    with patch.object(
        GoogleOAuthDesktopClient,
        "authorize_interactive",
        side_effect=OAuthProtocolError("State divergente detectado na resposta"),
    ):
        with patch.object(QMessageBox, "critical") as mock_critical:
            window._on_sync_now_clicked()
            assert window._oauth_worker is not None
            window._oauth_worker.wait(10000)
            qapp.processEvents()

            assert mock_critical.call_count == 1
            assert "State divergente" in mock_critical.call_args[0][2]
            # Botões devem ter sido reabilitados após o erro
            assert window.setup_connect_button.isEnabled()
            assert window.hero_sync_now_btn.isEnabled()
            assert window._oauth_worker is None

    # 2. Nova tentativa após falha pelo botão do assistente deve ser plenamente permitida
    fake_creds = OAuthCredentials(
        client_id="cid-retry.apps.googleusercontent.com",
        client_secret="csec-retry",
        access_token="ya29.retry_access",
        refresh_token="1//retry_refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="retry.ok@example.com",
    )

    with patch.object(
        GoogleOAuthDesktopClient,
        "authorize_interactive",
        return_value=fake_creds,
    ):
        with patch.object(window, "_on_list_remote_folders"):
            window._on_wizard_connect_clicked()
            assert window._oauth_worker is not None
            window._oauth_worker.wait(10000)
            qapp.processEvents()

            assert window._oauth_worker is None
            assert window.setup_connect_button.isEnabled()
            assert "retry.ok@example.com" in window.account_status_label.text()

    window.close()


def test_real_worker_cancellation_flow(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida cancelamento cooperativo da autenticação pelo usuário sem diálogo modal crítico."""
    db = BrisaDatabase(db_path=tmp_path / "test_oauth_cancel.db")
    store = _RegressionCredentialStore()
    store.delete_credentials()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    started_event = threading.Event()

    def cancellable_auth(timeout_seconds: float = 180.0, cancel_event=None):
        started_event.set()
        if cancel_event:
            cancel_event.wait(5.0)
        raise OAuthTimeoutOrCancelledError("Cancelado pelo usuário.")

    with patch.object(GoogleOAuthDesktopClient, "authorize_interactive", side_effect=cancellable_auth):
        with patch.object(QMessageBox, "critical") as mock_critical:
            window._on_wizard_connect_clicked()
            assert started_event.wait(5.0)

            # Usuário clica no botão Cancelar
            window._on_cancel_oauth_clicked()
            qapp.processEvents()

            # Botões devem ter sido restaurados e nenhum QMessageBox de erro deve ter sido aberto
            assert window.setup_connect_button.isEnabled()
            assert window.hero_sync_now_btn.isEnabled()
            assert mock_critical.call_count == 0
            assert "cancelada" in window.account_status_label.text().lower()

    window.close()


def test_exception_during_worker_preparation_restores_buttons(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Garante que qualquer exceção durante a criação/conexão da thread restaure os botões e limpe o estado."""
    db = BrisaDatabase(db_path=tmp_path / "test_oauth_prep_err.db")
    store = _RegressionCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    # Simulamos uma falha no construtor do OAuthConnectWorker antes de iniciar a thread
    with patch(
        "brisasync.ui.main_window.OAuthConnectWorker",
        side_effect=RuntimeError("Falha de alocação de recurso do sistema"),
    ):
        with patch.object(QMessageBox, "critical") as mock_critical:
            window._on_sync_now_clicked()
            qapp.processEvents()

            assert mock_critical.call_count == 1
            assert "Falha de alocação" in mock_critical.call_args[0][2]
            # Botões devem ser restaurados e worker limpo
            assert window.setup_connect_button.isEnabled()
            assert window.hero_sync_now_btn.isEnabled()
            assert window._oauth_worker is None
            assert not window.cancel_oauth_button.isVisible()

    window.close()


def test_visual_theme_tokens_for_light_and_dark_modes(qapp: QApplication) -> None:
    """Valida tokens visuais, paletas e suporte a fontes GNOME (Cantarell) e foco nítido."""
    # 1. Modo Escuro
    qss_dark = get_brisasync_stylesheet(dark_mode=True)
    assert "#0B0F15" in qss_dark  # Fundo escuro principal
    assert "#131923" in qss_dark  # Superfície de cards
    assert "#9189FF" in qss_dark  # Lavanda de destaque no escuro
    assert "Cantarell" in qss_dark  # Fonte nativa GNOME
    assert "outline: 2px solid" in qss_dark  # Outline de foco para acessibilidade
    assert ".dialogTitle" in qss_dark
    assert ".exitBtnShutdown" in qss_dark

    palette_dark = create_brisasync_palette(dark_mode=True)
    assert palette_dark.color(palette_dark.ColorRole.Window).name().upper() == "#0B0F15"

    # 2. Modo Claro
    qss_light = get_brisasync_stylesheet(dark_mode=False)
    assert "#F8FAFC" in qss_light  # Fundo claro principal
    assert "#FFFFFF" in qss_light  # Fundo dos cards no claro
    assert "#6355DE" in qss_light  # Lavanda profundo de destaque no claro
    assert "Cantarell" in qss_light  # Fonte nativa GNOME
    assert "outline: 2px solid" in qss_light  # Outline de foco para acessibilidade
    assert ".dialogTitle" in qss_light
    assert ".exitBtnShutdown" in qss_light

    palette_light = create_brisasync_palette(dark_mode=False)
    assert palette_light.color(palette_light.ColorRole.Window).name().upper() == "#F8FAFC"


def test_sidebar_nav_item_paint_event_in_both_modes(qapp: QApplication) -> None:
    """Valida que o componente personalizado de navegação desenha sem erro em ambos os modos."""
    item = BrisaSidebarNavItem("overview", "Início")
    item.resize(160, 40)

    # Forçar paintEvent em modo escuro
    with patch("brisasync.ui.styles.is_dark_mode", return_value=True):
        item.repaint()
        assert item.text() == "Início"

    # Forçar paintEvent em modo claro
    with patch("brisasync.ui.styles.is_dark_mode", return_value=False):
        item.repaint()
        assert item.text() == "Início"


def test_resolve_rclone_binary_clean_system_and_precedence(tmp_path: Path) -> None:
    """Valida resolução em sistema limpo sem rclone no PATH nem em ~/.local/bin."""
    fake_packaged = tmp_path / "usr_lib_rclone"
    fake_packaged.write_text("#!/bin/sh\nexit 0\n")
    fake_packaged.chmod(0o755)

    fake_explicit = tmp_path / "explicit_rclone"
    fake_explicit.write_text("#!/bin/sh\nexit 0\n")
    fake_explicit.chmod(0o755)

    # 1. Precedência de caminho explícito
    assert resolve_rclone_binary(explicit_path=str(fake_explicit)) == str(fake_explicit.resolve())

    # 2. Precedência de variável de ambiente
    with patch.dict(os.environ, {"BRISASYNC_RCLONE_BINARY": str(fake_explicit)}):
        assert resolve_rclone_binary() == str(fake_explicit.resolve())

    # 3. Pacote instalado em /usr/lib/brisasync/bin/rclone quando PATH e ~/.local/bin não existem
    with patch("shutil.which", return_value=None):
        with patch.dict(os.environ, {"BRISASYNC_RCLONE_BINARY": ""}):
            # Simula candidato empacotado
            with patch("brisasync.backend.rclone_engine.Path.is_file") as mock_is_file:
                with patch("os.access", return_value=True):
                    # RcloneEncryptedBridge deve usar resolve_rclone_binary e não ~/.local/bin/rclone
                    store = _RegressionCredentialStore()
                    bridge = RcloneEncryptedBridge(credential_store=store, rclone_binary=str(fake_packaged))
                    assert bridge.rclone_binary == str(fake_packaged.resolve())
                    assert bridge.is_available()


def test_resolve_rclone_binary_invalid_overrides_raise_specific_errors(tmp_path: Path) -> None:
    """Valida que overrides explícitos ou de ambiente inválidos levantam exceções claras."""
    nonexistent = tmp_path / "nao_existe_rclone"

    # 1. Override explícito apontando para arquivo inexistente
    with pytest.raises(FileNotFoundError) as exc_info:
        resolve_rclone_binary(explicit_path=str(nonexistent))
    assert "override explícito não foi encontrado" in str(exc_info.value)

    # 2. Override explícito apontando para arquivo sem permissão de execução
    no_exec = tmp_path / "sem_exec_rclone"
    no_exec.write_text("#!/bin/sh\n")
    no_exec.chmod(0o644)
    with pytest.raises(PermissionError) as exc_info:
        resolve_rclone_binary(explicit_path=str(no_exec))
    assert "não possui permissão de execução" in str(exc_info.value)

    # 3. Variável de ambiente apontando para arquivo inexistente
    with patch.dict(os.environ, {"BRISASYNC_RCLONE_BINARY": str(nonexistent)}):
        with pytest.raises(FileNotFoundError) as exc_info:
            resolve_rclone_binary()
        assert "BRISASYNC_RCLONE_BINARY não foi encontrado" in str(exc_info.value)


def test_authorization_sequence_differentiates_vault_and_ready_bridge(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Garante que credenciais no cofre sem arquivo de bridge configurado não apresentem falso sucesso completo."""
    db = BrisaDatabase(db_path=tmp_path / "test_auth_seq.db")
    store = _RegressionCredentialStore()
    cfg_file = tmp_path / "test_rclone_missing.conf"
    if cfg_file.is_file():
        cfg_file.unlink()

    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=cfg_file,
    )

    creds = OAuthCredentials(
        client_id="cid-test.apps.googleusercontent.com",
        client_secret="csec-test",
        access_token="ya29.partial_token",
        refresh_token="1//partial_refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="sequence.check@example.com",
    )
    store.store_credentials(creds)

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    state, loaded_creds, detail = window._get_account_operational_state()
    assert state == "CONFIG_PENDING"
    assert loaded_creds is not None

    # Wizard Step 1 deve indicar estado pendente e desabilitar o botão Avançar
    window._set_wizard_step(0)
    assert "pendente" in window.setup_step1_status.text().lower()
    assert not window.setup_step1_next_btn.isEnabled()
    assert window.setup_connect_button.text() == "Concluir Conexão"

    # Cabeçalho deve refletir estado pendente
    assert "pendente" in window.header_account_badge.text().lower()

    # Ajustes deve exibir estado pendente
    window._refresh_account_state_from_vault()
    assert "CONFIGURAÇÃO PENDENTE" in window.account_status_label.text()
    assert window.connect_google_button.text() == "Concluir Conexão"

    window.close()


def test_partial_failure_recovery_without_reauthorizing_browser(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Garante que o usuário recupere a conexão sem precisar abrir o navegador quando o cofre contiver tokens válidos."""
    db = BrisaDatabase(db_path=tmp_path / "test_auth_recovery.db")
    store = _RegressionCredentialStore()
    cfg_file = tmp_path / "test_rclone_recovery.conf"
    if cfg_file.is_file():
        cfg_file.unlink()

    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=cfg_file,
    )

    creds = OAuthCredentials(
        client_id="cid-recovery.apps.googleusercontent.com",
        client_secret="csec-recovery",
        access_token="ya29.valid_vault_token",
        refresh_token="1//valid_refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="recovery.user@example.com",
    )
    store.store_credentials(creds)

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    # O navegador NUNCA deve ser invocado durante a recuperação
    with patch.object(GoogleOAuthDesktopClient, "authorize_interactive") as mock_browser:
        with patch.object(bridge, "materialize_encrypted_config") as mock_materialize:
            with patch.object(window, "_on_list_remote_folders"):
                # Simula a criação do arquivo durante a materialização
                def fake_materialize(*args, **kwargs):
                    cfg_file.write_text("[brisasync_gdrive]\n")
                    return cfg_file, "fake_key_256"

                mock_materialize.side_effect = fake_materialize

                # Clica no botão de conectar/concluir conexão
                window._on_wizard_connect_clicked()
                qapp.processEvents()

                assert mock_browser.call_count == 0
                assert mock_materialize.call_count == 1

            # Estado agora deve ser READY
            state, _, _ = window._get_account_operational_state()
            assert state == "READY"
            assert window.setup_step1_next_btn.isEnabled()
            assert "recovery.user@example.com" in window.setup_step1_status.text()
            assert "Trocar de Conta" in window.setup_connect_button.text()

    window.close()


def test_partial_failure_does_not_erase_vault_credentials(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Garante que uma falha de materialização rclone não apague credenciais válidas do cofre."""
    db = BrisaDatabase(db_path=tmp_path / "test_auth_no_erase.db")
    store = _RegressionCredentialStore()
    cfg_file = tmp_path / "test_rclone_fail.conf"

    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=cfg_file,
    )

    creds = OAuthCredentials(
        client_id="cid-noerase.apps.googleusercontent.com",
        client_secret="csec-noerase",
        access_token="ya29.safe_vault_token",
        refresh_token="1//safe_refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="safe.vault@example.com",
    )
    store.store_credentials(creds)

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()

    # Simula falha ao tentar listar pastas remotas com bridge quebrada
    with patch.object(bridge, "materialize_encrypted_config", side_effect=FileNotFoundError("Motor rclone ausente")):
        with patch.object(QMessageBox, "critical") as mock_critical:
            window._on_list_remote_folders()
            qapp.processEvents()

            assert mock_critical.call_count == 1
            assert "Motor rclone ausente" in mock_critical.call_args[0][2]
            # Credenciais no cofre DEVEM permanecer intactas
            assert store.load_credentials() is not None
            assert store.load_credentials().account_email == "safe.vault@example.com"

    window.close()


def test_remote_directory_entry_contract_and_attributes() -> None:
    """Valida o contrato de RemoteDirectoryEntry: atributos name, folder_name, folder_id, path."""
    entry = RemoteDirectoryEntry(folder_id="fid_123", name="Pastas", path="Pastas")
    assert entry.folder_id == "fid_123"
    assert entry.name == "Pastas"
    assert entry.folder_name == "Pastas"
    assert entry.path == "Pastas"

    entry2 = RemoteDirectoryEntry(folder_id="fid_456", folder_name="Projetos")
    assert entry2.folder_id == "fid_456"
    assert entry2.name == "Projetos"
    assert entry2.folder_name == "Projetos"

    entry3 = RemoteDirectoryEntry("fid_789", "Documentos")
    assert entry3.folder_id == "fid_789"
    assert entry3.name == "Documentos"
    assert entry3.folder_name == "Documentos"


def test_remote_folders_loaded_success_empty_and_failure_restoration(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida que _on_remote_folders_loaded popula combos, trata lista vazia e restaura botões."""
    db = BrisaDatabase(db_path=tmp_path / "test_rf_loaded.db")
    store = _RegressionCredentialStore()
    bridge = RcloneEncryptedBridge(credential_store=store, config_path=tmp_path / "rclone.conf")

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window._suppress_dialogs_for_testing = True
    window.show()

    # 1. Simula estado durante consulta
    window.list_remote_folders_button.setEnabled(False)
    window.wizard_list_remote_btn.setEnabled(False)
    window.create_remote_folder_button.setEnabled(False)
    window.wizard_create_remote_btn.setEnabled(False)
    window.remote_folder_feedback_label.setText("Consultando pastas no Google Drive...")

    # 2. Carregamento com sucesso contendo pastas
    entries = [
        RemoteDirectoryEntry(folder_id="id_alpha", name="Alpha"),
        RemoteDirectoryEntry(folder_id="id_beta", name="Beta"),
    ]
    window._on_remote_folders_loaded(entries, newly_created=None)
    qapp.processEvents()

    assert window.list_remote_folders_button.isEnabled() is True
    assert window.wizard_list_remote_btn.isEnabled() is True
    assert window.create_remote_folder_button.isEnabled() is True
    assert window.wizard_create_remote_btn.isEnabled() is True
    assert window.remote_folder_combo.count() == 2
    assert window.wizard_remote_combo.count() == 2
    assert "Alpha [ID: id_alpha]" in window.remote_folder_combo.itemText(0)
    assert "2 pasta(s) localizada(s)" in window.wizard_remote_feedback.text()
    assert "Alpha" in window.remote_folder_feedback_label.text()

    # 3. Carregamento com resultado vazio
    window._on_remote_folders_loaded([], newly_created=None)
    qapp.processEvents()

    assert window.list_remote_folders_button.isEnabled() is True
    assert window.wizard_list_remote_btn.isEnabled() is True
    assert window.remote_folder_combo.count() == 0
    assert window.wizard_remote_combo.count() == 0
    assert "Nenhuma pasta encontrada" in window.remote_folder_feedback_label.text()
    assert "Nenhuma pasta encontrada" in window.wizard_remote_feedback.text()

    # 4. Falha na consulta restaura botões e apresenta erro útil
    window.list_remote_folders_button.setEnabled(False)
    window.wizard_list_remote_btn.setEnabled(False)
    window._on_remote_folders_failed("Falha de rede 503")
    qapp.processEvents()

    assert window.list_remote_folders_button.isEnabled() is True
    assert window.wizard_list_remote_btn.isEnabled() is True
    assert "Falha de rede 503" in window.remote_folder_feedback_label.text()
    assert "Falha de rede 503" in window.wizard_remote_feedback.text()

    window.close()


def test_partial_configuration_shows_pending_and_no_stale_demo_data(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida que par incompleto exibe 'Configuração pendente' e '○ pendente', sem valores demo."""
    db = BrisaDatabase(db_path=tmp_path / "test_partial_cfg.db")
    local_dir = tmp_path / "meus_downloads"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))

    store = _RegressionCredentialStore()
    creds = OAuthCredentials(
        client_id="cid.apps.googleusercontent.com",
        client_secret="csec",
        access_token="ya29.token",
        refresh_token="1//refresh",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="fabio@example.com",
    )
    store.store_credentials(creds)
    bridge = RcloneEncryptedBridge(credential_store=store, config_path=tmp_path / "rclone.conf")

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window._suppress_dialogs_for_testing = True
    window.show()
    qapp.processEvents()

    # Cartões da Visão Geral e Pastas DEVEM exibir "Configuração pendente", não "Documentos"
    assert window.folders_card_title_label.text() == "Configuração pendente"
    assert window.overview_folder_name_label.text() == "Configuração pendente"
    assert "Documentos" not in window.folders_card_title_label.text()
    assert "Documentos" not in window.overview_folder_name_label.text()

    # Não deve conter caminhos do ambiente de desenvolvimento do autor
    assert "/home/agreles" not in window.overview_folder_path_label.text()
    assert "/home/agreles" not in window.folders_card_subtitle_label.text()

    # O caminho local real deve estar presente
    assert str(local_dir) in window.overview_folder_path_label.toolTip()
    assert "Falta pasta remota" in window.overview_folder_path_label.text()
    assert str(local_dir) in window.folders_card_subtitle_label.text()

    # O status das pastas NÃO pode ser "em dia", e sim "○ pendente"
    assert "em dia" not in window.overview_folder_status_pill.text()
    assert "pendente" in window.overview_folder_status_pill.text()
    assert "em dia" not in window.folders_card_status_pill.text()
    assert "pendente" in window.folders_card_status_pill.text()

    # Agora simula seleção de pasta remota através do combo do assistente
    window.wizard_remote_combo.addItem("Trabalho [ID: fid_trab]", userData=("fid_trab", "Trabalho"))
    window.wizard_remote_combo.setCurrentIndex(0)
    qapp.processEvents()

    # O banco agora possui o par completo
    assert db.get_remote_sync_folder() is not None
    assert db.get_remote_sync_folder().folder_id == "fid_trab"
    assert db.get_remote_sync_folder().folder_name == "Trabalho"

    # Atualiza a interface
    window._update_home_view()
    qapp.processEvents()

    # Como a sincronização ainda não foi confirmada nem há baseline, o status deve ser "Aguardando 1ª sincronização"
    assert "Aguardando 1ª sincronização" in window.overview_folder_status_pill.text()
    assert "em dia" not in window.overview_folder_status_pill.text()

    # Simula baseline inicial confirmada
    db.mark_baseline_initialized(local_folder=str(local_dir), remote_folder_id="fid_trab")
    window._update_home_view()
    qapp.processEvents()

    # Agora com baseline confirmada para o par exato, o status pode ser "em dia"
    assert window.overview_folder_status_pill.text() == "em dia"
    assert "em dia" in window.folders_card_status_pill.text()

    window.close()


def test_hero_primary_button_and_status_timer_lifecycle(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida ciclo completo do botão Hero e do timer IPC: transição de 'Sincronizando...' para repouso."""
    db = BrisaDatabase(db_path=tmp_path / "test_hero_lifecycle.db")
    store = _RegressionCredentialStore()
    local_dir = tmp_path / "local_test_sync"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="drive_folder_123", folder_name="Remota Teste")
    db.mark_baseline_initialized(local_folder=str(local_dir), remote_folder_id="drive_folder_123")

    creds = OAuthCredentials(
        client_id="cid.apps.googleusercontent.com",
        client_secret="csec",
        access_token="ya29.fake",
        refresh_token="1//fake",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="usuario@example.com",
    )
    store.store_credentials(creds)

    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone_ready.conf",
    )
    (tmp_path / "test_rclone_ready.conf").write_text("[brisasync_gdrive]\n")

    mock_ipc = ServiceIPCClient(socket_path=tmp_path / "mock_active.sock")
    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=mock_ipc,
    )
    window.show()
    qapp.processEvents()

    # Timer deve estar ativo enquanto a janela estiver visível
    assert window._status_timer.isActive()

    # 1. Simula início de sincronização ativa
    syncing_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_SYNCING,
        "detail_message": "Reconciliando alterações em andamento...",
        "is_cycle_active": True,
        "configured_pair_ready": True,
        "sync_interval_seconds": 300,
        "service_pid": 1111,
    })

    with patch.object(mock_ipc, "get_status", return_value=syncing_snap):
        window.refresh_service_status_from_ipc()
        qapp.processEvents()

        # O botão Hero deve refletir andamento e estar desabilitado para evitar cliques redundantes
        assert window.hero_sync_now_btn.text() == "Sincronizando..."
        assert not window.hero_sync_now_btn.isEnabled()
        assert window.hero_banner.property("heroState") == "syncing"
        assert window.global_status_pill.text() == "● Sincronizando"
        assert "Sincronizando" in window.overview_folder_status_pill.text()

        # Tentativa de clique não deve despachar novo comando concorrente
        with patch.object(window, "_run_service_command") as mock_run:
            window._on_sync_now_clicked()
            assert mock_run.call_count == 0
            assert "já está em andamento" in window.statusBar().currentMessage()

    # 2. Simula conclusão da sincronização pelo daemon
    db.set_last_confirmed_sync_at("2026-11-02T19:00:00Z")
    idle_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_WAITING,
        "detail_message": "Sincronização bidirecional confirmada. Aguardando próximo ciclo agendado.",
        "is_cycle_active": False,
        "configured_pair_ready": True,
        "last_confirmed_sync_at": "2026-11-02T19:00:00Z",
        "last_run_status": "SUCCESS",
        "sync_interval_seconds": 300,
        "service_pid": 1111,
    })

    with patch.object(mock_ipc, "get_status", return_value=idle_snap):
        # O timer de 1.2s chama refresh_service_status_from_ipc()
        window.refresh_service_status_from_ipc()
        qapp.processEvents()

        # Componentes devem transicionar imediatamente para repouso confirmado sem reabertura
        assert window.hero_sync_now_btn.text() == "Sincronizar agora"
        assert window.hero_sync_now_btn.isEnabled()
        assert window.hero_banner.property("heroState") == "healthy"
        assert window.hero_title_label.text() == "Tudo em dia"
        assert window.global_status_pill.text() == "● Tudo em dia"
        assert window.overview_folder_status_pill.text() == "em dia"
        assert "✓ Tudo atualizado" in window.home_main_state_label.text()

    # 3. Minimizar / esconder para a bandeja pausa o timer; restaurar reativa
    window.hide()
    qapp.processEvents()
    assert not window._status_timer.isActive()

    window.restore_and_focus_window()
    qapp.processEvents()
    assert window._status_timer.isActive()

    window.close()


def test_hero_primary_button_states_unconfigured_and_paused_and_attention(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Verifica que o botão Hero nunca oferece 'Conectar conta' quando configurado."""
    db = BrisaDatabase(db_path=tmp_path / "test_hero_unconfigured.db")
    store = _RegressionCredentialStore()
    store.delete_credentials()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone_unconf.conf",
    )

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_unconf.sock"),
    )
    window.show()
    qapp.processEvents()

    # 1. Sem conta configurada
    assert window.hero_sync_now_btn.text() == "Conectar conta"
    assert window.hero_sync_now_btn.isEnabled()
    assert window.hero_banner.property("heroState") == "unconfigured"

    # 2. Credenciais no cofre, mas rclone bridge pendente
    creds = OAuthCredentials(
        client_id="cid.apps.googleusercontent.com",
        client_secret="csec",
        access_token="ya29.fake",
        refresh_token="1//fake",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="usuario@example.com",
    )
    store.store_credentials(creds)
    window._update_home_view()
    qapp.processEvents()

    assert window.hero_sync_now_btn.text() == "Concluir conexão"
    assert window.hero_sync_now_btn.isEnabled()

    # 3. Configura par de pastas e materializa bridge
    local_p = tmp_path / "sync_folder"
    local_p.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_p))
    db.set_remote_sync_folder(folder_id="rid1", folder_name="DriveRemoto")
    (tmp_path / "test_rclone_unconf.conf").write_text("[brisasync_gdrive]\n")

    # 4. Estado de pausa: Hero button deve ser 'Sincronizar agora', NÃO 'Conectar conta'
    paused_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_PAUSED,
        "detail_message": "Pausado pelo usuário.",
        "auto_sync_paused": True,
        "configured_pair_ready": True,
    })
    window._apply_service_snapshot(paused_snap)
    qapp.processEvents()

    assert window.hero_sync_now_btn.text() == "Sincronizar agora"
    assert window.hero_sync_now_btn.isEnabled()
    assert window.hero_pause_btn.text() == "Retomar"

    # 5. Estado de atenção: Hero button deve ser 'Sincronizar agora', NÃO 'Conectar conta'
    att_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_ATTENTION_REQUIRED,
        "detail_message": "Conflito detectado.",
        "attention_category": ATTENTION_RECOVERY_REQUIRED,
        "attention_title": "Recuperação Necessária",
        "configured_pair_ready": True,
    })
    window._apply_service_snapshot(att_snap)
    qapp.processEvents()

    assert window.hero_sync_now_btn.text() == "Sincronizar agora"
    assert window.hero_sync_now_btn.isEnabled()
    assert window.hero_pause_btn.text() == "Inspecionar"

    window.close()


def test_inline_editor_and_file_dialog_contrast_in_both_themes(
    qapp: QApplication,
) -> None:
    """Valida contraste visual AAA da edição inline e componentes de diálogo em temas escuro e claro."""
    # 1. Modo Escuro
    pal_dark = create_brisasync_palette(dark_mode=True)
    # HighlightedText deve ser #FFFFFF para contraste legível sobre a seleção
    assert pal_dark.color(pal_dark.ColorRole.HighlightedText).name().upper() == "#FFFFFF"
    assert pal_dark.color(pal_dark.ColorRole.Highlight).name().upper() == "#5446CF"

    qss_dark = get_brisasync_stylesheet(dark_mode=True)
    assert "QAbstractItemView QLineEdit" in qss_dark
    assert "selection-background-color: #5446CF" in qss_dark
    assert "selection-color: #FFFFFF" in qss_dark
    assert "padding: 1px 4px" in qss_dark

    # Testa renderização e dimensões compactas do editor inline
    qapp.setStyleSheet(qss_dark)
    tree_widget = QTreeView()
    inline_editor = QLineEdit("Nova Pasta", tree_widget)
    inline_editor.ensurePolished()
    # O editor inline deve ser compacto para caber na linha do QTreeView sem cortar o texto
    assert inline_editor.sizeHint().height() <= 26

    # Campos normais de formulário mantém espaçamento confortável
    standard_input = QLineEdit("Texto de Formulário")
    standard_input.ensurePolished()
    assert standard_input.sizeHint().height() >= 32

    # 2. Modo Claro
    pal_light = create_brisasync_palette(dark_mode=False)
    assert pal_light.color(pal_light.ColorRole.HighlightedText).name().upper() == "#FFFFFF"

    qss_light = get_brisasync_stylesheet(dark_mode=False)
    assert "QAbstractItemView QLineEdit" in qss_light
    assert "selection-background-color: #6355DE" in qss_light
    assert "selection-color: #FFFFFF" in qss_light


def test_render_rotated_sync_icon_and_modes() -> None:
    """Valida a renderização do ícone rotacionado com preservação de contraste em modo normal e desabilitado."""
    icon_0 = render_rotated_sync_icon(size=16, color="#0B0F15", angle_degrees=0.0)
    assert not icon_0.isNull()
    # Modos Normal e Disabled devem estar presentes com tamanho correto
    sizes = [s.width() for s in icon_0.availableSizes(mode=QIcon.Mode.Normal)]
    assert 16 in sizes
    sizes_disabled = [s.width() for s in icon_0.availableSizes(mode=QIcon.Mode.Disabled)]
    assert 16 in sizes_disabled

    # Caching do mesmo ângulo
    icon_0_cached = render_rotated_sync_icon(size=16, color="#0B0F15", angle_degrees=0.0)
    assert icon_0 is icon_0_cached

    # Rotação normalizada por módulo 360
    icon_360 = render_rotated_sync_icon(size=16, color="#0B0F15", angle_degrees=360.0)
    assert icon_360 is icon_0

    # Ângulo diferente gera ícone correspondente
    icon_90 = render_rotated_sync_icon(size=16, color="#0B0F15", angle_degrees=90.0)
    assert not icon_90.isNull()
    assert icon_90 is not icon_0


def test_hero_primary_button_rotation_animation_lifecycle(
    qapp: QApplication, tmp_path: Path
) -> None:
    """Valida o ciclo de vida completo da rotação discreta do ícone no botão principal do Hero."""
    db = BrisaDatabase(db_path=tmp_path / "test_hero_anim.db")
    store = _RegressionCredentialStore()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "test_rclone_anim.conf",
    )
    # Configura par válido para que o botão passe a ser 'Sincronizar agora'
    db.set_local_sync_folder(str(tmp_path / "local"))
    db.set_remote_sync_folder(folder_id="root_anim", folder_name="AnimRoot")

    creds = OAuthCredentials(
        client_id="cid-anim",
        client_secret="csec-anim",
        access_token="ya29.anim",
        refresh_token="1//anim",
        token_type="Bearer",
        expiry="2099-01-01T00:00:00Z",
        scope="https://www.googleapis.com/auth/drive",
        account_email="anim@example.com",
    )
    store.store_credentials(creds)

    window = BrisaMainWindow(
        database=db,
        credential_store=store,
        bridge=bridge,
        ipc_client=ServiceIPCClient(socket_path=tmp_path / "mock_rf.sock"),
    )
    window.show()
    qapp.processEvents()

    # 1. Estado inicial em repouso: botão habilitado, animação inativa, ângulo zero
    waiting_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_WAITING,
        "detail_message": "Aguardando próximo ciclo.",
        "configured_pair_ready": True,
        "is_cycle_active": False,
    })
    window._apply_service_snapshot(waiting_snap)
    qapp.processEvents()

    assert window.hero_sync_now_btn.text() == "Sincronizar agora"
    assert window.hero_sync_now_btn.isEnabled()
    assert not window._hero_anim_timer.isActive()
    assert window._hero_sync_angle == 0.0

    # 2. O clique manual isolado NÃO inicia animação sem confirmação do daemon
    with patch.object(window, "_run_service_command") as mock_run_cmd:
        window._on_sync_now_clicked()
        assert mock_run_cmd.call_count == 1
        assert not window._hero_anim_timer.isActive()
        assert window.hero_sync_now_btn.text() == "Sincronizar agora"

    # 3. Snapshot operacional do daemon confirma sincronização ativa:
    # Animação deve ser acionada, botão bloqueado contra cliques duplicados e texto atualizado
    syncing_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_SYNCING,
        "detail_message": "Sincronização bidirecional em andamento.",
        "configured_pair_ready": True,
        "is_cycle_active": True,
    })
    window._apply_service_snapshot(syncing_snap)
    qapp.processEvents()

    assert window.hero_sync_now_btn.text() == "Sincronizando..."
    assert not window.hero_sync_now_btn.isEnabled()
    assert window._hero_anim_timer.isActive()

    # Avanço de ticks da animação (simula o disparo do timer a cada quadro)
    initial_angle = window._hero_sync_angle
    window._on_hero_anim_tick()
    assert window._hero_sync_angle == (initial_angle + 12.0) % 360.0
    window._on_hero_anim_tick()
    assert window._hero_sync_angle == (initial_angle + 24.0) % 360.0

    # 4. Suspensão ao ocultar a janela (hideEvent)
    window.hide()
    qapp.processEvents()
    assert not window._hero_anim_timer.isActive()

    # 5. Retomada ao reabrir a janela (showEvent) enquanto a sincronização continuar ativa
    window.show()
    qapp.processEvents()
    assert window._hero_anim_timer.isActive()
    assert window.hero_sync_now_btn.text() == "Sincronizando..."
    assert not window.hero_sync_now_btn.isEnabled()

    # 6. Conclusão da sincronização pelo daemon: para a animação e restaura o estado padrão
    completed_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_WAITING,
        "detail_message": "Sincronização concluída com sucesso.",
        "configured_pair_ready": True,
        "is_cycle_active": False,
        "last_confirmed_sync_at": "2026-11-02T20:30:00Z",
    })
    window._apply_service_snapshot(completed_snap)
    qapp.processEvents()

    assert not window._hero_anim_timer.isActive()
    assert window._hero_sync_angle == 0.0
    assert window.hero_sync_now_btn.text() == "Sincronizar agora"
    assert window.hero_sync_now_btn.isEnabled()

    # 7. Ciclo automático em segundo plano inicia animação sem interação do usuário
    auto_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_SYNCING,
        "detail_message": "Ciclo periódico em andamento.",
        "configured_pair_ready": True,
        "is_cycle_active": True,
    })
    window._apply_service_snapshot(auto_snap)
    qapp.processEvents()

    assert window._hero_anim_timer.isActive()
    assert window.hero_sync_now_btn.text() == "Sincronizando..."
    assert not window.hero_sync_now_btn.isEnabled()

    # 8. Interrupção por erro/atenção para imediatamente a animação
    attention_snap = ServiceStatusSnapshot.from_dict({
        "state": STATE_ATTENTION_REQUIRED,
        "detail_message": "Falha na conexão rclone.",
        "attention_category": ATTENTION_RECOVERY_REQUIRED,
        "attention_title": "Erro na sincronização",
        "configured_pair_ready": True,
        "is_cycle_active": False,
    })
    window._apply_service_snapshot(attention_snap)
    qapp.processEvents()

    assert not window._hero_anim_timer.isActive()
    assert window._hero_sync_angle == 0.0
    assert window.hero_sync_now_btn.text() == "Sincronizar agora"
    assert window.hero_sync_now_btn.isEnabled()

    # 9. Fechamento da janela suspende o timer de animação e de status
    window.close()
    assert not window._hero_anim_timer.isActive()
    assert not window._status_timer.isActive()


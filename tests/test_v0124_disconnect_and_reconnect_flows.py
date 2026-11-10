"""Testes de validação dos requisitos da v0.1.24 do BrisaSync:
1. Diferenciação de desconexão voluntária com estado neutro "Nenhuma conta conectada".
2. Preservação de pares salvos em "Aguardando conexão" com 0 pastas ativas e bloqueio remoto.
3. Botão "Remover vínculo de sincronização" em Pastas, acessível sem conta e com preservação de arquivos e histórico.
4. Parada segura/coordenação com o daemon em ciclo ativo na desconexão.
5. Confirmação de identidade na reconexão (mesma conta vs conta diferente com invalidação de baseline).
6. Paridade i18n PT-BR e EN dos novos rótulos e alternância dinâmica.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync.i18n import get_current_language, set_current_language, tr
from brisasync.i18n.catalog import MESSAGES
from brisasync.storage.database import BrisaDatabase
from brisasync.service.daemon import (
    STATE_WAITING,
    STATE_SYNCING,
    ServiceStatusSnapshot,
)
from brisasync.credentials.store import OAuthCredentials
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.tray import BrisaTrayController, TRAY_STATE_HEALTHY


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_1_voluntary_disconnect_state_neutrality(tmp_path: Path, qapp: QApplication) -> None:
    db = BrisaDatabase(db_path=tmp_path / "test_neutral.db")
    local_dir = tmp_path / "minha_pasta_local"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="drive_folder_abc", folder_name="Docs Drive")
    db.set_pair_linked_account_email("antigo@gmail.com")
    db.set_voluntary_disconnect(True)

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win.show()
    qapp.processEvents()

    try:
        # 1. Badge do cabeçalho neutro
        assert win.header_account_badge.text() == tr("header_not_connected")
        assert "8B949E" in win.header_account_badge.styleSheet()

        # 2. Hero banner neutro
        assert win.hero_title_label.text() == tr("hero_title_no_account")
        assert win.hero_subtitle_label.text() == tr("hero_subtitle_no_account")
        assert win.hero_sync_now_btn.text() == tr("hero_btn_connect_account_action")
        assert win.hero_metric_folders_val.text() == "0 de 1"

        # 3. Cartão de contas na Visão Geral
        assert win.overview_account_email_label.text() == tr("menu_no_account")
        assert win.overview_account_status_label.text() == tr("folder_status_not_connected")

        # 4. Pílulas de status e conferência pré-execução
        assert win.overview_folder_status_pill.text() == tr("folder_status_waiting_account")
        assert win.folders_card_status_pill.text() == tr("folder_status_waiting_account")
        assert "[AGUARDANDO CONEXÃO]" in win.sync_target_preview_label.text()
        assert not win.folders_page_sync_btn.isEnabled()
        assert win.folders_page_sync_btn.toolTip() == tr("sync_blocked_no_account")

        # 5. Botão "Remover vínculo" visível na aba Pastas e habilitado
        win.set_current_page(1)
        qapp.processEvents()
        assert win.folders_remove_pair_btn.isVisible()
        assert win.folders_remove_pair_btn.isEnabled()
        assert win.folders_remove_pair_btn.text() == tr("folders_btn_remove_pair")

        # 6. Alerta indevido de atenção ausente
        assert not win.attention_banner_frame.isVisible()
        assert win.overview_operation_header.text() == tr("folder_status_waiting_account")

        # 7. Persistência da distinção após reiniciar (novo objeto lendo o mesmo banco)
        win2 = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
        win2._suppress_dialogs_for_testing = True
        win2.show()
        qapp.processEvents()
        try:
            assert win2.hero_title_label.text() == tr("hero_title_no_account")
            assert win2.hero_metric_folders_val.text() == "0 de 1"
            assert win2.folders_card_status_pill.text() == tr("folder_status_waiting_account")
        finally:
            win2.close()
    finally:
        win.close()


def test_2_tray_neutral_state_on_voluntary_disconnect(tmp_path: Path, qapp: QApplication) -> None:
    db = BrisaDatabase(db_path=tmp_path / "test_tray.db")
    db.set_voluntary_disconnect(True)

    tray = BrisaTrayController(database=db, force_tray_available=True)
    tray.update_from_snapshot(None)

    assert tray._current_state == TRAY_STATE_HEALTHY
    assert tray.status_header_action.text() == tr("tray_status_header_no_account")
    assert tray.tooltip_text == tr("tray_tooltip_no_account", app_name="BrisaSync")
    assert not tray.sync_now_action.isEnabled()
    assert not tray.pause_resume_action.isEnabled()


def test_3_disconnect_during_active_sync_cycle_coordination(tmp_path: Path, qapp: QApplication) -> None:
    db = BrisaDatabase(db_path=tmp_path / "test_active_disc.db")
    db.set_local_sync_folder(str(tmp_path / "loc"))
    db.set_remote_sync_folder(folder_id="f_id", folder_name="F_Name")
    db.set_pair_linked_account_email("user@gmail.com")

    mock_ipc = MagicMock()
    # Simula status inicial ativo e em seguida finalizado
    snap_active = ServiceStatusSnapshot(
        service_pid=1111,
        state=STATE_SYNCING,
        state_label="SINCRONIZANDO",
        detail_message="Sincronizando...",
        is_cycle_active=True,
        active_rclone_pid=2222,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=None,
        last_run_status="RUNNING",
        last_error_reason=None,
        autostart_enabled=False,
        configured_pair_ready=True,
    )
    snap_idle = ServiceStatusSnapshot(
        service_pid=1111,
        state=STATE_WAITING,
        state_label="AGUARDANDO",
        detail_message="Parado",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=None,
        last_run_status="STOPPED",
        last_error_reason=None,
        autostart_enabled=False,
        configured_pair_ready=True,
    )
    mock_ipc.get_status.side_effect = [snap_active, snap_idle, snap_idle]

    win = BrisaMainWindow(database=db, ipc_client=mock_ipc, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win._last_snapshot = snap_active
    win.show()
    qapp.processEvents()

    try:
        win.disconnect_google_account(prompt_confirmation=False)
        qapp.processEvents()

        # Verifica que solicitou a parada do ciclo ativo e a desconexão do daemon
        mock_ipc.execute_command.assert_any_call("stop_current")
        mock_ipc.execute_command.assert_any_call("disconnect_account")
        assert db.is_voluntary_disconnect() is True
        assert win.hero_title_label.text() == tr("hero_title_no_account")
    finally:
        win.close()


def test_4_remove_sync_pair_without_account(tmp_path: Path, qapp: QApplication) -> None:
    db = BrisaDatabase(db_path=tmp_path / "test_remove_pair.db")
    local_dir = tmp_path / "local_docs"
    local_dir.mkdir(parents=True, exist_ok=True)
    test_file = local_dir / "arquivo_preservado.txt"
    test_file.write_text("conteúdo local intacto")

    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="remote_drive_xyz", folder_name="Docs Remoto")
    db.set_pair_linked_account_email("user@gmail.com")
    db.set_voluntary_disconnect(True)

    # Insere execução histórica para garantir preservação do histórico
    db.record_sync_run(
        started_at="2026-11-08T12:00:00Z",
        finished_at="2026-11-08T12:01:00Z",
        path1=str(local_dir),
        path2="gdrive:Docs Remoto",
        operation="bisync",
        status="SUCCESS",
        exit_code=0,
        summary="Sincronização bidirecional concluída com sucesso.",
    )
    assert db.count_recent_sync_runs() == 1

    mock_ipc = MagicMock()
    win = BrisaMainWindow(database=db, ipc_client=mock_ipc, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win.show()
    qapp.processEvents()

    try:
        win._on_remove_pair_clicked()
        qapp.processEvents()

        # Configuração do par removida
        assert db.get_local_sync_folder() is None
        assert db.get_remote_sync_folder() is None
        assert db.get_pair_linked_account_email() is None

        # Daemon avisado para não mais agendar
        mock_ipc.execute_command.assert_called_with("clear_pair")

        # Arquivos locais preservados intactos
        assert test_file.exists()
        assert test_file.read_text() == "conteúdo local intacto"

        # Histórico de execuções preservado intacto
        assert db.count_recent_sync_runs() == 1

        # Interface alternou para assistente de configuração
        assert win.home_unconfigured_container.isVisible()
        assert not win.home_configured_container.isVisible()
    finally:
        win.close()


def test_5_reconnection_same_account_vs_different_account(tmp_path: Path, qapp: QApplication) -> None:
    db = BrisaDatabase(db_path=tmp_path / "test_reconnect.db")
    local_dir = tmp_path / "pasta_local"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="remote_id_1", folder_name="Remoto 1")
    db.mark_baseline_initialized(local_folder=str(local_dir), remote_folder_id="remote_id_1")
    db.set_pair_linked_account_email("conta1@gmail.com")
    db.set_voluntary_disconnect(True)

    mock_ipc = MagicMock()
    win = BrisaMainWindow(database=db, ipc_client=mock_ipc, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win.show()
    qapp.processEvents()

    try:
        # Caso A: Reconexão com a MESMA conta
        creds_same = OAuthCredentials(
            client_id="test_client_id",
            client_secret="test_client_secret",
            access_token="tok_123",
            refresh_token="ref_123",
            token_type="Bearer",
            expiry="2027-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="conta1@gmail.com",
        )
        win._on_oauth_succeeded(creds_same)
        qapp.processEvents()

        assert db.is_voluntary_disconnect() is False
        assert db.get_pair_linked_account_email() == "conta1@gmail.com"
        assert db.get_remote_sync_folder() is not None
        assert db.is_baseline_initialized(local_folder=str(local_dir), remote_folder_id="remote_id_1") is True
        mock_ipc.execute_command.assert_called_with("account_connected")

        # Caso B: Reconexão com conta DIFERENTE
        mock_ipc.reset_mock()
        db.set_voluntary_disconnect(True)
        creds_diff = OAuthCredentials(
            client_id="test_client_id",
            client_secret="test_client_secret",
            access_token="tok_999",
            refresh_token="ref_999",
            token_type="Bearer",
            expiry="2027-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="conta2@gmail.com",
        )
        win._on_oauth_succeeded(creds_diff)
        qapp.processEvents()

        # Baseline anterior invalidada por segurança
        assert db.is_baseline_initialized(local_folder=str(local_dir), remote_folder_id="remote_id_1") is False
        # Pasta remota anterior limpa para exigir nova seleção explícita
        assert db.get_remote_sync_folder() is None
        # Novo e-mail registrado
        assert db.get_pair_linked_account_email() == "conta2@gmail.com"
        assert db.is_voluntary_disconnect() is False
    finally:
        win.close()


def test_6_i18n_catalog_parity_for_v0124_keys(tmp_path: Path, qapp: QApplication) -> None:
    new_keys = [
        "folders_btn_remove_pair",
        "folders_remove_pair_confirm_title",
        "folders_remove_pair_confirm_message",
        "folder_status_waiting_account",
        "folders_status_waiting_connection",
        "hero_title_no_account",
        "hero_subtitle_no_account",
        "hero_btn_connect_account_action",
        "tray_status_header_no_account",
        "tray_tooltip_no_account",
        "folders_diff_account_notice",
        "folders_remote_blocked_no_account",
        "sync_blocked_no_account",
        "folders_pair_removed_feedback",
    ]

    for key in new_keys:
        assert key in MESSAGES["pt_BR"], f"Chave {key} ausente em pt_BR"
        assert key in MESSAGES["en"], f"Chave {key} ausente em en"
        assert len(MESSAGES["pt_BR"][key]) > 0
        assert len(MESSAGES["en"][key]) > 0

    # Valida alternância em tempo de execução
    db = BrisaDatabase(db_path=tmp_path / "test_i18n.db")
    db.set_local_sync_folder(str(tmp_path / "loc"))
    db.set_remote_sync_folder(folder_id="f_id", folder_name="Docs")
    db.set_voluntary_disconnect(True)

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win.show()
    qapp.processEvents()

    try:
        set_current_language("pt_BR")
        win.retranslate_ui()
        assert win.folders_remove_pair_btn.text() == "Remover vínculo de sincronização"
        assert win.hero_title_label.text() == "Nenhuma conta conectada"
        assert win.hero_sync_now_btn.text() == "Conectar conta"

        set_current_language("en")
        win.retranslate_ui()
        assert win.folders_remove_pair_btn.text() == "Remove sync link"
        assert win.hero_title_label.text() == "No account connected"
        assert win.hero_sync_now_btn.text() == "Connect account"

        set_current_language("pt_BR")
        win.retranslate_ui()
        assert win.folders_remove_pair_btn.text() == "Remover vínculo de sincronização"
        assert win.hero_title_label.text() == "Nenhuma conta conectada"
        assert win.hero_sync_now_btn.text() == "Conectar conta"
    finally:
        win.close()

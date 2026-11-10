"""Testes automatizados da revisão corretiva do BrisaSync v0.1.26.

Cobre:
1. Clique real em Ajuda na Visão Geral e Barra Lateral (sem método show_diagnostics_dialog inexistente).
2. Contador dinâmico de pastas (0 de 0, 0 de 1, 1 de 1), proteção de Salvar e Validar Pasta sem conta e conferência unificada.
3. Bandeja: recálculo e reabilitação de "Sincronizar agora" e "Pausar/Retomar" após ciclo desconectar -> reconectar.
4. Reconexão segura: bloqueio de agendamento no início do OAuth, rejeição de autoativação com conta anterior desconhecida
   e validação de destino remoto por ID (com fallback seguro para destino inacessível).
5. Paridade do catálogo de internacionalização.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from brisasync.credentials.store import OAuthCredentials
from brisasync.i18n import get_current_language, set_current_language, tr
from brisasync.i18n.catalog import MESSAGES
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_VAULT_LOCKED,
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_SYNCING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.tray import (
    TRAY_STATE_ATTENTION,
    TRAY_STATE_HEALTHY,
    TRAY_STATE_PAUSED,
    TRAY_STATE_SYNCING,
    BrisaTrayController,
)


@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication(["brisasync-test"])
    yield app


def make_snapshot(
    state: str = STATE_WAITING,
    state_label: str = "AGUARDANDO",
    service_pid: int = 1234,
    detail_message: str = "",
    is_cycle_active: bool = False,
    active_rclone_pid: int | None = None,
    pending_sync_coalesced: bool = False,
    auto_sync_paused: bool = False,
    sync_interval_seconds: int = 300,
    next_scheduled_sync_at: float | None = None,
    backoff_attempt: int = 0,
    backoff_seconds: int = 0,
    last_confirmed_sync_at: float | None = None,
    last_run_status: str | None = None,
    last_error_reason: str | None = None,
    autostart_enabled: bool = False,
    configured_pair_ready: bool = True,
    attention_category: str | None = None,
    attention_title: str | None = None,
    attention_explanation: str | None = None,
) -> ServiceStatusSnapshot:
    return ServiceStatusSnapshot(
        service_pid=service_pid,
        state=state,
        state_label=state_label,
        detail_message=detail_message,
        is_cycle_active=is_cycle_active,
        active_rclone_pid=active_rclone_pid,
        pending_sync_coalesced=pending_sync_coalesced,
        auto_sync_paused=auto_sync_paused,
        sync_interval_seconds=sync_interval_seconds,
        next_scheduled_sync_at=next_scheduled_sync_at,
        backoff_attempt=backoff_attempt,
        backoff_seconds=backoff_seconds,
        last_confirmed_sync_at=last_confirmed_sync_at,
        last_run_status=last_run_status,
        last_error_reason=last_error_reason,
        autostart_enabled=autostart_enabled,
        configured_pair_ready=configured_pair_ready,
        attention_category=attention_category,
        attention_title=attention_title,
        attention_explanation=attention_explanation,
    )


@pytest.fixture(autouse=True)
def reset_language():
    orig = get_current_language()
    set_current_language("pt_BR")
    yield
    set_current_language(orig)


def test_1_overview_help_click_and_sidebar_without_account(tmp_path: Path, qapp: QApplication) -> None:
    """Verifica se os atalhos de Ajuda funcionam sem exceção e preservam outras ações."""
    db = BrisaDatabase(db_path=tmp_path / "test_help.db")
    db.set_voluntary_disconnect(True)

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win.show()
    qapp.processEvents()

    try:
        # Sem conta: hero banner está no estado unconfigured
        assert win.hero_banner.property("heroState") == "unconfigured"
        assert win.hero_pause_btn.text() == tr("hero_btn_help")

        # Mock do método de abertura de diagnóstico para verificar que ambos os atalhos o invocam
        diag_mock = MagicMock()
        win._open_diagnostics_dialog = diag_mock

        # 1. Clique real no botão de Ajuda da Visão Geral (Hero pause toggle)
        win.hero_pause_btn.click()
        diag_mock.assert_called_once()

        # 2. Clique real no botão de Ajuda da Barra Lateral
        diag_mock.reset_mock()
        win.sidebar_diag_btn.click()
        diag_mock.assert_called_once()

        # 3. Preservação de ações nos demais estados operacionais
        # 3a. Cofre bloqueado
        diag_mock.reset_mock()
        unlock_mock = MagicMock()
        win._on_unlock_vault_clicked = unlock_mock
        snap_locked = make_snapshot(
            state=STATE_ATTENTION_REQUIRED,
            attention_category=ATTENTION_VAULT_LOCKED,
            detail_message="Keyring locked",
        )
        win._last_snapshot = snap_locked
        win._on_hero_pause_toggle()
        unlock_mock.assert_called_once()

        # 3b. Atenção técnica
        win._last_snapshot = None
        win.hero_banner.setProperty("heroState", "attention")
        attention_mock = MagicMock()
        win._show_attention_details_dialog = attention_mock
        snap_att = make_snapshot(
            state=STATE_ATTENTION_REQUIRED,
            attention_category="PERSISTENT_FAILURE",
            detail_message="Falha persistente",
        )
        win._last_snapshot = snap_att
        win._on_hero_pause_toggle()
        attention_mock.assert_called_once()

        # 3c. Pausado
        win._last_snapshot = None
        win.hero_banner.setProperty("heroState", "paused")
        resume_mock = MagicMock()
        win._on_resume_sync_clicked = resume_mock
        snap_paused = make_snapshot(
            state=STATE_PAUSED,
            auto_sync_paused=True,
        )
        win._last_snapshot = snap_paused
        win._on_hero_pause_toggle()
        resume_mock.assert_called_once()

        # 3d. Operando / Saudável
        win.hero_banner.setProperty("heroState", "healthy")
        pause_mock = MagicMock()
        win._on_pause_sync_clicked = pause_mock
        snap_healthy = make_snapshot(
            state=STATE_WAITING,
            auto_sync_paused=False,
        )
        win._last_snapshot = snap_healthy
        win._on_hero_pause_toggle()
        pause_mock.assert_called_once()
    finally:
        try:
            win.credential_store.delete_credentials()
        except Exception:
            pass
        win.close()


def test_2_folder_counter_and_folders_page_guards(tmp_path: Path, qapp: QApplication) -> None:
    """Verifica o contador calculado (0 de 0, 0 de 1, 1 de 1), bloqueio de Salvar e Validar Pasta sem conta e conferência."""
    db = BrisaDatabase(db_path=tmp_path / "test_counter.db")

    # 1. Sem par configurado inicialmente
    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win.show()
    qapp.processEvents()

    try:
        # Transição A: Sem par configurado -> 0 de 0
        assert win.hero_metric_folders_val.text() == "0 de 0"
        assert not win.sidebar_folders_badge.isVisible()
        assert not win.save_folder_button.isEnabled()
        assert win.save_folder_button.toolTip() == tr("sync_blocked_no_account")

        # Tentar salvar pasta sem conta utilizável deve ser bloqueado
        local_dir = tmp_path / "local_pasta"
        local_dir.mkdir(parents=True, exist_ok=True)
        win.folder_input.setText(str(local_dir))
        result = win.save_and_validate_folder()
        assert result is False
        assert "[ERRO]" in win.folder_feedback_label.text()
        assert db.get_local_sync_folder() is None

        # 2. Configura um par salvo no banco, mas sem conta conectada
        db.set_local_sync_folder(str(local_dir))
        db.set_remote_sync_folder(folder_id="drive_folder_1", folder_name="PastaDrive")
        win._update_home_view()
        qapp.processEvents()

        # Transição B: Com par salvo e sem conta conectada -> 0 de 1
        assert win.hero_metric_folders_val.text() == "0 de 1"
        assert not win.sidebar_folders_badge.isVisible()

        # Botões de pastas: ações locais habilitadas, ações remotas e salvar desabilitadas
        assert win.folders_page_open_btn.isEnabled()
        assert win.folders_remove_pair_btn.isEnabled()
        assert not win.folders_page_sync_btn.isEnabled()
        assert not win.save_folder_button.isEnabled()
        assert not win.folders_connect_account_btn.isHidden()
        assert win.folders_connect_account_btn.isEnabled()

        # Conferência pré-execução indica [AGUARDANDO CONEXÃO] mesmo sem flag de desconexão voluntária
        assert db.is_voluntary_disconnect() is False
        win._update_sync_target_preview()
        assert "[AGUARDANDO CONEXÃO]" in win.sync_target_preview_label.text()

        # 3. Simula conta conectada e utilizável
        mock_creds = OAuthCredentials(
            client_id="cid",
            client_secret="csec",
            access_token="tok_valid",
            refresh_token="ref_valid",
            token_type="Bearer",
            expiry="2028-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="usuario@gmail.com",
        )
        win.credential_store.store_credentials(mock_creds)
        win._has_usable_account = lambda: True

        win._update_home_view()
        win._update_sync_target_preview()
        qapp.processEvents()

        # Transição C: Com par configurado e conta conectada utilizável -> 1 de 1
        assert win.hero_metric_folders_val.text() == "1 de 1"
        assert win.sidebar_folders_badge.isVisible()
        assert win.folders_page_sync_btn.isEnabled()
        assert win.save_folder_button.isEnabled()
        assert "[PRONTO]" in win.sync_target_preview_label.text()

        # Teste de idioma inglês
        set_current_language("en")
        win.retranslate_ui()
        qapp.processEvents()
        assert win.hero_metric_folders_val.text() == "1 of 1"
    finally:
        try:
            win.credential_store.delete_credentials()
        except Exception:
            pass
        win.close()


def test_3_tray_action_recalculation_after_disconnect_and_reconnect(tmp_path: Path, qapp: QApplication) -> None:
    """Verifica se as ações da bandeja são recalculadas dinamicamente após desconexão e reconexão."""
    db = BrisaDatabase(db_path=tmp_path / "test_tray_cycle.db")
    local_dir = tmp_path / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="rem_123", folder_name="DriveFolder")
    db.set_pair_linked_account_email("test@gmail.com")

    tray = BrisaTrayController(database=db, force_tray_available=True)
    tray.has_account_connected = lambda: True

    # 1. Estado inicial ativo e pronto
    snap_ready = make_snapshot(
        state=STATE_WAITING,
        configured_pair_ready=True,
        auto_sync_paused=False,
        is_cycle_active=False,
    )
    tray.update_from_snapshot(snap_ready)
    assert tray.sync_now_action.isEnabled() is True
    assert tray.pause_resume_action.isEnabled() is True
    assert tray._current_state == TRAY_STATE_HEALTHY

    # 2. Desconexão voluntária
    db.set_voluntary_disconnect(True)
    tray.has_account_connected = lambda: False
    tray.update_from_snapshot(None)

    assert tray.sync_now_action.isEnabled() is False
    assert tray.pause_resume_action.isEnabled() is False
    assert tray._current_state == TRAY_STATE_HEALTHY
    assert "Nenhuma conta conectada" in tray.tooltip_text

    # Mesmo que chegue um snapshot defasado do daemon com erro, prioriza desconexão voluntária
    snap_stale = make_snapshot(
        state=STATE_ATTENTION_REQUIRED,
        attention_category=ATTENTION_AUTH_EXPIRED,
        detail_message="Nenhuma conta conectada",
    )
    tray.update_from_snapshot(snap_stale)
    assert tray._current_state == TRAY_STATE_HEALTHY
    assert tray.sync_now_action.isEnabled() is False

    # 3. Reconexão: conta reestabelecida e novo snapshot com par pronto
    db.set_voluntary_disconnect(False)
    tray.has_account_connected = lambda: True

    snap_reconnected = make_snapshot(
        state=STATE_WAITING,
        configured_pair_ready=True,
        auto_sync_paused=False,
        is_cycle_active=False,
    )
    tray.update_from_snapshot(snap_reconnected)

    # Ações devem estar reabilitadas imediatamente!
    assert tray.sync_now_action.isEnabled() is True
    assert tray.pause_resume_action.isEnabled() is True
    assert tray._current_state == TRAY_STATE_HEALTHY


def test_4_reconnection_unknown_previous_identity_keeps_pair_inactive(tmp_path: Path, qapp: QApplication) -> None:
    """Verifica se a reconexão quando prev_email é desconhecido mantém o par inativo até escolha explícita."""
    db = BrisaDatabase(db_path=tmp_path / "test_unknown_prev.db")
    local_dir = tmp_path / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="old_remote_id", folder_name="Remoto Antigo")
    db.mark_baseline_initialized(local_folder=str(local_dir), remote_folder_id="old_remote_id")
    # Identidade anterior desconhecida (None)
    db.set_pair_linked_account_email(None)
    db.set_voluntary_disconnect(True)

    mock_ipc = MagicMock()
    win = BrisaMainWindow(database=db, ipc_client=mock_ipc, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win._on_list_remote_folders = MagicMock()
    win.show()
    qapp.processEvents()

    try:
        new_creds = OAuthCredentials(
            client_id="cid",
            client_secret="csec",
            access_token="tok_new",
            refresh_token="ref_new",
            token_type="Bearer",
            expiry="2028-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="nova_conta@gmail.com",
        )
        win._on_oauth_succeeded(new_creds)
        qapp.processEvents()

        # Baseline anterior invalidada por segurança
        assert db.is_baseline_initialized(local_folder=str(local_dir), remote_folder_id="old_remote_id") is False
        # Pasta remota limpa para exigir seleção explícita
        assert db.get_remote_sync_folder() is None
        # Novo e-mail registrado
        assert db.get_pair_linked_account_email() == "nova_conta@gmail.com"
        # NÃO deve ter disparado account_connected ao daemon
        for call in mock_ipc.execute_command.call_args_list:
            assert call.args[0] != "account_connected"
        # Deve ter aberto a listagem para seleção explícita
        win._on_list_remote_folders.assert_called_once()
    finally:
        try:
            win.credential_store.delete_credentials()
        except Exception:
            pass
        win.close()


def test_5_reconnection_inaccessible_remote_destination_by_id(tmp_path: Path, qapp: QApplication) -> None:
    """Verifica se ao reconectar com a mesma conta, destino remoto inacessível/removido mantém o par inativo."""
    db = BrisaDatabase(db_path=tmp_path / "test_inaccessible.db")
    local_dir = tmp_path / "local"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="deleted_folder_id", folder_name="Pasta Deletada")
    db.mark_baseline_initialized(local_folder=str(local_dir), remote_folder_id="deleted_folder_id")
    db.set_pair_linked_account_email("mesma_conta@gmail.com")
    db.set_voluntary_disconnect(True)

    mock_ipc = MagicMock()
    win = BrisaMainWindow(database=db, ipc_client=mock_ipc, enable_tray=False, allow_notify_send=False)
    win._suppress_dialogs_for_testing = True
    win._on_list_remote_folders = MagicMock()
    # Simula validação remota falhando (pasta excluída ou 404 no Drive)
    win._remote_folder_id_validator = lambda fid: False
    win.show()
    qapp.processEvents()

    try:
        creds = OAuthCredentials(
            client_id="cid",
            client_secret="csec",
            access_token="tok_ok",
            refresh_token="ref_ok",
            token_type="Bearer",
            expiry="2028-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="mesma_conta@gmail.com",
        )
        win._on_oauth_succeeded(creds)
        qapp.processEvents()

        # Destino inacessível: baseline invalidada e pasta remota limpa
        assert db.is_baseline_initialized(local_folder=str(local_dir), remote_folder_id="deleted_folder_id") is False
        assert db.get_remote_sync_folder() is None
        # daemon NÃO notificado de account_connected
        for call in mock_ipc.execute_command.call_args_list:
            assert call.args[0] != "account_connected"
        win._on_list_remote_folders.assert_called_once()
    finally:
        try:
            win.credential_store.delete_credentials()
        except Exception:
            pass
        win.close()


def test_6_catalog_parity_and_new_keys_presence() -> None:
    """Confere paridade integral e presença das novas chaves da v0.1.26."""
    pt_keys = set(MESSAGES["pt_BR"].keys())
    en_keys = set(MESSAGES["en"].keys())
    assert pt_keys == en_keys, f"Diferença entre catálogos: {pt_keys ^ en_keys}"

    new_keys = [
        "hero_stat_folders_ratio",
        "folders_unknown_prev_account_notice",
        "folders_remote_inaccessible_notice",
    ]
    for key in new_keys:
        assert key in pt_keys, f"Chave {key} ausente em pt_BR"
        assert key in en_keys, f"Chave {key} ausente em en"

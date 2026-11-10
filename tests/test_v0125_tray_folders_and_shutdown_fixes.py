"""Testes de validação dos requisitos da v0.1.25 do BrisaSync:
1. Bandeja sem conta (ícone neutro, status e tooltip em PT e EN, snapshot antigo ignorado, start-hidden, preservação de alertas reais).
2. Pastas (sem par: "Nenhum par configurado" e botões ocultos; sem conta: "Conectar conta" e ações do Drive desabilitadas; com par salvo: "Aguardando conexão" com ações locais e remoção disponíveis).
3. Diálogo de saída ("Quit completely", botões ajustados ao texto, quebra de linha em descrições, ~540px e escalonamento).
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync import __app_name__
from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.i18n import get_current_language, set_current_language, tr
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_VAULT_LOCKED,
    STATE_ATTENTION_REQUIRED,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.icons import (
    TRAY_STATE_ATTENTION,
    TRAY_STATE_HEALTHY,
)
from brisasync.ui.main_window import BrisaExitDialog, BrisaMainWindow
from brisasync.ui.tray import BrisaTrayController


@pytest.fixture(autouse=True)
def qapp():
    app = QApplication.instance() or QApplication(["brisasync-test"])
    yield app


class DummyCredentialStore:
    def __init__(self, creds: OAuthCredentials | None = None, is_locked: bool = False):
        self._creds = creds
        self._is_locked = is_locked

    def is_vault_locked(self) -> bool:
        return self._is_locked

    def load_credentials(self, *, interactive: bool = False) -> OAuthCredentials | None:
        if self._is_locked:
            return None
        return self._creds

    def delete_credentials(self) -> None:
        self._creds = None


# =========================================================================
# REQUISITO 1: BANDEJA SEM CONTA
# =========================================================================

def test_tray_no_account_clean_initialization(tmp_path):
    """Inicialização sem conta configurada deve apresentar ícone neutro e tooltip 'Nenhuma conta conectada'."""
    db_path = tmp_path / "tray_clean.db"
    db = BrisaDatabase(db_path=db_path)
    store = DummyCredentialStore(creds=None, is_locked=False)

    set_current_language("pt_BR")
    tray = BrisaTrayController(
        database=db,
        credential_store=store,
        enable_tray=True,
        force_tray_available=True,
    )

    assert tray._current_state == TRAY_STATE_HEALTHY
    assert tray.status_header_action.text() == "Nenhuma conta conectada"
    assert tray.tooltip_text == f"{__app_name__} — Nenhuma conta conectada"
    assert not tray.sync_now_action.isEnabled()
    assert not tray.pause_resume_action.isEnabled()

    # Alternar para inglês
    set_current_language("en")
    tray.retranslate_tray()
    assert tray._current_state == TRAY_STATE_HEALTHY
    assert tray.status_header_action.text() == "No account connected"
    assert tray.tooltip_text == f"{__app_name__} — No account connected"
    assert not tray.sync_now_action.isEnabled()


def test_tray_no_account_ignores_stale_daemon_attention_snapshot(tmp_path):
    """Reproduz o triângulo amarelo antigo: quando não há conta, snapshots stale com ATTENTION_REQUIRED devem ser ignorados."""
    db_path = tmp_path / "tray_stale.db"
    db = BrisaDatabase(db_path=db_path)
    db.set_local_sync_folder(str(tmp_path / "local"))
    db.set_remote_sync_folder(folder_id="root_id", folder_name="RemoteFolder")
    store = DummyCredentialStore(creds=None, is_locked=False)

    set_current_language("en")
    tray = BrisaTrayController(
        database=db,
        credential_store=store,
        enable_tray=True,
        force_tray_available=True,
    )

    # Simula snapshot stale antigo do daemon reportando ATTENTION_REQUIRED por falta de conta
    stale_snapshot = ServiceStatusSnapshot(
        service_pid=12345,
        state=STATE_ATTENTION_REQUIRED,
        state_label="ATTENTION REQUIRED",
        detail_message="Nenhuma conta Google conectada no cofre da sessão. Conecte a conta pela janela do BrisaSync.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=None,
        last_run_status=None,
        last_error_reason="Nenhuma conta Google conectada no cofre da sessão.",
        autostart_enabled=True,
        configured_pair_ready=False,
        attention_category="AUTH_EXPIRED",
        attention_title="Autenticação Exige Atenção",
        attention_explanation="A autorização da conta expirou ou foi revogada.",
        conflict_files_count=0,
    )

    tray.update_from_snapshot(stale_snapshot)

    # O ícone DEVE permanecer neutro (HEALTHY) e NÃO exibir triângulo de atenção
    assert tray._current_state == TRAY_STATE_HEALTHY
    assert tray.status_header_action.text() == "No account connected"
    assert tray.tooltip_text == f"{__app_name__} — No account connected"
    assert not tray.sync_now_action.isEnabled()


def test_tray_preserves_legitimate_alerts(tmp_path):
    """Preserva alerta para cofre bloqueado e autorização realmente expirada quando há conta."""
    db_path = tmp_path / "tray_alerts.db"
    db = BrisaDatabase(db_path=db_path)

    # 1. Cofre bloqueado
    locked_store = DummyCredentialStore(creds=None, is_locked=True)
    set_current_language("en")
    tray_locked = BrisaTrayController(
        database=db,
        credential_store=locked_store,
        enable_tray=True,
        force_tray_available=True,
    )
    tray_locked.update_from_snapshot(None)
    assert tray_locked._current_state == TRAY_STATE_ATTENTION
    assert "[ATTENTION REQUIRED]" in tray_locked.tooltip_text
    assert "locked" in tray_locked.tooltip_text.lower()

    # 2. Autorização expirada / revogada com conta presente
    valid_creds = OAuthCredentials(
        account_email="user@example.com",
        access_token="valid_access",
        refresh_token="valid_refresh",
        token_type="Bearer",
        scope="https://www.googleapis.com/auth/drive",
        client_id="cid",
        client_secret="sec",
        expiry="2030-01-01T00:00:00Z",
    )
    unlocked_store = DummyCredentialStore(creds=valid_creds, is_locked=False)
    tray_auth = BrisaTrayController(
        database=db,
        credential_store=unlocked_store,
        enable_tray=True,
        force_tray_available=True,
    )

    auth_snapshot = ServiceStatusSnapshot(
        service_pid=12345,
        state=STATE_ATTENTION_REQUIRED,
        state_label="ATTENTION REQUIRED",
        detail_message="Token has been expired or revoked",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=None,
        last_run_status="ATTENTION_REQUIRED",
        last_error_reason="invalid_grant",
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category=ATTENTION_AUTH_EXPIRED,
        attention_title="Authentication Requires Attention",
        attention_explanation="Account authorization expired or revoked.",
        conflict_files_count=0,
    )
    tray_auth.update_from_snapshot(auth_snapshot)
    assert tray_auth._current_state == TRAY_STATE_ATTENTION
    assert "[ATTENTION REQUIRED]" in tray_auth.tooltip_text
    assert "expired or revoked" in tray_auth.tooltip_text.lower()


# =========================================================================
# REQUISITO 2: PASTAS (SEM PAR E SEM CONTA)
# =========================================================================

def test_folders_page_without_pair(tmp_path):
    """Sem par configurado, mostra 'Nenhum par configurado' e oculta 'Abrir Pasta Local' e 'Remover vínculo'."""
    db_path = tmp_path / "folders_no_pair.db"
    db = BrisaDatabase(db_path=db_path)
    store = DummyCredentialStore(creds=None, is_locked=False)

    ipc_client = MagicMock()
    ipc_client.get_status.return_value = None

    set_current_language("pt_BR")
    win = BrisaMainWindow(
        database=db,
        credential_store=store,
        ipc_client=ipc_client,
        enable_tray=False,
    )
    win.show()

    # 1. Sem par e sem conta
    assert win.folders_card_title_label.text() == "Nenhum par configurado"
    assert win.folders_page_open_btn.isHidden()
    assert win.folders_remove_pair_btn.isHidden()
    assert win.folders_page_sync_btn.isHidden()

    # Oferece 'Conectar conta'
    assert not win.folders_connect_account_btn.isHidden()
    assert win.folders_connect_account_btn.isEnabled()
    assert win.folders_connect_account_btn.text() == "Conectar conta"

    # Ações do Drive desabilitadas
    assert not win.list_remote_folders_button.isEnabled()
    assert not win.create_remote_folder_button.isEnabled()
    assert not win.remote_folder_combo.isEnabled()

    # Teste em inglês
    set_current_language("en")
    win.retranslate_ui()
    assert win.folders_card_title_label.text() == "No pair configured"
    assert win.folders_connect_account_btn.text() == "Connect account"


def test_folders_page_with_pair_and_no_account(tmp_path):
    """Com par salvo e sem conta, mostra 'Aguardando conexão' e mantém disponíveis 'Abrir pasta local' e 'Remover vínculo'."""
    db_path = tmp_path / "folders_with_pair.db"
    db = BrisaDatabase(db_path=db_path)
    local_p = tmp_path / "BrisaSyncLocal"
    local_p.mkdir()
    db.set_local_sync_folder(str(local_p))
    db.set_remote_sync_folder(folder_id="drive_folder_123", folder_name="MeusArquivos")

    store = DummyCredentialStore(creds=None, is_locked=False)

    ipc_client = MagicMock()
    ipc_client.get_status.return_value = None

    set_current_language("pt_BR")
    win = BrisaMainWindow(
        database=db,
        credential_store=store,
        ipc_client=ipc_client,
        enable_tray=False,
    )
    win.show()

    assert win.folders_card_title_label.text() == "MeusArquivos"
    assert "Aguardando conexão" in win.folders_card_status_pill.text()
    assert "Aguardando conexão" in win.overview_folder_status_pill.text()

    # Mantém disponíveis as ações locais
    assert not win.folders_page_open_btn.isHidden()
    assert win.folders_page_open_btn.isEnabled()
    assert not win.folders_remove_pair_btn.isHidden()
    assert win.folders_remove_pair_btn.isEnabled()

    # Oferece 'Conectar conta'
    assert not win.folders_connect_account_btn.isHidden()
    assert win.folders_connect_account_btn.isEnabled()

    # Ações remotas desabilitadas
    assert not win.folders_page_sync_btn.isEnabled()
    assert not win.list_remote_folders_button.isEnabled()
    assert not win.create_remote_folder_button.isEnabled()
    assert not win.remote_folder_combo.isEnabled()

    # Teste em inglês
    set_current_language("en")
    win.retranslate_ui()
    assert "Waiting for connection" in win.folders_card_status_pill.text()
    assert "Waiting for connection" in win.overview_folder_status_pill.text()
    assert win.folders_connect_account_btn.text() == "Connect account"


# =========================================================================
# REQUISITO 3: DIÁLOGO DE SAÍDA
# =========================================================================

def test_exit_dialog_shortened_text_and_dynamic_widths(tmp_path):
    """Valida texto encurtado 'Quit completely', largura adaptada ao texto e quebra de linha."""
    db_path = tmp_path / "exit_dlg.db"
    db = BrisaDatabase(db_path=db_path)
    store = DummyCredentialStore(creds=None, is_locked=False)
    ipc_client = MagicMock()

    win = BrisaMainWindow(
        database=db,
        credential_store=store,
        ipc_client=ipc_client,
        enable_tray=False,
    )

    # 1. Teste em Inglês
    set_current_language("en")
    dlg_en = BrisaExitDialog(main_window=win)
    assert dlg_en.btn_shutdown.text() == "Quit completely"
    assert dlg_en.btn_keep.text() == "Keep syncing"

    # Os botões devem ter largura proporcional ao texto (font metrics) e não rígida em 175 px
    w_en = dlg_en.btn_shutdown.width()
    fm_en = dlg_en.btn_shutdown.fontMetrics()
    expected_min_en = max(
        fm_en.horizontalAdvance(dlg_en.btn_keep.text()),
        fm_en.horizontalAdvance(dlg_en.btn_shutdown.text()),
    )
    assert w_en >= expected_min_en
    assert w_en < 170  # Em inglês, os textos são curtos e a largura é substancialmente menor que 175

    # 2. Teste em Português
    set_current_language("pt_BR")
    dlg_pt = BrisaExitDialog(main_window=win)
    assert dlg_pt.btn_shutdown.text() == "Encerrar tudo"
    assert dlg_pt.btn_keep.text() == "Manter sincronização"

    w_pt = dlg_pt.btn_shutdown.width()
    fm_pt = dlg_pt.btn_shutdown.fontMetrics()
    expected_min_pt = max(
        fm_pt.horizontalAdvance(dlg_pt.btn_keep.text()),
        fm_pt.horizontalAdvance(dlg_pt.btn_shutdown.text()),
    )
    assert w_pt >= expected_min_pt

    # Valida que as descrições possuem quebra de linha (setWordWrap == True)
    # Procuramos labels de descrição nos layouts do diálogo
    labels = dlg_pt.findChildren(type(dlg_pt.btn_keep.parent().layout().itemAt(0).layout().itemAt(1).widget()))
    desc_labels = [lbl for lbl in labels if lbl.wordWrap()]
    assert len(desc_labels) >= 2  # lbl_keep e lbl_shutdown

    # Diálogo acomoda 540 px
    assert dlg_pt.minimumWidth() <= 540

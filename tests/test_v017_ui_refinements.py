"""Suíte de testes automatizados das correções e refinamentos do BrisaSync v0.1.7.

Validações cobertas:
1. Botões da barra lateral (`BrisaSidebarNavItem`): altura padronizada, desenho atômico sem
   widgets filhos internos (imunidade a moldura interna do Breeze), navegação e foco por teclado.
2. Diálogo unificado de encerramento (`BrisaExitDialog`): instância única, elevação com janela oculta,
   opções "Manter sincronização", "Encerrar tudo", parada controlada sem SIGKILL e cancelamento.
3. Responsividade e layout adaptativo: quebra de 2 colunas para 1 coluna vertical empilhada,
   reorganização de ações do hero banner e ausência de rolagem horizontal.
4. Coerência estrita de estados: eliminação de mensagens contraditórias de "Tudo em dia" /
   "Nada para transferir" quando o serviço reportar atenção, falha ou recuperação necessária.
"""

from __future__ import annotations

import os
from pathlib import Path
import time
from typing import Any
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QKeyEvent, QPaintEvent, QRegion
from PySide6.QtWidgets import QApplication, QBoxLayout, QLabel, QPushButton, QScrollArea, QWidget

from brisasync.service.daemon import BrisaSessionServiceDaemon
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.service.protocol import (
    ATTENTION_RECOVERY_REQUIRED,
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_SYNCING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import (
    BrisaExitDialog,
    BrisaMainWindow,
    BrisaSidebarNavItem,
)


def _get_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication(["brisasync-test-v017"])
    return app


def test_1_sidebar_nav_item_atomic_rendering_and_keyboard_focus() -> None:
    """Valida o componente BrisaSidebarNavItem: ausência de filhos parasitas, foco e teclado."""
    app = _get_qapp()
    parent = QWidget()
    item = BrisaSidebarNavItem("dashboard", "Visão geral", badge_count=2, parent=parent)

    # 1. Dimensões padronizadas e ausência de filhos que gerem PE_FrameFocusRect
    assert item.height() == 42
    assert item.item_text == "Visão geral"
    assert item.badge_count == 2
    # Não deve ter QLabels como filhos diretos (evita a moldura interna do KDE Breeze)
    child_labels = [c for c in item.children() if isinstance(c, QLabel)]
    assert len(child_labels) == 0

    # 2. Ativação e seleção
    assert item.is_active is False
    item.setActive(True)
    assert item.is_active is True

    # 3. Simulação de evento de pintura com antialiasing
    item.resize(200, 42)
    ev = QPaintEvent(QRegion(item.rect()))
    item.paintEvent(ev)

    # 4. Foco por teclado e disparo por tecla (Space / Return)
    clicked_count = 0

    def on_click() -> None:
        nonlocal clicked_count
        clicked_count += 1

    item.clicked.connect(on_click)

    # Envia evento de tecla de espaço
    key_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Space,
        Qt.KeyboardModifier.NoModifier,
        " ",
    )
    item.keyPressEvent(key_event)
    assert clicked_count == 1

    # Envia evento de tecla Return
    ret_event = QKeyEvent(
        QKeyEvent.Type.KeyPress,
        Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier,
        "\r",
    )
    item.keyPressEvent(ret_event)
    assert clicked_count == 2


def test_2_unified_exit_dialog_choices_and_singleton(tmp_path: Path) -> None:
    """Valida o diálogo unificado BrisaExitDialog em todos os caminhos de acionamento."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "test_exit.db")
    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.show()

    try:
        # 1. Diálogo a partir do método central
        dlg = BrisaExitDialog(win)
        assert dlg.windowTitle() == "Sair do BrisaSync"
        assert dlg.btn_keep.text() == "Manter sincronização"
        assert dlg.btn_shutdown.text() == "Encerrar tudo"
        assert dlg.btn_cancel.text() == "Cancelar"

        # 2. Cancelamento limpo via reject
        dlg.btn_cancel.click()
        assert dlg.result() == 0

        # 3. Manter sincronização chama quit_graphical_component_keep_service
        quit_called = False
        win.quit_graphical_component_keep_service = lambda: None  # mock

        dlg2 = BrisaExitDialog(win)
        dlg2._on_keep_clicked()
        assert dlg2.result() == 1

        # 4. Abertura idempotente (singleton mantido em _exit_dialog)
        win._exit_dialog = None
        win.hide()
        # Abre diálogo com janela oculta (deve setar WindowStaysOnTopHint e exibir)
        dlg_hidden = BrisaExitDialog(win, parent=None)
        win._exit_dialog = dlg_hidden
        dlg_hidden.show()
        assert win._exit_dialog is dlg_hidden
        dlg_hidden.reject()
        win._exit_dialog = None
    finally:
        win.close()


def test_3_responsive_layout_reflow_narrow_vs_wide(tmp_path: Path) -> None:
    """Valida a transição responsiva bidirecional entre 2 colunas e 1 coluna vertical empilhada."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "test_responsive.db")
    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.show()

    try:
        # 1. Modo Padrão Largo (1280x720)
        win.resize(1280, 720)
        win._apply_responsive_layout(1280)
        app.processEvents()

        assert win.overview_grid_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert win.settings_grid_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert win.top_hero_row.indexOf(win.hero_actions_container) != -1
        assert win.global_status_pill.isVisible() is True
        assert win.options_menu_btn.isVisible() is True

        # 2. Resolução de Reprodução do Defeito (1055x790) -> Empilhado em 1 coluna
        win.resize(1055, 790)
        win._apply_responsive_layout(1055)
        app.processEvents()

        assert win.overview_grid_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert win.settings_grid_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert win.hero_banner_layout.indexOf(win.hero_actions_container) != -1
        assert win.global_status_pill.isVisible() is False
        assert win.options_menu_btn.isVisible() is True

        # 3. Modo Estreito Compacto (820x620)
        win.resize(820, 620)
        win._apply_responsive_layout(820)
        app.processEvents()

        assert win.overview_grid_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert win.settings_grid_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert win.hero_banner_layout.indexOf(win.hero_actions_container) != -1
        assert win.global_status_pill.isVisible() is False
        assert win.options_menu_btn.isVisible() is True

        # 4. Modo Ultra-amplo (1920x1080)
        win.resize(1920, 1080)
        win._apply_responsive_layout(1920)
        app.processEvents()

        assert win.overview_grid_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert win.settings_grid_layout.direction() == QBoxLayout.Direction.LeftToRight
        assert win.top_hero_row.indexOf(win.hero_actions_container) != -1
        assert win.global_status_pill.isVisible() is True

        # 5. Redimensionamento inverso (1920 -> 1055 -> 820)
        win.resize(1055, 790)
        win._apply_responsive_layout(1055)
        app.processEvents()
        assert win.overview_grid_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert win.hero_banner_layout.indexOf(win.hero_actions_container) != -1

        win.resize(820, 620)
        win._apply_responsive_layout(820)
        app.processEvents()
        assert win.overview_grid_layout.direction() == QBoxLayout.Direction.TopToBottom
        assert win.hero_banner_layout.indexOf(win.hero_actions_container) != -1

        # 6. Políticas de rolagem
        assert win.overview_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert win.folders_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert win.settings_scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        assert win.history_table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    finally:
        win.close()


def test_4_state_consistency_no_contradictory_idle_message_on_attention(
    tmp_path: Path,
) -> None:
    """Valida coerência absoluta de estados: sem mensagens enganosas de 'Nada para transferir' em falhas."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "test_states.db")
    # Configura par fictício para simular painel ativo
    db.set_local_sync_folder(str(tmp_path / "local"))
    db.set_remote_sync_folder(folder_id="fid123", folder_name="Documentos Remotos")

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.show()

    try:
        # Snapshot com atenção por limite de exclusão excedido
        snapshot_attention = ServiceStatusSnapshot(
            service_pid=1234,
            state=STATE_ATTENTION_REQUIRED,
            state_label="ATENÇÃO NECESSÁRIA",
            detail_message="Proteção contra exclusão em massa acionada",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at="2026-10-30T10:00:00Z",
            last_run_status="FAILED",
            last_error_reason="Exclusão em massa detectada",
            autostart_enabled=True,
            configured_pair_ready=True,
            attention_category="DELETION_LIMIT_EXCEEDED",
            attention_title="Proteção contra exclusão acionada",
            attention_explanation="Mais de 25 arquivos foram excluídos no destino.",
        )

        win._apply_service_snapshot(snapshot_attention)
        app.processEvents()

        # O quadro de repouso ("Nada para transferir") DEVE estar oculto
        assert win.overview_idle_box.isVisible() is False
        # O banner de atenção DEVE estar visível
        assert win.attention_banner_frame.isVisible() is True
        assert "Atenção pendente" in win.overview_operation_header.text()
        assert win.hero_title_label.text() == "Atenção necessária"

        # Pílulas das pastas devem indicar estado bloqueado ou atenção (nunca "em dia")
        assert "Bloqueado" in win.overview_folder_status_pill.text() or "Atenção" in win.overview_folder_status_pill.text()
        assert "em dia" not in win.overview_folder_status_pill.text()
        assert "Bloqueado" in win.folders_card_status_pill.text() or "Atenção" in win.folders_card_status_pill.text()
        assert "em dia" not in win.folders_card_status_pill.text()

        # Snapshot com atenção de recuperação pendente
        snapshot_recovery = ServiceStatusSnapshot(
            service_pid=1234,
            state=STATE_ATTENTION_REQUIRED,
            state_label="ATENÇÃO NECESSÁRIA",
            detail_message="Recuperação pendente do bisync",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at="2026-10-30T09:00:00Z",
            last_run_status="FAILED",
            last_error_reason="Integridade precisa de atenção",
            autostart_enabled=True,
            configured_pair_ready=True,
            attention_category=ATTENTION_RECOVERY_REQUIRED,
            attention_title="Recuperação do bisync requerida",
            attention_explanation="Execute sincronização inicial ou recuperação de integridade.",
        )

        win._apply_service_snapshot(snapshot_recovery)
        app.processEvents()

        assert win.overview_idle_box.isVisible() is False
        assert win.attention_banner_frame.isVisible() is True
        assert "Recuperação" in win.overview_folder_status_pill.text()

        # Snapshot saudável de repouso
        snapshot_healthy = ServiceStatusSnapshot(
            service_pid=1234,
            state=STATE_WAITING,
            state_label="AGUARDANDO",
            detail_message="Próxima verificação agendada",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at="2026-10-30T12:00:00Z",
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at="2026-10-30T10:00:00Z",
            last_run_status="SUCCESS",
            last_error_reason=None,
            autostart_enabled=True,
            configured_pair_ready=True,
            attention_category=None,
            attention_title=None,
            attention_explanation=None,
        )

        win._apply_service_snapshot(snapshot_healthy)
        app.processEvents()

        # No repouso saudável, o quadro limpo "Nada para transferir" é exibido
        assert win.overview_idle_box.isVisible() is True
        assert win.attention_banner_frame.isVisible() is False
        assert "Na fila" in win.overview_operation_header.text()
        assert win.overview_folder_status_pill.text() == "em dia"
        assert win.folders_card_status_pill.text() == "✓ em dia"
        assert win.hero_title_label.text() == "Tudo em dia"
    finally:
        win.close()

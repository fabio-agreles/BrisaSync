"""Suíte de testes de regressão para contraste e estados da bandeja, setas em QComboBox e layout de Ajustes (v0.1.20)."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QSizePolicy

from brisasync.service.protocol import (
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_SYNCING,
    STATE_VERIFYING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.icons import (
    TRAY_STATE_ATTENTION,
    TRAY_STATE_HEALTHY,
    TRAY_STATE_PAUSED,
    TRAY_STATE_SYNCING,
    detect_desktop_panel_is_dark,
    load_tray_state_icon,
    resolve_tray_icon_for_state,
)
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.styles import (
    apply_brisasync_theme,
    get_active_theme_preference,
    get_brisasync_stylesheet,
    set_active_theme_preference,
)
from brisasync.ui.tray import BrisaTrayController


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_tray_contrast_independence_and_desktop_detection(qapp, monkeypatch, tmp_path: Path):
    """Valida que o contraste da bandeja é independente do tema da janela e respeita GNOME e overrides manuais."""
    db = BrisaDatabase(tmp_path / "test.db")

    # 1. Detecção em ambiente GNOME
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setenv("XDG_SESSION_DESKTOP", "gnome")
    assert detect_desktop_panel_is_dark() is True

    # 2. Alternar o tema da janela para Claro não altera a detecção de painel escuro no GNOME
    set_active_theme_preference("light")
    assert get_active_theme_preference() == "light"
    # Mesmo com a janela em tema claro, a barra do GNOME é escura -> deve retornar True
    assert detect_desktop_panel_is_dark() is True

    # 3. Resolução no modo auto para GNOME retorna ícone claro (para barra escura)
    ic_auto = resolve_tray_icon_for_state(TRAY_STATE_HEALTHY, mode="auto")
    assert not ic_auto.isNull()
    sizes = [s.width() for s in ic_auto.availableSizes()]
    assert 22 in sizes or 24 in sizes

    # 4. Overrides manuais
    # dark_panel -> barra escura -> ícone claro
    ic_dark_panel = resolve_tray_icon_for_state(TRAY_STATE_HEALTHY, mode="dark_panel")
    assert not ic_dark_panel.isNull()

    # light_panel -> barra clara -> ícone escuro
    ic_light_panel = resolve_tray_icon_for_state(TRAY_STATE_HEALTHY, mode="light_panel")
    assert not ic_light_panel.isNull()

    # 5. Persistência de preferência da bandeja no banco
    assert db.get_tray_icon_theme_mode() == "auto"
    db.set_tray_icon_theme_mode("dark_panel")
    assert db.get_tray_icon_theme_mode() == "dark_panel"
    db.set_tray_icon_theme_mode("light_panel")
    assert db.get_tray_icon_theme_mode() == "light_panel"

    # 6. Método set_theme_mode em BrisaTrayController
    controller = BrisaTrayController(db, enable_tray=True, force_tray_available=True)
    assert hasattr(controller, "set_theme_mode")
    controller.set_theme_mode("dark_panel")
    assert controller._theme_mode == "dark_panel"
    controller.set_theme_mode("light_panel")
    assert controller._theme_mode == "light_panel"


def test_tray_semantic_states_transitions_and_information_notifications(qapp, monkeypatch, tmp_path: Path):
    """Valida a semântica dos 4 estados da bandeja e garante que minimizar não envia Warning."""
    db = BrisaDatabase(tmp_path / "test2.db")
    controller = BrisaTrayController(db, enable_tray=True, force_tray_available=True)

    # 1. Verifica os 4 estados geram ícones válidos em todos os tamanhos padrão
    for st in (TRAY_STATE_HEALTHY, TRAY_STATE_SYNCING, TRAY_STATE_PAUSED, TRAY_STATE_ATTENTION):
        ic_dark = load_tray_state_icon(st, panel_is_dark=True)
        assert not ic_dark.isNull(), f"Ícone do estado {st} nulo para painel escuro"
        ic_light = load_tray_state_icon(st, panel_is_dark=False)
        assert not ic_light.isNull(), f"Ícone do estado {st} nulo para painel claro"

    # 2. Transições em update_from_snapshot
    # Snapshot: SYNCING
    snap_sync = ServiceStatusSnapshot(
        service_pid=123,
        state=STATE_SYNCING,
        state_label="SINCRONIZANDO",
        detail_message="Transferindo arquivos...",
        is_cycle_active=True,
        active_rclone_pid=456,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at="2026-11-04 18:00:00",
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
    )
    controller.update_from_snapshot(snap_sync)
    assert controller._current_state == TRAY_STATE_SYNCING
    assert "SINCRONIZANDO" in controller.tooltip_text

    # Snapshot: PAUSED
    snap_paused = ServiceStatusSnapshot(
        service_pid=123,
        state=STATE_PAUSED,
        state_label="PAUSADO",
        detail_message="Sincronização em pausa.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=True,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at="2026-11-04 18:00:00",
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
    )
    controller.update_from_snapshot(snap_paused)
    assert controller._current_state == TRAY_STATE_PAUSED
    assert "PAUSADO" in controller.tooltip_text

    # Snapshot: ATTENTION
    snap_attn = ServiceStatusSnapshot(
        service_pid=123,
        state=STATE_ATTENTION_REQUIRED,
        state_label="ATENÇÃO NECESSÁRIA",
        detail_message="Cofre bloqueado.",
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
        last_error_reason="Cofre bloqueado",
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category="VAULT_LOCKED",
        attention_title="Cofre Bloqueado",
        attention_explanation="Desbloqueie o chaveiro.",
    )
    controller.update_from_snapshot(snap_attn)
    assert controller._current_state == TRAY_STATE_ATTENTION
    assert "ATENÇÃO NECESSÁRIA" in controller.tooltip_text

    # Snapshot: Retorno para HEALTHY (conclusão do ciclo)
    snap_healthy = ServiceStatusSnapshot(
        service_pid=123,
        state=STATE_WAITING,
        state_label="AGUARDANDO",
        detail_message="Tudo em dia.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at="2026-11-04 18:05:00",
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at="2026-11-04 18:00:00",
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
    )
    controller.update_from_snapshot(snap_healthy)
    assert controller._current_state == TRAY_STATE_HEALTHY
    assert "AGUARDANDO" in controller.tooltip_text

    # 3. Notificação na ocultação da janela: usa Information por padrão
    # Mock do tray_icon para capturar parâmetros de showMessage
    mock_tray = MagicMock()
    mock_tray.isVisible.return_value = True
    controller.tray_icon = mock_tray
    monkeypatch.setattr("PySide6.QtWidgets.QSystemTrayIcon.supportsMessages", lambda: True)

    controller.send_tray_message("BrisaSync", "Janela ocultada")
    assert mock_tray.showMessage.called
    args, kwargs = mock_tray.showMessage.call_args
    # O terceiro argumento posicional ou msg_icon deve ser Information, NUNCA Warning
    from PySide6.QtWidgets import QSystemTrayIcon
    assert args[2] == QSystemTrayIcon.MessageIcon.Information


def test_combobox_arrow_svg_files_and_stylesheet_rules():
    """Valida existência dos SVGs vetoriais de seta e regras completas em QSS."""
    # 1. SVGs existem e não são vazios
    arrows_dir = Path(__file__).resolve().parent.parent / "src" / "brisasync" / "resources" / "icons" / "arrows"
    expected_svgs = [
        "arrow-down-dark.svg",
        "arrow-down-light.svg",
        "arrow-down-hover-dark.svg",
        "arrow-down-hover-light.svg",
        "arrow-down-disabled.svg",
    ]
    for name in expected_svgs:
        p = arrows_dir / name
        assert p.is_file(), f"Arquivo SVG {name} não encontrado em {arrows_dir}"
        content = p.read_text(encoding="utf-8")
        assert "<svg" in content
        assert "path" in content

    # 2. QSS contém regras de QComboBox com down-arrow e padding reservado
    qss_dark = get_brisasync_stylesheet(True)
    qss_light = get_brisasync_stylesheet(False)

    for qss, mode in ((qss_dark, "dark"), (qss_light, "light")):
        assert "QComboBox::drop-down" in qss, f"Falta QComboBox::drop-down no modo {mode}"
        assert "QComboBox::down-arrow" in qss, f"Falta QComboBox::down-arrow no modo {mode}"
        assert "padding: 7px 32px 7px 12px" in qss or "padding-right: 32px" in qss
        assert "image: url(" in qss
        assert "QComboBox::down-arrow:hover" in qss
        assert "QComboBox::down-arrow:disabled" in qss


def test_settings_layout_proportions_and_subtitle_policy(qapp, tmp_path: Path):
    """Valida organização em Ajustes, larguras contidas dos seletores e política de tamanho do subtítulo."""
    db = BrisaDatabase(tmp_path / "test3.db")
    win = BrisaMainWindow(database=db, enable_tray=False)
    win.resize(1055, 790)

    # 1. Subtítulo do cabeçalho possui política Preferred (não Ignored)
    assert win.page_subtitle_label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Preferred

    # 2. Dimensões confortáveis e contidas nos seletores de Ajustes (não esticados)
    assert win.theme_mode_combo.maximumWidth() <= 260
    assert win.theme_mode_combo.minimumWidth() >= 140

    assert win.interval_combo.maximumWidth() <= 260
    assert win.interval_combo.minimumWidth() >= 160

    assert win.tray_mode_combo.maximumWidth() <= 280
    assert win.tray_mode_combo.minimumWidth() >= 200

    # 3. Teste responsivo de Ajustes em múltiplas geometrias
    for w, h in ((820, 620), (1055, 790), (1280, 720), (1920, 1080)):
        win.resize(w, h)
        win._apply_responsive_layout(w)
        # Verifica se as linhas existem e estão íntegras
        assert win.settings_theme_row is not None
        assert win.settings_int_row is not None
        assert win.settings_tray_row is not None
        # Verifica se nenhum widget foi desvinculado
        assert win.theme_mode_combo.parent() is not None
        assert win.interval_combo.parent() is not None
        assert win.tray_mode_combo.parent() is not None

    win.close()

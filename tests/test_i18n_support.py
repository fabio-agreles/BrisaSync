"""Testes automatizados completos para o suporte bilíngue (pt_BR e en) do BrisaSync v0.1.22.

Valida:
1. Paridade exata e integridade do catálogo bilíngue (chaves, formatação, interpolação e fallbacks).
2. Resolução de rótulos de estado do protocolo do serviço.
3. Persistência e recuperação da preferência de idioma no SQLite.
4. Invariância estrita dos dados financeiros/Pix e mensagens de apoio localizadas.
5. Alternância dinâmica em tempo de execução na janela principal (BrisaMainWindow).
6. Atualização imediata do controlador da bandeja (BrisaTrayController) e tooltips de estado.
7. Emissão de notificações desktop com títulos e corpos no idioma ativo.
8. Comportamento responsivo do seletor em janela compacta (820x620).
"""

import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QBoxLayout

from brisasync.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_current_language,
    get_state_label,
    get_supported_languages,
    set_current_language,
    tr,
)
from brisasync.i18n.catalog import MESSAGES
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_CONFLICT_DETECTED,
    STATE_ATTENTION_REQUIRED,
    STATE_OFFLINE,
    STATE_PAUSED,
    STATE_SYNCING,
    STATE_VERIFYING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.support import (
    DEFAULT_PIX_BENEFICIARY,
    DEFAULT_PIX_KEY,
    DEFAULT_PIX_PAYLOAD,
    get_localized_support_message,
    get_localized_support_title,
)
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.notifications import NotificationManager
from brisasync.ui.tray import BrisaTrayController


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["brisasync", "-platform", "offscreen"])
    return app


def test_1_catalog_parity_placeholders_and_fallbacks() -> None:
    """Valida paridade exata de chaves entre pt_BR e en, coerência de placeholders e resolução de fallbacks."""
    assert DEFAULT_LANGUAGE == "pt_BR"
    codes = [code for _, code in SUPPORTED_LANGUAGES]
    assert "pt_BR" in codes
    assert "en" in codes

    pt_keys = set(MESSAGES["pt_BR"].keys())
    en_keys = set(MESSAGES["en"].keys())

    missing_in_en = pt_keys - en_keys
    missing_in_pt = en_keys - pt_keys

    assert not missing_in_en, f"Chaves faltando no catálogo en: {missing_in_en}"
    assert not missing_in_pt, f"Chaves sobrando no catálogo en: {missing_in_pt}"
    assert len(pt_keys) >= 270, f"Catálogo possui menos chaves do que o esperado: {len(pt_keys)}"

    # Valida parâmetros de interpolação {param} em ambos os idiomas
    param_pattern = re.compile(r"\{([a-zA-Z0-9_]+)\}")
    for key in pt_keys:
        pt_val = MESSAGES["pt_BR"][key]
        en_val = MESSAGES["en"][key]
        assert isinstance(pt_val, str) and pt_val.strip(), f"Chave {key} vazia em pt_BR"
        assert isinstance(en_val, str) and en_val.strip(), f"Chave {key} vazia em en"

        pt_params = set(param_pattern.findall(pt_val))
        en_params = set(param_pattern.findall(en_val))
        assert pt_params == en_params, f"Divergência de parâmetros na chave {key}: pt={pt_params} en={en_params}"

    # Teste de resolução tr() com idioma ativo e fallback
    try:
        set_current_language("pt_BR")
        assert tr("nav_overview") == "Visão geral"
        assert tr("time_hours_ago", count=3) == "há 3 horas"

        set_current_language("en")
        assert tr("nav_overview") == "Overview"
        assert tr("time_hours_ago", count=3) == "3 hours ago"

        # Fallback para chave desconhecida retorna a própria chave
        assert tr("unknown_dummy_key_123") == "unknown_dummy_key_123"

        # Fallback para idioma não suportado usa pt_BR
        set_current_language("es_ES")
        assert get_current_language() == "pt_BR"
        assert tr("nav_overview") == "Visão geral"
    finally:
        set_current_language("pt_BR")


def test_2_state_labels_localization() -> None:
    """Valida mapeamento bilíngue de todos os estados operacionais do BrisaSync."""
    try:
        set_current_language("pt_BR")
        assert get_state_label(STATE_WAITING) == "AGUARDANDO"
        assert get_state_label(STATE_VERIFYING) == "VERIFICANDO"
        assert get_state_label(STATE_SYNCING) == "SINCRONIZANDO"
        assert get_state_label(STATE_PAUSED) == "PAUSADO"
        assert get_state_label(STATE_OFFLINE) == "SEM CONEXÃO"
        assert get_state_label(STATE_ATTENTION_REQUIRED) == "ATENÇÃO NECESSÁRIA"

        set_current_language("en")
        assert get_state_label(STATE_WAITING) == "WAITING"
        assert get_state_label(STATE_VERIFYING) == "VERIFYING"
        assert get_state_label(STATE_SYNCING) == "SYNCING"
        assert get_state_label(STATE_PAUSED) == "PAUSED"
        assert get_state_label(STATE_OFFLINE) == "NO CONNECTION"
        assert get_state_label(STATE_ATTENTION_REQUIRED) == "ATTENTION REQUIRED"
    finally:
        set_current_language("pt_BR")


def test_3_database_language_preference_persistence(tmp_path: Path) -> None:
    """Valida gravação e recuperação da preferência de idioma no SQLite."""
    db = BrisaDatabase(db_path=tmp_path / "test_lang.db")

    # 1. Padrão inicial sem configuração prévia
    assert db.get_language_preference() == "pt_BR"

    # 2. Persistência de English
    db.set_language_preference("en")
    assert db.get_language_preference() == "en"

    # 3. Persistência de Português
    db.set_language_preference("pt_BR")
    assert db.get_language_preference() == "pt_BR"

    # 4. Idioma inválido deve retornar padrão
    db.set_setting("language_preference", "fr_FR")
    assert db.get_language_preference() == "pt_BR"


def test_4_pix_data_strict_invariance_and_localized_messages() -> None:
    """Garante que a chave Pix, o beneficiário e o EMV payload permaneçam 100% idênticos em ambos os idiomas."""
    # Dados imutáveis
    assert DEFAULT_PIX_BENEFICIARY == "Fábio Agreles Bezerra"
    assert DEFAULT_PIX_KEY == "e4bf0532-8016-42bf-bf2a-fd81326b6621"
    assert DEFAULT_PIX_PAYLOAD == (
        "00020126580014BR.GOV.BCB.PIX0136e4bf0532-8016-42bf-bf2a-fd81326b6621"
        "5204000053039865802BR5921FABIO AGRELES BEZERRA6009GARANHUNS62070503***63046D9B"
    )

    # Mensagens localizadas correspondentes
    title_pt = get_localized_support_title("pt_BR")
    title_en = get_localized_support_title("en")
    assert "Apoie o BrisaSync" in title_pt
    assert "Support BrisaSync" in title_en

    msg_pt = get_localized_support_message("pt_BR")
    msg_en = get_localized_support_message("en")
    assert "O BrisaSync é gratuito e de código aberto" in msg_pt
    assert "BrisaSync is free and open source" in msg_en
    assert "Pix" in msg_pt and "Pix" in msg_en


def test_5_dynamic_language_switch_in_main_window(qapp, tmp_path: Path) -> None:
    """Valida a troca em tempo de execução na janela principal sem fechar ou reiniciar."""
    db = BrisaDatabase(db_path=tmp_path / "test_main_lang.db")
    db.set_language_preference("pt_BR")

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.show()

    try:
        # Estado inicial pt_BR
        assert get_current_language() == "pt_BR"
        assert win.nav_buttons[0].item_text == "Visão geral"
        assert win.nav_buttons[1].item_text == "Pastas"
        assert win.nav_buttons[2].item_text == "Atividade"
        assert win.nav_buttons[3].item_text == "Ajustes"
        assert win.language_combo.currentIndex() == 0
        assert win.language_combo.currentText() == "Português (Brasil)"
        assert win.settings_theme_lbl.text() == "Aparência:"

        # Troca para English (índice 1)
        win.language_combo.setCurrentIndex(1)
        qapp.processEvents()

        assert get_current_language() == "en"
        assert win.nav_buttons[0].item_text == "Overview"
        assert win.nav_buttons[1].item_text == "Folders"
        assert win.nav_buttons[2].item_text == "Activity"
        assert win.nav_buttons[3].item_text == "Settings"
        assert win.language_combo.currentIndex() == 1
        assert win.language_combo.currentText() == "English"
        assert win.settings_theme_lbl.text() == "Appearance:"
        assert db.get_language_preference() == "en"

        # Troca de volta para Português (Brasil) (índice 0)
        win.language_combo.setCurrentIndex(0)
        qapp.processEvents()

        assert get_current_language() == "pt_BR"
        assert win.nav_buttons[0].item_text == "Visão geral"
        assert win.nav_buttons[1].item_text == "Pastas"
        assert win.nav_buttons[2].item_text == "Atividade"
        assert win.nav_buttons[3].item_text == "Ajustes"
        assert win.language_combo.currentIndex() == 0
        assert win.settings_theme_lbl.text() == "Aparência:"
        assert db.get_language_preference() == "pt_BR"

    finally:
        win.close()


def test_6_tray_controller_localization_and_retranslation(qapp, tmp_path: Path) -> None:
    """Valida que o menu da bandeja e tooltips acompanham a troca de idioma."""
    db = BrisaDatabase(db_path=tmp_path / "test_tray_lang.db")

    set_current_language("pt_BR")
    tray = BrisaTrayController(db, enable_tray=True, force_tray_available=True)

    try:
        # Menus iniciais em pt_BR
        assert tray.open_panel_action.text() == "Abrir Painel"
        assert tray.sync_now_action.text() == "Sincronizar Agora"
        assert tray.shutdown_service_action.text() == "Encerrar Serviço de Sincronização"

        # Tooltip com snapshot ocioso/aguardando
        snap_waiting = ServiceStatusSnapshot(
            service_pid=100,
            state=STATE_WAITING,
            state_label="AGUARDANDO",
            detail_message="Tudo sincronizado.",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at="2026-11-08 14:00:00",
            last_run_status="SUCCESS",
            last_error_reason=None,
            autostart_enabled=True,
            configured_pair_ready=True,
        )
        tray.update_from_snapshot(snap_waiting)
        assert "AGUARDANDO" in tray.tooltip_text
        assert "Estado: [AGUARDANDO]" in tray.status_header_action.text()

        # Troca de idioma para en
        set_current_language("en")
        tray.retranslate_tray()

        assert tray.open_panel_action.text() == "Open Panel"
        assert tray.sync_now_action.text() == "Sync Now"
        assert tray.shutdown_service_action.text() == "Shut Down Sync Service"

        tray.update_from_snapshot(snap_waiting)
        assert "WAITING" in tray.tooltip_text
        assert "Status: [WAITING]" in tray.status_header_action.text()

        # Snapshot de sincronização ativa
        snap_syncing = ServiceStatusSnapshot(
            service_pid=100,
            state=STATE_SYNCING,
            state_label="SINCRONIZANDO",
            detail_message="Transferindo arquivos...",
            is_cycle_active=True,
            active_rclone_pid=200,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at=None,
            last_run_status=None,
            last_error_reason=None,
            autostart_enabled=True,
            configured_pair_ready=True,
        )
        tray.update_from_snapshot(snap_syncing)
        assert "SYNCING" in tray.tooltip_text
        assert "Status: [SYNCING]" in tray.status_header_action.text()

    finally:
        set_current_language("pt_BR")


def test_7_notifications_localization(tmp_path: Path) -> None:
    """Valida que títulos e mensagens das notificações respeitam o idioma configurado."""
    db = BrisaDatabase(db_path=tmp_path / "test_notif_lang.db")
    notif = NotificationManager(db, allow_notify_send=False)
    notif._dispatch_to_desktop = MagicMock()

    snap_conflict = ServiceStatusSnapshot(
        service_pid=100,
        state=STATE_ATTENTION_REQUIRED,
        state_label="ATENÇÃO",
        detail_message="Conflito detectado",
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
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category=ATTENTION_CONFLICT_DETECTED,
        conflict_files_count=2,
    )

    try:
        # 1. Notificação em pt_BR
        set_current_language("pt_BR")
        rec_pt = notif.evaluate_snapshot(snap_conflict)
        assert rec_pt is not None
        assert "Conflito" in rec_pt.title
        assert "2 arquivo(s)" in rec_pt.body

        # Reseta assinatura para permitir nova notificação do mesmo evento
        notif.reset_deduplication()

        # 2. Notificação em en
        set_current_language("en")
        rec_en = notif.evaluate_snapshot(snap_conflict)
        assert rec_en is not None
        assert "Conflict" in rec_en.title
        assert "2 file(s)" in rec_en.body

    finally:
        set_current_language("pt_BR")


def test_8_responsive_layout_stability_narrow_window(qapp, tmp_path: Path) -> None:
    """Valida estabilidade do layout de ajustes em janela estreita (820x620) em ambos os idiomas."""
    db = BrisaDatabase(db_path=tmp_path / "test_narrow.db")

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.resize(820, 620)
    win.set_current_page(3)  # Página de Ajustes
    win.show()

    try:
        # Testa responsividade em pt_BR (largura 820 -> LeftToRight)
        win._apply_responsive_layout(820)
        assert win.settings_lang_row.direction() == QBoxLayout.Direction.LeftToRight
        assert win.language_combo.currentIndex() == 0

        # Alterna para en e retesta responsividade
        win.language_combo.setCurrentIndex(1)
        qapp.processEvents()
        win._apply_responsive_layout(820)
        assert win.settings_lang_row.direction() == QBoxLayout.Direction.LeftToRight
        assert win.language_combo.currentIndex() == 1

        # Simula largura estreita extrema (ex: 420px) para testar empilhamento vertical
        win._apply_responsive_layout(420)
        assert win.settings_lang_row.direction() == QBoxLayout.Direction.TopToBottom
    finally:
        win.close()

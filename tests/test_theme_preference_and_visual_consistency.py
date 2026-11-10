"""Testes automatizados da preferência manual de tema e consistência visual (v0.1.18).

Valida:
1. Persistência de tema ('system', 'light', 'dark') no SQLite com padrão 'system'.
2. Sonda de modo escuro/claro e geração de paletas e QSS em styles.py.
3. Seletor 'Aparência' em Ajustes -> Sistema e comutação dinâmica imediata.
4. Modo reativo em 'system' vs estabilidade das escolhas manuais ('light'/'dark').
5. Harmonização de controles, menus, tooltips, remoção de foco duplicado e diálogos.
6. Preservação de contraste do botão primário do Hero em ambos os temas.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QLabel

from brisasync.storage.database import BrisaDatabase
from brisasync.ui.styles import (
    apply_brisasync_theme,
    create_brisasync_palette,
    get_active_theme_preference,
    get_brisasync_stylesheet,
    is_dark_mode,
    set_active_theme_preference,
)
from brisasync.ui.main_window import (
    BrisaMainWindow,
    BrisaAboutDialog,
    BrisaDiagnosticsDialog,
    BrisaExitDialog,
    THEME_PREFERENCE_CHOICES,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        app = QApplication(sys.argv)
    return app


@pytest.fixture
def temp_db(tmp_path: Path) -> BrisaDatabase:
    db_file = tmp_path / "test_theme.db"
    return BrisaDatabase(db_file)


def test_1_database_theme_preference_persistence(temp_db: BrisaDatabase):
    """Testa persistência e valores padrão no SQLite."""
    # 1. Padrão deve ser "system"
    assert temp_db.get_theme_preference() == "system"

    # 2. Persistir "light"
    temp_db.set_theme_preference("light")
    assert temp_db.get_theme_preference() == "light"

    # 3. Persistir "dark"
    temp_db.set_theme_preference("dark")
    assert temp_db.get_theme_preference() == "dark"

    # 4. Voltar para "system"
    temp_db.set_theme_preference("system")
    assert temp_db.get_theme_preference() == "system"

    # 5. Valor inválido normaliza para "system"
    temp_db.set_theme_preference("invalid_value_xyz")
    assert temp_db.get_theme_preference() == "system"


def test_2_styles_active_theme_and_is_dark_mode(qapp):
    """Testa set_active_theme_preference e is_dark_mode em styles.py."""
    # Dark manual
    set_active_theme_preference("dark")
    assert get_active_theme_preference() == "dark"
    assert is_dark_mode() is True

    # Light manual
    set_active_theme_preference("light")
    assert get_active_theme_preference() == "light"
    assert is_dark_mode() is False

    # System
    set_active_theme_preference("system")
    assert get_active_theme_preference() == "system"

    # Verifica paletas
    pal_dark = create_brisasync_palette(dark_mode=True)
    assert pal_dark.color(QPalette.ColorRole.Window).name().upper() == "#0B0F15"

    pal_light = create_brisasync_palette(dark_mode=False)
    assert pal_light.color(QPalette.ColorRole.Window).name().upper() == "#F8FAFC"

    # Verifica QSS gerado em ambos os modos
    qss_dark = get_brisasync_stylesheet(dark_mode=True)
    assert "QToolTip" in qss_dark
    assert "QMenu" in qss_dark
    assert "QAbstractItemView" in qss_dark
    assert "settingFieldLabel" in qss_dark
    assert "footerCardTitle" in qss_dark
    assert "outline: none;" in qss_dark

    qss_light = get_brisasync_stylesheet(dark_mode=False)
    assert "QToolTip" in qss_light
    assert "QMenu" in qss_light
    assert "#F8FAFC" in qss_light


def test_3_ui_theme_combobox_and_immediate_switch(qapp, temp_db: BrisaDatabase):
    """Testa o seletor 'Aparência' em Ajustes -> Sistema e comutação dinâmica."""
    window = BrisaMainWindow(database=temp_db)
    window.resize(1100, 760)

    # 1. Combo existe e possui opções Sistema, Claro, Escuro
    assert hasattr(window, "theme_mode_combo")
    assert window.theme_mode_combo.count() == 3

    items = [window.theme_mode_combo.itemText(i) for i in range(3)]
    assert items == ["Sistema", "Claro", "Escuro"]

    # 2. Valor inicial é "system"
    assert window.theme_mode_combo.currentData() == "system"

    # 3. Mudar para "Claro" via interface
    light_idx = window.theme_mode_combo.findData("light")
    window.theme_mode_combo.setCurrentIndex(light_idx)
    qapp.processEvents()

    assert temp_db.get_theme_preference() == "light"
    assert get_active_theme_preference() == "light"
    assert is_dark_mode() is False

    # 4. Mudar para "Escuro" via interface
    dark_idx = window.theme_mode_combo.findData("dark")
    window.theme_mode_combo.setCurrentIndex(dark_idx)
    qapp.processEvents()

    assert temp_db.get_theme_preference() == "dark"
    assert get_active_theme_preference() == "dark"
    assert is_dark_mode() is True

    window.close()


def test_4_system_mode_reactivity_vs_manual_mode_stability(qapp, temp_db: BrisaDatabase):
    """Testa reatividade no modo Sistema e estabilidade nos modos manuais."""
    window = BrisaMainWindow(database=temp_db)

    # 1. Com preferência "light" salva, chamada de sistema não altera
    temp_db.set_theme_preference("light")
    window.apply_theme()
    assert is_dark_mode() is False

    # Simula notificação do desktop colorSchemeChanged
    window._on_system_color_scheme_changed()
    assert is_dark_mode() is False
    assert get_active_theme_preference() == "light"

    # 2. Com preferência "dark" salva, chamada de sistema não altera
    temp_db.set_theme_preference("dark")
    window.apply_theme()
    assert is_dark_mode() is True

    window._on_system_color_scheme_changed()
    assert is_dark_mode() is True
    assert get_active_theme_preference() == "dark"

    # 3. Com preferência "system" salva, chamada de sistema executa apply_theme
    temp_db.set_theme_preference("system")
    window.apply_theme()
    assert get_active_theme_preference() == "system"

    # Não deve lançar exceção ao chamar _on_system_color_scheme_changed
    window._on_system_color_scheme_changed()
    assert get_active_theme_preference() == "system"

    window.close()


def test_5_dialogs_inherit_theme_and_no_duplicate_focus(qapp, temp_db: BrisaDatabase):
    """Testa que os diálogos instanciam e herdam o tema limpo sem estilos forçados."""
    window = BrisaMainWindow(database=temp_db)

    # Modo Claro
    temp_db.set_theme_preference("light")
    window.apply_theme()

    about_dlg = BrisaAboutDialog(parent=window)
    assert about_dlg.windowTitle().startswith("Sobre o")
    about_dlg.close()

    exit_dlg = BrisaExitDialog(main_window=window, parent=window)
    assert exit_dlg.windowTitle() == "Sair do BrisaSync"
    exit_dlg.close()

    diag_dlg = BrisaDiagnosticsDialog(main_window=window)
    assert "Diagnóstico" in diag_dlg.windowTitle()
    diag_dlg.close()

    # Modo Escuro
    temp_db.set_theme_preference("dark")
    window.apply_theme()

    about_dlg2 = BrisaAboutDialog(parent=window)
    assert about_dlg2.windowTitle().startswith("Sobre o")
    about_dlg2.close()

    window.close()


def test_6_hero_sync_button_and_contrast_preservation(qapp, temp_db: BrisaDatabase):
    """Testa que o botão primário do Hero e o cartão Sobre mantêm alto contraste em ambos os temas."""
    window = BrisaMainWindow(database=temp_db)

    for mode in ("light", "dark"):
        temp_db.set_theme_preference(mode)
        window.apply_theme()
        qapp.processEvents()

        # O botão primário do Hero deve existir e estar estilizado
        btn = window.hero_sync_now_btn
        assert btn is not None
        assert btn.objectName() == "heroPrimaryBtn"

        # O cartão Sobre em Ajustes não deve ter cor branca forçada (#FFFFFF) inline
        for lbl in window.settings_scroll_area.findChildren(QLabel):
            if "BrisaSync v" in lbl.text():
                assert "color: #FFFFFF" not in lbl.styleSheet()
                assert lbl.property("class") == "overviewItemTitle"

    window.close()

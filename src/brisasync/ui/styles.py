"""Folha de estilos (QSS) moderna e adaptativa do BrisaSync.

Harmoniza com as preferências de tema claro e escuro do desktop (GNOME/Adwaita e KDE/Breeze),
mantendo a identidade visual da marca (destaque lavanda, cantos arredondados,
organização visual com cartões e barra lateral nítida).
"""

from __future__ import annotations

import os
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget


_CURRENT_THEME_PREFERENCE: str = "system"


def set_active_theme_preference(pref: str) -> None:
    """Define a preferência ativa de tema ('system', 'light' ou 'dark')."""
    global _CURRENT_THEME_PREFERENCE
    clean = pref.strip().lower() if isinstance(pref, str) else "system"
    if clean in ("system", "light", "dark"):
        _CURRENT_THEME_PREFERENCE = clean


def get_active_theme_preference() -> str:
    """Retorna a preferência ativa de tema ('system', 'light' ou 'dark')."""
    return _CURRENT_THEME_PREFERENCE


def is_dark_mode() -> bool:
    """Detecta se o modo escuro está ativo considerando a preferência do usuário e o desktop.

    Se a preferência for 'dark', retorna True.
    Se a preferência for 'light', retorna False.
    Se a preferência for 'system', consulta a preferência do desktop via styleHints() do Qt
    (Freedesktop color-scheme no Wayland/X11) com fallback seguro para a luminosidade da paleta.
    """
    if _CURRENT_THEME_PREFERENCE == "dark":
        return True
    if _CURRENT_THEME_PREFERENCE == "light":
        return False

    app = QApplication.instance()
    if app is not None:
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Dark:
                return True
            if scheme == Qt.ColorScheme.Light:
                return False
        except (AttributeError, RuntimeError):
            pass
        try:
            window_color = app.palette().window().color()
            return window_color.lightness() < 128
        except (AttributeError, RuntimeError):
            pass
    return True


def create_brisasync_palette(dark_mode: bool = True) -> QPalette:
    """Cria uma paleta equilibrada para o QApplication, evitando menus ou diálogos nativos descompassados."""
    palette = QPalette()
    if dark_mode:
        bg_main = QColor("#0B0F15")
        bg_card = QColor("#131923")
        text_pri = QColor("#F0F4F8")
        text_sec = QColor("#8B949E")
        accent = QColor("#9189FF")
        border = QColor("#273140")

        palette.setColor(QPalette.ColorRole.Window, bg_main)
        palette.setColor(QPalette.ColorRole.WindowText, text_pri)
        palette.setColor(QPalette.ColorRole.Base, bg_card)
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#161D2A"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, bg_card)
        palette.setColor(QPalette.ColorRole.ToolTipText, text_pri)
        palette.setColor(QPalette.ColorRole.Text, text_pri)
        palette.setColor(QPalette.ColorRole.Button, bg_card)
        palette.setColor(QPalette.ColorRole.ButtonText, text_pri)
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#5446CF"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_sec)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_sec)
    else:
        bg_main = QColor("#F8FAFC")
        bg_card = QColor("#FFFFFF")
        text_pri = QColor("#0F172A")
        text_sec = QColor("#64748B")
        accent = QColor("#6355DE")
        border = QColor("#E2E8F0")

        palette.setColor(QPalette.ColorRole.Window, bg_main)
        palette.setColor(QPalette.ColorRole.WindowText, text_pri)
        palette.setColor(QPalette.ColorRole.Base, bg_card)
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F1F5F9"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, bg_card)
        palette.setColor(QPalette.ColorRole.ToolTipText, text_pri)
        palette.setColor(QPalette.ColorRole.Text, text_pri)
        palette.setColor(QPalette.ColorRole.Button, QColor("#F1F5F9"))
        palette.setColor(QPalette.ColorRole.ButtonText, text_pri)
        palette.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_sec)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_sec)

    return palette


def get_brisasync_stylesheet(dark_mode: bool | None = None) -> str:
    """Gera a folha de estilos (QSS) completa e harmonizada com a preferência do desktop."""
    if dark_mode is None:
        dark_mode = is_dark_mode()

    if dark_mode:
        bg_main = "#0B0F15"
        bg_sidebar = "#131923"
        bg_card = "#131923"
        bg_inner_card = "#1A2230"
        bg_control = "#1A2230"
        bg_control_hover = "#232C3D"
        bg_control_pressed = "#161D29"
        bg_control_disabled = "#131923"
        border_color = "#273140"
        border_hover = "#3B4758"
        border_disabled = "#1F2633"
        text_primary = "#F0F4F8"
        text_secondary = "#8B949E"
        text_muted = "#64748B"
        text_disabled = "#555E6D"
        text_heading = "#FFFFFF"
        accent_lavender = "#9189FF"
        accent_lavender_hover = "#A39DFF"
        accent_lavender_pressed = "#7D74FA"
        hero_unconf_bg = "#1E293B"
        hero_unconf_border = "#9189FF"
        hero_unconf_title_color = "#F0F4F8"
        hero_unconf_subtitle_color = "#94A3B8"
        hero_unconf_metric_lbl_color = "#64748B"
        hero_unconf_metric_val_color = "#F0F4F8"
        hero_unconf_primary_bg = "#FFFFFF"
        hero_unconf_primary_fg = "#0B0F15"
        hero_unconf_primary_hover = "#E2E8F0"
        hero_unconf_secondary_bg = "rgba(145, 137, 255, 0.12)"
        hero_unconf_secondary_fg = "#9189FF"
        hero_unconf_secondary_border = "rgba(145, 137, 255, 0.35)"
        hero_unconf_secondary_hover = "rgba(145, 137, 255, 0.22)"
        hero_unconf_secondary_border_hover = "#9189FF"
        table_bg = "#131923"
        table_alt_bg = "#161D2A"
        selection_bg = "#5446CF"
        selection_text = "#FFFFFF"
        scrollbar_handle = "#273140"
        scrollbar_hover = "#3B4758"
        focus_outline = "#9189FF"
        danger_bg = "rgba(248, 113, 113, 0.12)"
        danger_fg = "#F87171"
    else:
        bg_main = "#F8FAFC"
        bg_sidebar = "#F1F5F9"
        bg_card = "#FFFFFF"
        bg_inner_card = "#F8FAFC"
        bg_control = "#FFFFFF"
        bg_control_hover = "#F1F5F9"
        bg_control_pressed = "#E2E8F0"
        bg_control_disabled = "#F8FAFC"
        border_color = "#E2E8F0"
        border_hover = "#CBD5E1"
        border_disabled = "#E2E8F0"
        text_primary = "#0F172A"
        text_secondary = "#475569"
        text_muted = "#64748B"
        text_disabled = "#94A3B8"
        text_heading = "#0F172A"
        accent_lavender = "#6355DE"
        accent_lavender_hover = "#5446CF"
        accent_lavender_pressed = "#4537BF"
        hero_unconf_bg = "#FFFFFF"
        hero_unconf_border = "#6355DE"
        hero_unconf_title_color = "#0F172A"
        hero_unconf_subtitle_color = "#475569"
        hero_unconf_metric_lbl_color = "#64748B"
        hero_unconf_metric_val_color = "#0F172A"
        hero_unconf_primary_bg = "#6355DE"
        hero_unconf_primary_fg = "#FFFFFF"
        hero_unconf_primary_hover = "#5446CF"
        hero_unconf_secondary_bg = "#F1F5F9"
        hero_unconf_secondary_fg = "#4338CA"
        hero_unconf_secondary_border = "#CBD5E1"
        hero_unconf_secondary_hover = "#E2E8F0"
        hero_unconf_secondary_border_hover = "#6355DE"
        table_bg = "#FFFFFF"
        table_alt_bg = "#F8FAFC"
        selection_bg = "#6355DE"
        selection_text = "#FFFFFF"
        scrollbar_handle = "#CBD5E1"
        scrollbar_hover = "#94A3B8"
        focus_outline = "#6355DE"
        danger_bg = "#FEE2E2"
        danger_fg = "#DC2626"

    arrows_dir = Path(__file__).resolve().parent.parent / "resources" / "icons" / "arrows"
    arrow_normal = (arrows_dir / ("arrow-down-dark.svg" if dark_mode else "arrow-down-light.svg")).as_posix()
    arrow_hover = (arrows_dir / ("arrow-down-hover-dark.svg" if dark_mode else "arrow-down-hover-light.svg")).as_posix()
    arrow_disabled = (arrows_dir / "arrow-down-disabled.svg").as_posix()

    checkbox_dir = Path(__file__).resolve().parent.parent / "resources" / "icons" / "checkbox"
    checkmark_icon = (checkbox_dir / ("checkmark-dark.svg" if dark_mode else "checkmark-light.svg")).as_posix()

    return f"""
/* Estilo Global da Aplicação */
QMainWindow, QDialog, QMessageBox {{
    background-color: {bg_main};
    color: {text_primary};
    font-family: system-ui, Cantarell, "Segoe UI", Roboto, Ubuntu, -apple-system, sans-serif;
    font-size: 13px;
}}

QWidget {{
    color: {text_primary};
}}

/* Containers Centrais e Páginas */
#centralWidget, #pageContainer, QStackedWidget, QTabWidget, QTabWidget::pane {{
    background-color: {bg_main};
    border: none;
}}

/* Barra Lateral */
#sidebar {{
    background-color: {bg_sidebar};
    border-right: 1px solid {border_color};
}}

#sidebarBrandTitle {{
    color: {text_heading};
    font-size: 16px;
    font-weight: 700;
}}

#sidebarBrandSubtitle {{
    color: {text_secondary};
    font-size: 11px;
}}

#sidebarSectionLabel {{
    color: {text_muted};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    padding-left: 8px;
}}

/* Componente de Navegação da Barra Lateral */
BrisaSidebarNavItem {{
    background-color: transparent;
    border: none;
    outline: none;
}}

BrisaSidebarNavItem:focus {{
    outline: none;
    border: none;
}}

QPushButton.sidebarNavBtn {{
    background-color: transparent;
    color: {text_secondary};
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton.sidebarNavBtn:hover {{
    background-color: rgba(145, 137, 255, 0.08);
    color: {text_primary};
}}

QPushButton.sidebarNavBtn[active="true"] {{
    background-color: rgba(145, 137, 255, 0.16);
    color: {text_heading};
    font-weight: 600;
    border-left: 3px solid {accent_lavender};
}}

/* Mini Cards do Rodapé da Barra Lateral */
QFrame.sidebarFooterCard {{
    background-color: {bg_inner_card};
    border: 1px solid {border_color};
    border-radius: 10px;
    padding: 8px 10px;
}}

/* Cabeçalho da Área Principal */
#mainHeaderFrame {{
    background-color: {bg_main};
    border-bottom: 1px solid {border_color};
    padding: 14px 24px;
}}

#pageTitle {{
    color: {text_heading};
    font-size: 20px;
    font-weight: 700;
}}

#pageSubtitle {{
    color: {text_secondary};
    font-size: 12px;
}}

/* Pílula de Status Global */
QLabel.statusPill {{
    background-color: {bg_card};
    border: 1px solid {border_color};
    border-radius: 12px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel.statusPillHealthy {{
    background-color: rgba(16, 185, 129, 0.12);
    border: 1px solid rgba(16, 185, 129, 0.35);
    color: #10B981;
}}

QLabel.statusPillSyncing {{
    background-color: rgba(37, 99, 235, 0.12);
    border: 1px solid rgba(37, 99, 235, 0.35);
    color: #60A5FA;
}}

QLabel.statusPillPaused {{
    background-color: rgba(217, 119, 6, 0.12);
    border: 1px solid rgba(217, 119, 6, 0.35);
    color: #F59E0B;
}}

QLabel.statusPillAttention {{
    background-color: rgba(220, 38, 38, 0.12);
    border: 1px solid rgba(220, 38, 38, 0.35);
    color: #EF4444;
}}

/* Cartões Principais */
QFrame.brisaCard {{
    background-color: {bg_card};
    border: 1px solid {border_color};
    border-radius: 16px;
    padding: 16px;
}}

/* Cartões Internos / Superfícies Subordinadas */
QFrame.brisaInnerCard {{
    background-color: {bg_inner_card};
    border: 1px solid {border_color};
    border-radius: 12px;
    padding: 12px 14px;
}}

/* Títulos e Textos de Cartões */
QLabel.cardTitle {{
    color: {text_heading};
    font-size: 14px;
    font-weight: 600;
}}

QLabel.cardSubtitle {{
    color: {text_secondary};
    font-size: 12px;
}}

QLabel.textSecondary {{
    color: {text_secondary};
}}

QLabel.textMuted {{
    color: {text_muted};
}}

/* Hero Status Banner */
QFrame#heroBanner {{
    border-radius: 16px;
    padding: 0px;
}}

QFrame#heroBanner[heroState="healthy"] {{
    background-color: #10B981;
    border: none;
}}

QFrame#heroBanner[heroState="syncing"] {{
    background-color: #2563EB;
    border: none;
}}

QFrame#heroBanner[heroState="paused"] {{
    background-color: #D97706;
    border: none;
}}

QFrame#heroBanner[heroState="attention"] {{
    background-color: #DC2626;
    border: none;
}}

QFrame#heroBanner[heroState="unconfigured"] {{
    background-color: {hero_unconf_bg};
    border: 1.5px solid {hero_unconf_border};
}}

/* Tipografia e Métricas do Hero Banner (Padrão para estados vibrantes) */
QFrame#heroBanner QLabel#heroTitle {{
    color: #FFFFFF;
    font-size: 19px;
    font-weight: 700;
}}

QFrame#heroBanner QLabel#heroSubtitle {{
    color: rgba(255, 255, 255, 0.90);
    font-size: 12px;
}}

QFrame#heroBanner QLabel#heroMetricLabel {{
    font-size: 10px;
    font-weight: 700;
    color: rgba(255, 255, 255, 0.75);
}}

QFrame#heroBanner QLabel#heroMetricValue {{
    font-size: 12px;
    font-weight: 700;
    color: #FFFFFF;
}}

/* Sobrescritas Semânticas no Estado Não Configurado */
QFrame#heroBanner[heroState="unconfigured"] QLabel#heroTitle {{
    color: {hero_unconf_title_color};
}}

QFrame#heroBanner[heroState="unconfigured"] QLabel#heroSubtitle {{
    color: {hero_unconf_subtitle_color};
}}

QFrame#heroBanner[heroState="unconfigured"] QLabel#heroMetricLabel {{
    color: {hero_unconf_metric_lbl_color};
}}

QFrame#heroBanner[heroState="unconfigured"] QLabel#heroMetricValue {{
    color: {hero_unconf_metric_val_color};
}}

/* Botões de Ação do Hero Banner (Padrão para estados vibrantes) */
QPushButton#heroPrimaryBtn {{
    background-color: #FFFFFF;
    color: #0B0F15;
    font-weight: 700;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 13px;
}}

QPushButton#heroPrimaryBtn:hover {{
    background-color: #E2E8F0;
}}

QPushButton#heroPrimaryBtn:focus {{
    outline: 2px solid {focus_outline};
}}

QPushButton#heroPrimaryBtn:disabled {{
    background-color: #E2E8F0;
    color: #94A3B8;
    border: none;
}}

QPushButton#heroSecondaryBtn {{
    background-color: rgba(255, 255, 255, 0.16);
    color: #FFFFFF;
    font-weight: 600;
    border: 1px solid rgba(255, 255, 255, 0.40);
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 13px;
}}

QPushButton#heroSecondaryBtn:hover {{
    background-color: rgba(255, 255, 255, 0.28);
    border-color: rgba(255, 255, 255, 0.65);
}}

QPushButton#heroSecondaryBtn:focus {{
    outline: 2px solid #FFFFFF;
}}

/* Botões do Hero Banner no Estado Não Configurado */
QFrame#heroBanner[heroState="unconfigured"] QPushButton#heroPrimaryBtn {{
    background-color: {hero_unconf_primary_bg};
    color: {hero_unconf_primary_fg};
    border: none;
}}

QFrame#heroBanner[heroState="unconfigured"] QPushButton#heroPrimaryBtn:hover {{
    background-color: {hero_unconf_primary_hover};
}}

QFrame#heroBanner[heroState="unconfigured"] QPushButton#heroPrimaryBtn:disabled {{
    background-color: {bg_control_disabled};
    color: {text_disabled};
}}

QFrame#heroBanner[heroState="unconfigured"] QPushButton#heroSecondaryBtn {{
    background-color: {hero_unconf_secondary_bg};
    color: {hero_unconf_secondary_fg};
    border: 1px solid {hero_unconf_secondary_border};
}}

QFrame#heroBanner[heroState="unconfigured"] QPushButton#heroSecondaryBtn:hover {{
    background-color: {hero_unconf_secondary_hover};
    border-color: {hero_unconf_secondary_border_hover};
    color: {hero_unconf_secondary_fg};
}}

QFrame#heroBanner[heroState="unconfigured"] QPushButton#heroSecondaryBtn:focus {{
    outline: 2px solid {focus_outline};
}}

/* Botões Padrão */
QPushButton {{
    background-color: {bg_control};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {bg_control_hover};
    border-color: {border_hover};
}}

QPushButton:focus {{
    border: 2px solid {focus_outline};
    outline: none;
}}

QPushButton:pressed {{
    background-color: {bg_control_pressed};
}}

QPushButton:disabled {{
    background-color: {bg_control_disabled};
    color: {text_disabled};
    border-color: {border_disabled};
}}

/* Botão de Destaque Lavanda */
QPushButton[primary="true"] {{
    background-color: {accent_lavender};
    color: #FFFFFF;
    font-weight: 600;
    border: none;
}}

QPushButton[primary="true"]:hover {{
    background-color: {accent_lavender_hover};
}}

QPushButton[primary="true"]:focus {{
    outline: 2px solid {focus_outline};
}}

QPushButton[primary="true"]:pressed {{
    background-color: {accent_lavender_pressed};
}}

/* Botão Plano / Link */
QPushButton[flat="true"] {{
    background-color: transparent;
    border: none;
    color: {accent_lavender};
    font-weight: 500;
    padding: 4px 8px;
}}

QPushButton[flat="true"]:hover {{
    color: {accent_lavender_hover};
    text-decoration: underline;
}}

QPushButton[flat="true"]:focus {{
    outline: 2px solid {focus_outline};
}}

/* Campos de Texto */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {bg_control};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 12px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 2px solid {focus_outline};
    outline: none;
}}

/* Seletores Dropdown (QComboBox) com Seta Vetorial Nítida */
QComboBox {{
    background-color: {bg_control};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 7px 32px 7px 12px;
    font-size: 12px;
    min-height: 20px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

QComboBox:hover {{
    border: 1px solid {border_hover};
}}

QComboBox:focus {{
    border: 2px solid {focus_outline};
    outline: none;
}}

QComboBox:disabled {{
    background-color: {bg_control_disabled};
    color: {text_disabled};
    border: 1px solid {border_disabled};
}}

QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 28px;
    border: none;
    background-color: transparent;
}}

QComboBox::down-arrow {{
    image: url({arrow_normal});
    width: 12px;
    height: 12px;
}}

QComboBox::down-arrow:hover {{
    image: url({arrow_hover});
}}

QComboBox::down-arrow:disabled {{
    image: url({arrow_disabled});
}}

QComboBox QAbstractItemView {{
    background-color: {bg_control};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
    color: {text_primary};
    outline: none;
}}

QComboBox QAbstractItemView::item {{
    min-height: 24px;
    padding: 4px 8px;
    border-radius: 4px;
}}

QComboBox QAbstractItemView::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

/* Árvores, Listas e Diálogos de Seleção de Arquivos (QFileDialog) */
QTreeView, QListView, QFileDialog QTreeView, QFileDialog QListView {{
    background-color: {bg_control};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 8px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

QTreeView::item:hover, QListView::item:hover {{
    background-color: {bg_control_hover};
    color: {text_primary};
}}

QTreeView::item:selected, QListView::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

QTreeView:focus, QListView:focus {{
    border: 1.5px solid {focus_outline};
    outline: none;
}}

/* Edição Inline em Diálogos e Modos de Lista/Árvore (ex.: Nova Pasta no QFileDialog) */
QAbstractItemView QLineEdit,
QTreeView QLineEdit,
QListView QLineEdit,
QFileDialog QAbstractItemView QLineEdit {{
    background-color: {bg_control};
    color: {text_primary};
    border: 1.5px solid {focus_outline};
    border-radius: 4px;
    padding: 1px 4px;
    margin: 0px;
    min-height: 20px;
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

QAbstractItemView QLineEdit:focus,
QTreeView QLineEdit:focus,
QListView QLineEdit:focus,
QFileDialog QAbstractItemView QLineEdit:focus {{
    border: 2px solid {focus_outline};
    outline: none;
    color: {text_primary};
}}

/* Checkboxes */
QCheckBox {{
    spacing: 8px;
    font-size: 12px;
    color: {text_primary};
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 1px solid {border_color};
    border-radius: 4px;
    background-color: {bg_control};
}}

QCheckBox::indicator:unchecked {{
    background-color: {bg_control};
    border: 1px solid {border_color};
    image: none;
}}

QCheckBox::indicator:unchecked:hover {{
    border-color: {border_hover};
    background-color: {bg_control_hover};
}}

QCheckBox::indicator:checked {{
    background-color: {accent_lavender};
    border-color: {accent_lavender};
    image: url("{checkmark_icon}");
}}

QCheckBox::indicator:checked:hover {{
    background-color: {accent_lavender_hover};
    border-color: {accent_lavender_hover};
}}

QCheckBox:focus {{
    outline: none;
}}

QCheckBox::indicator:focus {{
    border: 2px solid {focus_outline};
}}

/* Tabelas */
QTableWidget {{
    background-color: {table_bg};
    alternate-background-color: {table_alt_bg};
    border: 1px solid {border_color};
    border-radius: 12px;
    gridline-color: {border_color};
    color: {text_primary};
    selection-background-color: {selection_bg};
    selection-color: {selection_text};
}}

QTableWidget::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

QTableWidget:focus {{
    border: 2px solid {focus_outline};
    outline: none;
}}

QHeaderView::section {{
    background-color: {table_alt_bg};
    color: {text_secondary};
    font-weight: 600;
    font-size: 11px;
    border: none;
    border-bottom: 1px solid {border_color};
    padding: 8px 10px;
}}

/* Rolagem Elegante */
QScrollArea {{
    border: none;
    background-color: {bg_main};
}}

QScrollArea > QWidget > QWidget {{
    background-color: {bg_main};
}}

QScrollBar:vertical {{
    background: {bg_main};
    width: 8px;
    margin: 0px;
    border: none;
}}

QScrollBar::handle:vertical {{
    background: {scrollbar_handle};
    border-radius: 4px;
    min-height: 20px;
}}

QScrollBar::handle:vertical:hover {{
    background: {scrollbar_hover};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: {bg_main};
    height: 8px;
    margin: 0px;
    border: none;
}}

QScrollBar::handle:horizontal {{
    background: {scrollbar_handle};
    border-radius: 4px;
    min-width: 20px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {scrollbar_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* Diálogos Nativos e Mensagens */
QMessageBox QLabel {{
    color: {text_primary};
    font-size: 13px;
}}

QMessageBox QPushButton {{
    min-width: 85px;
}}

QLabel.dialogTitle {{
    color: {text_heading};
    font-size: 15px;
    font-weight: 700;
}}

QLabel.dialogSubtitle {{
    color: {text_secondary};
    font-size: 12px;
}}

QLabel.dialogItemHint {{
    color: {text_muted};
    font-size: 11px;
}}

QPushButton.exitBtnKeep {{
    background-color: {accent_lavender};
    color: #FFFFFF;
    font-weight: 600;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
}}

QPushButton.exitBtnKeep:hover {{
    background-color: {accent_lavender_hover};
}}

QPushButton.exitBtnShutdown {{
    background-color: {danger_bg};
    color: {danger_fg};
    font-weight: 600;
    border: 1px solid {danger_fg};
    border-radius: 8px;
    padding: 10px 16px;
}}

QPushButton.exitBtnShutdown:hover {{
    background-color: {danger_fg};
    color: #FFFFFF;
}}

QPushButton.exitBtnCancel {{
    background-color: transparent;
    color: {text_secondary};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 8px 16px;
}}

QPushButton.exitBtnCancel:hover {{
    background-color: {bg_control_hover};
    color: {text_primary};
}}

/* Tooltips */
QToolTip {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 11px;
}}

/* Menus de Contexto e da Aplicação */
QMenu {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border_color};
    border-radius: 8px;
    padding: 4px;
}}

QMenu::item {{
    background-color: transparent;
    padding: 6px 20px 6px 10px;
    border-radius: 4px;
    font-size: 12px;
}}

QMenu::item:selected {{
    background-color: {selection_bg};
    color: {selection_text};
}}

QMenu::item:disabled {{
    color: {text_disabled};
}}

QMenu::separator {{
    height: 1px;
    background-color: {border_color};
    margin: 4px 6px;
}}

/* Remoção de molduras internas duplicadas */
QAbstractItemView {{
    outline: none;
}}

QTableWidget::item:focus, QTreeView::item:focus, QListView::item:focus {{
    outline: none;
}}

/* Rótulos e Textos Semânticos Adaptativos */
QLabel.settingFieldLabel {{
    font-size: 12px;
    color: {text_primary};
}}

QLabel.footerCardTitle {{
    font-size: 11px;
    font-weight: bold;
    color: {text_heading};
}}

QLabel.footerCardValue {{
    font-size: 10px;
    color: {text_secondary};
}}

QLabel.idleStateTitle {{
    font-weight: 600;
    font-size: 13px;
    color: {text_heading};
}}

QLabel.idleStateSub {{
    font-size: 11px;
    color: {text_secondary};
}}

QLabel.overviewItemTitle {{
    font-weight: 600;
    font-size: 13px;
    color: {text_heading};
}}

QLabel.overviewItemSub {{
    font-size: 11px;
    color: {text_secondary};
}}

QLabel.overviewItemMuted {{
    font-size: 10px;
    color: {text_muted};
}}

QLabel.dialogSubheader {{
    font-size: 12px;
    color: {text_secondary};
}}
"""


def apply_brisasync_theme(
    app: QApplication | None = None,
    main_window: QWidget | None = None,
    theme_preference: str | None = None,
) -> bool:
    """Aplica o tema adaptativo BrisaSync com estilo Fusion e paleta coerente para todo o ciclo de vida.

    Retorna True se o modo resultante for escuro, False se for claro.
    """
    if theme_preference is not None:
        set_active_theme_preference(theme_preference)

    if app is None:
        app = QApplication.instance()
    if app is None:
        return is_dark_mode()

    # Garante motor Fusion para evitar quebras por plugins GTK externos ausentes
    try:
        app.setStyle("Fusion")
    except Exception:
        pass

    dark = is_dark_mode()
    app.setPalette(create_brisasync_palette(dark))
    stylesheet = get_brisasync_stylesheet(dark)
    app.setStyleSheet(stylesheet)
    if main_window is not None:
        main_window.setStyleSheet(stylesheet)
    return dark

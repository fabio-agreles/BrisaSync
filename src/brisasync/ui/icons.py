"""Carregamento de ícones do BrisaSync (janela, aplicativo, HiDPI e recursos de bandeja).

Garantias de implementação:
- Resolve caminhos a partir da localização real do módulo (`Path(__file__).resolve()`),
  nunca dependendo do diretório de trabalho atual (`os.getcwd()`).
- Carrega o ícone colorido `brisasync.png` em todas as resoluções `hicolor`
  (16, 22, 24, 32, 48, 64, 96, 128, 256, 512 e 1024 px) para nitidez em escala
  normal (1x) e HiDPI (1.25x, 1.5x, 2x+).
- Disponibiliza o carregador dos ícones simbólicos de bandeja (`load_tray_icon`):
  como o renderizador SVG do Qt 6.11.2 avalia `fill="currentColor"` como preto
  fixo (`#000000`), utiliza os PNGs fixos multi-tamanho (`brisasync-light-*.png`
  com desenho claro sobre painel escuro e `brisasync-dark-*.png` com desenho
  escuro sobre painel claro).
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPalette, QPixmap

from brisasync.ui.vector_icons import render_vector_pixmap

HICOLOR_SIZES: tuple[int, ...] = (16, 22, 24, 32, 48, 64, 96, 128, 256, 512, 1024)
TRAY_PNG_SIZES: tuple[int, ...] = (16, 22, 24, 32, 48)

TRAY_STATE_HEALTHY: str = "healthy"
TRAY_STATE_SYNCING: str = "syncing"
TRAY_STATE_PAUSED: str = "paused"
TRAY_STATE_ATTENTION: str = "attention"


def get_icons_root_dir() -> Path:
    """Retorna o diretório raiz dos ícones empacotados, independente de `os.getcwd()`."""
    return Path(__file__).resolve().parent.parent / "resources" / "icons"


def get_desktop_entry_path() -> Path:
    """Retorna o caminho do arquivo lançador `brisasync.desktop` empacotado."""
    return Path(__file__).resolve().parent.parent / "resources" / "brisasync.desktop"


def get_hicolor_icon_path(size: int = 256) -> Path:
    """Retorna o caminho de `hicolor/<size>x<size>/apps/brisasync.png`."""
    if size not in HICOLOR_SIZES:
        raise ValueError(f"Tamanho hicolor inválido: {size}. Esperado um de {HICOLOR_SIZES}.")
    return get_icons_root_dir() / "hicolor" / f"{size}x{size}" / "apps" / "brisasync.png"


def load_app_icon() -> QIcon:
    """Carrega o `QIcon` colorido multi-resolução para o aplicativo e janelas."""
    icon = QIcon()
    for size in HICOLOR_SIZES:
        png_path = get_hicolor_icon_path(size)
        if png_path.is_file():
            icon.addFile(str(png_path), QSize(size, size))
    return icon


def load_header_logo_pixmap(
    logical_size: int = 44,
    device_pixel_ratio: float = 1.0,
) -> QPixmap:
    """Carrega `QPixmap` colorido para o cabeçalho da janela com suporte HiDPI."""
    dpr = max(1.0, float(device_pixel_ratio))
    target_px = max(16, int(round(logical_size * dpr)))

    chosen_size = HICOLOR_SIZES[-1]
    for candidate in HICOLOR_SIZES:
        if candidate >= target_px:
            chosen_size = candidate
            break

    source_path = get_hicolor_icon_path(chosen_size)
    raw_pixmap = QPixmap(str(source_path))
    if raw_pixmap.isNull():
        return raw_pixmap

    if chosen_size != target_px:
        scaled = raw_pixmap.scaled(
            target_px,
            target_px,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    else:
        scaled = raw_pixmap

    scaled.setDevicePixelRatio(dpr)
    return scaled


def detect_desktop_panel_is_dark() -> bool:
    """Detecta se o painel/barra de tarefas do desktop possui superfície escura.

    Diferencia a casca do desktop (GNOME Shell, KDE Plasma) da paleta da janela:
    - No GNOME, a barra superior padrão é escura independentemente do tema dos apps.
    - No KDE Plasma, consulta o esquema de cores do desktop via Qt styleHints().
    - Para outros desktops ou quando não há informação confiável, adota painel escuro
      (padrão da maioria das distribuições Linux modernas) para garantir contraste legível.

    Limitação conhecida do modo automático:
    Nem o protocolo StatusNotifierItem (DBus SNI) nem o XEmbed expõem uma API
    padronizada para consultar a cor real da superfície do container da bandeja ou
    temas customizados de shell/extensões. Assumir barra escura no GNOME e consultar
    colorScheme no KDE Plasma é uma inferência de ambiente gráfico, não detecção
    direta de pixels do painel. Por esse motivo, os overrides manuais em Ajustes
    (Automático, Claro, Escuro) são totalmente desacoplados do tema da janela e
    persistem de forma estável.
    """
    desktop = (
        os.environ.get("XDG_CURRENT_DESKTOP", "")
        + ":"
        + os.environ.get("XDG_SESSION_DESKTOP", "")
        + ":"
        + os.environ.get("DESKTOP_SESSION", "")
    ).lower()

    if "gnome" in desktop:
        return True

    app = QGuiApplication.instance()
    if isinstance(app, QGuiApplication):
        try:
            scheme = app.styleHints().colorScheme()
            if scheme == Qt.ColorScheme.Light:
                return False
            if scheme == Qt.ColorScheme.Dark:
                return True
        except (AttributeError, RuntimeError):
            pass

    # Fallback seguro para desktop Linux com barra escura (GNOME, Cinnamon, XFCE dark panels)
    return True


def is_dark_palette_active(palette: QPalette | None = None) -> bool:
    """Detecta se a paleta atual (ou do aplicativo) possui fundo escuro."""
    pal = palette
    if pal is None:
        app = QGuiApplication.instance()
        if isinstance(app, QGuiApplication):
            pal = app.palette()
    if pal is None:
        return True
    bg_color = pal.color(QPalette.ColorRole.Window)
    return bg_color.lightness() < 128


def load_tray_state_icon(
    state: str = TRAY_STATE_HEALTHY,
    *,
    panel_is_dark: bool = True,
) -> QIcon:
    """Carrega o ícone de bandeja multi-resolução para o estado operacional específico."""
    clean_state = (state or TRAY_STATE_HEALTHY).strip().lower()

    icon = QIcon()

    if clean_state == TRAY_STATE_HEALTHY:
        variant = "light" if panel_is_dark else "dark"
        tray_dir = get_icons_root_dir() / "tray"
        for size in TRAY_PNG_SIZES:
            png_path = tray_dir / f"brisasync-{variant}-{size}.png"
            if png_path.is_file():
                icon.addFile(str(png_path), QSize(size, size))
    elif clean_state == TRAY_STATE_SYNCING:
        # Setas circulares de sincronização
        color = "#60A5FA" if panel_is_dark else "#2563EB"
        for size in TRAY_PNG_SIZES:
            pix = render_vector_pixmap("sync", size=size, color=color)
            icon.addPixmap(pix)
    elif clean_state == TRAY_STATE_PAUSED:
        # Símbolo de pausa (duas barras)
        color = "#CBD5E1" if panel_is_dark else "#64748B"
        for size in TRAY_PNG_SIZES:
            pix = render_vector_pixmap("pause", size=size, color=color)
            icon.addPixmap(pix)
    elif clean_state == TRAY_STATE_ATTENTION:
        # Triângulo de alerta/atenção
        color = "#F59E0B" if panel_is_dark else "#D97706"
        for size in TRAY_PNG_SIZES:
            pix = render_vector_pixmap("alert", size=size, color=color)
            icon.addPixmap(pix)
    else:
        # Fallback para healthy
        variant = "light" if panel_is_dark else "dark"
        tray_dir = get_icons_root_dir() / "tray"
        for size in TRAY_PNG_SIZES:
            png_path = tray_dir / f"brisasync-{variant}-{size}.png"
            if png_path.is_file():
                icon.addFile(str(png_path), QSize(size, size))

    if hasattr(icon, "setIsMask"):
        icon.setIsMask(False)
    return icon


def resolve_tray_icon_for_state(
    state: str = TRAY_STATE_HEALTHY,
    mode: str = "auto",
) -> QIcon:
    """Resolve o ícone de bandeja para o estado operacional respeitando a preferência de contraste."""
    clean_mode = (mode or "auto").strip().lower()
    if clean_mode in ("dark_panel", "light", "light_icon"):
        panel_is_dark = True
    elif clean_mode in ("light_panel", "dark", "dark_icon"):
        panel_is_dark = False
    else:
        panel_is_dark = detect_desktop_panel_is_dark()
    return load_tray_state_icon(state, panel_is_dark=panel_is_dark)


def load_tray_icon(*, panel_is_dark: bool | None = None) -> QIcon:
    """Carrega o ícone simbólico de bandeja usando PNGs fixos multi-tamanho."""
    dark = detect_desktop_panel_is_dark() if panel_is_dark is None else panel_is_dark
    return load_tray_state_icon(TRAY_STATE_HEALTHY, panel_is_dark=dark)


def resolve_tray_icon_for_mode(
    mode: str = "auto", palette: QPalette | None = None
) -> QIcon:
    """Resolve o ícone simbólico de bandeja conforme o modo ('auto', 'dark_panel' ou 'light_panel')."""
    return resolve_tray_icon_for_state(TRAY_STATE_HEALTHY, mode=mode)



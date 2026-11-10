"""Camada de interface gráfica desktop (PySide6 / Qt6) do BrisaSync."""

from .icons import (
    HICOLOR_SIZES,
    TRAY_PNG_SIZES,
    TRAY_STATE_ATTENTION,
    TRAY_STATE_HEALTHY,
    TRAY_STATE_PAUSED,
    TRAY_STATE_SYNCING,
    get_desktop_entry_path,
    get_hicolor_icon_path,
    get_icons_root_dir,
    is_dark_palette_active,
    load_app_icon,
    load_header_logo_pixmap,
    load_tray_icon,
    load_tray_state_icon,
    resolve_tray_icon_for_state,
)
from .main_window import (
    BrisaAboutDialog,
    BrisaDiagnosticsDialog,
    BrisaMainWindow,
    SyncRunDetailsDialog,
)

__all__ = [
    "BrisaAboutDialog",
    "BrisaDiagnosticsDialog",
    "BrisaMainWindow",
    "HICOLOR_SIZES",
    "SyncRunDetailsDialog",
    "TRAY_PNG_SIZES",
    "TRAY_STATE_ATTENTION",
    "TRAY_STATE_HEALTHY",
    "TRAY_STATE_PAUSED",
    "TRAY_STATE_SYNCING",
    "get_desktop_entry_path",
    "get_hicolor_icon_path",
    "get_icons_root_dir",
    "is_dark_palette_active",
    "load_app_icon",
    "load_header_logo_pixmap",
    "load_tray_icon",
    "load_tray_state_icon",
    "resolve_tray_icon_for_state",
]

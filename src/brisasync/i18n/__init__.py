"""Subpacote de internacionalização (i18n) do BrisaSync."""

from brisasync.i18n.core import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_current_language,
    get_state_label,
    get_supported_languages,
    set_current_language,
    tr,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "get_current_language",
    "get_state_label",
    "get_supported_languages",
    "set_current_language",
    "tr",
]


"""Mecanismo central de internacionalização (i18n) do BrisaSync.

Gerencia o idioma ativo, funções de consulta e tradução em tempo de execução.
"""

from __future__ import annotations

import logging
from typing import Any

from brisasync.i18n.catalog import MESSAGES
from brisasync.service.protocol import (
    STATE_ATTENTION_REQUIRED,
    STATE_LABELS,
    STATE_OFFLINE,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_SYNCING,
    STATE_VERIFYING,
    STATE_WAITING,
)

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "pt_BR"
SUPPORTED_LANGUAGES: list[tuple[str, str]] = [
    ("Português (Brasil)", "pt_BR"),
    ("English", "en"),
]
_SUPPORTED_CODES = frozenset(code for _, code in SUPPORTED_LANGUAGES)

_ACTIVE_LANGUAGE: str = DEFAULT_LANGUAGE


def get_supported_languages() -> list[tuple[str, str]]:
    """Retorna a lista de opções de idiomas suportados com rótulos e códigos."""
    return list(SUPPORTED_LANGUAGES)


def get_current_language() -> str:
    """Retorna o código do idioma ativo no momento (`pt_BR` ou `en`)."""
    return _ACTIVE_LANGUAGE


def set_current_language(lang_code: str) -> str:
    """Define o idioma ativo no processo gráfico ou de serviço."""
    global _ACTIVE_LANGUAGE
    clean = (lang_code or "").strip()
    if clean not in _SUPPORTED_CODES:
        clean = DEFAULT_LANGUAGE
    _ACTIVE_LANGUAGE = clean
    return _ACTIVE_LANGUAGE


def tr(key: str, _lang: str | None = None, **kwargs: Any) -> str:
    """Retorna a tradução correspondente a `key` no idioma ativo (ou em `_lang`) com interpolação segura.

    Garante fallback para o português (`pt_BR`) caso a chave não seja localizada no idioma
    selecionado e, em última instância, retorna a própria chave textual.
    """
    lang = _lang or _ACTIVE_LANGUAGE
    catalog = MESSAGES.get(lang, {})
    text = catalog.get(key)

    if text is None:
        # Fallback para pt_BR
        text = MESSAGES.get(DEFAULT_LANGUAGE, {}).get(key)

    if text is None:
        text = key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception as exc:
            logger.debug("Falha ao interpolar tradução para chave '%s': %s", key, exc)
            return text

    return text


def get_state_label(state_code: str, lang: str | None = None) -> str:
    """Retorna o rótulo localizado para um código de estado operacional do protocolo."""
    target_lang = lang or _ACTIVE_LANGUAGE
    code_key_map = {
        STATE_WAITING: "state_waiting",
        STATE_VERIFYING: "state_verifying",
        STATE_SYNCING: "state_syncing",
        STATE_PAUSING: "state_pausing",
        STATE_PAUSED: "state_paused",
        STATE_OFFLINE: "state_offline",
        STATE_ATTENTION_REQUIRED: "state_attention_required",
    }
    msg_key = code_key_map.get(state_code)
    if msg_key:
        catalog = MESSAGES.get(target_lang, MESSAGES[DEFAULT_LANGUAGE])
        if msg_key in catalog:
            return catalog[msg_key]

    return STATE_LABELS.get(state_code, state_code)

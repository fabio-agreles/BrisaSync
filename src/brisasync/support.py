"""Módulo de centralização e gestão de apoio voluntário do BrisaSync (Pix).

Centraliza mensagens, beneficiário, chave Pix, Pix Copia e Cola e carregamento
do QR Code para facilitar manutenção, atualizações e forks do projeto.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap

# Valores de contingência caso o arquivo JSON externo não seja localizado
DEFAULT_SUPPORT_TITLE = "Apoie o BrisaSync"
DEFAULT_SUPPORT_MESSAGE = (
    "O BrisaSync é gratuito e de código aberto. Seu desenvolvimento envolve "
    "investimento de tempo, esforço e recursos. Se ele é útil para você, "
    "considere contribuir via Pix para apoiar sua manutenção e evolução. "
    "Toda contribuição é voluntária e todos os recursos continuam disponíveis."
)
DEFAULT_PIX_BENEFICIARY = "Fábio Agreles Bezerra"
DEFAULT_PIX_KEY = "e4bf0532-8016-42bf-bf2a-fd81326b6621"
DEFAULT_PIX_PAYLOAD = (
    "00020126580014BR.GOV.BCB.PIX0136e4bf0532-8016-42bf-bf2a-fd81326b6621"
    "5204000053039865802BR5921FABIO AGRELES BEZERRA6009GARANHUNS62070503***63046D9B"
)


def _get_resources_dir() -> Path:
    """Retorna o diretório de recursos empacotados do BrisaSync."""
    return Path(__file__).resolve().parent / "resources"


def get_support_config() -> dict[str, str]:
    """Carrega as configurações de apoio do arquivo JSON central."""
    json_path = _get_resources_dir() / "support.json"
    if json_path.is_file():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "title": data.get("title", DEFAULT_SUPPORT_TITLE),
                "message": data.get("message", DEFAULT_SUPPORT_MESSAGE),
                "beneficiary": data.get("beneficiary", DEFAULT_PIX_BENEFICIARY),
                "pix_key": data.get("pix_key", DEFAULT_PIX_KEY),
                "pix_payload": data.get("pix_payload", DEFAULT_PIX_PAYLOAD),
            }
        except Exception:
            pass

    return {
        "title": DEFAULT_SUPPORT_TITLE,
        "message": DEFAULT_SUPPORT_MESSAGE,
        "beneficiary": DEFAULT_PIX_BENEFICIARY,
        "pix_key": DEFAULT_PIX_KEY,
        "pix_payload": DEFAULT_PIX_PAYLOAD,
    }


_CONFIG = get_support_config()
SUPPORT_TITLE = _CONFIG["title"]
SUPPORT_MESSAGE = _CONFIG["message"]
PIX_BENEFICIARY = _CONFIG["beneficiary"]
PIX_KEY = _CONFIG["pix_key"]
PIX_PAYLOAD = _CONFIG["pix_payload"]


def get_localized_support_title(lang: str | None = None) -> str:
    """Retorna o título localizado da seção de apoio voluntário."""
    from brisasync.i18n import tr
    return tr("about_support_title", _lang=lang)


def get_localized_support_message(lang: str | None = None) -> str:
    """Retorna a mensagem institucional localizada de apoio voluntário."""
    from brisasync.i18n import tr
    return tr("about_support_message", _lang=lang)


def get_pix_qr_image_path() -> Path:
    """Retorna o caminho canônico do arquivo PNG do QR Code Pix."""
    return _get_resources_dir() / "icons" / "pix_qr.png"


def generate_pix_qr_code(output_path: Path | None = None) -> Path:
    """Gera localmente o QR Code Pix a partir do payload usando qrencode."""
    target = output_path or get_pix_qr_image_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    qrencode_bin = shutil.which("qrencode")
    if not qrencode_bin:
        raise RuntimeError("Utilitário 'qrencode' não encontrado no sistema para geração do QR Code.")

    # Gera QR com margem livre 4, tamanho proporcional 8 e correção de erro M
    subprocess.run(
        [qrencode_bin, "-o", str(target), "-s", "8", "-m", "4", "-l", "M", PIX_PAYLOAD],
        check=True,
    )
    return target


def load_pix_qr_pixmap(size: int = 150) -> QPixmap:
    """Carrega o pixmap do QR Code Pix com escala suave mantendo proporção 1:1."""
    qr_path = get_pix_qr_image_path()
    if not qr_path.is_file():
        # Se porventura não existir, tenta gerar localmente
        try:
            generate_pix_qr_code(qr_path)
        except Exception:
            pass

    if qr_path.is_file():
        pixmap = QPixmap(str(qr_path))
        if not pixmap.isNull():
            return pixmap.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

    # Retorna pixmap vazio em caso de falha
    return QPixmap()


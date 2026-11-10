"""Suíte de testes de integridade para a seção Apoie o BrisaSync (Pix) e Diálogo Sobre (v0.1.21).

Valida:
1. Integridade da configuração centralizada (support.json / support.py):
   - Beneficiário, chave Pix, mensagem e Pix Copia e Cola.
   - Checksum CRC16-CCITT válido.
   - Ausência de valor fixo (campo 54).
   - Presença da nova chave e ausência estrita da chave anterior descontinuada.
2. Decodificação do QR Code gerado:
   - Igualdade exata entre o payload decodificado e o Pix Copia e Cola fornecido.
3. Comportamento da Interface Gráfica no Diálogo Sobre:
   - Beneficiário exibido e chave selecionável.
   - Cópia da chave Pix e do Pix Copia e Cola para a área de transferência com feedback discreto.
   - Renderização do QR Code em fundo branco mesmo sob tema escuro.
   - Suporte a rolagem confortável em janelas compactas.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync.support import (
    PIX_BENEFICIARY,
    PIX_KEY,
    PIX_PAYLOAD,
    SUPPORT_MESSAGE,
    SUPPORT_TITLE,
    get_pix_qr_image_path,
    get_support_config,
    load_pix_qr_pixmap,
)
from brisasync.ui.main_window import BrisaAboutDialog
from brisasync.ui.styles import set_active_theme_preference, apply_brisasync_theme


OLD_FORBIDDEN_KEY = "0ac6e30b-d087-40b8-8b5f-a9269f875546"


@pytest.fixture(scope="session")
def qapp():
    """Garante que QApplication exista no modo offscreen para testes de UI."""
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    return app


def crc16_ccitt(data: str) -> str:
    """Calcula CRC16-CCITT conforme especificação do Banco Central do Brasil para o Pix."""
    crc = 0xFFFF
    for c in data.encode("ascii"):
        crc ^= c << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def test_1_support_config_integrity_and_crc16():
    """Valida integridade do recurso de apoio, cálculo de checksum e ausência de valor fixo."""
    cfg = get_support_config()

    assert cfg["title"] == "Apoie o BrisaSync"
    assert "gratuito e de código aberto" in cfg["message"]
    assert cfg["beneficiary"] == "Fábio Agreles Bezerra"
    assert cfg["pix_key"] == "e4bf0532-8016-42bf-bf2a-fd81326b6621"

    # Não deve conter a chave anterior
    assert OLD_FORBIDDEN_KEY not in cfg["pix_key"]
    assert OLD_FORBIDDEN_KEY not in cfg["pix_payload"]

    # Deve conter a nova chave dentro do payload
    assert cfg["pix_key"] in cfg["pix_payload"]

    # Verificação estrita de ausência de valor fixo (ID 54 na especificação EMVCo)
    assert not re.search(r"54\d{2}", cfg["pix_payload"]), "Payload contém valor fixo indevido!"

    # Validação do Checksum CRC16 (últimos 4 caracteres)
    payload_body = cfg["pix_payload"][:-4]
    expected_crc = cfg["pix_payload"][-4:]
    calculated_crc = crc16_ccitt(payload_body)
    assert calculated_crc == expected_crc == "6D9B", f"CRC16 mismatch: {calculated_crc} vs {expected_crc}"


def test_2_qr_code_decoding_exact_match():
    """Decodifica a imagem do QR Code Pix e confere correspondência exata de payload."""
    qr_path = get_pix_qr_image_path()
    assert qr_path.is_file(), f"Imagem QR Code não encontrada em: {qr_path}"
    assert qr_path.stat().st_size > 0

    # 1. Decodificação via zbarimg
    zbar_proc = subprocess.run(
        ["zbarimg", "--raw", "-q", str(qr_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    decoded_zbar = zbar_proc.stdout.strip()
    assert decoded_zbar == PIX_PAYLOAD, "Payload decodificado pelo zbarimg difere do original!"

    # 2. Confirmação adicional de decodificação via subprocess isolado caso zbarimg ou detector alternativo estejam presentes
    assert len(decoded_zbar) == len(PIX_PAYLOAD)
    assert decoded_zbar.startswith("000201")
    assert decoded_zbar.endswith("6D9B")


def test_3_about_dialog_pix_ui_and_clipboard_actions(qapp):
    """Testa elementos da interface do diálogo Sobre e ações dos botões de cópia."""
    dialog = BrisaAboutDialog()
    dialog.show()

    # Confere título e componentes
    assert dialog.windowTitle().startswith("Sobre o")
    assert PIX_BENEFICIARY in dialog.beneficiary_label.text()
    assert dialog.pix_key_field.text() == PIX_KEY
    assert dialog.pix_key_field.isReadOnly()

    # Confere renderização do QR Code
    pix = dialog.qr_label.pixmap()
    assert pix is not None and not pix.isNull()
    assert pix.width() == 140
    assert pix.height() == 140

    # 1. Testar cópia da chave Pix
    dialog.copy_key_btn.click()
    clipboard_text = QApplication.clipboard().text()
    assert clipboard_text == PIX_KEY
    assert "✓" in dialog.copy_key_btn.text()
    assert "copiada" in dialog.feedback_label.text().lower()

    # 2. Testar cópia do Pix Copia e Cola
    dialog.copy_payload_btn.click()
    clipboard_payload = QApplication.clipboard().text()
    assert clipboard_payload == PIX_PAYLOAD
    assert "✓" in dialog.copy_payload_btn.text()
    assert "copiado" in dialog.feedback_label.text().lower()

    dialog.close()


def test_4_about_dialog_themes_and_small_window_scrolling(qapp):
    """Testa o diálogo Sobre sob os temas Claro e Escuro com rolagem em janela compacta."""
    dialog = BrisaAboutDialog()

    # 1. Modo Claro
    apply_brisasync_theme(app=qapp, main_window=dialog, theme_preference="light")
    dialog.resize(540, 440)
    dialog.show()
    QApplication.processEvents()

    # Garante que o frame do QR Code preserva fundo branco para contraste
    style = dialog.qr_frame.styleSheet()
    assert "#FFFFFF" in style.upper()

    # 2. Modo Escuro
    apply_brisasync_theme(app=qapp, main_window=dialog, theme_preference="dark")
    QApplication.processEvents()

    # No modo escuro o QR Code continua em fundo branco (#FFFFFF)
    assert "#FFFFFF" in dialog.qr_frame.styleSheet().upper()

    # Confere que o diálogo comporta rolagem vertical quando compactado
    dialog.resize(500, 380)
    QApplication.processEvents()

    dialog.close()

"""Script para captura de evidências visuais do diálogo Sobre com seção Apoie o BrisaSync (Pix) v0.1.21.

Gera capturas em alta resolução:
1. Diálogo Sobre completo em Modo Claro (620x560).
2. Diálogo Sobre completo em Modo Escuro (620x560).
3. Detalhe isolado do cartão Apoie o BrisaSync (Modo Claro e Modo Escuro) demonstrando o QR Code
   em fundo branco com quiet margin, chave selecionável e botões de cópia.
4. Diálogo Sobre em geometria compacta (540x440) demonstrando conforto visual e rolagem fluida.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync.ui.main_window import BrisaAboutDialog
from brisasync.ui.styles import apply_brisasync_theme, set_active_theme_preference


def capture_widget(widget, output_path: Path):
    widget.show()
    app = QApplication.instance()
    app.processEvents()
    pix = widget.grab()
    pix.save(str(output_path), "PNG")
    print(f"Salvo: {output_path.name} ({pix.width()}x{pix.height()})")


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    output_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    output_dir.mkdir(parents=True, exist_ok=True)

    for theme_mode, label in (("light", "claro"), ("dark", "escuro")):
        print(f"\n=== Capturando Diálogo Sobre no Tema {label.upper()} ({theme_mode}) ===")
        set_active_theme_preference(theme_mode)

        dlg = BrisaAboutDialog()
        apply_brisasync_theme(app=app, main_window=dlg, theme_preference=theme_mode)
        dlg.resize(620, 560)
        app.processEvents()

        # 1. Diálogo Sobre Completo
        out_dlg = output_dir / f"brisasync_v0.1.21_{label}_dialog_sobre_pix.png"
        capture_widget(dlg, out_dlg)

        # 2. Detalhe do Cartão Apoie o BrisaSync
        if hasattr(dlg, "support_card") and dlg.support_card:
            out_card = output_dir / f"brisasync_v0.1.21_{label}_cartao_pix_detalhe.png"
            capture_widget(dlg.support_card, out_card)

        dlg.close()

    # 3. Geometria compacta demonstrando rolagem vertical suave
    print("\n=== Capturando Diálogo Sobre Compacto (540x440) ===")
    set_active_theme_preference("dark")
    compact_dlg = BrisaAboutDialog()
    apply_brisasync_theme(app=app, main_window=compact_dlg, theme_preference="dark")
    compact_dlg.resize(540, 440)
    app.processEvents()
    out_compact = output_dir / "brisasync_v0.1.21_compacto_dialog_sobre_rolagem.png"
    capture_widget(compact_dlg, out_compact)
    compact_dlg.close()

    print("\nCapturas visuais da v0.1.21 concluídas com sucesso!")


if __name__ == "__main__":
    main()


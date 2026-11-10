"""Script para captura de evidências visuais em alta resolução dos temas Claro e Escuro (v0.1.19).

Gera capturas de tela programáticas de:
- 4 páginas principais (Início/Visão geral, Pastas, Atividade, Ajustes) nas 4 resoluções requeridas:
  * 820x620 (Modo Compacto / Empilhado)
  * 1055x790 (Resolução de Reprodução do Defeito / Empilhado Limpo)
  * 1280x720 (Modo Padrão / Duas Colunas)
  * 1920x1080 (Modo Amplo / Duas Colunas)
- Captura detalhada do cartão Sobre em Ajustes demonstrando contraste perfeito no tema Claro e Escuro.
- Diálogos principais (Ajuda/Diagnóstico, Sobre o BrisaSync, Sair do BrisaSync e Detalhes da Execução).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

# Configura offscreen caso não haja display gráfico
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from brisasync.storage.database import BrisaDatabase, SyncRunRecord
from brisasync.ui.styles import set_active_theme_preference
from brisasync.ui.main_window import (
    BrisaMainWindow,
    BrisaAboutDialog,
    BrisaDiagnosticsDialog,
    BrisaExitDialog,
    SyncRunDetailsDialog,
)


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

    db_path = Path("/tmp/brisasync_screenshots_v019.db")
    if db_path.exists():
        db_path.unlink()
    db = BrisaDatabase(db_path)

    # Configura pares e histórico para evidência visual realista
    test_local = Path("/tmp/BrisaSyncTestFolder")
    test_local.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(test_local)
    db.set_remote_sync_folder(folder_id="1A2B3C4D5E6F", folder_name="Documentos")
    db.set_last_confirmed_sync_at("2026-11-04T13:40:00Z")

    db.record_sync_run(
        started_at="2026-11-04T13:39:45Z",
        finished_at="2026-11-04T13:40:00Z",
        path1="/tmp/BrisaSyncTestFolder",
        path2="drive:Documentos",
        operation="bisync",
        status="SUCCESS",
        exit_code=0,
        summary="3 arquivos baixados, 1 enviado.",
    )
    runs = db.list_recent_sync_runs(limit=1)
    run_rec = runs[0] if runs else None

    window = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)

    resolutions = [
        ("820x620", 820, 620),
        ("1055x790", 1055, 790),
        ("1280x720", 1280, 720),
        ("1920x1080", 1920, 1080),
    ]
    page_names = ["inicio", "pastas", "atividade", "ajustes"]

    for theme_mode, label in (("light", "claro"), ("dark", "escuro")):
        print(f"\n=== Capturando Tema {label.upper()} ({theme_mode}) ===")
        db.set_theme_preference(theme_mode)
        set_active_theme_preference(theme_mode)
        window.apply_theme()
        app.processEvents()

        # 1. Captura das 4 páginas nas 4 resoluções-alvo
        for res_name, w, h in resolutions:
            window.resize(w, h)
            window._apply_responsive_layout(w)
            app.processEvents()

            for idx, page_name in enumerate(page_names):
                window.set_current_page(idx)
                app.processEvents()
                out_file = output_dir / f"brisasync_v0.1.19_{label}_{page_name}_{res_name}.png"
                capture_widget(window, out_file)

        # 2. Captura detalhada do cartão Sobre em Ajustes
        window.set_current_page(3)
        window.resize(1055, 790)
        window._apply_responsive_layout(1055)
        app.processEvents()
        if hasattr(window, "open_about_dlg_btn"):
            about_card = window.open_about_dlg_btn.parentWidget()
            if about_card:
                capture_widget(about_card, output_dir / f"brisasync_v0.1.19_{label}_cartao_sobre_1055x790.png")

        # 3. Diálogos
        # Ajuda / Diagnóstico
        diag_dlg = BrisaDiagnosticsDialog(main_window=window)
        diag_dlg.resize(750, 520)
        app.processEvents()
        capture_widget(diag_dlg, output_dir / f"brisasync_v0.1.19_{label}_dialog_diagnostico.png")
        diag_dlg.close()

        # Sobre
        about_dlg = BrisaAboutDialog(parent=window)
        about_dlg.resize(600, 480)
        app.processEvents()
        capture_widget(about_dlg, output_dir / f"brisasync_v0.1.19_{label}_dialog_sobre.png")
        about_dlg.close()

        # Sair
        exit_dlg = BrisaExitDialog(main_window=window, parent=window)
        exit_dlg.resize(540, 360)
        app.processEvents()
        capture_widget(exit_dlg, output_dir / f"brisasync_v0.1.19_{label}_dialog_sair.png")
        exit_dlg.close()

        # Detalhes da Execução
        if run_rec:
            run_dlg = SyncRunDetailsDialog(run=run_rec, parent=window)
            run_dlg.resize(640, 480)
            app.processEvents()
            capture_widget(run_dlg, output_dir / f"brisasync_v0.1.19_{label}_dialog_detalhes_execucao.png")
            run_dlg.close()

    window.close()
    if db_path.exists():
        db_path.unlink()
    print("\nTodas as capturas v0.1.19 geradas com sucesso!")


if __name__ == "__main__":
    main()

"""Script de captura de telas reais da interface v0.1.22 para validação do suporte bilíngue."""

import os
from pathlib import Path
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync.i18n import get_current_language, set_current_language
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaAboutDialog, BrisaMainWindow

OUT_DIR = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")


def capture_all() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication(["capture_v0122"])

    db = BrisaDatabase(db_path=Path("/tmp/brisasync_capture_i18n.db"))

    # 1. Ajustes em Português (Brasil) (1055x790)
    set_current_language("pt_BR")
    db.set_language_preference("pt_BR")
    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.resize(1055, 790)
    win._apply_responsive_layout(1055)
    win.set_current_page(3)  # Ajustes
    win.show()
    app.processEvents()
    time.sleep(0.1)
    if hasattr(win, "settings_scroll_area"):
        win.settings_scroll_area.verticalScrollBar().setValue(
            win.settings_scroll_area.verticalScrollBar().maximum()
        )
    app.processEvents()
    time.sleep(0.1)

    pix_pt_settings = win.grab()
    pix_pt_settings.save(str(OUT_DIR / "brisasync_v0.1.22_pt_ajustes_sistema.png"))
    print("Salvo: brisasync_v0.1.22_pt_ajustes_sistema.png")

    # 2. Alterna para English via seletor (índice 1)
    win.language_combo.setCurrentIndex(1)
    app.processEvents()
    time.sleep(0.1)
    if hasattr(win, "settings_scroll_area"):
        win.settings_scroll_area.verticalScrollBar().setValue(
            win.settings_scroll_area.verticalScrollBar().maximum()
        )
    app.processEvents()
    time.sleep(0.1)

    pix_en_settings = win.grab()
    pix_en_settings.save(str(OUT_DIR / "brisasync_v0.1.22_en_settings_system.png"))
    print("Salvo: brisasync_v0.1.22_en_settings_system.png")

    # 3. Visão Geral em English (Overview)
    win.set_current_page(0)  # Overview
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()

    pix_en_overview = win.grab()
    pix_en_overview.save(str(OUT_DIR / "brisasync_v0.1.22_en_overview_wide.png"))
    print("Salvo: brisasync_v0.1.22_en_overview_wide.png")

    # 4. Diálogo Sobre em English com seção de Apoio Pix
    about_dlg = BrisaAboutDialog(win)
    about_dlg.show()
    app.processEvents()
    time.sleep(0.1)
    app.processEvents()

    pix_en_about = about_dlg.grab()
    pix_en_about.save(str(OUT_DIR / "brisasync_v0.1.22_en_about_dialog.png"))
    print("Salvo: brisasync_v0.1.22_en_about_dialog.png")
    about_dlg.close()

    # 5. Ajustes em English em Janela Compacta (820x620)
    win.set_current_page(3)
    win.resize(820, 620)
    win._apply_responsive_layout(820)
    app.processEvents()
    time.sleep(0.1)
    if hasattr(win, "settings_scroll_area"):
        win.settings_scroll_area.verticalScrollBar().setValue(
            win.settings_scroll_area.verticalScrollBar().maximum()
        )
    app.processEvents()
    time.sleep(0.1)

    pix_en_narrow = win.grab()
    pix_en_narrow.save(str(OUT_DIR / "brisasync_v0.1.22_en_narrow_settings_820x620.png"))
    print("Salvo: brisasync_v0.1.22_en_narrow_settings_820x620.png")

    win.close()
    print("Todas as capturas da v0.1.22 foram concluídas com sucesso!")


if __name__ == "__main__":
    capture_all()

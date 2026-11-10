"""Script de captura de telas reais da interface v0.1.7 para validação visual."""

import os
from pathlib import Path
import sys
import time

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import QApplication

from brisasync.service.protocol import (
    ATTENTION_RECOVERY_REQUIRED,
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaExitDialog, BrisaMainWindow

OUT_DIR = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")


def capture_all() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication(["capture_v017"])

    db_path = Path.home() / ".local/share/brisasync/brisasync.db"
    db = BrisaDatabase(db_path=db_path if db_path.is_file() else None)

    # 1. Visão Geral Larga (Normal/Maximizada 1100x760)
    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    win.resize(1100, 760)
    win._apply_responsive_layout(1100)
    win.set_current_page(0)
    win.show()
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pix = win.grab()
    pix.save(str(OUT_DIR / "brisasync_v0.1.7_overview_wide.png"))
    print("Salvo: brisasync_v0.1.7_overview_wide.png")

    # 2. Visão Geral Estreita Adaptativa (820x620)
    win.resize(820, 620)
    win._apply_responsive_layout(820)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pix_narrow = win.grab()
    pix_narrow.save(str(OUT_DIR / "brisasync_v0.1.7_overview_narrow.png"))
    print("Salvo: brisasync_v0.1.7_overview_narrow.png")

    # 3. Visão Geral com Estado de Atenção / Integridade Necessária
    snap_att = ServiceStatusSnapshot(
        service_pid=4567,
        state=STATE_ATTENTION_REQUIRED,
        state_label="ATENÇÃO NECESSÁRIA",
        detail_message="Proteção contra exclusão em massa acionada",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at="2026-10-29T22:35:38Z",
        last_run_status="FAILED",
        last_error_reason="Mais de 25 arquivos seriam excluídos em um único ciclo",
        autostart_enabled=False,
        configured_pair_ready=True,
        attention_category="DELETION_LIMIT_EXCEEDED",
        attention_title="Proteção contra exclusão em massa",
        attention_explanation="O bisync detectou que 28 arquivos seriam removidos. A sincronização foi suspensa para proteção dos dados.",
    )
    win.resize(1100, 760)
    win._apply_responsive_layout(1100)
    win._apply_service_snapshot(snap_att)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pix_att = win.grab()
    pix_att.save(str(OUT_DIR / "brisasync_v0.1.7_state_attention.png"))
    print("Salvo: brisasync_v0.1.7_state_attention.png")

    # 4. Ajustes em Janela Estreita (com botão 'Sair do BrisaSync…')
    win.set_current_page(3)
    win.resize(840, 640)
    win._apply_responsive_layout(840)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pix_set_narrow = win.grab()
    pix_set_narrow.save(str(OUT_DIR / "brisasync_v0.1.7_settings_narrow.png"))
    print("Salvo: brisasync_v0.1.7_settings_narrow.png")

    # 5. Diálogo Unificado "Sair do BrisaSync"
    dlg = BrisaExitDialog(win)
    dlg.show()
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pix_dlg = dlg.grab()
    pix_dlg.save(str(OUT_DIR / "brisasync_v0.1.7_exit_dialog.png"))
    print("Salvo: brisasync_v0.1.7_exit_dialog.png")
    dlg.reject()

    # 6. Pastas
    win.set_current_page(1)
    win.resize(1100, 760)
    win._apply_responsive_layout(1100)
    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pix_pastas = win.grab()
    pix_pastas.save(str(OUT_DIR / "brisasync_v0.1.7_pastas.png"))
    print("Salvo: brisasync_v0.1.7_pastas.png")

    win.close()


if __name__ == "__main__":
    capture_all()


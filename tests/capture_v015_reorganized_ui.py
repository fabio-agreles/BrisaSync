"""Gera capturas de tela reais e comparativas do BrisaSync v0.1.5.

Produz evidências em tamanho normal (750x510) e maximizado em tela cheia (1920x1080)
para Início, Atividade e Configurações, além dos diálogos secundários.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.service.protocol import ServiceStatusSnapshot
from brisasync.storage.database import BrisaDatabase, SyncRunRecord
from brisasync.ui.main_window import (
    BrisaAboutDialog,
    BrisaDiagnosticsDialog,
    BrisaMainWindow,
    SyncRunDetailsDialog,
)


class DummyIsolatedStore(CredentialStore):
    def __init__(self, email: str | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._test_email = email

    def has_connected_google_account(self) -> bool:
        return self._test_email is not None

    def load_credentials(self) -> OAuthCredentials | None:
        if not self._test_email:
            return None
        return OAuthCredentials(
            client_id="test_client_id.apps.googleusercontent.com",
            client_secret="test_secret",
            access_token="ya29.test_token",
            refresh_token="1//test_refresh",
            token_type="Bearer",
            expiry="2099-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive openid email",
            account_email=self._test_email,
        )


def capture_all_v015_views() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    output_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    output_dir.mkdir(parents=True, exist_ok=True)

    real_db_path = Path("/home/agreles/.local/share/brisasync/brisasync.db")
    real_db = BrisaDatabase(db_path=real_db_path)
    real_store = CredentialStore()

    # Janela real do usuário
    win = BrisaMainWindow(
        database=real_db,
        credential_store=real_store,
        enable_tray=False,
        allow_notify_send=False,
    )

    last_confirmed = real_db.get_last_confirmed_sync_at()
    snap = ServiceStatusSnapshot.from_dict({
        "service_pid": 326426,
        "state": "WAITING",
        "state_label": "AGUARDANDO",
        "detail_message": "Serviço ativo aguardando próximo ciclo.",
        "is_cycle_active": False,
        "auto_sync_paused": False,
        "sync_interval_seconds": 300,
        "last_confirmed_sync_at": last_confirmed,
        "autostart_enabled": False,
        "configured_pair_ready": True,
        "last_run_status": "SUCCESS",
    })
    win._apply_service_snapshot(snap)

    # 1. TAMANHO NORMAL (~750 × 510)
    win.resize(750, 510)
    win.show()
    app.processEvents()

    # 1.1 Início Normal
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_normal_home.png"))
    print("Salvo: brisasync_v0.1.5_normal_home.png")

    # 1.2 Atividade Normal
    win.tabs.setCurrentIndex(1)
    win.refresh_history_table()
    app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_normal_activity.png"))
    print("Salvo: brisasync_v0.1.5_normal_activity.png")

    # 1.3 Configurações Normal (Colapsado)
    win.tabs.setCurrentIndex(2)
    app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_normal_settings.png"))
    print("Salvo: brisasync_v0.1.5_normal_settings.png")

    # 1.4 Configurações Normal (Avançado Expandido)
    win.advanced_toggle_btn.click()
    app.processEvents()
    if hasattr(win, "settings_scroll_area") and win.settings_scroll_area.verticalScrollBar():
        win.settings_scroll_area.verticalScrollBar().setValue(
            win.settings_scroll_area.verticalScrollBar().maximum()
        )
        app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_normal_settings_advanced.png"))
    print("Salvo: brisasync_v0.1.5_normal_settings_advanced.png")
    win.advanced_toggle_btn.click()  # volta a colapsar
    if hasattr(win, "settings_scroll_area") and win.settings_scroll_area.verticalScrollBar():
        win.settings_scroll_area.verticalScrollBar().setValue(0)
    app.processEvents()

    # 2. TAMANHO MAXIMIZADO (1920 × 1080)
    win.resize(1920, 1080)
    app.processEvents()

    # 2.1 Início Maximizado
    win.tabs.setCurrentIndex(0)
    app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_maximized_home.png"))
    print("Salvo: brisasync_v0.1.5_maximized_home.png")

    # 2.2 Atividade Maximizado
    win.tabs.setCurrentIndex(1)
    app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_maximized_activity.png"))
    print("Salvo: brisasync_v0.1.5_maximized_activity.png")

    # 2.3 Configurações Maximizado
    win.tabs.setCurrentIndex(2)
    app.processEvents()
    win.grab().save(str(output_dir / "brisasync_v0.1.5_maximized_settings.png"))
    print("Salvo: brisasync_v0.1.5_maximized_settings.png")

    # 3. DIÁLOGOS SECUNDÁRIOS
    # 3.1 Ajuda e Diagnóstico
    diag_dlg = win.diagnostics_dialog
    diag_dlg.resize(750, 520)
    diag_dlg.show()
    app.processEvents()
    diag_dlg.grab().save(str(output_dir / "brisasync_v0.1.5_dialog_diagnostics.png"))
    print("Salvo: brisasync_v0.1.5_dialog_diagnostics.png")
    diag_dlg.close()

    # 3.2 Sobre o BrisaSync
    about_dlg = BrisaAboutDialog(win)
    about_dlg.resize(600, 480)
    about_dlg.show()
    app.processEvents()
    about_dlg.grab().save(str(output_dir / "brisasync_v0.1.5_dialog_about.png"))
    print("Salvo: brisasync_v0.1.5_dialog_about.png")
    about_dlg.close()

    # 3.3 Detalhes da Execução
    runs = real_db.list_recent_sync_runs(limit=1)
    if runs:
        run = runs[0]
    else:
        run = SyncRunRecord(
            id=1,
            started_at="2026-10-28T23:07:12Z",
            finished_at="2026-10-28T23:07:22Z",
            path1="/home/agreles/Android/brisa",
            path2="brisasync-1FT8h...:Documentos",
            operation="baseline_resync",
            status="SUCCESS",
            exit_code=0,
            summary="Baseline inicial estabelecida com sucesso.",
        )
    run_dlg = SyncRunDetailsDialog(run, parent=win)
    run_dlg.resize(640, 480)
    run_dlg.show()
    app.processEvents()
    run_dlg.grab().save(str(output_dir / "brisasync_v0.1.5_dialog_run_details.png"))
    print("Salvo: brisasync_v0.1.5_dialog_run_details.png")
    run_dlg.close()

    # 4. ASSISTENTE GUIADO (Ambiente limpo não configurado)
    clean_db_path = output_dir / "scratch" / "clean_v015.db"
    clean_db_path.parent.mkdir(parents=True, exist_ok=True)
    if clean_db_path.exists():
        clean_db_path.unlink()
    clean_db = BrisaDatabase(db_path=clean_db_path)
    clean_store = DummyIsolatedStore(email=None)

    win_clean = BrisaMainWindow(
        database=clean_db,
        credential_store=clean_store,
        enable_tray=False,
        allow_notify_send=False,
    )
    win_clean.resize(750, 510)
    win_clean.tabs.setCurrentIndex(0)
    win_clean.show()
    app.processEvents()
    win_clean.grab().save(str(output_dir / "brisasync_v0.1.5_wizard_unconfigured.png"))
    print("Salvo: brisasync_v0.1.5_wizard_unconfigured.png")

    win.close()
    win_clean.close()
    print("=== Todas as capturas v0.1.5 geradas com sucesso! ===")


if __name__ == "__main__":
    capture_all_v015_views()

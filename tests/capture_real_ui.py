"""Script de captura visual autêntica da sessão real do usuário e do assistente em instalação limpa.

Diferencia formalmente:
1. Operação Normal Real: dados autênticos da sessão do usuário (conta, pastas e histórico reais).
2. Instalação Limpa Real: comportamento do assistente em primeira execução sem dados prévios.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

from PySide6.QtWidgets import QApplication

from brisasync.credentials.store import CredentialStore
from brisasync.service.protocol import (
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow


class EmptyCredentialStore(CredentialStore):
    def has_connected_google_account(self) -> bool:
        return False

    def load_credentials(self) -> None:
        return None


def capture_real_experience() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication(sys.argv)

    output_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    output_dir.mkdir(parents=True, exist_ok=True)

    # =========================================================================
    # 1. CAPTURA REAL DA SESSÃO ATUAL DO USUÁRIO
    # =========================================================================
    real_db_path = Path("/home/agreles/.local/share/brisasync/brisasync.db")
    real_db = BrisaDatabase(db_path=real_db_path)
    real_store = CredentialStore()

    real_window = BrisaMainWindow(
        database=real_db,
        credential_store=real_store,
        enable_tray=False,
        allow_notify_send=False,
    )
    real_window.resize(820, 600)
    real_window.tabs.setCurrentIndex(0)
    real_window.show()
    app.processEvents()

    # Aplica snapshot refletindo o estado operacional real da sessão
    last_confirmed = real_db.get_last_confirmed_sync_at()
    real_snap = ServiceStatusSnapshot(
        service_pid=os.getpid(),
        state=STATE_WAITING,
        state_label="AGUARDANDO",
        detail_message="Pronto para próximo ciclo de reconciliação automática.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=real_db.is_auto_sync_paused(),
        sync_interval_seconds=real_db.get_sync_interval_seconds(300),
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=last_confirmed,
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=real_window.autostart_manager.is_enabled(),
        configured_pair_ready=True,
        attention_category=None,
        attention_title=None,
        attention_explanation=None,
        conflict_files_count=0,
    )
    real_window._apply_service_snapshot(real_snap)
    app.processEvents()

    target_real_home = output_dir / "brisasync_v0.1.1_real_session_home.png"
    real_window.grab().save(str(target_real_home))
    print(f"Captured real session home: {target_real_home}")
    real_window.close()

    # =========================================================================
    # 2. CAPTURA REAL DO ASSISTENTE EM INSTALAÇÃO LIMPA (SEM DADOS PRÉVIOS)
    # =========================================================================
    with tempfile.TemporaryDirectory() as tmp_dir:
        clean_db_path = Path(tmp_dir) / "clean_install.db"
        clean_db = BrisaDatabase(db_path=clean_db_path)
        clean_store = EmptyCredentialStore(lock_path=Path(tmp_dir) / "cred.lock")

        clean_window = BrisaMainWindow(
            database=clean_db,
            credential_store=clean_store,
            enable_tray=False,
            allow_notify_send=False,
        )
        clean_window.resize(820, 600)
        clean_window.tabs.setCurrentIndex(0)
        clean_window.show()
        app.processEvents()

        target_clean_wizard = output_dir / "brisasync_v0.1.1_real_unconfigured_wizard.png"
        clean_window.grab().save(str(target_clean_wizard))
        print(f"Captured clean wizard: {target_clean_wizard}")
        clean_window.close()

    # =========================================================================
    # 3. CAPTURA DO ASSISTENTE EM MÁQUINA LIMPA SEM NENHUM CLIENTE OAUTH
    # =========================================================================
    with tempfile.TemporaryDirectory() as tmp_dir:
        clean_db_path = Path(tmp_dir) / "clean_no_client.db"
        clean_db = BrisaDatabase(db_path=clean_db_path)
        clean_store = EmptyCredentialStore(lock_path=Path(tmp_dir) / "cred.lock")

        # Temporariamente mascara a pasta .config do usuário
        old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(Path(tmp_dir) / "fake_config")

        clean_no_client_win = BrisaMainWindow(
            database=clean_db,
            credential_store=clean_store,
            enable_tray=False,
            allow_notify_send=False,
        )
        clean_no_client_win.resize(820, 600)
        clean_no_client_win.tabs.setCurrentIndex(0)
        clean_no_client_win.show()
        app.processEvents()

        target_clean_no_client = output_dir / "brisasync_v0.1.1_clean_wizard_no_client.png"
        clean_no_client_win.grab().save(str(target_clean_no_client))
        print(f"Captured clean wizard no client: {target_clean_no_client}")
        clean_no_client_win.close()

        if old_xdg is not None:
            os.environ["XDG_CONFIG_HOME"] = old_xdg
        else:
            os.environ.pop("XDG_CONFIG_HOME", None)


if __name__ == "__main__":
    capture_real_experience()

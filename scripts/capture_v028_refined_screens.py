"""Script de captura das novas telas homologadas do BrisaSync v0.1.28.

Gera capturas de tela reais em alta resolução:
1. visao-geral-claro.png (1055x790) - Visão Geral no tema Claro
2. visao-geral-escuro.png (1055x790) - Visão Geral no tema Escuro
3. pastas-claro.png (1055x790) - Painel de Pastas no tema Claro
4. ajustes-claro.png (1055x790) - Painel de Ajustes no tema Claro
5. dialog-sobre-pix.png (620x560) - Diálogo Sobre com apoio Pix
6. brisasync_v0.1.28_unconfigured_light.png (1055x790) - Banner não-configurado corrigido (Claro)
7. brisasync_v0.1.28_unconfigured_dark.png (1055x790) - Banner não-configurado (Escuro)
8. brisasync_v0.1.28_overview_narrow_820x620.png (820x620) - Responsividade em janela compacta
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import time

if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.service.protocol import (
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaAboutDialog, BrisaMainWindow
from brisasync.ui.styles import apply_brisasync_theme, set_active_theme_preference


class MockDemoStore(CredentialStore):
    """Store isolado com dados genéricos de demonstração (zero dados reais)."""

    def __init__(self, email: str | None = "usuario@exemplo.com", **kwargs) -> None:
        super().__init__(**kwargs)
        self._demo_email = email

    def has_connected_google_account(self) -> bool:
        return bool(self._demo_email)

    def load_credentials(self) -> OAuthCredentials | None:
        if not self._demo_email:
            return None
        return OAuthCredentials(
            client_id="demo-client-id.apps.googleusercontent.com",
            client_secret="demo-secret",
            access_token="ya29.demo-token",
            refresh_token="1//demo-refresh",
            token_type="Bearer",
            expiry="2099-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive openid email",
            account_email=self._demo_email,
        )

    def delete_credentials(self) -> None:
        self._demo_email = None


def capture_widget(widget, output_path: Path):
    widget.show()
    app = QApplication.instance()
    app.processEvents()
    time.sleep(0.05)
    app.processEvents()
    pix = widget.grab()
    pix.save(str(output_path), "PNG")
    print(f"Salvo: {output_path.name} ({pix.width()}x{pix.height()})")


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    artifact_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    website_img_dir = Path("/home/agreles/Aplicativos/BrisaSync/website/assets/images")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    website_img_dir.mkdir(parents=True, exist_ok=True)

    # 1. Banco de dados de demonstração isolado
    tmp_db_path = Path("/tmp/brisasync_demo_v028.db")
    if tmp_db_path.exists():
        tmp_db_path.unlink()
    db = BrisaDatabase(tmp_db_path)

    local_folder = Path("/home/usuario/BrisaSync")
    db.set_local_sync_folder(local_folder)
    db.set_remote_sync_folder(folder_id="1BrisaSyncDriveFolderID", folder_name="BrisaSync")
    db.set_last_confirmed_sync_at("2026-11-11T18:00:00Z")
    db.record_sync_run(
        started_at="2026-11-11T17:59:45Z",
        finished_at="2026-11-11T18:00:00Z",
        path1=str(local_folder),
        path2="drive:BrisaSync",
        operation="bisync",
        status="SUCCESS",
        exit_code=0,
        summary="Sincronização bidirecional concluída: 4 arquivos atualizados.",
    )

    store = MockDemoStore(email="usuario@exemplo.com")

    # Snapshot Saudável / Configurado
    snap_healthy = ServiceStatusSnapshot(
        service_pid=12345,
        state=STATE_WAITING,
        state_label="Tudo em dia",
        detail_message="Serviço ativo aguardando próximo ciclo.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at="2026-11-11T18:05:00Z",
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at="2026-11-11T18:00:00Z",
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
    )

    win = BrisaMainWindow(
        database=db,
        credential_store=store,
        enable_tray=False,
        allow_notify_send=False,
    )
    win.show()
    app.processEvents()

    # --- CAPTURAS NO TEMA CLARO (LIGHT) ---
    print("\n--- Gerando Telas Homologadas Tema Claro ---")
    db.set_theme_preference("light")
    set_active_theme_preference("light")
    win.apply_theme()
    win._apply_service_snapshot(snap_healthy)

    # 1. Visão Geral Claro (1055x790)
    win.setFixedSize(1055, 790)
    win._apply_responsive_layout(1055)
    win.set_current_page(0)
    app.processEvents()
    out_vg_claro = website_img_dir / "visao-geral-claro.png"
    capture_widget(win, out_vg_claro)
    shutil.copy2(out_vg_claro, artifact_dir / "brisasync_v0.1.28_visao-geral-claro.png")

    # 2. Pastas Claro (1055x790)
    win.set_current_page(1)
    app.processEvents()
    out_pastas = website_img_dir / "pastas-claro.png"
    capture_widget(win, out_pastas)
    shutil.copy2(out_pastas, artifact_dir / "brisasync_v0.1.28_pastas-claro.png")

    # 3. Ajustes Claro (1055x790)
    win.set_current_page(3)
    app.processEvents()
    out_ajustes = website_img_dir / "ajustes-claro.png"
    capture_widget(win, out_ajustes)
    shutil.copy2(out_ajustes, artifact_dir / "brisasync_v0.1.28_ajustes-claro.png")

    # 4. Diálogo Sobre (Pix) Claro (620x560)
    dlg_about = BrisaAboutDialog(win)
    dlg_about.setFixedSize(620, 560)
    app.processEvents()
    out_dialog = website_img_dir / "dialog-sobre-pix.png"
    capture_widget(dlg_about, out_dialog)
    shutil.copy2(out_dialog, artifact_dir / "brisasync_v0.1.28_dialog-sobre-pix.png")
    dlg_about.close()

    # --- CAPTURAS NO TEMA ESCURO (DARK) ---
    print("\n--- Gerando Telas Homologadas Tema Escuro ---")
    db.set_theme_preference("dark")
    set_active_theme_preference("dark")
    win.apply_theme()
    win._apply_service_snapshot(snap_healthy)

    # 5. Visão Geral Escuro (1055x790)
    win.set_current_page(0)
    win.setFixedSize(1055, 790)
    win._apply_responsive_layout(1055)
    app.processEvents()
    out_vg_escuro = website_img_dir / "visao-geral-escuro.png"
    capture_widget(win, out_vg_escuro)
    shutil.copy2(out_vg_escuro, artifact_dir / "brisasync_v0.1.28_visao-geral-escuro.png")

    # 6. Janela Compacta Responsiva (820x620)
    win.setFixedSize(820, 620)
    win._apply_responsive_layout(820)
    app.processEvents()
    out_narrow = artifact_dir / "brisasync_v0.1.28_overview_narrow_820x620.png"
    capture_widget(win, out_narrow)

    win.close()

    # --- CAPTURA ESPECÍFICA DO ESTADO NÃO-CONFIGURADO (VALIDAÇÃO DE CONTRASTE WCAG) ---
    print("\n--- Gerando Telas de Validação do Banner Não-Configurado ---")
    tmp_unconf_db = Path("/tmp/brisasync_unconf_v028.db")
    if tmp_unconf_db.exists():
        tmp_unconf_db.unlink()
    db_unconf = BrisaDatabase(tmp_unconf_db)
    store_unconf = MockDemoStore(email=None)  # Sem conta

    snap_unconf = ServiceStatusSnapshot(
        service_pid=12345,
        state=STATE_WAITING,
        state_label="Aguardando",
        detail_message="Nenhuma conta conectada.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=None,
        last_run_status=None,
        last_error_reason=None,
        autostart_enabled=False,
        configured_pair_ready=False,
    )

    win_unconf = BrisaMainWindow(
        database=db_unconf,
        credential_store=store_unconf,
        enable_tray=False,
        allow_notify_send=False,
    )
    win_unconf.show()
    app.processEvents()

    # 7. Unconfigured Light (1055x790) - Comprova contraste legível do título, subtítulo e botão Ajuda
    db_unconf.set_theme_preference("light")
    set_active_theme_preference("light")
    win_unconf.apply_theme()
    win_unconf._apply_service_snapshot(snap_unconf)
    win_unconf.setFixedSize(1055, 790)
    win_unconf._apply_responsive_layout(1055)
    win_unconf.set_current_page(0)
    app.processEvents()
    capture_widget(win_unconf, artifact_dir / "brisasync_v0.1.28_unconfigured_light.png")

    # 8. Unconfigured Dark (1055x790)
    db_unconf.set_theme_preference("dark")
    set_active_theme_preference("dark")
    win_unconf.apply_theme()
    win_unconf._apply_service_snapshot(snap_unconf)
    win_unconf.setFixedSize(1055, 790)
    win_unconf._apply_responsive_layout(1055)
    win_unconf.set_current_page(0)
    app.processEvents()
    capture_widget(win_unconf, artifact_dir / "brisasync_v0.1.28_unconfigured_dark.png")

    win_unconf.close()

    print("\nTodas as 8 capturas foram geradas com sucesso!")


if __name__ == "__main__":
    main()

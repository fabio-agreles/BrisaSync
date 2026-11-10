"""Script para captura de telas da nova interface simplificada do BrisaSync v0.1.0.

Valida os 5 aspectos visuais da Rodada 7:
1. Tela Inicial Conectada (~820 × 600, limpa, sem PID/IDs brutos).
2. Tela Inicial Pausada (indicador visual e botão alternado para Retomar).
3. Tela Inicial com Atenção Necessária (banner acionável apenas quando há problema).
4. Aba Atividade (tabela de histórico com horários locais legíveis).
5. Aba Configurações (conta, pastas, intervalo, autoinício, notificações, seção avançada OAuth JSON).
6. Aba Ajuda (diagnóstico real do sistema e dicas).
7. Aba Sobre (identidade Open Source, GPL-3.0-or-later, aviso explícito de independência do Google).
8. Tratamento de caminhos longos (elipses sem deformação de layout).
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from brisasync import __app_name__, __version__
from brisasync.credentials.store import OAuthCredentials
from brisasync.service.protocol import (
    ATTENTION_CONFLICT_DETECTED,
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow


class DummyCredentialStore:
    def __init__(self, email: str = "usuario.teste@gmail.com") -> None:
        self.email = email

    def has_connected_google_account(self) -> bool:
        return bool(self.email)

    def load_credentials(self) -> OAuthCredentials | None:
        if not self.email:
            return None
        return OAuthCredentials(
            client_id="mock-client-id.apps.googleusercontent.com",
            client_secret="mock-secret",
            access_token="ya29.mock-token",
            refresh_token="1//mock-refresh",
            token_type="Bearer",
            expiry="2099-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email=self.email,
        )

    def delete_credentials(self) -> None:
        self.email = ""


def capture_all() -> None:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance() or QApplication(sys.argv)

    output_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        db_path = tmp_path / "screenshots.db"
        db = BrisaDatabase(db_path=db_path)

        local_dir = tmp_path / "GoogleDriveLocal"
        local_dir.mkdir()
        db.set_local_sync_folder(local_dir)
        db.set_remote_sync_folder(
            folder_id="1E5HsgHDPPXFVdFhqRhZGlI88fGdMND22",
            folder_name="Documentos e Projetos",
        )
        db.mark_baseline_initialized(
            local_folder=str(local_dir.resolve()),
            remote_folder_id="1E5HsgHDPPXFVdFhqRhZGlI88fGdMND22",
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        db.set_last_confirmed_sync_at(now_iso)

        # Registra execuções de histórico para a aba Atividade
        db.record_sync_run(
            started_at=now_iso,
            finished_at=now_iso,
            path1=str(local_dir),
            path2="Documentos e Projetos",
            operation="bisync (incremental)",
            status="SUCCESS",
            exit_code=0,
            summary="Sincronização bidirecional concluída: 3 arquivos enviados, 1 recebido.",
        )
        db.record_sync_run(
            started_at=now_iso,
            finished_at=now_iso,
            path1=str(local_dir),
            path2="Documentos e Projetos",
            operation="bisync (incremental)",
            status="ATTENTION_REQUIRED",
            exit_code=1,
            summary="Conflito detectado: 2 arquivos em conflito preservados (.conflict).",
        )

        store = DummyCredentialStore("usuario.teste@gmail.com")

        window = BrisaMainWindow(
            database=db,
            credential_store=store,
            enable_tray=False,
            allow_notify_send=False,
        )
        window.resize(820, 600)
        window.show()
        app.processEvents()

        # -----------------------------------------------------------------
        # 1. Tela Inicial - Conectada e Saudável (~820 × 600)
        # -----------------------------------------------------------------
        window.tabs.setCurrentIndex(0)
        healthy_snap = ServiceStatusSnapshot(
            service_pid=14205,
            state=STATE_WAITING,
            state_label="AGUARDANDO",
            detail_message="Pronto para próximo ciclo de sincronização.",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at=now_iso,
            last_run_status="SUCCESS",
            last_error_reason=None,
            autostart_enabled=True,
            configured_pair_ready=True,
            attention_category=None,
            attention_title=None,
            attention_explanation=None,
            conflict_files_count=0,
        )
        window._apply_service_snapshot(healthy_snap)
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_home_connected.png"))
        print("Captured: brisasync_v0.1.0_home_connected.png")

        # -----------------------------------------------------------------
        # 2. Tela Inicial - Pausada
        # -----------------------------------------------------------------
        paused_snap = ServiceStatusSnapshot(
            service_pid=14205,
            state=STATE_PAUSED,
            state_label="PAUSADO",
            detail_message="Sincronização automática pausada pelo usuário.",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=True,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at=now_iso,
            last_run_status="SUCCESS",
            last_error_reason=None,
            autostart_enabled=True,
            configured_pair_ready=True,
            attention_category=None,
            attention_title=None,
            attention_explanation=None,
            conflict_files_count=0,
        )
        window._apply_service_snapshot(paused_snap)
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_home_paused.png"))
        print("Captured: brisasync_v0.1.0_home_paused.png")

        # -----------------------------------------------------------------
        # 3. Tela Inicial - Atenção Necessária (Banner Ativo)
        # -----------------------------------------------------------------
        attention_snap = ServiceStatusSnapshot(
            service_pid=14205,
            state=STATE_ATTENTION_REQUIRED,
            state_label="ATENÇÃO NECESSÁRIA",
            detail_message="Conflito detectado durante a reconciliação bidirecional.",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at=now_iso,
            last_run_status="ATTENTION_REQUIRED",
            last_error_reason="2 arquivos em conflito.",
            autostart_enabled=True,
            configured_pair_ready=True,
            attention_category=ATTENTION_CONFLICT_DETECTED,
            attention_title="Conflito de Arquivos Detectado",
            attention_explanation="Foram identificadas alterações simultâneas em 2 arquivos. O BrisaSync preservou ambas as versões com segurança adicionando o sufixo '.conflict'.",
            conflict_files_count=2,
        )
        window._apply_service_snapshot(attention_snap)
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_home_attention.png"))
        print("Captured: brisasync_v0.1.0_home_attention.png")

        # -----------------------------------------------------------------
        # 4. Aba Atividade (Histórico de auditoria)
        # -----------------------------------------------------------------
        window.tabs.setCurrentIndex(1)
        window.refresh_history_table()
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_activity.png"))
        print("Captured: brisasync_v0.1.0_activity.png")

        # -----------------------------------------------------------------
        # 5. Aba Configurações
        # -----------------------------------------------------------------
        window.tabs.setCurrentIndex(2)
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_settings.png"))
        print("Captured: brisasync_v0.1.0_settings.png")

        # -----------------------------------------------------------------
        # 6. Aba Ajuda (Diagnóstico)
        # -----------------------------------------------------------------
        window.tabs.setCurrentIndex(3)
        window.refresh_diagnostics()
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_help.png"))
        print("Captured: brisasync_v0.1.0_help.png")

        # -----------------------------------------------------------------
        # 7. Aba Sobre (Identidade e Independência)
        # -----------------------------------------------------------------
        window.tabs.setCurrentIndex(4)
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_about.png"))
        print("Captured: brisasync_v0.1.0_about.png")

        # -----------------------------------------------------------------
        # 8. Teste de Caminhos Longos (Elipse e Estabilidade do Layout)
        # -----------------------------------------------------------------
        window.tabs.setCurrentIndex(0)
        long_path = tmp_path / "SubdiretorioMuitoLongo_Para_Testar_Elipses_Sem_Deformar_O_Layout_Da_Interface_BrisaSync_2026"
        long_path.mkdir(parents=True)
        db.set_local_sync_folder(long_path)
        window._update_home_view()
        app.processEvents()
        window.grab().save(str(output_dir / "brisasync_v0.1.0_long_paths.png"))
        print("Captured: brisasync_v0.1.0_long_paths.png")

        # -----------------------------------------------------------------
        # 9. Assistente de Primeira Configuração (Estado Não Configurado)
        # -----------------------------------------------------------------
        unconfigured_db = BrisaDatabase(db_path=tmp_path / "unconf.db")
        unconf_store = DummyCredentialStore(email="")
        unconf_win = BrisaMainWindow(
            database=unconfigured_db,
            credential_store=unconf_store,
            enable_tray=False,
            allow_notify_send=False,
        )
        unconf_win.resize(820, 600)
        unconf_win.show()
        app.processEvents()
        unconf_win.grab().save(str(output_dir / "brisasync_v0.1.0_home_unconfigured_wizard.png"))
        print("Captured: brisasync_v0.1.0_home_unconfigured_wizard.png")
        unconf_win.close()

        window.close()


if __name__ == "__main__":
    capture_all()

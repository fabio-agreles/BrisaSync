"""Gera capturas visuais da interface refinada do BrisaSync v0.1.3 para documentação e verificação visual.

Captura:
1. Sessão Real do Usuário (Configurada):
   - 'Tudo atualizado' (apenas com sincronização confirmada)
   - Horário local da última sincronização
   - Botões 'Sincronizar Agora' e apenas 'Pausar'
   - Cabeçalho com e-mail abreviado e sem truncamento contra 'Configurar'
   - Dimensões proporcionais (~720 × 480) sem vazio inferior
2. Estados Cotidianos:
   - Sincronizando (com ação secundária 'Parar Sincronização' visível)
   - Pausado (com botão 'Retomar' visível e 'Pausar' oculto)
   - Atenção necessária (com banner de alerta acionável)
3. Assistente Inicial Guiado (uma etapa ativa por vez):
   - Etapa 0: Conectar Conta Google (sem caminho JSON ou jargões)
   - Etapa 1: Pasta no Google Drive
   - Etapa 2: Pasta local dedicada e vazia
   - Etapa 3: Revisão (resumo + explicação de sincronização bidirecional e exclusões)
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication

from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.service.protocol import (
    STATE_ATTENTION_REQUIRED,
    STATE_PAUSED,
    STATE_SYNCING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow


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


def capture_all_refined_views() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    output_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Sessão Real do Usuário (Tudo Atualizado)
    real_db_path = Path("/home/agreles/.local/share/brisasync/brisasync.db")
    real_db = BrisaDatabase(db_path=real_db_path)
    real_store = CredentialStore()

    win_real = BrisaMainWindow(
        database=real_db,
        credential_store=real_store,
        enable_tray=False,
        allow_notify_send=False,
    )
    win_real.resize(750, 510)
    win_real.tabs.setCurrentIndex(0)
    win_real.show()
    app.processEvents()

    last_confirmed = real_db.get_last_confirmed_sync_at()
    snap_updated = ServiceStatusSnapshot(
        service_pid=os.getpid(),
        state=STATE_WAITING,
        state_label="AGUARDANDO",
        detail_message="Pronto para próximo ciclo de reconciliação automática.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=last_confirmed,
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category=None,
        attention_title=None,
        attention_explanation=None,
        conflict_files_count=0,
    )
    win_real._apply_service_snapshot(snap_updated)
    app.processEvents()

    p_updated = output_dir / "brisasync_v0.1.3_home_tudo_atualizado.png"
    win_real.grab().save(str(p_updated))
    print(f"✓ Captura salva: {p_updated}")

    # 2. Estado Sincronizando (com 'Parar Sincronização' visível)
    snap_syncing = ServiceStatusSnapshot(
        service_pid=os.getpid(),
        state=STATE_SYNCING,
        state_label="SINCRONIZANDO",
        detail_message="Executando reconciliação bidirecional com rclone bisync...",
        is_cycle_active=True,
        active_rclone_pid=12345,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=last_confirmed,
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category=None,
        attention_title=None,
        attention_explanation=None,
        conflict_files_count=0,
    )
    win_real._apply_service_snapshot(snap_syncing)
    app.processEvents()

    p_syncing = output_dir / "brisasync_v0.1.3_home_sincronizando.png"
    win_real.grab().save(str(p_syncing))
    print(f"✓ Captura salva: {p_syncing}")

    # 3. Estado Pausado (com 'Retomar' visível e 'Pausar' oculto)
    snap_paused = ServiceStatusSnapshot(
        service_pid=os.getpid(),
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
        last_confirmed_sync_at=last_confirmed,
        last_run_status="SUCCESS",
        last_error_reason=None,
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category=None,
        attention_title=None,
        attention_explanation=None,
        conflict_files_count=0,
    )
    win_real._apply_service_snapshot(snap_paused)
    app.processEvents()

    p_paused = output_dir / "brisasync_v0.1.3_home_pausado.png"
    win_real.grab().save(str(p_paused))
    print(f"✓ Captura salva: {p_paused}")

    # 4. Estado Atenção Necessária
    snap_attention = ServiceStatusSnapshot(
        service_pid=os.getpid(),
        state=STATE_ATTENTION_REQUIRED,
        state_label="ATENÇÃO NECESSÁRIA",
        detail_message="Conflito detectado: 2 arquivos foram modificados simultaneamente.",
        is_cycle_active=False,
        active_rclone_pid=None,
        pending_sync_coalesced=False,
        auto_sync_paused=False,
        sync_interval_seconds=300,
        next_scheduled_sync_at=None,
        backoff_attempt=0,
        backoff_seconds=0,
        last_confirmed_sync_at=last_confirmed,
        last_run_status="CONFLICT",
        last_error_reason="Arquivos em conflito preservados com sufixo seguro",
        autostart_enabled=True,
        configured_pair_ready=True,
        attention_category="CONFLITO_RESOLVIDO_SEGURAMENTE",
        attention_title="Conflito de Edição Simultânea",
        attention_explanation="Foram criadas cópias de segurança (.conflict1) para evitar perda de dados.",
        conflict_files_count=2,
    )
    win_real._apply_service_snapshot(snap_attention)
    app.processEvents()

    p_attention = output_dir / "brisasync_v0.1.3_home_atencao.png"
    win_real.grab().save(str(p_attention))
    print(f"✓ Captura salva: {p_attention}")

    win_real.close()

    # =========================================================================
    # 5. ASSISTENTE INICIAL GUIADO (Passo a Passo)
    # =========================================================================
    with tempfile.TemporaryDirectory() as tmp_dir:
        wz_db = BrisaDatabase(db_path=Path(tmp_dir) / "wz.db")
        wz_store = DummyIsolatedStore(email=None, lock_path=Path(tmp_dir) / "cred.lock")

        win_wz = BrisaMainWindow(
            database=wz_db,
            credential_store=wz_store,
            enable_tray=False,
            allow_notify_send=False,
        )
        win_wz.resize(750, 510)
        win_wz.tabs.setCurrentIndex(0)
        win_wz.show()
        app.processEvents()

        # Etapa 0: Conectar Conta
        win_wz._set_wizard_step(0)
        app.processEvents()
        p_step0 = output_dir / "brisasync_v0.1.3_wizard_etapa0_conectar.png"
        win_wz.grab().save(str(p_step0))
        print(f"✓ Captura salva: {p_step0}")

        # Simula conta conectada
        wz_store._test_email = "fabioagreles@gmail.com"
        win_wz._update_home_view()

        # Etapa 1: Pasta do Drive
        win_wz._set_wizard_step(1)
        wz_db.set_remote_sync_folder(folder_id="1fT8hLz90uYTEJPgsDiNcwlgCYkBJrP1g", folder_name="Documentos")
        win_wz.wizard_remote_combo.addItem("Documentos [ID: 1fT8hLz90uYTEJPgsDiNcwlgCYkBJrP1g]", userData=("1fT8hLz90uYTEJPgsDiNcwlgCYkBJrP1g", "Documentos"))
        win_wz.wizard_remote_combo.setCurrentIndex(0)
        win_wz.wizard_remote_feedback.setText("✓ Pasta remota selecionada: Documentos (ID: 1fT8hLz90uYTEJPgsDiNcwlgCYkBJrP1g)")
        win_wz.wizard_remote_feedback.setStyleSheet("color: #2e7d32;")
        win_wz.wizard_step2_next_btn.setEnabled(True)
        app.processEvents()
        p_step1 = output_dir / "brisasync_v0.1.3_wizard_etapa1_pasta_remota.png"
        win_wz.grab().save(str(p_step1))
        print(f"✓ Captura salva: {p_step1}")

        # Etapa 2: Pasta Local
        win_wz._set_wizard_step(2)
        local_sync_path = Path(tmp_dir) / "BrisaSync"
        local_sync_path.mkdir(exist_ok=True)
        win_wz.wizard_local_path_input.setText(str(local_sync_path))
        wz_db.set_local_sync_folder(str(local_sync_path))
        win_wz.wizard_local_feedback.setText(f"✓ Pasta local pronta e vazia: {local_sync_path}")
        win_wz.wizard_local_feedback.setStyleSheet("color: #2e7d32;")
        win_wz.wizard_step3_next_btn.setEnabled(True)
        app.processEvents()
        p_step2 = output_dir / "brisasync_v0.1.3_wizard_etapa2_pasta_local.png"
        win_wz.grab().save(str(p_step2))
        print(f"✓ Captura salva: {p_step2}")

        # Etapa 3: Revisar e Iniciar
        win_wz._set_wizard_step(3)
        app.processEvents()
        p_step3 = output_dir / "brisasync_v0.1.3_wizard_etapa3_revisar.png"
        win_wz.grab().save(str(p_step3))
        print(f"✓ Captura salva: {p_step3}")

        win_wz.close()

    print("✓ Todas as 8 capturas da interface refinada v0.1.3 foram geradas com sucesso!")


if __name__ == "__main__":
    capture_all_refined_views()

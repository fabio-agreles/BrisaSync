"""Testes de classificação de diagnóstico específico e auditoria de pré-checagem."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from brisasync.backend.rclone_engine import RemoteDirectoryEntry
from brisasync.orchestrator.sync_coordinator import (
    DirectoryAccessError,
    SyncCoordinator,
)
from brisasync.service.daemon import BrisaSessionServiceDaemon
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_CONFLICT_DETECTED,
    ATTENTION_PERSISTENT_FAILURE,
    ATTENTION_RECOVERY_REQUIRED,
    STATE_ATTENTION_REQUIRED,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow


def _get_qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test_attention"])
    return app


def test_daemon_classify_attention_specific_reasons(tmp_path: Path) -> None:
    """Valida que o daemon classifica motivos específicos com precisão sem listar hipóteses genéricas."""
    db = BrisaDatabase(db_path=tmp_path / "test_diag.db")
    daemon = BrisaSessionServiceDaemon(database=db)

    # 1. Pasta local não dedicada / não vazia
    daemon._last_error_reason = (
        "Para a primeira sincronização, a pasta local deve estar dedicada e vazia (3 item(ns) encontrado(s): a.txt, b.txt)."
    )
    cat, title, expl = daemon._classify_attention_details_locked(conflict_count=0)
    assert cat == ATTENTION_RECOVERY_REQUIRED
    assert title == "Pasta Local Não Dedicada ou Não Vazia"
    assert "exige pasta local vazia" in expl
    assert "limite de exclusão em massa atingido" not in expl  # Nenhuma hipótese genérica

    # 2. Exclusão em massa
    daemon._last_error_reason = "Safety abort: mais de 25 arquivos seriam removidos"
    cat, title, expl = daemon._classify_attention_details_locked(conflict_count=0)
    assert cat == ATTENTION_RECOVERY_REQUIRED
    assert title == "Proteção contra Exclusão em Massa"
    assert "número de exclusões detectadas ultrapassou o limite" in expl
    assert "marcador .brisasync_check ausente" not in expl

    # 3. Marcador ausente
    daemon._last_error_reason = "Marcador de integridade .brisasync_check não foi encontrado"
    cat, title, expl = daemon._classify_attention_details_locked(conflict_count=0)
    assert cat == ATTENTION_RECOVERY_REQUIRED
    assert title == "Marcador de Integridade Ausente"
    assert ".brisasync_check" in expl

    # 4. Pasta inacessível
    daemon._last_error_reason = "A pasta não existe ou não foi encontrada no caminho indicado"
    cat, title, expl = daemon._classify_attention_details_locked(conflict_count=0)
    assert cat == ATTENTION_RECOVERY_REQUIRED
    assert title == "Pasta Inacessível ou Inexistente"

    # 5. Motivo desconhecido / não categorizado
    daemon._last_error_reason = "Falha incomum do driver de rede de terceiros XYZ"
    daemon._backoff_attempt = 0
    daemon._last_run_status = "FAILED"
    cat, title, expl = daemon._classify_attention_details_locked(conflict_count=0)
    assert cat == ATTENTION_RECOVERY_REQUIRED
    assert title == "Atenção Necessária"
    assert "Motivo ainda não identificado" in expl
    assert "XYZ" in expl


def test_coordinator_precheck_records_sync_run_and_raises(tmp_path: Path) -> None:
    """Valida que falhas de pré-checagem gravam auditoria em sync_runs antes de propagar o erro."""
    db = BrisaDatabase(db_path=tmp_path / "test_coord.db")
    local_dir = tmp_path / "local_sync"
    local_dir.mkdir()
    (local_dir / "arquivo_existente.txt").write_text("conteudo anterior")

    mock_engine = MagicMock()
    mock_bridge = MagicMock()
    mock_bridge.authenticated_rclone_session.return_value.__enter__.return_value = {}

    remote_entry = RemoteDirectoryEntry(
        folder_id="remote_id_nova",
        name="Nova Pasta Remota",
        path="Nova Pasta Remota",
    )
    mock_engine.resolve_remote_directory_by_id.return_value = remote_entry

    coord = SyncCoordinator(database=db, engine=mock_engine, bridge=mock_bridge)

    with pytest.raises(DirectoryAccessError) as exc_info:
        coord.synchronize_google_drive_pair(
            local_folder=local_dir,
            remote_folder_id="remote_id_nova",
        )

    assert "deve estar dedicada e vazia" in str(exc_info.value)

    # Verifica se a auditoria foi gravada na tabela sync_runs
    runs = db.list_recent_sync_runs(limit=5)
    assert len(runs) == 1
    run = runs[0]
    assert run.operation == "baseline_precheck"
    assert run.status == "ATTENTION_REQUIRED"
    assert run.exit_code == -1
    assert "arquivo_existente.txt" in run.summary


def test_ui_displays_specific_attention_reason_and_opens_dialog(tmp_path: Path) -> None:
    """Valida a exibição fiel do motivo conhecido e acesso ao erro sanitizado na interface."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "test_ui_diag.db")
    db.set_local_sync_folder(str(tmp_path / "local"))
    db.set_remote_sync_folder(folder_id="fid99", folder_name="Remoto Teste")

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    fake_creds = MagicMock()
    fake_creds.access_token = "fake-token"
    fake_creds.refresh_token = "fake-refresh"
    fake_creds.has_drive_scope = True
    fake_creds.account_email = "usuario@example.com"
    win.credential_store = MagicMock()
    win.credential_store.load_credentials.return_value = fake_creds
    win.credential_store.is_vault_locked.return_value = False
    win.show()

    try:
        # Snapshot com motivo específico de pasta local não vazia
        snapshot = ServiceStatusSnapshot(
            service_pid=9999,
            state=STATE_ATTENTION_REQUIRED,
            state_label="ATENÇÃO NECESSÁRIA",
            detail_message="Atenção: pasta local ocupada",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at=None,
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at=None,
            last_run_status="ATTENTION_REQUIRED",
            last_error_reason="Para a primeira sincronização, a pasta local deve estar dedicada e vazia (3 itens)",
            autostart_enabled=False,
            configured_pair_ready=True,
            attention_category=ATTENTION_RECOVERY_REQUIRED,
            attention_title="Pasta Local Não Dedicada ou Não Vazia",
            attention_explanation="A primeira sincronização com uma nova pasta remota exige pasta local vazia. Para a primeira sincronização, a pasta local deve estar dedicada e vazia (3 itens)",
        )

        win._apply_service_snapshot(snapshot)
        app.processEvents()

        # O banner de atenção deve apresentar o motivo conhecido diretamente
        banner_text = win.attention_explanation_label.text()
        assert "Pasta Local Não Dedicada ou Não Vazia" in banner_text
        assert "exige pasta local vazia" in banner_text
        assert "limite de exclusão em massa atingido" not in banner_text

        # Botão 'Ver Detalhes...' existe e pode ser acionado
        assert win.inspect_details_button.isVisible() is True
        assert win.inspect_attention_button.isVisible() is True
    finally:
        win.close()


def test_reject_new_pair_when_local_folder_not_empty_and_preserves_config(tmp_path: Path) -> None:
    """Valida que a escolha de um novo par com pasta local não vazia é rejeitada e preserva a configuração anterior."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "test_reject_pair.db")

    local_orig = tmp_path / "local_orig"
    local_orig.mkdir()
    (local_orig / "arquivo_original.txt").write_text("dados existentes")

    db.set_local_sync_folder(str(local_orig))
    db.set_remote_sync_folder(folder_id="orig_id", folder_name="Documentos")
    db.mark_baseline_initialized(local_folder=str(local_orig), remote_folder_id="orig_id")

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    fake_creds = MagicMock()
    fake_creds.access_token = "fake-token"
    fake_creds.refresh_token = "fake-refresh"
    fake_creds.has_drive_scope = True
    fake_creds.account_email = "usuario@example.com"
    win.credential_store = MagicMock()
    win.credential_store.load_credentials.return_value = fake_creds
    win.credential_store.is_vault_locked.return_value = False
    win.show()

    try:
        # Preenche o combo com a pasta original e uma nova pasta sem baseline
        win.remote_folder_combo.blockSignals(True)
        win.remote_folder_combo.clear()
        win.remote_folder_combo.addItem("Documentos", ("orig_id", "Documentos"))
        win.remote_folder_combo.addItem("Mensagens", ("nova_id", "Mensagens"))
        win.remote_folder_combo.setCurrentIndex(0)
        win.remote_folder_combo.blockSignals(False)

        # 1. Usuário tenta selecionar "Mensagens" mantendo a pasta local povoada
        win._on_remote_folder_selection_changed(1)

        # Deve ser rejeitado: combo revertido para 0, banco mantém 'orig_id'
        assert win.remote_folder_combo.currentIndex() == 0
        rem_cfg = db.get_remote_sync_folder()
        assert rem_cfg is not None
        assert rem_cfg.folder_id == "orig_id"
        assert rem_cfg.folder_name == "Documentos"
        assert "[REJEITADA]" in win.remote_folder_feedback_label.text()
        assert "Escolha outra pasta local vazia" in win.remote_folder_feedback_label.text()

        # 2. Usuário tenta alterar a pasta local para outra pasta que contém arquivos
        other_non_empty = tmp_path / "outra_pasta_com_arquivos"
        other_non_empty.mkdir()
        (other_non_empty / "nota.txt").write_text("outro arquivo")

        # Configura um remote ainda não inicializado
        db.set_remote_sync_folder(folder_id="novo_remoto_id", folder_name="Nova Pasta Remota")
        win.folder_input.setText(str(other_non_empty))
        saved = win.save_and_validate_folder()

        # Deve ser rejeitado: retorna False, input restaurado para local_orig, banco preservado
        assert saved is False
        assert win.folder_input.text() == str(local_orig)
        assert db.get_local_sync_folder().folder_path == str(local_orig)
        assert "[REJEITADA]" in win.folder_feedback_label.text()
        assert "Escolha outra pasta vazia" in win.folder_feedback_label.text()
    finally:
        win.close()


def test_daemon_precondition_blocks_non_empty_local_folder(tmp_path: Path) -> None:
    """Valida que o daemon rejeita novo par antes de ativar ciclo ou agendamento periódico."""
    db = BrisaDatabase(db_path=tmp_path / "test_daemon_precond.db")
    local_dir = tmp_path / "local_brisa"
    local_dir.mkdir()
    (local_dir / "arquivo_existente.txt").write_text("conteudo")

    db.set_local_sync_folder(str(local_dir))
    db.set_remote_sync_folder(folder_id="fid_novo", folder_name="Mensagens")

    daemon = BrisaSessionServiceDaemon(database=db)
    daemon.credential_store = MagicMock()
    fake_creds = MagicMock()
    fake_creds.access_token = "token"
    fake_creds.refresh_token = "refresh"
    fake_creds.has_drive_scope = True
    daemon.credential_store.load_credentials.return_value = fake_creds

    # Pré-condição antes de iniciar o ciclo
    ok, target_state, msg = daemon._check_preconditions_before_cycle()
    assert ok is False
    assert target_state == STATE_ATTENTION_REQUIRED
    assert "deve estar dedicada e vazia" in msg
    assert "Escolha outra pasta vazia" in msg

    # Ao executar tentativa de ciclo único, não deve ativar ciclo e deve pausar agendamento
    daemon._run_single_sync_cycle()
    assert daemon._is_cycle_active is False
    assert daemon._state == STATE_ATTENTION_REQUIRED
    assert daemon._next_scheduled_epoch is None  # Agendamento desativado até resolução


def test_feedback_labels_distinguish_saved_pair_overcome_errors_and_new_rejections(tmp_path: Path) -> None:
    """Valida o ciclo completo de 5 passos:

    1. Rejeitar um destino inadequado.
    2. Configurar outro destino válido.
    3. Concluir a sincronização.
    4. Atualizar toda a interface sem precisar reabrir.
    5. Tentar outra escolha inválida e manter sua rejeição, apesar do sucesso anterior do par ativo.
    """
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "test_lifecycle_rejection.db")

    # 1. Destino inadequado: pasta local com arquivos para remote novo
    local_povoada = tmp_path / "local_povoada"
    local_povoada.mkdir()
    (local_povoada / "arquivo_existente.mp3").write_text("audio")

    db.set_local_sync_folder(str(local_povoada))
    db.set_remote_sync_folder(folder_id="remote_ativo", folder_name="Pasta Ativa")
    db.mark_baseline_initialized(local_folder=str(local_povoada), remote_folder_id="remote_ativo")

    win = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    fake_creds = MagicMock()
    fake_creds.access_token = "fake-token"
    fake_creds.refresh_token = "fake-refresh"
    fake_creds.has_drive_scope = True
    fake_creds.account_email = "usuario@example.com"
    win.credential_store = MagicMock()
    win.credential_store.load_credentials.return_value = fake_creds
    win.credential_store.is_vault_locked.return_value = False
    win.show()

    try:
        win.remote_folder_combo.blockSignals(True)
        win.remote_folder_combo.clear()
        win.remote_folder_combo.addItem("Pasta Ativa", ("remote_ativo", "Pasta Ativa"))
        win.remote_folder_combo.addItem("Novo Remote", ("novo_remote_id", "Novo Remote"))
        win.remote_folder_combo.setCurrentIndex(0)
        win.remote_folder_combo.blockSignals(False)

        # Passo 1: Usuário tenta selecionar Novo Remote mantendo a pasta local povoada -> Rejeitado
        win._on_remote_folder_selection_changed(1)
        assert win.remote_folder_combo.currentIndex() == 0
        assert "[REJEITADA]" in win.remote_folder_feedback_label.text()
        assert "Novo Remote" in win.remote_folder_feedback_label.text()

        # Passo 2: Configurar outro destino válido (pasta vazia dedicada)
        local_vazia = tmp_path / "local_vazia_dedicada"
        local_vazia.mkdir()

        # Configura o remote pretendido no banco e valida a nova pasta vazia
        db.set_remote_sync_folder(folder_id="novo_remote_id", folder_name="Novo Remote")
        win.folder_input.setText(str(local_vazia))
        saved = win.save_and_validate_folder()
        assert saved is True
        assert "[OK —" in win.folder_feedback_label.text()
        # O erro histórico de rejeição do remote foi superado pela configuração válida da pasta vazia!
        assert "[SELECIONADA]" in win.remote_folder_feedback_label.text()
        assert "Novo Remote" in win.remote_folder_feedback_label.text()

        # Passo 3: Concluir a sincronização (baseline estabelecida com sucesso)
        db.mark_baseline_initialized(local_folder=str(local_vazia), remote_folder_id="novo_remote_id")
        db.set_last_confirmed_sync_at("2026-10-30T20:00:00+00:00")
        (local_vazia / "musica_sincronizada.mp3").write_text("mp3 baixado")

        success_snapshot = ServiceStatusSnapshot(
            service_pid=1234,
            state=STATE_WAITING,
            state_label="AGUARDANDO",
            detail_message="Sincronização bidirecional confirmada. Aguardando próximo ciclo agendado.",
            is_cycle_active=False,
            active_rclone_pid=None,
            pending_sync_coalesced=False,
            auto_sync_paused=False,
            sync_interval_seconds=300,
            next_scheduled_sync_at="2026-10-30T20:05:00+00:00",
            backoff_attempt=0,
            backoff_seconds=0,
            last_confirmed_sync_at="2026-10-30T20:00:00+00:00",
            last_run_status="SUCCESS",
            last_error_reason=None,
            autostart_enabled=False,
            configured_pair_ready=True,
            attention_category=None,
            attention_title=None,
            attention_explanation=None,
            conflict_files_count=0,
        )

        # Passo 4: Atualizar toda a interface sem precisar reabrir
        win._apply_service_snapshot(success_snapshot)
        assert win.hero_banner.property("heroState") == "healthy"
        assert win.hero_title_label.text() == "Tudo em dia"
        assert "● Tudo em dia" in win.global_status_pill.text()
        assert "em dia" in win.overview_folder_status_pill.text()
        assert win.attention_banner_frame.isVisible() is False
        assert "[SELECIONADA]" in win.remote_folder_feedback_label.text()
        assert "[OK —" in win.folder_feedback_label.text()

        # Passo 5: Tentar outra escolha inválida e manter sua rejeição, apesar do sucesso anterior
        win.remote_folder_combo.blockSignals(True)
        win.remote_folder_combo.addItem("Terceiro Remote", ("terceiro_id", "Terceiro Remote"))
        win.remote_folder_combo.setCurrentIndex(1)  # Índice 1 é o Novo Remote (ativo salvo)
        win.remote_folder_combo.blockSignals(False)

        # Como local_vazia agora contém musica_sincronizada.mp3 e não tem baseline com terceiro_id:
        win._on_remote_folder_selection_changed(2)  # Tenta selecionar Terceiro Remote (índice 2)
        assert win.remote_folder_combo.currentIndex() == 1  # Revertido para o remote ativo (Novo Remote)
        assert "[REJEITADA]" in win.remote_folder_feedback_label.text()
        assert "Terceiro Remote" in win.remote_folder_feedback_label.text()

        # Novo snapshot de sucesso do par ativo em segundo plano NÃO deve apagar a rejeição pontual de Terceiro Remote!
        win._apply_service_snapshot(success_snapshot)
        assert "[REJEITADA]" in win.remote_folder_feedback_label.text()
        assert "Terceiro Remote" in win.remote_folder_feedback_label.text()
        # E o Hero Banner permanece refletindo o par ativo saudável
        assert win.hero_banner.property("heroState") == "healthy"
    finally:
        win.close()


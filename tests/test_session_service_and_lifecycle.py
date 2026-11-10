"""Testes automatizados da Rodada 4: Serviço de Sessão, IPC Local, Agendamento, Pausa/Retomada, Backoff e Autostart.

Valida os 7 cenários obrigatórios:
1. Fechar a janela durante um ciclo ativo e reabrir sem interromper nem duplicar a sincronização.
2. Solicitar sincronização em duas interfaces ao mesmo tempo sem duplicar serviços nem ciclos (coalescência).
3. Pausar (`PAUSANDO` -> `PAUSADO`, sem `SIGSTOP`) e reiniciar mantendo a preferência persistida.
4. Parar operação atual de forma controlada (`stop_current` via `SIGTERM`) e encerrar serviço (`shutdown_service`),
   recuperando no ciclo seguinte sem perda de arquivos nem processos órfãos.
5. Perder e recuperar conexão (`SEM CONEXÃO`), aplicando espera progressiva (exponential backoff) e recuperando.
6. Cofre indisponível (`VaultUnavailableError` -> `ATENÇÃO NECESSÁRIA` sem abrir navegador) e integridade de "Atualizado".
7. Ativar e desativar autoinício opcional na sessão via `systemd --user` (mecanismo único e reversível).
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import time
from typing import Any

from PySide6.QtWidgets import QApplication
import pytest

from brisasync.backend.rclone_engine import (
    BisyncConfig,
    BisyncExecutionResult,
    RcloneBisyncEngine,
)
from brisasync.credentials.store import (
    CredentialStore,
    OAuthCredentials,
    VaultUnavailableError,
)
from brisasync.orchestrator.sync_coordinator import (
    SyncCoordinator,
    inspect_linux_process,
)
from brisasync.service.autostart import (
    SystemdUserAutostartManager,
    competing_xdg_autostart_desktop_path,
)
from brisasync.service.daemon import (
    BrisaSessionServiceDaemon,
    ServiceAlreadyRunningError,
)
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.service.protocol import (
    STATE_ATTENTION_REQUIRED,
    STATE_OFFLINE,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_SYNCING,
    STATE_WAITING,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow


def _sha256(file_path: Path) -> str:
    h = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_local_pair_config(base_dir: Path) -> BisyncConfig:
    path1 = base_dir / "path1_local"
    path2 = base_dir / "path2_remote_sim"
    workdir = base_dir / "workdir"
    backup1 = base_dir / "backup1"
    backup2 = base_dir / "backup2"
    path1.mkdir(parents=True, exist_ok=True)
    path2.mkdir(parents=True, exist_ok=True)
    return BisyncConfig(
        path1=path1,
        path2=path2,
        workdir=workdir,
        backup_dir1=backup1,
        backup_dir2=backup2,
    )


def _get_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    return app


def test_scenario_1_close_and_reopen_window_during_active_cycle(tmp_path: Path) -> None:
    """Cenário 1: Fechar a janela durante um ciclo ativo e reabrir não interrompe nem duplica a sincronização."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    sock_path = tmp_path / "run" / "service.sock"

    # Prepara arquivo inicial e inicializa baseline
    (pair_cfg.path1 / "initial.txt").write_text("base-v1\n", encoding="utf-8")
    engine = RcloneBisyncEngine()
    coordinator = SyncCoordinator(database=db, engine=engine)
    init_res = coordinator.initialize_pair_baseline(pair_cfg)
    assert init_res.success
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id=str(pair_cfg.path2),
    )

    # Adiciona arquivo de 3MB para sincronizar com limite de banda para observar o ciclo ativo
    payload_bytes = os.urandom(3 * 1024 * 1024)
    src_file = pair_cfg.path1 / "active_window_close.bin"
    src_file.write_bytes(payload_bytes)
    expected_hash = _sha256(src_file)

    orig_run_bisync = engine.run_bisync

    def _paced_run_bisync(
        config: BisyncConfig, **kwargs: Any
    ) -> BisyncExecutionResult:
        extra = list(kwargs.get("extra_args") or [])
        extra.extend(["--bwlimit", "2M"])
        kwargs["extra_args"] = extra
        return orig_run_bisync(config, **kwargs)

    engine.run_bisync = _paced_run_bisync  # type: ignore[method-assign]

    daemon = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon.start_in_background()
    try:
        client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)

        # Abre a primeira janela e dispara sincronização via IPC
        win1 = BrisaMainWindow(database=db, ipc_client=client)
        win1.show()
        app.processEvents()

        snap, coalesced = client.sync_now()
        assert coalesced is False

        # Aguarda o ciclo entrar em execução (VERIFYING ou SYNCING)
        active_seen = False
        for _ in range(50):
            st = client.get_status()
            if st.is_cycle_active:
                active_seen = True
                break
            time.sleep(0.03)
        assert active_seen, "O ciclo de sincronização deveria estar ativo no serviço."

        # Atualiza a janela 1 e fecha-a enquanto a sincronização está ativa!
        win1.refresh_service_status_from_ipc()
        win1.close()
        app.processEvents()

        # Confirma que o serviço continua ativo após fechar a janela
        st_after_close = client.get_status()
        assert st_after_close.service_pid == os.getpid()

        # Reabre uma nova instância da janela enquanto/após o ciclo concluir
        win2 = BrisaMainWindow(database=db, ipc_client=client)
        win2.show()
        app.processEvents()

        # Aguarda conclusão do ciclo
        for _ in range(120):
            st = client.get_status()
            if not st.is_cycle_active and st.last_run_status == "SUCCESS":
                break
            time.sleep(0.05)

        win2.refresh_service_status_from_ipc()
        assert "AGUARDANDO" in win2.sync_status_label.text()
        assert "Nenhuma sincronização" not in win2.last_updated_label.text()
        win2.close()

        # Verifica que exatamente 1 ciclo incremental foi executado (sem duplicação) e o hash SHA-256 confere
        dst_file = Path(pair_cfg.path2) / "active_window_close.bin"
        assert dst_file.is_file()
        assert _sha256(dst_file) == expected_hash
        runs = db.list_recent_sync_runs(limit=10)
        inc_runs = [r for r in runs if r.operation == "incremental_bisync"]
        assert len(inc_runs) == 1
        assert inc_runs[0].status == "SUCCESS"
    finally:
        daemon.stop_and_wait()


def test_scenario_2_two_interfaces_simultaneous_sync_and_single_service_instance(
    tmp_path: Path,
) -> None:
    """Cenário 2: Duas interfaces solicitando sincronização simultaneamente não iniciam dois serviços nem ciclos concorrentes."""
    _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    sock_path = tmp_path / "run" / "service.sock"

    (pair_cfg.path1 / "doc.txt").write_text("hello\n", encoding="utf-8")
    engine = RcloneBisyncEngine()
    coordinator = SyncCoordinator(database=db, engine=engine)
    assert coordinator.initialize_pair_baseline(pair_cfg).success
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id=str(pair_cfg.path2),
    )

    (pair_cfg.path1 / "coalesce.bin").write_bytes(os.urandom(3 * 1024 * 1024))
    orig_run_bisync = engine.run_bisync

    def _paced_run_bisync(
        config: BisyncConfig, **kwargs: Any
    ) -> BisyncExecutionResult:
        extra = list(kwargs.get("extra_args") or [])
        extra.extend(["--bwlimit", "2M"])
        kwargs["extra_args"] = extra
        return orig_run_bisync(config, **kwargs)

    engine.run_bisync = _paced_run_bisync  # type: ignore[method-assign]

    daemon1 = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon1.start_in_background()
    try:
        # Tentar iniciar um segundo serviço no mesmo socket/lock deve ser bloqueado imediatamente
        daemon2 = BrisaSessionServiceDaemon(
            database=db,
            socket_path=sock_path,
            local_pair_config=pair_cfg,
        )
        with pytest.raises(ServiceAlreadyRunningError):
            daemon2.start_in_background()

        # Duas instâncias de cliente IPC (representando duas janelas abertas)
        client_a = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)
        client_b = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)

        # Cliente A inicia sincronização
        _, coalesced_first = client_a.sync_now()
        assert coalesced_first is False

        # Aguarda o ciclo ficar ativo
        for _ in range(50):
            if client_a.get_status().is_cycle_active:
                break
            time.sleep(0.03)

        # Enquanto o ciclo está ativo, Cliente A e Cliente B disparam 4 solicitações simultâneas
        _, coal_1 = client_b.sync_now()
        _, coal_2 = client_a.sync_now()
        _, coal_3 = client_b.sync_now()
        assert coal_1 is True
        assert coal_2 is True
        assert coal_3 is True
        assert client_b.get_status().pending_sync_coalesced is True

        # Aguarda todos os ciclos terminarem (o ciclo ativo + no máximo 1 ciclo coalescido)
        for _ in range(160):
            st = client_a.get_status()
            if not st.is_cycle_active and not st.pending_sync_coalesced:
                break
            time.sleep(0.05)

        runs = [
            r
            for r in db.list_recent_sync_runs(limit=10)
            if r.operation == "incremental_bisync"
        ]
        # Os 3 pedidos extras foram agrupados em apenas 1 ciclo adicional (total = 2, nunca 4)
        assert len(runs) == 2
        assert all(r.status == "SUCCESS" for r in runs)
    finally:
        daemon1.stop_and_wait()


def test_scenario_3_pause_pausing_distinction_and_persisted_preference_across_restart(
    tmp_path: Path,
) -> None:
    """Cenário 3: Diferencia PAUSANDO de PAUSADO (sem SIGSTOP) e persiste a preferência de pausa ao reiniciar."""
    _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    sock_path = tmp_path / "run" / "service.sock"

    (pair_cfg.path1 / "f1.txt").write_text("123\n", encoding="utf-8")
    engine = RcloneBisyncEngine()
    coordinator = SyncCoordinator(database=db, engine=engine)
    assert coordinator.initialize_pair_baseline(pair_cfg).success
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id=str(pair_cfg.path2),
    )

    (pair_cfg.path1 / "pause_test.bin").write_bytes(os.urandom(3 * 1024 * 1024))
    orig_run_bisync = engine.run_bisync

    def _paced_run_bisync(
        config: BisyncConfig, **kwargs: Any
    ) -> BisyncExecutionResult:
        extra = list(kwargs.get("extra_args") or [])
        extra.extend(["--bwlimit", "2M"])
        kwargs["extra_args"] = extra
        return orig_run_bisync(config, **kwargs)

    engine.run_bisync = _paced_run_bisync  # type: ignore[method-assign]

    daemon = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)
    try:
        client.sync_now()
        rclone_pid = None
        for _ in range(60):
            st = client.get_status()
            if st.is_cycle_active and st.active_rclone_pid is not None:
                rclone_pid = st.active_rclone_pid
                break
            time.sleep(0.03)
        assert rclone_pid is not None

        # Solicita pausa durante o ciclo ativo: deve entrar em PAUSANDO (PAUSING) sem usar SIGSTOP
        pause_snap = client.pause()
        assert pause_snap.state == STATE_PAUSING
        assert pause_snap.state_label == "PAUSANDO"
        assert pause_snap.auto_sync_paused is True
        assert db.is_auto_sync_paused() is True

        # Verifica no /proc/<pid>/stat que o processo rclone NÃO foi colocado em estado 'T' (SIGSTOP)
        proc_ident = inspect_linux_process(rclone_pid)
        if proc_ident is not None:
            assert proc_ident.state != "T", "Proibido usar SIGSTOP como mecanismo de pausa!"

        # Aguarda o ciclo ativo concluir normalmente e transicionar para PAUSADO (PAUSED)
        for _ in range(120):
            st = client.get_status()
            if not st.is_cycle_active:
                break
            time.sleep(0.05)

        final_snap = client.get_status()
        assert final_snap.state == STATE_PAUSED
        assert final_snap.state_label == "PAUSADO"
        assert final_snap.next_scheduled_sync_at is None
    finally:
        daemon.stop_and_wait()

    # Reinicia o serviço e a interface: deve continuar PAUSADO sem retomar contra a escolha do usuário
    daemon_restarted = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon_restarted.start_in_background()
    try:
        restarted_snap = client.get_status()
        assert restarted_snap.state == STATE_PAUSED
        assert restarted_snap.state_label == "PAUSADO"
        assert restarted_snap.auto_sync_paused is True
        assert restarted_snap.next_scheduled_sync_at is None

        win = BrisaMainWindow(database=db, ipc_client=client)
        win.refresh_service_status_from_ipc()
        assert "[PAUSADO]" in win.sync_status_label.text()
        assert win.pause_sync_button.isEnabled() is False
        assert win.resume_sync_button.isEnabled() is True
        win.close()

        # Agora retoma explicitamente
        resumed_snap = client.resume()
        assert resumed_snap.auto_sync_paused is False
        assert db.is_auto_sync_paused() is False
    finally:
        daemon_restarted.stop_and_wait()


def test_scenario_4_controlled_stop_and_service_shutdown_recovery_no_orphans(
    tmp_path: Path,
) -> None:
    """Cenário 4: Parar operação atual (`stop_current` via SIGTERM) e recuperar no próximo ciclo sem perda de arquivos nem processos órfãos."""
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    sock_path = tmp_path / "run" / "service.sock"

    (pair_cfg.path1 / "keep.txt").write_text("keep-me\n", encoding="utf-8")
    engine = RcloneBisyncEngine()
    coordinator = SyncCoordinator(database=db, engine=engine)
    assert coordinator.initialize_pair_baseline(pair_cfg).success
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id=str(pair_cfg.path2),
    )
    confirmed_before = db.get_last_confirmed_sync_at()
    assert confirmed_before is not None

    # Cria arquivo grande (8 MB) com bwlimit de 1M para dar tempo de enviar stop_current (SIGTERM)
    big_file = pair_cfg.path1 / "stoppable_payload.bin"
    big_file.write_bytes(os.urandom(8 * 1024 * 1024))
    expected_big_hash = _sha256(big_file)

    orig_run_bisync = engine.run_bisync

    def _slow_run_bisync(
        config: BisyncConfig, **kwargs: Any
    ) -> BisyncExecutionResult:
        extra = list(kwargs.get("extra_args") or [])
        extra.extend(["--bwlimit", "1M"])
        kwargs["extra_args"] = extra
        return orig_run_bisync(config, **kwargs)

    engine.run_bisync = _slow_run_bisync  # type: ignore[method-assign]

    daemon = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)
    try:
        # Pausa agendamento automático para controlar cada ciclo manualmente
        client.pause()
        client.sync_now()

        active_pid = None
        for _ in range(80):
            st = client.get_status()
            if st.is_cycle_active and st.active_rclone_pid is not None:
                active_pid = st.active_rclone_pid
                break
            time.sleep(0.04)
        assert active_pid is not None

        # Solicita parada controlada da operação atual (SIGTERM único ao rclone bisync)
        client.stop_current()

        for _ in range(100):
            st = client.get_status()
            if not st.is_cycle_active:
                break
            time.sleep(0.05)

        st_after_stop = client.get_status()
        assert st_after_stop.last_run_status == "STOPPED_BY_USER"
        # A parada controlada NÃO pode ter atualizado last_confirmed_sync_at ("Atualizado")
        assert db.get_last_confirmed_sync_at() == confirmed_before
        # Confirma que o processo rclone encerrou (zero processos órfãos)
        assert inspect_linux_process(active_pid) is None

        # Encerra o serviço via IPC ("shutdown_service")
        client.shutdown_service()
        time.sleep(0.3)
    finally:
        daemon.stop_and_wait()

    # Restaura velocidade normal e inicia novo serviço para reconciliar/recuperar (--recover)
    engine.run_bisync = orig_run_bisync  # type: ignore[method-assign]
    daemon_rec = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon_rec.start_in_background()
    try:
        client.sync_now()
        for _ in range(100):
            st = client.get_status()
            if not st.is_cycle_active and st.last_run_status == "SUCCESS":
                break
            time.sleep(0.05)

        st_recovered = client.get_status()
        assert st_recovered.last_run_status == "SUCCESS"
        assert db.get_last_confirmed_sync_at() != confirmed_before

        dst_big = Path(pair_cfg.path2) / "stoppable_payload.bin"
        assert dst_big.is_file()
        assert _sha256(dst_big) == expected_big_hash
        assert _sha256(Path(pair_cfg.path2) / "keep.txt") == _sha256(
            pair_cfg.path1 / "keep.txt"
        )
    finally:
        daemon_rec.stop_and_wait()


def test_scenario_5_connection_loss_progressive_backoff_and_recovery(
    tmp_path: Path,
) -> None:
    """Cenário 5: Perda de conexão aplica espera progressiva (SEM CONEXÃO) e recupera quando a conexão volta."""
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    sock_path = tmp_path / "run" / "service.sock"

    (pair_cfg.path1 / "net.txt").write_text("online-v1\n", encoding="utf-8")
    engine = RcloneBisyncEngine()
    coordinator = SyncCoordinator(database=db, engine=engine)
    assert coordinator.initialize_pair_baseline(pair_cfg).success
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id=str(pair_cfg.path2),
    )
    confirmed_initial = db.get_last_confirmed_sync_at()

    # Simula 2 falhas transitórias de rede seguidas de recuperação na 3ª tentativa
    attempt_counter = {"count": 0}
    orig_run_bisync = engine.run_bisync

    def _flaky_network_run_bisync(
        config: BisyncConfig, **kwargs: Any
    ) -> BisyncExecutionResult:
        attempt_counter["count"] += 1
        if attempt_counter["count"] <= 2:
            return BisyncExecutionResult(
                success=False,
                exit_code=1,
                command=["rclone", "bisync"],
                stdout="",
                stderr="ERROR : dial tcp: lookup www.googleapis.com: i/o timeout",
                was_resync=False,
                error_reason="dial tcp: lookup www.googleapis.com: i/o timeout",
            )
        return orig_run_bisync(config, **kwargs)

    engine.run_bisync = _flaky_network_run_bisync  # type: ignore[method-assign]
    (pair_cfg.path1 / "after_reconnect.txt").write_text(
        "reconnected-ok\n", encoding="utf-8"
    )

    daemon = BrisaSessionServiceDaemon(
        database=db,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
        base_backoff_seconds=4,
        max_backoff_seconds=60,
    )
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)
    try:
        # 1ª falha de rede -> estado SEM CONEXÃO, backoff_attempt=1, backoff_seconds=4s
        client.sync_now()
        for _ in range(50):
            st = client.get_status()
            if not st.is_cycle_active and st.backoff_attempt == 1:
                break
            time.sleep(0.04)

        st1 = client.get_status()
        assert st1.state == STATE_OFFLINE
        assert st1.state_label == "SEM CONEXÃO"
        assert st1.backoff_attempt == 1
        assert st1.backoff_seconds == 4
        assert db.get_last_confirmed_sync_at() == confirmed_initial

        # 2ª falha de rede -> estado SEM CONEXÃO, backoff_attempt=2, backoff_seconds=8s (dobrou!)
        client.sync_now()
        for _ in range(50):
            st = client.get_status()
            if not st.is_cycle_active and st.backoff_attempt == 2:
                break
            time.sleep(0.04)

        st2 = client.get_status()
        assert st2.state == STATE_OFFLINE
        assert st2.state_label == "SEM CONEXÃO"
        assert st2.backoff_attempt == 2
        assert st2.backoff_seconds == 8
        assert db.get_last_confirmed_sync_at() == confirmed_initial

        # 3ª tentativa: conexão restabelecida -> sincroniza com sucesso e zera backoff
        client.sync_now()
        for _ in range(80):
            st = client.get_status()
            if not st.is_cycle_active and st.last_run_status == "SUCCESS":
                break
            time.sleep(0.05)

        st3 = client.get_status()
        assert st3.state == STATE_WAITING
        assert st3.state_label == "AGUARDANDO"
        assert st3.backoff_attempt == 0
        assert st3.backoff_seconds == 0
        assert db.get_last_confirmed_sync_at() != confirmed_initial
        assert (Path(pair_cfg.path2) / "after_reconnect.txt").read_text(
            encoding="utf-8"
        ) == "reconnected-ok\n"
    finally:
        daemon.stop_and_wait()


def test_scenario_6_vault_unavailable_waits_without_browser_prompt(
    tmp_path: Path,
) -> None:
    """Cenário 6: Cofre indisponível transiciona para ATENÇÃO NECESSÁRIA sem abrir navegador nem marcar 'Atualizado'."""
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    local_dir = tmp_path / "local_sync"
    local_dir.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(local_dir)
    db.set_remote_sync_folder(
        folder_id="1E5HsgHDPPXFVdFhqRhZGlI88fGdMND22",
        folder_name="BrisaSync-Teste-Automatico",
    )

    class _LockedCredentialStore(CredentialStore):
        @classmethod
        def is_vault_locked(cls) -> bool:
            return True

        def load_credentials(self, interactive: bool = False) -> OAuthCredentials | None:
            raise VaultUnavailableError(
                "Cofre de segredos da sessão bloqueado (secret-tool/kwallet inacessível)."
            )

    locked_store = _LockedCredentialStore(lock_path=tmp_path / "cred.lock")
    sock_path = tmp_path / "run" / "service.sock"

    daemon = BrisaSessionServiceDaemon(
        database=db,
        credential_store=locked_store,
        socket_path=sock_path,
    )
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)
    try:
        client.sync_now()
        for _ in range(50):
            st = client.get_status()
            if st.state == STATE_ATTENTION_REQUIRED:
                break
            time.sleep(0.04)

        st = client.get_status()
        assert st.state == STATE_ATTENTION_REQUIRED
        assert st.state_label == "ATENÇÃO NECESSÁRIA"
        assert "Cofre da sessão bloqueado ou indisponível" in st.detail_message
        assert "sem abrir navegador" in st.detail_message
        assert st.last_confirmed_sync_at is None
    finally:
        daemon.stop_and_wait()


def test_scenario_7_systemd_user_autostart_enable_and_disable_reversible(
    tmp_path: Path,
) -> None:
    """Cenário 7: Ativar e desativar autoinício via systemd --user (mecanismo único e reversível)."""
    # 7a. Verifica renderização e ciclo completo em diretório isolado + validação real no systemd --user da sessão
    isolated_unit_dir = tmp_path / "systemd_user"
    mgr_isolated = SystemdUserAutostartManager(
        unit_dir=isolated_unit_dir,
        db_path=tmp_path / "brisasync.db",
        run_systemctl=False,
    )
    assert mgr_isolated.is_enabled() is False
    unit_file = mgr_isolated.enable()
    assert unit_file.is_file()
    content = unit_file.read_text(encoding="utf-8")
    assert "--service" in content
    assert "WantedBy=default.target" in content
    assert mgr_isolated.is_enabled() is True
    assert not mgr_isolated.has_competing_xdg_autostart()

    mgr_isolated.disable()
    assert not unit_file.exists()
    assert mgr_isolated.is_enabled() is False

    # 7b. Validação real contra o `systemd --user` da sessão Linux atual (restaurando estado ao final)
    real_mgr = SystemdUserAutostartManager()
    was_originally_enabled = real_mgr.is_enabled()
    try:
        real_mgr.enable()
        assert real_mgr.is_enabled() is True
        assert real_mgr.unit_path.is_file()
        assert not real_mgr.has_competing_xdg_autostart()

        real_mgr.disable()
        assert real_mgr.is_enabled() is False
        assert not real_mgr.unit_path.exists()
    finally:
        if was_originally_enabled:
            real_mgr.enable()
        else:
            real_mgr.disable()
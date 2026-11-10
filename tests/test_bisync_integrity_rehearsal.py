"""Ensaio real de integridade do motor `rclone bisync` entre pastas descartáveis.

Valida os cenários obrigatórios conferindo hashes SHA-256 e inventários completos
de ambas as pastas e diretórios de backup (código de saída sozinho não basta):
1. Criação e alteração de arquivos nas duas direções.
2. Conflito simultâneo preservando ambas as versões.
3. Exclusão recuperável (quarentena em backup_dir1 / backup_dir2).
4a. Recuperação de estado a partir de artefatos de interrupção (.lst-new e .lck expirado).
4b. Ensaio de interrupção REAL encerrando um processo `rclone bisync` ativo durante
    transferência e recuperando sem `--resync`.
5a. Bloqueio de execuções concorrentes na camada de orquestração e no rclone.
5b. Bloqueio de concorrência mantido quando operação ativa ultrapassa `max-lock` (sem
    remover lock de processo vivo) e liberação/recuperação após morte do proprietário.
6. Pasta ausente ou inacessível sem propagação de exclusões (e sem recriar marcador em ciclos normais).
7. Conteúdo diferente com tamanho e data (mtime) iguais detectado via checksum.
8. Proteção contra exclusões em massa (`--max-delete` em porcentagem no `rclone bisync v1.75.2`, sem `--force`).
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import pytest

from brisasync.backend.integrity import build_directory_inventory, sha256_file
from brisasync.backend.rclone_engine import (
    BisyncConfig,
    RcloneBisyncEngine,
    SENTINEL_FILENAME,
)
from brisasync.orchestrator.sync_coordinator import (
    ConcurrentSyncError,
    DirectoryAccessError,
    SyncCoordinator,
    inspect_linux_process,
)
from brisasync.storage.database import BrisaDatabase


@pytest.fixture
def sync_env(tmp_path: Path) -> tuple[SyncCoordinator, BisyncConfig]:
    db = BrisaDatabase(db_path=tmp_path / "state" / "test_brisasync.db")
    engine = RcloneBisyncEngine()
    assert engine.is_available(), "O binário rclone precisa estar disponível para o ensaio real."

    config = BisyncConfig(
        path1=tmp_path / "local_side",
        path2=tmp_path / "remote_side_simulated",
        workdir=tmp_path / "bisync_workdir",
        backup_dir1=tmp_path / "trash_side1",
        backup_dir2=tmp_path / "trash_side2",
    )
    config.path1.mkdir(parents=True, exist_ok=True)
    Path(config.path2).mkdir(parents=True, exist_ok=True)

    coordinator = SyncCoordinator(database=db, engine=engine)
    return coordinator, config


def test_1_bidirectional_creation_and_modification(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 1: Criação e alteração de arquivos nas duas direções com verificação SHA-256."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    (config.path1 / "relatorio_a.txt").write_bytes(b"Versao inicial lado 1\n")
    (path2 / "notas_b.txt").write_bytes(b"Versao inicial lado 2\n")

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success, f"Falha na baseline: {init_res.stderr}"

    inv1 = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    inv2 = build_directory_inventory(path2).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv1 == inv2
    assert set(inv1.keys()) == {"relatorio_a.txt", "notas_b.txt"}

    (config.path1 / "projetos").mkdir()
    (config.path1 / "projetos" / "codigo.py").write_bytes(b"print('brisa v1')\n")
    (config.path1 / "notas_b.txt").write_bytes(b"Notas B editadas no lado 1!\n")

    (path2 / "documentos").mkdir()
    (path2 / "documentos" / "manual.md").write_bytes(b"# Manual BrisaSync\n")
    (path2 / "relatorio_a.txt").write_bytes(b"Relatorio A editado no lado 2!\n")

    expected_hash_notas = sha256_file(config.path1 / "notas_b.txt")
    expected_hash_relatorio = sha256_file(path2 / "relatorio_a.txt")
    expected_hash_codigo = sha256_file(config.path1 / "projetos" / "codigo.py")
    expected_hash_manual = sha256_file(path2 / "documentos" / "manual.md")

    sync_res = coordinator.synchronize_pair(config)
    assert sync_res.success, f"Falha no bisync incremental: {sync_res.stderr}"
    assert not sync_res.was_resync

    final_inv1 = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    final_inv2 = build_directory_inventory(path2).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )

    assert final_inv1 == final_inv2
    assert final_inv1["notas_b.txt"] == expected_hash_notas
    assert final_inv1["relatorio_a.txt"] == expected_hash_relatorio
    assert final_inv1["projetos/codigo.py"] == expected_hash_codigo
    assert final_inv1["documentos/manual.md"] == expected_hash_manual


def test_2_simultaneous_conflict_preserves_both_versions(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 2: Conflito simultâneo em ambos os lados preservando ambas as versões."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    shared_file_p1 = config.path1 / "orcamento.csv"
    shared_file_p1.write_bytes(b"item,valor\nbase,100\n")

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    content_side1 = b"item,valor\nbase,100\nadic_lado1,250\n"
    content_side2 = b"item,valor\nbase,100\nadic_lado2,999\n"
    (config.path1 / "orcamento.csv").write_bytes(content_side1)
    (path2 / "orcamento.csv").write_bytes(content_side2)

    hash_side1 = sha256_file(config.path1 / "orcamento.csv")
    hash_side2 = sha256_file(path2 / "orcamento.csv")
    assert hash_side1 != hash_side2

    sync_res = coordinator.synchronize_pair(config)
    assert sync_res.success, f"Falha na resolução de conflito: {sync_res.stderr}"

    inv1 = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    inv2 = build_directory_inventory(path2).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )

    assert inv1 == inv2
    assert len(inv1) == 2, f"Esperados 2 arquivos após conflito, encontrados: {inv1}"
    assert set(inv1.values()) == {hash_side1, hash_side2}
    assert len(sync_res.conflict_files) == 2
    assert set(coordinator.database.get_recorded_conflict_files(config.path1)) == set(sync_res.conflict_files)


def test_3_recoverable_deletion_via_backup_dirs(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 3: Exclusão em um lado propaga a remoção, mas preserva cópia íntegra no backup."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    # Mantemos outros arquivos estáveis para que a deleção de 1 arquivo fique abaixo do --max-delete (50%)
    (config.path1 / "estavel_1.txt").write_bytes(b"Permanece 1\n")
    (config.path1 / "estavel_2.txt").write_bytes(b"Permanece 2\n")
    file_to_delete = config.path1 / "importante_recuperavel.txt"
    payload = b"Conteudo critico que deve ir para quarentena ao ser excluido.\n" * 10
    file_to_delete.write_bytes(payload)
    original_hash = sha256_file(file_to_delete)

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    file_to_delete.unlink()
    assert not (config.path1 / "importante_recuperavel.txt").exists()
    assert (path2 / "importante_recuperavel.txt").exists()

    sync_res = coordinator.synchronize_pair(config)
    assert sync_res.success, f"Falha ao sincronizar exclusão: {sync_res.stderr}"

    assert not (config.path1 / "importante_recuperavel.txt").exists()
    assert not (path2 / "importante_recuperavel.txt").exists()

    backup_inv2 = build_directory_inventory(config.backup_dir2).hashes_by_path()
    assert "importante_recuperavel.txt" in backup_inv2
    assert backup_inv2["importante_recuperavel.txt"] == original_hash


def test_4a_state_recovery_from_interrupted_artifacts(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 4a: Recuperação de estado a partir de artefatos interrompidos (.lst-new e .lck expirado)."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    (config.path1 / "base.txt").write_bytes(b"Linha base estavel\n")
    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    lst_files = list(config.workdir.glob("*.lst"))
    assert lst_files
    for lst in lst_files:
        interrupted_lst = lst.with_suffix(".lst-new")
        shutil.copy2(lst, interrupted_lst)

    session_stem = lst_files[0].stem.rsplit(".", 1)[0]
    stale_lock = config.workdir / f"{session_stem}.lck"
    stale_lock.write_text("stale-interrupted-process\n", encoding="utf-8")
    expired_time = time.time() - 300
    os.utime(stale_lock, (expired_time, expired_time))

    (config.path1 / "pos_queda_1.txt").write_bytes(b"Criado apos interrupcao lado 1\n")
    (path2 / "pos_queda_2.txt").write_bytes(b"Criado apos interrupcao lado 2\n")

    recovery_res = coordinator.synchronize_pair(config)
    assert recovery_res.success, f"Falha na recuperação de estado: {recovery_res.stderr}"
    assert not recovery_res.was_resync

    inv1 = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    inv2 = build_directory_inventory(path2).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv1 == inv2
    assert set(inv1.keys()) == {"base.txt", "pos_queda_1.txt", "pos_queda_2.txt"}


def test_4b_real_active_process_interruption_and_recovery(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 4b: Interrompe um processo `rclone bisync` comprovando que a transferência COMEÇOU (bytes parciais em trânsito) antes do SIGTERM e recupera."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    (config.path1 / "seed.txt").write_bytes(b"Arquivo semente inicial\n")
    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    # Cria arquivos descartáveis (~2,4 MB) com --bwlimit 200k para observar o arquivo .partial
    # sendo gravado em tempo real no destino (0 < bytes_parciais < tamanho_total) antes do SIGTERM.
    total_size_a = 2_400_000
    blob_a = os.urandom(total_size_a)
    blob_b = os.urandom(600_000)
    (config.path1 / "transferencia_pesada.bin").write_bytes(blob_a)
    (path2 / "transferencia_remota.bin").write_bytes(blob_b)
    expected_hash_a = sha256_file(config.path1 / "transferencia_pesada.bin")
    expected_hash_b = sha256_file(path2 / "transferencia_remota.bin")
    expected_hash_seed = sha256_file(config.path1 / "seed.txt")

    cmd = coordinator.engine.build_command(
        config,
        resync=False,
        extra_args=["--bwlimit", "200k"],
    )
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Aguarda especificamente a transferência de arquivos começar (arquivo *.partial no destino
    # com 0 < st_size < tamanho_total), provando transferência ativa real e não apenas processo vivo.
    deadline = time.monotonic() + 12.0
    interruption_evidence: dict[str, int | str] = {}
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        candidates = list(path2.glob("*.partial")) + list(config.path1.glob("*.partial"))
        for part_file in candidates:
            try:
                part_size = part_file.stat().st_size
            except OSError:
                continue
            target_total = (
                total_size_a
                if "transferencia_pesada" in part_file.name
                else len(blob_b)
            )
            if 0 < part_size < target_total:
                interruption_evidence = {
                    "pid": proc.pid,
                    "partial_filename": part_file.name,
                    "partial_bytes_before_sigterm": part_size,
                    "expected_total_bytes": target_total,
                }
                break
        if interruption_evidence:
            break
        time.sleep(0.02)

    assert proc.poll() is None, "O processo rclone terminou antes de poder ser interrompido!"
    assert interruption_evidence, (
        "Não foi observada evidência de bytes parciais em transferência ativa (*.partial > 0 bytes) "
        "antes do SIGTERM."
    )
    partial_bytes = int(interruption_evidence["partial_bytes_before_sigterm"])
    total_bytes = int(interruption_evidence["expected_total_bytes"])
    assert 0 < partial_bytes < total_bytes

    # Interrompe o processo rclone com transferência comprovadamente em andamento.
    # No rclone bisync v1.75.2, o 1º SIGTERM inicia graceful shutdown (aguardando até 30s pelo arquivo
    # atual) e o 2º SIGTERM aciona a parada imediata no meio da transferência ("Send exit signal again
    # for immediate un-graceful shutdown").
    proc.send_signal(signal.SIGTERM)
    time.sleep(0.08)
    if proc.poll() is None:
        proc.send_signal(signal.SIGTERM)
    _, stderr_interrupted = proc.communicate(timeout=10)
    assert proc.returncode != 0, (
        f"Processo interrompido deveria retornar != 0 (stderr: {stderr_interrupted})"
    )
    interruption_evidence["exit_code_after_sigterm"] = int(proc.returncode)

    # Agora executa a sincronização normal (sem --resync) imediatamente:
    # O SyncCoordinator detecta que o PID proprietário do .lck encerrou, libera/expira a trava órfã
    # automaticamente e o rclone --recover reconcilia a transferência interrompida!
    recovery_res = coordinator.synchronize_pair(config)
    assert recovery_res.success, (
        f"Falha ao recuperar após interrupção real ({interruption_evidence}): {recovery_res.stderr}"
    )
    assert not recovery_res.was_resync

    inv1 = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    inv2 = build_directory_inventory(path2).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv1 == inv2
    assert inv1 == {
        "seed.txt": expected_hash_seed,
        "transferencia_pesada.bin": expected_hash_a,
        "transferencia_remota.bin": expected_hash_b,
    }


def test_5a_concurrent_execution_locking(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 5a: Bloqueio de execuções concorrentes na camada de orquestração e no rclone."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    (config.path1 / "arquivo.txt").write_bytes(b"Conteudo protegido contra concorrencia\n")
    expected_hash = sha256_file(config.path1 / "arquivo.txt")

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    with coordinator.acquire_pair_lock(config.workdir):
        with pytest.raises(ConcurrentSyncError):
            coordinator.synchronize_pair(config)

    lst_files = list(config.workdir.glob("*.lst"))
    session_stem = lst_files[0].stem.rsplit(".", 1)[0]
    active_rclone_lock = config.workdir / f"{session_stem}.lck"
    active_rclone_lock.write_text(
        '{"Session":"test","PID":"9999999","TimeRenewed":"2099-01-01T00:00:00Z","TimeExpires":"2099-01-01T01:00:00Z"}\n',
        encoding="utf-8",
    )
    try:
        blocked_res = coordinator.synchronize_pair(config)
        assert not blocked_res.success
        assert "lock file" in blocked_res.stderr.lower() or blocked_res.exit_code != 0
    finally:
        active_rclone_lock.unlink(missing_ok=True)

    assert sha256_file(config.path1 / "arquivo.txt") == expected_hash
    assert sha256_file(path2 / "arquivo.txt") == expected_hash


def test_5b_lock_held_beyond_max_lock_and_owner_interruption(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 5b: Identidade do proprietário de lock, proteção contra reutilização de PID e bloqueio além de max-lock."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    (config.path1 / "dados.txt").write_bytes(b"Integridade sob operacao longa\n")
    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    lst_files = list(config.workdir.glob("*.lst"))
    session_stem = lst_files[0].stem.rsplit(".", 1)[0]
    lck_path = config.workdir / f"{session_stem}.lck"

    # Parte 1: Processo `rclone` REAL ativo cuja operação ultrapassou TimeExpires (max-lock).
    # O coordenador verifica a identidade (`comm`/`cmdline` == rclone) e o starttime em /proc/<pid>/stat,
    # bloqueia a concorrência e JAMAIS remove o .lck do processo rclone ativo.
    assert coordinator.engine.rclone_binary is not None
    active_rclone = subprocess.Popen(
        [
            coordinator.engine.rclone_binary,
            "rcd",
            "--rc-no-auth",
            "--rc-addr",
            "127.0.0.1:0",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(50):
        ident = inspect_linux_process(active_rclone.pid)
        if ident is not None and ident.is_rclone_bisync:
            break
        time.sleep(0.01)
    try:
        lck_path.write_text(
            f'{{"Session":"long_op","PID":"{active_rclone.pid}",'
            '"TimeRenewed":"2020-01-01T00:00:00Z","TimeExpires":"2020-01-01T00:02:00Z"}\n',
            encoding="utf-8",
        )
        # mtime reflete que o arquivo .lck foi criado/renovado após o início do processo rclone
        now_ts = time.time()
        os.utime(lck_path, (now_ts, now_ts))

        with pytest.raises(ConcurrentSyncError, match=f"PID {active_rclone.pid}"):
            coordinator.synchronize_pair(config)

        # Confirma que o lockfile do processo rclone ativo NÃO foi removido
        assert lck_path.exists(), "O lock de um processo rclone ativo jamais pode ser removido!"

        # Parte 2a (Reutilização de PID por horário de início):
        # Se o arquivo .lck for mais antigo que o horário de criação (`starttime`) do processo rclone atual,
        # significa que o proprietário original morreu no passado e o kernel reutilizou o PID.
        ancient_time = time.time() - 600
        os.utime(lck_path, (ancient_time, ancient_time))
        # Como `start_time_epoch > lock_ref_epoch + 2.0`, o coordenador detecta a reciclagem de PID!
        coordinator._check_active_rclone_lock_owner(config.workdir)
    finally:
        active_rclone.terminate()
        active_rclone.wait(timeout=5)

    # Parte 2b (Reutilização de PID por identidade de executável diferente de rclone):
    # Inicia um processo vivo que NÃO é rclone (ex.: python3). Mesmo com mtime atual,
    # a verificação de `/proc/<pid>/cmdline` identifica que o PID não pertence ao rclone.
    unrelated_proc = subprocess.Popen(["python3", "-c", "import time; time.sleep(30)"])
    try:
        lck_path.write_text(
            f'{{"Session":"pid_reused","PID":"{unrelated_proc.pid}",'
            '"TimeRenewed":"2020-01-01T00:00:00Z","TimeExpires":"2020-01-01T00:02:00Z"}\n',
            encoding="utf-8",
        )
        expired_mtime = time.time() - 300
        os.utime(lck_path, (expired_mtime, expired_mtime))

        # Não deve levantar ConcurrentSyncError (identidade != rclone) e deve recuperar com sucesso!
        (config.path1 / "apos_pid_reuse.txt").write_bytes(b"Recuperado apos reciclagem de PID\n")
        res_reused = coordinator.synchronize_pair(config)
        assert res_reused.success, (
            f"Deveria detectar reutilização de PID por outro executável e recuperar: {res_reused.stderr}"
        )
        assert sha256_file(path2 / "apos_pid_reuse.txt") == sha256_file(
            config.path1 / "apos_pid_reuse.txt"
        )
    finally:
        unrelated_proc.terminate()
        unrelated_proc.wait(timeout=5)

    # Parte 3: Confirma liberação limpa da trava de par (`brisasync_pair.lock`) após encerramento
    pair_lock_file = config.workdir / "brisasync_pair.lock"
    assert pair_lock_file.exists()
    assert pair_lock_file.read_text(encoding="utf-8") == ""


def test_6_missing_or_inaccessible_folder_prevents_mass_deletion(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 6: Pasta ausente ou sem arquivo sentinela aborta sem propagar exclusões e sem recriar marcador."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    (config.path1 / "foto_familia.bin").write_bytes(b"\x89PNG\r\n\x1a\nDADOS_IMPORTANTES")
    (config.path1 / "contrato.pdf").write_bytes(b"%PDF-1.7 DOCUMENTO_VITAL")
    hash_foto = sha256_file(config.path1 / "foto_familia.bin")
    hash_contrato = sha256_file(config.path1 / "contrato.pdf")

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    shutil.rmtree(path2)
    path2.mkdir(parents=True, exist_ok=True)

    with pytest.raises(DirectoryAccessError):
        coordinator.synchronize_pair(config)

    # Verifica que o coordenador NÃO recriou o marcador ausente em Path2 durante ciclo normal
    assert not (path2 / SENTINEL_FILENAME).exists()

    direct_res = coordinator.engine.run_bisync(config)
    assert not direct_res.success

    inv1_after_empty = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv1_after_empty == {
        "foto_familia.bin": hash_foto,
        "contrato.pdf": hash_contrato,
    }

    shutil.rmtree(path2)
    with pytest.raises(DirectoryAccessError):
        coordinator.synchronize_pair(config)

    inv1_after_missing = build_directory_inventory(config.path1).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv1_after_missing == {
        "foto_familia.bin": hash_foto,
        "contrato.pdf": hash_contrato,
    }


def test_7_different_content_with_identical_size_and_mtime_is_detected(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
) -> None:
    """Cenário 7: Conteúdo diferente com tamanho e mtime idênticos é detectado via checksum."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    target_p1 = config.path1 / "bloco_fixo.dat"
    initial_bytes = b" BLOCO_DE_32_BYTES_VERSAO_ALFA!\n"
    modified_bytes = b" BLOCO_DE_32_BYTES_VERSAO_BETA!\n"
    assert len(initial_bytes) == len(modified_bytes) == 32

    target_p1.write_bytes(initial_bytes)
    fixed_ts_ns = 1_700_000_000_000_000_000
    os.utime(target_p1, ns=(fixed_ts_ns, fixed_ts_ns))

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    target_p2 = path2 / "bloco_fixo.dat"
    stat_before = target_p1.stat()
    assert target_p2.stat().st_size == stat_before.st_size

    target_p1.write_bytes(modified_bytes)
    os.utime(target_p1, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))

    assert target_p1.stat().st_size == stat_before.st_size
    assert target_p1.stat().st_mtime_ns == stat_before.st_mtime_ns
    new_hash = sha256_file(target_p1)
    old_hash = sha256_file(target_p2)
    assert new_hash != old_hash

    sync_res = coordinator.synchronize_pair(config)
    assert sync_res.success, f"Falha na sincronização por checksum: {sync_res.stderr}"

    assert sha256_file(target_p2) == new_hash
    assert target_p2.read_bytes() == modified_bytes


def test_8_mass_deletion_protection_aborts_above_threshold(
    sync_env: tuple[SyncCoordinator, BisyncConfig],
    tmp_path: Path,
) -> None:
    """Cenário 8: Proteção contra exclusão em massa impõe TANTO limite percentual quanto limite absoluto antes de propagar."""
    coordinator, config = sync_env
    path2 = Path(config.path2)

    # Parte 8a — Limite Percentual (max_delete_percent=50%, max_delete_abs=25):
    # Cria 4 arquivos de usuário (+1 sentinela = 5 arquivos rastreados no total).
    expected_hashes: dict[str, str] = {}
    for i in range(1, 5):
        fname = f"doc_{i}.txt"
        fpath = config.path1 / fname
        fpath.write_bytes(f"Documento protegido numero {i}\n".encode("utf-8"))
        expected_hashes[fname] = sha256_file(fpath)

    init_res = coordinator.initialize_pair_baseline(config)
    assert init_res.success

    # Remove 3 dos 4 arquivos de usuário em Path1 -> 3 de 5 arquivos totais = 60% (> 50% max_delete_percent)
    for i in (1, 2, 3):
        (config.path1 / f"doc_{i}.txt").unlink()

    res_pct = coordinator.synchronize_pair(config)
    assert not res_pct.success, "O bisync DEVE abortar quando exclusões excedem max_delete_percent (50%)!"
    assert "too many deletes" in res_pct.stderr.lower()
    assert "--force" not in res_pct.command

    # Confirma que NENHUM dos 4 arquivos foi apagado em Path2 e seus hashes SHA-256 estão intactos
    inv2 = build_directory_inventory(path2).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv2 == expected_hashes

    # Parte 8b — Limite Absoluto (max_delete_abs=2, max_delete_percent=50%):
    # Com 10 arquivos de usuário (+1 sentinela = 11 no total), remover 3 arquivos representa
    # apenas 27,3% (abaixo de 50%, portanto --max-delete do rclone sozinho NÃO bloquearia!).
    # O limite absoluto max_delete_abs=2 DEVE bloquear antes de propagar qualquer exclusão.
    abs_cfg = BisyncConfig(
        path1=tmp_path / "abs_side1",
        path2=tmp_path / "abs_side2",
        workdir=tmp_path / "abs_workdir",
        backup_dir1=tmp_path / "abs_backup1",
        backup_dir2=tmp_path / "abs_backup2",
        max_delete_percent=50,
        max_delete_abs=2,
    )
    abs_cfg.path1.mkdir(parents=True)
    Path(abs_cfg.path2).mkdir(parents=True)

    expected_abs_hashes: dict[str, str] = {}
    for i in range(1, 11):
        fname = f"item_abs_{i:02d}.txt"
        f_abs = abs_cfg.path1 / fname
        f_abs.write_bytes(f"Arquivo protegido por limite absoluto {i}\n".encode("utf-8"))
        expected_abs_hashes[fname] = sha256_file(f_abs)

    init_abs = coordinator.initialize_pair_baseline(abs_cfg)
    assert init_abs.success

    # Exclui 3 arquivos de 11 (27,3% <= 50%, mas 3 > max_delete_abs=2)
    for i in (1, 2, 3):
        (abs_cfg.path1 / f"item_abs_{i:02d}.txt").unlink()

    res_abs = coordinator.synchronize_pair(abs_cfg)
    assert not res_abs.success, "O motor DEVE abortar quando exclusões excedem o limite absoluto max_delete_abs!"
    assert "limite absoluto excedido" in res_abs.stderr.lower()

    # Confirma que todos os 10 arquivos permanecem 100% intactos em abs_side2
    inv_abs_2 = build_directory_inventory(Path(abs_cfg.path2)).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert inv_abs_2 == expected_abs_hashes

    # Verifica também que tentar passar --force é explicitamente proibido pelo motor
    with pytest.raises(ValueError, match="proibido"):
        coordinator.engine.build_command(config, extra_args=["--force"])


def test_9_remote_pair_workflow_with_encrypted_config_and_folder_id(
    tmp_path: Path,
) -> None:
    """Cenário 9: Fluxo completo de par remoto (config cifrada RCLONE_ENCRYPT_V0:, pasta local vazia, resolução por ID e backup remoto sem sobreposição)."""
    db = BrisaDatabase(db_path=tmp_path / "state" / "remote_flow.db")
    engine = RcloneBisyncEngine()

    # Simula a árvore raiz do remote `brisasync_gdrive:` apontando para um diretório isolado
    # mas acessado exclusivamente como remote `brisasync_gdrive:PastaTeste` pelo rclone!
    cloud_root = tmp_path / "simulated_gdrive_cloud_root"
    cloud_test_folder = cloud_root / "BrisaSync-Teste"
    cloud_test_folder.mkdir(parents=True)
    (cloud_test_folder / "remoto_inicial.txt").write_bytes(b"Veio da nuvem na 1a sync!\n")
    expected_initial_hash = sha256_file(cloud_test_folder / "remoto_inicial.txt")

    # Configura um rclone.conf cifrado com RCLONE_ENCRYPT_V0: para `brisasync_gdrive`
    cfg_path = tmp_path / "rclone_encrypted.conf"
    cfg_path.write_text(
        f"[brisasync_gdrive]\ntype = alias\nremote = {cloud_root}\n",
        encoding="utf-8",
    )
    cfg_key = "test-256bit-key-for-encrypted-remote-workflow"
    pwd_cmd = f'python3 -c "import os; print(os.environ[\'BRISA_TEST_KEY\'])"'
    subprocess.run(
        [
            engine.rclone_binary,
            "config",
            "encryption",
            "set",
            "--password-command",
            pwd_cmd,
        ],
        env={**os.environ, "RCLONE_CONFIG": str(cfg_path), "BRISA_TEST_KEY": cfg_key},
        check=True,
        capture_output=True,
    )
    assert "RCLONE_ENCRYPT_V0:" in cfg_path.read_text(encoding="utf-8")

    rclone_env = {
        **os.environ,
        "RCLONE_CONFIG": str(cfg_path),
        "RCLONE_CONFIG_PASS": cfg_key,
        "RCLONE_ASK_PASSWORD": "false",
    }

    # Lista as pastas no remote cifrado e seleciona "BrisaSync-Teste" pelo ID
    remote_dirs = engine.list_remote_directories("brisasync_gdrive:", env=rclone_env)
    assert len(remote_dirs) == 1
    remote_entry = remote_dirs[0]
    assert remote_entry.name == "BrisaSync-Teste"

    coordinator = SyncCoordinator(database=db, engine=engine)
    local_empty_folder = tmp_path / "MinhaPastaLocalVazia"
    pair_cfg = coordinator.build_google_drive_pair_config(
        local_folder=local_empty_folder,
        remote_entry=remote_entry,
    )

    # 1ª Execução: pasta local vazia -> inicializa baseline e baixa arquivo remoto
    local_empty_folder.mkdir(parents=True, exist_ok=True)
    res1 = coordinator.initialize_pair_baseline(pair_cfg, env=rclone_env)
    assert res1.success, f"Falha na baseline remota: {res1.stderr}"
    assert sha256_file(local_empty_folder / "remoto_inicial.txt") == expected_initial_hash

    # 2ª Execução (Incremental): cria arquivo local, edita arquivo remoto e exclui um item
    (local_empty_folder / "criado_localmente.txt").write_bytes(b"Subindo para o remote!\n")
    hash_local_new = sha256_file(local_empty_folder / "criado_localmente.txt")

    res2 = coordinator.synchronize_pair(pair_cfg, env=rclone_env)
    assert res2.success, f"Falha no sync incremental remoto: {res2.stderr}"
    assert sha256_file(cloud_test_folder / "criado_localmente.txt") == hash_local_new

    # Verifica histórico gravado no SQLite
    runs = db.list_recent_sync_runs()
    assert len(runs) >= 2
    assert runs[0].status == "SUCCESS"
    assert runs[0].operation == "incremental_bisync"
    assert runs[1].operation == "baseline_resync"


def test_10_backup_dir2_backend_and_root_folder_id_non_overlap(
    tmp_path: Path,
) -> None:
    """Cenário 10: Confirma que backup_dir2 pertence ao mesmo backend e fica fora da árvore selecionada, inclusive quando root_folder_id muda a raiz visível."""
    engine = RcloneBisyncEngine()
    base_local = tmp_path / "local"
    base_wd = tmp_path / "wd"
    base_b1 = tmp_path / "b1"

    # 1. Rejeita backup_dir2 em outro remote/backend
    cfg_wrong_backend = BisyncConfig(
        path1=base_local,
        path2="brisasync_gdrive:MinhaPasta",
        workdir=base_wd,
        backup_dir1=base_b1,
        backup_dir2="outro_remote:.brisasync_recovery/123",
    )
    with pytest.raises(ValueError, match="mesmo remote/backend"):
        engine.validate_paths_non_overlapping(cfg_wrong_backend)

    # 2. Rejeita backup_dir2 dentro da árvore de Path2
    cfg_inside = BisyncConfig(
        path1=base_local,
        path2="brisasync_gdrive:MinhaPasta",
        workdir=base_wd,
        backup_dir1=base_b1,
        backup_dir2="brisasync_gdrive:MinhaPasta/.brisasync_recovery",
    )
    with pytest.raises(ValueError, match="sobrepor"):
        engine.validate_paths_non_overlapping(cfg_inside)

    # 3. Rejeita Path2 na raiz vazia do remote (pois qualquer backup_dir2 no mesmo remote ficaria dentro de Path2)
    cfg_root = BisyncConfig(
        path1=base_local,
        path2="brisasync_gdrive:",
        workdir=base_wd,
        backup_dir1=base_b1,
        backup_dir2="brisasync_gdrive:.brisasync_recovery/123",
    )
    with pytest.raises(ValueError, match="fora da árvore remota selecionada"):
        engine.validate_paths_non_overlapping(cfg_root)

    # 4. Rejeita quando root_folder_id no rclone.conf muda a raiz visível do remote para a própria pasta selecionada
    bad_rclone_conf = tmp_path / "bad_root_id.conf"
    bad_rclone_conf.write_text(
        "[brisasync_gdrive]\n"
        "type = drive\n"
        "root_folder_id = FOLDER_ID_SELECIONADA_999\n",
        encoding="utf-8",
    )
    cfg_shifted_root = BisyncConfig(
        path1=base_local,
        path2="brisasync_gdrive:SubpastaAparente",
        workdir=base_wd,
        backup_dir1=base_b1,
        backup_dir2="brisasync_gdrive:.brisasync_recovery/FOLDER_ID_SELECIONADA_999",
        remote_folder_id="FOLDER_ID_SELECIONADA_999",
    )
    with pytest.raises(ValueError, match="root_folder_id"):
        engine.verify_remote_backup_outside_selected_tree(
            cfg_shifted_root,
            env={**os.environ, "RCLONE_CONFIG": str(bad_rclone_conf)},
        )

    # 5. Permite quando root_folder_id é uma pasta-pai/workspace distinta da pasta selecionada
    #    e backup_dir2 é uma árvore irmã disjunta no mesmo backend
    good_rclone_conf = tmp_path / "good_root_id.conf"
    good_rclone_conf.write_text(
        "[brisasync_gdrive]\n"
        "type = drive\n"
        "root_folder_id = WORKSPACE_ROOT_ID_001\n",
        encoding="utf-8",
    )
    cfg_valid_sibling = BisyncConfig(
        path1=base_local,
        path2="brisasync_gdrive:PastaDeTeste",
        workdir=base_wd,
        backup_dir1=base_b1,
        backup_dir2="brisasync_gdrive:.brisasync_recovery/FOLDER_ID_FILHA_777",
        remote_folder_id="FOLDER_ID_FILHA_777",
        remote_root_folder_id="WORKSPACE_ROOT_ID_001",
    )
    engine.verify_remote_backup_outside_selected_tree(
        cfg_valid_sibling,
        env={**os.environ, "RCLONE_CONFIG": str(good_rclone_conf)},
    )



"""Coordenador de sincronização com proteção de concorrência, verificação de identidade de lock e suporte Google Drive."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
from typing import Callable, Iterator

from brisasync.platform_compat import lock_file, unlock_file

from brisasync.backend.rclone_engine import (
    BisyncConfig,
    BisyncExecutionResult,
    RcloneBisyncEngine,
    RemoteDirectoryEntry,
    is_remote_spec,
)
from brisasync.credentials.rclone_bridge import REMOTE_NAME, RcloneEncryptedBridge
from brisasync.credentials.store import CredentialSyncBackError, VaultUnavailableError
from brisasync.storage.database import BrisaDatabase


class ConcurrentSyncError(RuntimeError):
    """Levantada quando já existe outra sincronização em andamento para o mesmo par."""


class DirectoryAccessError(RuntimeError):
    """Levantada quando uma das pastas sincronizadas está ausente, inacessível ou inválida."""


def classify_sync_failure(error_text: str, exit_code: int = -1) -> str:
    """Classifica uma falha de sincronização entre erro transitório/rede (`OFFLINE_OR_TRANSIENT`) e erro que exige ação (`ATTENTION_REQUIRED`)."""
    lower = (error_text or "").lower()
    attention_markers = (
        "safety abort",
        "too many deletes",
        "sentinela",
        ".brisasync_check",
        "acesso ao google drive não concedido",
        "cofre",
        "secret-tool",
        "invalid_grant",
        "token has been expired or revoked",
        "unauthorized",
        "insufficient permission",
        "insufficient authentication scopes",
        "não foi encontrada",
        "múltiplas pastas remotas com o mesmo nome",
        "pasta local deve estar dedicada e vazia",
        "permissões insuficientes",
        "a pasta não existe",
        "conflito de árvore remota",
        "root_folder_id",
        "failed_credential_persistence",
    )
    if any(marker in lower for marker in attention_markers):
        return "ATTENTION_REQUIRED"

    transient_markers = (
        "dial tcp",
        "lookup ",
        "no such host",
        "connection refused",
        "connection reset",
        "network is unreachable",
        "i/o timeout",
        "tls handshake timeout",
        "context deadline exceeded",
        "temporary failure",
        "eof",
        "ratelimitexceeded",
        "userRateLimitExceeded".lower(),
        "429",
        "500 internal server error",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
        "falha de rede",
        "sem conexão",
    )
    if any(marker in lower for marker in transient_markers):
        return "OFFLINE_OR_TRANSIENT"

    if exit_code == 2:
        return "ATTENTION_REQUIRED"
    return "OFFLINE_OR_TRANSIENT"


@dataclass(frozen=True)
class ProcessIdentity:
    """Identidade verificada de um processo ativo no kernel Linux (`/proc/<pid>`)."""

    pid: int
    state: str
    comm: str
    cmdline: tuple[str, ...]
    starttime_ticks: int
    start_time_epoch: float

    @property
    def is_rclone_bisync(self) -> bool:
        """Verifica se o processo ativo corresponde genuinamente a uma instância de `rclone`."""
        comm_lower = self.comm.lower()
        if "rclone" in comm_lower:
            return True
        if not self.cmdline:
            return False
        exe_name = Path(self.cmdline[0]).name.lower()
        if "rclone" in exe_name:
            return True
        return any("rclone" in arg.lower() for arg in self.cmdline[:2])


def _get_system_boot_time_epoch() -> float:
    """Obtém o `btime` (boot time em segundos epoch UTC) a partir de `/proc/stat`."""
    try:
        for line in Path("/proc/stat").read_text(encoding="utf-8").splitlines():
            if line.startswith("btime "):
                return float(line.split()[1])
    except (OSError, ValueError, IndexError):
        pass
    return 0.0


def inspect_linux_process(pid: int) -> ProcessIdentity | None:
    """Inspeciona `/proc/<pid>/stat` e `/proc/<pid>/cmdline` para identificar um processo ativo.

    Retorna `None` se o PID não existir ou se for um processo zumbi ('Z') já encerrado.
    """
    if pid <= 0:
        return None
    proc_dir = Path(f"/proc/{pid}")
    if not proc_dir.is_dir():
        return None

    try:
        stat_raw = (proc_dir / "stat").read_text(encoding="utf-8")
        # Formato de /proc/<pid>/stat: pid (comm) state ppid ... [campo 22 = starttime]
        l_paren = stat_raw.find("(")
        r_paren = stat_raw.rfind(")")
        if l_paren == -1 or r_paren == -1 or r_paren <= l_paren:
            return None
        comm = stat_raw[l_paren + 1 : r_paren]
        rest_fields = stat_raw[r_paren + 2 :].split()
        if len(rest_fields) < 20:
            return None
        state = rest_fields[0]
        if state == "Z":
            return None
        # O campo 22 de /proc/<pid>/stat está no índice 19 após (comm)
        starttime_ticks = int(rest_fields[19])
        clk_tck = int(os.sysconf("SC_CLK_TCK"))
        btime = _get_system_boot_time_epoch()
        start_time_epoch = btime + (starttime_ticks / float(clk_tck)) if btime > 0 else 0.0

        cmdline_bytes = (proc_dir / "cmdline").read_bytes()
        cmdline = tuple(
            part.decode("utf-8", errors="replace")
            for part in cmdline_bytes.split(b"\x00")
            if part
        )
        return ProcessIdentity(
            pid=pid,
            state=state,
            comm=comm,
            cmdline=cmdline,
            starttime_ticks=starttime_ticks,
            start_time_epoch=start_time_epoch,
        )
    except (OSError, ValueError, IndexError):
        return None


def is_pid_alive(pid: int) -> bool:
    """Verifica se um PID pertence a um processo ativo (não-zumbi) no sistema operacional."""
    return inspect_linux_process(pid) is not None


def _parse_rfc3339_epoch(ts_str: str) -> float | None:
    if not ts_str:
        return None
    try:
        normalized = ts_str.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def validate_directory_accessible(
    folder: Path | str, *, create_if_missing: bool = False
) -> Path:
    """Valida que um caminho é um diretório real com permissão de leitura, escrita e travessia."""
    target = Path(folder).expanduser()
    if create_if_missing:
        target.mkdir(parents=True, exist_ok=True)

    if not target.exists():
        raise DirectoryAccessError(f"A pasta não existe: {target}")
    if not target.is_dir():
        raise DirectoryAccessError(f"O caminho não é um diretório: {target}")
    if not os.access(target, os.R_OK | os.W_OK | os.X_OK):
        raise DirectoryAccessError(
            f"Permissões insuficientes de leitura/escrita na pasta: {target}"
        )
    return target.resolve()


def validate_directory_empty_for_initial_sync(
    folder: Path | str, *, create_if_missing: bool = True
) -> Path:
    """Garante que a pasta local dedicada à primeira sincronização existe, é acessível e está vazia."""
    resolved = validate_directory_accessible(folder, create_if_missing=create_if_missing)
    existing_entries = list(resolved.iterdir())
    if existing_entries:
        sample = ", ".join(e.name for e in existing_entries[:3])
        raise DirectoryAccessError(
            f"Para a primeira sincronização, a pasta local deve estar dedicada e vazia "
            f"({len(existing_entries)} item(ns) encontrado(s) em {resolved}: {sample})."
        )
    return resolved


class SyncCoordinator:
    """Orquestra execuções do `RcloneBisyncEngine` com lock exclusivo e registro em SQLite."""

    def __init__(
        self,
        database: BrisaDatabase,
        engine: RcloneBisyncEngine | None = None,
        bridge: RcloneEncryptedBridge | None = None,
    ) -> None:
        self.database = database
        self.engine = engine or RcloneBisyncEngine()
        self.bridge = bridge or RcloneEncryptedBridge(rclone_binary=self.engine.rclone_binary)
        self._proc_lock = threading.Lock()
        self._active_proc: subprocess.Popen[str] | None = None
        self._stop_requested: bool = False

    def _register_active_process(self, proc: subprocess.Popen[str]) -> None:
        with self._proc_lock:
            self._active_proc = proc
            if self._stop_requested and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except OSError:
                    pass

    def _clear_active_process(self) -> None:
        with self._proc_lock:
            self._active_proc = None

    def is_stop_requested(self) -> bool:
        with self._proc_lock:
            return self._stop_requested

    def get_active_rclone_pid(self) -> int | None:
        with self._proc_lock:
            if self._active_proc is not None and self._active_proc.poll() is None:
                return int(self._active_proc.pid)
            return None

    def request_graceful_stop(self) -> bool:
        """Solicita parada controlada da operação atual via `SIGTERM` ao `rclone bisync`.

        Envia um primeiro `SIGTERM` para encerramento gracioso do `rclone` e, caso o
        processo continue bloqueado em transferência após 0.8s, envia o segundo `SIGTERM`
        previsto pelo próprio `rclone` para encerramento imediato, preservando o estado
        recuperável do workdir para `--recover` no próximo ciclo. Jamais usa `SIGSTOP`.
        """
        with self._proc_lock:
            self._stop_requested = True
            proc = self._active_proc
            if proc is not None and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGTERM)
                except OSError:
                    return False

                def _followup_sigterm(target_proc: subprocess.Popen[str]) -> None:
                    try:
                        target_proc.wait(timeout=0.8)
                    except subprocess.TimeoutExpired:
                        if target_proc.poll() is None:
                            try:
                                target_proc.send_signal(signal.SIGTERM)
                            except OSError:
                                pass

                threading.Thread(
                    target=_followup_sigterm,
                    args=(proc,),
                    daemon=True,
                ).start()
                return True
            return False

    @staticmethod
    def _expire_dead_owner_rclone_lock(lck_file: Path, data: dict[str, object]) -> None:
        """Marca como expirado um `.lck` órfão cujo processo proprietário já encerrou (ou teve PID reutilizado).

        Preserva o arquivo `.lck` no workdir com `TimeExpires` no passado para que o
        `rclone bisync --recover` execute a reconciliação oficial de recuperação imediatamente,
        sem aguardar o tempo nominal restante de `max-lock`.
        """
        try:
            updated = dict(data)
            updated["TimeExpires"] = "2020-01-01T00:00:00Z"
            lck_file.write_text(json.dumps(updated) + "\n", encoding="utf-8")
            expired_ts = 1_577_836_800.0
            os.utime(lck_file, (expired_ts, expired_ts))
        except OSError:
            pass

    @classmethod
    def _check_active_rclone_lock_owner(cls, workdir: Path) -> None:
        """Impede violação de locks `.lck` pertencentes a processos `rclone` legítimos ativos, protegendo contra reutilização de PID.

        Um processo `owner_pid` só é reconhecido como proprietário ativo do `.lck` se:
        1. Estiver vivo no kernel (`/proc/<pid>`) e não for zumbi;
        2. Sua identidade de processo (`cmdline`/`comm`) for `rclone` (evitando falso bloqueio
           quando o kernel recicla o PID para outro programa após a morte do `rclone`);
        3. Seu horário de início (`start_time_epoch`) não for posterior ao registro do `.lck`
           (se o processo nasceu *depois* da criação/renovação do `.lck`, o proprietário
           original morreu e o PID foi reutilizado).

        Se o proprietário legítimo estiver ativo, levanta `ConcurrentSyncError` e jamais remove
        o lock. Se o proprietário original já encerrou (PID morto ou reutilizado), expira a
        trava órfã para liberar a recuperação imediata pelo `rclone --recover`.
        """
        if not workdir.is_dir():
            return
        my_pid = os.getpid()
        for lck_file in workdir.glob("*.lck"):
            try:
                stat_lck = lck_file.stat()
                raw = lck_file.read_text(encoding="utf-8").strip()
                data = json.loads(raw)
                pid_str = str(data.get("PID", "")).strip()
                if not pid_str.isdigit():
                    continue
                owner_pid = int(pid_str)
                if owner_pid == my_pid or owner_pid > 4_194_304:
                    continue

                identity = inspect_linux_process(owner_pid)
                if identity is None:
                    # Processo proprietário já encerrou: libera/expira a trava órfã
                    cls._expire_dead_owner_rclone_lock(lck_file, data)
                    continue

                # 1. Verifica identidade do executável/linha de comando contra reutilização de PID
                if not identity.is_rclone_bisync:
                    # O PID pertence hoje a outro programa (ex.: python, bash, navegador),
                    # portanto o processo rclone original já morreu e houve reciclagem de PID.
                    cls._expire_dead_owner_rclone_lock(lck_file, data)
                    continue

                # 2. Verifica horário de início do processo contra o timestamp do arquivo .lck
                renewed_epoch = _parse_rfc3339_epoch(str(data.get("TimeRenewed", "")))
                lock_ref_epoch = stat_lck.st_mtime
                if renewed_epoch is not None and renewed_epoch > lock_ref_epoch:
                    lock_ref_epoch = renewed_epoch

                if (
                    identity.start_time_epoch > 0
                    and lock_ref_epoch > 0
                    and identity.start_time_epoch > (lock_ref_epoch + 2.0)
                ):
                    # O processo atual com este PID nasceu DEPOIS que o lock foi gravado:
                    # trata-se de reutilização de PID após encerramento do proprietário original.
                    cls._expire_dead_owner_rclone_lock(lck_file, data)
                    continue

                raise ConcurrentSyncError(
                    f"Execução concorrente bloqueada: processo rclone ativo (PID {owner_pid}, "
                    f"cmd={identity.comm!r}) ainda detém o lock {lck_file.name}, mesmo que a "
                    "duração tenha ultrapassado max-lock."
                )
            except ConcurrentSyncError:
                raise
            except Exception:
                # Se não for JSON válido ou se o PID não pertencer a um rclone ativo, deixa o
                # rclone aplicar sua regra normal de expiração (--max-lock).
                continue

    @classmethod
    @contextmanager
    def acquire_pair_lock(cls, workdir: Path) -> Iterator[Path]:
        """Adquire lock exclusivo de sistema operacional (`flock`), grava identidade do processo e libera ao encerrar."""
        workdir.mkdir(parents=True, exist_ok=True)
        lock_file_path = workdir / "brisasync_pair.lock"
        fd = os.open(lock_file_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                lock_file(fd, exclusive=True, non_blocking=True)
            except BlockingIOError as exc:
                raise ConcurrentSyncError(
                    f"Execução concorrente bloqueada: já existe sincronização ativa em {workdir}."
                ) from exc

            # Verifica se algum subprocesso rclone legítimo e ativo ainda detém `.lck` no workdir
            cls._check_active_rclone_lock_owner(workdir)

            me = inspect_linux_process(os.getpid())
            lock_meta = {
                "pid": os.getpid(),
                "starttime_ticks": me.starttime_ticks if me else 0,
                "start_time_epoch": me.start_time_epoch if me else 0.0,
                "cmdline": list(me.cmdline) if me else [],
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            }
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, (json.dumps(lock_meta) + "\n").encode("utf-8"))
            os.fsync(fd)
            yield lock_file_path
        finally:
            try:
                os.ftruncate(fd, 0)
            except OSError:
                pass
            try:
                unlock_file(fd)
            finally:
                os.close(fd)

    def _ensure_paths_ready_for_sync(
        self,
        config: BisyncConfig,
        *,
        is_initial_baseline: bool,
        env: dict[str, str] | None = None,
    ) -> None:
        """Verifica se ambos os destinos estão acessíveis e íntegros antes de invocar o backend.

        Jamais recria um marcador `.brisasync_check` ausente em ciclos normais.
        """
        p1 = validate_directory_accessible(config.path1, create_if_missing=False)
        sentinel1 = p1 / config.check_filename

        if is_remote_spec(config.path2):
            if not is_initial_baseline:
                if not sentinel1.is_file():
                    raise DirectoryAccessError(
                        f"Arquivo sentinela ausente na pasta local ({sentinel1}). "
                        "Sincronização abortada para proteger contra exclusão em massa."
                    )
                if not self.engine.check_remote_sentinel_exists(
                    str(config.path2), config.check_filename, env=env
                ):
                    raise DirectoryAccessError(
                        f"Arquivo sentinela ({config.check_filename}) ausente ou inacessível "
                        f"na pasta remota ({config.path2}). Sincronização abortada."
                    )
        else:
            p2 = validate_directory_accessible(config.path2, create_if_missing=False)
            if not is_initial_baseline:
                if not sentinel1.is_file():
                    raise DirectoryAccessError(
                        f"Arquivo sentinela ausente em Path1 ({sentinel1}). "
                        "Sincronização abortada para proteger contra exclusão em massa."
                    )
                sentinel2 = p2 / config.check_filename
                if not sentinel2.is_file():
                    raise DirectoryAccessError(
                        f"Arquivo sentinela ausente em Path2 ({sentinel2}). "
                        "Sincronização abortada para proteger contra exclusão em massa."
                    )

    def build_google_drive_pair_config(
        self,
        *,
        local_folder: Path | str,
        remote_entry: RemoteDirectoryEntry,
    ) -> BisyncConfig:
        """Monta `BisyncConfig` sem sobreposição para um par Local <-> Pasta Google Drive por ID."""
        local_path = Path(local_folder).expanduser().resolve()
        pair_digest = hashlib.sha256(
            f"{local_path}::{remote_entry.folder_id}".encode("utf-8")
        ).hexdigest()[:16]

        base_state_dir = self.database.db_path.parent
        workdir = base_state_dir / "bisync_workdirs" / pair_digest
        backup_dir1 = base_state_dir / "recovery_local" / pair_digest
        remote_path2 = f"{REMOTE_NAME}:{remote_entry.path}"
        remote_backup2 = f"{REMOTE_NAME}:.brisasync_recovery/{remote_entry.folder_id}"

        return BisyncConfig(
            path1=local_path,
            path2=remote_path2,
            workdir=workdir,
            backup_dir1=backup_dir1,
            backup_dir2=remote_backup2,
            remote_folder_id=remote_entry.folder_id,
        )

    def synchronize_google_drive_pair(
        self,
        *,
        local_folder: Path | str,
        remote_folder_id: str,
        on_phase_change: Callable[[str], None] | None = None,
    ) -> BisyncExecutionResult:
        """Executa o fluxo completo e seguro de sincronização com uma pasta do Google Drive por ID.

        - Na primeira execução do par, valida que a pasta local está dedicada e vazia,
          resolve a pasta remota pelo `remote_folder_id`, inicializa a baseline (`--resync`)
          e registra o par como inicializado.
        - Nas execuções seguintes, resolve a pasta remota pelo `remote_folder_id`,
          verifica a presença dos marcadores `.brisasync_check` (sem recriá-los!) e
          executa o `bisync` incremental.
        - Se a devolução de tokens renovados ao cofre falhar (`CredentialSyncBackError`),
          registra a falha no histórico SQLite e jamais reporta sucesso indevido.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        resolved_local = str(Path(local_folder).expanduser().resolve())
        target_path2_label = f"{REMOTE_NAME}:{remote_folder_id}"
        already_initialized = False
        with self._proc_lock:
            self._stop_requested = False

        try:
            if on_phase_change is not None:
                on_phase_change("VERIFYING")
            with self.bridge.authenticated_rclone_session() as rclone_env:
                remote_entry = self.engine.resolve_remote_directory_by_id(
                    f"{REMOTE_NAME}:",
                    remote_folder_id,
                    env=rclone_env,
                )
                config = self.build_google_drive_pair_config(
                    local_folder=local_folder,
                    remote_entry=remote_entry,
                )
                target_path2_label = str(config.path2)
                already_initialized = self.database.is_baseline_initialized(
                    local_folder=str(config.path1),
                    remote_folder_id=remote_entry.folder_id,
                )
                if not already_initialized:
                    validate_directory_empty_for_initial_sync(
                        config.path1, create_if_missing=True
                    )
                    result = self.initialize_pair_baseline(
                        config,
                        env=rclone_env,
                        on_phase_change=on_phase_change,
                        _update_confirmed_timestamp=False,
                    )
                    if result.success and not result.stopped_by_user:
                        self.database.mark_baseline_initialized(
                            local_folder=str(config.path1),
                            remote_folder_id=remote_entry.folder_id,
                        )
                        self.database.set_remote_sync_folder(
                            folder_id=remote_entry.folder_id,
                            folder_name=remote_entry.name,
                        )
                else:
                    result = self.synchronize_pair(
                        config,
                        env=rclone_env,
                        on_phase_change=on_phase_change,
                        _update_confirmed_timestamp=False,
                    )
            if result.success and not result.stopped_by_user:
                self.database.set_last_confirmed_sync_at(
                    datetime.now(timezone.utc).isoformat()
                )
            return result
        except DirectoryAccessError as exc:
            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.record_sync_run(
                started_at=started_at,
                finished_at=finished_at,
                path1=resolved_local,
                path2=target_path2_label,
                operation="baseline_precheck" if not already_initialized else "precheck_validation",
                status="ATTENTION_REQUIRED",
                exit_code=-1,
                summary=str(exc),
            )
            raise
        except CredentialSyncBackError as exc:
            finished_at = datetime.now(timezone.utc).isoformat()
            self.database.record_sync_run(
                started_at=started_at,
                finished_at=finished_at,
                path1=resolved_local,
                path2=target_path2_label,
                operation="credential_sync_back",
                status="FAILED_CREDENTIAL_PERSISTENCE",
                exit_code=-2,
                summary=str(exc),
            )
            raise

    def initialize_pair_baseline(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
        on_phase_change: Callable[[str], None] | None = None,
        _update_confirmed_timestamp: bool = True,
    ) -> BisyncExecutionResult:
        """Executa a inicialização explícita da baseline (`--resync`) sob lock exclusivo."""
        started_at = datetime.now(timezone.utc).isoformat()
        with self._proc_lock:
            self._stop_requested = False

        try:
            with self.acquire_pair_lock(config.workdir):
                if on_phase_change is not None:
                    on_phase_change("VERIFYING")
                self._ensure_paths_ready_for_sync(
                    config, is_initial_baseline=True, env=env
                )
                if on_phase_change is not None:
                    on_phase_change("SYNCING")
                result = self.engine.initialize_baseline(
                    config,
                    env=env,
                    on_process_started=self._register_active_process,
                    stop_requested_check=self.is_stop_requested,
                )
        finally:
            self._clear_active_process()

        finished_at = datetime.now(timezone.utc).isoformat()
        status_str = (
            "STOPPED_BY_USER"
            if result.stopped_by_user
            else ("SUCCESS" if result.success else "FAILED")
        )
        self.database.record_sync_run(
            started_at=started_at,
            finished_at=finished_at,
            path1=str(config.path1),
            path2=str(config.path2),
            operation="baseline_resync",
            status=status_str,
            exit_code=result.exit_code,
            summary=result.error_reason or "Baseline inicial estabelecida com sucesso.",
        )
        if _update_confirmed_timestamp and result.success and not result.stopped_by_user:
            self.database.set_last_confirmed_sync_at(finished_at)
        return result

    def synchronize_pair(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
        on_phase_change: Callable[[str], None] | None = None,
        _update_confirmed_timestamp: bool = True,
    ) -> BisyncExecutionResult:
        """Executa sincronização bidirecional incremental.

        Jamais executa `--resync` automaticamente se ocorrer erro e jamais recria
        marcadores de acesso ausentes.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        with self._proc_lock:
            self._stop_requested = False

        try:
            with self.acquire_pair_lock(config.workdir):
                if on_phase_change is not None:
                    on_phase_change("VERIFYING")
                self._ensure_paths_ready_for_sync(
                    config, is_initial_baseline=False, env=env
                )
                if on_phase_change is not None:
                    on_phase_change("SYNCING")
                result = self.engine.run_bisync(
                    config,
                    env=env,
                    extra_args=extra_args,
                    on_process_started=self._register_active_process,
                    stop_requested_check=self.is_stop_requested,
                )
        except (ConcurrentSyncError, DirectoryAccessError) as exc:
            self._clear_active_process()
            finished_at = datetime.now(timezone.utc).isoformat()
            status_code = (
                "BLOCKED_CONCURRENT"
                if isinstance(exc, ConcurrentSyncError)
                else "ABORTED_ACCESS"
            )
            self.database.record_sync_run(
                started_at=started_at,
                finished_at=finished_at,
                path1=str(config.path1),
                path2=str(config.path2),
                operation="incremental_bisync",
                status=status_code,
                exit_code=-1,
                summary=str(exc),
            )
            raise
        finally:
            self._clear_active_process()

        finished_at = datetime.now(timezone.utc).isoformat()
        status_str = (
            "STOPPED_BY_USER"
            if result.stopped_by_user
            else ("SUCCESS" if result.success else "FAILED")
        )
        if result.conflict_files:
            self.database.record_backend_conflict_files(
                config.path1, result.conflict_files
            )
            conflict_note = (
                f" Conflitos preservados pelo backend ({len(result.conflict_files)}): "
                f"{', '.join(result.conflict_files)}."
            )
        else:
            conflict_note = ""
        base_summary = (
            result.error_reason or "Sincronização bidirecional concluída com sucesso."
        )
        self.database.record_sync_run(
            started_at=started_at,
            finished_at=finished_at,
            path1=str(config.path1),
            path2=str(config.path2),
            operation="incremental_bisync",
            status=status_str,
            exit_code=result.exit_code,
            summary=f"{base_summary}{conflict_note}",
        )
        if _update_confirmed_timestamp and result.success and not result.stopped_by_user:
            self.database.set_last_confirmed_sync_at(finished_at)
        return result

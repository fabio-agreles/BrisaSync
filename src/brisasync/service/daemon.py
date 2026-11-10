"""Daemon do serviço de sessão do usuário (`brisasync --service`).

Proprietário exclusivo do agendamento periódico, coalescência de pedidos,
espera progressiva (backoff) e execução de processos `rclone bisync`.
Controlado pela interface exclusivamente via IPC local (`AF_UNIX` + `SO_PEERCRED`).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import signal
import socket
import threading
import time
from typing import Any

from brisasync.platform_compat import is_windows, lock_file, unlock_file

from brisasync.backend.rclone_engine import (
    BisyncConfig,
    BisyncExecutionResult,
    RcloneBisyncEngine,
)
from brisasync.credentials.rclone_bridge import RcloneEncryptedBridge
from brisasync.credentials.store import (
    CredentialStore,
    CredentialSyncBackError,
    VaultUnavailableError,
)
from brisasync.orchestrator.sync_coordinator import (
    ConcurrentSyncError,
    DirectoryAccessError,
    SyncCoordinator,
    classify_sync_failure,
)
from brisasync.service.autostart import (
    BrisaAutostartCoordinator,
    SystemdUserAutostartManager,
)
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_CONFLICT_DETECTED,
    ATTENTION_PERSISTENT_FAILURE,
    ATTENTION_RECOVERY_REQUIRED,
    ATTENTION_VAULT_LOCKED,
    STATE_ATTENTION_REQUIRED,
    STATE_LABELS,
    STATE_OFFLINE,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_SYNCING,
    STATE_VERIFYING,
    STATE_WAITING,
    ServiceStatusSnapshot,
    default_service_socket_path,
    verify_peer_credentials,
)
from brisasync.storage.database import BrisaDatabase


class ServiceAlreadyRunningError(RuntimeError):
    """Levantada quando já existe uma instância ativa do serviço na sessão do usuário."""


class BrisaSessionServiceDaemon:
    """Serviço sem root da sessão do usuário, proprietário único do agendamento e do `rclone bisync`."""

    def __init__(
        self,
        database: BrisaDatabase | None = None,
        credential_store: CredentialStore | None = None,
        engine: RcloneBisyncEngine | None = None,
        bridge: RcloneEncryptedBridge | None = None,
        coordinator: SyncCoordinator | None = None,
        autostart_manager: BrisaAutostartCoordinator | SystemdUserAutostartManager | None = None,
        *,
        socket_path: Path | str | None = None,
        local_pair_config: BisyncConfig | None = None,
        base_backoff_seconds: int = 30,
        max_backoff_seconds: int = 900,
    ) -> None:
        self.database = database or BrisaDatabase()
        self.credential_store = credential_store or CredentialStore()
        self.engine = engine or RcloneBisyncEngine()
        self.bridge = bridge or RcloneEncryptedBridge(
            credential_store=self.credential_store,
            rclone_binary=self.engine.rclone_binary,
        )
        self.coordinator = coordinator or SyncCoordinator(
            database=self.database,
            engine=self.engine,
            bridge=self.bridge,
        )
        self.autostart_manager = autostart_manager or BrisaAutostartCoordinator(
            db_path=self.database.db_path
        )
        self.socket_path = (
            Path(socket_path).expanduser().resolve()
            if socket_path is not None
            else default_service_socket_path()
        )
        self.lock_path = self.socket_path.with_name(f"{self.socket_path.name}.lock")
        self.local_pair_config = local_pair_config
        self.base_backoff_seconds = max(1, int(base_backoff_seconds))
        self.max_backoff_seconds = max(self.base_backoff_seconds, int(max_backoff_seconds))

        self._state_lock = threading.RLock()
        self._wake_event = threading.Event()
        self._shutdown_requested = False
        self._manual_trigger_requested = False
        self._pending_sync_coalesced = False
        self._is_cycle_active = False

        self._auto_sync_paused: bool = self.database.is_auto_sync_paused()
        self._sync_interval_seconds: int = self.database.get_sync_interval_seconds(default=300)
        self._state: str = STATE_PAUSED if self._auto_sync_paused else STATE_WAITING
        self._detail_message: str = (
            "Sincronização automática pausada pelo usuário."
            if self._auto_sync_paused
            else "Serviço ativo aguardando próximo ciclo."
        )
        self._backoff_attempt: int = 0
        self._backoff_seconds: int = 0
        self._next_scheduled_epoch: float | None = None
        self._last_run_status: str | None = None
        self._last_error_reason: str | None = None

        self._lock_fd: int | None = None
        self._server_sock: socket.socket | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._accept_thread: threading.Thread | None = None

    def _acquire_single_instance_lock(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.socket_path.parent, 0o700)
        except OSError:
            pass
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            lock_file(fd, exclusive=True, non_blocking=True)
        except BlockingIOError as exc:
            os.close(fd)
            raise ServiceAlreadyRunningError(
                f"O serviço BrisaSync já está em execução na sessão (lock ativo em {self.lock_path})."
            ) from exc

        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        payload = {
            "pid": os.getpid(),
            "socket_path": str(self.socket_path),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        os.write(fd, (json.dumps(payload) + "\n").encode("utf-8"))
        os.fsync(fd)
        self._lock_fd = fd

    def _release_single_instance_lock(self) -> None:
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        try:
            self.socket_path.unlink(missing_ok=True)
        except OSError:
            pass
        if self._lock_fd is not None:
            try:
                os.ftruncate(self._lock_fd, 0)
                unlock_file(self._lock_fd)
            except OSError:
                pass
            finally:
                try:
                    os.close(self._lock_fd)
                except OSError:
                    pass
                self._lock_fd = None

    def _bind_ipc_socket(self) -> None:
        try:
            self.socket_path.unlink(missing_ok=True)
        except OSError:
            pass
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(self.socket_path))
        if not is_windows():
            try:
                os.chmod(self.socket_path, 0o600)
            except OSError:
                pass
        srv.listen(16)
        srv.settimeout(0.5)
        self._server_sock = srv

    def start_in_background(self) -> None:
        """Inicia o socket IPC e as threads do serviço dentro do processo atual."""
        self._acquire_single_instance_lock()
        try:
            self._bind_ipc_socket()
        except Exception:
            self._release_single_instance_lock()
            raise

        with self._state_lock:
            self._shutdown_requested = False
            if not self._auto_sync_paused:
                self._next_scheduled_epoch = time.time() + float(
                    self._sync_interval_seconds
                )

        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="BrisaSync-Scheduler",
            daemon=True,
        )
        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name="BrisaSync-IPC-Accept",
            daemon=True,
        )
        self._scheduler_thread.start()
        self._accept_thread.start()

    def serve_forever(self) -> int:
        """Executa o daemon do serviço bloqueando até receber `shutdown_service` ou sinal de término."""
        self.start_in_background()

        def _sig_handler(_signum: int, _frame: Any) -> None:
            self.request_shutdown()

        prev_int = signal.getsignal(signal.SIGINT)
        prev_term = signal.getsignal(signal.SIGTERM)
        try:
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, _sig_handler)
                signal.signal(signal.SIGTERM, _sig_handler)
            while True:
                with self._state_lock:
                    if self._shutdown_requested and not self._is_cycle_active:
                        break
                time.sleep(0.1)
        finally:
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, prev_int)
                signal.signal(signal.SIGTERM, prev_term)
            self.stop_and_wait()
        return 0

    def stop_and_wait(self, timeout: float = 15.0) -> None:
        """Solicita encerramento controlado, aguarda término de ciclo ativo e libera socket/locks."""
        self.request_shutdown()
        if self._scheduler_thread is not None and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=timeout)
        if self._accept_thread is not None and self._accept_thread.is_alive():
            self._accept_thread.join(timeout=2.0)
        self._release_single_instance_lock()

    def request_shutdown(self) -> None:
        with self._state_lock:
            self._shutdown_requested = True
            self._pending_sync_coalesced = False
            self._manual_trigger_requested = False
            if self._is_cycle_active:
                self.coordinator.request_graceful_stop()
        self._wake_event.set()

    def _is_pair_configured(self) -> bool:
        if self.database.is_voluntary_disconnect():
            return False
        if self.credential_store.is_vault_locked():
            return False
        try:
            creds = self.credential_store.load_credentials(interactive=False)
        except Exception:
            return False
        if not creds or not creds.access_token:
            return False

        if self.local_pair_config is not None:
            return True
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        return bool(local_cfg and remote_cfg)

    def _count_local_conflict_files(self) -> int:
        """Conta exclusivamente arquivos de conflito efetivamente registrados pelo backend e ainda presentes na pasta local.

        Um arquivo legítimo do usuário cujo nome termine em `.conflict1`/`.conflict2`
        (sem ter sido gerado por uma operação de conflito do `rclone bisync`) não gera
        alerta de conflito e jamais é renomeado ou removido.
        """
        target_dir: Path | None = None
        if self.local_pair_config is not None:
            target_dir = self.local_pair_config.path1
        else:
            local_cfg = self.database.get_local_sync_folder()
            if local_cfg:
                target_dir = Path(local_cfg.folder_path)
        if target_dir is None or not target_dir.is_dir():
            return 0
        try:
            recorded = self.database.get_recorded_conflict_files(target_dir)
            if not recorded:
                return 0
            resolved_root = target_dir.expanduser().resolve()
            still_present: list[str] = []
            for rel_path in recorded:
                candidate = (resolved_root / rel_path).resolve()
                if candidate.is_relative_to(resolved_root) and candidate.is_file():
                    still_present.append(rel_path)
            if len(still_present) != len(recorded):
                self.database.set_recorded_conflict_files(target_dir, still_present)
            return len(still_present)
        except OSError:
            return 0

    def _classify_attention_details_locked(
        self, conflict_count: int
    ) -> tuple[str | None, str | None, str | None]:
        """Classifica situações que exigem atenção do usuário em categorias com motivo real comprovado e sanitizado."""
        if hasattr(self.credential_store, "is_vault_locked") and self.credential_store.is_vault_locked() is True:
            return (
                ATTENTION_VAULT_LOCKED,
                "Cofre de Credenciais Bloqueado",
                "O chaveiro da sessão está bloqueado. Desbloqueie o chaveiro para retomar a sincronização.",
            )

        if self.database.is_voluntary_disconnect():
            return None, None, None

        try:
            creds = self.credential_store.load_credentials(interactive=False)
        except Exception:
            creds = None
        has_creds = bool(creds and creds.access_token and creds.refresh_token)

        err_raw = (self._last_error_reason or "").strip()
        err_lower = err_raw.lower()
        if err_lower:
            if "bloqueado" in err_lower or "locked" in err_lower:
                return (
                    ATTENTION_VAULT_LOCKED,
                    "Cofre de Credenciais Bloqueado",
                    "O chaveiro da sessão está bloqueado. Desbloqueie o chaveiro para retomar a sincronização.",
                )

            # Se a mensagem for informativa sobre ausência voluntária ou inicial de conta, não trata como alerta
            if "nenhuma conta" in err_lower or "no account" in err_lower:
                return None, None, None

            auth_markers = (
                "invalid_grant",
                "token has been expired or revoked",
                "unauthorized",
                "insufficient permission",
                "insufficient authentication scopes",
                "acesso ao google drive não concedido",
            )
            if any(m in err_lower for m in auth_markers):
                if has_creds:
                    return (
                        ATTENTION_AUTH_EXPIRED,
                        "Autenticação Exige Atenção",
                        f"A autorização da conta expirou ou foi revogada. {err_raw}",
                    )
                return None, None, None

            # 1. Pasta local não dedicada / não vazia para baseline
            if "pasta local deve estar dedicada e vazia" in err_lower or "dedicated and empty" in err_lower:
                return (
                    ATTENTION_RECOVERY_REQUIRED,
                    "Pasta Local Não Dedicada ou Não Vazia",
                    f"A primeira sincronização com uma nova pasta remota exige pasta local vazia para proteção contra mistura ou perda de dados. {err_raw}",
                )

            # 2. Exclusão em massa
            if (
                "safety abort" in err_lower
                or "too many deletes" in err_lower
                or "limite de exclusão" in err_lower
                or "exclusão em massa" in err_lower
            ):
                return (
                    ATTENTION_RECOVERY_REQUIRED,
                    "Proteção contra Exclusão em Massa",
                    f"A sincronização foi suspensa para proteção dos dados porque o número de exclusões detectadas ultrapassou o limite de segurança. {err_raw}",
                )

            # 3. Marcador sentinela
            if "sentinela" in err_lower or ".brisasync_check" in err_lower:
                return (
                    ATTENTION_RECOVERY_REQUIRED,
                    "Marcador de Integridade Ausente",
                    f"O marcador de segurança (.brisasync_check) não foi localizado ou não pôde ser verificado. {err_raw}",
                )

            # 4. Pasta remota ou local inacessível / inexistente
            if any(
                m in err_lower
                for m in (
                    "a pasta não existe",
                    "não foi encontrada",
                    "permissões insuficientes",
                    "não foi possível acessar",
                    "directoryaccesserror",
                    "directorynotfounderror",
                )
            ):
                return (
                    ATTENTION_RECOVERY_REQUIRED,
                    "Pasta Inacessível ou Inexistente",
                    f"Não foi possível acessar ou localizar o diretório configurado. {err_raw}",
                )

            # 5. Inconsistência de raiz / conflito de árvore remota
            if any(
                m in err_lower
                for m in (
                    "conflito de árvore remota",
                    "root_folder_id",
                    "múltiplas pastas remotas",
                )
            ):
                return (
                    ATTENTION_RECOVERY_REQUIRED,
                    "Inconsistência de Configuração Remota",
                    f"Inconsistência detectada entre a raiz do remote e a pasta selecionada. {err_raw}",
                )

            # 6. Falha ao devolver credenciais
            if "failed_credential_persistence" in err_lower or "devolver credenciais" in err_lower:
                return (
                    ATTENTION_PERSISTENT_FAILURE,
                    "Falha ao Persistir Credenciais",
                    f"Não foi possível salvar os tokens atualizados no cofre da sessão. {err_raw}",
                )

            # 7. Falhas persistentes / repetidas
            if self._backoff_attempt >= 2 or self._last_run_status == "ATTENTION_REQUIRED":
                return (
                    ATTENTION_PERSISTENT_FAILURE,
                    "Falha Persistente de Sincronização",
                    f"O serviço registrou falhas repetidas. Detalhe técnico: {err_raw}",
                )

            # 8. Motivo desconhecido / não categorizado (sem listar hipóteses genéricas)
            return (
                ATTENTION_RECOVERY_REQUIRED,
                "Atenção Necessária",
                f"Motivo ainda não identificado. Detalhe técnico: {err_raw}",
            )

        if conflict_count > 0:
            return (
                ATTENTION_CONFLICT_DETECTED,
                "Conflito de Edição Preservado",
                f"Foram detectados {conflict_count} arquivo(s) com alterações concorrentes (.conflict). "
                "Ambas as versões foram preservadas com segurança; abra o painel ou a pasta local para revisar.",
            )

        return None, None, None

    def get_status_snapshot(self) -> ServiceStatusSnapshot:
        with self._state_lock:
            next_iso = (
                datetime.fromtimestamp(self._next_scheduled_epoch, tz=timezone.utc).isoformat()
                if self._next_scheduled_epoch is not None and not self._auto_sync_paused
                else None
            )
            state_code = self._state
            state_label = STATE_LABELS.get(state_code, state_code)
            last_confirmed = self.database.get_last_confirmed_sync_at()
            conflict_count = self._count_local_conflict_files()
            att_cat, att_title, att_expl = self._classify_attention_details_locked(
                conflict_count
            )
            return ServiceStatusSnapshot(
                service_pid=os.getpid(),
                state=state_code,
                state_label=state_label,
                detail_message=self._detail_message,
                is_cycle_active=self._is_cycle_active,
                active_rclone_pid=self.coordinator.get_active_rclone_pid(),
                pending_sync_coalesced=self._pending_sync_coalesced,
                auto_sync_paused=self._auto_sync_paused,
                sync_interval_seconds=self._sync_interval_seconds,
                next_scheduled_sync_at=next_iso,
                backoff_attempt=self._backoff_attempt,
                backoff_seconds=self._backoff_seconds,
                last_confirmed_sync_at=last_confirmed,
                last_run_status=self._last_run_status,
                last_error_reason=self._last_error_reason,
                autostart_enabled=self.autostart_manager.is_enabled(),
                configured_pair_ready=self._is_pair_configured(),
                attention_category=att_cat,
                attention_title=att_title,
                attention_explanation=att_expl,
                conflict_files_count=conflict_count,
            )

    def _on_coordinator_phase_change(self, phase: str) -> None:
        with self._state_lock:
            if self._state == STATE_PAUSING:
                # Mantém indicação explícita de PAUSANDO enquanto o ciclo atual termina
                self._detail_message = (
                    "Pausando sincronização automática: aguardando término seguro da operação atual..."
                )
                return
            if phase == "VERIFYING":
                self._state = STATE_VERIFYING
                self._detail_message = (
                    "Verificando acessibilidade, marcadores .brisasync_check e limites de exclusão..."
                )
            elif phase == "SYNCING":
                self._state = STATE_SYNCING
                self._detail_message = (
                    "Sincronizando arquivos bidirecionalmente via rclone bisync..."
                )

    def _check_preconditions_before_cycle(self) -> tuple[bool, str, str]:
        """Verifica cofre, credenciais e configuração antes de iniciar um ciclo.

        Jamais abre o navegador a partir do serviço em segundo plano.
        Retorna `(ok, target_state_if_false, detail_message)`.
        """
        if self.local_pair_config is not None:
            return True, STATE_WAITING, ""

        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        if not local_cfg or not remote_cfg:
            return (
                False,
                STATE_WAITING,
                "Aguardando configuração da pasta local e da pasta remota na interface.",
            )

        # Rejeita novo par com pasta local não vazia antes de ativar agendamento ou ciclo
        is_init = self.database.is_baseline_initialized(
            local_folder=local_cfg.folder_path,
            remote_folder_id=remote_cfg.folder_id,
        )
        if not is_init:
            local_p = Path(local_cfg.folder_path).expanduser()
            if local_p.is_dir():
                items = list(local_p.iterdir())
                if items:
                    sample = ", ".join(e.name for e in items[:3])
                    return (
                        False,
                        STATE_ATTENTION_REQUIRED,
                        f"Para a primeira sincronização com '{remote_cfg.folder_name}', "
                        f"a pasta local deve estar dedicada e vazia ({len(items)} item(ns) encontrado(s) em {local_p.name}: {sample}). "
                        f"Escolha outra pasta vazia.",
                    )

        if hasattr(self.credential_store, "is_vault_locked") and self.credential_store.is_vault_locked() is True:
            return (
                False,
                STATE_ATTENTION_REQUIRED,
                "Cofre da sessão bloqueado ou indisponível. Aguardando desbloqueio sem abrir navegador.",
            )

        try:
            try:
                creds = self.credential_store.load_credentials(interactive=False)
            except TypeError:
                creds = self.credential_store.load_credentials()
        except VaultUnavailableError as exc:
            return (
                False,
                STATE_ATTENTION_REQUIRED,
                f"Cofre da sessão bloqueado ou indisponível ({exc}). Aguardando desbloqueio sem abrir navegador.",
            )

        if not creds or not creds.access_token or not creds.refresh_token:
            return (
                False,
                STATE_WAITING,
                "Nenhuma conta Google conectada. Conecte a conta pela janela do BrisaSync.",
            )

        if not creds.has_drive_scope:
            return (
                False,
                STATE_ATTENTION_REQUIRED,
                "Acesso ao Google Drive não concedido. Reconecte a conta pela interface e marque a permissão do Drive.",
            )

        return True, STATE_WAITING, ""

    def _run_single_sync_cycle(self) -> None:
        with self._state_lock:
            if self._shutdown_requested:
                return
            ok, target_state, msg = self._check_preconditions_before_cycle()
            if not ok:
                self._state = (
                    STATE_PAUSED
                    if (self._auto_sync_paused and target_state == STATE_WAITING)
                    else target_state
                )
                self._detail_message = msg
                self._last_error_reason = msg if target_state == STATE_ATTENTION_REQUIRED else None
                self._next_scheduled_epoch = (
                    None
                    if (self._auto_sync_paused or target_state == STATE_ATTENTION_REQUIRED or target_state == STATE_WAITING)
                    else (time.time() + float(self._sync_interval_seconds))
                )
                return

            self._is_cycle_active = True
            self._state = STATE_VERIFYING
            self._detail_message = "Verificando par configurado antes de sincronizar..."

        result: BisyncExecutionResult | None = None
        caught_exc: Exception | None = None
        try:
            if self.local_pair_config is not None:
                is_init = self.database.is_baseline_initialized(
                    local_folder=str(self.local_pair_config.path1),
                    remote_folder_id=str(self.local_pair_config.path2),
                )
                if not is_init:
                    result = self.coordinator.initialize_pair_baseline(
                        self.local_pair_config,
                        on_phase_change=self._on_coordinator_phase_change,
                    )
                    if result.success and not result.stopped_by_user:
                        self.database.mark_baseline_initialized(
                            local_folder=str(self.local_pair_config.path1),
                            remote_folder_id=str(self.local_pair_config.path2),
                        )
                else:
                    result = self.coordinator.synchronize_pair(
                        self.local_pair_config,
                        on_phase_change=self._on_coordinator_phase_change,
                    )
            else:
                local_cfg = self.database.get_local_sync_folder()
                remote_cfg = self.database.get_remote_sync_folder()
                assert local_cfg is not None and remote_cfg is not None
                result = self.coordinator.synchronize_google_drive_pair(
                    local_folder=local_cfg.folder_path,
                    remote_folder_id=remote_cfg.folder_id,
                    on_phase_change=self._on_coordinator_phase_change,
                )
        except Exception as exc:
            caught_exc = exc

        with self._state_lock:
            self._is_cycle_active = False

            if caught_exc is not None:
                err_str = str(caught_exc)
                self._last_error_reason = err_str
                if isinstance(
                    caught_exc,
                    (
                        VaultUnavailableError,
                        CredentialSyncBackError,
                        DirectoryAccessError,
                    ),
                ):
                    self._last_run_status = "ATTENTION_REQUIRED"
                    self._state = STATE_PAUSED if self._auto_sync_paused else STATE_ATTENTION_REQUIRED
                    self._detail_message = f"Atenção necessária: {err_str}"
                    self._next_scheduled_epoch = (
                        None
                        if self._auto_sync_paused
                        else (time.time() + float(self._sync_interval_seconds))
                    )
                else:
                    category = classify_sync_failure(err_str)
                    if category == "ATTENTION_REQUIRED":
                        self._last_run_status = "ATTENTION_REQUIRED"
                        self._state = STATE_PAUSED if self._auto_sync_paused else STATE_ATTENTION_REQUIRED
                        self._detail_message = f"Atenção necessária: {err_str}"
                        self._next_scheduled_epoch = (
                            None
                            if self._auto_sync_paused
                            else (time.time() + float(self._sync_interval_seconds))
                        )
                    else:
                        self._apply_transient_backoff_locked(err_str)
                return

            assert result is not None
            if result.stopped_by_user:
                self._last_run_status = "STOPPED_BY_USER"
                self._last_error_reason = result.error_reason
                self._pending_sync_coalesced = False
                if self._auto_sync_paused:
                    self._state = STATE_PAUSED
                    self._detail_message = (
                        "Operação interrompida de forma controlada; sincronização automática pausada."
                    )
                    self._next_scheduled_epoch = None
                else:
                    self._state = STATE_WAITING
                    self._detail_message = (
                        "Operação atual parada de forma controlada pelo usuário. Estado recuperável preservado."
                    )
                    self._next_scheduled_epoch = time.time() + float(
                        self._sync_interval_seconds
                    )
                return

            if result.success:
                self._backoff_attempt = 0
                self._backoff_seconds = 0
                self._last_run_status = "SUCCESS"
                self._last_error_reason = None
                if self._auto_sync_paused:
                    self._state = STATE_PAUSED
                    self._detail_message = (
                        "Ciclo concluído com sucesso; sincronização automática pausada."
                    )
                    self._next_scheduled_epoch = None
                else:
                    self._state = STATE_WAITING
                    self._detail_message = (
                        "Sincronização bidirecional confirmada. Aguardando próximo ciclo agendado."
                    )
                    self._next_scheduled_epoch = time.time() + float(
                        self._sync_interval_seconds
                    )
                return

            # Falha reportada pelo rclone bisync
            err_msg = result.error_reason or f"Falha com código {result.exit_code}"
            self._last_error_reason = err_msg
            category = classify_sync_failure(err_msg, result.exit_code)
            if category == "ATTENTION_REQUIRED":
                self._last_run_status = "ATTENTION_REQUIRED"
                self._state = (
                    STATE_PAUSED if self._auto_sync_paused else STATE_ATTENTION_REQUIRED
                )
                self._detail_message = f"Atenção necessária: {err_msg}"
                self._next_scheduled_epoch = (
                    None
                    if (self._auto_sync_paused or target_state == STATE_ATTENTION_REQUIRED)
                    else (time.time() + float(self._sync_interval_seconds))
                )
            else:
                self._apply_transient_backoff_locked(err_msg)

    def _apply_transient_backoff_locked(self, err_msg: str) -> None:
        self._backoff_attempt += 1
        computed = self.base_backoff_seconds * (2 ** (self._backoff_attempt - 1))
        self._backoff_seconds = int(min(computed, self.max_backoff_seconds))
        self._last_run_status = "OFFLINE_BACKOFF"
        if self._auto_sync_paused:
            self._state = STATE_PAUSED
            self._detail_message = (
                f"Sincronização pausada (última tentativa falhou por conexão: {err_msg})."
            )
            self._next_scheduled_epoch = None
        else:
            self._state = STATE_OFFLINE
            self._next_scheduled_epoch = time.time() + float(self._backoff_seconds)
            self._detail_message = (
                f"Falha transitória/conexão (tentativa {self._backoff_attempt}). "
                f"Nova tentativa agendada com espera progressiva em {self._backoff_seconds}s: {err_msg}"
            )

    def _scheduler_loop(self) -> None:
        while True:
            should_run = False
            wait_timeout = 1.0

            with self._state_lock:
                if self._shutdown_requested:
                    break

                now = time.time()
                if self._manual_trigger_requested:
                    self._manual_trigger_requested = False
                    should_run = True
                elif self._pending_sync_coalesced and not self._auto_sync_paused:
                    self._pending_sync_coalesced = False
                    should_run = True
                elif not self._auto_sync_paused and self._state == STATE_ATTENTION_REQUIRED:
                    # Detecta desbloqueio externo do cofre de forma não-interativa
                    err_msg = (self._last_error_reason or "").lower()
                    if ("bloqueado" in err_msg or "locked" in err_msg) and not self.credential_store.is_vault_locked():
                        self._state = STATE_WAITING
                        self._last_error_reason = None
                        self._last_run_status = None
                        self._detail_message = "Cofre de credenciais desbloqueado. Retomando sincronização."
                        should_run = True
                elif not self._auto_sync_paused and self._next_scheduled_epoch is not None:
                    remaining = self._next_scheduled_epoch - now
                    if remaining <= 0:
                        should_run = True
                    else:
                        wait_timeout = min(remaining, 1.0)

            if should_run:
                self._run_single_sync_cycle()
                # Se houve pedido coalescido durante o ciclo recém-encerrado, processa na próxima iteração imediata
                continue

            self._wake_event.wait(timeout=max(0.05, wait_timeout))
            self._wake_event.clear()

    def _accept_loop(self) -> None:
        while True:
            with self._state_lock:
                if self._shutdown_requested:
                    break
            srv = self._server_sock
            if srv is None:
                break
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            client_thread = threading.Thread(
                target=self._handle_client_connection,
                args=(conn,),
                daemon=True,
            )
            client_thread.start()

    def _handle_client_connection(self, conn: socket.socket) -> None:
        with conn:
            conn.settimeout(5.0)
            try:
                verify_peer_credentials(conn)
                raw_data = b""
                while b"\n" not in raw_data and len(raw_data) < 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw_data += chunk
                if not raw_data:
                    return
                request = json.loads(raw_data.decode("utf-8").strip())
                response = self.handle_ipc_command(request)
            except PermissionError as exc:
                response = {"ok": False, "error": str(exc)}
            except Exception as exc:
                response = {"ok": False, "error": f"Erro ao processar comando IPC: {exc}"}

            try:
                conn.sendall((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass

    def handle_ipc_command(self, request: dict[str, Any]) -> dict[str, Any]:
        """Processa um comando IPC autenticado e retorna um dicionário JSON com `status`."""
        action = str(request.get("action", "")).strip()

        if action == "get_status":
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "sync_now":
            with self._state_lock:
                if self._is_cycle_active:
                    # Coalesce múltiplos pedidos enquanto há um ciclo ativo
                    self._pending_sync_coalesced = True
                    coalesced = True
                else:
                    self._manual_trigger_requested = True
                    coalesced = False
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "coalesced": coalesced,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "pause":
            with self._state_lock:
                self._auto_sync_paused = True
                self.database.set_auto_sync_paused(True)
                self._pending_sync_coalesced = False
                self._manual_trigger_requested = False
                self._next_scheduled_epoch = None
                if self._is_cycle_active:
                    self._state = STATE_PAUSING
                    self._detail_message = (
                        "Pausando sincronização automática: aguardando conclusão segura do ciclo ativo..."
                    )
                else:
                    self._state = STATE_PAUSED
                    self._detail_message = "Sincronização automática pausada pelo usuário."
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "resume":
            with self._state_lock:
                self._auto_sync_paused = False
                self.database.set_auto_sync_paused(False)
                self._backoff_attempt = 0
                self._backoff_seconds = 0
                if self._is_cycle_active:
                    self._state = STATE_SYNCING
                    self._detail_message = (
                        "Sincronização automática retomada; ciclo atual em andamento."
                    )
                else:
                    self._state = STATE_WAITING
                    self._detail_message = (
                        "Sincronização automática retomada. Agendando verificação..."
                    )
                    self._next_scheduled_epoch = time.time() + 0.2
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "stop_current":
            with self._state_lock:
                self._pending_sync_coalesced = False
                self._manual_trigger_requested = False
                was_active = self._is_cycle_active
                signal_sent = self.coordinator.request_graceful_stop() if was_active else False
                if was_active:
                    self._detail_message = (
                        "Parando operação atual de forma controlada (SIGTERM enviado ao rclone bisync)..."
                    )
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "was_active": was_active,
                "signal_sent": signal_sent,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "disconnect_account":
            with self._state_lock:
                self._pending_sync_coalesced = False
                self._manual_trigger_requested = False
                self._next_scheduled_epoch = None
                was_active = self._is_cycle_active
                if was_active:
                    self.coordinator.request_graceful_stop()
                self._state = STATE_WAITING
                self._last_error_reason = None
                self._last_run_status = None
                self._detail_message = (
                    "Nenhuma conta Google conectada. Aguardando conexão de conta."
                )
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "was_active": was_active,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "clear_pair":
            with self._state_lock:
                self._pending_sync_coalesced = False
                self._manual_trigger_requested = False
                self._next_scheduled_epoch = None
                self.local_pair_config = None
                was_active = self._is_cycle_active
                if was_active:
                    self.coordinator.request_graceful_stop()
                self._state = STATE_WAITING
                self._detail_message = (
                    "Vínculo de pastas removido. Nenhum par de sincronização configurado."
                )
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "account_connected":
            with self._state_lock:
                self._last_error_reason = None
                self._last_run_status = None
                self._state = STATE_WAITING
                self._detail_message = "Conta Google conectada. Pronto para verificar pastas."
                self._next_scheduled_epoch = (
                    time.time() + float(self._sync_interval_seconds)
                    if not self._auto_sync_paused
                    else None
                )
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "set_interval":
            seconds = int(request.get("interval_seconds", 300))
            with self._state_lock:
                self.database.set_sync_interval_seconds(seconds)
                self._sync_interval_seconds = self.database.get_sync_interval_seconds()
                if not self._auto_sync_paused and not self._is_cycle_active:
                    self._next_scheduled_epoch = time.time() + float(
                        self._sync_interval_seconds
                    )
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "set_autostart":
            enabled = bool(request.get("enabled", False))
            if enabled:
                self.autostart_manager.enable()
            else:
                self.autostart_manager.disable()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "vault_unlocked":
            with self._state_lock:
                if not self.credential_store.is_vault_locked():
                    if self._state == STATE_ATTENTION_REQUIRED:
                        self._state = STATE_WAITING
                        self._last_error_reason = None
                        self._last_run_status = None
                        self._detail_message = "Cofre desbloqueado pela interface. Pronto para sincronizar."
                    self._manual_trigger_requested = True
            self._wake_event.set()
            return {
                "ok": True,
                "action": action,
                "status": self.get_status_snapshot().to_dict(),
            }

        if action == "shutdown_service":
            self.request_shutdown()
            return {
                "ok": True,
                "action": action,
                "shutting_down": True,
                "status": self.get_status_snapshot().to_dict(),
            }

        return {
            "ok": False,
            "error": f"Ação IPC desconhecida: {action!r}",
            "status": self.get_status_snapshot().to_dict(),
        }

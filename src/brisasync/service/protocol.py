"""Protocolo IPC local restrito ao usuário da sessão (`AF_UNIX` + `SO_PEERCRED`) e estados do serviço."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import socket
import struct
from typing import Any

from brisasync.platform_compat import (
    get_current_uid,
    get_runtime_dir,
    is_windows,
)

STATE_WAITING = "WAITING"
STATE_VERIFYING = "VERIFYING"
STATE_SYNCING = "SYNCING"
STATE_PAUSING = "PAUSING"
STATE_PAUSED = "PAUSED"
STATE_OFFLINE = "OFFLINE"
STATE_ATTENTION_REQUIRED = "ATTENTION_REQUIRED"

STATE_LABELS: dict[str, str] = {
    STATE_WAITING: "AGUARDANDO",
    STATE_VERIFYING: "VERIFICANDO",
    STATE_SYNCING: "SINCRONIZANDO",
    STATE_PAUSING: "PAUSANDO",
    STATE_PAUSED: "PAUSADO",
    STATE_OFFLINE: "SEM CONEXÃO",
    STATE_ATTENTION_REQUIRED: "ATENÇÃO NECESSÁRIA",
}

ATTENTION_AUTH_EXPIRED = "AUTH_EXPIRED"
ATTENTION_VAULT_LOCKED = "VAULT_LOCKED"
ATTENTION_CONFLICT_DETECTED = "CONFLICT_DETECTED"
ATTENTION_PERSISTENT_FAILURE = "PERSISTENT_FAILURE"
ATTENTION_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


def default_service_runtime_dir() -> Path:
    """Retorna o diretório de runtime restrito ao usuário para socket IPC e lock do serviço."""
    return get_runtime_dir()


def default_service_socket_path() -> Path:
    """Retorna o caminho padrão do socket `AF_UNIX` do serviço da sessão do usuário."""
    env_override = os.environ.get("BRISASYNC_SOCKET_PATH", "").strip()
    if env_override:
        sock_path = Path(env_override).expanduser().resolve()
        sock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not is_windows():
            try:
                os.chmod(sock_path.parent, 0o700)
            except OSError:
                pass
        return sock_path
    return default_service_runtime_dir() / "service.sock"


def verify_peer_credentials(conn: socket.socket) -> tuple[int, int, int]:
    """Verifica no kernel (SO_PEERCRED) que o par conectado pertence ao mesmo UID da sessão."""
    if hasattr(socket, "SO_PEERCRED"):
        fmt = "3i"
        cred_size = struct.calcsize(fmt)
        raw = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, cred_size)
        peer_pid, peer_uid, peer_gid = struct.unpack(fmt, raw)
        my_uid = get_current_uid()
        if peer_uid != my_uid:
            raise PermissionError(
                f"Conexão IPC rejeitada: peer UID ({peer_uid}) difere do usuário da sessão ({my_uid})."
            )
        return int(peer_pid), int(peer_uid), int(peer_gid)

    # Plataformas sem SO_PEERCRED (ex.: Windows com AF_UNIX):
    # O diretório do socket já é protegido pelas permissões de usuário (NTFS ACL).
    return int(os.getpid()), 0, 0


@dataclass(frozen=True)
class ServiceStatusSnapshot:
    """Instantâneo auditável e completo do estado real do serviço de sincronização."""

    service_pid: int
    state: str
    state_label: str
    detail_message: str
    is_cycle_active: bool
    active_rclone_pid: int | None
    pending_sync_coalesced: bool
    auto_sync_paused: bool
    sync_interval_seconds: int
    next_scheduled_sync_at: str | None
    backoff_attempt: int
    backoff_seconds: int
    last_confirmed_sync_at: str | None
    last_run_status: str | None
    last_error_reason: str | None
    autostart_enabled: bool
    configured_pair_ready: bool
    attention_category: str | None = None
    attention_title: str | None = None
    attention_explanation: str | None = None
    conflict_files_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceStatusSnapshot:
        state_code = str(data.get("state", STATE_WAITING))
        return cls(
            service_pid=int(data.get("service_pid", 0)),
            state=state_code,
            state_label=str(
                data.get("state_label", STATE_LABELS.get(state_code, state_code))
            ),
            detail_message=str(data.get("detail_message", "")),
            is_cycle_active=bool(data.get("is_cycle_active", False)),
            active_rclone_pid=(
                int(data["active_rclone_pid"])
                if data.get("active_rclone_pid") is not None
                else None
            ),
            pending_sync_coalesced=bool(data.get("pending_sync_coalesced", False)),
            auto_sync_paused=bool(data.get("auto_sync_paused", False)),
            sync_interval_seconds=int(data.get("sync_interval_seconds", 300)),
            next_scheduled_sync_at=(
                str(data["next_scheduled_sync_at"])
                if data.get("next_scheduled_sync_at")
                else None
            ),
            backoff_attempt=int(data.get("backoff_attempt", 0)),
            backoff_seconds=int(data.get("backoff_seconds", 0)),
            last_confirmed_sync_at=(
                str(data["last_confirmed_sync_at"])
                if data.get("last_confirmed_sync_at")
                else None
            ),
            last_run_status=(
                str(data["last_run_status"]) if data.get("last_run_status") else None
            ),
            last_error_reason=(
                str(data["last_error_reason"])
                if data.get("last_error_reason")
                else None
            ),
            autostart_enabled=bool(data.get("autostart_enabled", False)),
            configured_pair_ready=bool(data.get("configured_pair_ready", False)),
            attention_category=(
                str(data["attention_category"])
                if data.get("attention_category")
                else None
            ),
            attention_title=(
                str(data["attention_title"]) if data.get("attention_title") else None
            ),
            attention_explanation=(
                str(data["attention_explanation"])
                if data.get("attention_explanation")
                else None
            ),
            conflict_files_count=int(data.get("conflict_files_count", 0)),
        )


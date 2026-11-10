"""Serviço de sessão do usuário e controle IPC local (`AF_UNIX`) do BrisaSync."""

from brisasync.service.autostart import (
    BrisaAutostartCoordinator,
    SystemdUserAutostartManager,
    XDGAutostartManager,
)
from brisasync.service.daemon import BrisaSessionServiceDaemon
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.service.protocol import (
    STATE_LABELS,
    ServiceStatusSnapshot,
    default_service_runtime_dir,
    default_service_socket_path,
)

__all__ = [
    "BrisaAutostartCoordinator",
    "BrisaSessionServiceDaemon",
    "STATE_LABELS",
    "ServiceIPCClient",
    "ServiceStatusSnapshot",
    "SystemdUserAutostartManager",
    "XDGAutostartManager",
    "default_service_runtime_dir",
    "default_service_socket_path",
]


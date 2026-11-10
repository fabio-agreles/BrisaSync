"""Workers QThread para OAuth, listagem de pastas de configuração e comandos IPC ao serviço da sessão."""

from __future__ import annotations

import threading
from typing import Any

from PySide6.QtCore import QThread, Signal

from brisasync.backend.rclone_engine import (
    RcloneBisyncEngine,
    RemoteDirectoryEntry,
)
from brisasync.credentials.oauth_google import (
    GoogleOAuthDesktopClient,
    OAuthClientConfig,
)
from brisasync.credentials.rclone_bridge import REMOTE_NAME, RcloneEncryptedBridge
from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.service.protocol import ServiceStatusSnapshot


class OAuthConnectWorker(QThread):
    """Executa o fluxo OAuth 2.0 Desktop (PKCE S256 + Loopback) fora da thread da UI."""

    succeeded = Signal(object)  # OAuthCredentials
    failed = Signal(str)

    # Aliases de compatibilidade para contratos de sinal
    oauth_succeeded = succeeded
    oauth_failed = failed

    def __init__(
        self,
        client_config: OAuthClientConfig,
        credential_store: CredentialStore,
        bridge: RcloneEncryptedBridge,
    ) -> None:
        super().__init__()
        self.client_config = client_config
        self.credential_store = credential_store
        self.bridge = bridge
        self.cancel_event = threading.Event()

    def request_cancel(self) -> None:
        self.cancel_event.set()

    def cancel(self) -> None:
        """Alias para request_cancel para manter consistência de chamada."""
        self.request_cancel()

    def run(self) -> None:
        try:
            # Antes de abrir o navegador, valida que o cofre da sessão está acessível
            self.credential_store.verify_vault_operation()
            oauth_client = GoogleOAuthDesktopClient(self.client_config)
            creds: OAuthCredentials = oauth_client.authorize_interactive(
                timeout_seconds=180.0,
                cancel_event=self.cancel_event,
            )
            self.credential_store.store_credentials(creds)
            self.bridge.materialize_encrypted_config(creds)
            self.succeeded.emit(creds)
        except Exception as exc:
            if self.cancel_event.is_set():
                self.failed.emit("Operação cancelada pelo usuário.")
            else:
                self.failed.emit(str(exc))


class RemoteFoldersWorker(QThread):
    """Lista ou cria pasta remota dedicada a testes no Google Drive fora da thread da UI."""

    succeeded = Signal(list, object)  # (list[RemoteDirectoryEntry], created_or_none)
    failed = Signal(str)

    # Aliases de compatibilidade para contratos de sinal
    folders_loaded = succeeded
    operation_failed = failed

    def __init__(
        self,
        arg1: Any = None,
        arg2: Any = None,
        *,
        bridge: RcloneEncryptedBridge | None = None,
        engine: RcloneBisyncEngine | None = None,
        action: str = "list",
        folder_name: str | None = None,
        create_folder_name: str | None = None,
    ) -> None:
        super().__init__()
        if isinstance(arg1, RcloneEncryptedBridge):
            resolved_bridge = arg1
            bin_path = getattr(resolved_bridge, "rclone_binary", getattr(resolved_bridge, "rclone_path", None))
            resolved_engine = arg2 or engine or RcloneBisyncEngine(bin_path)
        elif isinstance(arg1, RcloneBisyncEngine):
            resolved_engine = arg1
            resolved_bridge = arg2 or bridge
        else:
            resolved_bridge = bridge or (arg2 if isinstance(arg2, RcloneEncryptedBridge) else None)
            resolved_engine = engine or (arg1 if isinstance(arg1, RcloneBisyncEngine) else None)
            if resolved_engine is None and resolved_bridge is not None:
                bin_path = getattr(resolved_bridge, "rclone_binary", getattr(resolved_bridge, "rclone_path", None))
                resolved_engine = RcloneBisyncEngine(bin_path)

        if resolved_bridge is None:
            raise ValueError("RcloneEncryptedBridge é obrigatório para RemoteFoldersWorker")

        self.bridge = resolved_bridge
        self.engine = resolved_engine
        self.action = action
        self.create_folder_name = folder_name or create_folder_name

    def run(self) -> None:
        try:
            with self.bridge.authenticated_rclone_session() as env:
                created_entry: RemoteDirectoryEntry | None = None
                if (self.action == "create" and self.create_folder_name) or (
                    self.create_folder_name and self.action != "list"
                ):
                    created_entry = self.engine.create_remote_directory(
                        f"{REMOTE_NAME}:",
                        self.create_folder_name,
                        env=env,
                    )
                entries = self.engine.list_remote_directories(
                    f"{REMOTE_NAME}:",
                    env=env,
                )
            self.succeeded.emit(entries, created_entry)
        except Exception as exc:
            self.failed.emit(str(exc))


class ServiceCommandWorker(QThread):
    """Envia comandos de controle ao serviço da sessão (`BrisaSessionServiceDaemon`) via IPC local (`AF_UNIX`)."""

    succeeded = Signal(str, object, object)  # (action, ServiceStatusSnapshot, extra_info)
    failed = Signal(str, str)  # (action, error_message)

    # Aliases de compatibilidade para contratos de sinal
    command_succeeded = succeeded
    command_failed = failed

    def __init__(
        self,
        ipc_client: ServiceIPCClient,
        action: str,
        *,
        payload: dict[str, Any] | None = None,
        ensure_running: bool = True,
    ) -> None:
        super().__init__()
        self.ipc_client = ipc_client
        self.action = action
        self.payload = payload or {}
        self.ensure_running = ensure_running

    def run(self) -> None:
        try:
            if self.ensure_running and self.action != "shutdown_service":
                self.ipc_client.ensure_service_running()

            extra: Any = None
            if self.action == "get_status":
                snapshot: ServiceStatusSnapshot = self.ipc_client.get_status()
            elif self.action == "sync_now":
                snapshot, coalesced = self.ipc_client.sync_now()
                extra = coalesced
            elif self.action == "pause":
                snapshot = self.ipc_client.pause()
            elif self.action == "resume":
                snapshot = self.ipc_client.resume()
            elif self.action == "stop_current":
                snapshot = self.ipc_client.stop_current()
            elif self.action == "set_interval":
                snapshot = self.ipc_client.set_interval(
                    int(self.payload.get("interval_seconds", 300))
                )
            elif self.action == "set_autostart":
                snapshot = self.ipc_client.set_autostart(
                    bool(self.payload.get("enabled", False))
                )
            elif self.action == "shutdown_service":
                snapshot = self.ipc_client.shutdown_service()
            elif self.action == "vault_unlocked":
                snapshot = self.ipc_client.notify_vault_unlocked()
            else:
                raise ValueError(f"Ação IPC não suportada pelo worker: {self.action!r}")

            self.succeeded.emit(self.action, snapshot, extra)
        except Exception as exc:
            self.failed.emit(self.action, str(exc))


class UnlockVaultWorker(QThread):
    """Executa a tentativa explícita de desbloqueio interativo do cofre fora da thread da UI."""

    succeeded = Signal(object)  # OAuthCredentials | None
    failed = Signal(str)

    def __init__(
        self,
        credential_store: CredentialStore,
        bridge: RcloneEncryptedBridge | None = None,
        parent: Any = None,
    ) -> None:
        super().__init__(parent)
        self.credential_store = credential_store
        self.bridge = bridge

    def run(self) -> None:
        try:
            creds = self.credential_store.load_credentials(interactive=True)
            if creds and self.bridge is not None:
                try:
                    self.bridge.materialize_encrypted_config(creds)
                except Exception:
                    pass
            self.succeeded.emit(creds)
        except Exception as exc:
            self.failed.emit(str(exc))


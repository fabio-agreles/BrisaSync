"""Controle de instância única do componente gráfico (`ui.sock` via `AF_UNIX` + `SO_PEERCRED`).

Quando o usuário abre novamente o BrisaSync pelo lançador (`.desktop`) ou CLI enquanto
o processo gráfico já está ativo (por exemplo, oculto na bandeja do sistema), a nova
invocação envia `{"action": "show_window"}` ao socket local e encerra imediatamente,
fazendo o processo gráfico existente restaurar e focar o painel sem duplicar componentes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from brisasync.service.protocol import (
    default_service_runtime_dir,
    verify_peer_credentials,
)
from brisasync.platform_compat import is_windows, lock_file, unlock_file


def default_ui_socket_path() -> Path:
    env_override = os.environ.get("BRISASYNC_UI_SOCKET_PATH", "").strip()
    if env_override:
        sock = Path(env_override).expanduser().resolve()
        sock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(sock.parent, 0o700)
        except OSError:
            pass
        return sock
    return default_service_runtime_dir() / "ui.sock"


def try_activate_existing_ui(
    socket_path: Path | str | None = None,
    timeout: float = 1.5,
    show_window: bool = True,
) -> bool:
    """Se já houver um componente gráfico ativo na sessão, solicita abertura do painel (se show_window=True) e retorna True."""
    target = (
        Path(socket_path).expanduser().resolve()
        if socket_path is not None
        else default_ui_socket_path()
    )
    if not target.exists():
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(str(target))
            action = "show_window" if show_window else "ping"
            sock.sendall((json.dumps({"action": action}) + "\n").encode("utf-8"))
            raw = sock.recv(4096)
            if not raw:
                return False
            resp = json.loads(raw.decode("utf-8").strip())
            return bool(isinstance(resp, dict) and resp.get("ok") is True)
    except (OSError, json.JSONDecodeError):
        return False


class UISingleInstanceServer(QObject):
    """Servidor IPC leve no processo gráfico para receber pedidos de reabertura do painel."""

    show_window_requested = Signal()
    _server_registry: list[UISingleInstanceServer] = []

    def __init__(
        self,
        socket_path: Path | str | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.socket_path = (
            Path(socket_path).expanduser().resolve()
            if socket_path is not None
            else default_ui_socket_path()
        )
        self.lock_path = self.socket_path.with_name(f"{self.socket_path.name}.lock")
        self._lock_fd: int | None = None
        self._server_sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._pending_show_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._dispatch_timer = QTimer(self)
        self._dispatch_timer.setInterval(50)
        self._dispatch_timer.timeout.connect(self._poll_pending_requests)
        UISingleInstanceServer._server_registry.append(self)

    def _poll_pending_requests(self) -> None:
        if self._pending_show_event.is_set():
            self._pending_show_event.clear()
            self.show_window_requested.emit()

    def start(self) -> bool:
        """Tenta adquirir o lock de instância única da UI e iniciar o listener `AF_UNIX`."""
        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.socket_path.parent, 0o700)
        except OSError:
            pass

        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            lock_file(fd, exclusive=True, non_blocking=True)
        except BlockingIOError:
            os.close(fd)
            return False

        self._lock_fd = fd
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
        srv.listen(8)
        srv.settimeout(0.4)
        self._server_sock = srv
        self._stop_event.clear()
        self._pending_show_event.clear()

        self._thread = threading.Thread(
            target=self._accept_loop,
            name="BrisaSync-UI-SingleInstance",
            daemon=True,
        )
        self._thread.start()
        self._dispatch_timer.start()
        return True

    def stop(self) -> None:
        self._dispatch_timer.stop()
        self._stop_event.set()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        try:
            self.socket_path.unlink(missing_ok=True)
        except OSError:
            pass
        if self._lock_fd is not None:
            try:
                unlock_file(self._lock_fd)
            except OSError:
                pass
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None

    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            srv = self._server_sock
            if srv is None:
                break
            try:
                conn, _ = srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with conn:
                conn.settimeout(2.0)
                try:
                    verify_peer_credentials(conn)
                    data = conn.recv(4096).decode("utf-8", errors="replace").strip()
                    req = json.loads(data) if data else {}
                    action = req.get("action")
                    if action == "show_window":
                        self._pending_show_event.set()
                        conn.sendall(b'{"ok": true}\n')
                    elif action == "ping":
                        conn.sendall(b'{"ok": true}\n')
                    else:
                        conn.sendall(b'{"ok": false}\n')
                except Exception:
                    try:
                        conn.sendall(b'{"ok": false}\n')
                    except OSError:
                        pass

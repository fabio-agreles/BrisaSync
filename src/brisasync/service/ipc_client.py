"""Cliente IPC local (`AF_UNIX`) para a interface consultar e controlar o serviço da sessão."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from typing import Any

from brisasync.service.protocol import (
    ServiceStatusSnapshot,
    default_service_socket_path,
)
from brisasync.platform_compat import (
    get_background_popen_kwargs,
    is_windows,
    lock_file,
    unlock_file,
)


class ServiceUnavailableError(RuntimeError):
    """Levantada quando o serviço de sessão não está em execução ou não responde no socket IPC."""


class ServiceIPCClient:
    """Cliente IPC local restrito ao usuário (`AF_UNIX`) com garantia de instância única ao iniciar."""

    def __init__(
        self,
        *,
        socket_path: Path | str | None = None,
        db_path: Path | str | None = None,
        timeout: float = 3.0,
    ) -> None:
        self.socket_path = (
            Path(socket_path).expanduser().resolve()
            if socket_path is not None
            else default_service_socket_path()
        )
        self.db_path = Path(db_path).expanduser().resolve() if db_path is not None else None
        self.timeout = timeout

    def send_command(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Envia um comando JSON ao socket `AF_UNIX` do serviço e retorna a resposta."""
        if not self.socket_path.exists():
            raise ServiceUnavailableError(
                f"Socket do serviço não encontrado em {self.socket_path}."
            )
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(str(self.socket_path))
                raw_msg = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
                sock.sendall(raw_msg)
                buf = b""
                while b"\n" not in buf and len(buf) < 65536:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
        except OSError as exc:
            raise ServiceUnavailableError(
                f"Não foi possível conectar ao serviço em {self.socket_path}: {exc}"
            ) from exc

        if not buf:
            raise ServiceUnavailableError("Resposta vazia do serviço IPC.")
        try:
            resp = json.loads(buf.decode("utf-8").strip())
        except json.JSONDecodeError as exc:
            raise ServiceUnavailableError("Resposta JSON inválida do serviço IPC.") from exc

        if not isinstance(resp, dict):
            raise ServiceUnavailableError("Formato de resposta inesperado do serviço IPC.")
        if not resp.get("ok", False):
            raise RuntimeError(str(resp.get("error", "Falha desconhecida no comando IPC.")))
        return resp

    def is_service_running(self) -> bool:
        try:
            self.get_status()
            return True
        except Exception:
            return False

    def get_status(self) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "get_status"})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def ensure_service_running(self, startup_timeout: float = 6.0) -> ServiceStatusSnapshot:
        """Garante que o serviço da sessão está ativo, iniciando-o sob lock exclusivo se necessário.

        Duas instâncias da interface jamais conseguem iniciar dois serviços concorrentes.
        """
        try:
            return self.get_status()
        except ServiceUnavailableError:
            pass

        self.socket_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        spawn_lock_path = self.socket_path.with_name(f"{self.socket_path.name}.spawn.lock")
        fd = os.open(spawn_lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            lock_file(fd, exclusive=True)
            # Verifica novamente após obter o lock de spawn (outra instância pode ter acabado de iniciar)
            try:
                return self.get_status()
            except ServiceUnavailableError:
                pass

            if getattr(sys, "frozen", False):
                cmd = [
                    sys.executable,
                    "--service",
                    "--socket-path",
                    str(self.socket_path),
                ]
            else:
                cmd = [
                    sys.executable,
                    "-m",
                    "brisasync.main",
                    "--service",
                    "--socket-path",
                    str(self.socket_path),
                ]
            if self.db_path is not None:
                cmd.extend(["--db-path", str(self.db_path)])

            env = os.environ.copy()
            src_dir = str(Path(__file__).resolve().parents[2])
            existing_py = env.get("PYTHONPATH", "")
            sep = ";" if is_windows() else ":"
            env["PYTHONPATH"] = f"{src_dir}{sep}{existing_py}" if existing_py else src_dir

            popen_kwargs = get_background_popen_kwargs()
            subprocess.Popen(
                cmd,
                env=env,
                **popen_kwargs,
            )

            deadline = time.time() + startup_timeout
            last_err: Exception | None = None
            while time.time() < deadline:
                try:
                    return self.get_status()
                except Exception as exc:
                    last_err = exc
                    time.sleep(0.08)
            raise ServiceUnavailableError(
                f"Não foi possível iniciar o serviço da sessão em {startup_timeout}s: {last_err}"
            )
        finally:
            try:
                unlock_file(fd)
            except OSError:
                pass
            os.close(fd)

    def sync_now(self) -> tuple[ServiceStatusSnapshot, bool]:
        resp = self.send_command({"action": "sync_now"})
        return (
            ServiceStatusSnapshot.from_dict(resp.get("status", {})),
            bool(resp.get("coalesced", False)),
        )

    def pause(self) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "pause"})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def resume(self) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "resume"})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def stop_current(self) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "stop_current"})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def set_interval(self, interval_seconds: int) -> ServiceStatusSnapshot:
        resp = self.send_command(
            {"action": "set_interval", "interval_seconds": int(interval_seconds)}
        )
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def set_autostart(self, enabled: bool) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "set_autostart", "enabled": bool(enabled)})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def shutdown_service(self) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "shutdown_service"})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def execute_command(self, action: str, **kwargs: Any) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": action, **kwargs})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))

    def notify_vault_unlocked(self) -> ServiceStatusSnapshot:
        resp = self.send_command({"action": "vault_unlocked"})
        return ServiceStatusSnapshot.from_dict(resp.get("status", {}))


"""Gerenciador de autoinício opcional na sessão do usuário via `systemd --user` (sem `sudo`).

Diretrizes de arquitetura:
1. Ativa exclusivamente UM mecanismo de autoinício (`systemd --user` em
   `~/.config/systemd/user/brisasync.service`), evitando mecanismos concorrentes
   (nunca grava `~/.config/autostart/brisasync.desktop`).
2. Totalmente reversível pelo usuário sem `sudo`: `enable()` instala a unit e executa
   `systemctl --user daemon-reload` + `systemctl --user enable brisasync.service`;
   `disable()` executa `systemctl --user disable brisasync.service`, remove o arquivo
   unit e recarrega o daemon do usuário.
"""

from __future__ import annotations

import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

from brisasync.platform_compat import (
    disable_windows_autostart,
    is_windows,
    is_windows_autostart_enabled,
    set_windows_autostart,
)

UNIT_FILENAME = "brisasync.service"
DESKTOP_FILENAME = "brisasync.desktop"


def default_systemd_user_dir() -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_config) if xdg_config else (Path.home() / ".config")
    return base / "systemd" / "user"


def default_xdg_autostart_dir() -> Path:
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_config) if xdg_config else (Path.home() / ".config")
    return base / "autostart"


def xdg_autostart_desktop_path() -> Path:
    return default_xdg_autostart_dir() / DESKTOP_FILENAME


def competing_xdg_autostart_desktop_path() -> Path:
    return xdg_autostart_desktop_path()


class SystemdUserAutostartManager:
    """Controla a unit `brisasync.service` no `systemd --user` da sessão."""

    def __init__(
        self,
        unit_dir: Path | None = None,
        *,
        db_path: Path | None = None,
        python_executable: str | None = None,
        service_executable: str | Path | None = None,
        run_systemctl: bool = True,
    ) -> None:
        self.unit_dir = Path(unit_dir) if unit_dir is not None else default_systemd_user_dir()
        self.unit_path = self.unit_dir / UNIT_FILENAME
        self.db_path = Path(db_path).resolve() if db_path is not None else None
        self.python_executable = python_executable or sys.executable
        self.service_executable = (
            str(Path(service_executable).expanduser().resolve())
            if service_executable is not None
            else None
        )
        self.run_systemctl = run_systemctl

    @classmethod
    def _is_installed_package_layout(cls) -> bool:
        mod_path = Path(__file__).resolve().as_posix()
        return "/site-packages/" in mod_path or "/dist-packages/" in mod_path

    def _resolve_installed_service_binary(self) -> str | None:
        if self.service_executable:
            return self.service_executable

        appimage = os.environ.get("APPIMAGE")
        if appimage and Path(appimage).is_file():
            return appimage

        if getattr(sys, "frozen", False):
            return sys.executable

        if self._is_installed_package_layout():
            candidates = (
                Path(sys.prefix) / "bin" / "brisasync",
                Path(self.python_executable).resolve().with_name("brisasync"),
                Path("/usr/bin/brisasync"),
            )
            for cand in candidates:
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
            which_bin = shutil.which("brisasync")
            if which_bin:
                return which_bin
        return None

    def render_unit_content(self) -> str:
        """Gera o conteúdo da unit `systemd --user` priorizando o caminho instalado do pacote."""
        installed_bin = self._resolve_installed_service_binary()
        if installed_bin is not None:
            cmd_parts = [installed_bin, "--service"]
            if self.db_path is not None:
                cmd_parts.extend(["--db-path", str(self.db_path)])
            exec_start = " ".join(shlex.quote(part) for part in cmd_parts)
            return (
                "[Unit]\n"
                "Description=BrisaSync — Servico de Sincronizacao Bidirecional da Sessao do Usuario\n"
                "After=graphical-session.target network-online.target\n"
                "Wants=network-online.target\n"
                "\n"
                "[Service]\n"
                "Type=simple\n"
                "WorkingDirectory=%h\n"
                f"ExecStart={exec_start}\n"
                "Restart=on-failure\n"
                "RestartSec=10\n"
                "\n"
                "[Install]\n"
                "WantedBy=default.target\n"
            )

        if self._is_installed_package_layout():
            cmd_parts = [self.python_executable, "-m", "brisasync.main", "--service"]
            if self.db_path is not None:
                cmd_parts.extend(["--db-path", str(self.db_path)])
            exec_start = " ".join(shlex.quote(part) for part in cmd_parts)
            return (
                "[Unit]\n"
                "Description=BrisaSync — Servico de Sincronizacao Bidirecional da Sessao do Usuario\n"
                "After=graphical-session.target network-online.target\n"
                "Wants=network-online.target\n"
                "\n"
                "[Service]\n"
                "Type=simple\n"
                "WorkingDirectory=%h\n"
                f"ExecStart={exec_start}\n"
                "Restart=on-failure\n"
                "RestartSec=10\n"
                "\n"
                "[Install]\n"
                "WantedBy=default.target\n"
            )

        cmd_parts = [self.python_executable, "-m", "brisasync.main", "--service"]
        if self.db_path is not None:
            cmd_parts.extend(["--db-path", str(self.db_path)])
        exec_start = " ".join(shlex.quote(part) for part in cmd_parts)
        src_dir = Path(__file__).resolve().parents[2]
        return (
            "[Unit]\n"
            "Description=BrisaSync — Servico de Sincronizacao Bidirecional da Sessao do Usuario\n"
            "After=graphical-session.target network-online.target\n"
            "Wants=network-online.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={src_dir.parent}\n"
            f"Environment=PYTHONPATH={src_dir}\n"
            f"ExecStart={exec_start}\n"
            "Restart=on-failure\n"
            "RestartSec=10\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n"
        )

    def has_competing_xdg_autostart(self) -> bool:
        """Verifica se existe algum arquivo XDG autostart concorrente de serviço em `~/.config/autostart`."""
        legacy_path = competing_xdg_autostart_desktop_path()
        if not legacy_path.is_file():
            return False
        try:
            content = legacy_path.read_text(encoding="utf-8", errors="replace")
            if "X-BrisaSync-Managed=true" in content or "--start-hidden" in content:
                return False
            return "--service" in content
        except OSError:
            return False

    def is_enabled(self) -> bool:
        """Retorna True se o autoinício via `systemd --user` estiver habilitado."""
        if not self.unit_path.is_file():
            return False
        if not self.run_systemctl or shutil.which("systemctl") is None:
            return True
        try:
            proc = subprocess.run(
                ["systemctl", "--user", "is-enabled", UNIT_FILENAME],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            state = (proc.stdout or "").strip().lower()
            return proc.returncode == 0 and state in ("enabled", "enabled-runtime", "static")
        except (OSError, subprocess.SubprocessError):
            return self.unit_path.is_file()

    def enable(self) -> Path:
        """Ativa o autoinício opcional na sessão do usuário via `systemd --user`."""
        if self.has_competing_xdg_autostart():
            raise RuntimeError(
                f"Detectado mecanismo concorrente de autoinício em {competing_xdg_autostart_desktop_path()}. "
                "Remova o arquivo .desktop concorrente para manter apenas o systemd --user ativo."
            )
        self.unit_dir.mkdir(parents=True, exist_ok=True)
        content = self.render_unit_content()
        self.unit_path.write_text(content, encoding="utf-8")
        os.chmod(self.unit_path, 0o644)

        if self.run_systemctl and shutil.which("systemctl") is not None:
            reload_proc = subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if reload_proc.returncode != 0:
                raise RuntimeError(
                    f"Falha ao recarregar systemd --user: {(reload_proc.stderr or '').strip()}"
                )
            enable_proc = subprocess.run(
                ["systemctl", "--user", "enable", UNIT_FILENAME],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            if enable_proc.returncode != 0:
                raise RuntimeError(
                    f"Falha ao habilitar {UNIT_FILENAME} no systemd --user: {(enable_proc.stderr or '').strip()}"
                )
        return self.unit_path

    def disable(self) -> None:
        """Desativa o autoinício na sessão do usuário e remove a unit `brisasync.service`."""
        if self.run_systemctl and shutil.which("systemctl") is not None:
            subprocess.run(
                ["systemctl", "--user", "disable", UNIT_FILENAME],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        try:
            self.unit_path.unlink(missing_ok=True)
        except OSError:
            pass
        wanted_symlink = self.unit_dir / "default.target.wants" / UNIT_FILENAME
        try:
            wanted_symlink.unlink(missing_ok=True)
        except OSError:
            pass
        if self.run_systemctl and shutil.which("systemctl") is not None:
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )


class XDGAutostartManager:
    """Controla o arquivo `brisasync.desktop` em `~/.config/autostart/` para inicialização da interface na bandeja."""

    def __init__(
        self,
        autostart_dir: Path | None = None,
        *,
        db_path: Path | None = None,
        python_executable: str | None = None,
        service_executable: str | Path | None = None,
    ) -> None:
        self.autostart_dir = (
            Path(autostart_dir)
            if autostart_dir is not None
            else default_xdg_autostart_dir()
        )
        self.desktop_path = self.autostart_dir / DESKTOP_FILENAME
        self.db_path = Path(db_path).resolve() if db_path is not None else None
        self.python_executable = python_executable or sys.executable
        self.service_executable = (
            str(Path(service_executable).expanduser().resolve())
            if service_executable is not None
            else None
        )

    @classmethod
    def _is_installed_package_layout(cls) -> bool:
        mod_path = Path(__file__).resolve().as_posix()
        return "/site-packages/" in mod_path or "/dist-packages/" in mod_path

    def _resolve_installed_binary(self) -> str | None:
        if self.service_executable:
            return self.service_executable

        appimage = os.environ.get("APPIMAGE")
        if appimage and Path(appimage).is_file():
            return appimage

        if getattr(sys, "frozen", False):
            return sys.executable

        if self._is_installed_package_layout():
            candidates = (
                Path(sys.prefix) / "bin" / "brisasync",
                Path(self.python_executable).resolve().with_name("brisasync"),
                Path("/usr/bin/brisasync"),
            )
            for cand in candidates:
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
            which_bin = shutil.which("brisasync")
            if which_bin:
                return which_bin
        return None

    def render_desktop_content(self) -> str:
        """Gera o arquivo .desktop para autoinício da interface oculta na bandeja."""
        installed_bin = self._resolve_installed_binary()
        if installed_bin is not None:
            cmd_parts = [installed_bin, "--start-hidden"]
            if self.db_path is not None:
                cmd_parts.extend(["--db-path", str(self.db_path)])
            exec_cmd = " ".join(shlex.quote(p) for p in cmd_parts)
        else:
            cmd_parts = [self.python_executable, "-m", "brisasync.main", "--start-hidden"]
            if self.db_path is not None:
                cmd_parts.extend(["--db-path", str(self.db_path)])
            exec_cmd = " ".join(shlex.quote(p) for p in cmd_parts)

        return (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=BrisaSync\n"
            "GenericName=Sincronizador Google Drive\n"
            "Comment=Sincronização bidirecional em segundo plano (Google Drive)\n"
            f"Exec={exec_cmd}\n"
            "Icon=brisasync\n"
            "Terminal=false\n"
            "Categories=Utility;FileTransfer;Network;Qt;\n"
            "StartupNotify=false\n"
            "X-GNOME-Autostart-enabled=true\n"
            "X-BrisaSync-Managed=true\n"
        )

    def is_enabled(self) -> bool:
        """Verifica se o autoinício da interface gráfica via XDG autostart está ativo."""
        if not self.desktop_path.is_file():
            return False
        try:
            content = self.desktop_path.read_text(encoding="utf-8", errors="replace")
            if "X-GNOME-Autostart-enabled=false" in content or "Hidden=true" in content:
                return False
            return True
        except OSError:
            return self.desktop_path.is_file()

    def enable(self) -> Path:
        """Instala e ativa a entrada XDG autostart em `~/.config/autostart/brisasync.desktop`."""
        self.autostart_dir.mkdir(parents=True, exist_ok=True)
        content = self.render_desktop_content()
        self.desktop_path.write_text(content, encoding="utf-8")
        os.chmod(self.desktop_path, 0o644)
        return self.desktop_path

    def disable(self) -> None:
        """Remove a entrada XDG autostart da interface gráfica."""
        try:
            self.desktop_path.unlink(missing_ok=True)
        except OSError:
            pass


class WindowsRegistryAutostartManager:
    """Gerencia autoinício no Registro do Windows (HKCU Run)."""

    def __init__(
        self,
        app_name: str = "BrisaSync",
        executable_path: str | Path | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.app_name = app_name
        self.executable_path = (
            str(executable_path).strip()
            if executable_path is not None
            else None
        )
        self.db_path = Path(db_path).resolve() if db_path is not None else None

    def _resolve_command(self) -> str:
        if self.executable_path:
            cmd = f'"{self.executable_path}" --start-hidden'
        else:
            exe = shutil.which("brisasync") or sys.executable
            if "brisasync" in Path(exe).name.lower():
                cmd = f'"{exe}" --start-hidden'
            else:
                cmd = f'"{exe}" -m brisasync.main --start-hidden'
        if self.db_path:
            cmd += f' --db-path "{self.db_path}"'
        return cmd

    def is_enabled(self) -> bool:
        return is_windows_autostart_enabled(self.app_name)

    def enable(self) -> str:
        cmd = self._resolve_command()
        set_windows_autostart(self.app_name, cmd)
        return cmd

    def disable(self) -> None:
        disable_windows_autostart(self.app_name)


class BrisaAutostartCoordinator:
    """Coordena os componentes de autoinício do BrisaSync na sessão do usuário:
    - No Linux: Serviço systemd --user (`brisasync.service`) e entrada XDG Autostart (`brisasync.desktop`).
    - No Windows: Chave de inicialização no Registro do Windows (`HKCU Run`).
    """

    def __init__(
        self,
        systemd_manager: SystemdUserAutostartManager | None = None,
        xdg_manager: XDGAutostartManager | None = None,
        win_manager: WindowsRegistryAutostartManager | None = None,
        *,
        unit_dir: Path | None = None,
        autostart_dir: Path | None = None,
        db_path: Path | None = None,
        service_executable: str | Path | None = None,
        run_systemctl: bool = True,
    ) -> None:
        self.win_manager = win_manager or WindowsRegistryAutostartManager(
            executable_path=service_executable,
            db_path=db_path,
        )
        self.systemd_manager = systemd_manager or SystemdUserAutostartManager(
            unit_dir=unit_dir,
            db_path=db_path,
            service_executable=service_executable,
            run_systemctl=run_systemctl,
        )
        self.xdg_manager = xdg_manager or XDGAutostartManager(
            autostart_dir=autostart_dir,
            db_path=db_path,
            service_executable=service_executable,
        )

    @property
    def unit_path(self) -> Path:
        return self.systemd_manager.unit_path

    @property
    def desktop_path(self) -> Path:
        return self.xdg_manager.desktop_path

    def is_enabled(self) -> bool:
        """Retorna True se os componentes de autoinício estiverem habilitados na plataforma ativa."""
        if is_windows():
            return self.win_manager.is_enabled()
        return self.systemd_manager.is_enabled() or self.xdg_manager.is_enabled()

    def sync_state(self) -> None:
        """Garante consistência entre os componentes de autoinício gerenciados."""
        if is_windows():
            return
        sys_on = self.systemd_manager.is_enabled()
        xdg_on = self.xdg_manager.is_enabled()
        if sys_on and not xdg_on:
            self.xdg_manager.enable()
        elif xdg_on and not sys_on:
            self.systemd_manager.enable()

    def enable(self) -> tuple[Path | str, ...]:
        """Habilita o autoinício na sessão do usuário conforme a plataforma."""
        if is_windows():
            cmd = self.win_manager.enable()
            return (cmd,)
        unit_path = self.systemd_manager.enable()
        desktop_path = self.xdg_manager.enable()
        return unit_path, desktop_path

    def disable(self) -> None:
        """Desabilita os componentes de autoinício gerenciados pelo aplicativo, preservando dados."""
        if is_windows():
            self.win_manager.disable()
            return
        self.systemd_manager.disable()
        self.xdg_manager.disable()



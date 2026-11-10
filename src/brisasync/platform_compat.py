"""Camada de compatibilidade multiplataforma do BrisaSync (Linux, macOS e Windows).

Centraliza abstrações de:
1. Bloqueio de arquivos (fcntl.flock no POSIX, msvcrt.locking no Windows).
2. Diretórios canônicos de dados, configuração, cache e runtime (XDG no Linux, AppData no Windows).
3. Parâmetros de criação de subprocessos desacoplados em segundo plano.
4. Armazenamento seguro de credenciais via Windows Credential Manager (Advapi32.dll).
5. Autoinício na inicialização da sessão do Windows (HKCU Run).
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any

# Identificação de Plataforma
def is_windows() -> bool:
    return sys.platform == "win32"


def is_linux() -> bool:
    return sys.platform.startswith("linux")


def is_macos() -> bool:
    return sys.platform == "darwin"


def get_current_uid() -> int:
    """Retorna o UID do usuário corrente no POSIX ou 0 no Windows."""
    if hasattr(os, "getuid"):
        return os.getuid()
    return 0


# Diretórios do Sistema
def get_user_home() -> Path:
    return Path.home()


def get_data_dir() -> Path:
    """Retorna o diretório base para dados persistentes (banco SQLite, baselines rclone)."""
    if is_windows():
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "BrisaSync"
    xdg_data = os.environ.get("XDG_DATA_HOME", "").strip()
    base = Path(xdg_data) if xdg_data else (Path.home() / ".local" / "share")
    return base / "brisasync"


def get_config_dir() -> Path:
    """Retorna o diretório base para configurações do usuário."""
    if is_windows():
        base = Path(os.environ.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
        return base / "BrisaSync"
    xdg_config = os.environ.get("XDG_CONFIG_HOME", "").strip()
    base = Path(xdg_config) if xdg_config else (Path.home() / ".config")
    return base / "brisasync"


def get_cache_dir() -> Path:
    """Retorna o diretório base para caches voláteis."""
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "BrisaSync" / "Cache"
    xdg_cache = os.environ.get("XDG_CACHE_HOME", "").strip()
    base = Path(xdg_cache) if xdg_cache else (Path.home() / ".cache")
    return base / "brisasync"


def get_runtime_dir() -> Path:
    """Retorna o diretório de execução restrito ao usuário para sockets IPC e arquivos de lock."""
    if is_windows():
        base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        run_dir = base / "BrisaSync" / "Run"
        try:
            run_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        return run_dir

    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if xdg_runtime:
        base = Path(xdg_runtime)
    else:
        uid = get_current_uid()
        uid_run = Path(f"/run/user/{uid}")
        base = uid_run if uid_run.is_dir() else (Path.home() / ".cache")
    run_dir = base / "brisasync"
    try:
        run_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        pass
    try:
        os.chmod(run_dir, 0o700)
    except OSError:
        pass
    return run_dir


# Bloqueio de Arquivos Cross-Platform
def lock_file(fd: int, exclusive: bool = True, non_blocking: bool = False) -> None:
    """Aplica bloqueio de arquivo consultivo/mandatório em descritor de arquivo aberto.

    No Linux/macOS, utiliza `fcntl.flock`.
    No Windows, utiliza `msvcrt.locking` a partir da posição inicial do arquivo.
    Lança `BlockingIOError` se `non_blocking=True` e o arquivo já estiver bloqueado por outro processo.
    """
    if is_windows():
        import msvcrt  # type: ignore[import-not-found]

        mode = msvcrt.LK_NBLCK if non_blocking else msvcrt.LK_LOCK
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            # Bloqueia 1 byte da posição 0
            msvcrt.locking(fd, mode, 1)
        except (OSError, IOError) as exc:
            if non_blocking:
                raise BlockingIOError(f"Arquivo bloqueado por outra instância: {exc}") from exc
            raise
    else:
        import fcntl

        flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        if non_blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except (BlockingIOError, OSError) as exc:
            # Em alguns unixes/kernels OSError com errno EAGAIN/EWOULDBLOCK é lançado
            raise BlockingIOError(f"Arquivo bloqueado por outra instância: {exc}") from exc


def unlock_file(fd: int) -> None:
    """Libera o bloqueio do arquivo previamente adquirido."""
    if is_windows():
        import msvcrt  # type: ignore[import-not-found]

        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except (OSError, IOError):
            pass
    else:
        import fcntl

        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


# Configuração de Subprocessos Desacoplados
def get_background_popen_kwargs() -> dict[str, Any]:
    """Retorna argumentos de `subprocess.Popen` para criar um processo em segundo plano invisível e desacoplado."""
    kwargs: dict[str, Any] = {
        "stdin": -3,  # subprocess.DEVNULL
        "stdout": -3,  # subprocess.DEVNULL
        "stderr": -3,  # subprocess.DEVNULL
        "close_fds": True,
    }
    if is_windows():
        # flags no Windows para ocultar console cmd.exe e desvincular o processo pai
        CREATE_NO_WINDOW = 0x08000000
        DETACHED_PROCESS = 0x00000008
        kwargs["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    return kwargs


# Windows Credential Manager
_mock_win_credentials: dict[str, tuple[str, str]] | None = None


def set_mock_win_credentials(storage: dict[str, tuple[str, str]] | None) -> None:
    """Permite testar a lógica do Windows Credential Manager em suítes de teste multiplataforma."""
    global _mock_win_credentials
    _mock_win_credentials = storage


def win_cred_write(target: str, user: str, secret: str) -> bool:
    """Grava credencial no Windows Credential Manager (CRED_TYPE_GENERIC)."""
    if _mock_win_credentials is not None:
        _mock_win_credentials[target] = (user, secret)
        return True

    if not is_windows():
        raise NotImplementedError("Windows Credential Manager disponível apenas no Windows.")

    try:
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        CRED_TYPE_GENERIC = 1
        CRED_PERSIST_LOCAL_MACHINE = 2

        blob_bytes = secret.encode("utf-8")
        blob_buf = ctypes.create_string_buffer(blob_bytes)

        cred = CREDENTIAL()
        cred.Flags = 0
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = target
        cred.Comment = "BrisaSync Credentials"
        cred.CredentialBlobSize = len(blob_bytes)
        cred.CredentialBlob = ctypes.cast(blob_buf, ctypes.POINTER(ctypes.c_char))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = 0
        cred.Attributes = None
        cred.TargetAlias = None
        cred.UserName = user

        advapi32 = ctypes.windll.advapi32
        advapi32.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        advapi32.CredWriteW.restype = wintypes.BOOL

        res = advapi32.CredWriteW(ctypes.byref(cred), 0)
        return bool(res)
    except Exception as exc:
        raise RuntimeError(f"Falha ao gravar credencial no Windows Credential Manager: {exc}") from exc


def win_cred_read(target: str) -> str | None:
    """Lê credencial do Windows Credential Manager."""
    if _mock_win_credentials is not None:
        val = _mock_win_credentials.get(target)
        return val[1] if val else None

    if not is_windows():
        raise NotImplementedError("Windows Credential Manager disponível apenas no Windows.")

    try:
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags", wintypes.DWORD),
                ("Type", wintypes.DWORD),
                ("TargetName", wintypes.LPWSTR),
                ("Comment", wintypes.LPWSTR),
                ("LastWritten", FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob", ctypes.c_char_p),
                ("Persist", wintypes.DWORD),
                ("AttributeCount", wintypes.DWORD),
                ("Attributes", ctypes.c_void_p),
                ("TargetAlias", wintypes.LPWSTR),
                ("UserName", wintypes.LPWSTR),
            ]

        CRED_TYPE_GENERIC = 1
        advapi32 = ctypes.windll.advapi32
        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(CREDENTIAL)),
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None

        pcred = ctypes.POINTER(CREDENTIAL)()
        ok = advapi32.CredReadW(target, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred))
        if not ok or not pcred:
            return None

        try:
            size = pcred.contents.CredentialBlobSize
            blob_ptr = pcred.contents.CredentialBlob
            if not blob_ptr or size <= 0:
                return ""
            raw_bytes = ctypes.string_at(blob_ptr, size)
            return raw_bytes.decode("utf-8")
        finally:
            advapi32.CredFree(pcred)
    except Exception:
        return None


def win_cred_delete(target: str) -> bool:
    """Remove credencial do Windows Credential Manager."""
    if _mock_win_credentials is not None:
        return _mock_win_credentials.pop(target, None) is not None

    if not is_windows():
        raise NotImplementedError("Windows Credential Manager disponível apenas no Windows.")

    try:
        from ctypes import wintypes

        CRED_TYPE_GENERIC = 1
        advapi32 = ctypes.windll.advapi32
        advapi32.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        advapi32.CredDeleteW.restype = wintypes.BOOL
        return bool(advapi32.CredDeleteW(target, CRED_TYPE_GENERIC, 0))
    except Exception:
        return False


# Autoinício no Registro do Windows (HKCU Run)
_mock_winreg_entries: dict[str, str] | None = None


def set_mock_winreg(entries: dict[str, str] | None) -> None:
    """Permite testar o gerenciador de autoinício do Windows em qualquer plataforma."""
    global _mock_winreg_entries
    _mock_winreg_entries = entries


def is_windows_autostart_enabled(app_name: str = "BrisaSync") -> bool:
    if _mock_winreg_entries is not None:
        return app_name in _mock_winreg_entries

    if not is_windows():
        return False

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        ) as key:
            try:
                val, _ = winreg.QueryValueEx(key, app_name)
                return bool(val)
            except FileNotFoundError:
                return False
    except Exception:
        return False


def set_windows_autostart(app_name: str = "BrisaSync", command: str = "") -> None:
    if _mock_winreg_entries is not None:
        _mock_winreg_entries[app_name] = command
        return

    if not is_windows():
        raise NotImplementedError("Autoinício de registro disponível apenas no Windows.")

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, command)
    except Exception as exc:
        raise RuntimeError(f"Falha ao configurar autoinício no Registro do Windows: {exc}") from exc


def disable_windows_autostart(app_name: str = "BrisaSync") -> None:
    if _mock_winreg_entries is not None:
        _mock_winreg_entries.pop(app_name, None)
        return

    if not is_windows():
        return

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            try:
                winreg.DeleteValue(key, app_name)
            except FileNotFoundError:
                pass
    except Exception:
        pass

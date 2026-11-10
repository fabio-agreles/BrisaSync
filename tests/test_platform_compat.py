"""Testes de unidade para a camada de compatibilidade multiplataforma (Linux / Windows)."""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import pytest

from brisasync.platform_compat import (
    disable_windows_autostart,
    get_background_popen_kwargs,
    get_cache_dir,
    get_config_dir,
    get_data_dir,
    get_runtime_dir,
    is_windows_autostart_enabled,
    lock_file,
    set_mock_win_credentials,
    set_mock_winreg,
    set_windows_autostart,
    unlock_file,
    win_cred_delete,
    win_cred_read,
    win_cred_write,
)
from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.service.autostart import (
    BrisaAutostartCoordinator,
    WindowsRegistryAutostartManager,
)


def test_file_locking_exclusive_and_non_blocking() -> None:
    """Valida o funcionamento cross-platform de lock_file e unlock_file."""
    with tempfile.NamedTemporaryFile() as tf:
        fd1 = os.open(tf.name, os.O_RDWR)
        fd2 = os.open(tf.name, os.O_RDWR)
        try:
            lock_file(fd1, exclusive=True, non_blocking=True)
            # Segunda tentativa não bloqueante deve falhar com BlockingIOError
            with pytest.raises(BlockingIOError):
                lock_file(fd2, exclusive=True, non_blocking=True)
            unlock_file(fd1)
            # Após liberar, segunda tentativa deve obter o lock com sucesso
            lock_file(fd2, exclusive=True, non_blocking=True)
            unlock_file(fd2)
        finally:
            os.close(fd1)
            os.close(fd2)


def test_directory_resolution_and_windows_simulation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida a resolução de diretórios de dados, config, cache e runtime em Windows e POSIX."""
    # Cenário POSIX
    monkeypatch.setattr("brisasync.platform_compat.is_windows", lambda: False)
    monkeypatch.setenv("XDG_DATA_HOME", "/custom/share")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/custom/config")
    monkeypatch.setenv("XDG_CACHE_HOME", "/custom/cache")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/custom/run")

    assert get_data_dir() == Path("/custom/share/brisasync")
    assert get_config_dir() == Path("/custom/config/brisasync")
    assert get_cache_dir() == Path("/custom/cache/brisasync")
    assert get_runtime_dir() == Path("/custom/run/brisasync")

    # Cenário Windows
    monkeypatch.setattr("brisasync.platform_compat.is_windows", lambda: True)
    appdata = r"C:\Users\User\AppData\Roaming"
    localappdata = r"C:\Users\User\AppData\Local"
    monkeypatch.setenv("APPDATA", appdata)
    monkeypatch.setenv("LOCALAPPDATA", localappdata)

    assert get_data_dir() == Path(appdata) / "BrisaSync"
    assert get_config_dir() == Path(appdata) / "BrisaSync"
    assert get_cache_dir() == Path(localappdata) / "BrisaSync" / "Cache"
    assert get_runtime_dir() == Path(localappdata) / "BrisaSync" / "Run"


def test_background_popen_kwargs_windows_vs_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida as flags de desacoplamento do processo filho no Windows e no Linux."""
    monkeypatch.setattr("brisasync.platform_compat.is_windows", lambda: False)
    posix_kwargs = get_background_popen_kwargs()
    assert posix_kwargs.get("start_new_session") is True
    assert "creationflags" not in posix_kwargs

    monkeypatch.setattr("brisasync.platform_compat.is_windows", lambda: True)
    win_kwargs = get_background_popen_kwargs()
    assert "start_new_session" not in win_kwargs
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    assert win_kwargs.get("creationflags") == (CREATE_NO_WINDOW | DETACHED_PROCESS)


def test_windows_credential_manager_integration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida o ciclo completo de credenciais sob o backend Windows Credential Manager."""
    mock_store: dict[str, tuple[str, str]] = {}
    set_mock_win_credentials(mock_store)
    try:
        # 1. Teste direto das rotinas
        assert win_cred_write("BrisaSync/test_target", "BrisaSync", "secret_value_123") is True
        assert win_cred_read("BrisaSync/test_target") == "secret_value_123"
        assert win_cred_delete("BrisaSync/test_target") is True
        assert win_cred_read("BrisaSync/test_target") is None

        # 2. Teste integrado com CredentialStore
        monkeypatch.setattr(CredentialStore, "_force_windows_backend", True)
        caps = CredentialStore.probe_capabilities(verify_roundtrip=True)
        assert caps.utility_installed is True
        assert caps.vault_verified is True
        assert caps.active_backend == "Windows Credential Manager"

        with tempfile.TemporaryDirectory() as tmp_dir:
            lock_p = Path(tmp_dir) / "cred.lock"
            store = CredentialStore(lock_path=lock_p)
            creds = OAuthCredentials(
                client_id="win-client-id",
                client_secret="win-secret",
                access_token="ya29.win_token",
                refresh_token="1//win_refresh",
                token_type="Bearer",
                expiry="2030-01-01T00:00:00Z",
                scope="https://www.googleapis.com/auth/drive",
                account_email="win@example.com",
            )
            store.store_credentials(creds)
            loaded = store.load_credentials()
            assert loaded is not None
            assert loaded.account_email == "win@example.com"
            assert loaded.access_token == "ya29.win_token"

            store.delete_credentials()
            assert store.load_credentials() is None
    finally:
        set_mock_win_credentials(None)


def test_windows_autostart_registry_manager(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valida o gerenciamento de autoinício no Registro do Windows (HKCU Run)."""
    mock_reg: dict[str, str] = {}
    set_mock_winreg(mock_reg)
    try:
        assert is_windows_autostart_enabled("BrisaSync") is False
        set_windows_autostart("BrisaSync", '"C:\\Programs\\BrisaSync\\brisasync.exe" --start-hidden')
        assert is_windows_autostart_enabled("BrisaSync") is True
        disable_windows_autostart("BrisaSync")
        assert is_windows_autostart_enabled("BrisaSync") is False

        # Teste com WindowsRegistryAutostartManager
        win_mgr = WindowsRegistryAutostartManager(
            app_name="BrisaSync",
            executable_path="C:\\BrisaSync\\brisasync.exe",
        )
        assert win_mgr.is_enabled() is False
        win_mgr.enable()
        assert win_mgr.is_enabled() is True
        assert mock_reg["BrisaSync"] == '"C:\\BrisaSync\\brisasync.exe" --start-hidden'
        win_mgr.disable()
        assert win_mgr.is_enabled() is False

        # Teste integrado com BrisaAutostartCoordinator em modo Windows
        monkeypatch.setattr("brisasync.service.autostart.is_windows", lambda: True)
        coord = BrisaAutostartCoordinator(
            service_executable="C:\\BrisaSync\\brisasync.exe",
        )
        assert coord.is_enabled() is False
        coord.enable()
        assert coord.is_enabled() is True
        coord.disable()
        assert coord.is_enabled() is False
    finally:
        set_mock_winreg(None)

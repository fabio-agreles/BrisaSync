"""Testes da camada SQLite, proteção de credenciais e fluxos da janela principal PySide6."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from brisasync.credentials.rclone_bridge import RcloneEncryptedBridge
from brisasync.credentials.store import (
    CredentialStore,
    OAuthCredentials,
    redact_secrets,
)
from brisasync.orchestrator.sync_coordinator import (
    DirectoryAccessError,
    validate_directory_empty_for_initial_sync,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.icons import (
    HICOLOR_SIZES,
    TRAY_PNG_SIZES,
    get_desktop_entry_path,
    load_app_icon,
    load_header_logo_pixmap,
    load_tray_icon,
)
from brisasync.ui.main_window import BrisaMainWindow


class _UITestCredentialStore(CredentialStore):
    OAUTH_ACCOUNT_KEY = "pytest_ui_google_oauth"
    RCLONE_KEY_ACCOUNT = "pytest_ui_rclone_cfg_key"


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sqlite_rejects_secret_keys_and_redacts_values(tmp_path: Path) -> None:
    db = BrisaDatabase(db_path=tmp_path / "brisasync.db")

    for forbidden_key in (
        "access_token",
        "refresh_token",
        "google_client_secret",
        "oauth_token",
        "rclone_config_key",
    ):
        with pytest.raises(ValueError, match="Proibido armazenar segredos"):
            db.set_setting(forbidden_key, "valor-secreto")

    raw_log = (
        'Erro na chamada: Authorization: Bearer ya29.a0AfH6SMBx_segredo '
        '{"access_token": "12345"} refresh=1//0g_secret_ref'
    )
    sanitized = redact_secrets(raw_log)
    assert "ya29." not in sanitized
    assert "12345" not in sanitized
    assert "1//0g_secret_ref" not in sanitized
    assert "[REDACTED" in sanitized


def test_empty_local_folder_validation_for_initial_sync(tmp_path: Path) -> None:
    empty_dir = tmp_path / "pasta_vazia"
    validated = validate_directory_empty_for_initial_sync(
        empty_dir, create_if_missing=True
    )
    assert validated == empty_dir.resolve()

    non_empty_dir = tmp_path / "pasta_ocupada"
    non_empty_dir.mkdir()
    (non_empty_dir / "existente.txt").write_text("nao vazia", encoding="utf-8")
    with pytest.raises(DirectoryAccessError, match="dedicada e vazia"):
        validate_directory_empty_for_initial_sync(non_empty_dir)


def test_main_window_account_reopen_remote_id_and_safe_disconnect(
    qapp: QApplication, tmp_path: Path
) -> None:
    db_file = tmp_path / "ui_test.db"
    sync_folder = tmp_path / "MinhaPastaBrisaVazia"
    local_preserved_file = tmp_path / "outro_local" / "preservado.txt"
    local_preserved_file.parent.mkdir(parents=True)
    local_preserved_file.write_text("nao apagar", encoding="utf-8")

    store = _UITestCredentialStore(lock_path=tmp_path / "cred.lock")
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=tmp_path / "rclone.conf",
    )

    try:
        store.delete_credentials()
        db = BrisaDatabase(db_path=db_file)
        window = BrisaMainWindow(
            database=db,
            credential_store=store,
            bridge=bridge,
        )

        # 1. Estado inicial sem conta conectada
        assert "[NÃO CONECTADA]" in window.account_status_label.text()
        assert window.diagnostics_table.rowCount() >= 6

        # 2. Configura pasta local vazia e pasta remota por ID
        window.folder_input.setText(str(sync_folder))
        assert window.save_and_validate_folder() is True
        assert sync_folder.is_dir()
        assert "[OK — CONFIGURADA E ACESSÍVEL]" in window.folder_feedback_label.text()

        db.set_remote_sync_folder(
            folder_id="1DriveFolderId_XYZ987",
            folder_name="BrisaSync-Teste",
        )

        # 3. Simula credenciais salvas no cofre e reabre o aplicativo:
        #    deve reconhecer a sessão válida sem exigir novo login!
        creds = OAuthCredentials(
            client_id="cid.apps.googleusercontent.com",
            client_secret="csec",
            access_token="ya29.valid_session",
            refresh_token="1//valid_refresh",
            token_type="Bearer",
            expiry="2099-01-01T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive",
            account_email="sessao.persistida@example.com",
        )
        store.store_credentials(creds)
        bridge.materialize_encrypted_config(creds)

        window_reopened = BrisaMainWindow(
            database=BrisaDatabase(db_path=db_file),
            credential_store=store,
            bridge=bridge,
        )
        assert "[CONECTADA] sessao.persistida@example.com" in window_reopened.account_status_label.text()
        assert "1DriveFolderId_XYZ987" in window_reopened.remote_folder_feedback_label.text()
        assert "[PRONTO]" in window_reopened.sync_target_preview_label.text()

        # 4. Cria um arquivo dentro da pasta local antes de desconectar para comprovar
        #    que desconectar NÃO apaga arquivos locais
        sample_file = sync_folder / "meus_dados.txt"
        sample_file.write_text("Meus dados importantes", encoding="utf-8")

        window_reopened.disconnect_google_account()
        assert "[NÃO CONECTADA]" in window_reopened.account_status_label.text()
        assert store.load_credentials() is None
        assert not (tmp_path / "rclone.conf").exists()
        assert sample_file.read_text(encoding="utf-8") == "Meus dados importantes"
    finally:
        bridge.remove_encrypted_config()
        store.delete_credentials()


def test_icons_loading_cwd_independence_hidpi_and_light_dark_variants(
    qapp: QApplication, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida carregamento dos ícones fora do diretório do projeto, em 1x/HiDPI e variantes claro/escuro."""
    # Muda o diretório de trabalho atual para uma pasta vazia em /tmp
    outside_cwd = tmp_path / "outside_working_dir"
    outside_cwd.mkdir()
    monkeypatch.chdir(outside_cwd)

    # 1. Ícone colorido principal (todas as resoluções hicolor presentes)
    app_icon = load_app_icon()
    assert not app_icon.isNull()
    available_widths = {sz.width() for sz in app_icon.availableSizes()}
    for expected_size in HICOLOR_SIZES:
        assert expected_size in available_widths

    # 2. Escala normal (1x) vs HiDPI (2x) no cabeçalho
    pm_1x = load_header_logo_pixmap(logical_size=44, device_pixel_ratio=1.0)
    assert not pm_1x.isNull()
    assert pm_1x.width() == 44
    assert pm_1x.devicePixelRatio() == 1.0

    pm_2x = load_header_logo_pixmap(logical_size=44, device_pixel_ratio=2.0)
    assert not pm_2x.isNull()
    assert pm_2x.width() == 88
    assert pm_2x.devicePixelRatio() == 2.0

    # 3. Variantes de bandeja (PNGs fixos):
    #    - panel_is_dark=True -> variante 'light' (desenho claro sobre painel escuro)
    #    - panel_is_dark=False -> variante 'dark' (desenho escuro sobre painel claro)
    tray_on_dark_panel = load_tray_icon(panel_is_dark=True)
    tray_on_light_panel = load_tray_icon(panel_is_dark=False)
    assert not tray_on_dark_panel.isNull()
    assert not tray_on_light_panel.isNull()
    assert {sz.width() for sz in tray_on_dark_panel.availableSizes()} == set(TRAY_PNG_SIZES)
    assert {sz.width() for sz in tray_on_light_panel.availableSizes()} == set(TRAY_PNG_SIZES)

    img_light = tray_on_dark_panel.pixmap(24, 24).toImage()
    img_dark = tray_on_light_panel.pixmap(24, 24).toImage()
    light_lumas = [
        img_light.pixelColor(x, y).lightness()
        for y in range(24)
        for x in range(24)
        if img_light.pixelColor(x, y).alpha() > 200
    ]
    dark_lumas = [
        img_dark.pixelColor(x, y).lightness()
        for y in range(24)
        for x in range(24)
        if img_dark.pixelColor(x, y).alpha() > 200
    ]
    assert light_lumas and sum(light_lumas) / len(light_lumas) > 200
    assert dark_lumas and sum(dark_lumas) / len(dark_lumas) < 60

    # 4. Lançador .desktop preparado com Icon=brisasync
    desktop_entry = get_desktop_entry_path()
    assert desktop_entry.is_file()
    desktop_text = desktop_entry.read_text(encoding="utf-8")
    assert "Icon=brisasync" in desktop_text
    assert "StartupWMClass=brisasync" in desktop_text

    # 5. Janela principal carrega o ícone colorido mesmo com cwd alterado
    window = BrisaMainWindow(database=BrisaDatabase(db_path=tmp_path / "icon_win.db"))
    assert not window.windowIcon().isNull()
    assert window.header_icon_label.pixmap() is not None
    assert not window.header_icon_label.pixmap().isNull()


#!/usr/bin/env python3
"""Validação da experiência do usuário comum com o cliente OAuth de distribuição empacotado.

Executa em perfil de teste estritamente isolado:
- Sem JSON manual em ~/.config/brisasync
- Sem configuração explícita na UI
- Sem banco SQLite preexistente
- Com cofre isolado (BRISASYNC_VAULT_ACCOUNT_KEY="test_round9_isolated")
- Sem alterar ou desconectar a sessão real do desenvolvedor/usuário.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

# Forçar Qt para modo offscreen durante os testes automatizados
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ARTIFACT_DIR = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")


def test_isolated_distribution_oauth_experience() -> None:
    # 1. Criar perfil temporário totalmente isolado
    tmp_root = Path(tempfile.mkdtemp(prefix="brisasync_dist_oauth_test_"))
    try:
        isolated_config = tmp_root / "config"
        isolated_data = tmp_root / "data"
        isolated_runtime = tmp_root / "runtime"
        isolated_config.mkdir(parents=True)
        isolated_data.mkdir(parents=True)
        isolated_runtime.mkdir(parents=True, mode=0o700)

        # Configurar ambiente do processo de teste
        os.environ["XDG_CONFIG_HOME"] = str(isolated_config)
        os.environ["XDG_DATA_HOME"] = str(isolated_data)
        os.environ["XDG_RUNTIME_DIR"] = str(isolated_runtime)
        os.environ["BRISASYNC_VAULT_ACCOUNT_KEY"] = "test_round9_isolated_account"
        os.environ["BRISASYNC_VAULT_RCLONE_KEY"] = "test_round9_isolated_rclone_key"

        # Importar após configurar variáveis de ambiente
        from brisasync.credentials.oauth_google import OAuthClientConfig
        from brisasync.credentials.store import CredentialStore, OAuthCredentials
        from brisasync.credentials.rclone_bridge import RcloneEncryptedBridge
        from brisasync.storage.database import BrisaDatabase
        from brisasync.ui.main_window import BrisaMainWindow

        # 2. Confirmar ausência de JSON em ~/.config/brisasync do perfil isolado
        user_config_file = isolated_config / "brisasync" / "google_oauth_client.json"
        assert not user_config_file.exists(), "Não deve haver JSON no perfil de teste limpo."

        # 3. Confirmar que o cliente empacotado é descoberto automaticamente
        is_avail = OAuthClientConfig.is_distribution_client_available()
        assert is_avail is True, "Cliente de distribuição deve estar disponível."

        has_client, client_src = OAuthClientConfig.get_active_client_source()
        assert has_client is True, "Deve detectar cliente OAuth ativo."
        assert "Cliente de distribuição empacotado" in client_src, f"Origem inesperada: {client_src}"
        print(f"✓ Cliente de distribuição descoberto com sucesso: {client_src}")

        # 4. Carregar cliente e verificar metadados
        client_cfg = OAuthClientConfig.load_available()
        assert client_cfg.client_id.startswith("626522180431")
        assert client_cfg.auth_uri.startswith("https://accounts.google.com/o/oauth2")
        print("✓ Metadados públicos do cliente verificados (client_id e URIs oficiais).")

        # 5. Instanciar UI da aplicação no perfil limpo
        app = QApplication.instance() or QApplication(sys.argv)

        db = BrisaDatabase(isolated_data / "brisasync" / "brisasync.db")
        cred_store = CredentialStore()
        # Garantir cofre limpo no perfil de teste
        try:
            cred_store.delete_credentials()
        except Exception:
            pass

        bridge = RcloneEncryptedBridge(credential_store=cred_store)

        win = BrisaMainWindow(
            database=db,
            credential_store=cred_store,
            bridge=bridge,
            enable_tray=False,
        )
        win.resize(820, 600)
        win.show()

        # 6. Validar que o assistente na aba Início exibe o fluxo normal sem aviso vermelho e sem jargões técnicos
        assert win.home_unconfigured_container.isVisible() is True
        assert "1. Conectar conta Google" in win.setup_step1_label.text()
        assert win.setup_connect_button.text() == "Conectar Conta Google"
        assert win.setup_step1_hint.isVisible() is False
        assert "Requer Cliente de Teste nesta versão" not in win.setup_step1_label.text()

        # Renderizar e salvar captura da tela inicial com assistente limpo usando cliente de distribuição
        pix_wizard = win.grab()
        img_wizard_path = ARTIFACT_DIR / "brisasync_v0.1.2_wizard_with_distribution_client.png"
        pix_wizard.save(str(img_wizard_path))
        print(f"✓ Captura do assistente sem JSON manual salva em: {img_wizard_path}")

        # 7. Simular autorização da conta de teste autorizada (fabioagreles@gmail.com) no perfil isolado
        # Cria credencial válida para teste no cofre isolado
        test_creds = OAuthCredentials(
            client_id=client_cfg.client_id,
            client_secret=client_cfg.client_secret,
            access_token="ya29.a0AfH6SM_test_token_distribution_flow",
            refresh_token="1//04_test_refresh_token_distribution_flow",
            token_type="Bearer",
            expiry="2026-10-30T00:00:00Z",
            scope="https://www.googleapis.com/auth/drive openid https://www.googleapis.com/auth/userinfo.email",
            account_email="fabioagreles@gmail.com",
        )
        cred_store.store_credentials(test_creds)

        # Atualizar a interface
        win._refresh_account_state_from_vault()
        win._update_home_view()

        # 8. Validar que a Etapa 1 avançou para conta conectada com sucesso
        step1_text = getattr(win, "setup_step1_status", win.setup_step1_label).text()
        assert "fabioagreles@gmail.com" in step1_text
        assert win.setup_connect_button.text() in ("Trocar Conta...", "Concluir Conexão")
        print("✓ Etapa 1 atualizada para conta conectada no perfil isolado.")

        # Renderizar e salvar captura do assistente com conta conectada
        pix_connected_wizard = win.grab()
        img_connected_wizard_path = ARTIFACT_DIR / "brisasync_v0.1.2_wizard_account_connected.png"
        pix_connected_wizard.save(str(img_connected_wizard_path))
        print(f"✓ Captura do assistente com conta conectada salva em: {img_connected_wizard_path}")

        # 9. Configurar pastas no perfil isolado para comprovar a Tela Inicial conectada
        db.set_local_sync_folder("/home/agreles/Android/brisa")
        db.set_remote_sync_folder(folder_id="1fT8hLz90uYTEJPgsDiNcwlgCYkBJrP1g", folder_name="Documentos")
        db.record_sync_run(
            started_at="2026-10-29T22:50:00Z",
            finished_at="2026-10-29T22:50:15Z",
            operation="BISYNC",
            status="SUCCESS",
            exit_code=0,
            summary="Sincronização normal concluída sem conflitos",
            path1="/home/agreles/Android/brisa",
            path2="brisasync_gdrive:Documentos",
        )
        win._refresh_account_state_from_vault()
        win._update_home_view()

        assert win.home_unconfigured_container.isVisible() is False
        assert win.home_configured_container.isVisible() is True
        assert "fabioagreles@gmail.com" in win.header_account_badge.toolTip()
        assert "fabi" in win.header_account_badge.text()

        pix_home = win.grab()
        img_home_path = ARTIFACT_DIR / "brisasync_v0.1.2_home_account_connected.png"
        pix_home.save(str(img_home_path))
        print(f"✓ Captura da tela inicial conectada salva em: {img_home_path}")

        # Limpeza do cofre isolado
        try:
            cred_store.delete_credentials()
        except Exception:
            pass

        win.close()
        print("✓ Ensaio em perfil isolado concluído com 100% de sucesso!")

    finally:
        # Remover diretório temporário do perfil isolado
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    test_isolated_distribution_oauth_experience()

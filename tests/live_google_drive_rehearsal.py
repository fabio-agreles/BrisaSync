"""Ensaio real de ponta a ponta contra o Google Drive (Seção 4).

Executa com consentimento interativo no navegador e pasta remota dedicada a testes
(`BrisaSync-Teste-Automatico`), sem tocar em nenhuma outra pasta da conta Google:
1. Login interativo no navegador (PKCE S256 + state + loopback 127.0.0.1) e identificação real da conta.
2. Listagem e seleção da pasta dedicada por ID (`folder_id`).
3. Inicialização segura com pasta local vazia (`--resync` controlado).
4. Criação e edição de arquivos nas duas direções (conferência SHA-256 local e remota).
5. Conflito simultâneo preservando ambas as versões (conferência SHA-256 local e remota).
6. Exclusão recuperável em `backup_dir2` fora da árvore remota selecionada (conferência SHA-256).
7. Reabertura da janela `BrisaMainWindow` usando credenciais protegidas no cofre da sessão.
8. Renovação REAL de `access_token` contra `https://oauth2.googleapis.com/token` (distinta de simulação).
9. Desconexão segura removendo credenciais sem apagar arquivos locais ou remotos.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from brisasync.backend.integrity import build_directory_inventory, sha256_file


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
from brisasync.backend.rclone_engine import (
    RcloneBisyncEngine,
    SENTINEL_FILENAME,
)
from brisasync.credentials.oauth_google import (
    GOOGLE_TOKEN_URI,
    GoogleOAuthDesktopClient,
    OAuthClientConfig,
)
from brisasync.credentials.rclone_bridge import REMOTE_NAME, RcloneEncryptedBridge
from brisasync.credentials.store import CredentialStore
from brisasync.orchestrator.sync_coordinator import (
    SyncCoordinator,
    validate_directory_empty_for_initial_sync,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.main_window import BrisaMainWindow

DEDICATED_REMOTE_FOLDER_NAME = "BrisaSync-Teste-Automatico"


def _remote_file_sha256(
    engine: RcloneBisyncEngine,
    remote_file_spec: str,
    *,
    env: dict[str, str],
) -> str:
    assert engine.rclone_binary is not None
    proc = subprocess.run(
        [engine.rclone_binary, "cat", remote_file_spec],
        env=env,
        capture_output=True,
        timeout=30,
        check=True,
    )
    return sha256_bytes(proc.stdout)


def _remote_upload_bytes(
    engine: RcloneBisyncEngine,
    remote_file_spec: str,
    payload: bytes,
    *,
    env: dict[str, str],
) -> str:
    assert engine.rclone_binary is not None
    proc = subprocess.run(
        [engine.rclone_binary, "rcat", remote_file_spec],
        input=payload,
        env=env,
        capture_output=True,
        timeout=30,
        check=True,
    )
    assert proc.returncode == 0
    return sha256_bytes(payload)


def _remote_inventory_hashes(
    engine: RcloneBisyncEngine,
    remote_folder_spec: str,
    *,
    env: dict[str, str],
    ignore_names: set[str] | None = None,
) -> dict[str, str]:
    assert engine.rclone_binary is not None
    ignored = ignore_names or set()
    proc = subprocess.run(
        [
            engine.rclone_binary,
            "lsjson",
            remote_folder_spec,
            "--recursive",
            "--files-only",
            "--no-modtime",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    items = json.loads(proc.stdout or "[]")
    hashes: dict[str, str] = {}
    for item in items:
        rel_path = str(item.get("Path", "")).strip()
        name = str(item.get("Name", "")).strip()
        if not rel_path or name in ignored:
            continue
        file_spec = f"{remote_folder_spec.rstrip('/')}/{rel_path}"
        hashes[rel_path] = _remote_file_sha256(engine, file_spec, env=env)
    return hashes


def run_live_rehearsal() -> None:
    work_root = Path("/tmp/brisasync_live_google_rehearsal")
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True, mode=0o700)

    db_path = work_root / "state" / "live_rehearsal.db"
    enc_cfg_path = work_root / "state" / "rclone_live.conf"
    local_sync_folder = work_root / "PastaLocalDedicadaVazia"

    db = BrisaDatabase(db_path=db_path)
    store = CredentialStore(lock_path=work_root / "state" / "cred.lock")
    engine = RcloneBisyncEngine()
    bridge = RcloneEncryptedBridge(
        credential_store=store,
        config_path=enc_cfg_path,
        rclone_binary=engine.rclone_binary,
    )
    coordinator = SyncCoordinator(database=db, engine=engine, bridge=bridge)

    client_cfg = OAuthClientConfig.load_available()
    assert client_cfg.token_uri == GOOGLE_TOKEN_URI
    oauth_client = GoogleOAuthDesktopClient(client_cfg)

    print("=== [1/9] Login OAuth 2.0 Interativo no Navegador (PKCE S256 + Loopback 127.0.0.1) ===", flush=True)

    def _on_auth_url_ready(auth_url: str) -> None:
        parsed_url = urllib.parse.urlparse(auth_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        raw_scope = query_params.get("scope", [""])[0]
        requested_scopes = raw_scope.split()
        prompt_val = query_params.get("prompt", [""])[0]
        challenge_method = query_params.get("code_challenge_method", [""])[0]
        assert requested_scopes == [
            "https://www.googleapis.com/auth/drive",
            "openid",
            "https://www.googleapis.com/auth/userinfo.email",
        ]
        assert prompt_val == "consent"
        assert challenge_method == "S256"
        print("Escopos solicitados no pedido OAuth:", flush=True)
        for s in requested_scopes:
            print(f" - {s}", flush=True)
        print(
            f"Parâmetros verificados: prompt={prompt_val}, code_challenge_method={challenge_method}, callback=loopback (127.0.0.1).",
            flush=True,
        )
        print(
            "Abrindo navegador padrão para seleção da conta de teste e concessão da permissão do Drive...",
            flush=True,
        )

    creds = oauth_client.authorize_interactive(
        timeout_seconds=180.0,
        on_auth_url_ready=_on_auth_url_ready,
    )
    assert creds.has_drive_scope, "Acesso ao Google Drive não concedido"
    print(
        f"Escopos efetivamente concedidos na resposta de tokens: {creds.scope.split()}",
        flush=True,
    )
    assert creds.account_email and "@" in creds.account_email
    assert creds.access_token and creds.refresh_token
    store.store_credentials(creds)
    cfg_file, _ = bridge.materialize_encrypted_config(creds)
    assert cfg_file.is_file()
    assert (cfg_file.stat().st_mode & 0o777) == 0o600
    cfg_text = cfg_file.read_text(encoding="utf-8")
    assert "RCLONE_ENCRYPT_V0:" in cfg_text
    assert creds.access_token not in cfg_text
    assert creds.refresh_token not in cfg_text
    # Mascara parcialmente o e-mail apenas para log legível sem expor tokens
    email_parts = creds.account_email.split("@", 1)
    masked_email = f"{email_parts[0][:3]}***@{email_parts[1]}"
    print(f"[OK 1/9] Conta autenticada e salva no cofre: {masked_email}", flush=True)

    print("=== [2/9] Listagem e Seleção da Pasta Remota Dedicada por ID ===", flush=True)
    with bridge.authenticated_rclone_session() as rclone_env:
        existing_dirs = engine.list_remote_directories(f"{REMOTE_NAME}:", env=rclone_env)
        target_entry = next(
            (d for d in existing_dirs if d.name == DEDICATED_REMOTE_FOLDER_NAME),
            None,
        )
        if target_entry is None:
            target_entry = engine.create_remote_directory(
                f"{REMOTE_NAME}:",
                DEDICATED_REMOTE_FOLDER_NAME,
                env=rclone_env,
            )
        else:
            # Limpa apenas o conteúdo de ensaios anteriores dentro da pasta dedicada de testes
            assert engine.rclone_binary is not None
            subprocess.run(
                [
                    engine.rclone_binary,
                    "delete",
                    f"{REMOTE_NAME}:{DEDICATED_REMOTE_FOLDER_NAME}",
                ],
                env=rclone_env,
                capture_output=True,
                timeout=30,
                check=False,
            )
            subprocess.run(
                [
                    engine.rclone_binary,
                    "purge",
                    f"{REMOTE_NAME}:.brisasync_recovery/{target_entry.folder_id}",
                ],
                env=rclone_env,
                capture_output=True,
                timeout=30,
                check=False,
            )

        resolved_entry = engine.resolve_remote_directory_by_id(
            f"{REMOTE_NAME}:",
            target_entry.folder_id,
            env=rclone_env,
        )
        assert resolved_entry.folder_id == target_entry.folder_id
        assert resolved_entry.name == DEDICATED_REMOTE_FOLDER_NAME
        db.set_remote_sync_folder(
            folder_id=resolved_entry.folder_id,
            folder_name=resolved_entry.name,
        )
        print(
            f"[OK 2/9] Pasta remota dedicada selecionada por ID: "
            f"nome={resolved_entry.name!r}, folder_id={resolved_entry.folder_id!r}",
            flush=True,
        )

        print("=== [3/9] Inicialização Segura com Pasta Local Vazia (--resync) ===", flush=True)
        seed_payload = b"Arquivo semente inicial criado no Google Drive para teste real do BrisaSync.\n"
        expected_seed_hash = _remote_upload_bytes(
            engine,
            f"{REMOTE_NAME}:{resolved_entry.path}/remoto_inicial.txt",
            seed_payload,
            env=rclone_env,
        )
        validated_local = validate_directory_empty_for_initial_sync(
            local_sync_folder, create_if_missing=True
        )
        db.set_local_sync_folder(validated_local)

    init_res = coordinator.synchronize_google_drive_pair(
        local_folder=local_sync_folder,
        remote_folder_id=resolved_entry.folder_id,
    )
    assert init_res.success, f"Falha na inicialização: {init_res.stderr}"
    assert init_res.was_resync is True
    assert (local_sync_folder / SENTINEL_FILENAME).is_file()
    assert (local_sync_folder / "remoto_inicial.txt").is_file()
    assert sha256_file(local_sync_folder / "remoto_inicial.txt") == expected_seed_hash
    print(
        f"[OK 3/9] Baseline inicial estabelecida: 'remoto_inicial.txt' baixado com SHA-256={expected_seed_hash[:16]}...",
        flush=True,
    )

    print("=== [4/9] Criação e Edição de Arquivos nas Duas Direções ===", flush=True)
    local_created_bytes = b"Criado localmente no Linux Desktop e sincronizado para o Google Drive.\n"
    local_edited_seed_bytes = b"Arquivo semente editado localmente no Linux (versao 2)!\n"
    remote_created_bytes = b"Criado diretamente no Google Drive e sincronizado para a pasta local.\n"

    (local_sync_folder / "criado_no_linux.txt").write_bytes(local_created_bytes)
    (local_sync_folder / "remoto_inicial.txt").write_bytes(local_edited_seed_bytes)
    hash_local_created = sha256_file(local_sync_folder / "criado_no_linux.txt")
    hash_edited_seed = sha256_file(local_sync_folder / "remoto_inicial.txt")

    with bridge.authenticated_rclone_session() as rclone_env:
        hash_remote_created = _remote_upload_bytes(
            engine,
            f"{REMOTE_NAME}:{resolved_entry.path}/criado_no_drive.txt",
            remote_created_bytes,
            env=rclone_env,
        )

    bidir_res = coordinator.synchronize_google_drive_pair(
        local_folder=local_sync_folder,
        remote_folder_id=resolved_entry.folder_id,
    )
    assert bidir_res.success, f"Falha na sincronização bidirecional: {bidir_res.stderr}"
    assert bidir_res.was_resync is False

    local_inv_step4 = build_directory_inventory(local_sync_folder).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    with bridge.authenticated_rclone_session() as rclone_env:
        remote_inv_step4 = _remote_inventory_hashes(
            engine,
            f"{REMOTE_NAME}:{resolved_entry.path}",
            env=rclone_env,
            ignore_names={SENTINEL_FILENAME},
        )
    expected_step4 = {
        "remoto_inicial.txt": hash_edited_seed,
        "criado_no_linux.txt": hash_local_created,
        "criado_no_drive.txt": hash_remote_created,
    }
    assert local_inv_step4 == expected_step4
    assert remote_inv_step4 == expected_step4
    print(
        f"[OK 4/9] Criação/edição bidirecional validada com hashes SHA-256 idênticos local/remoto: "
        f"{list(local_inv_step4.keys())}",
        flush=True,
    )

    print("=== [5/9] Conflito Simultâneo Preservando Ambas as Versões ===", flush=True)
    conflict_local_bytes = b"Conteudo divergente editado no LINUX DESKTOP (conflito lado 1).\n"
    conflict_remote_bytes = b"Conteudo divergente editado na NUVEM GOOGLE DRIVE (conflito lado 2).\n"

    (local_sync_folder / "criado_no_linux.txt").write_bytes(conflict_local_bytes)
    hash_conflict_local = sha256_file(local_sync_folder / "criado_no_linux.txt")
    with bridge.authenticated_rclone_session() as rclone_env:
        hash_conflict_remote = _remote_upload_bytes(
            engine,
            f"{REMOTE_NAME}:{resolved_entry.path}/criado_no_linux.txt",
            conflict_remote_bytes,
            env=rclone_env,
        )
    assert hash_conflict_local != hash_conflict_remote

    conflict_res = coordinator.synchronize_google_drive_pair(
        local_folder=local_sync_folder,
        remote_folder_id=resolved_entry.folder_id,
    )
    assert conflict_res.success, f"Falha ao resolver conflito: {conflict_res.stderr}"
    assert conflict_res.was_resync is False

    local_inv_step5 = build_directory_inventory(local_sync_folder).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    with bridge.authenticated_rclone_session() as rclone_env:
        remote_inv_step5 = _remote_inventory_hashes(
            engine,
            f"{REMOTE_NAME}:{resolved_entry.path}",
            env=rclone_env,
            ignore_names={SENTINEL_FILENAME},
        )
    assert local_inv_step5 == remote_inv_step5
    conflict_files = {
        k: v for k, v in local_inv_step5.items() if k.startswith("criado_no_linux.txt")
    }
    assert len(conflict_files) == 2, f"Esperadas 2 versões preservadas, obtido: {conflict_files}"
    assert set(conflict_files.values()) == {hash_conflict_local, hash_conflict_remote}
    print(
        f"[OK 5/9] Conflito simultâneo preservou ambas as versões localmente e no Drive: "
        f"{sorted(conflict_files.keys())}",
        flush=True,
    )

    print("=== [6/9] Exclusão Recuperável em backup_dir2 (Fora da Árvore Remota Selecionada) ===", flush=True)
    deleted_target = local_sync_folder / "criado_no_drive.txt"
    deleted_original_hash = sha256_file(deleted_target)
    deleted_target.unlink()

    del_res = coordinator.synchronize_google_drive_pair(
        local_folder=local_sync_folder,
        remote_folder_id=resolved_entry.folder_id,
    )
    assert del_res.success, f"Falha ao sincronizar exclusão recuperável: {del_res.stderr}"
    assert not (local_sync_folder / "criado_no_drive.txt").exists()

    with bridge.authenticated_rclone_session() as rclone_env:
        remote_inv_step6 = _remote_inventory_hashes(
            engine,
            f"{REMOTE_NAME}:{resolved_entry.path}",
            env=rclone_env,
            ignore_names={SENTINEL_FILENAME},
        )
        backup_inv_step6 = _remote_inventory_hashes(
            engine,
            f"{REMOTE_NAME}:.brisasync_recovery/{resolved_entry.folder_id}",
            env=rclone_env,
        )
    assert "criado_no_drive.txt" not in remote_inv_step6
    assert "criado_no_drive.txt" in backup_inv_step6
    assert backup_inv_step6["criado_no_drive.txt"] == deleted_original_hash
    print(
        f"[OK 6/9] Exclusão recuperável confirmada: 'criado_no_drive.txt' movido para "
        f".brisasync_recovery/{resolved_entry.folder_id} com SHA-256={deleted_original_hash[:16]}...",
        flush=True,
    )

    print("=== [7/9] Reabertura do Aplicativo Usando Credenciais Protegidas no Cofre ===", flush=True)
    app = QApplication.instance() or QApplication([])
    reopened_window = BrisaMainWindow(
        database=BrisaDatabase(db_path=db_path),
        credential_store=store,
        engine=engine,
        bridge=bridge,
    )
    assert "[CONECTADA]" in reopened_window.account_status_label.text()
    assert creds.account_email in reopened_window.account_status_label.text()
    assert resolved_entry.folder_id in reopened_window.remote_folder_feedback_label.text()
    assert "[PRONTO]" in reopened_window.sync_target_preview_label.text()
    assert reopened_window.history_table.rowCount() >= 4
    print(
        f"[OK 7/9] Reabertura da janela principal reconheceu sessão no cofre, "
        f"pasta remota por ID e {reopened_window.history_table.rowCount()} registros no histórico SQLite.",
        flush=True,
    )

    print("=== [8/9] Renovação REAL de Acesso contra https://oauth2.googleapis.com/token ===", flush=True)
    stored_before = store.load_credentials()
    assert stored_before is not None
    # Executa POST real de grant_type=refresh_token contra https://oauth2.googleapis.com/token
    refreshed_real = oauth_client.refresh_access_token(stored_before)
    assert refreshed_real.access_token.startswith("ya29.")
    assert refreshed_real.expiry
    # Comprova que o access_token emitido na renovação é aceito pela API Google real
    verified_email_after_refresh = oauth_client.fetch_user_email(refreshed_real.access_token)
    assert verified_email_after_refresh == stored_before.account_email
    store.store_credentials(refreshed_real)
    bridge.materialize_encrypted_config(refreshed_real)
    token_digest_before = hashlib.sha256(stored_before.access_token.encode()).hexdigest()[:12]
    token_digest_after = hashlib.sha256(refreshed_real.access_token.encode()).hexdigest()[:12]
    print(
        f"[OK 8/9] Renovação OAuth real contra {GOOGLE_TOKEN_URI} validada "
        f"(sha256_prefix antes={token_digest_before}, depois={token_digest_after}, nova expiry={refreshed_real.expiry}).",
        flush=True,
    )

    print("=== [9/9] Desconexão Segura Sem Apagar Arquivos Locais ou Remotos ===", flush=True)
    local_inv_before_disconnect = build_directory_inventory(local_sync_folder).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    reopened_window.disconnect_google_account()
    assert "[NÃO CONECTADA]" in reopened_window.account_status_label.text()
    assert store.load_credentials() is None
    assert not enc_cfg_path.exists()
    local_inv_after_disconnect = build_directory_inventory(local_sync_folder).hashes_by_path(
        ignore_names={SENTINEL_FILENAME}
    )
    assert local_inv_after_disconnect == local_inv_before_disconnect
    assert len(local_inv_after_disconnect) >= 3
    print(
        f"[OK 9/9] Desconexão concluída: cofre e rclone.conf limpos; "
        f"{len(local_inv_after_disconnect)} arquivos locais preservados com SHA-256 intacto.",
        flush=True,
    )
    print("\n=== TODOS OS 9 CENÁRIOS REAIS CONTRA O GOOGLE DRIVE FORAM APROVADOS COM SUCESSO ===", flush=True)


if __name__ == "__main__":
    try:
        run_live_rehearsal()
    except Exception as exc:
        print(f"ERRO NO ENSAIO REAL: {exc}", file=sys.stderr, flush=True)
        sys.exit(1)

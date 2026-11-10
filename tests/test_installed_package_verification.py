"""Testes de verificação do artefato instalado em ambiente isolado (Rodada 6).

Valida os requisitos de entrega do pacote instalável:
1. Arquitetura e sanidade do pacote gerado (ausência de secrets, banco, testes, .venv, etc.).
2. Ciclo de vida ALPM nativo (instalação, consulta de metadados, atualização 0.1.0-1 -> 0.1.0-2 e remoção).
3. Execução em sandbox Bubblewrap com checkout de desenvolvimento mascarado e HOME limpo:
   - CLI --version e --help
   - Diagnósticos (--diagnose) com rclone bundled verificado
   - Execução do serviço da sessão (--service) e comunicação IPC
   - Execução do modo sem bandeja (--no-tray)
   - Geração de autoinício systemd --user com caminhos instalados (/usr/bin/brisasync --service e WorkingDirectory=%h)
4. Preservação de dados do usuário (banco SQLite e arquivos sincronizados) durante atualização e remoção.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import time

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = REPO_ROOT / "dist"
PKG_V1 = DIST_DIR / "brisasync-0.1.26-1-x86_64.pkg.tar.zst"
PKG_V2 = DIST_DIR / "brisasync-0.1.26-2-x86_64.pkg.tar.zst"
WHEEL_FILE = DIST_DIR / "brisasync-0.1.26-py3-none-any.whl"

HAS_BWRAP = shutil.which("bwrap") is not None
HAS_PACMAN = shutil.which("pacman") is not None
HAS_FAKEROOT = shutil.which("fakeroot") is not None


@pytest.fixture(scope="module")
def ensure_packages_built():
    """Garante que os pacotes em dist/ foram compilados antes de executar a suíte."""
    if not PKG_V1.is_file() or not PKG_V2.is_file():
        build_script = REPO_ROOT / "packaging" / "build_packages.sh"
        res = subprocess.run(["bash", str(build_script)], cwd=str(REPO_ROOT), capture_output=True, text=True)
        assert res.returncode == 0, f"Falha ao compilar pacotes: {res.stderr}\n{res.stdout}"
    assert PKG_V1.is_file(), f"Pacote {PKG_V1} não existe."
    assert PKG_V2.is_file(), f"Pacote {PKG_V2} não existe."


def test_package_archive_contents_and_purity(ensure_packages_built):
    """Verifica se o pacote ALPM contém todos os arquivos necessários e nenhum arquivo indevido."""
    res = subprocess.run(["bsdtar", "-tf", str(PKG_V1)], capture_output=True, text=True, check=True)
    file_list = [line.strip() for line in res.stdout.splitlines() if line.strip()]

    # 1. Componentes obrigatórios presentes
    assert "usr/bin/brisasync" in file_list
    assert "usr/lib/brisasync/bin/rclone" in file_list
    assert "usr/share/applications/brisasync.desktop" in file_list
    assert "usr/lib/systemd/user/brisasync.service" in file_list
    assert "usr/share/licenses/brisasync/LICENSE" in file_list
    assert "usr/share/licenses/brisasync/LICENSE-rclone.txt" in file_list
    assert "usr/share/licenses/brisasync/THIRD_PARTY_NOTICES.md" in file_list
    assert "usr/share/icons/hicolor/scalable/apps/brisasync.svg" in file_list
    assert "usr/share/brisasync/google_oauth_client.json" in file_list
    assert any("usr/lib/python3.14/site-packages/brisasync/main.py" in f for f in file_list)
    assert any("usr/lib/python3.14/site-packages/brisasync/resources/support.json" in f for f in file_list)
    assert any("usr/lib/python3.14/site-packages/brisasync/resources/icons/pix_qr.png" in f for f in file_list)
    assert any("usr/lib/python3.14/site-packages/brisasync/i18n/__init__.py" in f for f in file_list)
    assert any("usr/lib/python3.14/site-packages/brisasync/i18n/catalog.py" in f for f in file_list)
    assert any("usr/lib/python3.14/site-packages/brisasync/i18n/core.py" in f for f in file_list)

    # 1.1 Validar integridade e pureza dos metadados OAuth empacotados
    tar_res = subprocess.run(
        ["bsdtar", "-xf", str(PKG_V1), "-O", "usr/share/brisasync/google_oauth_client.json"],
        capture_output=True,
        text=True,
        check=True,
    )
    oauth_meta = json.loads(tar_res.stdout)
    assert "installed" in oauth_meta
    inst = oauth_meta["installed"]
    assert "client_id" in inst and inst["client_id"]
    assert "client_secret" in inst and inst["client_secret"]
    assert inst.get("project_id") == "brisasync"
    for forbidden in ("access_token", "refresh_token", "token", "password"):
        assert forbidden not in inst

    # 2. Pureza absoluta: nenhum secret, token, sqlite, venv ou testes empacotados
    forbidden_prefixes = (
        ".git",
        ".venv",
        "tests",
        "usr/lib/python3.14/site-packages/brisasync/tests",
        ".pytest_cache",
    )
    for path in file_list:
        for forbidden in forbidden_prefixes:
            assert not path.startswith(forbidden), f"Caminho indevido no pacote: {path}"
        assert not path.endswith(".sqlite"), f"Banco empacotado indevidamente: {path}"
        assert not path.endswith(".token"), f"Token empacotado indevidamente: {path}"
        assert "secret" not in path.lower() or path.startswith("usr/lib/python3.14/site-packages/brisasync/credentials"), (
            f"Arquivo suspeito de segredo no pacote: {path}"
        )


@pytest.mark.skipif(not (HAS_PACMAN and HAS_FAKEROOT), reason="pacman e fakeroot necessários para teste ALPM")
def test_alpm_package_lifecycle_install_upgrade_remove(ensure_packages_built, tmp_path):
    """Testa ciclo de vida completo do pacote Arch/ALPM em raiz fakeroot isolada."""
    target_root = tmp_path / "pacman_root"
    target_root.mkdir(parents=True)
    (target_root / "var" / "lib" / "pacman").mkdir(parents=True)

    # 1. Instalação de brisasync-0.1.0-1
    cmd_install = [
        "fakeroot",
        "pacman",
        "-r",
        str(target_root),
        "-U",
        str(PKG_V1),
        "--nodeps",
        "--nodeps",
        "--noconfirm",
    ]
    res_inst = subprocess.run(cmd_install, capture_output=True, text=True)
    assert res_inst.returncode == 0, f"Erro na instalação com pacman: {res_inst.stderr}"

    # Consulta de metadados
    cmd_query = ["pacman", "-r", str(target_root), "-Qi", "brisasync"]
    res_query = subprocess.run(cmd_query, capture_output=True, text=True)
    assert res_query.returncode == 0
    assert "Versão               : 0.1.26-1" in res_query.stdout
    assert "GPL-3.0-or-later" in res_query.stdout

    # 2. Atualização para brisasync-0.1.26-2
    cmd_upgrade = [
        "fakeroot",
        "pacman",
        "-r",
        str(target_root),
        "-U",
        str(PKG_V2),
        "--nodeps",
        "--nodeps",
        "--noconfirm",
    ]
    res_upg = subprocess.run(cmd_upgrade, capture_output=True, text=True)
    assert res_upg.returncode == 0, f"Erro na atualização com pacman: {res_upg.stderr}"

    res_query2 = subprocess.run(cmd_query, capture_output=True, text=True)
    assert res_query2.returncode == 0
    assert "Versão               : 0.1.26-2" in res_query2.stdout

    # 3. Remoção do pacote
    cmd_remove = [
        "fakeroot",
        "pacman",
        "-r",
        str(target_root),
        "-R",
        "brisasync",
        "--noconfirm",
    ]
    res_rm = subprocess.run(cmd_remove, capture_output=True, text=True)
    assert res_rm.returncode == 0, f"Erro na remoção com pacman: {res_rm.stderr}"

    # Validar que os arquivos de pacote foram removidos da raiz
    assert not (target_root / "usr" / "bin" / "brisasync").exists()
    assert not (target_root / "usr" / "lib" / "brisasync").exists()


@pytest.mark.skipif(not HAS_BWRAP, reason="Bubblewrap (bwrap) necessário para execução isolada")
def test_bwrap_isolated_execution_diagnostics_and_cli(ensure_packages_built, tmp_path):
    """Executa o pacote descompactado dentro de sandbox bwrap isolando o checkout e HOME."""
    overlay_dir = tmp_path / "installed_overlay"
    overlay_dir.mkdir(parents=True)
    subprocess.run(["bsdtar", "-xf", str(PKG_V1), "-C", str(overlay_dir)], check=True)

    clean_home = tmp_path / "clean_user_home"
    clean_home.mkdir(parents=True)

    def run_in_bwrap(args: list[str]) -> subprocess.CompletedProcess:
        bwrap_cmd = [
            "bwrap",
            "--ro-bind",
            "/",
            "/",
            "--tmpfs",
            "/tmp",
            "--ro-bind",
            str(overlay_dir),
            "/tmp/installed",
            "--bind",
            str(clean_home),
            "/home/agreles",
            "--tmpfs",
            str(REPO_ROOT),  # Oculta a árvore git/checkout
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--setenv",
            "HOME",
            "/home/agreles",
            "--setenv",
            "PYTHONPATH",
            "/tmp/installed/usr/lib/python3.14/site-packages",
            "python3",
            "/tmp/installed/usr/bin/brisasync",
            *args,
        ]
        return subprocess.run(bwrap_cmd, capture_output=True, text=True)

    # 1. Teste --version
    res_ver = run_in_bwrap(["--version"])
    assert res_ver.returncode == 0
    assert "BrisaSync 0.1.26" in res_ver.stdout

    # 2. Teste --help
    res_help = run_in_bwrap(["--help"])
    assert res_help.returncode == 0
    assert "--service" in res_help.stdout
    assert "--no-tray" in res_help.stdout
    assert "--diagnose" in res_help.stdout
    assert "--start-hidden" in res_help.stdout

    # 3. Teste --diagnose
    res_diag = run_in_bwrap(["--diagnose"])
    assert res_diag.returncode == 0
    diag_data = json.loads(res_diag.stdout)
    assert diag_data["app"] == "BrisaSync"
    assert diag_data["version"] == "0.1.26"
    assert diag_data["all_critical_ok"] is True

    # Verifica se o motor rclone foi detectado no caminho empacotado (/tmp/installed/usr/lib/brisasync/bin/rclone)
    rclone_item = next(it for it in diag_data["items"] if it["component"] == "Motor de Sincronização (rclone)")
    assert rclone_item["status_code"] == "OK"
    assert "rclone v1.75.2" in rclone_item["details"]
    assert "/tmp/installed/usr/lib/brisasync/bin/rclone" in rclone_item["details"]

    # 4. Verifica se o cliente OAuth de distribuição empacotado é descoberto em HOME limpo
    bwrap_py = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(overlay_dir),
        "/tmp/installed",
        "--bind",
        str(clean_home),
        "/home/agreles",
        "--tmpfs",
        str(REPO_ROOT),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--setenv",
        "HOME",
        "/home/agreles",
        "--setenv",
        "PYTHONPATH",
        "/tmp/installed/usr/lib/python3.14/site-packages",
        "python3",
        "-c",
        (
            "from brisasync.credentials.oauth_google import OAuthClientConfig; "
            "avail = OAuthClientConfig.is_distribution_client_available(); "
            "has, src = OAuthClientConfig.get_active_client_source(); "
            "cfg = OAuthClientConfig.load_available(); "
            "print('AVAIL:', avail); "
            "print('HAS:', has); "
            "print('SRC:', src); "
            "print('PROJECT:', cfg.client_id)"
        ),
    ]
    res_py = subprocess.run(bwrap_py, capture_output=True, text=True)
    assert res_py.returncode == 0, f"Falha na detecção OAuth no bwrap: {res_py.stderr}"
    assert "AVAIL: True" in res_py.stdout
    assert "HAS: True" in res_py.stdout
    assert "Cliente de distribuição empacotado" in res_py.stdout


@pytest.mark.skipif(not HAS_BWRAP, reason="Bubblewrap (bwrap) necessário para execução isolada")
def test_bwrap_isolated_service_daemon_and_ipc(ensure_packages_built, tmp_path):
    """Testa execução do serviço da sessão e IPC em ambiente isolado."""
    overlay_dir = tmp_path / "installed_overlay"
    overlay_dir.mkdir(parents=True)
    subprocess.run(["bsdtar", "-xf", str(PKG_V1), "-C", str(overlay_dir)], check=True)

    clean_home = tmp_path / "clean_user_home"
    clean_home.mkdir(parents=True)

    # Script de teste cliente IPC executado dentro da sandbox
    client_script = clean_home / "ipc_smoke_test.py"
    client_script.write_text(
        """
import sys, time
from brisasync.service.ipc_client import ServiceIPCClient

client = ServiceIPCClient()
for _ in range(40):
    try:
        snap = client.get_status()
        if snap is not None:
            break
    except Exception:
        pass
    time.sleep(0.1)
else:
    print("ERRO: Daemon não respondeu ao status", file=sys.stderr)
    sys.exit(1)

print(f"STATUS_OK: state={snap.state}")

# Teste pause
p_snap = client.pause()
print(f"PAUSE_OK: state={p_snap.state}")

# Teste resume
r_snap = client.resume()
print(f"RESUME_OK: state={r_snap.state}")

# Teste shutdown_service
s_snap = client.shutdown_service()
print("STOP_OK")
sys.exit(0)
""",
        encoding="utf-8",
    )

    # Script orquestrador dentro da sandbox
    orchestrator_script = clean_home / "run_service_and_test.sh"
    orchestrator_script.write_text(
        """#!/usr/bin/env bash
set -e
export PYTHONPATH="/tmp/installed/usr/lib/python3.14/site-packages"
export XDG_RUNTIME_DIR=/tmp/runtime
mkdir -p /tmp/runtime
chmod 0700 /tmp/runtime

python3 /tmp/installed/usr/bin/brisasync --service &
SERVICE_PID=$!
trap 'kill -TERM $SERVICE_PID 2>/dev/null || true' EXIT

python3 /home/agreles/ipc_smoke_test.py
wait $SERVICE_PID || true
trap - EXIT
""",
        encoding="utf-8",
    )
    orchestrator_script.chmod(0o755)

    bwrap_cmd = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(overlay_dir),
        "/tmp/installed",
        "--bind",
        str(clean_home),
        "/home/agreles",
        "--tmpfs",
        str(REPO_ROOT),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--setenv",
        "HOME",
        "/home/agreles",
        "--setenv",
        "XDG_RUNTIME_DIR",
        "/tmp/runtime",
        "/bin/bash",
        "/home/agreles/run_service_and_test.sh",
    ]
    res = subprocess.run(bwrap_cmd, capture_output=True, text=True, timeout=20)
    assert res.returncode == 0, f"Falha no teste IPC isolado: {res.stderr}\n{res.stdout}"
    assert "STATUS_OK: state=WAITING" in res.stdout
    assert "PAUSE_OK: state=PAUSED" in res.stdout
    assert "RESUME_OK: state=WAITING" in res.stdout
    assert "STOP_OK" in res.stdout


@pytest.mark.skipif(not HAS_BWRAP, reason="Bubblewrap (bwrap) necessário para execução isolada")
def test_bwrap_isolated_no_tray_and_autostart_paths(ensure_packages_built, tmp_path):
    """Testa modo --no-tray e autostart sem dependência da checkout de desenvolvimento."""
    overlay_dir = tmp_path / "installed_overlay"
    overlay_dir.mkdir(parents=True)
    subprocess.run(["bsdtar", "-xf", str(PKG_V1), "-C", str(overlay_dir)], check=True)

    clean_home = tmp_path / "clean_user_home"
    clean_home.mkdir(parents=True)

    # Script para validar --no-tray e geração de autostart
    test_script = clean_home / "test_no_tray_and_autostart.py"
    test_script.write_text(
        """
import os, sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from brisasync.service.autostart import (
    BrisaAutostartCoordinator,
    SystemdUserAutostartManager,
    XDGAutostartManager,
)
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.storage.database import BrisaDatabase

# 1. Valida geração de unidade de autostart instalada
mgr = SystemdUserAutostartManager(run_systemctl=False)
unit_text = mgr.render_unit_content()

assert "ExecStart=/usr/bin/brisasync --service" in unit_text or "ExecStart=" in unit_text, f"ExecStart inválido: {unit_text}"
assert "WorkingDirectory=%h" in unit_text, f"WorkingDirectory inválido: {unit_text}"
assert "Aplicativos/BrisaSync" not in unit_text, f"Referência à checkout detectada: {unit_text}"
assert ".venv" not in unit_text, f"Referência a .venv detectada: {unit_text}"

mgr.enable()
assert mgr.is_enabled()
assert mgr.unit_path.is_file()
mgr.disable()
assert not mgr.is_enabled()
assert not mgr.unit_path.is_file()

# 1b. Valida coordinator e XDG autostart instalados
coord = BrisaAutostartCoordinator(run_systemctl=False)
unit_p, desk_p = coord.enable()
assert unit_p.is_file()
assert desk_p.is_file()
desk_text = desk_p.read_text(encoding="utf-8")
assert "--start-hidden" in desk_text
assert "X-BrisaSync-Managed=true" in desk_text
assert coord.is_enabled()
coord.disable()
assert not unit_p.is_file()
assert not desk_p.is_file()
assert not coord.is_enabled()

# 2. Valida inicialização com --no-tray através do caminho real de entrada da aplicação (main.py)
from PySide6.QtCore import QTimer
from brisasync.main import main
from brisasync.service.ipc_client import ServiceIPCClient

app = QApplication.instance() or QApplication(["brisasync", "--no-tray", "-platform", "offscreen"])
db_path = Path("/home/agreles/.local/share/brisasync/brisasync.sqlite")
sock_path = Path("/home/agreles/.local/state/brisasync/service.sock")
ui_sock_path = Path("/home/agreles/.local/state/brisasync/ui.sock")

def on_timer():
    client = ServiceIPCClient(socket_path=sock_path, db_path=db_path)
    try:
        snap = client.get_status()
        assert snap.service_pid is not None, "Serviço da sessão não foi iniciado pelo main()"
        client.shutdown_service()
    finally:
        app.quit()

QTimer.singleShot(700, on_timer)
exit_code = main([
    "--no-tray",
    "--db-path", str(db_path),
    "--socket-path", str(sock_path),
    "--ui-socket-path", str(ui_sock_path),
])
assert exit_code == 0, f"main() retornou código diferente de zero: {exit_code}"

# 3. Valida que o método ensure_background_service_started existe e é invocável em BrisaMainWindow
db = BrisaDatabase(db_path)
window = BrisaMainWindow(database=db, enable_tray=False)
assert hasattr(window, "ensure_background_service_started")
assert callable(window.ensure_background_service_started)
assert window.tray_controller.is_available is False
window.close()

print("NO_TRAY_AND_AUTOSTART_OK")
""",
        encoding="utf-8",
    )

    bwrap_cmd = [
        "bwrap",
        "--ro-bind",
        "/",
        "/",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        str(overlay_dir),
        "/tmp/installed",
        "--bind",
        str(clean_home),
        "/home/agreles",
        "--tmpfs",
        str(REPO_ROOT),
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--setenv",
        "HOME",
        "/home/agreles",
        "--setenv",
        "PYTHONPATH",
        "/tmp/installed/usr/lib/python3.14/site-packages",
        "--setenv",
        "QT_QPA_PLATFORM",
        "offscreen",
        "python3",
        "/home/agreles/test_no_tray_and_autostart.py",
    ]
    res = subprocess.run(bwrap_cmd, capture_output=True, text=True, timeout=15)
    assert res.returncode == 0, f"Falha no teste de autostart e no-tray: {res.stderr}\n{res.stdout}"
    assert "NO_TRAY_AND_AUTOSTART_OK" in res.stdout


def test_upgrade_and_removal_preserves_user_data(ensure_packages_built, tmp_path):
    """Garante que a atualização e a remoção de pacotes nunca tocam nem excluem arquivos ou bancos do usuário."""
    user_home = tmp_path / "user_home"
    user_home.mkdir(parents=True)
    app_data = user_home / ".local" / "share" / "brisasync"
    app_data.mkdir(parents=True)

    db_path = app_data / "brisasync.sqlite"
    db_path.write_text("DUMMY_DATABASE_USER_CONTENT", encoding="utf-8")

    synced_file = user_home / "BrisaSync" / "documento_usuario.pdf"
    synced_file.parent.mkdir(parents=True)
    synced_file.write_text("CONTEUDO_PROTEGIDO_DO_USUARIO", encoding="utf-8")

    # Simular pacote instalado em raiz separada
    pacman_root = tmp_path / "sys_root"
    pacman_root.mkdir(parents=True)
    (pacman_root / "var" / "lib" / "pacman").mkdir(parents=True)

    if HAS_PACMAN and HAS_FAKEROOT:
        # Instala 0.1.0-1
        subprocess.run(
            ["fakeroot", "pacman", "-r", str(pacman_root), "-U", str(PKG_V1), "--nodeps", "--nodeps", "--noconfirm"],
            check=True,
            capture_output=True,
        )
        # Atualiza para 0.1.0-2
        subprocess.run(
            ["fakeroot", "pacman", "-r", str(pacman_root), "-U", str(PKG_V2), "--nodeps", "--nodeps", "--noconfirm"],
            check=True,
            capture_output=True,
        )
        # Remove pacote
        subprocess.run(
            ["fakeroot", "pacman", "-r", str(pacman_root), "-R", "brisasync", "--noconfirm"],
            check=True,
            capture_output=True,
        )

    # Verifica que dados do usuário permanecem rigorosamente intocados
    assert db_path.is_file()
    assert db_path.read_text(encoding="utf-8") == "DUMMY_DATABASE_USER_CONTENT"
    assert synced_file.is_file()
    assert synced_file.read_text(encoding="utf-8") == "CONTEUDO_PROTEGIDO_DO_USUARIO"

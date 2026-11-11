#!/usr/bin/env python3
"""Script de automação para construção do pacote Windows x64 do BrisaSync.

Executável tanto no Windows quanto no runner CI `windows-latest` do GitHub Actions:
1. Valida dependências (PyInstaller, PySide6).
2. Obtém o binário `rclone.exe` oficial para Windows x64.
3. Compila o pacote binário standalone via PyInstaller.
4. Gera o pacote portátil (.zip) em `dist/`.
5. Se `makensis` estiver disponível, compila o instalador NSIS (.exe) em `dist/`.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

# Garantir saída UTF-8 no console Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VERSION = "0.1.27"
RCLONE_VERSION = "v1.75.2"
RCLONE_URL = f"https://github.com/rclone/rclone/releases/download/{RCLONE_VERSION}/rclone-{RCLONE_VERSION}-windows-amd64.zip"


def ensure_rclone_exe(dest_dir: Path) -> Path:
    """Garante que rclone.exe esteja presente para empacotamento no Windows."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    rclone_exe = dest_dir / "rclone.exe"
    if rclone_exe.is_file():
        return rclone_exe

    print(f"Baixando motor rclone oficial {RCLONE_VERSION} para Windows x64...")
    tmp_zip = dest_dir / "rclone_win.zip"
    urllib.request.urlretrieve(RCLONE_URL, tmp_zip)
    try:
        with zipfile.ZipFile(tmp_zip) as z:
            for member in z.namelist():
                if member.endswith("rclone.exe"):
                    with z.open(member) as src, open(rclone_exe, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    break
    finally:
        tmp_zip.unlink(missing_ok=True)

    if not rclone_exe.is_file():
        raise FileNotFoundError("Não foi possível extrair rclone.exe do arquivo baixado.")

    print(f"[OK] rclone.exe pronto em: {rclone_exe}")
    return rclone_exe


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    build_dir = script_dir / "dist_win"
    shutil.rmtree(build_dir, ignore_errors=True)

    print(f"=== Construindo BrisaSync v{VERSION} para Windows x64 ===")
    rclone_bin = ensure_rclone_exe(script_dir / "bin")

    # 1. Compilação com PyInstaller se disponível
    pyinstaller = shutil.which("pyinstaller")
    icon_ico = script_dir / "brisasync.ico"

    entrypoint = repo_root / "src" / "brisasync" / "main.py"
    pyinstaller_cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name",
        "brisasync",
        "--paths",
        str(repo_root / "src"),
        "--add-data",
        f"{repo_root / 'src' / 'brisasync' / 'resources'}{os.pathsep}brisasync/resources",
        "--add-binary",
        f"{rclone_bin}{os.pathsep}.",
        "--distpath",
        str(script_dir),
        str(entrypoint),
    ]

    print("Executando PyInstaller...")
    res = subprocess.run(pyinstaller_cmd, check=False)
    if res.returncode != 0:
        print("AVISO: PyInstaller retornou código diferente de zero. Verifique as dependências locais.", file=sys.stderr)
        return res.returncode

    # Renomeia pasta de saída do PyInstaller para dist_win
    pyinstaller_out = script_dir / "brisasync"
    if pyinstaller_out.is_dir():
        shutil.rmtree(build_dir, ignore_errors=True)
        pyinstaller_out.rename(build_dir)

    # 2. Gera ZIP portátil
    zip_name = f"BrisaSync-{VERSION}-windows-x64.zip"
    zip_path = dist_dir / zip_name
    print(f"Gerando pacote portátil {zip_name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(build_dir):
            for f in files:
                full_p = Path(root) / f
                rel_p = full_p.relative_to(build_dir)
                z.write(full_p, f"BrisaSync/{rel_p}")
    print(f"[OK] Pacote portátil gerado: {zip_path}")

    # 3. Compila instalador NSIS se makensis estiver instalado
    makensis = shutil.which("makensis")
    if not makensis:
        for candidate in [
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "NSIS" / "makensis.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "NSIS" / "makensis.exe",
            Path(r"C:\Program Files (x86)\NSIS\makensis.exe"),
            Path(r"C:\Program Files\NSIS\makensis.exe"),
        ]:
            if candidate.is_file():
                makensis = str(candidate)
                break

    if makensis:
        print(f"Compilando instalador NSIS com {makensis}...")
        nsis_script = script_dir / "installer.nsi"
        res_nsis = subprocess.run([makensis, str(nsis_script)], check=False)
        if res_nsis.returncode == 0:
            print("[OK] Instalador NSIS gerado com sucesso em dist/")
        else:
            print(f"ERRO: Falha ao compilar instalador NSIS (código {res_nsis.returncode}).", file=sys.stderr)
            return res_nsis.returncode
    else:
        print("makensis não encontrado no sistema. O instalador .exe requer NSIS instalado.")

    return 0


if __name__ == "__main__":
    sys.exit(main())


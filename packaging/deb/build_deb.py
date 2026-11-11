#!/usr/bin/env python3
"""Construtor de pacotes Debian/Ubuntu (.deb) para o BrisaSync.

Gera pacotes no formato padrão Debian (ar archive contendo debian-binary,
control.tar.gz e data.tar.gz) com compatibilidade nativa para Debian 12+,
Ubuntu 22.04 LTS+, Linux Mint e derivados.
Não requer dpkg-deb instalado (usa empacotamento ar/tarfile padrão).
"""

from __future__ import annotations

import gzip
import io
import os
from pathlib import Path
import shutil
import stat
import struct
import sys
import tarfile
import time

VERSION = "0.1.27"
PKG_REL = "1"
ARCH = "amd64"
PACKAGE_NAME = "brisasync"


def create_ar_archive(out_path: Path, members: list[tuple[str, bytes]]) -> None:
    """Cria um arquivo no formato ar padrão do Debian."""
    # Global ar magic: "!<arch>\n"
    with open(out_path, "wb") as f:
        f.write(b"!<arch>\n")
        for filename, data in members:
            # ar header format:
            # 16 bytes: file identifier
            # 12 bytes: file modification timestamp (decimal)
            # 6 bytes: owner ID (decimal)
            # 6 bytes: group ID (decimal)
            # 8 bytes: file mode (octal)
            # 10 bytes: file size in bytes (decimal)
            # 2 bytes: trailer `\x60\n`
            name_padded = (filename + "/").ljust(16) if not filename.endswith("/") else filename.ljust(16)
            timestamp = str(int(time.time())).ljust(12)
            uid = "0".ljust(6)
            gid = "0".ljust(6)
            mode = "100644".ljust(8)
            size = str(len(data)).ljust(10)
            trailer = b"`\n"
            header = f"{name_padded}{timestamp}{uid}{gid}{mode}{size}".encode("ascii") + trailer
            f.write(header)
            f.write(data)
            # 2-byte alignment padding if odd size
            if len(data) % 2 != 0:
                f.write(b"\n")


def build_control_tar(pkg_dir: Path, installed_size_kb: int) -> bytes:
    control_content = f"""Package: {PACKAGE_NAME}
Version: {VERSION}-{PKG_REL}
Section: utils
Priority: optional
Architecture: {ARCH}
Maintainer: Fábio Agreles <fabioagreles@gmail.com>
Installed-Size: {installed_size_kb}
Depends: python3 (>= 3.11), python3-pyside6, libsecret-tools | kwalletcli, ca-certificates
Recommends: systemd
Homepage: https://brisasync.com.br/
Description: Modern, native, and efficient Google Drive synchronizer
 BrisaSync is a modern graphical synchronization client for Google Drive,
 combining a native Qt6 user interface with the proven reliability
 of the rclone bidirectional synchronization engine.
 Features continuous background operation, safe conflict handling,
 voluntary session vault storage, and full Portuguese (Brazil) and English support.
"""
    postinst_content = """#!/bin/sh
set -e
if [ "$1" = "configure" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
"""
    postrm_content = """#!/bin/sh
set -e
if [ "$1" = "remove" ] || [ "$1" = "purge" ]; then
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q /usr/share/applications || true
    fi
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
    fi
fi
exit 0
"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def add_file(name: str, content: str, mode: int) -> None:
            raw = content.encode("utf-8")
            ti = tarfile.TarInfo(name=name)
            ti.size = len(raw)
            ti.mtime = int(time.time())
            ti.mode = mode
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            tar.addfile(ti, io.BytesIO(raw))

        add_file("./control", control_content, 0o644)
        add_file("./postinst", postinst_content, 0o755)
        add_file("./postrm", postrm_content, 0o755)

    return buf.getvalue()


def build_data_tar(root_dir: Path, rclone_binary: Path) -> tuple[bytes, int]:
    """Empacota a árvore de arquivos de sistema /usr/... e retorna (tar_gz_bytes, size_kb)."""
    buf = io.BytesIO()
    total_size = 0

    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        def add_dir(rel_path: str) -> None:
            ti = tarfile.TarInfo(name=rel_path)
            ti.type = tarfile.DIRTYPE
            ti.mode = 0o755
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            ti.mtime = int(time.time())
            tar.addfile(ti)

        def add_bytes(rel_path: str, data: bytes, mode: int = 0o644) -> None:
            nonlocal total_size
            total_size += len(data)
            ti = tarfile.TarInfo(name=rel_path)
            ti.size = len(data)
            ti.mode = mode
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            ti.mtime = int(time.time())
            tar.addfile(ti, io.BytesIO(data))

        # Diretórios padrão
        for d in (
            "./usr",
            "./usr/bin",
            "./usr/lib",
            "./usr/lib/brisasync",
            "./usr/lib/brisasync/bin",
            "./usr/lib/brisasync/src",
            "./usr/lib/brisasync/src/brisasync",
            "./usr/share",
            "./usr/share/applications",
            "./usr/share/icons",
            "./usr/share/icons/hicolor",
            "./usr/share/icons/hicolor/scalable",
            "./usr/share/icons/hicolor/scalable/apps",
            "./usr/share/icons/hicolor/512x512",
            "./usr/share/icons/hicolor/512x512/apps",
            "./usr/share/doc",
            "./usr/share/doc/brisasync",
        ):
            add_dir(d)

        # 1. Launcher executável /usr/bin/brisasync
        launcher_script = """#!/usr/bin/env sh
export PYTHONPATH="/usr/lib/brisasync/src${PYTHONPATH:+:$PYTHONPATH}"
exec /usr/bin/python3 -m brisasync.main "$@"
"""
        add_bytes("./usr/bin/brisasync", launcher_script.encode("utf-8"), 0o755)

        # 2. Binário rclone empacotado em /usr/lib/brisasync/bin/rclone
        if rclone_binary.is_file():
            add_bytes("./usr/lib/brisasync/bin/rclone", rclone_binary.read_bytes(), 0o755)

        # 3. Código fonte e recursos em /usr/lib/brisasync/src/brisasync
        src_base = root_dir / "src" / "brisasync"
        for root, dirs, files in os.walk(src_base):
            rel_dir = Path(root).relative_to(root_dir / "src")
            target_dir = f"./usr/lib/brisasync/src/{rel_dir.as_posix()}"
            add_dir(target_dir)
            for f in files:
                if f.endswith(".pyc") or f == "__pycache__":
                    continue
                file_path = Path(root) / f
                target_file = f"{target_dir}/{f}"
                is_exec = os.access(file_path, os.X_OK) and not f.endswith((".py", ".json", ".svg", ".png", ".txt"))
                mode = 0o755 if is_exec else 0o644
                add_bytes(target_file, file_path.read_bytes(), mode)

        # 4. Lançador .desktop em /usr/share/applications/brisasync.desktop
        desktop_src = root_dir / "packaging" / "brisasync.desktop"
        if desktop_src.is_file():
            add_bytes("./usr/share/applications/brisasync.desktop", desktop_src.read_bytes(), 0o644)

        # 5. Ícones
        icon_svg = src_base / "resources" / "icons" / "brisasync.svg"
        if icon_svg.is_file():
            add_bytes("./usr/share/icons/hicolor/scalable/apps/brisasync.svg", icon_svg.read_bytes(), 0o644)
        icon_png = src_base / "resources" / "icons" / "brisasync.png"
        if icon_png.is_file():
            add_bytes("./usr/share/icons/hicolor/512x512/apps/brisasync.png", icon_png.read_bytes(), 0o644)

        # 6. Documentação e Licença
        lic_file = root_dir / "LICENSE"
        if lic_file.is_file():
            add_bytes("./usr/share/doc/brisasync/copyright", lic_file.read_bytes(), 0o644)

    return buf.getvalue(), max(1, total_size // 1024)


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    dist_dir = repo_root / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)

    rclone_cand = Path.home() / ".local" / "bin" / "rclone"
    if not rclone_cand.is_file():
        which_r = shutil.which("rclone")
        rclone_cand = Path(which_r) if which_r else rclone_cand

    if not rclone_cand.is_file():
        print(f"ERRO: Executável do rclone não localizado: {rclone_cand}", file=sys.stderr)
        return 1

    print(f"✓ Construindo pacote Debian ({PACKAGE_NAME}_{VERSION}-{PKG_REL}_{ARCH}.deb)...")
    print(f"  Motor rclone: {rclone_cand}")

    data_tar_bytes, size_kb = build_data_tar(repo_root, rclone_cand)
    control_tar_bytes = build_control_tar(repo_root, size_kb)
    debian_binary = b"2.0\n"

    deb_filename = f"{PACKAGE_NAME}_{VERSION}-{PKG_REL}_{ARCH}.deb"
    out_deb = dist_dir / deb_filename

    members = [
        ("debian-binary", debian_binary),
        ("control.tar.gz", control_tar_bytes),
        ("data.tar.gz", data_tar_bytes),
    ]

    create_ar_archive(out_deb, members)
    print(f"✓ Pacote Debian gerado com sucesso: {out_deb} ({out_deb.stat().st_size} bytes, {size_kb} KB instalado)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Utilitários de verificação de integridade de arquivos (SHA-256 e inventário).

Código de saída 0 sozinho não comprova integridade: esta camada calcula hashes
criptográficos (SHA-256), tamanhos e metadados de todos os arquivos para comprovar
que dois diretórios (e seus backups/conflitos) estão exatamente no estado esperado.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path


@dataclass(frozen=True)
class FileDigest:
    """Metadados e hash SHA-256 de um arquivo relativo à raiz sincronizada."""

    relative_path: str
    size_bytes: int
    sha256: str
    mtime_ns: int


@dataclass(frozen=True)
class DirectoryInventory:
    """Inventário completo de uma pasta sincronizada."""

    root: Path
    files: dict[str, FileDigest]

    def hashes_by_path(self, *, ignore_names: set[str] | None = None) -> dict[str, str]:
        ignored = ignore_names or set()
        return {
            rel: digest.sha256
            for rel, digest in sorted(self.files.items())
            if Path(rel).name not in ignored
        }


def sha256_file(path: Path | str) -> str:
    """Calcula o digest SHA-256 completo do conteúdo de um arquivo."""
    hasher = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def build_directory_inventory(root: Path | str) -> DirectoryInventory:
    """Gera o inventário determinístico de todos os arquivos regulares dentro de root."""
    root_path = Path(root).resolve()
    files: dict[str, FileDigest] = {}
    if not root_path.exists():
        return DirectoryInventory(root=root_path, files=files)

    for item in sorted(root_path.rglob("*")):
        if item.is_file() and not item.is_symlink():
            rel = item.relative_to(root_path).as_posix()
            stat = item.stat()
            files[rel] = FileDigest(
                relative_path=rel,
                size_bytes=stat.st_size,
                sha256=sha256_file(item),
                mtime_ns=stat.st_mtime_ns,
            )
    return DirectoryInventory(root=root_path, files=files)


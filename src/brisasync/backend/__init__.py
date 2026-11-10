"""Camada de backend de sincronização e auditoria de integridade do BrisaSync."""

from .integrity import DirectoryInventory, FileDigest, build_directory_inventory, sha256_file
from .rclone_engine import (
    BisyncConfig,
    BisyncExecutionResult,
    RcloneBisyncEngine,
    RemoteDirectoryEntry,
    SENTINEL_CONTENT,
    SENTINEL_FILENAME,
    is_remote_spec,
    resolve_rclone_binary,
)

__all__ = [
    "BisyncConfig",
    "BisyncExecutionResult",
    "DirectoryInventory",
    "FileDigest",
    "RcloneBisyncEngine",
    "RemoteDirectoryEntry",
    "SENTINEL_CONTENT",
    "SENTINEL_FILENAME",
    "build_directory_inventory",
    "is_remote_spec",
    "resolve_rclone_binary",
    "sha256_file",
]

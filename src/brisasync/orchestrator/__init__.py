"""Camada de orquestração e diagnóstico do BrisaSync."""

from .diagnostics import DependencyCheckItem, SystemDiagnostics, collect_system_diagnostics
from .sync_coordinator import (
    ConcurrentSyncError,
    DirectoryAccessError,
    SyncCoordinator,
    is_pid_alive,
    validate_directory_accessible,
    validate_directory_empty_for_initial_sync,
)

__all__ = [
    "ConcurrentSyncError",
    "DependencyCheckItem",
    "DirectoryAccessError",
    "SyncCoordinator",
    "SystemDiagnostics",
    "collect_system_diagnostics",
    "is_pid_alive",
    "validate_directory_accessible",
    "validate_directory_empty_for_initial_sync",
]

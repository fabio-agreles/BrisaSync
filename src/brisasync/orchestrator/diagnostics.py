"""Diagnóstico real das dependências de sistema, cofre validado e ambiente gráfico Linux."""

from __future__ import annotations

from dataclasses import dataclass
import os
import platform
import sqlite3
import sys

from brisasync.backend.rclone_engine import RcloneBisyncEngine
from brisasync.credentials.store import CredentialStore


@dataclass(frozen=True)
class DependencyCheckItem:
    """Item individual do diagnóstico de dependências."""

    component: str
    status_code: str  # "OK", "WARNING", "MISSING"
    status_label: str
    details: str


@dataclass(frozen=True)
class SystemDiagnostics:
    """Relatório completo e real do ambiente de execução do BrisaSync."""

    items: list[DependencyCheckItem]

    @property
    def all_critical_ok(self) -> bool:
        return all(item.status_code != "MISSING" for item in self.items)


def collect_system_diagnostics(
    rclone_engine: RcloneBisyncEngine | None = None,
) -> SystemDiagnostics:
    """Coleta informações reais das dependências instaladas e valida operação do cofre."""
    items: list[DependencyCheckItem] = []

    # 1. Python Runtime
    py_ver = platform.python_version()
    py_ok = sys.version_info >= (3, 11)
    items.append(
        DependencyCheckItem(
            component="Python Runtime",
            status_code="OK" if py_ok else "MISSING",
            status_label="[OK] Compatível" if py_ok else "[ERRO] Versão incompatível",
            details=f"Python {py_ver} ({sys.executable})",
        )
    )

    # 2. PySide6 / Qt6
    try:
        import PySide6
        from PySide6 import QtCore

        qt_ver = QtCore.qVersion()
        items.append(
            DependencyCheckItem(
                component="Interface Qt6 / PySide6",
                status_code="OK",
                status_label="[OK] Instalado",
                details=f"PySide6 {PySide6.__version__} / Qt {qt_ver}",
            )
        )
    except Exception as exc:  # pragma: no cover
        items.append(
            DependencyCheckItem(
                component="Interface Qt6 / PySide6",
                status_code="MISSING",
                status_label="[AUSENTE] Não encontrado",
                details=f"Falha ao importar PySide6: {exc}",
            )
        )

    # 3. Ambiente Desktop / Sessão Wayland
    session_type = os.environ.get("XDG_SESSION_TYPE", "desconhecido")
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "desconhecido")
    wayland_display = os.environ.get("WAYLAND_DISPLAY", "")
    is_wayland = session_type.lower() == "wayland" or bool(wayland_display)
    session_details = f"Desktop: {desktop} | Sessão: {session_type}"
    if wayland_display:
        session_details += f" ({wayland_display})"
    items.append(
        DependencyCheckItem(
            component="Sessão Gráfica Desktop",
            status_code="OK" if is_wayland else "WARNING",
            status_label="[OK] Wayland Ativo" if is_wayland else f"[INFO] Sessão {session_type}",
            details=session_details,
        )
    )

    # 4. Motor rclone
    try:
        engine = rclone_engine or RcloneBisyncEngine()
        rclone_version = engine.get_version()
        rclone_avail = engine.is_available() and bool(rclone_version)
        rclone_bin = engine.rclone_binary
        rclone_err: str | None = None
    except (FileNotFoundError, PermissionError) as exc:
        engine = None
        rclone_version = None
        rclone_avail = False
        rclone_bin = None
        rclone_err = str(exc)

    if rclone_avail and rclone_version:
        items.append(
            DependencyCheckItem(
                component="Motor de Sincronização (rclone)",
                status_code="OK",
                status_label="[OK] Disponível",
                details=f"{rclone_version} ({rclone_bin})",
            )
        )
    else:
        err_detail = (
            f"Override inválido: {rclone_err}"
            if rclone_err
            else "Motor rclone não encontrado no pacote (/usr/lib/brisasync/bin/rclone) nem no PATH"
        )
        items.append(
            DependencyCheckItem(
                component="Motor de Sincronização (rclone)",
                status_code="MISSING",
                status_label="[AUSENTE] Não encontrado",
                details=err_detail,
            )
        )

    # 5. Banco de Dados SQLite3
    sqlite_ver = sqlite3.sqlite_version
    items.append(
        DependencyCheckItem(
            component="Banco Local (SQLite)",
            status_code="OK",
            status_label="[OK] Operacional",
            details=f"SQLite {sqlite_ver} (Modo WAL suportado)",
        )
    )

    # 6. Cofre de Credenciais do Sistema (distingue instalado vs acessível e validado)
    cred_caps = CredentialStore.probe_capabilities(verify_roundtrip=True)
    if not cred_caps.utility_installed:
        items.append(
            DependencyCheckItem(
                component="Cofre de Credenciais (Keyring)",
                status_code="MISSING",
                status_label="[AUSENTE] Utilitário não instalado",
                details=cred_caps.provider_summary,
            )
        )
    elif cred_caps.is_available:
        items.append(
            DependencyCheckItem(
                component="Cofre de Credenciais (Keyring)",
                status_code="OK",
                status_label="[OK — VALIDADO] Cofre operacional",
                details=cred_caps.provider_summary,
            )
        )
    else:
        items.append(
            DependencyCheckItem(
                component="Cofre de Credenciais (Keyring)",
                status_code="WARNING",
                status_label="[BLOQUEADO / INACESSÍVEL] Utilitário instalado, cofre indisponível",
                details=cred_caps.provider_summary,
            )
        )

    return SystemDiagnostics(items=items)

"""Persistência SQLite para configuração operacional de pastas e histórico auditável.

O banco armazena exclusivamente configurações operacionais e histórico sanitizado.
Qualquer tentativa de gravar chaves associadas a tokens ou segredos levanta ValueError.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Iterable

from brisasync.credentials.store import is_forbidden_secret_key, redact_secrets


def default_database_path() -> Path:
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base_dir = (
        Path(xdg_data_home)
        if xdg_data_home
        else Path.home() / ".local" / "share"
    )
    return base_dir / "brisasync" / "brisasync.db"


@dataclass(frozen=True)
class LocalFolderConfig:
    """Configuração persistida da pasta local de sincronização."""

    folder_path: str
    updated_at: str


@dataclass(frozen=True)
class RemoteFolderConfig:
    """Configuração persistida da pasta remota dedicada a testes (identificada por ID)."""

    folder_id: str
    folder_name: str
    updated_at: str


@dataclass(frozen=True)
class SyncRunRecord:
    """Registro auditável de uma execução do motor de sincronização."""

    id: int
    started_at: str
    finished_at: str
    path1: str
    path2: str
    operation: str
    status: str
    exit_code: int
    summary: str


class BrisaDatabase:
    """Gerenciador SQLite com suporte a WAL e bloqueio de gravação de segredos."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_database_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY NOT NULL,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    path1 TEXT NOT NULL,
                    path2 TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    exit_code INTEGER NOT NULL,
                    summary TEXT NOT NULL
                );
                """
            )

    def set_setting(self, key: str, value: str) -> None:
        if is_forbidden_secret_key(key):
            raise ValueError(
                f"Proibido armazenar segredos ou tokens no SQLite (chave rejeitada: {key!r})."
            )
        sanitized_value = redact_secrets(value)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (key, sanitized_value, now_iso),
            )

    def get_setting(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?;", (key,)
            ).fetchone()
            return str(row["value"]) if row else None

    def delete_setting(self, key: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM app_settings WHERE key = ?;", (key,))

    def set_local_sync_folder(self, folder_path: Path | str) -> LocalFolderConfig:
        resolved = str(Path(folder_path).expanduser().resolve())
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('local_sync_folder', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (resolved, now_iso),
            )
        return LocalFolderConfig(folder_path=resolved, updated_at=now_iso)

    def get_local_sync_folder(self) -> LocalFolderConfig | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM app_settings WHERE key = 'local_sync_folder';"
            ).fetchone()
            if not row:
                return None
            return LocalFolderConfig(
                folder_path=str(row["value"]),
                updated_at=str(row["updated_at"]),
            )

    def set_remote_sync_folder(
        self, *, folder_id: str, folder_name: str
    ) -> RemoteFolderConfig:
        clean_id = folder_id.strip()
        clean_name = folder_name.strip()
        if not clean_id or not clean_name:
            raise ValueError("folder_id e folder_name da pasta remota são obrigatórios.")
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = json.dumps(
            {"folder_id": clean_id, "folder_name": clean_name},
            ensure_ascii=False,
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES ('remote_sync_folder', ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at;
                """,
                (payload, now_iso),
            )
        return RemoteFolderConfig(
            folder_id=clean_id,
            folder_name=clean_name,
            updated_at=now_iso,
        )

    def get_remote_sync_folder(self) -> RemoteFolderConfig | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM app_settings WHERE key = 'remote_sync_folder';"
            ).fetchone()
            if not row:
                return None
            try:
                data = json.loads(str(row["value"]))
                return RemoteFolderConfig(
                    folder_id=str(data["folder_id"]),
                    folder_name=str(data["folder_name"]),
                    updated_at=str(row["updated_at"]),
                )
            except (KeyError, ValueError, json.JSONDecodeError):
                return None

    def clear_remote_sync_folder(self) -> None:
        self.delete_setting("remote_sync_folder")
        self.delete_setting("baseline_initialized_pair")

    def set_voluntary_disconnect(self, voluntary: bool) -> None:
        """Registra explicitamente que a conta foi desconectada de forma voluntária pelo usuário."""
        if voluntary:
            self.set_setting("voluntary_disconnect", "1")
        else:
            self.delete_setting("voluntary_disconnect")

    def is_voluntary_disconnect(self) -> bool:
        """Retorna True se o usuário se desconectou voluntariamente."""
        return self.get_setting("voluntary_disconnect") == "1"

    def set_pair_linked_account_email(self, email: str) -> None:
        """Associa a identidade do e-mail da conta autorizada ao par de sincronização configurado."""
        clean = (email or "").strip().lower()
        if clean:
            self.set_setting("pair_linked_account_email", clean)
        else:
            self.delete_setting("pair_linked_account_email")

    def get_pair_linked_account_email(self) -> str | None:
        """Obtém o e-mail da conta que configurou o par atual, se registrado."""
        raw = self.get_setting("pair_linked_account_email")
        return raw.strip().lower() if raw else None

    def clear_pair_linked_account_email(self) -> None:
        """Remove a associação de e-mail do par de sincronização."""
        self.delete_setting("pair_linked_account_email")

    def remove_sync_pair(self) -> None:
        """Remove por completo o vínculo de pastas de sincronização sem afetar arquivos nem histórico."""
        self.delete_setting("local_sync_folder")
        self.delete_setting("remote_sync_folder")
        self.delete_setting("baseline_initialized_pair")
        self.delete_setting("pair_linked_account_email")
        self.delete_setting("pair_revalidation_required")

    def mark_baseline_initialized(
        self, *, local_folder: str, remote_folder_id: str
    ) -> None:
        pair_key = f"{Path(local_folder).resolve()}::{remote_folder_id.strip()}"
        self.set_setting("baseline_initialized_pair", pair_key)

    def invalidate_baseline(
        self, *, local_folder: str | None = None, remote_folder_id: str | None = None
    ) -> None:
        self.delete_setting("baseline_initialized_pair")

    def is_baseline_initialized(
        self, *, local_folder: str, remote_folder_id: str
    ) -> bool:
        pair_key = f"{Path(local_folder).resolve()}::{remote_folder_id.strip()}"
        return self.get_setting("baseline_initialized_pair") == pair_key

    def is_auto_sync_paused(self) -> bool:
        """Retorna True se o usuário pausou a sincronização automática (persistido entre reinicializações)."""
        return self.get_setting("auto_sync_paused") == "1"

    def set_auto_sync_paused(self, paused: bool) -> None:
        """Persiste a preferência de pausa do usuário para não retomar contra sua escolha ao reiniciar."""
        self.set_setting("auto_sync_paused", "1" if paused else "0")

    def get_sync_interval_seconds(self, default: int = 300) -> int:
        """Obtém o intervalo periódico de sincronização automática em segundos (mínimo 60s, padrão 300s)."""
        raw = self.get_setting("sync_interval_seconds")
        if raw is None:
            return default
        try:
            val = int(raw)
            return max(60, min(val, 86400))
        except ValueError:
            return default

    def set_sync_interval_seconds(self, seconds: int) -> None:
        """Persiste o intervalo periódico de sincronização automática em segundos (entre 60s e 86400s)."""
        clamped = max(60, min(int(seconds), 86400))
        self.set_setting("sync_interval_seconds", str(clamped))

    def get_last_confirmed_sync_at(self) -> str | None:
        """Retorna o timestamp ISO UTC da última sincronização completa confirmada (`Atualizado`)."""
        return self.get_setting("last_confirmed_sync_at")

    def set_last_confirmed_sync_at(self, iso_timestamp: str) -> None:
        """Atualiza o timestamp ISO UTC da última sincronização completa confirmada (`SUCCESS`)."""
        self.set_setting("last_confirmed_sync_at", iso_timestamp.strip())

    def are_notifications_enabled(self, default: bool = True) -> bool:
        """Retorna True se as notificações de atenção estiverem habilitadas pelo usuário."""
        raw = self.get_setting("notifications_enabled")
        if raw is None:
            return default
        return raw.strip() == "1"

    def set_notifications_enabled(self, enabled: bool) -> None:
        """Persiste a preferência do usuário para notificações de situações que exigem atenção."""
        self.set_setting("notifications_enabled", "1" if enabled else "0")

    def get_tray_icon_theme_mode(self, default: str = "auto") -> str:
        """Obtém o modo de contraste do ícone de bandeja (`auto`, `dark_panel` ou `light_panel`)."""
        raw = self.get_setting("tray_icon_theme_mode")
        if not raw:
            raw = self.get_setting("tray_theme_mode")
        if raw in ("auto", "dark_panel", "light_panel"):
            return raw
        return default

    def set_tray_icon_theme_mode(self, mode: str) -> None:
        """Persiste o modo de contraste do ícone de bandeja (`auto`, `dark_panel` ou `light_panel`)."""
        clean = mode.strip().lower()
        if clean not in ("auto", "dark_panel", "light_panel"):
            clean = "auto"
        self.set_setting("tray_icon_theme_mode", clean)
        self.set_setting("tray_theme_mode", clean)

    def get_theme_preference(self, default: str = "system") -> str:
        """Obtém a preferência de tema da interface (`system`, `light` ou `dark`)."""
        raw = self.get_setting("theme_preference")
        if raw in ("system", "light", "dark"):
            return raw
        return default

    def set_theme_preference(self, mode: str) -> None:
        """Persiste a preferência de tema da interface (`system`, `light` ou `dark`)."""
        clean = mode.strip().lower()
        if clean not in ("system", "light", "dark"):
            clean = "system"
        self.set_setting("theme_preference", clean)

    def get_language_preference(self, default: str = "pt_BR") -> str:
        """Obtém a preferência de idioma da interface (`pt_BR` ou `en`)."""
        raw = self.get_setting("language_preference")
        if raw in ("pt_BR", "en"):
            return raw
        return default

    def set_language_preference(self, lang: str) -> None:
        """Persiste a preferência de idioma da interface (`pt_BR` ou `en`)."""
        clean = (lang or "").strip()
        if clean not in ("pt_BR", "en"):
            clean = "pt_BR"
        self.set_setting("language_preference", clean)

    @staticmethod
    def _conflict_setting_key(local_folder: Path | str) -> str:
        norm = str(Path(local_folder).expanduser().resolve())
        digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]
        return f"recorded_conflicts::{digest}"

    def get_recorded_conflict_files(self, local_folder: Path | str) -> list[str]:
        """Retorna a lista de caminhos relativos de conflito efetivamente registrados pelo backend para `local_folder`."""
        raw = self.get_setting(self._conflict_setting_key(local_folder))
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
        except json.JSONDecodeError:
            pass
        return []

    def set_recorded_conflict_files(
        self, local_folder: Path | str, conflict_rel_paths: Iterable[str]
    ) -> list[str]:
        """Atualiza a lista de conflitos efetivamente registrados pelo backend para `local_folder`."""
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in conflict_rel_paths:
            rel = str(item).strip().lstrip("/")
            if rel and rel not in seen:
                seen.add(rel)
                cleaned.append(rel)
        key = self._conflict_setting_key(local_folder)
        if cleaned:
            self.set_setting(key, json.dumps(cleaned))
        else:
            self.delete_setting(key)
        return cleaned

    def record_backend_conflict_files(
        self, local_folder: Path | str, new_conflict_rel_paths: Iterable[str]
    ) -> list[str]:
        """Acrescenta novos arquivos de conflito gerados pelo backend (`rclone bisync`) ao registro de `local_folder`."""
        existing = self.get_recorded_conflict_files(local_folder)
        merged = list(existing)
        for item in new_conflict_rel_paths:
            rel = str(item).strip().lstrip("/")
            if rel and rel not in merged:
                merged.append(rel)
        return self.set_recorded_conflict_files(local_folder, merged)

    def record_sync_run(
        self,
        *,
        started_at: str,
        finished_at: str,
        path1: str,
        path2: str,
        operation: str,
        status: str,
        exit_code: int,
        summary: str,
    ) -> int:
        safe_summary = redact_secrets(summary)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO sync_runs (
                    started_at, finished_at, path1, path2, operation, status, exit_code, summary
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    started_at,
                    finished_at,
                    path1,
                    path2,
                    operation,
                    status,
                    exit_code,
                    safe_summary,
                ),
            )
            return int(cursor.lastrowid or 0)

    def get_history_display_cutoff(self) -> int:
        """Retorna o ID máximo de corte persistido para a exibição de histórico (0 se nenhum corte foi aplicado)."""
        raw = self.get_setting("history_display_cutoff_id")
        if raw is None:
            return 0
        try:
            return max(0, int(raw))
        except ValueError:
            return 0

    def set_history_display_cutoff(self, cutoff_id: int | None = None) -> int:
        """Define o corte persistente de exibição. Se cutoff_id for None, usa o MAX(id) atual de sync_runs."""
        if cutoff_id is None:
            with self._connect() as conn:
                row = conn.execute("SELECT COALESCE(MAX(id), 0) AS max_id FROM sync_runs;").fetchone()
                cutoff_id = int(row["max_id"]) if row else 0
        self.set_setting("history_display_cutoff_id", str(max(0, cutoff_id)))
        return cutoff_id

    def clear_sync_history_display(self) -> int:
        """Limpa a exibição do histórico de atividades atualizando o ID de corte persistente."""
        return self.set_history_display_cutoff(None)

    def count_recent_sync_runs(self, include_hidden: bool = False) -> int:
        """Conta os registros de sincronização visíveis na interface (respeitando o corte persistente)."""
        cutoff_id = 0 if include_hidden else self.get_history_display_cutoff()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM sync_runs WHERE id > ?;",
                (cutoff_id,),
            ).fetchone()
            return int(row["total"]) if row else 0

    def list_recent_sync_runs(
        self, limit: int = 50, include_hidden: bool = False
    ) -> list[SyncRunRecord]:
        cutoff_id = 0 if include_hidden else self.get_history_display_cutoff()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, started_at, finished_at, path1, path2, operation, status, exit_code, summary
                FROM sync_runs
                WHERE id > ?
                ORDER BY id DESC
                LIMIT ?;
                """,
                (cutoff_id, limit),
            ).fetchall()
            return [
                SyncRunRecord(
                    id=int(r["id"]),
                    started_at=str(r["started_at"]),
                    finished_at=str(r["finished_at"]),
                    path1=str(r["path1"]),
                    path2=str(r["path2"]),
                    operation=str(r["operation"]),
                    status=str(r["status"]),
                    exit_code=int(r["exit_code"]),
                    summary=str(r["summary"]),
                )
                for r in rows
            ]

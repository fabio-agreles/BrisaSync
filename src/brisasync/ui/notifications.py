"""Gerenciador de notificações desktop configuráveis, agrupadas, deduplicadas e sanitizadas.

Regras estritas de privacidade e usabilidade:
1. Emite notificações somente para situações que exigem atenção do usuário:
   - `AUTH_EXPIRED`: autenticação expirada/revogada ou cofre bloqueado.
   - `CONFLICT_DETECTED`: conflitos detectados e preservados (agrupados por contagem, nunca 1 por arquivo).
   - `PERSISTENT_FAILURE`: falha persistente de sincronização ou de devolução ao cofre.
   - `RECOVERY_REQUIRED`: proteção contra exclusões em massa, sentinela ausente ou pasta inacessível.
2. Jamais emite uma notificação por arquivo ou por ciclo concluído com sucesso (`SUCCESS`).
3. Agrupa eventos e evita repetição contínua do mesmo erro enquanto a condição persistir.
4. Jamais inclui tokens, conteúdo de arquivos ou detalhes pessoais (como e-mail) na notificação.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import shutil
import subprocess
from typing import Callable

from brisasync.credentials.store import redact_secrets
from brisasync.i18n import tr
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_CONFLICT_DETECTED,
    ATTENTION_PERSISTENT_FAILURE,
    ATTENTION_RECOVERY_REQUIRED,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase

ALLOWED_ATTENTION_CATEGORIES: frozenset[str] = frozenset(
    {
        ATTENTION_AUTH_EXPIRED,
        ATTENTION_CONFLICT_DETECTED,
        ATTENTION_PERSISTENT_FAILURE,
        ATTENTION_RECOVERY_REQUIRED,
    }
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def sanitize_notification_text(text: str) -> str:
    """Remove qualquer segredo/token e mascara endereços de e-mail para proteger privacidade em popups."""
    redacted = redact_secrets(text or "")
    return _EMAIL_RE.sub("[CONTA]", redacted).strip()


@dataclass(frozen=True)
class NotificationRecord:
    """Registro auditável de uma notificação emitida na sessão."""

    category: str
    signature: str
    title: str
    body: str
    emitted_at: str


class NotificationManager:
    """Avalia snapshots do serviço e emite notificações agrupadas sem repetição contínua."""

    def __init__(
        self,
        database: BrisaDatabase,
        *,
        tray_sender: Callable[[str, str], bool] | None = None,
        allow_notify_send: bool = True,
    ) -> None:
        self.database = database
        self.tray_sender = tray_sender
        self.allow_notify_send = allow_notify_send
        self._last_emitted_signature: str | None = None
        self.emitted_history: list[NotificationRecord] = []

    @property
    def last_notification(self) -> NotificationRecord | None:
        return self.emitted_history[-1] if self.emitted_history else None

    def reset_deduplication(self) -> None:
        self._last_emitted_signature = None

    def evaluate_snapshot(
        self, snapshot: ServiceStatusSnapshot
    ) -> NotificationRecord | None:
        """Avalia o estado atual do serviço e emite notificação apenas se houver novo evento de atenção."""
        category = snapshot.attention_category
        if not category or category not in ALLOWED_ATTENTION_CATEGORIES:
            # Quando o problema é resolvido, limpa a assinatura para permitir notificar evento futuro
            if not snapshot.is_cycle_active and snapshot.last_run_status == "SUCCESS":
                self._last_emitted_signature = None
            return None

        if not self.database.are_notifications_enabled(default=True):
            return None

        # Constrói assinatura agrupada: para conflitos, agrupa em um único alerta até que a contagem aumente;
        # para erros contínuos da mesma categoria, não repete a cada ciclo.
        if category == ATTENTION_CONFLICT_DETECTED:
            sig = f"{category}::count={snapshot.conflict_files_count}"
        else:
            sig = f"{category}::{snapshot.attention_title or category}"

        if sig == self._last_emitted_signature:
            return None

        if category == ATTENTION_CONFLICT_DETECTED:
            raw_title = tr("notif_title_conflict")
            raw_body = tr("notif_body_conflict", count=snapshot.conflict_files_count)
        elif category == ATTENTION_AUTH_EXPIRED:
            raw_title = tr("notif_title_auth_expired")
            raw_body = snapshot.attention_explanation or tr("notif_body_auth_expired")
        elif category == ATTENTION_RECOVERY_REQUIRED and any(
            k in (snapshot.attention_title or "").lower() for k in ("exclusão", "deletion", "salvaguarda")
        ):
            raw_title = tr("notif_title_mass_deletion")
            raw_body = snapshot.attention_explanation or tr("notif_body_mass_deletion")
        elif category == ATTENTION_PERSISTENT_FAILURE:
            raw_title = tr("notif_title_failure")
            raw_body = snapshot.attention_explanation or tr("notif_body_default")
        else:
            raw_title = snapshot.attention_title or tr("notif_title_attention")
            raw_body = snapshot.attention_explanation or tr("notif_body_default")

        safe_title = sanitize_notification_text(raw_title)
        safe_body = sanitize_notification_text(raw_body)

        self._last_emitted_signature = sig
        record = NotificationRecord(
            category=category,
            signature=sig,
            title=safe_title,
            body=safe_body,
            emitted_at=datetime.now(timezone.utc).isoformat(),
        )
        self.emitted_history.append(record)
        self._dispatch_to_desktop(safe_title, safe_body)
        return record

    def _dispatch_to_desktop(self, title: str, body: str) -> None:
        sent_by_tray = False
        if self.tray_sender is not None:
            try:
                sent_by_tray = bool(self.tray_sender(title, body))
            except Exception:
                sent_by_tray = False

        if sent_by_tray or not self.allow_notify_send:
            return

        notify_bin = shutil.which("notify-send")
        if notify_bin:
            try:
                subprocess.run(
                    [
                        notify_bin,
                        "--app-name=BrisaSync",
                        "--icon=brisasync",
                        title,
                        body,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
            except (OSError, subprocess.SubprocessError):
                pass


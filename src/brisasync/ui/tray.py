"""Controlador da bandeja opcional do sistema (`QSystemTrayIcon`) do BrisaSync.

Garantias arquiteturais:
- Mantido vivo exclusivamente pelo processo gráfico (`QApplication`), sem adicionar
  nenhuma dependência gráfica ao serviço de sincronização (`brisasync --service`).
- Todas as ações de sincronização delegam ao `ServiceIPCClient` existente (através da
  janela principal), sem criar agendador ou processo paralelo.
- Detecta disponibilidade real da bandeja (`QSystemTrayIcon.isSystemTrayAvailable()`).
  Se não houver bandeja disponível na sessão (ou se `--no-tray` for usado), o aplicativo
  opera integralmente pela janela principal e pelo lançador.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon, QWidget

from brisasync import __app_name__
from brisasync.credentials.store import CredentialStore
from brisasync.i18n import get_state_label, tr
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_VAULT_LOCKED,
    STATE_ATTENTION_REQUIRED,
    STATE_LABELS,
    STATE_OFFLINE,
    STATE_PAUSED,
    STATE_PAUSING,
    STATE_SYNCING,
    STATE_VERIFYING,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.icons import (
    TRAY_STATE_ATTENTION,
    TRAY_STATE_HEALTHY,
    TRAY_STATE_PAUSED,
    TRAY_STATE_SYNCING,
    resolve_tray_icon_for_state,
)


class BrisaTrayController(QObject):
    """Gerencia o ícone simbólico e o menu de contexto na bandeja do sistema."""

    open_panel_requested = Signal()
    open_local_folder_requested = Signal()
    sync_now_requested = Signal()
    pause_or_resume_requested = Signal()
    quit_ui_keep_service_requested = Signal()
    shutdown_service_requested = Signal()
    quit_requested = Signal()

    def __init__(
        self,
        database: BrisaDatabase,
        *,
        credential_store: CredentialStore | None = None,
        parent_widget: QWidget | None = None,
        enable_tray: bool = True,
        force_tray_available: bool | None = None,
    ) -> None:
        super().__init__(parent_widget)
        self.database = database
        self.credential_store = credential_store or CredentialStore()
        self._parent_widget = parent_widget
        self._is_paused_cached: bool = self.database.is_auto_sync_paused()

        is_offscreen = QGuiApplication.platformName().lower() == "offscreen"
        if force_tray_available is not None:
            sys_avail = bool(force_tray_available)
        elif is_offscreen:
            sys_avail = False
        else:
            sys_avail = bool(QSystemTrayIcon.isSystemTrayAvailable())
        self.is_available: bool = bool(enable_tray and sys_avail)
        self._is_offscreen: bool = is_offscreen

        self._current_state: str = (
            TRAY_STATE_PAUSED if self._is_paused_cached else TRAY_STATE_HEALTHY
        )
        self._theme_mode: str = self.database.get_tray_icon_theme_mode(default="auto")
        self._last_snapshot: ServiceStatusSnapshot | None = None

        self.tray_icon: QSystemTrayIcon | None = None
        self.current_icon: QIcon = QIcon()
        self.tooltip_text: str = ""
        self.menu: QMenu | None = None

        self.status_header_action: QAction | None = None
        self.updated_header_action: QAction | None = None
        self.open_panel_action: QAction | None = None
        self.open_folder_action: QAction | None = None
        self.sync_now_action: QAction | None = None
        self.pause_resume_action: QAction | None = None
        self.quit_action: QAction | None = None
        self.quit_ui_action: QAction | None = None
        self.shutdown_service_action: QAction | None = None

        if self.is_available:
            self._setup_tray()

    @property
    def is_currently_paused(self) -> bool:
        return self._is_paused_cached

    def has_account_connected(self) -> bool:
        """Determina se há uma conta Google conectada e utilizável no cofre."""
        if self.database.is_voluntary_disconnect():
            return False
        if self.credential_store is not None:
            if self.credential_store.is_vault_locked():
                return True
            try:
                creds = self.credential_store.load_credentials(interactive=False)
                return bool(creds and creds.access_token)
            except Exception:
                return False
        return bool(self.database.get_pair_linked_account_email())

    def is_no_account_state(self, snapshot: ServiceStatusSnapshot | None) -> bool:
        """Detecta confiavelmente ausência de conta configurada ou desconexão voluntária, neutralizando snapshots antigos."""
        if self.database.is_voluntary_disconnect():
            return True
        if self.credential_store and self.credential_store.is_vault_locked():
            return False
        has_acct = self.has_account_connected()
        if snapshot is not None:
            # Alertas legítimos com conta vinculada não são considerados "sem conta"
            if snapshot.attention_category in (ATTENTION_AUTH_EXPIRED, ATTENTION_VAULT_LOCKED) and has_acct:
                return False
            detail_lower = (snapshot.detail_message or "").lower()
            error_lower = (snapshot.last_error_reason or "").lower()
            if "nenhuma conta" in detail_lower or "nenhuma conta" in error_lower or "no account" in detail_lower or "no account" in error_lower:
                return True
            if not getattr(snapshot, "configured_pair_ready", False) and not has_acct:
                return True
            return False
        return not has_acct

    def _setup_tray(self) -> None:
        self._theme_mode = self.database.get_tray_icon_theme_mode(default="auto")
        if self.is_no_account_state(None):
            self._current_state = TRAY_STATE_HEALTHY
        self.current_icon = resolve_tray_icon_for_state(
            self._current_state, mode=self._theme_mode
        )
        self.tooltip_text = tr("tray_tooltip_active", app_name=__app_name__)

        menu = QMenu(self._parent_widget)

        initial_st_lbl = get_state_label(STATE_WAITING)
        self.status_header_action = QAction(tr("tray_status_header", status=initial_st_lbl), menu)
        self.status_header_action.setEnabled(False)

        self.updated_header_action = QAction(tr("tray_updated_none"), menu)
        self.updated_header_action.setEnabled(False)

        self.open_panel_action = QAction(tr("tray_action_open_panel"), menu)
        self.open_panel_action.triggered.connect(self.open_panel_requested.emit)

        self.open_folder_action = QAction(tr("tray_action_open_folder"), menu)
        self.open_folder_action.triggered.connect(self.open_local_folder_requested.emit)
        self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))

        self.sync_now_action = QAction(tr("tray_action_sync_now"), menu)
        self.sync_now_action.triggered.connect(self.sync_now_requested.emit)

        initial_pause_label = (
            tr("tray_action_resume")
            if self._is_paused_cached
            else tr("tray_action_pause")
        )
        self.pause_resume_action = QAction(initial_pause_label, menu)
        self.pause_resume_action.triggered.connect(
            self.pause_or_resume_requested.emit
        )

        if self.is_no_account_state(None):
            self.status_header_action.setText(tr("tray_status_header_no_account"))
            self.tooltip_text = tr("tray_tooltip_no_account", app_name=__app_name__)
            self.sync_now_action.setEnabled(False)
            self.pause_resume_action.setEnabled(False)

        self.quit_action = QAction(tr("tray_action_quit"), menu)
        self.quit_action.triggered.connect(self.quit_requested.emit)

        # Ações mantidas para compatibilidade retroativa e testes
        self.quit_ui_action = QAction(
            tr("tray_action_quit_ui"), menu
        )
        self.quit_ui_action.triggered.connect(
            self.quit_ui_keep_service_requested.emit
        )

        self.shutdown_service_action = QAction(
            tr("tray_action_shutdown_service"), menu
        )
        self.shutdown_service_action.triggered.connect(
            self.shutdown_service_requested.emit
        )

        menu.addAction(self.status_header_action)
        menu.addAction(self.updated_header_action)
        menu.addSeparator()
        menu.addAction(self.open_panel_action)
        menu.addAction(self.open_folder_action)
        menu.addSeparator()
        menu.addAction(self.sync_now_action)
        menu.addAction(self.pause_resume_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)

        self.menu = menu

        if not self._is_offscreen:
            tray = QSystemTrayIcon(self.current_icon, self._parent_widget)
            tray.setToolTip(self.tooltip_text)
            tray.setContextMenu(menu)
            tray.activated.connect(self._on_tray_activated)
            tray.show()
            self.tray_icon = tray

    def _on_tray_activated(
        self, reason: QSystemTrayIcon.ActivationReason
    ) -> None:
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.open_panel_requested.emit()

    def set_theme_mode(self, mode: str) -> None:
        """Define o modo de contraste do ícone da bandeja e atualiza imediatamente."""
        clean_mode = (mode or "auto").strip().lower()
        self._theme_mode = clean_mode
        self.refresh_icon(mode=clean_mode)

    def refresh_icon(self, mode: str | None = None) -> None:
        """Atualiza o ícone simbólico da bandeja para refletir o modo e o estado operacional atual."""
        if not self.is_available:
            return
        effective_mode = mode or self._theme_mode or self.database.get_tray_icon_theme_mode(default="auto")
        self._theme_mode = effective_mode
        self.current_icon = resolve_tray_icon_for_state(
            self._current_state, mode=effective_mode
        )
        if self.tray_icon is not None:
            self.tray_icon.setIcon(self.current_icon)

    def update_from_snapshot(self, snapshot: ServiceStatusSnapshot | None) -> None:
        """Sincroniza os textos, ícone de estado e ações da bandeja com o snapshot real do serviço."""
        self._last_snapshot = snapshot
        if not self.is_available:
            return

        # 1. Prioridade absoluta: Desconexão voluntária
        if self.database.is_voluntary_disconnect():
            self._current_state = TRAY_STATE_HEALTHY
            if self.status_header_action is not None:
                self.status_header_action.setText(tr("tray_status_header_no_account"))
            if self.pause_resume_action is not None:
                self.pause_resume_action.setText(tr("tray_action_pause"))
                self.pause_resume_action.setEnabled(False)
            if self.sync_now_action is not None:
                self.sync_now_action.setEnabled(False)
            if self.open_folder_action is not None:
                self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))
            if self.updated_header_action is not None:
                self.updated_header_action.setText(tr("tray_updated_none"))
            if self.shutdown_service_action is not None:
                self.shutdown_service_action.setEnabled(snapshot is not None)
            self.tooltip_text = tr("tray_tooltip_no_account", app_name=__app_name__)
            if self.tray_icon is not None:
                self.tray_icon.setToolTip(self.tooltip_text)
            self.refresh_icon()
            return

        # 2. Alertas legítimos
        is_locked = bool(
            (self.credential_store and self.credential_store.is_vault_locked())
            or (snapshot and snapshot.attention_category == ATTENTION_VAULT_LOCKED)
        )
        if is_locked:
            self._current_state = TRAY_STATE_ATTENTION
            st_lbl = get_state_label(STATE_ATTENTION_REQUIRED)
            if self.status_header_action is not None:
                self.status_header_action.setText(tr("tray_status_header", status=st_lbl))
            if self.pause_resume_action is not None:
                self.pause_resume_action.setText(tr("tray_action_pause"))
                self.pause_resume_action.setEnabled(False)
            if self.sync_now_action is not None:
                self.sync_now_action.setEnabled(False)
            if self.open_folder_action is not None:
                self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))
            if self.shutdown_service_action is not None:
                self.shutdown_service_action.setEnabled(snapshot is not None)
            detail = tr("tray_tooltip_vault_locked_detail")
            self.tooltip_text = tr(
                "tray_tooltip_state_detail",
                app_name=__app_name__,
                status=st_lbl,
                detail=detail,
            )
            if self.tray_icon is not None:
                self.tray_icon.setToolTip(self.tooltip_text)
            self.refresh_icon()
            return

        is_auth_expired = bool(snapshot and snapshot.attention_category == ATTENTION_AUTH_EXPIRED)
        if is_auth_expired and not self.is_no_account_state(snapshot):
            self._current_state = TRAY_STATE_ATTENTION
            st_lbl = get_state_label(STATE_ATTENTION_REQUIRED)
            if self.status_header_action is not None:
                self.status_header_action.setText(tr("tray_status_header", status=st_lbl))
            if self.pause_resume_action is not None:
                self.pause_resume_action.setText(tr("tray_action_pause"))
                self.pause_resume_action.setEnabled(False)
            if self.sync_now_action is not None:
                self.sync_now_action.setEnabled(False)
            if self.open_folder_action is not None:
                self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))
            if self.shutdown_service_action is not None:
                self.shutdown_service_action.setEnabled(snapshot is not None)
            detail = tr("tray_tooltip_auth_expired_detail")
            self.tooltip_text = tr(
                "tray_tooltip_state_detail",
                app_name=__app_name__,
                status=st_lbl,
                detail=detail,
            )
            if self.tray_icon is not None:
                self.tray_icon.setToolTip(self.tooltip_text)
            self.refresh_icon()
            return

        # 3. Estado neutro: Sem conta conectada
        if self.is_no_account_state(snapshot):
            self._current_state = TRAY_STATE_HEALTHY
            if self.status_header_action is not None:
                self.status_header_action.setText(tr("tray_status_header_no_account"))
            if self.pause_resume_action is not None:
                self.pause_resume_action.setText(tr("tray_action_pause"))
                self.pause_resume_action.setEnabled(False)
            if self.sync_now_action is not None:
                self.sync_now_action.setEnabled(False)
            if self.open_folder_action is not None:
                self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))
            if self.updated_header_action is not None:
                self.updated_header_action.setText(tr("tray_updated_none"))
            if self.shutdown_service_action is not None:
                self.shutdown_service_action.setEnabled(snapshot is not None)
            self.tooltip_text = tr("tray_tooltip_no_account", app_name=__app_name__)
            if self.tray_icon is not None:
                self.tray_icon.setToolTip(self.tooltip_text)
            self.refresh_icon()
            return

        if snapshot is None:
            self._is_paused_cached = self.database.is_auto_sync_paused()
            self._current_state = (
                TRAY_STATE_PAUSED if self._is_paused_cached else TRAY_STATE_HEALTHY
            )
            raw_state = STATE_PAUSED if self._is_paused_cached else STATE_WAITING
            st_lbl = get_state_label(raw_state)
            if self.status_header_action is not None:
                self.status_header_action.setText(
                    tr("tray_status_header_stopped", status=st_lbl)
                )
            has_pair = bool(
                self.database.get_local_sync_folder()
                and self.database.get_remote_sync_folder()
            )
            if self.pause_resume_action is not None:
                self.pause_resume_action.setEnabled(True)
                self.pause_resume_action.setText(
                    tr("tray_action_resume")
                    if self._is_paused_cached
                    else tr("tray_action_pause")
                )
            if self.sync_now_action is not None:
                self.sync_now_action.setEnabled(has_pair and not self._is_paused_cached)
            if self.open_folder_action is not None:
                self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))
            if self.shutdown_service_action is not None:
                self.shutdown_service_action.setEnabled(False)
            self.tooltip_text = tr("tray_tooltip_stopped", app_name=__app_name__, status=st_lbl)
            if self.tray_icon is not None:
                self.tray_icon.setToolTip(self.tooltip_text)
            self.refresh_icon()
            return

        self._is_paused_cached = bool(
            snapshot.auto_sync_paused or snapshot.state == STATE_PAUSING
        )

        # Semântica rigorosa dos 4 estados operacionais:
        if snapshot.state in (STATE_SYNCING, STATE_VERIFYING) or getattr(
            snapshot, "is_cycle_active", False
        ):
            self._current_state = TRAY_STATE_SYNCING
        elif snapshot.auto_sync_paused or snapshot.state in (STATE_PAUSED, STATE_PAUSING):
            self._current_state = TRAY_STATE_PAUSED
        elif snapshot.state in (STATE_ATTENTION_REQUIRED, STATE_OFFLINE):
            self._current_state = TRAY_STATE_ATTENTION
        else:
            self._current_state = TRAY_STATE_HEALTHY

        st_lbl = get_state_label(snapshot.state)
        if self.status_header_action is not None:
            self.status_header_action.setText(tr("tray_status_header", status=st_lbl))
        if self.updated_header_action is not None:
            if snapshot.last_confirmed_sync_at:
                self.updated_header_action.setText(
                    tr("tray_updated_header", time=snapshot.last_confirmed_sync_at)
                )
            else:
                self.updated_header_action.setText(tr("tray_updated_none"))

        has_pair = bool(
            self.database.get_local_sync_folder()
            and self.database.get_remote_sync_folder()
        )
        pair_ready = getattr(snapshot, "configured_pair_ready", has_pair)
        is_cycle_active = getattr(snapshot, "is_cycle_active", False)

        if self.pause_resume_action is not None:
            self.pause_resume_action.setEnabled(True)
            self.pause_resume_action.setText(
                tr("tray_action_resume")
                if self._is_paused_cached
                else tr("tray_action_pause")
            )
        if self.sync_now_action is not None:
            self.sync_now_action.setEnabled(pair_ready and not is_cycle_active)
        if self.open_folder_action is not None:
            self.open_folder_action.setEnabled(bool(self.database.get_local_sync_folder()))
        if self.shutdown_service_action is not None:
            self.shutdown_service_action.setEnabled(True)

        detail = ""
        if snapshot.attention_category == ATTENTION_AUTH_EXPIRED:
            detail = tr("tray_tooltip_auth_expired_detail")
        elif snapshot.attention_category == ATTENTION_VAULT_LOCKED:
            detail = tr("tray_tooltip_vault_locked_detail")
        else:
            detail = (snapshot.detail_message or "").strip()

        if detail:
            self.tooltip_text = tr(
                "tray_tooltip_state_detail",
                app_name=__app_name__,
                status=st_lbl,
                detail=detail,
            )
        else:
            self.tooltip_text = tr(
                "tray_tooltip_state",
                app_name=__app_name__,
                status=st_lbl,
            )
        if self.tray_icon is not None:
            self.tray_icon.setToolTip(self.tooltip_text)

        self.refresh_icon()

    def retranslate_tray(self) -> None:
        """Atualiza todos os textos das ações de menu e tooltip no idioma selecionado."""
        if self.open_panel_action is not None:
            self.open_panel_action.setText(tr("tray_action_open_panel"))
        if self.open_folder_action is not None:
            self.open_folder_action.setText(tr("tray_action_open_folder"))
        if self.sync_now_action is not None:
            self.sync_now_action.setText(tr("tray_action_sync_now"))
        if self.quit_action is not None:
            self.quit_action.setText(tr("tray_action_quit"))
        if self.quit_ui_action is not None:
            self.quit_ui_action.setText(tr("tray_action_quit_ui"))
        if self.shutdown_service_action is not None:
            self.shutdown_service_action.setText(tr("tray_action_shutdown_service"))
        self.update_from_snapshot(self._last_snapshot)

    def send_tray_message(
        self,
        title: str,
        body: str,
        *,
        is_warning: bool = False,
        timeout_ms: int = 6000,
    ) -> bool:
        """Exibe notificação nativa pela bandeja se suportada e ativa."""
        if (
            not self.is_available
            or self.tray_icon is None
            or not self.tray_icon.isVisible()
            or not QSystemTrayIcon.supportsMessages()
        ):
            return False
        msg_icon = (
            QSystemTrayIcon.MessageIcon.Warning
            if is_warning
            else QSystemTrayIcon.MessageIcon.Information
        )
        self.tray_icon.showMessage(
            title,
            body,
            msg_icon,
            timeout_ms,
        )
        return True

    def hide_and_cleanup(self) -> None:
        if self.tray_icon is not None:
            try:
                self.tray_icon.hide()
                self.tray_icon.setContextMenu(None)
            except RuntimeError:
                pass
            self.tray_icon = None
        if self.menu is not None:
            try:
                self.menu.clear()
            except RuntimeError:
                pass
            self.menu = None

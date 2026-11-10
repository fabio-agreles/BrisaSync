"""Janela principal do BrisaSync em PySide6 / Qt6 (v0.1.6 — Barra Lateral e Painel em Cartões).

Diretrizes seguidas:
- Barra lateral fixa (~230px) com identidade BrisaSync, navegação em 4 páginas:
  1. Visão geral: Hero Status Banner, estado das pastas, atividade recente e ações rápidas.
  2. Pastas: Cartão horizontal do par configurado e controles de pastas.
  3. Atividade: Histórico auditável de sincronizações registradas no SQLite.
  4. Ajustes: Conta, motor de sincronização, preferências do sistema e opções avançadas.
- Cores de alto contraste (#0B0F15 fundo, #131923 cartões, #273140 bordas sutis, #9189FF lavanda).
- Ícones vetoriais nativos de alta fidelidade sem dependência de emojis.
- Preserva todas as garantias existentes: PySide6, serviço da sessão (IPC AF_UNIX + SO_PEERCRED),
  rclone bisync, cofre da sessão (Secret Service), modo sem bandeja e proteção contra exclusão.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re
from typing import Any

from PySide6.QtCore import QEvent, QRect, QRectF, QSize, QTimer, QUrl, Qt
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QEnterEvent,
    QFocusEvent,
    QFont,
    QFontMetrics,
    QHideEvent,
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QApplication,
    QBoxLayout,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from brisasync import __app_name__, __version__
from brisasync.backend.rclone_engine import (
    RcloneBisyncEngine,
    RemoteDirectoryEntry,
)
from brisasync.credentials.oauth_google import (
    OAuthClientConfig,
    OAuthConfigurationError,
    default_oauth_client_config_path,
)
from brisasync.credentials.rclone_bridge import REMOTE_NAME, RcloneEncryptedBridge
from brisasync.credentials.store import (
    CredentialStore,
    OAuthCredentials,
    VaultLockedError,
    VaultUnavailableError,
)
from brisasync.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    get_current_language,
    get_state_label,
    set_current_language,
    tr,
)
from brisasync.orchestrator.diagnostics import (
    SystemDiagnostics,
    collect_system_diagnostics,
)
from brisasync.orchestrator.sync_coordinator import (
    DirectoryAccessError,
    validate_directory_accessible,
    validate_directory_empty_for_initial_sync,
)
from brisasync.service.autostart import (
    BrisaAutostartCoordinator,
    SystemdUserAutostartManager,
)
from brisasync.service.ipc_client import ServiceIPCClient, ServiceUnavailableError
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_CONFLICT_DETECTED,
    ATTENTION_PERSISTENT_FAILURE,
    ATTENTION_RECOVERY_REQUIRED,
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
from brisasync.storage.database import BrisaDatabase, SyncRunRecord
from brisasync.support import (
    PIX_BENEFICIARY,
    PIX_KEY,
    PIX_PAYLOAD,
    SUPPORT_MESSAGE,
    SUPPORT_TITLE,
    get_localized_support_message,
    get_localized_support_title,
    load_pix_qr_pixmap,
)
from brisasync.ui.icons import load_app_icon, load_header_logo_pixmap
from brisasync.ui.notifications import NotificationManager
from brisasync.ui.styles import apply_brisasync_theme, get_brisasync_stylesheet, is_dark_mode
from brisasync.ui.tray import BrisaTrayController
from brisasync.ui.vector_icons import (
    get_vector_icon,
    render_rotated_sync_icon,
    render_vector_pixmap,
)
from brisasync.ui.workers import (
    OAuthConnectWorker,
    RemoteFoldersWorker,
    ServiceCommandWorker,
    UnlockVaultWorker,
)

INTERVAL_CHOICES: tuple[tuple[str, int], ...] = (
    ("1 minuto (60s)", 60),
    ("5 minutos (300s — Padrão)", 300),
    ("15 minutos (900s)", 900),
    ("30 minutos (1800s)", 1800),
    ("60 minutos (3600s)", 3600),
)

TRAY_THEME_CHOICES: tuple[tuple[str, str], ...] = (
    ("Automático (adapta ao sistema)", "auto"),
    ("Claro (para barra escura)", "dark_panel"),
    ("Escuro (para barra clara)", "light_panel"),
)

THEME_PREFERENCE_CHOICES: tuple[tuple[str, str], ...] = (
    ("Sistema", "system"),
    ("Claro", "light"),
    ("Escuro", "dark"),
)


def _format_elided_email(email: str, max_chars: int = 22) -> str:
    """Abrevia o e-mail de forma legível preservando o domínio quando excede max_chars."""
    if not email or len(email) <= max_chars:
        return email
    if "@" in email:
        user, domain = email.split("@", 1)
        avail = max_chars - len(domain) - 2
        if avail >= 2:
            return f"{user[:avail]}…@{domain}"
        if len(domain) > 8:
            d_avail = max(4, max_chars - 5)
            return f"{user[:2]}…@{domain[:d_avail]}…"
    return email[: max_chars - 1] + "…"


def _format_relative_timestamp(iso_str: str | None) -> str:
    """Calcula descrição de tempo relativo curto (ex: 'há 1 min', 'há 30 min')."""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta_sec = max(0, int((now - dt).total_seconds()))
        if delta_sec < 60:
            return tr("time_just_now")
        elif delta_sec < 120:
            return tr("time_1_min_ago")
        elif delta_sec < 3600:
            return tr("time_mins_ago", count=delta_sec // 60)
        elif delta_sec < 86400:
            hours = delta_sec // 3600
            return tr("time_1_hour_ago") if hours == 1 else tr("time_hours_ago", count=hours)
        else:
            return dt.astimezone().strftime("%d/%m %H:%M")
    except Exception:
        return iso_str


def _format_status_display(status: str) -> tuple[str, Qt.GlobalColor]:
    """Converte status interno de execução para apresentação amigável e cor de alto contraste."""
    st = (status or "").upper()
    if st == "SUCCESS":
        return tr("activity_status_completed"), Qt.GlobalColor.darkGreen
    elif st == "RUNNING":
        return tr("activity_status_in_progress"), Qt.GlobalColor.darkBlue
    elif st == "STOPPED_BY_USER":
        return tr("activity_status_stopped"), Qt.GlobalColor.darkYellow
    elif st == "OFFLINE_BACKOFF":
        return tr("activity_status_offline"), Qt.GlobalColor.darkYellow
    elif st == "ATTENTION_REQUIRED":
        return tr("activity_status_attention_needed"), Qt.GlobalColor.darkYellow
    else:
        return f"✕ {status}", Qt.GlobalColor.darkRed


def _format_operation_display(operation: str) -> str:
    """Traduz tipo de operação do rclone/bisync para terminologia amigável."""
    op = (operation or "").lower()
    if op == "baseline_resync":
        return tr("op_baseline_resync")
    elif op in ("bisync", "incremental_bisync"):
        return tr("op_sync")
    elif op == "resync":
        return tr("op_resync")
    elif op in ("baseline_precheck", "precheck_validation"):
        return tr("op_precheck")
    return operation


def _format_folders_display(path1: str, path2: str) -> str:
    """Apresenta os nomes limpos das pastas sincronizadas mantendo paths técnicos nos tooltips."""
    p1 = Path(path1).name if path1 else "local"
    if not p1:
        p1 = path1
    if ":" in path2:
        p2 = path2.split(":")[-1]
    else:
        p2 = Path(path2).name if path2 else "Drive"
    if not p2:
        p2 = "Drive"
    return f"{p1} ⮂ {p2}"


def _format_summary_display(raw_summary: str | None, status: str) -> str:
    """Traduz resumos conhecidos para a língua ativa preservando dados livres e logs técnicos."""
    text = (raw_summary or "").strip()
    if not text:
        return tr("summary_completed_no_conflicts") if status == "SUCCESS" else tr("summary_attention_needed")

    if text in (
        "Baseline inicial estabelecida com sucesso.",
        "Initial baseline established successfully.",
    ):
        return tr("summary_baseline_success")

    if (
        "Operação interrompida de forma controlada pelo usuário" in text
        or "Operation gracefully interrupted by user" in text
    ):
        return tr("summary_stopped_by_user")

    conflict_pattern = re.compile(
        r"^(?:Sincronização bidirecional concluída com sucesso\.|Bidirectional synchronization completed successfully\.)"
        r"(?:\s+(?:Conflitos preservados pelo backend|Conflicts preserved by backend)\s*\((?P<cnt>\d+)\):\s*(?P<files>.+?)\.?)?$",
        re.DOTALL,
    )
    m = conflict_pattern.match(text)
    if m:
        base = tr("summary_bidirectional_success")
        cnt = m.group("cnt")
        files = m.group("files")
        if cnt and files:
            return f"{base} {tr('summary_conflicts_preserved', count=cnt, files=files)}"
        return base

    if text in (
        "Concluído sem conflitos.",
        "Completed without conflicts.",
    ):
        return tr("summary_completed_no_conflicts")

    if text in (
        "Atenção necessária.",
        "Attention required.",
    ):
        return tr("summary_attention_needed")

    return text


def _wrap_in_responsive_container(content: QWidget, max_width: int = 920) -> QWidget:
    """Envolve o conteúdo em um container responsivo centralizado com largura máxima de leitura."""
    wrapper = QWidget()
    h_box = QHBoxLayout(wrapper)
    h_box.setContentsMargins(0, 0, 0, 0)
    h_box.setSpacing(0)
    h_box.addStretch(1)
    content.setMaximumWidth(max_width)
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    h_box.addWidget(content, stretch=10)
    h_box.addStretch(1)
    return wrapper


class BrisaDiagnosticsDialog(QDialog):
    """Diálogo secundário de Ajuda e Diagnóstico de Dependências do Sistema."""

    def __init__(self, main_window: BrisaMainWindow) -> None:
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle(f"Ajuda e Diagnóstico — {__app_name__}")
        self.setMinimumSize(680, 460)
        self.resize(750, 520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        self.diagnostics_summary_label = QLabel("Verificando dependências do sistema...", self)
        self.diagnostics_summary_label.setStyleSheet("font-weight: bold;")
        self.diagnostics_summary_label.setWordWrap(True)

        self.refresh_diag_button = QPushButton("&Atualizar Diagnóstico", self)
        self.refresh_diag_button.setAccessibleName("Atualizar diagnóstico das dependências")
        self.refresh_diag_button.clicked.connect(self.refresh)

        top_bar.addWidget(self.diagnostics_summary_label, stretch=1)
        top_bar.addWidget(self.refresh_diag_button)
        layout.addLayout(top_bar)

        self.diagnostics_table = QTableWidget(0, 3, self)
        self.diagnostics_table.setAccessibleName("Tabela de diagnóstico de dependências")
        self.diagnostics_table.setHorizontalHeaderLabels(
            ["Componente", "Estado", "Detalhes Verificados"]
        )
        self.diagnostics_table.verticalHeader().setVisible(False)
        self.diagnostics_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.diagnostics_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.diagnostics_table.setAlternatingRowColors(True)

        self.main_window.diagnostics_summary_label = self.diagnostics_summary_label
        self.main_window.diagnostics_table = self.diagnostics_table

        diag_header = self.diagnostics_table.horizontalHeader()
        diag_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        diag_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        diag_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.diagnostics_table, stretch=1)

        svc_frame = QFrame(self)
        svc_frame.setProperty("class", "brisaInnerCard")
        sf_layout = QVBoxLayout(svc_frame)
        sf_layout.setContentsMargins(12, 10, 12, 10)
        sf_layout.setSpacing(4)
        sf_title = QLabel("Status do Serviço em Segundo Plano (IPC da Sessão):", svc_frame)
        sf_title.setStyleSheet("font-weight: bold;")
        self.sync_status_label = QLabel(
            "Estado do Serviço: [AGUARDANDO] — Consultando serviço da sessão...",
            svc_frame,
        )
        self.sync_status_label.setWordWrap(True)
        self.sync_status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        sf_layout.addWidget(sf_title)
        sf_layout.addWidget(self.sync_status_label)
        layout.addWidget(svc_frame)

        help_box = QFrame(self)
        help_box.setProperty("class", "brisaInnerCard")
        hb_layout = QVBoxLayout(help_box)
        hb_layout.setContentsMargins(12, 10, 12, 10)
        hb_layout.setSpacing(4)
        hb_title = QLabel("Dicas de Resolução de Problemas:", help_box)
        hb_title.setStyleSheet("font-weight: bold;")
        hb_desc = QLabel(
            "• Cofre Indisponível: Certifique-se de que o serviço Secret Service (KDE Wallet ou GNOME Keyring) está ativo.\n"
            "• Falha de Conexão: O BrisaSync aplica espera progressiva automática (backoff exponencial) para não sobrecarregar a rede.\n"
            "• Conflitos: Quando um mesmo arquivo é modificado em ambos os lados, o BrisaSync preserva ambas as versões com sufixo '.conflict'.",
            help_box,
        )
        hb_desc.setWordWrap(True)
        hb_layout.addWidget(hb_title)
        hb_layout.addWidget(hb_desc)
        layout.addWidget(help_box)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch(1)
        close_btn = QPushButton("Fechar", self)
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        layout.addLayout(bottom_bar)

        self.refresh()

    def refresh(self) -> None:
        self.main_window.refresh_diagnostics()
        diag = collect_system_diagnostics()
        summary = (
            f"Diagnóstico do Sistema: {__app_name__} v{__version__} — "
            + ("Todas as dependências críticas estão operacionais." if diag.all_critical_ok else "Atenção necessária em dependências.")
        )
        self.diagnostics_summary_label.setText(summary)
        self.diagnostics_table.setRowCount(len(diag.items))

        for row, item in enumerate(diag.items):
            c_it = QTableWidgetItem(item.component)
            s_it = QTableWidgetItem(item.status_label)
            d_it = QTableWidgetItem(item.details)

            if item.status_code == "OK":
                s_it.setForeground(Qt.GlobalColor.darkGreen)
            elif item.status_code == "WARNING":
                s_it.setForeground(Qt.GlobalColor.darkYellow)
            else:
                s_it.setForeground(Qt.GlobalColor.darkRed)

            self.diagnostics_table.setItem(row, 0, c_it)
            self.diagnostics_table.setItem(row, 1, s_it)
            self.diagnostics_table.setItem(row, 2, d_it)

        if hasattr(self.main_window, "_last_snapshot") and self.main_window._last_snapshot:
            snap = self.main_window._last_snapshot
            self.sync_status_label.setText(
                f"Estado do Serviço: [{snap.state_label}] — {snap.detail_message} (PID: {snap.service_pid})"
            )


class BrisaAboutDialog(QDialog):
    """Diálogo Sobre o BrisaSync com declaração de independência, apoio voluntário e licenças."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("about_dialog_title"))
        self.setMinimumSize(540, 440)
        self.resize(620, 560)

        main_dialog_layout = QVBoxLayout(self)
        main_dialog_layout.setContentsMargins(16, 16, 16, 16)
        main_dialog_layout.setSpacing(12)

        # Área de rolagem para garantir leitura confortável em janelas pequenas
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content_widget = QWidget()
        layout = QVBoxLayout(content_widget)
        layout.setContentsMargins(4, 4, 12, 4)
        layout.setSpacing(14)

        # 1. Cabeçalho com logo e nome da aplicação
        top_row = QHBoxLayout()
        top_row.setSpacing(14)
        about_icon = QLabel(content_widget)
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        logo = load_header_logo_pixmap(logical_size=52, device_pixel_ratio=dpr)
        if not logo.isNull():
            about_icon.setPixmap(logo)
        about_icon.setFixedSize(52, 52)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        ab_title = QLabel(f"{__app_name__} v{__version__}", content_widget)
        ab_tfont = QFont(self.font())
        ab_tfont.setPointSize(max(ab_tfont.pointSize() + 3, 13))
        ab_tfont.setBold(True)
        ab_title.setFont(ab_tfont)

        ab_sub = QLabel(
            tr("about_headline"),
            content_widget,
        )
        ab_sub.setWordWrap(True)
        title_box.addWidget(ab_title)
        title_box.addWidget(ab_sub)

        top_row.addWidget(about_icon)
        top_row.addLayout(title_box, stretch=1)
        layout.addLayout(top_row)

        # 2. Seção Apoie o BrisaSync (Pix)
        self.support_card = QFrame(content_widget)
        self.support_card.setProperty("class", "brisaInnerCard")
        supp_layout = QVBoxLayout(self.support_card)
        supp_layout.setSpacing(10)

        supp_title = QLabel(get_localized_support_title(), self.support_card)
        supp_title.setStyleSheet("font-weight: bold; color: #9189FF; font-size: 13px;")
        supp_layout.addWidget(supp_title)

        supp_body = QLabel(get_localized_support_message(), self.support_card)
        supp_body.setWordWrap(True)
        supp_layout.addWidget(supp_body)

        # Painel horizontal do Pix: QR Code à esquerda e dados/botões à direita
        pix_content_layout = QHBoxLayout()
        pix_content_layout.setSpacing(16)
        pix_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Coluna do QR Code
        qr_container = QVBoxLayout()
        qr_container.setSpacing(6)
        qr_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qr_frame = QFrame(self.support_card)
        self.qr_frame.setObjectName("pixQrFrame")
        self.qr_frame.setStyleSheet(
            "#pixQrFrame { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 6px; }"
        )
        qr_frame_layout = QVBoxLayout(self.qr_frame)
        qr_frame_layout.setContentsMargins(6, 6, 6, 6)
        qr_frame_layout.setSpacing(0)
        qr_frame_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.qr_label = QLabel(self.qr_frame)
        self.qr_label.setFixedSize(140, 140)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setStyleSheet("background-color: transparent;")
        pixmap = load_pix_qr_pixmap(140)
        if not pixmap.isNull():
            self.qr_label.setPixmap(pixmap)
        qr_frame_layout.addWidget(self.qr_label)
        qr_container.addWidget(self.qr_frame)

        qr_hint = QLabel(tr("about_qr_hint"), self.support_card)
        qr_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_hint.setStyleSheet("color: #94A3B8; font-size: 11px;")
        qr_container.addWidget(qr_hint)

        pix_content_layout.addLayout(qr_container)

        # Coluna de Detalhes e Ações
        details_layout = QVBoxLayout()
        details_layout.setSpacing(8)
        details_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.beneficiary_label = QLabel(f"<b>{tr('about_beneficiary_label')}</b> {PIX_BENEFICIARY}", self.support_card)
        self.beneficiary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details_layout.addWidget(self.beneficiary_label)

        key_label = QLabel(f"<b>{tr('about_pix_key_label')}</b>", self.support_card)
        details_layout.addWidget(key_label)

        self.pix_key_field = QLineEdit(PIX_KEY, self.support_card)
        self.pix_key_field.setReadOnly(True)
        self.pix_key_field.setCursorPosition(0)
        details_layout.addWidget(self.pix_key_field)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.copy_key_btn = QPushButton(tr("about_btn_copy_key"), self.support_card)
        self.copy_key_btn.setToolTip(tr("about_copy_hint_key"))
        self.copy_key_btn.clicked.connect(self._copy_pix_key)
        btn_row.addWidget(self.copy_key_btn)

        self.copy_payload_btn = QPushButton(tr("about_btn_copy_payload"), self.support_card)
        self.copy_payload_btn.setToolTip(tr("about_copy_hint_payload"))
        self.copy_payload_btn.clicked.connect(self._copy_pix_payload)
        btn_row.addWidget(self.copy_payload_btn)

        details_layout.addLayout(btn_row)

        self.feedback_label = QLabel("", self.support_card)
        self.feedback_label.setStyleSheet("color: #10B981; font-weight: bold; font-size: 11px;")
        details_layout.addWidget(self.feedback_label)

        pix_content_layout.addLayout(details_layout, stretch=1)
        supp_layout.addLayout(pix_content_layout)
        layout.addWidget(self.support_card)

        # 3. Cartão de Declaração de Independência
        disclaimer_card = QFrame(content_widget)
        disclaimer_card.setProperty("class", "brisaInnerCard")
        disc_layout = QVBoxLayout(disclaimer_card)
        disc_layout.setSpacing(6)

        disc_title = QLabel(tr("about_independence_title"), disclaimer_card)
        disc_title.setStyleSheet("font-weight: bold; color: #9189FF;")
        disc_body = QLabel(
            tr("about_independence_text"),
            disclaimer_card,
        )
        disc_body.setWordWrap(True)
        disc_layout.addWidget(disc_title)
        disc_layout.addWidget(disc_body)
        layout.addWidget(disclaimer_card)

        # 4. Cartão de Licenciamento
        license_card = QFrame(content_widget)
        license_card.setProperty("class", "brisaInnerCard")
        lic_layout = QVBoxLayout(license_card)
        lic_layout.setSpacing(6)

        lic_title = QLabel(tr("about_license_title"), license_card)
        lic_title.setStyleSheet("font-weight: bold;")
        lic_body = QLabel(
            "• Licença: GNU General Public License v3.0 ou posterior (GPL-3.0-or-later).\n"
            "• rclone (Motor de sincronização bidirecional): Licença MIT\n"
            "• Qt 6 / PySide6 (Framework de interface gráfica): Licença LGPLv3 / GPLv3\n"
            "• Python: Python Software Foundation License (PSF-2.0)\n"
            "• libsecret / secret-tool & libnotify / notify-send: Licença LGPLv2.1+",
            license_card,
        )
        lic_body.setWordWrap(True)
        lic_layout.addWidget(lic_title)
        lic_layout.addWidget(lic_body)
        layout.addWidget(license_card)

        layout.addStretch(1)

        scroll_area.setWidget(content_widget)
        main_dialog_layout.addWidget(scroll_area, stretch=1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch(1)
        close_btn = QPushButton(tr("about_btn_close"), self)
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        main_dialog_layout.addLayout(bottom_bar)

    def _copy_pix_key(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(PIX_KEY)
        self.copy_key_btn.setText(tr("about_copy_key_success"))
        self.feedback_label.setText(tr("about_copy_hint_key"))
        QTimer.singleShot(2500, self._reset_copy_buttons)

    def _copy_pix_payload(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(PIX_PAYLOAD)
        self.copy_payload_btn.setText(tr("about_copy_payload_success"))
        self.feedback_label.setText(tr("about_copy_hint_payload"))
        QTimer.singleShot(2500, self._reset_copy_buttons)

    def _reset_copy_buttons(self) -> None:
        self.copy_key_btn.setText(tr("about_btn_copy_key"))
        self.copy_payload_btn.setText(tr("about_btn_copy_payload"))
        self.feedback_label.setText("")


class SyncRunDetailsDialog(QDialog):
    """Diálogo com detalhes completos e auditáveis de uma execução registrada no SQLite."""

    def __init__(self, run: SyncRunRecord, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Detalhes da Execução #{run.id} — {__app_name__}")
        self.setMinimumSize(560, 420)
        self.resize(640, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title_label = QLabel(f"Execução #{run.id} — {_format_operation_display(run.operation)}", self)
        title_font = QFont(self.font())
        title_font.setPointSize(max(title_font.pointSize() + 2, 12))
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        details_frame = QFrame(self)
        details_frame.setProperty("class", "brisaInnerCard")
        grid = QGridLayout(details_frame)
        grid.setContentsMargins(14, 12, 14, 12)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)

        try:
            start_dt = datetime.fromisoformat(run.started_at.replace("Z", "+00:00")).astimezone()
            start_str = start_dt.strftime("%d/%m/%Y às %H:%M:%S")
        except Exception:
            start_str = run.started_at

        try:
            finish_dt = datetime.fromisoformat(run.finished_at.replace("Z", "+00:00")).astimezone()
            finish_str = finish_dt.strftime("%d/%m/%Y às %H:%M:%S")
            duration_sec = (finish_dt - start_dt).total_seconds()
            dur_str = f"{duration_sec:.1f}s"
        except Exception:
            finish_str = run.finished_at
            dur_str = "—"

        st_label, st_color = _format_status_display(run.status)

        grid.addWidget(QLabel("Início:", details_frame), 0, 0)
        grid.addWidget(QLabel(start_str, details_frame), 0, 1)
        grid.addWidget(QLabel("Término:", details_frame), 1, 0)
        grid.addWidget(QLabel(f"{finish_str} (Duração: {dur_str})", details_frame), 1, 1)

        status_val_lbl = QLabel(f"{st_label} (Código de saída: {run.exit_code})", details_frame)
        status_val_lbl.setStyleSheet("font-weight: bold;")
        grid.addWidget(QLabel("Estado:", details_frame), 2, 0)
        grid.addWidget(status_val_lbl, 2, 1)

        grid.addWidget(QLabel("Pasta Local:", details_frame), 3, 0)
        local_lbl = QLabel(run.path1, details_frame)
        local_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(local_lbl, 3, 1)

        grid.addWidget(QLabel("Destino Remoto:", details_frame), 4, 0)
        rem_lbl = QLabel(run.path2, details_frame)
        rem_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(rem_lbl, 4, 1)

        layout.addWidget(details_frame)

        summary_title = QLabel("Resumo e Saída da Execução:", self)
        summary_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(summary_title)

        summary_edit = QTextEdit(self)
        summary_edit.setReadOnly(True)
        summary_edit.setPlainText(run.summary or "Nenhuma mensagem adicional registrada.")
        font_mono = QFont("monospace")
        font_mono.setStyleHint(QFont.StyleHint.Monospace)
        summary_edit.setFont(font_mono)
        layout.addWidget(summary_edit, stretch=1)

        bottom_bar = QHBoxLayout()
        bottom_bar.addStretch(1)
        close_btn = QPushButton("Fechar", self)
        close_btn.clicked.connect(self.accept)
        bottom_bar.addWidget(close_btn)
        layout.addLayout(bottom_bar)


class BrisaSidebarNavItem(QAbstractButton):
    """Item de navegação atômico da barra lateral com desenho vetorial unificado."""

    def __init__(
        self,
        icon_name: str,
        text: str,
        badge_count: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self.item_text = text
        self.setText(text)
        self.badge_count = badge_count
        self.is_active = False
        self.setFixedHeight(42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setAccessibleName(f"Navegar para {text}")

    def setText(self, text: str) -> None:
        self.item_text = text
        super().setText(text)
        self.setAccessibleName(f"Navegar para {text}")
        self.update()

    def setActive(self, active: bool) -> None:
        if self.is_active != active:
            self.is_active = active
            self.update()

    def setBadgeCount(self, count: int | None) -> None:
        if self.badge_count != count:
            self.badge_count = count
            self.update()

    def sizeHint(self) -> QSize:
        return QSize(200, 42)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, 42)

    def enterEvent(self, event: QEnterEvent) -> None:
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event: QEvent) -> None:
        super().leaveEvent(event)
        self.update()

    def focusInEvent(self, event: QFocusEvent) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event: QFocusEvent) -> None:
        super().focusOutEvent(event)
        self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()

        is_hovered = self.underMouse()
        is_focused = self.hasFocus()
        is_dark = is_dark_mode()

        lavender_accent = QColor("#9189FF") if is_dark else QColor("#6355DE")
        lavender_active_bg = QColor(145, 137, 255, 41) if is_dark else QColor(99, 85, 222, 35)
        hover_bg = QColor(145, 137, 255, 20) if is_dark else QColor(99, 85, 222, 20)

        # 1. Fundo (seleção lavanda suave ou hover sutil)
        if self.is_active:
            painter.setBrush(lavender_active_bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)

            # Indicador lateral de 3px
            painter.setBrush(lavender_accent)
            painter.drawRoundedRect(QRectF(2, 10, 3, 22), 1.5, 1.5)
        elif is_hovered:
            painter.setBrush(hover_bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)

        # 2. Foco por teclado (contorno visível envolvendo o item inteiro)
        if is_focused:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            focus_pen = QPen(lavender_accent, 2.0)
            painter.setPen(focus_pen)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 10, 10)

        # 3. Ícone vetorial alinhado (18x18 a 14px da margem esquerda)
        if is_dark:
            icon_color = "#9189FF" if self.is_active else ("#F0F4F8" if is_hovered else "#8B949E")
        else:
            icon_color = "#6355DE" if self.is_active else ("#0F172A" if is_hovered else "#64748B")
        pix = render_vector_pixmap(self.icon_name, 18, icon_color)
        icon_y = (rect.height() - 18) // 2
        painter.drawPixmap(14, icon_y, pix)

        # 4. Texto do item
        if is_dark:
            text_color = QColor("#FFFFFF") if self.is_active else (QColor("#F0F4F8") if is_hovered else QColor("#8B949E"))
        else:
            text_color = QColor("#0F172A") if self.is_active else (QColor("#0F172A") if is_hovered else QColor("#475569"))
        painter.setPen(text_color)
        f = self.font()
        f.setPixelSize(13)
        f.setWeight(QFont.Weight.DemiBold if self.is_active else QFont.Weight.Medium)
        painter.setFont(f)

        text_x = 42
        badge_reserved = 38 if (self.badge_count is not None and self.badge_count > 0) else 14
        text_w = max(10, rect.width() - text_x - badge_reserved)
        painter.drawText(
            QRect(text_x, 0, text_w, rect.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.item_text,
        )

        # 5. Badge compacto na mesma linha
        if self.badge_count is not None and self.badge_count > 0:
            badge_str = str(self.badge_count)
            bh = 18
            bw = max(20, painter.fontMetrics().horizontalAdvance(badge_str) + 12)
            bx = rect.width() - 14 - bw
            by = (rect.height() - bh) // 2

            badge_bg = QColor("#273140") if is_dark else QColor("#E2E8F0")
            badge_fg = QColor("#F0F4F8") if is_dark else QColor("#334155")
            painter.setBrush(badge_bg)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(bx, by, bw, bh), 9, 9)

            bfont = QFont(self.font())
            bfont.setPixelSize(10)
            bfont.setWeight(QFont.Weight.Bold)
            painter.setFont(bfont)
            painter.setPen(badge_fg)
            painter.drawText(QRect(bx, by, bw, bh), Qt.AlignmentFlag.AlignCenter, badge_str)

        painter.end()


class BrisaExitDialog(QDialog):
    """Diálogo unificado de encerramento do BrisaSync."""

    def __init__(self, main_window: BrisaMainWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle(tr("exit_dialog_title"))
        self.setMinimumWidth(500)
        self.setMinimumHeight(320)
        self.resize(540, 360)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.CustomizeWindowHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        # Cabeçalho
        title_lbl = QLabel(tr("exit_dialog_title"), self)
        title_lbl.setProperty("class", "dialogTitle")
        subtitle_lbl = QLabel(tr("exit_question"), self)
        subtitle_lbl.setProperty("class", "dialogSubtitle")
        layout.addWidget(title_lbl)
        layout.addWidget(subtitle_lbl)

        # Quadro de opções
        choices_frame = QFrame(self)
        choices_frame.setProperty("class", "brisaCard")
        c_lay = QVBoxLayout(choices_frame)
        c_lay.setContentsMargins(14, 12, 14, 12)
        c_lay.setSpacing(12)

        # Opção 1: Manter sincronização
        row1 = QHBoxLayout()
        row1.setSpacing(14)
        self.btn_keep = QPushButton(tr("exit_option_keep_service"), choices_frame)
        self.btn_keep.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_keep.setObjectName("exitBtnKeep")
        lbl_keep = QLabel(
            tr("exit_option_keep_service_desc"),
            choices_frame,
        )
        lbl_keep.setProperty("class", "dialogItemHint")
        lbl_keep.setWordWrap(True)
        lbl_keep.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row1.addWidget(self.btn_keep)
        row1.addWidget(lbl_keep, stretch=1)
        c_lay.addLayout(row1)

        sep = QFrame(choices_frame)
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)
        c_lay.addWidget(sep)

        # Opção 2: Encerrar tudo
        row2 = QHBoxLayout()
        row2.setSpacing(14)
        self.btn_shutdown = QPushButton(tr("exit_option_shutdown"), choices_frame)
        self.btn_shutdown.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_shutdown.setObjectName("exitBtnShutdown")
        lbl_shutdown = QLabel(
            tr("exit_option_shutdown_desc"),
            choices_frame,
        )
        lbl_shutdown.setProperty("class", "dialogItemHint")
        lbl_shutdown.setWordWrap(True)
        lbl_shutdown.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row2.addWidget(self.btn_shutdown)
        row2.addWidget(lbl_shutdown, stretch=1)
        c_lay.addLayout(row2)

        # Ajusta a largura dos botões harmoniosamente ao texto com margem adequada
        fm_keep = self.btn_keep.fontMetrics()
        fm_shut = self.btn_shutdown.fontMetrics()
        btn_w = max(
            fm_keep.horizontalAdvance(self.btn_keep.text()),
            fm_shut.horizontalAdvance(self.btn_shutdown.text()),
        ) + 28
        self.btn_keep.setFixedWidth(btn_w)
        self.btn_shutdown.setFixedWidth(btn_w)

        layout.addWidget(choices_frame)

        # Status de encerramento em andamento / alerta
        self.status_msg = QLabel("", self)
        self.status_msg.setStyleSheet("font-size: 11px; color: #F59E0B;")
        self.status_msg.setWordWrap(True)
        self.status_msg.setVisible(False)
        layout.addWidget(self.status_msg)

        # Botão inferior: Cancelar
        bot_row = QHBoxLayout()
        bot_row.addStretch(1)
        self.btn_cancel = QPushButton(tr("exit_btn_cancel"), self)
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setObjectName("exitBtnCancel")
        self.btn_cancel.clicked.connect(self.reject)
        bot_row.addWidget(self.btn_cancel)
        layout.addLayout(bot_row)

        self.btn_keep.clicked.connect(self._on_keep_clicked)
        self.btn_shutdown.clicked.connect(self._on_shutdown_clicked)

        self._shutdown_poll_timer: QTimer | None = None
        self._shutdown_polls = 0

    def _on_keep_clicked(self) -> None:
        self.accept()
        self.main_window.quit_graphical_component_keep_service()

    def _on_shutdown_clicked(self) -> None:
        snapshot = self.main_window._last_snapshot
        is_active = bool(snapshot and snapshot.is_cycle_active)

        if is_active:
            self.btn_keep.setEnabled(False)
            self.btn_shutdown.setEnabled(False)
            self.btn_cancel.setEnabled(False)
            self.status_msg.setText("Interrompendo sincronização ativa de forma controlada...")
            self.status_msg.setStyleSheet("font-size: 11px; color: #F59E0B;")
            self.status_msg.setVisible(True)

            try:
                self.main_window.ipc_client.execute_command("stop_current")
            except Exception:
                pass

            self._shutdown_polls = 0
            self._shutdown_poll_timer = QTimer(self)
            self._shutdown_poll_timer.setInterval(250)
            self._shutdown_poll_timer.timeout.connect(self._check_stop_and_finalize)
            self._shutdown_poll_timer.start()
        else:
            self._finalize_full_shutdown()

    def _check_stop_and_finalize(self) -> None:
        self._shutdown_polls += 1
        is_still_active = False
        try:
            st = self.main_window.ipc_client.get_status()
            is_still_active = bool(st.is_cycle_active)
        except Exception:
            is_still_active = False

        if not is_still_active or self._shutdown_polls >= 16:  # 4 segundos
            if self._shutdown_poll_timer:
                self._shutdown_poll_timer.stop()
                self._shutdown_poll_timer = None

            if is_still_active:
                self.status_msg.setText(
                    "A sincronização em andamento demorou mais que o esperado para parar. "
                    "A aplicação permanece aberta para que você possa verificar o estado com segurança."
                )
                self.status_msg.setStyleSheet("font-size: 11px; color: #EF4444;")
                self.btn_keep.setEnabled(True)
                self.btn_shutdown.setEnabled(True)
                self.btn_cancel.setEnabled(True)
            else:
                self._finalize_full_shutdown()

    def _finalize_full_shutdown(self) -> None:
        try:
            self.main_window.ipc_client.execute_command("shutdown_service")
        except Exception:
            pass
        self.accept()
        self.main_window.quit_graphical_component_keep_service()


class BrisaMainWindow(QMainWindow):
    """Janela principal do BrisaSync v0.1.6 com barra lateral e painel responsivo em cartões."""

    _window_registry: list[BrisaMainWindow] = []

    def __init__(
        self,
        *,
        database: BrisaDatabase | None = None,
        credential_store: CredentialStore | None = None,
        bridge: RcloneEncryptedBridge | None = None,
        ipc_client: ServiceIPCClient | None = None,
        autostart_manager: BrisaAutostartCoordinator | SystemdUserAutostartManager | None = None,
        enable_tray: bool = True,
        force_tray_available: bool | None = None,
        allow_notify_send: bool = True,
    ) -> None:
        super().__init__()
        self.database = database or BrisaDatabase()
        saved_lang = self.database.get_language_preference(default="pt_BR")
        set_current_language(saved_lang)
        self.credential_store = credential_store or CredentialStore()
        self.bridge = bridge or RcloneEncryptedBridge(credential_store=self.credential_store)
        self.ipc_client = ipc_client or ServiceIPCClient()
        self.autostart_manager = autostart_manager or BrisaAutostartCoordinator(
            db_path=self.database.db_path
        )

        self.tray_controller = BrisaTrayController(
            self.database,
            credential_store=self.credential_store,
            parent_widget=self,
            enable_tray=enable_tray,
            force_tray_available=force_tray_available,
        )
        self.notification_manager = NotificationManager(
            self.database,
            tray_sender=(
                self.tray_controller.send_tray_message
                if self.tray_controller.is_available
                else None
            ),
            allow_notify_send=allow_notify_send,
        )
        self._connect_tray_signals()

        self._oauth_worker: OAuthConnectWorker | None = None
        self._folders_worker: RemoteFoldersWorker | None = None
        self._cmd_worker: ServiceCommandWorker | None = None
        self._unlock_worker: UnlockVaultWorker | None = None
        self._cached_account_state: tuple[str, OAuthCredentials | None, str] | None = None
        self._retired_workers: list[Any] = []
        self._remote_entries: list[RemoteDirectoryEntry] = []
        self._last_snapshot: ServiceStatusSnapshot | None = None
        self._last_history_top_id: int | None = None
        self._minimize_to_tray_on_close: bool = False
        self._explicit_ui_quit_requested: bool = False
        self.last_opened_local_folder: Path | None = None
        self._exit_dialog: BrisaExitDialog | None = None
        self._is_narrow_mode: bool = False
        self._is_sub_narrow_mode: bool = False
        self._force_layout_refresh: bool = False
        self._pending_remote_rejection: dict[str, Any] | None = None
        self._pending_local_rejection: dict[str, Any] | None = None

        try:
            app = QApplication.instance()
            if app is not None and hasattr(app, "styleHints"):
                app.styleHints().colorSchemeChanged.connect(self._on_system_color_scheme_changed)
        except Exception:
            pass

        self._init_ui()

    def apply_theme(self) -> None:
        """Aplica o tema do BrisaSync com base na preferência salva e atualiza controles dinâmicos."""
        pref = self.database.get_theme_preference(default="system")
        apply_brisasync_theme(QApplication.instance(), self, theme_preference=pref)
        self._update_theme_dependent_icons()
        if hasattr(self, "sidebar_items"):
            for it in self.sidebar_items.values():
                it.update()
        if hasattr(self, "nav_buttons"):
            for btn in self.nav_buttons:
                btn.update()
        if hasattr(self, "header_account_badge"):
            self._update_home_view()
        self.update()

    def _update_theme_dependent_icons(self) -> None:
        """Atualiza ícones que dependem de contraste com botões e cartões nos temas claro e escuro."""
        is_dark = is_dark_mode()
        btn_icon_color = "#F0F4F8" if is_dark else "#475569"
        sec_icon_color = "#8B949E" if is_dark else "#64748B"

        if hasattr(self, "overview_verify_again_btn"):
            self.overview_verify_again_btn.setIcon(get_vector_icon("sync", 14, btn_icon_color))
        if hasattr(self, "overview_open_folder_btn"):
            self.overview_open_folder_btn.setIcon(get_vector_icon("open_folder", 16, btn_icon_color))
        if hasattr(self, "folders_page_open_btn"):
            self.folders_page_open_btn.setIcon(get_vector_icon("open_folder", 14, btn_icon_color))
        if hasattr(self, "folders_page_sync_btn"):
            self.folders_page_sync_btn.setIcon(get_vector_icon("sync", 14, btn_icon_color))
        if hasattr(self, "folders_remove_pair_btn"):
            self.folders_remove_pair_btn.setIcon(get_vector_icon("clear", 14, btn_icon_color))
        if hasattr(self, "folders_connect_account_btn"):
            self.folders_connect_account_btn.setIcon(get_vector_icon("link", 14, btn_icon_color))
        if hasattr(self, "refresh_history_button"):
            self.refresh_history_button.setIcon(get_vector_icon("sync", 14, btn_icon_color))
        if hasattr(self, "sidebar_diag_btn"):
            self.sidebar_diag_btn.setIcon(get_vector_icon("info", 14, sec_icon_color))
        if hasattr(self, "sidebar_about_btn"):
            self.sidebar_about_btn.setIcon(get_vector_icon("info", 14, sec_icon_color))

    def _on_system_color_scheme_changed(self) -> None:
        # Se a preferência salva for manual ("light" ou "dark"), mantém estável e ignora alterações do desktop
        pref = self.database.get_theme_preference(default="system")
        if pref == "system":
            self.apply_theme()

    def _init_ui(self) -> None:
        self.setWindowTitle(f"{__app_name__} v{__version__}")
        self.setWindowIcon(load_app_icon())
        self.setMinimumSize(780, 520)
        self.resize(1100, 760)
        self.apply_theme()

        central = QWidget(self)
        self.setCentralWidget(central)

        main_h_layout = QHBoxLayout(central)
        main_h_layout.setContentsMargins(0, 0, 0, 0)
        main_h_layout.setSpacing(0)

        # 1. Barra Lateral (~230px)
        main_h_layout.addWidget(self._build_sidebar())

        # 2. Área de Conteúdo Principal
        main_content_widget = QWidget(central)
        content_v_layout = QVBoxLayout(main_content_widget)
        content_v_layout.setContentsMargins(0, 0, 0, 0)
        content_v_layout.setSpacing(0)

        # Cabeçalho Superior da Área de Conteúdo
        content_v_layout.addWidget(self._build_header_section())

        # Diálogo secundário de diagnóstico e dependências (acessível via Opções ou Rodapé)
        self.diagnostics_dialog = BrisaDiagnosticsDialog(self)
        self.diagnostics_table = self.diagnostics_dialog.diagnostics_table
        self.diagnostics_summary_label = self.diagnostics_dialog.diagnostics_summary_label
        self.sync_status_label = self.diagnostics_dialog.sync_status_label
        self.refresh_diag_button = self.diagnostics_dialog.refresh_diag_button

        # Navegação em abas (barra nativa oculta, controlada pela barra lateral)
        content_v_layout.addWidget(self._build_tabs_section(), stretch=1)
        main_h_layout.addWidget(main_content_widget, stretch=1)

        self._load_persisted_state()
        self.refresh_diagnostics()
        self.refresh_history_table()
        self._update_sync_target_preview()
        self.refresh_service_status_from_ipc()
        self._update_home_view()
        self._apply_responsive_layout(self.width())

        self._status_timer = QTimer(self)
        self._status_timer.setInterval(1200)
        self._status_timer.timeout.connect(self.refresh_service_status_from_ipc)
        if self.isVisible():
            self._status_timer.start(1200)

        self._hero_sync_angle: float = 0.0
        self._hero_anim_timer = QTimer(self)
        self._hero_anim_timer.setInterval(40)
        self._hero_anim_timer.timeout.connect(self._on_hero_anim_tick)

        if hasattr(self.autostart_manager, "sync_state"):
            try:
                self.autostart_manager.sync_state()
            except Exception:
                pass

        BrisaMainWindow._window_registry.append(self)

    def _connect_tray_signals(self) -> None:
        self.tray_controller.open_panel_requested.connect(self.restore_and_focus_window)
        self.tray_controller.open_local_folder_requested.connect(
            self.open_configured_local_folder
        )
        self.tray_controller.sync_now_requested.connect(self._on_sync_now_clicked)
        self.tray_controller.pause_or_resume_requested.connect(
            self._on_tray_pause_or_resume_clicked
        )
        self.tray_controller.quit_requested.connect(self.open_exit_dialog)
        self.tray_controller.quit_ui_keep_service_requested.connect(
            self.quit_graphical_component_keep_service
        )
        self.tray_controller.shutdown_service_requested.connect(
            self._on_shutdown_service_clicked
        )

    def set_minimize_to_tray_on_close(self, enabled: bool) -> None:
        self._minimize_to_tray_on_close = bool(
            enabled and self.tray_controller.is_available
        )
        self._update_lifecycle_notice_text()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if hasattr(self, "_status_timer") and not self._status_timer.isActive():
            self._status_timer.start(1200)
        snap = getattr(self, "_last_snapshot", None)
        if snap is not None and (
            snap.is_cycle_active or snap.state in (STATE_SYNCING, STATE_VERIFYING)
        ):
            self._start_hero_sync_animation()
        else:
            self._stop_hero_sync_animation()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        if hasattr(self, "_status_timer") and self._status_timer.isActive():
            self._status_timer.stop()
        if hasattr(self, "_hero_anim_timer") and self._hero_anim_timer.isActive():
            self._hero_anim_timer.stop()

    def restore_and_focus_window(self) -> None:
        if hasattr(self, "_status_timer") and not self._status_timer.isActive():
            self._status_timer.start(1200)
        self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.refresh_service_status_from_ipc()

    def open_configured_local_folder(self) -> bool:
        local_cfg = self.database.get_local_sync_folder()
        raw_path = (
            local_cfg.folder_path
            if local_cfg
            else self.folder_input.text().strip()
        )
        if not raw_path:
            self.folder_feedback_label.setText(
                "Status da pasta: [ATENÇÃO] Configure uma pasta local antes de abri-la."
            )
            return False
        p = Path(raw_path).expanduser().resolve()
        if not p.is_dir():
            self.folder_feedback_label.setText(
                f"Status da pasta: [ERRO] Diretório inexistente: {p}"
            )
            return False
        self.last_opened_local_folder = p
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
        return True

    def quit_graphical_component_keep_service(self) -> None:
        self._explicit_ui_quit_requested = True
        self._status_timer.stop()
        self.tray_controller.hide_and_cleanup()
        self.close()
        app = QApplication.instance()
        if app is not None:
            app.quit()

    # =========================================================================
    # BARRA LATERAL E CABEÇALHO
    # =========================================================================

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 16)
        layout.setSpacing(10)

        # 1. Identidade BrisaSync
        brand_row = QHBoxLayout()
        brand_row.setSpacing(10)
        brand_row.setContentsMargins(4, 0, 4, 0)

        self.header_icon_label = QLabel(sidebar)
        self.header_icon_label.setAccessibleName("Ícone do aplicativo BrisaSync")
        dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        logo_pixmap = load_header_logo_pixmap(logical_size=32, device_pixel_ratio=dpr)
        if not logo_pixmap.isNull():
            self.header_icon_label.setPixmap(logo_pixmap)
        self.header_icon_label.setFixedSize(32, 32)
        brand_row.addWidget(self.header_icon_label)

        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        brand_title = QLabel(f"{__app_name__}", sidebar)
        brand_title.setObjectName("sidebarBrandTitle")
        self.sidebar_brand_sub = QLabel(tr("sidebar_brand_sub"), sidebar)
        self.sidebar_brand_sub.setObjectName("sidebarBrandSubtitle")
        brand_text.addWidget(brand_title)
        brand_text.addWidget(self.sidebar_brand_sub)
        brand_row.addLayout(brand_text)
        brand_row.addStretch(1)
        layout.addLayout(brand_row)

        layout.addSpacing(14)
        nav_lbl = QLabel(tr("sidebar_section_nav"), sidebar)
        nav_lbl.setObjectName("sidebarSectionLabel")
        layout.addWidget(nav_lbl)
        self.sidebar_nav_lbl = nav_lbl

        # 2. Itens de Navegação
        self.nav_buttons: list[BrisaSidebarNavItem] = []
        nav_items = [
            (tr("nav_overview"), "dashboard", 0),
            (tr("nav_folders"), "folder", 1),
            (tr("nav_activity"), "activity", 2),
            (tr("nav_settings"), "settings", 3),
        ]
        self.sidebar_folders_badge = QLabel("1", sidebar)
        self.sidebar_folders_badge.setVisible(False)
        for label, icon_name, idx in nav_items:
            nav_item = BrisaSidebarNavItem(icon_name, label, parent=sidebar)
            if idx == 0:
                nav_item.setActive(True)
            if idx == 1:
                self.sidebar_folders_item = nav_item

            nav_item.clicked.connect(lambda checked=False, i=idx: self.set_current_page(i))
            layout.addWidget(nav_item)
            self.nav_buttons.append(nav_item)

        layout.addStretch(1)

        # 3. Mini cards informativos no rodapé da barra lateral
        rclone_card = QFrame(sidebar)
        rclone_card.setProperty("class", "sidebarFooterCard")
        rc_lay = QVBoxLayout(rclone_card)
        rc_lay.setContentsMargins(10, 8, 10, 8)
        rc_lay.setSpacing(2)
        rc_t = QLabel(tr("sidebar_rclone_connected"), rclone_card)
        rc_t.setProperty("class", "footerCardTitle")
        self.sidebar_rclone_title = rc_t
        rc_v = QLabel("v1.75.2", rclone_card)
        rc_v.setProperty("class", "footerCardValue")
        rc_lay.addWidget(rc_t)
        rc_lay.addWidget(rc_v)
        layout.addWidget(rclone_card)

        tray_card = QFrame(sidebar)
        tray_card.setProperty("class", "sidebarFooterCard")
        tr_lay = QVBoxLayout(tray_card)
        tr_lay.setContentsMargins(10, 8, 10, 8)
        tr_lay.setSpacing(2)
        tr_t = QLabel(tr("sidebar_tray_sync"), tray_card)
        tr_t.setProperty("class", "footerCardTitle")
        self.sidebar_tray_title = tr_t
        tr_v = QLabel(tr("sidebar_tray_desc"), tray_card)
        tr_v.setWordWrap(True)
        tr_v.setProperty("class", "footerCardValue")
        self.sidebar_tray_desc = tr_v
        tr_lay.addWidget(tr_t)
        tr_lay.addWidget(tr_v)
        layout.addWidget(tray_card)

        # 4. Links secundários
        footer_links = QHBoxLayout()
        footer_links.setSpacing(6)
        self.sidebar_diag_btn = QPushButton(tr("nav_help"), sidebar)
        self.sidebar_diag_btn.setFlat(True)
        self.sidebar_diag_btn.setIcon(get_vector_icon("info", 14, "#8B949E"))
        self.sidebar_diag_btn.setStyleSheet("font-size: 11px; color: #8B949E; text-align: left;")
        self.sidebar_diag_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_diag_btn.clicked.connect(self._open_diagnostics_dialog)

        self.sidebar_about_btn = QPushButton(tr("nav_about"), sidebar)
        self.sidebar_about_btn.setFlat(True)
        self.sidebar_about_btn.setIcon(get_vector_icon("info", 14, "#8B949E"))
        self.sidebar_about_btn.setStyleSheet("font-size: 11px; color: #8B949E; text-align: left;")
        self.sidebar_about_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.sidebar_about_btn.clicked.connect(self._open_about_dialog)

        footer_links.addWidget(self.sidebar_diag_btn)
        footer_links.addWidget(self.sidebar_about_btn)
        layout.addLayout(footer_links)

        return sidebar

    def _build_header_section(self) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName("mainHeaderFrame")
        outer_layout = QHBoxLayout(frame)
        outer_layout.setContentsMargins(24, 14, 24, 14)
        outer_layout.setSpacing(16)

        left_vbox = QVBoxLayout()
        left_vbox.setSpacing(2)
        self.page_title_label = QLabel(tr("nav_overview"), frame)
        self.page_title_label.setObjectName("pageTitle")
        self.page_subtitle_label = QLabel(tr("header_subtitle_overview"), frame)
        self.page_subtitle_label.setObjectName("pageSubtitle")
        self.page_subtitle_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        left_vbox.addWidget(self.page_title_label)
        left_vbox.addWidget(self.page_subtitle_label)
        outer_layout.addLayout(left_vbox)

        outer_layout.addStretch(1)

        # Lado direito: pílula de status global, conta conectada e opções
        right_widget = QWidget(frame)
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        self.global_status_pill = QLabel(tr("pill_healthy"), right_widget)
        self.global_status_pill.setProperty("class", "statusPill statusPillHealthy")

        self.header_account_badge = QLabel(tr("header_not_connected"), right_widget)
        self.header_account_badge.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.header_account_badge.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.header_account_badge.setStyleSheet("color: #8B949E; font-size: 12px;")

        self.options_menu_btn = QPushButton(tr("header_btn_options"), right_widget)
        self.options_menu_btn.setAccessibleName("Menu de opções secundárias")
        self.options_menu_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.options_menu = QMenu(self)
        self.menu_diag_action = self.options_menu.addAction(tr("menu_action_diagnostics"), self._open_diagnostics_dialog)
        self.menu_about_action = self.options_menu.addAction(tr("menu_action_about"), self._open_about_dialog)
        self.options_menu.addSeparator()
        self.menu_exit_action = self.options_menu.addAction(tr("menu_action_exit"), self.open_exit_dialog)
        self.options_menu_btn.setMenu(self.options_menu)

        self.header_settings_shortcut_btn = QPushButton(tr("header_btn_configure"), right_widget)
        self.header_settings_shortcut_btn.setVisible(False)
        self.header_settings_shortcut_btn.clicked.connect(lambda: self.set_current_page(3))

        right_layout.addWidget(self.global_status_pill)
        right_layout.addWidget(self.header_account_badge)
        right_layout.addWidget(self.options_menu_btn)
        outer_layout.addWidget(right_widget, alignment=Qt.AlignmentFlag.AlignVCenter)

        return frame

    def _build_tabs_section(self) -> QTabWidget:
        self.tabs = QTabWidget(self)
        self.tabs.setAccessibleName("Páginas de navegação do BrisaSync")
        self.tabs.tabBar().setVisible(False)
        self.tabs.setDocumentMode(True)

        self.tabs.addTab(self._build_overview_page(), "Visão geral")
        self.tabs.addTab(self._build_folders_page(), "Pastas")
        self.tabs.addTab(self._build_activity_page(), "Atividade")
        self.tabs.addTab(self._build_settings_page(), "Ajustes")

        self.tabs.currentChanged.connect(self._on_tab_changed)
        return self.tabs

    def set_current_page(self, index: int) -> None:
        index = max(0, min(self.tabs.count() - 1, index))
        self.tabs.setCurrentIndex(index)

    def _on_tab_changed(self, index: int) -> None:
        meta = [
            (tr("nav_overview"), tr("header_subtitle_overview")),
            (tr("nav_folders"), tr("header_subtitle_folders")),
            (tr("nav_activity"), tr("header_subtitle_activity")),
            (tr("nav_settings"), tr("header_subtitle_settings")),
        ]
        if 0 <= index < len(meta):
            t, s = meta[index]
            self.page_title_label.setText(t)
            self.page_subtitle_label.setText(s)

        for i, btn in enumerate(self.nav_buttons):
            is_active = (i == index)
            if isinstance(btn, BrisaSidebarNavItem):
                btn.setActive(is_active)
            else:
                btn.setProperty("active", "true" if is_active else "false")
                btn.style().unpolish(btn)
                btn.style().polish(btn)

        if index == 2:
            self.refresh_history_table()
        elif index == 1:
            self._update_sync_target_preview()

    def open_exit_dialog(self) -> None:
        """Abre a instância única do diálogo unificado de saída do BrisaSync."""
        if self._exit_dialog is not None and self._exit_dialog.isVisible():
            self._exit_dialog.raise_()
            self._exit_dialog.activateWindow()
            return

        parent = None if self.isHidden() else self
        dlg = BrisaExitDialog(self, parent=parent)
        self._exit_dialog = dlg
        if self.isHidden():
            dlg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        dlg.exec()
        if self._exit_dialog is dlg:
            self._exit_dialog = None

    def _open_diagnostics_dialog(self) -> None:
        self.refresh_diagnostics()
        if getattr(self, "_suppress_dialogs_for_testing", False):
            return
        self.diagnostics_dialog.exec()

    def _open_about_dialog(self) -> None:
        dlg = BrisaAboutDialog(self)
        dlg.exec()

    # =========================================================================
    # PÁGINA 0: VISÃO GERAL (HERO BANNER + PAINEL EM CARTÕES)
    # =========================================================================

    def _build_overview_page(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.overview_scroll = scroll

        container = QWidget(scroll)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # 1. Hero Status Banner
        self.hero_banner = QFrame(container)
        self.hero_banner.setObjectName("heroBanner")
        self.hero_banner.setProperty("heroState", "healthy")
        hero_layout = QVBoxLayout(self.hero_banner)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(12)
        self.hero_banner_layout = hero_layout

        top_hero_row = QHBoxLayout()
        top_hero_row.setSpacing(14)
        self.top_hero_row = top_hero_row

        self.hero_icon_label = QLabel(self.hero_banner)
        self.hero_icon_label.setPixmap(render_vector_pixmap("check_circle", 36, "#FFFFFF"))
        self.hero_icon_label.setFixedSize(36, 36)

        text_vbox = QVBoxLayout()
        text_vbox.setSpacing(2)
        self.hero_title_label = QLabel("Tudo em dia", self.hero_banner)
        self.hero_title_label.setStyleSheet("color: #FFFFFF; font-size: 19px; font-weight: bold;")
        self.hero_subtitle_label = QLabel("Última verificação há 1 min", self.hero_banner)
        self.hero_subtitle_label.setStyleSheet("color: rgba(255, 255, 255, 0.85); font-size: 12px;")
        text_vbox.addWidget(self.hero_title_label)
        text_vbox.addWidget(self.hero_subtitle_label)

        self.hero_actions_container = QWidget(self.hero_banner)
        hero_actions_row = QHBoxLayout(self.hero_actions_container)
        hero_actions_row.setContentsMargins(0, 0, 0, 0)
        hero_actions_row.setSpacing(10)
        self.hero_actions_row = hero_actions_row

        self.hero_sync_now_btn = QPushButton("Sincronizar agora", self.hero_actions_container)
        self.hero_sync_now_btn.setObjectName("heroPrimaryBtn")
        self.hero_sync_now_btn.setIcon(get_vector_icon("sync", 16, "#0B0F15"))
        self.hero_sync_now_btn.setIconSize(QSize(16, 16))
        self.hero_sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hero_sync_now_btn.clicked.connect(self._on_sync_now_clicked)

        self.hero_pause_btn = QPushButton("Pausar tudo", self.hero_actions_container)
        self.hero_pause_btn.setObjectName("heroSecondaryBtn")
        self.hero_pause_btn.setIcon(get_vector_icon("pause", 14, "#FFFFFF"))
        self.hero_pause_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hero_pause_btn.clicked.connect(self._on_hero_pause_toggle)

        hero_actions_row.addWidget(self.hero_sync_now_btn)
        hero_actions_row.addWidget(self.hero_pause_btn)

        top_hero_row.addWidget(self.hero_icon_label)
        top_hero_row.addLayout(text_vbox, stretch=1)
        top_hero_row.addWidget(self.hero_actions_container)
        hero_layout.addLayout(top_hero_row)

        # Faixa inferior de métricas no Hero Banner
        metric_strip = QHBoxLayout()
        metric_strip.setSpacing(28)

        speed_col = QVBoxLayout()
        speed_col.setSpacing(1)
        lbl_sp_t = QLabel(tr("hero_stat_speed"), self.hero_banner)
        lbl_sp_t.setStyleSheet("font-size: 9px; font-weight: bold; color: rgba(255, 255, 255, 0.7);")
        self.hero_metric_speed_lbl = lbl_sp_t
        self.hero_metric_speed_val = QLabel("—", self.hero_banner)
        self.hero_metric_speed_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #FFFFFF;")
        speed_col.addWidget(lbl_sp_t)
        speed_col.addWidget(self.hero_metric_speed_val)

        trans_col = QVBoxLayout()
        trans_col.setSpacing(1)
        lbl_tr_t = QLabel(tr("hero_stat_transferred"), self.hero_banner)
        lbl_tr_t.setStyleSheet("font-size: 9px; font-weight: bold; color: rgba(255, 255, 255, 0.7);")
        self.hero_metric_transfer_lbl = lbl_tr_t
        self.hero_metric_transfer_val = QLabel("0 B", self.hero_banner)
        self.hero_metric_transfer_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #FFFFFF;")
        trans_col.addWidget(lbl_tr_t)
        trans_col.addWidget(self.hero_metric_transfer_val)

        fold_col = QVBoxLayout()
        fold_col.setSpacing(1)
        lbl_fd_t = QLabel(tr("hero_stat_active_folders"), self.hero_banner)
        lbl_fd_t.setStyleSheet("font-size: 9px; font-weight: bold; color: rgba(255, 255, 255, 0.7);")
        self.hero_metric_folders_lbl = lbl_fd_t
        self.hero_metric_folders_val = QLabel(tr("hero_stat_folders_ratio", active=0, total=0), self.hero_banner)
        self.hero_metric_folders_val.setStyleSheet("font-size: 12px; font-weight: bold; color: #FFFFFF;")
        fold_col.addWidget(lbl_fd_t)
        fold_col.addWidget(self.hero_metric_folders_val)

        metric_strip.addLayout(speed_col)
        metric_strip.addLayout(trans_col)
        metric_strip.addLayout(fold_col)
        metric_strip.addStretch(1)
        hero_layout.addLayout(metric_strip)
        layout.addWidget(self.hero_banner)

        # 2. Container Configurado: 2 Colunas Responsivas
        self.home_configured_container = QWidget(container)
        grid_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self.home_configured_container)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(16)
        self.overview_grid_layout = grid_layout

        # 2.1 Coluna Esquerda (~60%): Na Fila / Operação Atual + Atividade Recente
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # Card: Na fila / Operação atual
        self.overview_operation_card = QFrame(self.home_configured_container)
        self.overview_operation_card.setProperty("class", "brisaCard")
        op_card_lay = QVBoxLayout(self.overview_operation_card)
        op_card_lay.setContentsMargins(18, 16, 18, 16)
        op_card_lay.setSpacing(12)

        op_header = QLabel("Na fila", self.overview_operation_card)
        op_header.setProperty("class", "cardTitle")
        self.overview_operation_header = op_header
        op_card_lay.addWidget(op_header)

        # Estado em repouso (vazio limpo)
        self.overview_idle_box = QWidget(self.overview_operation_card)
        idle_lay = QVBoxLayout(self.overview_idle_box)
        idle_lay.setContentsMargins(0, 12, 0, 12)
        idle_lay.setSpacing(8)
        idle_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        idle_ic = QLabel(self.overview_idle_box)
        idle_ic.setPixmap(render_vector_pixmap("check", 24, "#9189FF"))
        idle_ic.setStyleSheet("background-color: rgba(145, 137, 255, 0.15); border-radius: 20px; padding: 8px;")
        idle_ic.setFixedSize(40, 40)
        idle_ic.setAlignment(Qt.AlignmentFlag.AlignCenter)

        idle_title = QLabel("Nada para transferir", self.overview_idle_box)
        idle_title.setProperty("class", "idleStateTitle")
        idle_sub = QLabel("Todas as pastas ativas estão atualizadas.", self.overview_idle_box)
        idle_sub.setProperty("class", "idleStateSub")

        btn_icon_col = "#F0F4F8" if is_dark_mode() else "#475569"
        self.overview_verify_again_btn = QPushButton("Verificar novamente", self.overview_idle_box)
        self.overview_verify_again_btn.setIcon(get_vector_icon("sync", 14, btn_icon_col))
        self.overview_verify_again_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overview_verify_again_btn.clicked.connect(self._on_sync_now_clicked)

        idle_lay.addWidget(idle_ic, alignment=Qt.AlignmentFlag.AlignCenter)
        idle_lay.addWidget(idle_title, alignment=Qt.AlignmentFlag.AlignCenter)
        idle_lay.addWidget(idle_sub, alignment=Qt.AlignmentFlag.AlignCenter)
        idle_lay.addWidget(self.overview_verify_again_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        op_card_lay.addWidget(self.overview_idle_box)

        # Banner de atenção (visível apenas em erro / conflito)
        self.attention_banner_frame = QFrame(self.overview_operation_card)
        self.attention_banner_frame.setObjectName("attentionBanner")
        self.attention_banner_frame.setStyleSheet(
            "#attentionBanner { background-color: rgba(220, 38, 38, 0.12); "
            "border: 1px solid rgba(220, 38, 38, 0.4); border-radius: 10px; padding: 10px; }"
        )
        banner_layout = QHBoxLayout(self.attention_banner_frame)
        banner_layout.setContentsMargins(10, 8, 10, 8)
        banner_layout.setSpacing(10)

        self.attention_explanation_label = QLabel(
            "Status de Atenção: [NENHUM ALERTA ATIVO] — Nenhum conflito, falha persistente ou bloqueio pendente.",
            self.attention_banner_frame,
        )
        self.attention_explanation_label.setWordWrap(True)
        self.attention_explanation_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        self.inspect_details_button = QPushButton("Ver Detalhes...", self.attention_banner_frame)
        self.inspect_details_button.setAccessibleName("Abrir diagnóstico técnico do alerta")
        self.inspect_details_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.inspect_details_button.clicked.connect(self._show_attention_details_dialog)

        self.inspect_attention_button = QPushButton("Ver no &Histórico", self.attention_banner_frame)
        self.inspect_attention_button.setAccessibleName("Ver detalhes do alerta no histórico")
        self.inspect_attention_button.clicked.connect(self._on_inspect_attention_clicked)

        banner_layout.addWidget(self.attention_explanation_label, stretch=1)
        banner_layout.addWidget(self.inspect_details_button)
        banner_layout.addWidget(self.inspect_attention_button)
        self.attention_banner_frame.setVisible(False)
        op_card_lay.addWidget(self.attention_banner_frame)
        left_col.addWidget(self.overview_operation_card)

        # Card: Atividade recente
        self.overview_recent_card = QFrame(self.home_configured_container)
        self.overview_recent_card.setProperty("class", "brisaCard")
        rec_lay = QVBoxLayout(self.overview_recent_card)
        rec_lay.setContentsMargins(18, 16, 18, 16)
        rec_lay.setSpacing(12)

        rec_head = QHBoxLayout()
        rec_title = QLabel("Atividade recente", self.overview_recent_card)
        rec_title.setProperty("class", "cardTitle")
        self.overview_view_all_activity_btn = QPushButton("Ver tudo", self.overview_recent_card)
        self.overview_view_all_activity_btn.setFlat(True)
        self.overview_view_all_activity_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overview_view_all_activity_btn.clicked.connect(lambda: self.set_current_page(2))
        rec_head.addWidget(rec_title)
        rec_head.addStretch(1)
        rec_head.addWidget(self.overview_view_all_activity_btn)
        rec_lay.addLayout(rec_head)

        self.overview_recent_list_container = QWidget(self.overview_recent_card)
        self.overview_recent_list_layout = QVBoxLayout(self.overview_recent_list_container)
        self.overview_recent_list_layout.setContentsMargins(0, 0, 0, 0)
        self.overview_recent_list_layout.setSpacing(8)
        rec_lay.addWidget(self.overview_recent_list_container)
        left_col.addWidget(self.overview_recent_card)
        grid_layout.addLayout(left_col, stretch=3)

        # 2.2 Coluna Direita (~40%): Contas + Pastas
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Card: Contas
        accounts_card = QFrame(self.home_configured_container)
        accounts_card.setProperty("class", "brisaCard")
        acc_lay = QVBoxLayout(accounts_card)
        acc_lay.setContentsMargins(18, 16, 18, 16)
        acc_lay.setSpacing(12)

        acc_head = QLabel("Contas", accounts_card)
        acc_head.setProperty("class", "cardTitle")
        acc_lay.addWidget(acc_head)

        acc_box = QFrame(accounts_card)
        acc_box.setProperty("class", "brisaInnerCard")
        abox_lay = QHBoxLayout(acc_box)
        abox_lay.setContentsMargins(12, 10, 12, 10)
        abox_lay.setSpacing(12)

        drv_ic = QLabel(acc_box)
        drv_ic.setPixmap(render_vector_pixmap("google_drive", 24, "#9189FF"))
        drv_ic.setFixedSize(24, 24)

        abox_text = QVBoxLayout()
        abox_text.setSpacing(2)
        self.overview_account_email_label = QLabel("Nenhuma conta vinculada", acc_box)
        self.overview_account_email_label.setProperty("class", "overviewItemTitle")
        self.overview_account_email_label.setWordWrap(True)
        self.overview_account_sub_label = QLabel("Google Drive", acc_box)
        self.overview_account_sub_label.setProperty("class", "overviewItemSub")
        abox_text.addWidget(self.overview_account_email_label)
        abox_text.addWidget(self.overview_account_sub_label)

        self.overview_account_status_label = QLabel("○ não conectada", acc_box)
        self.overview_account_status_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.overview_account_status_label.setStyleSheet("color: #8B949E; font-weight: 600; font-size: 11px;")

        abox_lay.addWidget(drv_ic)
        abox_lay.addLayout(abox_text, stretch=1)
        abox_lay.addWidget(self.overview_account_status_label)
        acc_lay.addWidget(acc_box)
        right_col.addWidget(accounts_card)

        # Card: Pastas
        folders_card = QFrame(self.home_configured_container)
        folders_card.setProperty("class", "brisaCard")
        fld_lay = QVBoxLayout(folders_card)
        fld_lay.setContentsMargins(18, 16, 18, 16)
        fld_lay.setSpacing(12)

        fld_head = QHBoxLayout()
        fld_title = QLabel("Pastas", folders_card)
        fld_title.setProperty("class", "cardTitle")
        self.overview_manage_folders_btn = QPushButton("Gerenciar", folders_card)
        self.overview_manage_folders_btn.setFlat(True)
        self.overview_manage_folders_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overview_manage_folders_btn.clicked.connect(lambda: self.set_current_page(1))
        fld_head.addWidget(fld_title)
        fld_head.addStretch(1)
        fld_head.addWidget(self.overview_manage_folders_btn)
        fld_lay.addLayout(fld_head)

        fld_box = QFrame(folders_card)
        fld_box.setProperty("class", "brisaInnerCard")
        fbox_lay = QHBoxLayout(fld_box)
        fbox_lay.setContentsMargins(12, 10, 12, 10)
        fbox_lay.setSpacing(12)

        f_ic = QLabel(fld_box)
        f_ic.setPixmap(render_vector_pixmap("folder", 24, "#9189FF"))
        f_ic.setFixedSize(24, 24)

        fbox_text = QVBoxLayout()
        fbox_text.setSpacing(2)
        self.overview_folder_name_label = QLabel("Configuração pendente", fld_box)
        self.overview_folder_name_label.setProperty("class", "overviewItemTitle")
        self.overview_folder_name_label.setWordWrap(True)
        self.overview_folder_path_label = QLabel("Nenhuma pasta sincronizada configurada", fld_box)
        self.overview_folder_path_label.setProperty("class", "overviewItemSub")
        fbox_text.addWidget(self.overview_folder_name_label)
        fbox_text.addWidget(self.overview_folder_path_label)

        self.overview_folder_status_pill = QLabel("○ pendente", fld_box)
        self.overview_folder_status_pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.overview_folder_status_pill.setStyleSheet(
            "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
            "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
        )

        f_btn_col = "#F0F4F8" if is_dark_mode() else "#475569"
        self.overview_open_folder_btn = QPushButton(fld_box)
        self.overview_open_folder_btn.setIcon(get_vector_icon("open_folder", 16, f_btn_col))
        self.overview_open_folder_btn.setToolTip("Abrir pasta local no gerenciador de arquivos")
        self.overview_open_folder_btn.setFixedSize(30, 30)
        self.overview_open_folder_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.overview_open_folder_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.overview_open_folder_btn.clicked.connect(self.open_configured_local_folder)

        fbox_lay.addWidget(f_ic)
        fbox_lay.addLayout(fbox_text, stretch=1)
        fbox_lay.addWidget(self.overview_folder_status_pill)
        fbox_lay.addWidget(self.overview_open_folder_btn)
        fld_lay.addWidget(fld_box)
        right_col.addWidget(folders_card)
        right_col.addStretch(1)

        grid_layout.addLayout(right_col, stretch=2)
        layout.addWidget(self.home_configured_container)

        # 3. Widgets Legados Ocultos mantidos para 100% de Compatibilidade Reversa com Testes
        self._legacy_hidden_box = QWidget(self)
        self._legacy_hidden_box.setVisible(False)
        self.home_status_card = QFrame(self._legacy_hidden_box)
        self.home_main_state_label = QLabel(self.home_status_card)
        self.last_updated_label = QLabel(self.home_status_card)

        self.home_folders_card = QFrame(self._legacy_hidden_box)
        self.home_remote_folder_display = QLabel(self.home_folders_card)
        self.home_local_folder_display = QLabel(self.home_folders_card)
        self.home_change_folders_button = QPushButton(self.home_folders_card)
        self.home_change_folders_button.clicked.connect(lambda: self.set_current_page(1))
        self.open_local_folder_button = QPushButton(self.home_folders_card)
        self.open_local_folder_button.clicked.connect(self.open_configured_local_folder)

        self.sync_now_button = QPushButton(self._legacy_hidden_box)
        self.sync_now_button.clicked.connect(self._on_sync_now_clicked)
        self.pause_sync_button = QPushButton(self._legacy_hidden_box)
        self.pause_sync_button.clicked.connect(self._on_pause_sync_clicked)
        self.resume_sync_button = QPushButton(self._legacy_hidden_box)
        self.resume_sync_button.clicked.connect(self._on_resume_sync_clicked)
        self.stop_current_button = QPushButton(self._legacy_hidden_box)
        self.stop_current_button.clicked.connect(self._on_stop_current_clicked)

        # 4. Container Não Configurado (Assistente Guiado Passo a Passo)
        self.home_unconfigured_container = QWidget(container)
        unconf_layout = QVBoxLayout(self.home_unconfigured_container)
        unconf_layout.setContentsMargins(0, 0, 0, 0)
        unconf_layout.setSpacing(10)

        self.wizard_card = QFrame(self.home_unconfigured_container)
        self.wizard_card.setProperty("class", "brisaCard")
        wz_layout = QVBoxLayout(self.wizard_card)
        wz_layout.setContentsMargins(20, 16, 20, 16)
        wz_layout.setSpacing(10)

        wz_title = QLabel("Configuração Inicial do BrisaSync", self.wizard_card)
        wz_title_font = QFont(self.font())
        wz_title_font.setPointSize(max(wz_title_font.pointSize() + 3, 14))
        wz_title_font.setBold(True)
        wz_title.setFont(wz_title_font)

        wz_subtitle = QLabel(
            "Mantenha seus arquivos sincronizados e disponíveis offline.",
            self.wizard_card,
        )
        wz_subtitle.setWordWrap(True)
        wz_subtitle.setStyleSheet("color: #8B949E;")

        self.wizard_step_indicator = QLabel(self.wizard_card)
        self.wizard_step_indicator.setStyleSheet("padding: 4px 0px; font-size: 11px;")
        self._update_wizard_progress(0)

        self.wizard_stack = QStackedWidget(self.wizard_card)
        self.wizard_stack.addWidget(self._build_wizard_page_connect(self.wizard_card))
        self.wizard_stack.addWidget(self._build_wizard_page_remote(self.wizard_card))
        self.wizard_stack.addWidget(self._build_wizard_page_local(self.wizard_card))
        self.wizard_stack.addWidget(self._build_wizard_page_review(self.wizard_card))

        wz_layout.addWidget(wz_title)
        wz_layout.addWidget(wz_subtitle)
        wz_layout.addWidget(self.wizard_step_indicator)
        wz_layout.addWidget(self.wizard_stack, stretch=1)

        unconf_layout.addWidget(self.wizard_card)
        layout.addWidget(self.home_unconfigured_container)

        layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    def _build_wizard_page_connect(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.setup_step1_label = QLabel("1. Conectar conta Google", page)
        self.setup_step1_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        desc = QLabel(
            "Conecte sua conta do Google Drive para iniciar a sincronização com este computador.\n"
            "Seu navegador padrão será aberto para autorizar com segurança via Google OAuth.",
            page,
        )
        desc.setWordWrap(True)

        self.setup_step1_status = QLabel("Nenhuma conta Google conectada no momento.", page)
        self.setup_step1_status.setStyleSheet("color: #8B949E;")

        btn_row = QHBoxLayout()
        self.setup_connect_button = QPushButton("Conectar Conta Google", page)
        self.setup_connect_button.setProperty("primary", "true")
        self.setup_connect_button.clicked.connect(self._on_wizard_connect_clicked)
        btn_row.addWidget(self.setup_connect_button)
        btn_row.addStretch(1)

        self.setup_step1_hint = QLabel(page)
        self.setup_step1_hint.setWordWrap(True)
        self.setup_step1_hint.setStyleSheet("color: #EF4444; font-size: 11px;")
        self.setup_step1_hint.setVisible(False)

        layout.addWidget(self.setup_step1_label)
        layout.addWidget(desc)
        layout.addWidget(self.setup_step1_status)
        layout.addLayout(btn_row)
        layout.addWidget(self.setup_step1_hint)
        layout.addStretch(1)

        nav_row = QHBoxLayout()
        nav_row.addStretch(1)
        self.setup_step1_next_btn = QPushButton("Avançar →", page)
        self.setup_step1_next_btn.setEnabled(False)
        self.setup_step1_next_btn.clicked.connect(lambda: self._set_wizard_step(1))
        nav_row.addWidget(self.setup_step1_next_btn)
        layout.addLayout(nav_row)

        return page

    def _build_wizard_page_remote(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.setup_step2_label = QLabel("2. Escolher pasta no Google Drive", page)
        self.setup_step2_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        desc = QLabel(
            "Selecione qual pasta do seu Google Drive será sincronizada com este computador:",
            page,
        )
        desc.setWordWrap(True)

        combo_row = QHBoxLayout()
        self.wizard_remote_combo = QComboBox(page)
        self.wizard_remote_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.wizard_remote_combo.currentIndexChanged.connect(
            self._on_wizard_remote_combo_changed
        )
        combo_row.addWidget(self.wizard_remote_combo)

        btns_row = QHBoxLayout()
        self.wizard_list_remote_btn = QPushButton("Listar Pastas do Drive", page)
        self.wizard_list_remote_btn.clicked.connect(self._on_list_remote_folders)
        self.wizard_create_remote_btn = QPushButton("+ Nova Pasta...", page)
        self.wizard_create_remote_btn.clicked.connect(
            self._on_wizard_create_remote_clicked
        )
        btns_row.addWidget(self.wizard_list_remote_btn)
        btns_row.addWidget(self.wizard_create_remote_btn)
        btns_row.addStretch(1)

        self.wizard_remote_feedback = QLabel(
            "Clique em 'Listar Pastas do Drive' para carregar ou selecione a pasta desejada.",
            page,
        )
        self.wizard_remote_feedback.setWordWrap(True)
        self.wizard_remote_feedback.setStyleSheet("color: #8B949E;")

        self.setup_remote_button = self.wizard_list_remote_btn

        layout.addWidget(self.setup_step2_label)
        layout.addWidget(desc)
        layout.addLayout(combo_row)
        layout.addLayout(btns_row)
        layout.addWidget(self.wizard_remote_feedback)
        layout.addStretch(1)

        nav_row = QHBoxLayout()
        self.wizard_step2_back_btn = QPushButton("← Voltar", page)
        self.wizard_step2_back_btn.clicked.connect(lambda: self._set_wizard_step(0))
        self.wizard_step2_next_btn = QPushButton("Avançar →", page)
        self.wizard_step2_next_btn.setEnabled(False)
        self.wizard_step2_next_btn.clicked.connect(lambda: self._set_wizard_step(2))
        nav_row.addWidget(self.wizard_step2_back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.wizard_step2_next_btn)
        layout.addLayout(nav_row)

        return page

    def _build_wizard_page_local(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        self.setup_step3_label = QLabel("3. Escolher pasta local (vazia na 1ª vez)", page)
        self.setup_step3_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        desc = QLabel(
            "Selecione uma pasta no computador onde os arquivos serão mantidos sincronizados.\n"
            "Para a segurança dos seus dados, na primeira sincronização a pasta local deve estar vazia.",
            page,
        )
        desc.setWordWrap(True)

        path_row = QHBoxLayout()
        self.wizard_local_path_input = QLineEdit(page)
        self.wizard_local_path_input.setPlaceholderText(str(Path.home() / "BrisaSync"))
        self.wizard_local_path_input.textChanged.connect(self._on_wizard_local_path_edited)

        self.wizard_local_browse_btn = QPushButton("Procurar Pasta...", page)
        self.wizard_local_browse_btn.clicked.connect(self._on_wizard_browse_local_folder)
        path_row.addWidget(self.wizard_local_path_input, stretch=1)
        path_row.addWidget(self.wizard_local_browse_btn)

        self.wizard_local_feedback = QLabel(
            "Escolha uma pasta vazia para a sincronização inicial.", page
        )
        self.wizard_local_feedback.setWordWrap(True)
        self.wizard_local_feedback.setStyleSheet("color: #8B949E;")

        self.setup_local_button = self.wizard_local_browse_btn

        layout.addWidget(self.setup_step3_label)
        layout.addWidget(desc)
        layout.addLayout(path_row)
        layout.addWidget(self.wizard_local_feedback)
        layout.addStretch(1)

        nav_row = QHBoxLayout()
        self.wizard_step3_back_btn = QPushButton("← Voltar", page)
        self.wizard_step3_back_btn.clicked.connect(lambda: self._set_wizard_step(1))
        self.wizard_step3_next_btn = QPushButton("Avançar →", page)
        self.wizard_step3_next_btn.setEnabled(False)
        self.wizard_step3_next_btn.clicked.connect(lambda: self._set_wizard_step(3))
        nav_row.addWidget(self.wizard_step3_back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.wizard_step3_next_btn)
        layout.addLayout(nav_row)

        return page

    def _build_wizard_page_review(self, parent: QWidget) -> QWidget:
        page = QWidget(parent)
        layout = QVBoxLayout(page)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)

        self.setup_step4_label = QLabel("Revisão e confirmação das configurações:", page)
        self.setup_step4_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        summary_frame = QFrame(page)
        summary_frame.setProperty("class", "brisaInnerCard")
        grid = QGridLayout(summary_frame)
        grid.setContentsMargins(12, 6, 12, 6)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(1, 1)

        lbl_acc = QLabel("Conta Google:", summary_frame)
        lbl_acc.setStyleSheet("color: #8B949E;")
        self.wizard_review_account_label = QLabel("—", summary_frame)
        self.wizard_review_account_label.setStyleSheet("font-weight: bold;")
        self.wizard_review_account_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        lbl_rem = QLabel("Google Drive:", summary_frame)
        lbl_rem.setStyleSheet("color: #8B949E;")
        self.wizard_review_remote_label = QLabel("—", summary_frame)
        self.wizard_review_remote_label.setStyleSheet("font-weight: bold;")
        self.wizard_review_remote_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        lbl_loc = QLabel("Pasta no Computador:", summary_frame)
        lbl_loc.setStyleSheet("color: #8B949E;")
        self.wizard_review_local_label = QLabel("—", summary_frame)
        self.wizard_review_local_label.setStyleSheet("font-weight: bold;")
        self.wizard_review_local_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        grid.addWidget(lbl_acc, 0, 0)
        grid.addWidget(self.wizard_review_account_label, 0, 1)
        grid.addWidget(lbl_rem, 1, 0)
        grid.addWidget(self.wizard_review_remote_label, 1, 1)
        grid.addWidget(lbl_loc, 2, 0)
        grid.addWidget(self.wizard_review_local_label, 2, 1)

        explanation_frame = QFrame(page)
        explanation_frame.setProperty("class", "brisaInnerCard")
        expl_layout = QVBoxLayout(explanation_frame)
        expl_layout.setContentsMargins(12, 6, 12, 6)
        expl_layout.setSpacing(3)

        expl_title = QLabel("Como funciona a sincronização do BrisaSync:", explanation_frame)
        expl_title.setStyleSheet("font-weight: bold;")

        expl_body = QLabel(
            "• <b>Sincronização Bidirecional:</b> Novos arquivos e alterações são espelhados em ambos os sentidos.<br>"
            "• <b>Exclusões e Lixeira:</b> Apagar um arquivo localmente também o move para a lixeira no Drive.<br>"
            "• <b>Segurança dos Dados:</b> Conflitos simultâneos geram cópias seguras sem sobrescrita.",
            explanation_frame,
        )
        expl_body.setWordWrap(True)
        expl_layout.addWidget(expl_title)
        expl_layout.addWidget(expl_body)

        layout.addWidget(self.setup_step4_label)
        layout.addWidget(summary_frame)
        layout.addWidget(explanation_frame, stretch=1)

        nav_row = QHBoxLayout()
        self.wizard_step4_back_btn = QPushButton("← Voltar", page)
        self.wizard_step4_back_btn.clicked.connect(lambda: self._set_wizard_step(2))
        self.setup_start_button = QPushButton("Iniciar Sincronização", page)
        self.setup_start_button.setProperty("primary", "true")
        self.setup_start_button.clicked.connect(self._on_wizard_finish_and_sync)
        nav_row.addWidget(self.wizard_step4_back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.setup_start_button)
        layout.addLayout(nav_row)

        return page

    def _update_wizard_progress(self, current_step: int) -> None:
        steps = [
            "1. Conectar Conta",
            "2. Pasta do Drive",
            "3. Pasta Local",
            "4. Revisar e Iniciar",
        ]
        parts = []
        for idx, name in enumerate(steps):
            if idx == current_step:
                parts.append(f"<b><span style='color: #9189FF;'>● {name}</span></b>")
            elif idx < current_step:
                parts.append(f"<span style='color: #10B981;'>✓ {name}</span>")
            else:
                parts.append(f"<span style='color: #64748B;'>○ {name}</span>")
        self.wizard_step_indicator.setText("   ›   ".join(parts))

    def _set_wizard_step(self, step_idx: int) -> None:
        step_idx = max(0, min(3, step_idx))
        self.wizard_stack.setCurrentIndex(step_idx)
        self._update_wizard_progress(step_idx)
        self._refresh_wizard_step_data(step_idx)

    def _get_account_operational_state(
        self, *, interactive: bool = False, force_refresh: bool = False
    ) -> tuple[str, OAuthCredentials | None, str]:
        """Avalia de forma unificada e rigorosa o estado da conta Google no sistema.

        Retorna:
            (estado, credenciais_ou_none, mensagem_detalhe)
            Estados:
            - "VAULT_LOCKED": Cofre de segredos inacessível ou bloqueado.
            - "NOT_CONNECTED": Nenhuma conta autorizada presente no cofre.
            - "CONFIG_PENDING": Credenciais válidas no cofre, mas arquivo cifrado rclone pendente de geração.
            - "READY": Conta autorizada e motor rclone materializado e pronto para operar.
        """
        # Checagem não interativa: se o cofre estiver bloqueado, jamais tenta lookup interativo
        if not interactive and self.credential_store.is_vault_locked():
            return (
                "VAULT_LOCKED",
                None,
                "Cofre de credenciais bloqueado. Desbloqueie o chaveiro da sessão.",
            )

        try:
            try:
                creds = self.credential_store.load_credentials(interactive=interactive)
            except TypeError:
                creds = self.credential_store.load_credentials()
        except VaultLockedError as exc:
            return "VAULT_LOCKED", None, f"Cofre bloqueado: {exc}"
        except VaultUnavailableError as exc:
            return "VAULT_LOCKED", None, f"Cofre inacessível: {exc}"
        except Exception as exc:
            return "VAULT_LOCKED", None, f"Erro no cofre: {exc}"

        if not (creds and creds.access_token and creds.has_drive_scope):
            return "NOT_CONNECTED", None, "Nenhuma conta Google conectada."

        if not self.bridge.config_path.is_file():
            return (
                "CONFIG_PENDING",
                creds,
                f"Credenciais salvas ({creds.account_email}), mas configuração do rclone pendente de conclusão.",
            )

        return "READY", creds, f"Conta conectada ({creds.account_email}) e rclone operacional."

    def _has_usable_account(self) -> bool:
        """Determina de forma rigorosa e unificada se há uma conta Google autorizada e utilizável."""
        if self.database.is_voluntary_disconnect():
            return False
        state, creds, _ = self._get_account_operational_state()
        if state in ("NOT_CONNECTED", "VAULT_LOCKED"):
            return False
        return bool(creds and creds.access_token and creds.has_drive_scope)

    def _refresh_wizard_step_data(self, step_idx: int) -> None:
        state, creds, detail = self._get_account_operational_state()
        account_email = creds.account_email if (creds and creds.account_email) else ""
        remote_cfg = self.database.get_remote_sync_folder()
        local_cfg = self.database.get_local_sync_folder()

        if step_idx == 0:
            if state == "READY" and account_email:
                self.setup_step1_status.setText(f"✓ {tr('wizard_step1_connected', email=account_email)}")
                self.setup_step1_status.setStyleSheet("color: #10B981; font-weight: bold;")
                self.setup_connect_button.setText(tr("wizard_btn_switch_account"))
                self.setup_step1_next_btn.setEnabled(True)
            elif state == "CONFIG_PENDING" and account_email:
                self.setup_step1_status.setText(
                    f"⚠ Credenciais no cofre ({account_email}), mas configuração pendente de conclusão."
                )
                self.setup_step1_status.setStyleSheet("color: #F59E0B; font-weight: bold;")
                self.setup_connect_button.setText(tr("settings_btn_complete_setup"))
                self.setup_step1_next_btn.setEnabled(False)
            elif state == "VAULT_LOCKED":
                self.setup_step1_status.setText(f"Cofre bloqueado: {detail}")
                self.setup_step1_status.setStyleSheet("color: #EF4444; font-weight: bold;")
                self.setup_connect_button.setText(tr("settings_btn_unlock_vault"))
                self.setup_step1_next_btn.setEnabled(False)
            else:
                self.setup_step1_status.setText(tr("wizard_step1_not_connected"))
                self.setup_step1_status.setStyleSheet("color: #8B949E;")
                self.setup_connect_button.setText(tr("settings_btn_connect"))
                self.setup_step1_next_btn.setEnabled(False)

        elif step_idx == 1:
            if remote_cfg:
                self.setup_step2_label.setText(f"✓ 2. Pasta remota: {remote_cfg.folder_name}")
                self.wizard_remote_feedback.setText(
                    f"✓ Pasta remota selecionada: {remote_cfg.folder_name} (ID: {remote_cfg.folder_id})"
                )
                self.wizard_remote_feedback.setStyleSheet("color: #10B981;")
                self.wizard_step2_next_btn.setEnabled(True)
                if self.wizard_remote_combo.count() == 0:
                    self.wizard_remote_combo.addItem(
                        f"{remote_cfg.folder_name} [ID: {remote_cfg.folder_id}]",
                        userData=(remote_cfg.folder_id, remote_cfg.folder_name),
                    )
            else:
                self.setup_step2_label.setText("2. Escolher pasta no Google Drive")
                has_items = self.wizard_remote_combo.count() > 0 and self.wizard_remote_combo.currentIndex() >= 0
                self.wizard_step2_next_btn.setEnabled(has_items)

        elif step_idx == 2:
            if local_cfg:
                self.setup_step3_label.setText(
                    f"✓ 3. Pasta local: {self._format_elided_path(local_cfg.folder_path, 34)}"
                )
                self.wizard_local_path_input.setText(local_cfg.folder_path)
                self.wizard_local_feedback.setText(f"✓ Pasta configurada: {local_cfg.folder_path}")
                self.wizard_local_feedback.setStyleSheet("color: #10B981;")
                self.wizard_step3_next_btn.setEnabled(True)
            else:
                self.setup_step3_label.setText("3. Escolher pasta local (vazia na 1ª vez)")
                raw = self.wizard_local_path_input.text().strip()
                self.wizard_step3_next_btn.setEnabled(bool(raw and Path(raw).expanduser().is_dir()))

        elif step_idx == 3:
            self.wizard_review_account_label.setText(account_email or "Não conectada")
            if remote_cfg:
                self.wizard_review_remote_label.setText(
                    f"{remote_cfg.folder_name} (ID: {remote_cfg.folder_id})"
                )
            else:
                self.wizard_review_remote_label.setText("Não selecionada")

            if local_cfg:
                self.wizard_review_local_label.setText(local_cfg.folder_path)
            else:
                raw_local = self.wizard_local_path_input.text().strip()
                self.wizard_review_local_label.setText(raw_local or "Não selecionada")

    def _on_wizard_connect_clicked(self) -> None:
        self._on_connect_google_clicked()

    def _on_wizard_remote_combo_changed(self, index: int) -> None:
        if index < 0 or self.wizard_remote_combo.count() == 0:
            self.wizard_step2_next_btn.setEnabled(False)
            return
        data = self.wizard_remote_combo.itemData(index)
        if data and isinstance(data, (tuple, list)) and len(data) >= 2:
            folder_id, folder_name = data[0], data[1]
            self.database.set_remote_sync_folder(folder_id=folder_id, folder_name=folder_name)
            self.wizard_remote_feedback.setText(f"✓ Selecionada: {folder_name}")
            self.wizard_remote_feedback.setStyleSheet("color: #10B981;")
            self.wizard_step2_next_btn.setEnabled(True)
            self._update_sync_target_preview()
            self._update_home_view()

    def _on_wizard_create_remote_clicked(self) -> None:
        folder_name, ok = QInputDialog.getText(
            self,
            "Criar Pasta no Google Drive",
            "Nome da nova pasta remota:",
        )
        if ok and folder_name.strip():
            self._create_remote_folder_by_name(folder_name.strip())

    def _on_wizard_browse_local_folder(self) -> None:
        start_dir = str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta Local de Sincronização",
            start_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self.wizard_local_path_input.setText(chosen)

    def _on_wizard_local_path_edited(self, text: str) -> None:
        raw = text.strip()
        if not raw:
            self.wizard_local_feedback.setText("Informe o caminho de uma pasta local.")
            self.wizard_local_feedback.setStyleSheet("color: #8B949E;")
            self.wizard_step3_next_btn.setEnabled(False)
            return

        p = Path(raw).expanduser()
        if not p.exists():
            self.wizard_local_feedback.setText(f"A pasta será criada automaticamente: {p}")
            self.wizard_local_feedback.setStyleSheet("color: #9189FF;")
            self.wizard_step3_next_btn.setEnabled(True)
        elif p.is_dir():
            items = list(p.iterdir())
            if items:
                sample = ", ".join(e.name for e in items[:3])
                self.wizard_local_feedback.setText(
                    f"Atenção: A pasta local contém {len(items)} item(ns) ({sample}). "
                    f"Para a primeira sincronização, escolha outra pasta vazia."
                )
                self.wizard_local_feedback.setStyleSheet("color: #EF4444;")
                self.wizard_step3_next_btn.setEnabled(False)
            else:
                self.wizard_local_feedback.setText(f"✓ Pasta vazia e pronta para sincronização: {p}")
                self.wizard_local_feedback.setStyleSheet("color: #10B981;")
                self.wizard_step3_next_btn.setEnabled(True)
        else:
            self.wizard_local_feedback.setText("O caminho indicado não é um diretório válido.")
            self.wizard_local_feedback.setStyleSheet("color: #EF4444;")
            self.wizard_step3_next_btn.setEnabled(False)

    def _on_wizard_finish_and_sync(self) -> None:
        raw_local = self.wizard_local_path_input.text().strip()
        if raw_local:
            p = Path(raw_local).expanduser()
            if p.is_dir() and any(p.iterdir()):
                remote_cfg = self.database.get_remote_sync_folder()
                remote_name = remote_cfg.folder_name if remote_cfg else "Google Drive"
                self.wizard_local_feedback.setText(
                    f"Para a primeira sincronização com '{remote_name}', a pasta local deve estar vazia. Escolha outra pasta vazia."
                )
                self.wizard_local_feedback.setStyleSheet("color: #EF4444;")
                return
            p.mkdir(parents=True, exist_ok=True)
            self.database.set_local_sync_folder(str(p))
            self.folder_input.setText(str(p))

        self._update_home_view()
        self._on_sync_now_clicked()

    def _on_setup_step1_clicked(self) -> None:
        self._on_wizard_connect_clicked()

    # =========================================================================
    # PÁGINA 1: PASTAS (CARTÃO HORIZONTAL E CONFIGURAÇÃO DE CAMINHOS)
    # =========================================================================

    def _build_folders_page(self) -> QWidget:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.folders_scroll = scroll

        container = QWidget(scroll)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        # 1. Cartão Principal do Par Sincronizado
        self.folders_card_frame = QFrame(container)
        self.folders_card_frame.setProperty("class", "brisaCard")
        fcard_lay = QVBoxLayout(self.folders_card_frame)
        fcard_lay.setContentsMargins(18, 16, 18, 16)
        fcard_lay.setSpacing(12)

        fcard_row = QHBoxLayout()
        fcard_row.setSpacing(14)

        fic = QLabel(self.folders_card_frame)
        fic.setPixmap(render_vector_pixmap("folder", 28, "#9189FF"))
        fic.setStyleSheet("background-color: rgba(145, 137, 255, 0.15); border-radius: 8px; padding: 6px;")
        fic.setFixedSize(40, 40)

        ftext_vbox = QVBoxLayout()
        ftext_vbox.setSpacing(2)
        self.folders_card_title_label = QLabel(tr("folders_card_title"), self.folders_card_frame)
        self.folders_card_title_label.setProperty("class", "cardTitle")
        self.folders_card_subtitle_label = QLabel(
            tr("folders_pending_notice"),
            self.folders_card_frame,
        )
        self.folders_card_subtitle_label.setStyleSheet("font-size: 12px; color: #8B949E;")
        self.folders_card_subtitle_label.setWordWrap(True)
        ftext_vbox.addWidget(self.folders_card_title_label)
        ftext_vbox.addWidget(self.folders_card_subtitle_label)

        fcard_row.addWidget(fic)
        fcard_row.addLayout(ftext_vbox, stretch=1)

        self.folders_card_status_pill = QLabel(tr("folder_status_pending"), self.folders_card_frame)
        self.folders_card_status_pill.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.folders_card_status_pill.setStyleSheet(
            "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
            "border-radius: 12px; padding: 4px 10px; font-size: 11px; font-weight: 600;"
        )
        fcard_row.addWidget(self.folders_card_status_pill)

        f_btn_col = "#F0F4F8" if is_dark_mode() else "#475569"
        self.folders_page_open_btn = QPushButton(tr("folders_local_open_btn"), self.folders_card_frame)
        self.folders_page_open_btn.setIcon(get_vector_icon("open_folder", 14, f_btn_col))
        self.folders_page_open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folders_page_open_btn.clicked.connect(self.open_configured_local_folder)

        self.folders_page_sync_btn = QPushButton(tr("folders_local_sync_btn"), self.folders_card_frame)
        self.folders_page_sync_btn.setIcon(get_vector_icon("sync", 14, f_btn_col))
        self.folders_page_sync_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folders_page_sync_btn.clicked.connect(self._on_sync_now_clicked)

        self.folders_card_actions_container = QWidget(self.folders_card_frame)
        self.folders_card_actions_layout = QHBoxLayout(self.folders_card_actions_container)
        self.folders_card_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.folders_card_actions_layout.setSpacing(8)
        self.folders_card_actions_layout.addWidget(self.folders_page_open_btn)
        self.folders_card_actions_layout.addWidget(self.folders_page_sync_btn)

        self.folders_remove_pair_btn = QPushButton(tr("folders_btn_remove_pair"), self.folders_card_frame)
        self.folders_remove_pair_btn.setIcon(get_vector_icon("clear", 14, f_btn_col))
        self.folders_remove_pair_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folders_remove_pair_btn.clicked.connect(self._on_remove_pair_clicked)
        self.folders_card_actions_layout.addWidget(self.folders_remove_pair_btn)

        self.folders_connect_account_btn = QPushButton(tr("folders_btn_connect_account"), self.folders_card_frame)
        self.folders_connect_account_btn.setIcon(get_vector_icon("link", 14, f_btn_col))
        self.folders_connect_account_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.folders_connect_account_btn.clicked.connect(self._on_connect_google_clicked)
        self.folders_connect_account_btn.setVisible(False)
        self.folders_card_actions_layout.addWidget(self.folders_connect_account_btn)

        fcard_row.addWidget(self.folders_card_actions_container)
        self.folders_card_top_row = fcard_row
        self.folders_card_layout = fcard_lay
        fcard_lay.addLayout(fcard_row)

        fnote = QLabel(
            tr("folders_rule_notice"),
            self.folders_card_frame,
        )
        fnote.setWordWrap(True)
        fnote.setStyleSheet("color: #8B949E; font-size: 11px;")
        self.folders_rule_notice = fnote
        fcard_lay.addWidget(fnote)
        layout.addWidget(self.folders_card_frame)

        # 2. Card de Alteração de Vínculo de Pastas
        paths_card = QFrame(container)
        paths_card.setProperty("class", "brisaCard")
        playout = QVBoxLayout(paths_card)
        playout.setContentsMargins(18, 16, 18, 16)
        playout.setSpacing(14)

        playout_title = QLabel(tr("folders_card_title"), paths_card)
        playout_title.setProperty("class", "cardTitle")
        self.folders_paths_card_title = playout_title
        playout.addWidget(playout_title)

        # Pasta Remota no Google Drive
        r_box = QVBoxLayout()
        r_box.setSpacing(6)
        r_lbl = QLabel(tr("folders_remote_label"), paths_card)
        r_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.folders_remote_lbl = r_lbl

        r_row = QHBoxLayout()
        r_row.setSpacing(8)
        self.remote_folder_combo = QComboBox(paths_card)
        self.remote_folder_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.remote_folder_combo.currentIndexChanged.connect(self._on_remote_folder_selection_changed)

        self.list_remote_folders_button = QPushButton(tr("folders_remote_list_btn"), paths_card)
        self.list_remote_folders_button.clicked.connect(self._on_list_remote_folders)

        self.create_remote_folder_button = QPushButton(tr("folders_remote_new_btn"), paths_card)
        self.create_remote_folder_button.clicked.connect(self._on_create_remote_folder)

        r_row.addWidget(self.remote_folder_combo, stretch=1)
        r_row.addWidget(self.list_remote_folders_button)
        r_row.addWidget(self.create_remote_folder_button)

        self.remote_folder_feedback_label = QLabel(
            tr("folders_remote_status_none"),
            paths_card,
        )
        self.remote_folder_feedback_label.setWordWrap(True)
        self.remote_folder_feedback_label.setStyleSheet("color: #8B949E; font-size: 11px;")

        r_box.addWidget(r_lbl)
        r_box.addLayout(r_row)
        r_box.addWidget(self.remote_folder_feedback_label)
        playout.addLayout(r_box)

        # Pasta Local Dedicada
        l_box = QVBoxLayout()
        l_box.setSpacing(6)
        l_lbl = QLabel(tr("folders_local_label"), paths_card)
        l_lbl.setStyleSheet("font-weight: 600; font-size: 12px;")
        self.folders_local_lbl = l_lbl

        l_row = QHBoxLayout()
        l_row.setSpacing(8)
        self.folder_input = QLineEdit(paths_card)
        self.folder_input.setPlaceholderText(str(Path.home() / "BrisaSync"))
        l_lbl.setBuddy(self.folder_input)

        self.browse_folder_button = QPushButton(tr("folders_local_browse_btn"), paths_card)
        self.browse_folder_button.clicked.connect(self._on_browse_folder)

        self.save_folder_button = QPushButton(tr("folders_local_save_btn"), paths_card)
        self.save_folder_button.clicked.connect(self.save_and_validate_folder)

        l_row.addWidget(self.folder_input, stretch=1)
        l_row.addWidget(self.browse_folder_button)
        l_row.addWidget(self.save_folder_button)

        self.folder_feedback_label = QLabel(
            "Status da pasta: [NÃO CONFIGURADA] — Nenhuma pasta local selecionada.",
            paths_card,
        )
        self.folder_feedback_label.setWordWrap(True)
        self.folder_feedback_label.setStyleSheet("color: #8B949E; font-size: 11px;")

        l_box.addWidget(l_lbl)
        l_box.addLayout(l_row)
        l_box.addWidget(self.folder_feedback_label)
        playout.addLayout(l_box)

        self.sync_target_preview_label = QLabel(
            "Conferência pré-execução: [PENDENTE] — Configure as pastas remota e local.",
            paths_card,
        )
        self.sync_target_preview_label.setWordWrap(True)
        self.sync_target_preview_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        playout.addWidget(self.sync_target_preview_label)

        layout.addWidget(paths_card)
        layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    # =========================================================================
    # PÁGINA 2: ATIVIDADE (HISTÓRICO AUDITÁVEL)
    # =========================================================================

    def _build_activity_page(self) -> QWidget:
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)

        top_bar = QHBoxLayout()
        self.history_summary_label = QLabel(tr("history_summary_count", count=0), container)
        title_font = QFont(self.font())
        title_font.setPointSize(max(title_font.pointSize() + 2, 13))
        title_font.setBold(True)
        self.history_summary_label.setFont(title_font)

        hist_icon_col = "#F0F4F8" if is_dark_mode() else "#475569"
        self.refresh_history_button = QPushButton(tr("history_btn_refresh"), container)
        self.refresh_history_button.setIcon(get_vector_icon("sync", 14, hist_icon_col))
        self.refresh_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_history_button.clicked.connect(self.refresh_history_table)

        self.clear_history_button = QPushButton(tr("history_btn_clear"), container)
        self.clear_history_button.setIcon(get_vector_icon("clear", 14, hist_icon_col))
        self.clear_history_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_history_button.clicked.connect(self._on_clear_history_clicked)

        top_bar.addWidget(self.history_summary_label, stretch=1)
        top_bar.addWidget(self.refresh_history_button)
        top_bar.addWidget(self.clear_history_button)
        layout.addLayout(top_bar)

        self.history_table = QTableWidget(0, 5, container)
        self.history_table.setAccessibleName("Tabela de atividade recente de sincronizações")
        self.history_table.setHorizontalHeaderLabels(
            [
                tr("history_table_header_started"),
                tr("history_table_header_operation"),
                tr("history_table_header_status"),
                tr("history_table_header_folders"),
                tr("history_table_header_summary"),
            ]
        )
        self.history_table.verticalHeader().setVisible(False)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setAlternatingRowColors(True)
        self.history_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_table.itemDoubleClicked.connect(self._on_history_row_double_clicked)

        hist_header = self.history_table.horizontalHeader()
        hist_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hist_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hist_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hist_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hist_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hist_header.setStretchLastSection(True)

        layout.addWidget(self.history_table, stretch=1)

        self.history_hint_label = QLabel(
            tr("history_hint_double_click"),
            container,
        )
        self.history_hint_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        layout.addWidget(self.history_hint_label)

        return container

    # =========================================================================
    # PÁGINA 3: AJUSTES (CONFIGURAÇÕES EM 2 COLUNAS RESPONSIVAS)
    # =========================================================================

    def _build_settings_page(self) -> QWidget:
        self.settings_scroll_area = QScrollArea(self)
        self.settings_scroll_area.setWidgetResizable(True)
        self.settings_scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.settings_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget(self.settings_scroll_area)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(16)

        grid_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        grid_layout.setSpacing(16)
        self.settings_grid_layout = grid_layout

        # Coluna 1: Contas, Motor de sincronização, Avançado
        col1 = QVBoxLayout()
        col1.setSpacing(16)
        col1.addWidget(self._build_account_status_section())
        col1.addWidget(self._build_engine_section())
        col1.addWidget(self._build_advanced_section())
        col1.addStretch(1)
        grid_layout.addLayout(col1, stretch=1)

        # Coluna 2: Sistema e Sobre
        col2 = QVBoxLayout()
        col2.setSpacing(16)
        col2.addWidget(self._build_preferences_section())
        col2.addWidget(self._build_about_card_section())
        col2.addStretch(1)
        grid_layout.addLayout(col2, stretch=1)

        layout.addLayout(grid_layout)
        layout.addStretch(1)
        self.settings_scroll_area.setWidget(container)
        return self.settings_scroll_area

    def _build_account_status_section(self) -> QFrame:
        card = QFrame(self)
        card.setProperty("class", "brisaCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel(tr("settings_card_accounts"), card)
        title.setProperty("class", "cardTitle")
        self.settings_accounts_title = title
        layout.addWidget(title)

        acc_box = QFrame(card)
        acc_box.setProperty("class", "brisaInnerCard")
        abox_lay = QHBoxLayout(acc_box)
        abox_lay.setContentsMargins(12, 10, 12, 10)
        abox_lay.setSpacing(12)

        drv_ic = QLabel(acc_box)
        drv_ic.setPixmap(render_vector_pixmap("google_drive", 24, "#9189FF"))
        drv_ic.setFixedSize(24, 24)

        abox_text = QVBoxLayout()
        abox_text.setSpacing(2)
        self.account_status_label = QLabel(
            "Conta Google: [NÃO CONECTADA] — Nenhuma conta vinculada.", acc_box
        )
        self.account_status_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.account_status_label.setWordWrap(True)
        abox_text.addWidget(self.account_status_label)

        abox_lay.addWidget(drv_ic)
        abox_lay.addLayout(abox_text, stretch=1)
        layout.addWidget(acc_box)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.connect_google_button = QPushButton(tr("settings_btn_connect"), card)
        self.connect_google_button.setProperty("primary", "true")
        self.connect_google_button.clicked.connect(self._on_connect_google_clicked)

        self.cancel_oauth_button = QPushButton("Cancelar Login", card)
        self.cancel_oauth_button.setEnabled(False)
        self.cancel_oauth_button.setVisible(False)
        self.cancel_oauth_button.clicked.connect(self._on_cancel_oauth_clicked)

        self.disconnect_google_button = QPushButton(tr("settings_btn_disconnect"), card)
        self.disconnect_google_button.setEnabled(False)
        self.disconnect_google_button.setVisible(False)
        self.disconnect_google_button.clicked.connect(self._on_disconnect_google_clicked)

        btn_row.addWidget(self.connect_google_button)
        btn_row.addWidget(self.cancel_oauth_button)
        btn_row.addWidget(self.disconnect_google_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.oauth_security_note_label = QLabel(
            tr("settings_account_security_notice"),
            card,
        )
        self.oauth_security_note_label.setWordWrap(True)
        self.oauth_security_note_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        layout.addWidget(self.oauth_security_note_label)

        return card

    def _build_engine_section(self) -> QFrame:
        card = QFrame(self)
        card.setProperty("class", "brisaCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        title = QLabel(tr("settings_card_engine"), card)
        title.setProperty("class", "cardTitle")
        self.settings_engine_title = title
        layout.addWidget(title)

        box = QFrame(card)
        box.setProperty("class", "brisaInnerCard")
        blay = QVBoxLayout(box)
        blay.setContentsMargins(12, 10, 12, 10)
        blay.setSpacing(6)

        rc_row = QHBoxLayout()
        rc_title = QLabel("rclone", box)
        rc_title.setProperty("class", "overviewItemTitle")
        rc_badge = QLabel("v1.75.2", box)
        rc_badge.setStyleSheet(
            "background-color: rgba(16, 185, 129, 0.15); color: #10B981; "
            "border-radius: 8px; padding: 2px 8px; font-size: 10px; font-weight: 600;"
        )
        rc_row.addWidget(rc_title)
        rc_row.addStretch(1)
        rc_row.addWidget(rc_badge)
        blay.addLayout(rc_row)

        rc_path = QLabel("/usr/lib/brisasync/bin/rclone", box)
        rc_path.setStyleSheet("font-size: 11px; color: #8B949E; font-family: monospace;")
        blay.addWidget(rc_path)

        bs_desc = QLabel(tr("settings_engine_bisync_mode"), box)
        bs_desc.setStyleSheet("font-size: 11px; color: #8B949E;")
        self.settings_engine_mode_lbl = bs_desc
        blay.addWidget(bs_desc)
        layout.addWidget(box)

        self.open_diagnostics_from_settings_btn = QPushButton(tr("settings_btn_diagnostics"), card)
        self.open_diagnostics_from_settings_btn.clicked.connect(self._open_diagnostics_dialog)
        layout.addWidget(self.open_diagnostics_from_settings_btn)

        return card

    def _build_preferences_section(self) -> QFrame:
        card = QFrame(self)
        card.setProperty("class", "brisaCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel(tr("settings_card_system"), card)
        title.setProperty("class", "cardTitle")
        self.settings_system_card_title = title
        layout.addWidget(title)

        # Aparência
        self.settings_theme_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.settings_theme_row.setSpacing(10)
        theme_lbl = QLabel(tr("settings_theme_label"), card)
        theme_lbl.setProperty("class", "settingFieldLabel")
        self.settings_theme_lbl = theme_lbl
        self.theme_mode_combo = QComboBox(card)
        self.theme_mode_combo.setMinimumWidth(160)
        self.theme_mode_combo.setMaximumWidth(240)
        theme_choices = [
            (tr("theme_system"), "system"),
            (tr("theme_light"), "light"),
            (tr("theme_dark"), "dark"),
        ]
        for text, mode in theme_choices:
            self.theme_mode_combo.addItem(text, userData=mode)
        current_theme = self.database.get_theme_preference(default="system")
        t_idx = self.theme_mode_combo.findData(current_theme)
        if t_idx >= 0:
            self.theme_mode_combo.setCurrentIndex(t_idx)
        self.theme_mode_combo.currentIndexChanged.connect(self._on_theme_mode_changed)
        self.settings_theme_row.addWidget(theme_lbl, stretch=1)
        self.settings_theme_row.addWidget(self.theme_mode_combo, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.settings_theme_row)

        # Idioma / Language
        self.settings_lang_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.settings_lang_row.setSpacing(10)
        lang_lbl = QLabel(tr("settings_language_label"), card)
        lang_lbl.setProperty("class", "settingFieldLabel")
        self.settings_lang_lbl = lang_lbl
        self.language_combo = QComboBox(card)
        self.language_combo.setMinimumWidth(180)
        self.language_combo.setMaximumWidth(240)
        self.language_combo.addItem("Português (Brasil)", userData="pt_BR")
        self.language_combo.addItem("English", userData="en")
        current_lang = self.database.get_language_preference(default="pt_BR")
        l_idx = self.language_combo.findData(current_lang)
        if l_idx >= 0:
            self.language_combo.setCurrentIndex(l_idx)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.settings_lang_row.addWidget(lang_lbl, stretch=1)
        self.settings_lang_row.addWidget(self.language_combo, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.settings_lang_row)

        # Intervalo
        self.settings_int_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.settings_int_row.setSpacing(10)
        int_lbl = QLabel(tr("settings_interval_label"), card)
        int_lbl.setProperty("class", "settingFieldLabel")
        int_lbl.setWordWrap(True)
        self.settings_int_lbl = int_lbl
        self.interval_combo = QComboBox(card)
        self.interval_combo.setMinimumWidth(180)
        self.interval_combo.setMaximumWidth(240)
        interval_choices = [
            (tr("interval_1min"), 60),
            (tr("interval_5min"), 300),
            (tr("interval_15min"), 900),
            (tr("interval_30min"), 1800),
            (tr("interval_60min"), 3600),
        ]
        for text, seconds in interval_choices:
            self.interval_combo.addItem(text, userData=seconds)
        self.interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        self.settings_int_row.addWidget(int_lbl, stretch=1)
        self.settings_int_row.addWidget(self.interval_combo, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.settings_int_row)

        # Tema da bandeja
        self.settings_tray_row = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.settings_tray_row.setSpacing(10)
        tray_lbl = QLabel(tr("settings_tray_label"), card)
        tray_lbl.setProperty("class", "settingFieldLabel")
        tray_lbl.setWordWrap(True)
        self.settings_tray_lbl = tray_lbl
        self.tray_mode_combo = QComboBox(card)
        self.tray_mode_combo.setMinimumWidth(220)
        self.tray_mode_combo.setMaximumWidth(270)
        tray_choices = [
            (tr("tray_auto"), "auto"),
            (tr("tray_light"), "dark_panel"),
            (tr("tray_dark"), "light_panel"),
        ]
        for text, mode in tray_choices:
            self.tray_mode_combo.addItem(text, userData=mode)
        self.tray_mode_combo.currentIndexChanged.connect(self._on_tray_mode_changed)
        self.settings_tray_row.addWidget(tray_lbl, stretch=1)
        self.settings_tray_row.addWidget(self.tray_mode_combo, stretch=0, alignment=Qt.AlignmentFlag.AlignRight)
        layout.addLayout(self.settings_tray_row)

        # Checkboxes
        self.autostart_checkbox = QCheckBox(tr("settings_autostart_checkbox"), card)
        self.autostart_checkbox.toggled.connect(self._on_autostart_toggled)

        self.notifications_checkbox = QCheckBox(tr("settings_notifications_checkbox"), card)
        self.notifications_checkbox.toggled.connect(self._on_notifications_toggled)

        layout.addWidget(self.autostart_checkbox)
        layout.addWidget(self.notifications_checkbox)

        # Ciclo de vida
        self.lifecycle_notice_label = QLabel(card)
        self.lifecycle_notice_label.setWordWrap(True)
        self.lifecycle_notice_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        self._update_lifecycle_notice_text()
        layout.addWidget(self.lifecycle_notice_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.exit_app_button = QPushButton(tr("settings_btn_exit"), card)
        self.exit_app_button.setAccessibleName("Abrir diálogo para sair do BrisaSync")
        self.exit_app_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_app_button.clicked.connect(self.open_exit_dialog)
        btn_row.addWidget(self.exit_app_button)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.quit_ui_keep_service_button = QPushButton("Encerrar Interface (Manter Serviço)", card)
        self.quit_ui_keep_service_button.clicked.connect(self.quit_graphical_component_keep_service)
        self.quit_ui_keep_service_button.setVisible(False)

        self.shutdown_service_button = QPushButton("Encerrar Serviço", card)
        self.shutdown_service_button.clicked.connect(self._on_shutdown_service_clicked)
        self.shutdown_service_button.setVisible(False)

        return card

    def _build_advanced_section(self) -> QWidget:
        wrapper = QWidget(self)
        vbox = QVBoxLayout(wrapper)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(6)

        self.advanced_toggle_btn = QPushButton(f"▶ {tr('settings_card_advanced')}", wrapper)
        self.advanced_toggle_btn.setFlat(True)
        self.advanced_toggle_btn.setStyleSheet("text-align: left; font-weight: bold; padding: 4px 0px; color: #9189FF;")
        self.advanced_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.advanced_toggle_btn.clicked.connect(self._toggle_advanced_section)
        vbox.addWidget(self.advanced_toggle_btn)

        self.advanced_container = QFrame(wrapper)
        self.advanced_container.setProperty("class", "brisaCard")
        self.advanced_container.setVisible(False)
        adv_layout = QVBoxLayout(self.advanced_container)
        adv_layout.setContentsMargins(18, 16, 18, 16)
        adv_layout.setSpacing(10)

        json_row = QHBoxLayout()
        json_row.setSpacing(8)
        client_label = QLabel("Cliente &OAuth JSON (opcional):", self.advanced_container)
        self.oauth_client_path_input = QLineEdit(self.advanced_container)
        self.oauth_client_path_input.setPlaceholderText(
            f"Automático na distribuição oficial (ou {default_oauth_client_config_path()})"
        )
        client_label.setBuddy(self.oauth_client_path_input)

        self.browse_oauth_client_button = QPushButton("Selecionar JSON...", self.advanced_container)
        self.browse_oauth_client_button.clicked.connect(self._on_browse_oauth_client_json)

        json_row.addWidget(client_label)
        json_row.addWidget(self.oauth_client_path_input, stretch=1)
        json_row.addWidget(self.browse_oauth_client_button)
        adv_layout.addLayout(json_row)

        self.oauth_client_origin_label = QLabel(self.advanced_container)
        self.oauth_client_origin_label.setStyleSheet("color: #8B949E; font-size: 11px;")
        adv_layout.addWidget(self.oauth_client_origin_label)

        self.debug_info_label = QLabel(
            f"Banco SQLite: {self.database.db_path} | Socket IPC: {self.ipc_client.socket_path}",
            self.advanced_container,
        )
        self.debug_info_label.setWordWrap(True)
        self.debug_info_label.setStyleSheet("color: #8B949E; font-size: 10px; font-family: monospace;")
        adv_layout.addWidget(self.debug_info_label)

        vbox.addWidget(self.advanced_container)
        return wrapper

    def _build_about_card_section(self) -> QFrame:
        card = QFrame(self)
        card.setProperty("class", "brisaCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        self.settings_about_title = QLabel(tr("settings_card_about"), card)
        self.settings_about_title.setProperty("class", "cardTitle")
        layout.addWidget(self.settings_about_title)

        box = QFrame(card)
        box.setProperty("class", "brisaInnerCard")
        blay = QVBoxLayout(box)
        blay.setContentsMargins(12, 10, 12, 10)
        blay.setSpacing(4)

        v_lbl = QLabel(f"{__app_name__} v{__version__}", box)
        v_lbl.setProperty("class", "overviewItemTitle")
        self.settings_about_sub_lbl = QLabel(tr("about_headline"), box)
        self.settings_about_sub_lbl.setWordWrap(True)
        self.settings_about_sub_lbl.setProperty("class", "overviewItemSub")
        self.settings_about_lic_lbl = QLabel(tr("settings_about_license"), box)
        self.settings_about_lic_lbl.setWordWrap(True)
        self.settings_about_lic_lbl.setProperty("class", "overviewItemMuted")

        blay.addWidget(v_lbl)
        blay.addWidget(self.settings_about_sub_lbl)
        blay.addWidget(self.settings_about_lic_lbl)
        layout.addWidget(box)

        self.open_about_dlg_btn = QPushButton(tr("settings_btn_open_about"), card)
        self.open_about_dlg_btn.clicked.connect(self._open_about_dialog)
        layout.addWidget(self.open_about_dlg_btn)

        return card

    def _toggle_advanced_section(self) -> None:
        is_visible = self.advanced_container.isVisible()
        self.advanced_container.setVisible(not is_visible)
        prefix = "▼ " if not is_visible else "▶ "
        self.advanced_toggle_btn.setText(f"{prefix}{tr('settings_card_advanced')}")

    def _on_disconnect_google_clicked(self) -> None:
        self.disconnect_google_account(prompt_confirmation=True)

    def disconnect_google_account(self, *, prompt_confirmation: bool = False) -> None:
        if prompt_confirmation and not getattr(self, "_suppress_dialogs_for_testing", False):
            reply = QMessageBox.question(
                self,
                "Desconectar Conta Google",
                "Tem certeza que deseja desconectar sua conta Google?\n\n"
                "Seus arquivos sincronizados permanecerão intactos neste computador e no Google Drive. "
                "A sincronização em segundo plano será interrompida até que você conecte uma conta novamente.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 1. Se ciclo estiver ativo, solicita parada e aguarda conclusão graciosa
        is_active = False
        if hasattr(self, "_last_snapshot") and self._last_snapshot and self._last_snapshot.is_cycle_active:
            is_active = True
        else:
            try:
                st = self.ipc_client.get_status()
                is_active = bool(st and st.is_cycle_active)
            except Exception:
                is_active = False

        if is_active:
            try:
                self.ipc_client.execute_command("stop_current")
            except Exception:
                pass
            import time
            for _ in range(25):  # até 2.5s
                time.sleep(0.1)
                try:
                    st = self.ipc_client.get_status()
                    if not st or not st.is_cycle_active:
                        break
                except Exception:
                    break

        # 2. Informa o daemon sobre a desconexão voluntária
        try:
            self.ipc_client.execute_command("disconnect_account")
        except Exception:
            pass

        # 3. Marca desconexão voluntária e apaga credenciais/configurações
        self.database.set_voluntary_disconnect(True)
        self.credential_store.delete_credentials()
        self.bridge.remove_encrypted_config()
        self._last_snapshot = None

        # 4. Atualiza estado e interface
        self._refresh_account_state_from_vault()
        self._update_home_view()
        self._update_folder_status_pills(None)
        self._update_sync_target_preview()
        if hasattr(self, "tray_controller"):
            self.tray_controller.update_from_snapshot(None)
        self.refresh_service_status_from_ipc()
        self.statusBar().showMessage(tr("tray_status_header_no_account"), 4000)

    def _format_elided_path(self, text: str, max_chars: int = 50) -> str:
        if len(text) <= max_chars:
            return text
        half = (max_chars - 3) // 2
        return f"{text[:half]}...{text[-half:]}"

    def _update_home_view(self) -> None:
        state, creds, detail = self._get_account_operational_state()
        account_email = creds.account_email if (creds and creds.account_email) else ""
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        has_folders = bool(local_cfg and remote_cfg)
        is_voluntary = self.database.is_voluntary_disconnect()
        service_pair_ready = bool(
            hasattr(self, "_last_snapshot")
            and self._last_snapshot is not None
            and self._last_snapshot.configured_pair_ready
        )
        is_configured = (state == "READY" or service_pair_ready) and not is_voluntary and has_folders

        # 1. Badge do cabeçalho
        max_email_chars = 15 if getattr(self, "_is_narrow_mode", False) else 22
        if is_voluntary or not self._has_usable_account():
            if state == "VAULT_LOCKED":
                self.header_account_badge.setText(tr("header_vault_locked"))
                self.header_account_badge.setToolTip(detail)
                self.header_account_badge.setStyleSheet("color: #EF4444; font-weight: bold;")
            else:
                self.header_account_badge.setText(tr("header_not_connected"))
                self.header_account_badge.setToolTip(tr("header_no_account_linked"))
                self.header_account_badge.setStyleSheet("color: #8B949E;")
        elif state == "READY" and account_email:
            elided = _format_elided_email(account_email, max_email_chars)
            self.header_account_badge.setText(f"● {elided}")
            self.header_account_badge.setToolTip(f"Conta conectada: {account_email}")
            self.header_account_badge.setStyleSheet("color: #9189FF; font-weight: bold;")
        elif state == "CONFIG_PENDING" and account_email:
            elided = _format_elided_email(account_email, max_email_chars)
            self.header_account_badge.setText(f"○ {elided} {tr('header_account_pending_suffix')}")
            self.header_account_badge.setToolTip(
                f"Credenciais salvas no cofre ({account_email}), mas configuração do rclone pendente de conclusão."
            )
            self.header_account_badge.setStyleSheet("color: #F59E0B; font-weight: bold;")
        else:
            self.header_account_badge.setText(tr("header_not_connected"))
            self.header_account_badge.setToolTip(tr("header_no_account_linked"))
            self.header_account_badge.setStyleSheet("color: #8B949E;")

        # 2. Alternância entre visão de uso diário e assistente de primeira configuração
        is_locked = (state == "VAULT_LOCKED") or (
            hasattr(self, "_last_snapshot")
            and self._last_snapshot is not None
            and self._last_snapshot.attention_category == ATTENTION_VAULT_LOCKED
        )
        show_configured_view = is_configured or has_folders
        self.home_configured_container.setVisible(show_configured_view)
        self.home_unconfigured_container.setVisible(not show_configured_view)

        if is_locked:
            self.hero_banner.setProperty("heroState", "attention")
            self.hero_icon_label.setPixmap(render_vector_pixmap("alert", 36, "#FFFFFF"))
            self.hero_title_label.setText(tr("hero_vault_locked_title"))
            self.hero_subtitle_label.setText(tr("hero_vault_locked_subtitle"))
            self.hero_pause_btn.setText(tr("hero_btn_unlock"))
            self.hero_pause_btn.setIcon(get_vector_icon("lock", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("pill_vault_locked"))
            self.global_status_pill.setProperty("class", "statusPill statusPillAttention")
            self.overview_idle_box.setVisible(False)
            self.attention_banner_frame.setVisible(True)
            self.overview_operation_header.setText(tr("overview_header_attention_pending"))
            self.attention_explanation_label.setText(
                "[VAULT_LOCKED] Cofre bloqueado: O chaveiro da sessão está bloqueado. "
                "Desbloqueie o chaveiro para retomar a sincronização."
            )
        elif is_voluntary or state == "NOT_CONNECTED":
            self.hero_banner.setProperty("heroState", "unconfigured")
            self.hero_icon_label.setPixmap(render_vector_pixmap("folder", 36, "#9189FF"))
            self.hero_title_label.setText(tr("hero_title_no_account"))
            self.hero_subtitle_label.setText(tr("hero_subtitle_no_account"))
            self.hero_pause_btn.setText(tr("hero_btn_help"))
            self.hero_pause_btn.setIcon(get_vector_icon("info", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("folder_status_waiting_account") if has_folders else tr("pill_unconfigured"))
            self.global_status_pill.setProperty("class", "statusPill")
            self.attention_banner_frame.setVisible(False)
            self.overview_idle_box.setVisible(True)
            self.overview_operation_header.setText(tr("folder_status_waiting_account") if has_folders else tr("overview_header_idle"))
        elif not is_configured:
            self.hero_banner.setProperty("heroState", "unconfigured")
            self.hero_icon_label.setPixmap(render_vector_pixmap("folder", 36, "#9189FF"))
            self.hero_title_label.setText(tr("hero_welcome_title"))
            if state == "CONFIG_PENDING":
                self.hero_subtitle_label.setText(tr("hero_config_pending_subtitle"))
                self.global_status_pill.setText(tr("pill_config_pending"))
            else:
                self.hero_subtitle_label.setText(tr("hero_unconfigured_subtitle"))
                self.global_status_pill.setText(tr("pill_unconfigured"))
            self.hero_pause_btn.setText(tr("hero_btn_help"))
            self.hero_pause_btn.setIcon(get_vector_icon("info", 14, "#FFFFFF"))
            self.global_status_pill.setProperty("class", "statusPill")

        self._update_hero_primary_button(self._last_snapshot)

        has_client, client_desc = OAuthClientConfig.get_active_client_source(
            explicit_path=self.oauth_client_path_input.text().strip() or None
        )
        self.oauth_client_origin_label.setText(f"{tr('settings_oauth_desktop_metadata')}: {client_desc}")

        if show_configured_view and local_cfg is not None and remote_cfg is not None:
            loc_str = local_cfg.folder_path
            self.home_local_folder_display.setText(self._format_elided_path(loc_str, 46))
            self.home_local_folder_display.setToolTip(f"Pasta local:\n{loc_str}")

            rem_name = remote_cfg.folder_name or "Pasta Remota"
            self.home_remote_folder_display.setText(f"{rem_name}")
            self.home_remote_folder_display.setToolTip(
                f"Pasta remota no Google Drive:\n{rem_name}\n(ID imutável: {remote_cfg.folder_id})"
            )

            # Atualiza cards da Visão Geral e da página Pastas
            self.folders_card_title_label.setText(rem_name)
            has_usable = self._has_usable_account()
            if has_usable:
                self.overview_account_email_label.setText(account_email or tr("header_account_connected"))
                self.overview_account_status_label.setText(f"● {tr('folder_status_connected')}")
                self.overview_account_status_label.setStyleSheet("color: #10B981; font-weight: 600; font-size: 11px;")
                self.folders_card_subtitle_label.setText(f"{account_email} ↔ {loc_str}" if account_email else f"{loc_str}")
                self.folders_card_subtitle_label.setToolTip(f"{account_email}\n↔\n{loc_str}" if account_email else loc_str)
                if hasattr(self, "sidebar_folders_item"):
                    self.sidebar_folders_item.setBadgeCount(1)
                self.sidebar_folders_badge.setVisible(True)
                self.hero_metric_folders_val.setText(tr("hero_stat_folders_ratio", active=1, total=1))

                self.folders_page_open_btn.setVisible(True)
                self.folders_page_open_btn.setEnabled(True)
                self.folders_remove_pair_btn.setVisible(True)
                self.folders_remove_pair_btn.setEnabled(True)
                self.folders_page_sync_btn.setVisible(True)
                self.folders_page_sync_btn.setEnabled(True)
                self.folders_page_sync_btn.setToolTip("")
                self.folders_connect_account_btn.setVisible(False)
                self.list_remote_folders_button.setEnabled(True)
                self.create_remote_folder_button.setEnabled(True)
                self.remote_folder_combo.setEnabled(True)
                if hasattr(self, "save_folder_button"):
                    self.save_folder_button.setEnabled(True)
                    self.save_folder_button.setToolTip("")
            else:
                self.overview_account_email_label.setText(tr("menu_no_account"))
                self.overview_account_status_label.setText(tr("folder_status_not_connected"))
                self.overview_account_status_label.setStyleSheet("color: #8B949E; font-weight: 600; font-size: 11px;")
                self.folders_card_subtitle_label.setText(f"({tr('menu_no_account')}) ↔ {loc_str}")
                self.folders_card_subtitle_label.setToolTip(f"({tr('menu_no_account')})\n↔\n{loc_str}")
                if hasattr(self, "sidebar_folders_item"):
                    self.sidebar_folders_item.setBadgeCount(None)
                self.sidebar_folders_badge.setVisible(False)
                self.hero_metric_folders_val.setText(tr("hero_stat_folders_ratio", active=0, total=1))

                # Com par salvo, mas sem conta conectada: mantém abrir pasta local e remover vínculo disponíveis
                self.folders_page_open_btn.setVisible(True)
                self.folders_page_open_btn.setEnabled(True)
                self.folders_remove_pair_btn.setVisible(True)
                self.folders_remove_pair_btn.setEnabled(True)
                self.folders_page_sync_btn.setVisible(True)
                self.folders_page_sync_btn.setEnabled(False)
                self.folders_page_sync_btn.setToolTip(tr("sync_blocked_no_account"))
                self.folders_connect_account_btn.setVisible(True)
                self.folders_connect_account_btn.setEnabled(True)
                self.list_remote_folders_button.setEnabled(False)
                self.create_remote_folder_button.setEnabled(False)
                self.remote_folder_combo.setEnabled(False)
                if hasattr(self, "save_folder_button"):
                    self.save_folder_button.setEnabled(False)
                    self.save_folder_button.setToolTip(tr("sync_blocked_no_account"))

            self._update_folder_status_pills(self._last_snapshot)
        else:
            has_usable = self._has_usable_account()
            if hasattr(self, "save_folder_button"):
                self.save_folder_button.setEnabled(has_usable)
                self.save_folder_button.setToolTip("" if has_usable else tr("sync_blocked_no_account"))

            if account_email:
                self.overview_account_email_label.setText(account_email)
                self.overview_account_status_label.setText(f"● {tr('folder_status_connected')}" if state == "READY" else f"○ {tr('folder_status_pending')}")
                st_color = "#10B981" if state == "READY" else "#F59E0B"
                self.overview_account_status_label.setStyleSheet(f"color: {st_color}; font-weight: 600; font-size: 11px;")
            else:
                self.overview_account_email_label.setText(tr("menu_no_account"))
                self.overview_account_status_label.setText(tr("folder_status_not_connected"))
                self.overview_account_status_label.setStyleSheet("color: #8B949E; font-weight: 600; font-size: 11px;")

            if local_cfg is not None and remote_cfg is None:
                loc_str = local_cfg.folder_path
                pending_title = "Configuração pendente" if get_current_language() == "pt_BR" else "Configuration pending"
                self.overview_folder_name_label.setText(pending_title)
                self.overview_folder_path_label.setText(f"{self._format_elided_path(loc_str, 30)} (Falta pasta remota)")
                self.overview_folder_path_label.setToolTip(f"Pasta local: {loc_str}\n(Pasta remota no Google Drive ainda não definida)")
                self.folders_card_title_label.setText(pending_title)
                self.folders_card_subtitle_label.setText(f"Local: {loc_str} (Falta pasta remota)")
                self.folders_page_open_btn.setVisible(True)
                self.folders_page_open_btn.setEnabled(True)
                self.folders_remove_pair_btn.setVisible(True)
                self.folders_remove_pair_btn.setEnabled(True)
                self.folders_page_sync_btn.setVisible(False)
                self.hero_metric_folders_val.setText(tr("hero_stat_folders_ratio", active=0, total=0))
            elif local_cfg is None and remote_cfg is not None:
                rem_name = remote_cfg.folder_name or "Pasta Remota"
                self.overview_folder_name_label.setText(rem_name)
                self.overview_folder_path_label.setText("Falta selecionar pasta local")
                self.overview_folder_path_label.setToolTip("Pasta local ainda não selecionada")
                self.folders_card_title_label.setText(rem_name)
                self.folders_card_subtitle_label.setText("Falta selecionar pasta local")
                self.folders_page_open_btn.setVisible(False)
                self.folders_remove_pair_btn.setVisible(True)
                self.folders_remove_pair_btn.setEnabled(True)
                self.folders_page_sync_btn.setVisible(False)
                self.hero_metric_folders_val.setText(tr("hero_stat_folders_ratio", active=0, total=0))
            else:
                # Sem par configurado: oculta Abrir Pasta Local e Remover Vínculo
                self.overview_folder_name_label.setText(tr("folders_no_pair_title"))
                self.overview_folder_path_label.setText("Nenhuma pasta sincronizada configurada")
                self.overview_folder_path_label.setToolTip("")
                self.folders_card_title_label.setText(tr("folders_no_pair_title"))
                self.folders_card_subtitle_label.setText(tr("folders_no_pair_subtitle"))
                self.folders_page_open_btn.setVisible(False)
                self.folders_remove_pair_btn.setVisible(False)
                self.folders_page_sync_btn.setVisible(False)
                self.hero_metric_folders_val.setText(tr("hero_stat_folders_ratio", active=0, total=0))

            if not has_usable:
                self.folders_connect_account_btn.setVisible(True)
                self.folders_connect_account_btn.setEnabled(True)
                self.list_remote_folders_button.setEnabled(False)
                self.create_remote_folder_button.setEnabled(False)
                self.remote_folder_combo.setEnabled(False)
                if not remote_cfg:
                    self.remote_folder_feedback_label.setText(tr("folders_remote_connect_prompt"))
            else:
                self.folders_connect_account_btn.setVisible(False)
                self.list_remote_folders_button.setEnabled(True)
                self.create_remote_folder_button.setEnabled(True)
                self.remote_folder_combo.setEnabled(True)

            self._update_folder_status_pills(self._last_snapshot)

            if hasattr(self, "sidebar_folders_item"):
                self.sidebar_folders_item.setBadgeCount(None)
            self.sidebar_folders_badge.setVisible(False)
            if not has_client:
                self.setup_step1_hint.setText(
                    "Cliente OAuth não localizado. Indique seu arquivo JSON de teste em "
                    "Ajustes > Seção Avançada para prosseguir."
                )
                self.setup_step1_hint.setVisible(True)
            else:
                self.setup_step1_hint.setText("")
                self.setup_step1_hint.setVisible(False)

            current_wz_step = self.wizard_stack.currentIndex()
            self._refresh_wizard_step_data(current_wz_step)
            self._update_wizard_progress(current_wz_step)

    def _update_overview_recent_activity(self, runs: list[SyncRunRecord] | None = None) -> None:
        """Popula os itens de atividade recente no card da Visão Geral."""
        if runs is None:
            runs = self.database.list_recent_sync_runs(limit=4)

        while self.overview_recent_list_layout.count() > 0:
            item = self.overview_recent_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not runs:
            empty_lbl = QLabel(tr("overview_recent_empty"), self.overview_recent_list_container)
            empty_lbl.setStyleSheet("color: #8B949E; font-size: 12px; padding: 8px 0px;")
            self.overview_recent_list_layout.addWidget(empty_lbl)
            return

        for r in runs[:4]:
            row_frame = QFrame(self.overview_recent_list_container)
            row_frame.setProperty("class", "brisaInnerCard")
            rlay = QHBoxLayout(row_frame)
            rlay.setContentsMargins(8, 6, 8, 6)
            rlay.setSpacing(10)

            ic = QLabel(row_frame)
            ic_name = "check" if r.status == "SUCCESS" else ("sync" if r.status == "RUNNING" else "alert")
            ic_col = "#10B981" if r.status == "SUCCESS" else ("#60A5FA" if r.status == "RUNNING" else "#F59E0B")
            ic.setPixmap(render_vector_pixmap(ic_name, 16, ic_col))
            ic.setFixedSize(16, 16)

            text_box = QVBoxLayout()
            text_box.setSpacing(1)
            op_t = _format_operation_display(r.operation)
            lbl_title = tr("overview_op_completed", op=op_t) if r.status == "SUCCESS" else op_t
            t_lbl = QLabel(lbl_title, row_frame)
            t_lbl.setProperty("class", "overviewItemTitle")
            dest_t = _format_folders_display(r.path1, r.path2)
            d_lbl = QLabel(tr("overview_folder_up_to_date", target=dest_t), row_frame)
            d_lbl.setStyleSheet("font-size: 11px; color: #8B949E;")
            text_box.addWidget(t_lbl)
            text_box.addWidget(d_lbl)

            rel_time = _format_relative_timestamp(r.finished_at or r.started_at)
            time_lbl = QLabel(rel_time, row_frame)
            time_lbl.setStyleSheet("font-size: 11px; color: #8B949E;")

            rlay.addWidget(ic)
            rlay.addLayout(text_box, stretch=1)
            rlay.addWidget(time_lbl)
            self.overview_recent_list_layout.addWidget(row_frame)

    def _update_lifecycle_notice_text(self) -> None:
        if self.tray_controller.is_available:
            self.lifecycle_notice_label.setText(tr("settings_lifecycle_notice_tray"))
        else:
            self.lifecycle_notice_label.setText(tr("settings_lifecycle_notice_no_tray"))

    def _load_persisted_state(self) -> None:
        saved_oauth_json = self.database.get_setting("oauth_client_json_path")
        if saved_oauth_json:
            self.oauth_client_path_input.setText(saved_oauth_json)
        elif default_oauth_client_config_path().is_file():
            self.oauth_client_path_input.setText(str(default_oauth_client_config_path()))

        self._refresh_account_state_from_vault()

        remote_cfg = self.database.get_remote_sync_folder()
        if remote_cfg:
            self.remote_folder_combo.blockSignals(True)
            self.remote_folder_combo.clear()
            self.remote_folder_combo.addItem(
                f"{remote_cfg.folder_name} [ID: {remote_cfg.folder_id}]",
                userData=(remote_cfg.folder_id, remote_cfg.folder_name),
            )
            self.remote_folder_combo.blockSignals(False)
            self.remote_folder_feedback_label.setText(
                f"Status da pasta remota: [SELECIONADA] {remote_cfg.folder_name} (ID: {remote_cfg.folder_id})"
            )
            self.remote_folder_feedback_label.setStyleSheet("color: #10B981;")

        local_cfg = self.database.get_local_sync_folder()
        if local_cfg:
            self.folder_input.setText(local_cfg.folder_path)
            self.folder_feedback_label.setText(
                f"Status da pasta: [OK — CONFIGURADA E ACESSÍVEL] {local_cfg.folder_path}"
            )
            self.folder_feedback_label.setStyleSheet("color: #10B981;")

        interval = self.database.get_sync_interval_seconds()
        self._select_interval_in_combo(interval)

        tray_mode = self.database.get_tray_icon_theme_mode(default="auto")
        self._select_tray_mode_in_combo(tray_mode)

        autostart_on = self.autostart_manager.is_enabled()
        self.autostart_checkbox.blockSignals(True)
        self.autostart_checkbox.setChecked(autostart_on)
        self.autostart_checkbox.blockSignals(False)

        notif_on = self.database.get_setting("notifications_enabled")
        self.notifications_checkbox.blockSignals(True)
        self.notifications_checkbox.setChecked(
            True if notif_on is None else (notif_on.lower() in ("1", "true"))
        )
        self.notifications_checkbox.blockSignals(False)

    def _refresh_account_state_from_vault(self, *, force_refresh: bool = False) -> None:
        state, creds, detail = self._get_account_operational_state(force_refresh=force_refresh)

        if state == "VAULT_LOCKED":
            self.account_status_label.setText(
                tr("settings_acc_vault_locked", detail=detail)
            )
            self.account_status_label.setStyleSheet("color: #EF4444; font-weight: bold;")
            self.connect_google_button.setEnabled(True)
            self.connect_google_button.setText(tr("settings_btn_unlock_vault"))
            self.connect_google_button.setVisible(True)
            self.disconnect_google_button.setEnabled(False)
            self.disconnect_google_button.setVisible(False)
            return

        if state == "CONFIG_PENDING" and creds:
            self.account_status_label.setText(
                tr("settings_acc_config_pending", email=creds.account_email)
            )
            self.account_status_label.setStyleSheet("color: #F59E0B; font-weight: bold;")
            self.connect_google_button.setEnabled(True)
            self.connect_google_button.setText(tr("settings_btn_complete_setup"))
            self.disconnect_google_button.setEnabled(True)
            self.disconnect_google_button.setVisible(True)
            return

        if state == "READY" and creds:
            self.account_status_label.setText(
                tr("settings_acc_connected", email=creds.account_email)
            )
            self.account_status_label.setStyleSheet("color: #10B981; font-weight: bold;")
            self.connect_google_button.setEnabled(True)
            self.connect_google_button.setText(tr("settings_btn_reconnect"))
            self.disconnect_google_button.setEnabled(True)
            self.disconnect_google_button.setVisible(True)
            return

        self.account_status_label.setText(
            tr("settings_acc_not_connected")
        )
        self.account_status_label.setStyleSheet("color: #8B949E;")
        self.connect_google_button.setEnabled(True)
        self.connect_google_button.setText(tr("settings_btn_connect"))
        self.disconnect_google_button.setEnabled(False)
        self.disconnect_google_button.setVisible(False)

    def _update_sync_target_preview(self) -> None:
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()

        if local_cfg and remote_cfg:
            rem_name = remote_cfg.folder_name or "Pasta Remota"
            loc_path = local_cfg.folder_path

            if not self._has_usable_account():
                self.sync_target_preview_label.setText(
                    tr("folders_status_waiting_connection", local=loc_path, remote=rem_name)
                )
                self.sync_target_preview_label.setStyleSheet("color: #F59E0B;")
            else:
                self.sync_target_preview_label.setText(
                    f"Conferência pré-execução: [PRONTO] {loc_path} = "
                    f"Google Drive: {rem_name} [ID: {remote_cfg.folder_id}] | "
                    "Modo: Reconciliação bidirecional incremental"
                )
                self.sync_target_preview_label.setStyleSheet("color: #10B981;")
        else:
            missing: list[str] = []
            if not remote_cfg:
                missing.append("pasta remota no Drive")
            if not local_cfg:
                missing.append("pasta local")
            self.sync_target_preview_label.setText(
                f"Conferência pré-execução: [PENDENTE] Falta configurar: {', '.join(missing)}."
            )
            self.sync_target_preview_label.setStyleSheet("color: #F59E0B;")

    def _sync_path_feedback_labels(self) -> None:
        """Sincroniza os rótulos de feedback dos caminhos distinguindo par ativo salvo e tentativas não superadas."""
        if not hasattr(self, "folder_feedback_label") or not hasattr(self, "remote_folder_feedback_label"):
            return

        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()

        # 1. Feedback da Pasta Local
        if self._pending_local_rejection is not None:
            rejection_target = self._pending_local_rejection.get("target_path", "")
            if local_cfg is not None and local_cfg.folder_path != rejection_target:
                self._pending_local_rejection = None
                self.folder_feedback_label.setText(
                    f"Status da pasta: [OK — CONFIGURADA E ACESSÍVEL] {local_cfg.folder_path}"
                )
                self.folder_feedback_label.setStyleSheet("color: #10B981;")
            else:
                err_msg = self._pending_local_rejection.get("error_msg", "")
                self.folder_feedback_label.setText(err_msg)
                self.folder_feedback_label.setStyleSheet("color: #EF4444;")
        else:
            if local_cfg is not None:
                self.folder_feedback_label.setText(
                    f"Status da pasta: [OK — CONFIGURADA E ACESSÍVEL] {local_cfg.folder_path}"
                )
                self.folder_feedback_label.setStyleSheet("color: #10B981;")
            else:
                self.folder_feedback_label.setText(
                    "Status da pasta: [NÃO CONFIGURADA] — Nenhuma pasta local selecionada."
                )
                self.folder_feedback_label.setStyleSheet("color: #8B949E; font-size: 11px;")

        # 2. Feedback da Pasta Remota
        if self._pending_remote_rejection is not None:
            target_id = self._pending_remote_rejection.get("target_folder_id", "")
            tested_local = self._pending_remote_rejection.get("local_path_tested", "")

            is_overcome = False
            if remote_cfg is not None and local_cfg is not None:
                if remote_cfg.folder_id == target_id:
                    is_init = self.database.is_baseline_initialized(
                        local_folder=local_cfg.folder_path,
                        remote_folder_id=remote_cfg.folder_id,
                    )
                    if is_init:
                        is_overcome = True
                    else:
                        lp = Path(local_cfg.folder_path).expanduser()
                        if lp.is_dir() and not list(lp.iterdir()):
                            is_overcome = True
                        elif local_cfg.folder_path != tested_local:
                            is_overcome = True

            if is_overcome:
                self._pending_remote_rejection = None
                self.remote_folder_feedback_label.setText(
                    f"Status da pasta remota: [SELECIONADA] {remote_cfg.folder_name} (ID: {remote_cfg.folder_id})"
                )
                self.remote_folder_feedback_label.setStyleSheet("color: #10B981;")
            else:
                err_msg = self._pending_remote_rejection.get("error_msg", "")
                self.remote_folder_feedback_label.setText(err_msg)
                self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
        else:
            if remote_cfg is not None:
                self.remote_folder_feedback_label.setText(
                    f"Status da pasta remota: [SELECIONADA] {remote_cfg.folder_name} (ID: {remote_cfg.folder_id})"
                )
                self.remote_folder_feedback_label.setStyleSheet("color: #10B981;")
            else:
                state, creds, _ = self._get_account_operational_state()
                is_vol = self.database.is_voluntary_disconnect()
                has_acc = (state != "NOT_CONNECTED") and not is_vol and bool(creds and creds.access_token)
                if not has_acc:
                    self.remote_folder_feedback_label.setText(
                        f"Status da pasta remota: [NÃO SELECIONADA] — {tr('folders_remote_connect_prompt')}"
                    )
                else:
                    self.remote_folder_feedback_label.setText(
                        "Status da pasta remota: [NÃO SELECIONADA] — Selecione ou liste as pastas do Drive."
                    )
                self.remote_folder_feedback_label.setStyleSheet("color: #8B949E; font-size: 11px;")

    def _refresh_last_updated_label(self, last_confirmed: str | None) -> None:
        if last_confirmed:
            try:
                dt = datetime.fromisoformat(last_confirmed.replace("Z", "+00:00"))
                local_dt = dt.astimezone()
                human_date = local_dt.strftime("%d/%m/%Y às %H:%M:%S")
                self.last_updated_label.setText(
                    f"Última sincronização concluída: {human_date}"
                )
            except Exception:
                self.last_updated_label.setText(
                    f"Última sincronização concluída: {last_confirmed}"
                )
        else:
            self.last_updated_label.setText(
                "Nenhuma sincronização completa confirmada ainda."
            )

    def _update_home_state_display(self, state: str, detail: str = "") -> None:
        last_sync = self.database.get_last_confirmed_sync_at()
        if state == STATE_WAITING:
            if last_sync:
                self.home_main_state_label.setText("✓ Tudo atualizado")
                self.home_main_state_label.setStyleSheet("color: #10B981; font-weight: bold;")
            else:
                self.home_main_state_label.setText("● Aguardando primeira sincronização")
                fg_col = "#F0F4F8" if is_dark_mode() else "#0F172A"
                self.home_main_state_label.setStyleSheet(f"color: {fg_col}; font-weight: bold;")
        elif state in (STATE_SYNCING, STATE_VERIFYING):
            self.home_main_state_label.setText("🔄 Sincronizando arquivos...")
            self.home_main_state_label.setStyleSheet("color: #60A5FA; font-weight: bold;")
        elif state == STATE_PAUSING:
            self.home_main_state_label.setText("⏳ Pausando sincronização...")
            self.home_main_state_label.setStyleSheet("color: #F59E0B; font-weight: bold;")
        elif state == STATE_PAUSED:
            self.home_main_state_label.setText("⏸ Sincronização pausada")
            self.home_main_state_label.setStyleSheet("color: #F59E0B; font-weight: bold;")
        elif state == STATE_ATTENTION_REQUIRED:
            self.home_main_state_label.setText("⚠ Atenção necessária")
            self.home_main_state_label.setStyleSheet("color: #EF4444; font-weight: bold;")
        elif state == STATE_OFFLINE:
            self.home_main_state_label.setText("⏳ Sem conexão (aguardando rede)...")
            self.home_main_state_label.setStyleSheet("color: #F59E0B; font-weight: bold;")
        else:
            self.home_main_state_label.setText(f"● {detail or state}")
            self.home_main_state_label.setStyleSheet("")

    def refresh_service_status_from_ipc(self) -> ServiceStatusSnapshot | None:
        try:
            snapshot = self.ipc_client.get_status()
            self._apply_service_snapshot(snapshot)
            return snapshot
        except ServiceUnavailableError:
            is_paused = self.database.is_auto_sync_paused()
            state_txt = (
                STATE_LABELS[STATE_PAUSED]
                if is_paused
                else STATE_LABELS[STATE_WAITING]
            )
            self.sync_status_label.setText(
                f"Estado do Serviço: [{state_txt}] — Serviço em segundo plano parado "
                "(será iniciado automaticamente ao acionar 'Sincronizar Agora' ou 'Retomar')."
            )
            self._update_home_state_display(
                STATE_PAUSED if is_paused else STATE_WAITING,
                "Serviço em segundo plano parado",
            )
            self.stop_current_button.setVisible(False)
            self.stop_current_button.setEnabled(False)
            self.shutdown_service_button.setEnabled(False)
            self.pause_sync_button.setVisible(not is_paused)
            self.pause_sync_button.setEnabled(not is_paused)
            self.resume_sync_button.setVisible(is_paused)
            self.resume_sync_button.setEnabled(is_paused)
            self._refresh_last_updated_label(self.database.get_last_confirmed_sync_at())
            self.tray_controller.update_from_snapshot(None)
            self._update_home_view()
            return None
        except Exception:
            return None

    def ensure_background_service_started(
        self,
        startup_timeout: float = 6.0,
    ) -> ServiceStatusSnapshot | None:
        try:
            snapshot = self.ipc_client.ensure_service_running(startup_timeout=startup_timeout)
            self._apply_service_snapshot(snapshot)
            return snapshot
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "Falha ao inicializar o serviço da sessão em segundo plano: %s", exc
            )
            self.refresh_service_status_from_ipc()
            return None

    def _update_hero_primary_button(
        self, snapshot: ServiceStatusSnapshot | None = None
    ) -> None:
        """Centraliza a atualização de rótulo, ícone, ação e habilitação do botão principal do Hero."""
        if not hasattr(self, "hero_sync_now_btn") or self.hero_sync_now_btn is None:
            return

        snap = snapshot or self._last_snapshot
        state, _, _ = self._get_account_operational_state()
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        is_locked = (state == "VAULT_LOCKED") or (
            snap is not None and snap.attention_category == ATTENTION_VAULT_LOCKED
        )

        if is_locked:
            self._stop_hero_sync_animation()
            self.hero_sync_now_btn.setText(tr("hero_btn_unlock_vault"))
            self.hero_sync_now_btn.setToolTip(
                "Cofre de credenciais bloqueado. Clique para desbloquear o chaveiro da sessão."
            )
            self.hero_sync_now_btn.setIcon(
                get_vector_icon("lock", 16, "#0B0F15")
            )
            self.hero_sync_now_btn.setEnabled(True)
            self.hero_sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            return

        configured_pair_ready = snap.configured_pair_ready if snap else False
        is_configured = (
            (state == "READY" or configured_pair_ready)
            and not self.database.is_voluntary_disconnect()
            and bool(local_cfg and remote_cfg)
        )

        if not is_configured:
            self._stop_hero_sync_animation()
            if state == "CONFIG_PENDING":
                self.hero_sync_now_btn.setText(tr("hero_btn_complete_setup"))
                self.hero_sync_now_btn.setToolTip(
                    "Credenciais salvas no cofre. Conclua a conexão para iniciar."
                )
            else:
                self.hero_sync_now_btn.setText(tr("hero_btn_connect_account_action"))
                self.hero_sync_now_btn.setToolTip(
                    tr("sync_blocked_no_account")
                )
            self.hero_sync_now_btn.setIcon(
                get_vector_icon("google_drive", 16, "#0B0F15")
            )
            self.hero_sync_now_btn.setEnabled(True)
            self.hero_sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            return

        # Conta e par de pastas devidamente configurados
        is_active = snap is not None and (
            snap.is_cycle_active
            or snap.state in (STATE_SYNCING, STATE_VERIFYING)
        )
        if is_active:
            self.hero_sync_now_btn.setText(tr("hero_syncing_title"))
            self.hero_sync_now_btn.setToolTip(
                "Sincronização bidirecional em andamento..."
            )
            self.hero_sync_now_btn.setEnabled(False)
            self.hero_sync_now_btn.setCursor(Qt.CursorShape.ArrowCursor)
            self._start_hero_sync_animation()
        else:
            self._stop_hero_sync_animation()
            self.hero_sync_now_btn.setText(tr("hero_btn_sync_now"))
            self.hero_sync_now_btn.setIcon(
                get_vector_icon("sync", 16, "#0B0F15")
            )
            self.hero_sync_now_btn.setToolTip(
                "Executar reconciliação e sincronização bidirecional imediatamente."
            )
            self.hero_sync_now_btn.setEnabled(True)
            self.hero_sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _start_hero_sync_animation(self) -> None:
        """Inicia ou retoma a rotação discreta do ícone no botão principal durante sincronização ativa."""
        if not hasattr(self, "hero_sync_now_btn") or self.hero_sync_now_btn is None:
            return
        if not hasattr(self, "_hero_anim_timer"):
            return
        self.hero_sync_now_btn.setIcon(
            render_rotated_sync_icon(16, "#0B0F15", self._hero_sync_angle)
        )
        if self.isVisible() and not self._hero_anim_timer.isActive():
            self._hero_anim_timer.start(40)

    def _stop_hero_sync_animation(self) -> None:
        """Interrompe a animação do botão principal e restaura o ângulo para a posição inicial."""
        if hasattr(self, "_hero_anim_timer") and self._hero_anim_timer.isActive():
            self._hero_anim_timer.stop()
        self._hero_sync_angle = 0.0

    def _on_hero_anim_tick(self) -> None:
        """Avança a rotação suave das setas de sincronização a cada quadro (25 FPS)."""
        if not hasattr(self, "hero_sync_now_btn") or self.hero_sync_now_btn is None:
            return
        if not self.isVisible():
            if hasattr(self, "_hero_anim_timer") and self._hero_anim_timer.isActive():
                self._hero_anim_timer.stop()
            return
        self._hero_sync_angle = (self._hero_sync_angle + 12.0) % 360.0
        self.hero_sync_now_btn.setIcon(
            render_rotated_sync_icon(16, "#0B0F15", self._hero_sync_angle)
        )

    def _apply_service_snapshot(self, snapshot: ServiceStatusSnapshot) -> None:
        self._last_snapshot = snapshot

        pid_suffix = f" (PID Serviço: {snapshot.service_pid})" if snapshot.service_pid else ""
        self.sync_status_label.setText(
            f"Estado do Serviço: [{snapshot.state_label}] — {snapshot.detail_message}{pid_suffix}"
        )
        self.sync_status_label.setToolTip(
            f"PID Serviço: {snapshot.service_pid}\n"
            f"PID rclone: {snapshot.active_rclone_pid or 'inativo'}\n"
            f"Ciclo ativo: {'Sim' if snapshot.is_cycle_active else 'Não'}\n"
            f"Intervalo: {snapshot.sync_interval_seconds}s"
        )
        self._update_home_state_display(snapshot.state, snapshot.detail_message)
        self._refresh_last_updated_label(snapshot.last_confirmed_sync_at)

        # Atualiza o Hero Status Banner e a Pílula Global
        state, creds, _ = self._get_account_operational_state()
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        has_folders = bool(local_cfg and remote_cfg)
        is_voluntary = self.database.is_voluntary_disconnect()
        is_configured = (state == "READY" or snapshot.configured_pair_ready) and not is_voluntary and has_folders
        is_locked = (state == "VAULT_LOCKED") or (snapshot.attention_category == ATTENTION_VAULT_LOCKED)

        is_paused = snapshot.auto_sync_paused or snapshot.state == STATE_PAUSED
        if is_locked:
            self.hero_banner.setProperty("heroState", "attention")
            self.hero_icon_label.setPixmap(render_vector_pixmap("alert", 36, "#FFFFFF"))
            self.hero_title_label.setText(tr("hero_vault_locked_title"))
            self.hero_subtitle_label.setText(
                tr("hero_vault_locked_subtitle")
            )
            self.hero_pause_btn.setText(tr("hero_btn_unlock"))
            self.hero_pause_btn.setIcon(get_vector_icon("lock", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("pill_vault_locked"))
            self.global_status_pill.setProperty("class", "statusPill statusPillAttention")
            self.overview_idle_box.setVisible(False)
            self.attention_banner_frame.setVisible(True)
            self.overview_operation_header.setText(tr("overview_header_attention_pending"))
            self.attention_explanation_label.setText(
                "[VAULT_LOCKED] "
                + (
                    "Cofre bloqueado: O chaveiro da sessão está bloqueado. Desbloqueie o chaveiro para retomar a sincronização."
                    if get_current_language() == "pt_BR"
                    else "Vault locked: The session keyring is locked. Unlock the keyring to resume sync."
                )
            )
        elif is_voluntary or state == "NOT_CONNECTED":
            if snapshot.attention_category in (ATTENTION_RECOVERY_REQUIRED, ATTENTION_CONFLICT_DETECTED, ATTENTION_PERSISTENT_FAILURE):
                self.hero_banner.setProperty("heroState", "attention")
                self.hero_icon_label.setPixmap(render_vector_pixmap("alert", 36, "#FFFFFF"))
                self.hero_title_label.setText(tr("hero_attention_title"))
                self.hero_subtitle_label.setText(snapshot.attention_title or snapshot.detail_message)
                self.hero_pause_btn.setText(tr("hero_btn_inspect"))
                self.hero_pause_btn.setIcon(get_vector_icon("info", 14, "#FFFFFF"))
                self.global_status_pill.setText(tr("pill_attention"))
                self.global_status_pill.setProperty("class", "statusPill statusPillAttention")
            else:
                self.hero_banner.setProperty("heroState", "unconfigured")
                self.hero_icon_label.setPixmap(render_vector_pixmap("folder", 36, "#9189FF"))
                self.hero_title_label.setText(tr("hero_title_no_account"))
                self.hero_subtitle_label.setText(tr("hero_subtitle_no_account"))
                self.hero_pause_btn.setText(tr("hero_btn_help"))
                self.hero_pause_btn.setIcon(get_vector_icon("info", 14, "#FFFFFF"))
                self.global_status_pill.setText(tr("folder_status_waiting_account") if has_folders else tr("pill_unconfigured"))
                self.global_status_pill.setProperty("class", "statusPill")
        elif not is_configured:
            self.hero_banner.setProperty("heroState", "unconfigured")
            self.hero_icon_label.setPixmap(render_vector_pixmap("folder", 36, "#9189FF"))
            self.hero_title_label.setText(tr("hero_welcome_title"))
            if state == "CONFIG_PENDING":
                self.hero_subtitle_label.setText(tr("hero_config_pending_subtitle"))
                self.global_status_pill.setText(tr("pill_config_pending"))
            else:
                self.hero_subtitle_label.setText(tr("hero_unconfigured_subtitle"))
                self.global_status_pill.setText(tr("pill_unconfigured"))
            self.hero_pause_btn.setText(tr("hero_btn_help"))
            self.hero_pause_btn.setIcon(get_vector_icon("info", 14, "#FFFFFF"))
            self.global_status_pill.setProperty("class", "statusPill")
        elif snapshot.attention_category or snapshot.state == STATE_ATTENTION_REQUIRED:
            self.hero_banner.setProperty("heroState", "attention")
            self.hero_icon_label.setPixmap(render_vector_pixmap("alert", 36, "#FFFFFF"))
            self.hero_title_label.setText(tr("hero_attention_title"))
            self.hero_subtitle_label.setText(snapshot.attention_title or snapshot.detail_message)
            self.hero_pause_btn.setText(tr("hero_btn_inspect"))
            self.hero_pause_btn.setIcon(get_vector_icon("info", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("pill_attention"))
            self.global_status_pill.setProperty("class", "statusPill statusPillAttention")
        elif is_paused or snapshot.state == STATE_PAUSING:
            self.hero_banner.setProperty("heroState", "paused")
            self.hero_icon_label.setPixmap(render_vector_pixmap("pause", 36, "#FFFFFF"))
            self.hero_title_label.setText(tr("hero_paused_title"))
            self.hero_subtitle_label.setText(tr("hero_paused_subtitle"))
            self.hero_pause_btn.setText(tr("hero_btn_resume"))
            self.hero_pause_btn.setIcon(get_vector_icon("play", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("pill_paused"))
            self.global_status_pill.setProperty("class", "statusPill statusPillPaused")
        elif snapshot.state in (STATE_SYNCING, STATE_VERIFYING) or snapshot.is_cycle_active:
            self.hero_banner.setProperty("heroState", "syncing")
            self.hero_icon_label.setPixmap(render_vector_pixmap("sync", 36, "#FFFFFF"))
            self.hero_title_label.setText(tr("hero_syncing_title"))
            self.hero_subtitle_label.setText(tr("hero_syncing_subtitle"))
            self.hero_pause_btn.setText(tr("hero_btn_pause"))
            self.hero_pause_btn.setIcon(get_vector_icon("pause", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("pill_syncing"))
            self.global_status_pill.setProperty("class", "statusPill statusPillSyncing")
        else:
            self.hero_banner.setProperty("heroState", "healthy")
            self.hero_icon_label.setPixmap(render_vector_pixmap("check_circle", 36, "#FFFFFF"))
            self.hero_title_label.setText(tr("hero_healthy_title"))
            rel_time = _format_relative_timestamp(snapshot.last_confirmed_sync_at)
            self.hero_subtitle_label.setText(tr("hero_last_check", rel_time=rel_time) if rel_time else tr("hero_waiting_first_check"))
            self.hero_pause_btn.setText(tr("hero_btn_pause_all"))
            self.hero_pause_btn.setIcon(get_vector_icon("pause", 14, "#FFFFFF"))
            self.global_status_pill.setText(tr("pill_healthy"))
            self.global_status_pill.setProperty("class", "statusPill statusPillHealthy")

        self.hero_banner.style().unpolish(self.hero_banner)
        self.hero_banner.style().polish(self.hero_banner)
        self.global_status_pill.style().unpolish(self.global_status_pill)
        self.global_status_pill.style().polish(self.global_status_pill)
        self._update_hero_primary_button(snapshot)

        # Banner de atenção acionável e coerência com o card de operação
        is_spurious_auth_alert = (
            snapshot.attention_category == ATTENTION_AUTH_EXPIRED
            and (is_voluntary or state == "NOT_CONNECTED" or not self._has_usable_account())
        )
        has_attention = bool(
            is_locked
            or (
                (snapshot.attention_category or snapshot.state == STATE_ATTENTION_REQUIRED)
                and not is_spurious_auth_alert
                and not (is_voluntary and not snapshot.attention_category)
            )
        )
        if has_attention:
            self.overview_idle_box.setVisible(False)
            self.attention_banner_frame.setVisible(True)
            self.overview_operation_header.setText(tr("overview_header_attention_pending"))
            if is_locked:
                self.attention_explanation_label.setText(
                    "[VAULT_LOCKED] "
                    + (
                        "Cofre bloqueado: O chaveiro da sessão está bloqueado. Desbloqueie o chaveiro para retomar a sincronização."
                        if get_current_language() == "pt_BR"
                        else "Vault locked: The session keyring is locked. Unlock the keyring to resume sync."
                    )
                )
            else:
                prefix = f"[{snapshot.attention_category}] " if snapshot.attention_category else ""
                title = snapshot.attention_title or tr("hero_attention_title")
                desc = (
                    snapshot.attention_explanation
                    or snapshot.last_error_reason
                    or snapshot.detail_message
                    or "Motivo ainda não identificado."
                )
                self.attention_explanation_label.setText(f"{prefix}{title}: {desc}")
        elif snapshot.state in (STATE_SYNCING, STATE_VERIFYING) or snapshot.is_cycle_active:
            self.overview_idle_box.setVisible(False)
            self.attention_banner_frame.setVisible(False)
            self.overview_operation_header.setText(tr("overview_header_in_progress"))
        else:
            self.overview_idle_box.setVisible(True)
            self.attention_banner_frame.setVisible(False)
            if is_voluntary or state == "NOT_CONNECTED":
                self.overview_operation_header.setText(
                    tr("folder_status_waiting_account") if has_folders else tr("overview_header_idle")
                )
            else:
                self.overview_operation_header.setText(tr("overview_header_in_queue"))

        self.notification_manager.evaluate_snapshot(snapshot)
        self.tray_controller.update_from_snapshot(snapshot)

        self.pause_sync_button.setVisible(not is_paused)
        self.pause_sync_button.setEnabled(not is_paused and snapshot.state != STATE_PAUSING)
        self.resume_sync_button.setVisible(is_paused)
        self.resume_sync_button.setEnabled(is_paused or snapshot.state == STATE_PAUSING)

        self.stop_current_button.setVisible(snapshot.is_cycle_active)
        self.stop_current_button.setEnabled(snapshot.is_cycle_active)
        self.shutdown_service_button.setEnabled(True)

        self._select_interval_in_combo(snapshot.sync_interval_seconds)

        self.autostart_checkbox.blockSignals(True)
        self.autostart_checkbox.setChecked(snapshot.autostart_enabled)
        self.autostart_checkbox.blockSignals(False)

        recent = self.database.list_recent_sync_runs(limit=1)
        top_id = recent[0].id if recent else None
        if top_id != self._last_history_top_id:
            self.refresh_history_table()
            self._update_sync_target_preview()

        self._update_home_view()
        self._update_folder_status_pills(snapshot)
        self._sync_path_feedback_labels()

    def _on_hero_pause_toggle(self) -> None:
        state, _, _ = self._get_account_operational_state()
        if state == "VAULT_LOCKED" or (
            self._last_snapshot and self._last_snapshot.attention_category == ATTENTION_VAULT_LOCKED
        ):
            self._on_unlock_vault_clicked()
            return

        if self.hero_banner.property("heroState") == "unconfigured":
            self._open_diagnostics_dialog()
            return

        if self._last_snapshot and (self._last_snapshot.attention_category or self._last_snapshot.state == STATE_ATTENTION_REQUIRED):
            self._show_attention_details_dialog()
            return

        is_paused = (
            self._last_snapshot.auto_sync_paused or self._last_snapshot.state == STATE_PAUSED
            if self._last_snapshot
            else self.database.is_auto_sync_paused()
        )
        if is_paused:
            self._on_resume_sync_clicked()
        else:
            self._on_pause_sync_clicked()

    def _show_attention_details_dialog(self) -> None:
        """Abre diálogo modal com o diagnóstico técnico sanitizado completo da ocorrência."""
        snap = self._last_snapshot
        title = snap.attention_title if (snap and snap.attention_title) else "Atenção Necessária"
        err_text = (
            (snap.last_error_reason or snap.detail_message or "Nenhum detalhe técnico adicional registrado.")
            if snap
            else "Sem snapshot de serviço disponível."
        )

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Diagnóstico — {title}")
        dlg.resize(580, 340)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        t_lbl = QLabel(title, dlg)
        t_lbl.setProperty("class", "dialogTitle")
        layout.addWidget(t_lbl)

        sub_lbl = QLabel("Erro original sanitizado registrado pelo serviço:", dlg)
        sub_lbl.setProperty("class", "dialogSubtitle")
        layout.addWidget(sub_lbl)

        txt_box = QTextEdit(dlg)
        txt_box.setReadOnly(True)
        txt_box.setPlainText(err_text)
        txt_box.setStyleSheet("font-family: monospace; font-size: 12px;")
        layout.addWidget(txt_box, stretch=1)

        btn_row = QHBoxLayout()
        state, _, _ = self._get_account_operational_state()
        if (snap and snap.attention_category == ATTENTION_VAULT_LOCKED) or state == "VAULT_LOCKED":
            btn_unlock = QPushButton("Desbloquear Cofre", dlg)
            btn_unlock.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_unlock.setStyleSheet(
                "background-color: #9189FF; color: #0B0F15; font-weight: bold; padding: 6px 14px; border-radius: 6px;"
            )
            btn_unlock.clicked.connect(lambda: (dlg.accept(), self._on_unlock_vault_clicked()))
            btn_row.addWidget(btn_unlock)
        btn_row.addStretch(1)
        btn_close = QPushButton("Fechar", dlg)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.exec()

    def _on_inspect_attention_clicked(self) -> None:
        self.restore_and_focus_window()
        self.set_current_page(2)
        self.refresh_history_table()
        if self.history_table.rowCount() > 0:
            self.history_table.selectRow(0)

    def _run_service_command(
        self,
        action: str,
        *,
        payload: dict[str, Any] | None = None,
        ensure_running: bool = True,
    ) -> None:
        data = payload or {}
        if not ensure_running or self.ipc_client.is_service_running():
            try:
                extra: Any = None
                if action == "get_status":
                    snapshot = self.ipc_client.get_status()
                elif action == "sync_now":
                    snapshot, coalesced = self.ipc_client.sync_now()
                    extra = coalesced
                elif action == "pause":
                    snapshot = self.ipc_client.pause()
                elif action == "resume":
                    snapshot = self.ipc_client.resume()
                elif action == "stop_current":
                    snapshot = self.ipc_client.stop_current()
                elif action == "set_interval":
                    snapshot = self.ipc_client.set_interval(int(data.get("interval_seconds", 300)))
                elif action == "set_autostart":
                    snapshot = self.ipc_client.set_autostart(bool(data.get("enabled", False)))
                elif action == "shutdown_service":
                    snapshot = self.ipc_client.shutdown_service()
                elif action == "vault_unlocked":
                    snapshot = self.ipc_client.notify_vault_unlocked()
                else:
                    raise ValueError(f"Ação IPC desconhecida: {action!r}")
                self._on_service_command_succeeded(action, snapshot, extra)
            except Exception as exc:
                self._on_service_command_failed(action, str(exc))
            return

        if self._cmd_worker is not None:
            try:
                if self._cmd_worker.isRunning():
                    return
            except RuntimeError:
                pass
            self._retired_workers.append(self._cmd_worker)

        try:
            worker = ServiceCommandWorker(
                ipc_client=self.ipc_client,
                action=action,
                payload=data,
                ensure_running=ensure_running,
            )
            self._cmd_worker = worker
            worker.command_succeeded.connect(self._on_service_command_succeeded)
            worker.command_failed.connect(self._on_service_command_failed)
            worker.finished.connect(worker.deleteLater)
            worker.start()
        except Exception as exc:
            self._cmd_worker = None
            self._on_service_command_failed(action, str(exc))

    def _on_service_command_succeeded(
        self, action: str, snapshot: ServiceStatusSnapshot, extra: Any
    ) -> None:
        self._apply_service_snapshot(snapshot)
        if action == "sync_now":
            coalesced = bool(extra)
            msg = (
                "Sincronização já em andamento. Pedido consolidado ao ciclo ativo."
                if coalesced
                else "Sincronização solicitada ao serviço da sessão."
            )
            self.statusBar().showMessage(msg, 4000)
        elif action == "pause":
            self.statusBar().showMessage("Sincronização automática pausada.", 4000)
        elif action == "resume":
            self.statusBar().showMessage("Sincronização automática retomada.", 4000)
        elif action == "shutdown_service":
            self.statusBar().showMessage("Serviço em segundo plano encerrado.", 4000)
            self.refresh_service_status_from_ipc()
        elif action == "vault_unlocked":
            self.refresh_service_status_from_ipc()

    def _on_service_command_failed(self, action: str, error_msg: str) -> None:
        self.statusBar().showMessage(f"Falha ao executar '{action}': {error_msg}", 5000)
        self.refresh_service_status_from_ipc()

    def _on_sync_now_clicked(self) -> None:
        state, creds, _ = self._get_account_operational_state()
        if state == "VAULT_LOCKED" or (
            self._last_snapshot is not None
            and self._last_snapshot.attention_category == ATTENTION_VAULT_LOCKED
        ):
            self._on_unlock_vault_clicked()
            return

        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        configured_pair_ready = (
            self._last_snapshot.configured_pair_ready
            if self._last_snapshot
            else True
        )
        is_configured = (
            (state == "READY" or configured_pair_ready)
            and not self.database.is_voluntary_disconnect()
            and bool(local_cfg and remote_cfg)
        )

        if not is_configured:
            self._on_connect_google_clicked()
            return

        if self._last_snapshot and (
            self._last_snapshot.is_cycle_active
            or self._last_snapshot.state in (STATE_SYNCING, STATE_VERIFYING)
        ):
            self.statusBar().showMessage(
                "Sincronização bidirecional já está em andamento.", 3000
            )
            return

        self._run_service_command("sync_now", ensure_running=True)

    def _on_pause_sync_clicked(self) -> None:
        self._run_service_command("pause", ensure_running=False)

    def _on_resume_sync_clicked(self) -> None:
        self._run_service_command("resume", ensure_running=True)

    def _on_tray_pause_or_resume_clicked(self) -> None:
        is_paused = (
            self._last_snapshot.auto_sync_paused or self._last_snapshot.state == STATE_PAUSED
            if self._last_snapshot
            else self.database.is_auto_sync_paused()
        )
        if is_paused:
            self._on_resume_sync_clicked()
        else:
            self._on_pause_sync_clicked()

    def _on_stop_current_clicked(self) -> None:
        self._run_service_command("stop_current", ensure_running=False)

    def _on_shutdown_service_clicked(self) -> None:
        self._run_service_command("shutdown_service", ensure_running=False)

    def _on_theme_mode_changed(self, index: int) -> None:
        if index < 0:
            return
        mode = self.theme_mode_combo.itemData(index)
        if mode in ("system", "light", "dark"):
            self.database.set_theme_preference(str(mode))
            self.apply_theme()

    def _select_theme_mode_in_combo(self, mode: str) -> None:
        for idx in range(self.theme_mode_combo.count()):
            if self.theme_mode_combo.itemData(idx) == mode:
                self.theme_mode_combo.blockSignals(True)
                self.theme_mode_combo.setCurrentIndex(idx)
                self.theme_mode_combo.blockSignals(False)
                break

    def _on_language_changed(self, index: int) -> None:
        if index < 0:
            return
        code = self.language_combo.itemData(index)
        valid_codes = {c for _, c in SUPPORTED_LANGUAGES}
        if code in valid_codes:
            self.database.set_language_preference(str(code))
            set_current_language(str(code))
            self.retranslate_ui()
            if hasattr(self, "tray_controller") and self.tray_controller:
                self.tray_controller.retranslate_tray()

    def _select_language_in_combo(self, lang_code: str) -> None:
        if not hasattr(self, "language_combo"):
            return
        for idx in range(self.language_combo.count()):
            if self.language_combo.itemData(idx) == lang_code:
                self.language_combo.blockSignals(True)
                self.language_combo.setCurrentIndex(idx)
                self.language_combo.blockSignals(False)
                break

    def retranslate_ui(self) -> None:
        """Atualiza dinamicamente em tempo de execução todas as telas, cabeçalho e diálogos no idioma ativo."""
        # 1. Título da janela
        self.setWindowTitle(f"{tr('app_title')} — {tr('app_tagline')}")

        # 2. Barra lateral
        if hasattr(self, "sidebar_nav_lbl"):
            self.sidebar_nav_lbl.setText(tr("sidebar_section_nav"))
        if hasattr(self, "nav_buttons") and len(self.nav_buttons) >= 4:
            self.nav_buttons[0].setText(tr("nav_overview"))
            self.nav_buttons[1].setText(tr("nav_folders"))
            self.nav_buttons[2].setText(tr("nav_activity"))
            self.nav_buttons[3].setText(tr("nav_settings"))
        if hasattr(self, "sidebar_brand_sub"):
            self.sidebar_brand_sub.setText(tr("sidebar_brand_sub"))
        if hasattr(self, "sidebar_rclone_title"):
            self.sidebar_rclone_title.setText(tr("sidebar_rclone_connected"))
        if hasattr(self, "sidebar_tray_title"):
            self.sidebar_tray_title.setText(tr("sidebar_tray_sync"))
        if hasattr(self, "sidebar_tray_desc"):
            self.sidebar_tray_desc.setText(tr("sidebar_tray_desc"))
        if hasattr(self, "sidebar_diag_btn"):
            self.sidebar_diag_btn.setText(tr("nav_help"))
        if hasattr(self, "sidebar_about_btn"):
            self.sidebar_about_btn.setText(tr("nav_about"))

        # 3. Cabeçalho
        if hasattr(self, "tabs"):
            self._on_tab_changed(self.tabs.currentIndex())
        if hasattr(self, "options_menu_btn"):
            self.options_menu_btn.setText(tr("header_btn_options"))
        if hasattr(self, "menu_diag_action"):
            self.menu_diag_action.setText(tr("menu_action_diagnostics"))
        if hasattr(self, "menu_about_action"):
            self.menu_about_action.setText(tr("menu_action_about"))
        if hasattr(self, "menu_exit_action"):
            self.menu_exit_action.setText(tr("menu_action_exit"))
        if hasattr(self, "header_settings_shortcut_btn"):
            self.header_settings_shortcut_btn.setText(tr("header_btn_configure"))

        # 4. Hero Banner e Métricas
        if hasattr(self, "hero_sync_now_btn"):
            self.hero_sync_now_btn.setText(tr("hero_btn_sync_now"))
        if hasattr(self, "hero_metric_speed_lbl"):
            self.hero_metric_speed_lbl.setText(tr("hero_stat_speed"))
        if hasattr(self, "hero_metric_transfer_lbl"):
            self.hero_metric_transfer_lbl.setText(tr("hero_stat_transferred"))
        if hasattr(self, "hero_metric_folders_lbl"):
            self.hero_metric_folders_lbl.setText(tr("hero_stat_active_folders"))

        # 5. Visão Geral (Idle / Recente / Alertas)
        if hasattr(self, "overview_recent_activity_title"):
            self.overview_recent_activity_title.setText(tr("overview_recent_activity_title"))
        if hasattr(self, "overview_recent_open_btn"):
            self.overview_recent_open_btn.setText(tr("overview_btn_view_all_history"))

        # 6. Assistente (Wizard)
        if hasattr(self, "setup_step1_label"):
            self.setup_step1_label.setText(tr("wizard_step1_title"))
        if hasattr(self, "setup_step1_desc"):
            self.setup_step1_desc.setText(tr("wizard_step1_desc"))
        if hasattr(self, "setup_connect_button"):
            self.setup_connect_button.setText(tr("settings_btn_connect"))
        if hasattr(self, "setup_step2_label"):
            self.setup_step2_label.setText(tr("wizard_step2_title"))
        if hasattr(self, "setup_step3_label"):
            self.setup_step3_label.setText(tr("wizard_step3_title"))

        # 7. Aba Pastas
        if hasattr(self, "folders_card_title_label"):
            self.folders_card_title_label.setText(tr("folders_card_title"))
        if hasattr(self, "folders_page_open_btn"):
            self.folders_page_open_btn.setText(tr("folders_local_open_btn"))
        if hasattr(self, "folders_page_sync_btn"):
            self.folders_page_sync_btn.setText(tr("folders_local_sync_btn"))
        if hasattr(self, "folders_remove_pair_btn"):
            self.folders_remove_pair_btn.setText(tr("folders_btn_remove_pair"))
        if hasattr(self, "folders_connect_account_btn"):
            self.folders_connect_account_btn.setText(tr("folders_btn_connect_account"))
        if hasattr(self, "folders_paths_card_title"):
            self.folders_paths_card_title.setText(tr("folders_card_title"))
        if hasattr(self, "folders_remote_lbl"):
            self.folders_remote_lbl.setText(tr("folders_remote_label"))
        if hasattr(self, "list_remote_folders_button"):
            self.list_remote_folders_button.setText(tr("folders_remote_list_btn"))
        if hasattr(self, "create_remote_folder_button"):
            self.create_remote_folder_button.setText(tr("folders_remote_new_btn"))
        if hasattr(self, "folders_local_lbl"):
            self.folders_local_lbl.setText(tr("folders_local_label"))
        if hasattr(self, "browse_folder_button"):
            self.browse_folder_button.setText(tr("folders_local_browse_btn"))
        if hasattr(self, "save_folder_button"):
            self.save_folder_button.setText(tr("folders_local_save_btn"))
        if hasattr(self, "folders_rule_notice"):
            self.folders_rule_notice.setText(tr("folders_rule_notice"))

        # 8. Aba Atividade
        if hasattr(self, "history_summary_label"):
            total_runs_count = self.database.count_recent_sync_runs()
            self.history_summary_label.setText(
                tr("history_summary_count", count=total_runs_count)
            )
        if hasattr(self, "refresh_history_button"):
            self.refresh_history_button.setText(tr("history_btn_refresh"))
        if hasattr(self, "clear_history_button"):
            self.clear_history_button.setText(tr("history_btn_clear"))
        if hasattr(self, "history_hint_label"):
            self.history_hint_label.setText(tr("history_hint_double_click"))
        if hasattr(self, "history_table"):
            self.history_table.setHorizontalHeaderLabels(
                [
                    tr("history_table_header_started"),
                    tr("history_table_header_operation"),
                    tr("history_table_header_status"),
                    tr("history_table_header_folders"),
                    tr("history_table_header_summary"),
                ]
            )
            self.refresh_history_table()

        # 9. Aba Ajustes
        if hasattr(self, "settings_accounts_title"):
            self.settings_accounts_title.setText(tr("settings_card_accounts"))
        if hasattr(self, "settings_engine_title"):
            self.settings_engine_title.setText(tr("settings_card_engine"))
        if hasattr(self, "settings_system_card_title"):
            self.settings_system_card_title.setText(tr("settings_card_system"))
        if hasattr(self, "advanced_toggle_btn"):
            prefix = "▼ " if getattr(self, "advanced_container", None) and self.advanced_container.isVisible() else "▶ "
            self.advanced_toggle_btn.setText(f"{prefix}{tr('settings_card_advanced')}")

        if hasattr(self, "connect_google_button"):
            self.connect_google_button.setText(tr("settings_btn_connect"))
        if hasattr(self, "disconnect_google_button"):
            self.disconnect_google_button.setText(tr("settings_btn_disconnect"))
        if hasattr(self, "oauth_security_note_label"):
            self.oauth_security_note_label.setText(tr("settings_account_security_notice"))
        if hasattr(self, "settings_engine_mode_lbl"):
            self.settings_engine_mode_lbl.setText(tr("settings_engine_bisync_mode"))
        if hasattr(self, "open_diagnostics_from_settings_btn"):
            self.open_diagnostics_from_settings_btn.setText(tr("settings_btn_diagnostics"))

        if hasattr(self, "settings_theme_lbl"):
            self.settings_theme_lbl.setText(tr("settings_theme_label"))
        if hasattr(self, "settings_lang_lbl"):
            self.settings_lang_lbl.setText(tr("settings_language_label"))
        if hasattr(self, "settings_int_lbl"):
            self.settings_int_lbl.setText(tr("settings_interval_label"))
        if hasattr(self, "settings_tray_lbl"):
            self.settings_tray_lbl.setText(tr("settings_tray_label"))

        # Atualiza opções dos seletores mantendo seleção
        if hasattr(self, "theme_mode_combo"):
            cur_theme = self.theme_mode_combo.currentData()
            self.theme_mode_combo.blockSignals(True)
            self.theme_mode_combo.clear()
            for txt, val in [
                (tr("theme_system"), "system"),
                (tr("theme_light"), "light"),
                (tr("theme_dark"), "dark"),
            ]:
                self.theme_mode_combo.addItem(txt, userData=val)
            t_idx = self.theme_mode_combo.findData(cur_theme)
            if t_idx >= 0:
                self.theme_mode_combo.setCurrentIndex(t_idx)
            self.theme_mode_combo.blockSignals(False)

        if hasattr(self, "interval_combo"):
            cur_int = self.interval_combo.currentData()
            self.interval_combo.blockSignals(True)
            self.interval_combo.clear()
            for txt, val in [
                (tr("interval_1min"), 60),
                (tr("interval_5min"), 300),
                (tr("interval_15min"), 900),
                (tr("interval_30min"), 1800),
                (tr("interval_60min"), 3600),
            ]:
                self.interval_combo.addItem(txt, userData=val)
            i_idx = self.interval_combo.findData(cur_int)
            if i_idx >= 0:
                self.interval_combo.setCurrentIndex(i_idx)
            self.interval_combo.blockSignals(False)

        if hasattr(self, "tray_mode_combo"):
            cur_tray = self.tray_mode_combo.currentData()
            self.tray_mode_combo.blockSignals(True)
            self.tray_mode_combo.clear()
            for txt, val in [
                (tr("tray_auto"), "auto"),
                (tr("tray_light"), "dark_panel"),
                (tr("tray_dark"), "light_panel"),
            ]:
                self.tray_mode_combo.addItem(txt, userData=val)
            tr_idx = self.tray_mode_combo.findData(cur_tray)
            if tr_idx >= 0:
                self.tray_mode_combo.setCurrentIndex(tr_idx)
            self.tray_mode_combo.blockSignals(False)

        if hasattr(self, "autostart_checkbox"):
            self.autostart_checkbox.setText(tr("settings_autostart_checkbox"))
        if hasattr(self, "notifications_checkbox"):
            self.notifications_checkbox.setText(tr("settings_notifications_checkbox"))
        if hasattr(self, "exit_app_button"):
            self.exit_app_button.setText(tr("settings_btn_exit"))
        if hasattr(self, "settings_about_title"):
            self.settings_about_title.setText(tr("settings_card_about"))
        if hasattr(self, "settings_about_sub_lbl"):
            self.settings_about_sub_lbl.setText(tr("about_headline"))
        if hasattr(self, "settings_about_lic_lbl"):
            self.settings_about_lic_lbl.setText(tr("settings_about_license"))
        if hasattr(self, "open_about_dlg_btn"):
            self.open_about_dlg_btn.setText(tr("settings_btn_open_about"))

        self._update_lifecycle_notice_text()
        self._refresh_account_state_from_vault()
        self._update_home_view()
        if hasattr(self, "_last_snapshot") and self._last_snapshot:
            self._apply_service_snapshot(self._last_snapshot)
        self._sync_path_feedback_labels()

    def _on_interval_changed(self, index: int) -> None:
        if index < 0:
            return
        seconds = self.interval_combo.itemData(index)
        if seconds:
            self.database.set_sync_interval_seconds(int(seconds))
            self._run_service_command(
                "set_interval",
                payload={"interval_seconds": int(seconds)},
                ensure_running=False,
            )

    def _select_interval_in_combo(self, seconds: int) -> None:
        for idx in range(self.interval_combo.count()):
            if self.interval_combo.itemData(idx) == seconds:
                self.interval_combo.blockSignals(True)
                self.interval_combo.setCurrentIndex(idx)
                self.interval_combo.blockSignals(False)
                break

    def _on_tray_mode_changed(self, index: int) -> None:
        if index < 0:
            return
        mode = self.tray_mode_combo.itemData(index)
        if mode:
            self.database.set_tray_icon_theme_mode(str(mode))
            self.tray_controller.set_theme_mode(str(mode))

    def _select_tray_mode_in_combo(self, mode: str) -> None:
        for idx in range(self.tray_mode_combo.count()):
            if self.tray_mode_combo.itemData(idx) == mode:
                self.tray_mode_combo.blockSignals(True)
                self.tray_mode_combo.setCurrentIndex(idx)
                self.tray_mode_combo.blockSignals(False)
                break

    def _on_autostart_toggled(self, checked: bool) -> None:
        try:
            if checked:
                self.autostart_manager.enable()
            else:
                self.autostart_manager.disable()
            self._run_service_command(
                "set_autostart",
                payload={"enabled": checked},
                ensure_running=False,
            )
        except Exception as exc:
            self.autostart_checkbox.blockSignals(True)
            self.autostart_checkbox.setChecked(not checked)
            self.autostart_checkbox.blockSignals(False)
            QMessageBox.warning(
                self,
                "Autoinício",
                f"Falha ao configurar o autoinício: {exc}",
            )

    def _on_notifications_toggled(self, checked: bool) -> None:
        self.database.set_setting("notifications_enabled", "1" if checked else "0")
        self.notification_manager.set_enabled(checked)

    def _on_browse_oauth_client_json(self) -> None:
        start_dir = str(Path.home())
        chosen, _ = QFileDialog.getOpenFileName(
            self,
            "Selecionar Cliente OAuth Desktop Google (.json)",
            start_dir,
            "Arquivos JSON (*.json);;Todos os Arquivos (*)",
        )
        if chosen:
            self.oauth_client_path_input.setText(chosen)
            self.database.set_setting("oauth_client_json_path", chosen)
            self._update_home_view()

    def _set_oauth_in_progress(self, in_progress: bool) -> None:
        """Controla o estado de habilitação dos botões de conexão e cancelamento OAuth."""
        if hasattr(self, "connect_google_button") and self.connect_google_button is not None:
            self.connect_google_button.setEnabled(not in_progress)
        if hasattr(self, "setup_connect_button") and self.setup_connect_button is not None:
            self.setup_connect_button.setEnabled(not in_progress)
        if hasattr(self, "hero_sync_now_btn") and self.hero_sync_now_btn is not None:
            self.hero_sync_now_btn.setEnabled(not in_progress)
        if hasattr(self, "cancel_oauth_button") and self.cancel_oauth_button is not None:
            self.cancel_oauth_button.setEnabled(in_progress)
            self.cancel_oauth_button.setVisible(in_progress)
        if not in_progress:
            self._update_hero_primary_button(self._last_snapshot)

    def _on_unlock_vault_clicked(self) -> None:
        """Inicia o desbloqueio interativo do cofre de credenciais em thread secundária."""
        if self._unlock_worker is not None:
            try:
                if self._unlock_worker.isRunning():
                    self.statusBar().showMessage("Desbloqueio do cofre já em andamento...", 3000)
                    return
            except RuntimeError:
                self._unlock_worker = None

        self.statusBar().showMessage("Aguardando confirmação do desbloqueio do cofre da sessão...", 5000)
        if hasattr(self, "hero_sync_now_btn") and self.hero_sync_now_btn is not None:
            self.hero_sync_now_btn.setEnabled(False)
        if hasattr(self, "connect_google_button") and self.connect_google_button is not None:
            self.connect_google_button.setEnabled(False)
        if hasattr(self, "setup_connect_button") and self.setup_connect_button is not None:
            self.setup_connect_button.setEnabled(False)

        worker = UnlockVaultWorker(self.credential_store, self.bridge, parent=self)
        self._unlock_worker = worker
        worker.succeeded.connect(self._on_vault_unlock_succeeded)
        worker.failed.connect(self._on_vault_unlock_failed)
        worker.finished.connect(self._on_vault_unlock_finished)
        worker.start()

    def _on_vault_unlock_finished(self) -> None:
        self._unlock_worker = None
        if hasattr(self, "hero_sync_now_btn") and self.hero_sync_now_btn is not None:
            self.hero_sync_now_btn.setEnabled(True)
        if hasattr(self, "connect_google_button") and self.connect_google_button is not None:
            self.connect_google_button.setEnabled(True)
        if hasattr(self, "setup_connect_button") and self.setup_connect_button is not None:
            self.setup_connect_button.setEnabled(True)

    def _on_vault_unlock_succeeded(self, creds: Any) -> None:
        self._cached_account_state = None
        email = getattr(creds, "account_email", "") if creds else ""
        msg = f"Cofre desbloqueado com sucesso! Conta ativa: {email}" if email else "Cofre desbloqueado com sucesso!"
        self.statusBar().showMessage(msg, 5000)
        self._refresh_account_state_from_vault(force_refresh=True)
        self._update_home_view()
        self._run_service_command("vault_unlocked", ensure_running=False)
        self.refresh_service_status_from_ipc()

    def _on_vault_unlock_failed(self, error_msg: str) -> None:
        self._cached_account_state = None
        self.statusBar().showMessage(f"Cofre permanece bloqueado: {error_msg}", 5000)
        self._refresh_account_state_from_vault(force_refresh=True)
        self._update_home_view()

    def _on_connect_google_clicked(self) -> None:
        state, creds, detail = self._get_account_operational_state()

        if state == "VAULT_LOCKED":
            self._on_unlock_vault_clicked()
            return

        # Recuperação sem navegador quando as credenciais no cofre já forem válidas
        if state == "CONFIG_PENDING" and creds is not None:
            self.account_status_label.setText("Restabelecendo configuração do Google Drive...")
            self.account_status_label.setStyleSheet("color: #60A5FA;")
            try:
                self.bridge.materialize_encrypted_config(creds)
                self._refresh_account_state_from_vault()
                self._update_home_view()
                self.statusBar().showMessage(
                    "Configuração do Google Drive concluída com sucesso!", 4000
                )
                if not self.database.get_remote_sync_folder():
                    self._on_list_remote_folders()
                return
            except Exception as exc:
                self.account_status_label.setText(f"Falha ao materializar configuração rclone: {exc}")
                self.account_status_label.setStyleSheet("color: #EF4444;")
                QMessageBox.critical(
                    self,
                    "Falha na Configuração",
                    f"As credenciais estão salvas no cofre da sessão, mas o motor rclone não pôde ser configurado:\n\n{exc}\n\n"
                    "Verifique se o pacote oficial do BrisaSync foi instalado e se o motor rclone está disponível.",
                )
                return

        if self._oauth_worker is not None:
            try:
                if self._oauth_worker.isRunning():
                    self.statusBar().showMessage("Autenticação Google já em andamento...", 3000)
                    return
            except RuntimeError:
                self._oauth_worker = None

        self._set_oauth_in_progress(True)
        # Mantém agendamento bloqueado durante a troca de credenciais
        try:
            self.ipc_client.execute_command("disconnect_account")
        except Exception:
            pass
        self.account_status_label.setText("Iniciando autenticação Google no navegador...")
        self.account_status_label.setStyleSheet("color: #60A5FA;")

        explicit_json = self.oauth_client_path_input.text().strip() or None
        try:
            client_config = OAuthClientConfig.load_available(explicit_path=explicit_json)
        except OAuthConfigurationError as exc:
            self._set_oauth_in_progress(False)
            self._oauth_worker = None
            self.account_status_label.setText("Configuração OAuth necessária.")
            self.account_status_label.setStyleSheet("color: #EF4444;")
            QMessageBox.critical(
                self,
                "Configuração OAuth Necessária",
                f"{exc}\n\n"
                "Para forks ou desenvolvimento, selecione um arquivo 'google_oauth_client.json' "
                "do tipo 'Desktop App' na Seção Avançada.",
            )
            return
        except Exception as exc:
            self._set_oauth_in_progress(False)
            self._oauth_worker = None
            self.account_status_label.setText(f"Falha ao carregar cliente OAuth: {exc}")
            self.account_status_label.setStyleSheet("color: #EF4444;")
            QMessageBox.critical(
                self,
                "Falha ao Inicializar Conexão",
                f"Erro inesperado ao inicializar a autenticação:\n\n{exc}\n\n"
                "Verifique se o pacote oficial do BrisaSync foi instalado corretamente.",
            )
            return

        try:
            worker = OAuthConnectWorker(
                client_config=client_config,
                credential_store=self.credential_store,
                bridge=self.bridge,
            )
            self._oauth_worker = worker
            worker.succeeded.connect(self._on_oauth_succeeded)
            worker.failed.connect(self._on_oauth_failed)
            worker.finished.connect(self._on_oauth_worker_finished)
            worker.finished.connect(worker.deleteLater)
            worker.start()
        except Exception as exc:
            self._oauth_worker = None
            self._set_oauth_in_progress(False)
            self.account_status_label.setText(f"Falha ao iniciar autenticação: {exc}")
            self.account_status_label.setStyleSheet("color: #EF4444;")
            QMessageBox.critical(
                self,
                "Falha ao Iniciar Autenticação",
                f"Não foi possível iniciar o assistente de conexão:\n\n{exc}",
            )
            return

    def _on_oauth_worker_finished(self) -> None:
        self._oauth_worker = None

    def _on_cancel_oauth_clicked(self) -> None:
        if self._oauth_worker is not None:
            try:
                if self._oauth_worker.isRunning():
                    self._oauth_worker.request_cancel()
                    self._oauth_worker.wait(1500)
            except RuntimeError:
                pass
            self._oauth_worker = None
        self._set_oauth_in_progress(False)
        self.account_status_label.setText("Autenticação cancelada.")
        self.account_status_label.setStyleSheet("color: #8B949E;")
        self._refresh_account_state_from_vault()

    def _validate_remote_destination_by_id(self, folder_id: str) -> bool:
        """Valida se a pasta remota existe e está acessível no Google Drive pelo seu ID imutável."""
        if not folder_id:
            return False
        validator = getattr(self, "_remote_folder_id_validator", None)
        if validator is not None:
            return bool(validator(folder_id))
        if getattr(self, "_suppress_dialogs_for_testing", False) and not self.bridge.config_path.is_file():
            return True
        config_path = self.bridge.config_path
        if not config_path.is_file():
            try:
                creds = self.credential_store.load_credentials(interactive=False)
                if creds and creds.access_token and creds.has_drive_scope:
                    self.bridge.materialize_encrypted_config(creds)
            except Exception:
                pass
        if not config_path.is_file():
            return False
        try:
            with self.bridge.authenticated_rclone_session() as env:
                bin_path = getattr(self.bridge, "rclone_binary", getattr(self.bridge, "rclone_path", None))
                engine = RcloneBisyncEngine(bin_path)
                engine.resolve_remote_directory_by_id(f"{REMOTE_NAME}:", folder_id, env=env)
                return True
        except Exception as exc:
            logger.warning("Falha ao validar destino remoto por ID %s: %s", folder_id, exc)
            return False

    def _on_oauth_succeeded(self, creds: OAuthCredentials) -> None:
        self._oauth_worker = None
        self._set_oauth_in_progress(False)
        self.database.set_voluntary_disconnect(False)

        new_email = (creds.account_email or "").strip()
        prev_email = (self.database.get_pair_linked_account_email() or "").strip()
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()

        is_same_account = bool(prev_email and new_email and prev_email.lower() == new_email.lower())

        if not is_same_account:
            has_prior_pair = bool(local_cfg or remote_cfg)
            if local_cfg and remote_cfg:
                self.database.invalidate_baseline(
                    local_folder=local_cfg.folder_path,
                    remote_folder_id=remote_cfg.folder_id,
                )
            self.database.clear_remote_sync_folder()
            if hasattr(self, "remote_folder_input"):
                self.remote_folder_input.clear()
            if hasattr(self, "remote_folder_combo"):
                self.remote_folder_combo.clear()
            if new_email:
                self.database.set_pair_linked_account_email(new_email)
            if has_prior_pair and not getattr(self, "_suppress_dialogs_for_testing", False):
                notice_msg = (
                    tr("folders_diff_account_notice", new_email=new_email, prev_email=prev_email, current=new_email, prev=prev_email)
                    if prev_email
                    else tr("folders_unknown_prev_account_notice", current=new_email)
                )
                QMessageBox.information(
                    self,
                    tr("header_account_connected"),
                    notice_msg,
                )
            self._on_list_remote_folders()
        else:
            if new_email:
                self.database.set_pair_linked_account_email(new_email)
            if remote_cfg:
                if self._validate_remote_destination_by_id(remote_cfg.folder_id):
                    if local_cfg:
                        try:
                            self.ipc_client.execute_command("account_connected")
                        except Exception:
                            pass
                else:
                    if local_cfg:
                        self.database.invalidate_baseline(
                            local_folder=local_cfg.folder_path,
                            remote_folder_id=remote_cfg.folder_id,
                        )
                    self.database.clear_remote_sync_folder()
                    if hasattr(self, "remote_folder_input"):
                        self.remote_folder_input.clear()
                    if hasattr(self, "remote_folder_combo"):
                        self.remote_folder_combo.clear()
                    if not getattr(self, "_suppress_dialogs_for_testing", False):
                        QMessageBox.warning(
                            self,
                            tr("header_attention"),
                            tr("folders_remote_inaccessible_notice", folder=remote_cfg.folder_name or remote_cfg.folder_id),
                        )
                    self._on_list_remote_folders()
            else:
                self._on_list_remote_folders()

        self._refresh_account_state_from_vault()
        self._update_home_view()
        self.refresh_service_status_from_ipc()
        self.statusBar().showMessage(tr("header_account_connected"), 4000)

    def _on_oauth_failed(self, error_msg: str) -> None:
        self._oauth_worker = None
        self._set_oauth_in_progress(False)
        self._refresh_account_state_from_vault()
        self._update_home_view()
        if "cancelad" in error_msg.lower():
            self.account_status_label.setText("Autenticação cancelada pelo usuário.")
            self.account_status_label.setStyleSheet("color: #8B949E;")
            self.statusBar().showMessage("Login cancelado.", 3000)
            return
        self.account_status_label.setText(f"Falha na autenticação: {error_msg}")
        self.account_status_label.setStyleSheet("color: #EF4444;")
        QMessageBox.critical(
            self,
            "Falha na Autenticação",
            f"Não foi possível concluir o login com o Google:\n\n{error_msg}",
        )

    def _on_list_remote_folders(self) -> None:
        config_path = self.bridge.config_path
        if not config_path.is_file():
            try:
                creds = self.credential_store.load_credentials()
                if creds and creds.access_token and creds.has_drive_scope:
                    self.bridge.materialize_encrypted_config(creds)
            except Exception as exc:
                if not getattr(self, "_suppress_dialogs_for_testing", False):
                    QMessageBox.critical(
                        self,
                        "Falha na Configuração",
                        f"Não foi possível inicializar a configuração do Google Drive:\n\n{exc}",
                    )
                self.remote_folder_feedback_label.setText(f"Erro de configuração: {exc}")
                self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
                if hasattr(self, "wizard_remote_feedback"):
                    self.wizard_remote_feedback.setText(f"Erro de configuração: {exc}")
                    self.wizard_remote_feedback.setStyleSheet("color: #EF4444;")
                return

        if not config_path.is_file():
            msg = tr("folders_remote_blocked_no_account")
            if not getattr(self, "_suppress_dialogs_for_testing", False):
                QMessageBox.warning(
                    self,
                    tr("header_not_connected"),
                    msg,
                )
            self.remote_folder_feedback_label.setText(msg)
            self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
            if hasattr(self, "wizard_remote_feedback"):
                self.wizard_remote_feedback.setText(msg)
                self.wizard_remote_feedback.setStyleSheet("color: #EF4444;")
            return

        self.list_remote_folders_button.setEnabled(False)
        if hasattr(self, "wizard_list_remote_btn"):
            self.wizard_list_remote_btn.setEnabled(False)
        self.remote_folder_feedback_label.setText("Consultando pastas no Google Drive...")
        self.remote_folder_feedback_label.setStyleSheet("color: #8B949E;")
        if hasattr(self, "wizard_remote_feedback"):
            self.wizard_remote_feedback.setText("Consultando pastas no Google Drive...")
            self.wizard_remote_feedback.setStyleSheet("color: #8B949E;")

        try:
            worker = RemoteFoldersWorker(bridge=self.bridge, action="list")
            self._folders_worker = worker
            worker.folders_loaded.connect(self._on_remote_folders_loaded)
            worker.operation_failed.connect(self._on_remote_folders_failed)
            worker.finished.connect(worker.deleteLater)
            worker.start()
        except Exception as exc:
            self._folders_worker = None
            self.list_remote_folders_button.setEnabled(True)
            if hasattr(self, "wizard_list_remote_btn"):
                self.wizard_list_remote_btn.setEnabled(True)
            self.remote_folder_feedback_label.setText(f"Erro ao listar pastas: {exc}")
            self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
            if hasattr(self, "wizard_remote_feedback"):
                self.wizard_remote_feedback.setText(f"Erro ao listar pastas: {exc}")
                self.wizard_remote_feedback.setStyleSheet("color: #EF4444;")

    def _on_create_remote_folder(self) -> None:
        name, ok = QInputDialog.getText(
            self,
            "Criar Pasta no Google Drive",
            "Nome da nova pasta no Drive:",
        )
        if ok and name.strip():
            self._create_remote_folder_by_name(name.strip())

    def _create_remote_folder_by_name(self, name: str) -> None:
        self.create_remote_folder_button.setEnabled(False)
        if hasattr(self, "wizard_create_remote_btn"):
            self.wizard_create_remote_btn.setEnabled(False)
        self.remote_folder_feedback_label.setText(f"Criando pasta '{name}' no Drive...")
        self.remote_folder_feedback_label.setStyleSheet("color: #8B949E;")
        if hasattr(self, "wizard_remote_feedback"):
            self.wizard_remote_feedback.setText(f"Criando pasta '{name}' no Drive...")
            self.wizard_remote_feedback.setStyleSheet("color: #8B949E;")

        try:
            worker = RemoteFoldersWorker(
                bridge=self.bridge,
                action="create",
                folder_name=name,
            )
            self._folders_worker = worker
            worker.folders_loaded.connect(self._on_remote_folders_loaded)
            worker.operation_failed.connect(self._on_remote_folders_failed)
            worker.finished.connect(worker.deleteLater)
            worker.start()
        except Exception as exc:
            self._folders_worker = None
            self.create_remote_folder_button.setEnabled(True)
            if hasattr(self, "wizard_create_remote_btn"):
                self.wizard_create_remote_btn.setEnabled(True)
            self.remote_folder_feedback_label.setText(f"Erro ao criar pasta: {exc}")
            self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
            if hasattr(self, "wizard_remote_feedback"):
                self.wizard_remote_feedback.setText(f"Erro ao criar pasta: {exc}")
                self.wizard_remote_feedback.setStyleSheet("color: #EF4444;")

    def _on_remote_folders_loaded(
        self, entries: list[RemoteDirectoryEntry], newly_created: RemoteDirectoryEntry | None
    ) -> None:
        try:
            self.list_remote_folders_button.setEnabled(True)
            if hasattr(self, "wizard_list_remote_btn"):
                self.wizard_list_remote_btn.setEnabled(True)
            self.create_remote_folder_button.setEnabled(True)
            if hasattr(self, "wizard_create_remote_btn"):
                self.wizard_create_remote_btn.setEnabled(True)
            self._remote_entries = entries or []

            current_saved = self.database.get_remote_sync_folder()
            select_id = (
                getattr(newly_created, "folder_id", None)
                if newly_created
                else (current_saved.folder_id if current_saved else None)
            )

            self.remote_folder_combo.blockSignals(True)
            self.remote_folder_combo.clear()
            self.wizard_remote_combo.blockSignals(True)
            self.wizard_remote_combo.clear()

            target_index = -1
            for idx, entry in enumerate(self._remote_entries):
                folder_name = getattr(entry, "name", getattr(entry, "folder_name", "")) or ""
                folder_id = getattr(entry, "folder_id", "") or ""
                display_text = f"{folder_name} [ID: {folder_id}]" if folder_id else folder_name
                data = (folder_id, folder_name)
                self.remote_folder_combo.addItem(display_text, userData=data)
                self.wizard_remote_combo.addItem(display_text, userData=data)
                if select_id and folder_id == select_id:
                    target_index = idx

            if target_index >= 0:
                self.remote_folder_combo.setCurrentIndex(target_index)
                self.wizard_remote_combo.setCurrentIndex(target_index)
            elif self._remote_entries:
                self.remote_folder_combo.setCurrentIndex(0)
                self.wizard_remote_combo.setCurrentIndex(0)

            if not self._remote_entries:
                msg = "Nenhuma pasta encontrada no Google Drive. Use '+ Nova Pasta...' para criar uma."
                self.remote_folder_feedback_label.setText(msg)
                self.remote_folder_feedback_label.setStyleSheet("color: #F59E0B;")
                if hasattr(self, "wizard_remote_feedback"):
                    self.wizard_remote_feedback.setText(msg)
                    self.wizard_remote_feedback.setStyleSheet("color: #F59E0B;")
            elif newly_created:
                cname = getattr(newly_created, "name", getattr(newly_created, "folder_name", ""))
                msg = f"✓ Pasta '{cname}' criada com sucesso."
                self.remote_folder_feedback_label.setText(msg)
                self.remote_folder_feedback_label.setStyleSheet("color: #10B981;")
                if hasattr(self, "wizard_remote_feedback"):
                    self.wizard_remote_feedback.setText(msg)
                    self.wizard_remote_feedback.setStyleSheet("color: #10B981;")
            else:
                msg = f"✓ {len(self._remote_entries)} pasta(s) localizada(s) no Google Drive."
                self.remote_folder_feedback_label.setText(msg)
                self.remote_folder_feedback_label.setStyleSheet("color: #10B981;")
                if hasattr(self, "wizard_remote_feedback"):
                    self.wizard_remote_feedback.setText(msg)
                    self.wizard_remote_feedback.setStyleSheet("color: #10B981;")
        finally:
            self.remote_folder_combo.blockSignals(False)
            self.wizard_remote_combo.blockSignals(False)
            self.list_remote_folders_button.setEnabled(True)
            if hasattr(self, "wizard_list_remote_btn"):
                self.wizard_list_remote_btn.setEnabled(True)
            self.create_remote_folder_button.setEnabled(True)
            if hasattr(self, "wizard_create_remote_btn"):
                self.wizard_create_remote_btn.setEnabled(True)

        if self.remote_folder_combo.currentIndex() >= 0:
            self._on_remote_folder_selection_changed(self.remote_folder_combo.currentIndex())

    def _on_remote_folders_failed(self, error_msg: str) -> None:
        self.list_remote_folders_button.setEnabled(True)
        if hasattr(self, "wizard_list_remote_btn"):
            self.wizard_list_remote_btn.setEnabled(True)
        self.create_remote_folder_button.setEnabled(True)
        if hasattr(self, "wizard_create_remote_btn"):
            self.wizard_create_remote_btn.setEnabled(True)
        msg = f"Erro ao consultar pastas no Drive: {error_msg}"
        self.remote_folder_feedback_label.setText(msg)
        self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
        if hasattr(self, "wizard_remote_feedback"):
            self.wizard_remote_feedback.setText(msg)
            self.wizard_remote_feedback.setStyleSheet("color: #EF4444;")

    def _on_remote_folder_selection_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self.remote_folder_combo.itemData(index)
        if data and isinstance(data, (tuple, list)) and len(data) >= 2:
            folder_id, folder_name = data[0], data[1]
            prev_remote = self.database.get_remote_sync_folder()
            if prev_remote is not None and prev_remote.folder_id == folder_id:
                return

            local_cfg = self.database.get_local_sync_folder()
            if local_cfg is not None:
                # Verifica se o par exige baseline inicial (não foi inicializado anteriormente)
                is_init = self.database.is_baseline_initialized(
                    local_folder=local_cfg.folder_path,
                    remote_folder_id=folder_id,
                )
                if not is_init:
                    local_p = Path(local_cfg.folder_path).expanduser()
                    if local_p.is_dir():
                        items = list(local_p.iterdir())
                        if items:
                            # Rejeita a alteração e preserva a configuração válida anterior
                            if prev_remote is not None:
                                self.remote_folder_combo.blockSignals(True)
                                for i in range(self.remote_folder_combo.count()):
                                    d = self.remote_folder_combo.itemData(i)
                                    if d and d[0] == prev_remote.folder_id:
                                        self.remote_folder_combo.setCurrentIndex(i)
                                        break
                                self.remote_folder_combo.blockSignals(False)

                            sample = ", ".join(e.name for e in items[:3])
                            err_msg = (
                                f"Status da pasta remota: [REJEITADA] Configuração rejeitada: Para iniciar a sincronização com '{folder_name}', "
                                f"a pasta local deve estar dedicada e vazia ({len(items)} item(ns) em {local_p.name}: {sample}). "
                                f"Escolha outra pasta local vazia antes de alterar a pasta remota."
                            )
                            self._pending_remote_rejection = {
                                "target_folder_id": folder_id,
                                "target_folder_name": folder_name,
                                "local_path_tested": local_cfg.folder_path,
                                "error_msg": err_msg,
                            }
                            self.remote_folder_feedback_label.setText(err_msg)
                            self.remote_folder_feedback_label.setStyleSheet("color: #EF4444;")
                            self._update_sync_target_preview()
                            return

            self._pending_remote_rejection = None
            self.database.set_remote_sync_folder(
                folder_id=folder_id,
                folder_name=folder_name,
            )
            self._sync_path_feedback_labels()
            self._update_sync_target_preview()
            self._update_home_view()

    def _on_browse_folder(self) -> None:
        start_dir = self.folder_input.text().strip() or str(Path.home())
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Selecionar Pasta Local",
            start_dir,
            QFileDialog.Option.ShowDirsOnly,
        )
        if chosen:
            self.folder_input.setText(chosen)
            self.save_and_validate_folder()

    def save_and_validate_folder(self) -> bool:
        raw_path = self.folder_input.text().strip()
        if not raw_path:
            self.folder_feedback_label.setText("Status da pasta: [ERRO] Informe o caminho local.")
            self.folder_feedback_label.setStyleSheet("color: #EF4444;")
            return False

        path = Path(raw_path).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
            validate_directory_accessible(path)

            remote_cfg = self.database.get_remote_sync_folder()
            if remote_cfg is not None:
                is_init = self.database.is_baseline_initialized(
                    local_folder=str(path),
                    remote_folder_id=remote_cfg.folder_id,
                )
                if not is_init:
                    items = list(path.iterdir())
                    if items:
                        sample = ", ".join(e.name for e in items[:3])
                        prev_local = self.database.get_local_sync_folder()
                        if prev_local:
                            self.folder_input.setText(prev_local.folder_path)
                        err_msg = (
                            f"Status da pasta: [REJEITADA] Configuração rejeitada: Para a primeira sincronização com '{remote_cfg.folder_name}', "
                            f"a pasta local deve estar dedicada e vazia ({len(items)} item(ns) encontrado(s)). "
                            f"Escolha outra pasta vazia."
                        )
                        self._pending_local_rejection = {
                            "target_path": str(path),
                            "remote_id": remote_cfg.folder_id,
                            "error_msg": err_msg,
                        }
                        self.folder_feedback_label.setText(err_msg)
                        self.folder_feedback_label.setStyleSheet("color: #EF4444;")
                        self._update_sync_target_preview()
                        return False

            if not self._has_usable_account():
                msg = tr("sync_blocked_no_account")
                self.folder_feedback_label.setText(f"Status da pasta: [ERRO] {msg}")
                self.folder_feedback_label.setStyleSheet("color: #EF4444;")
                return False

            self._pending_local_rejection = None
            self.database.set_local_sync_folder(str(path))
            if self._pending_remote_rejection is not None:
                if self._pending_remote_rejection.get("target_folder_id") == (remote_cfg.folder_id if remote_cfg else None):
                    self._pending_remote_rejection = None
            self._sync_path_feedback_labels()
            self._update_sync_target_preview()
            self._update_home_view()
            return True
        except DirectoryAccessError as exc:
            self.folder_feedback_label.setText(f"Status da pasta: [ACESSO NEGADO] {exc}")
            self.folder_feedback_label.setStyleSheet("color: #EF4444;")
            return False
        except Exception as exc:
            self.folder_feedback_label.setText(f"Status da pasta: [ERRO] {exc}")
            self.folder_feedback_label.setStyleSheet("color: #EF4444;")
            return False

    def _on_remove_pair_clicked(self) -> None:
        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        if not (local_cfg or remote_cfg):
            return

        if not getattr(self, "_suppress_dialogs_for_testing", False):
            reply = QMessageBox.question(
                self,
                tr("folders_remove_pair_confirm_title"),
                tr("folders_remove_pair_confirm_message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Para ciclo em andamento se houver
        if hasattr(self, "_last_snapshot") and self._last_snapshot and self._last_snapshot.is_cycle_active:
            try:
                self.ipc_client.execute_command("stop_current")
            except Exception:
                pass

        # Remove o vínculo no banco e avisa o daemon
        self.database.remove_sync_pair()
        try:
            self.ipc_client.execute_command("clear_pair")
        except Exception:
            pass

        self._pending_local_rejection = None
        self._pending_remote_rejection = None
        if hasattr(self, "folder_input"):
            self.folder_input.clear()
        if hasattr(self, "remote_folder_input"):
            self.remote_folder_input.clear()
        if hasattr(self, "remote_folder_combo"):
            self.remote_folder_combo.clear()
        if hasattr(self, "folder_feedback_label"):
            self.folder_feedback_label.setText("")
        if hasattr(self, "remote_folder_feedback_label"):
            self.remote_folder_feedback_label.setText("")

        self._sync_path_feedback_labels()
        self._update_sync_target_preview()
        self._update_home_view()
        self.refresh_service_status_from_ipc()
        self.statusBar().showMessage(tr("folders_pair_removed_feedback"), 4000)

    def refresh_diagnostics(self) -> None:
        diag = collect_system_diagnostics()
        summary = (
            f"Diagnóstico do Sistema: {__app_name__} v{__version__} — "
            + ("Todas as dependências críticas estão operacionais." if diag.all_critical_ok else "Atenção necessária em dependências.")
        )
        self.diagnostics_summary_label.setText(summary)
        self.diagnostics_table.setRowCount(len(diag.items))

        for row, item in enumerate(diag.items):
            c_it = QTableWidgetItem(item.component)
            s_it = QTableWidgetItem(item.status_label)
            d_it = QTableWidgetItem(item.details)

            if item.status_code == "OK":
                s_it.setForeground(Qt.GlobalColor.darkGreen)
            elif item.status_code == "WARNING":
                s_it.setForeground(Qt.GlobalColor.darkYellow)
            else:
                s_it.setForeground(Qt.GlobalColor.darkRed)

            self.diagnostics_table.setItem(row, 0, c_it)
            self.diagnostics_table.setItem(row, 1, s_it)
            self.diagnostics_table.setItem(row, 2, d_it)

    def refresh_history_table(self) -> None:
        runs = self.database.list_recent_sync_runs(limit=50)
        self._current_history_runs = list(runs)
        self._last_history_top_id = runs[0].id if runs else None
        self.history_table.setRowCount(len(runs))
        total_runs_count = self.database.count_recent_sync_runs()
        self.history_summary_label.setText(tr("history_summary_count", count=total_runs_count))

        for row, r in enumerate(runs):
            try:
                dt = datetime.fromisoformat(r.started_at.replace("Z", "+00:00"))
                started_display = dt.astimezone().strftime("%d/%m/%Y %H:%M:%S")
            except Exception:
                started_display = r.started_at

            op_display = _format_operation_display(r.operation)
            st_display, st_color = _format_status_display(r.status)
            target_display = _format_folders_display(r.path1, r.path2)
            summary_display = _format_summary_display(r.summary, r.status)

            item_time = QTableWidgetItem(started_display)
            item_op = QTableWidgetItem(op_display)
            item_st = QTableWidgetItem(st_display)
            item_tgt = QTableWidgetItem(target_display)
            item_tgt.setToolTip(f"Origem / Destino 1: {r.path1}\nDestino 2: {r.path2}")
            item_sum = QTableWidgetItem(summary_display)
            item_sum.setToolTip(r.summary or "")

            item_st.setForeground(st_color)

            self.history_table.setItem(row, 0, item_time)
            self.history_table.setItem(row, 1, item_op)
            self.history_table.setItem(row, 2, item_st)
            self.history_table.setItem(row, 3, item_tgt)
            self.history_table.setItem(row, 4, item_sum)

        self._update_overview_recent_activity(self._current_history_runs)

    def _on_clear_history_clicked(self) -> None:
        title = tr("history_clear_confirm_title")
        message = tr("history_clear_confirm_message")
        reply = QMessageBox.question(
            self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.database.clear_sync_history_display()
            self.refresh_history_table()

    def _on_history_row_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if hasattr(self, "_current_history_runs") and 0 <= row < len(self._current_history_runs):
            run = self._current_history_runs[row]
            dlg = SyncRunDetailsDialog(run, parent=self)
            dlg.exec()

    def _update_folder_status_pills(self, snapshot: ServiceStatusSnapshot | None) -> None:
        """Atualiza com fidelidade o status dos cartões de pastas em Visão Geral e Pastas."""
        if not hasattr(self, "overview_folder_status_pill") or not hasattr(self, "folders_card_status_pill"):
            return

        local_cfg = self.database.get_local_sync_folder()
        remote_cfg = self.database.get_remote_sync_folder()
        if not (local_cfg and remote_cfg):
            txt = tr("folder_status_pending")
            style = (
                "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
                "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
            )
            self.overview_folder_status_pill.setText(txt)
            self.overview_folder_status_pill.setStyleSheet(style)
            self.folders_card_status_pill.setText(txt)
            self.folders_card_status_pill.setStyleSheet(style)
            if hasattr(self, "folders_page_sync_btn"):
                self.folders_page_sync_btn.setEnabled(False)
                self.folders_page_sync_btn.setToolTip(tr("sync_blocked_no_account"))
            return

        has_account = self._has_usable_account()

        if not has_account:
            txt = tr("folder_status_waiting_account")
            style = (
                "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
                "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
            )
            self.overview_folder_status_pill.setText(txt)
            self.overview_folder_status_pill.setStyleSheet(style)
            self.folders_card_status_pill.setText(txt)
            self.folders_card_status_pill.setStyleSheet(style)
            if hasattr(self, "folders_page_sync_btn"):
                self.folders_page_sync_btn.setEnabled(False)
                self.folders_page_sync_btn.setToolTip(tr("sync_blocked_no_account"))
            return

        if hasattr(self, "folders_page_sync_btn"):
            self.folders_page_sync_btn.setEnabled(True)
            self.folders_page_sync_btn.setToolTip("")

        if snapshot is None:
            is_init = self.database.is_baseline_initialized(
                local_folder=local_cfg.folder_path,
                remote_folder_id=remote_cfg.folder_id,
            )
            if is_init:
                style = (
                    "background-color: rgba(16, 185, 129, 0.15); color: #10B981; "
                    "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
                )
                self.overview_folder_status_pill.setText(tr("folder_status_up_to_date"))
                self.overview_folder_status_pill.setStyleSheet(style)
                self.folders_card_status_pill.setText(tr("folder_status_up_to_date_check"))
                self.folders_card_status_pill.setStyleSheet(style)
            else:
                txt = tr("folder_status_waiting_first_sync")
                style = (
                    "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
                    "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
                )
                self.overview_folder_status_pill.setText(txt)
                self.overview_folder_status_pill.setStyleSheet(style)
                self.folders_card_status_pill.setText(txt)
                self.folders_card_status_pill.setStyleSheet(style)
            return

        has_attention = bool(snapshot.attention_category or snapshot.state == STATE_ATTENTION_REQUIRED)
        is_paused = bool(snapshot.auto_sync_paused or snapshot.state == STATE_PAUSED)
        is_syncing = bool(snapshot.state in (STATE_SYNCING, STATE_VERIFYING) or snapshot.is_cycle_active)

        if has_attention:
            if snapshot.attention_category == ATTENTION_RECOVERY_REQUIRED:
                txt = tr("folder_status_recovery_pending")
            else:
                txt = tr("folder_status_blocked")
            style = (
                "background-color: rgba(239, 68, 68, 0.15); color: #EF4444; "
                "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
            )
            self.overview_folder_status_pill.setText(txt)
            self.overview_folder_status_pill.setStyleSheet(style)
            self.folders_card_status_pill.setText(txt)
            self.folders_card_status_pill.setStyleSheet(style)
        elif is_paused:
            txt = tr("folder_status_paused")
            style = (
                "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
                "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
            )
            self.overview_folder_status_pill.setText(txt)
            self.overview_folder_status_pill.setStyleSheet(style)
            self.folders_card_status_pill.setText(txt)
            self.folders_card_status_pill.setStyleSheet(style)
        elif is_syncing:
            txt = tr("folder_status_syncing")
            style = (
                "background-color: rgba(59, 130, 246, 0.15); color: #60A5FA; "
                "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
            )
            self.overview_folder_status_pill.setText(txt)
            self.overview_folder_status_pill.setStyleSheet(style)
            self.folders_card_status_pill.setText(txt)
            self.folders_card_status_pill.setStyleSheet(style)
        else:
            is_init = self.database.is_baseline_initialized(
                local_folder=local_cfg.folder_path,
                remote_folder_id=remote_cfg.folder_id,
            )
            has_confirmed_sync = bool(
                (snapshot.last_confirmed_sync_at and snapshot.last_run_status == "SUCCESS")
                or is_init
            )
            if not has_confirmed_sync:
                txt = tr("folder_status_waiting_first_sync")
                style = (
                    "background-color: rgba(245, 158, 11, 0.15); color: #F59E0B; "
                    "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
                )
                self.overview_folder_status_pill.setText(txt)
                self.overview_folder_status_pill.setStyleSheet(style)
                self.folders_card_status_pill.setText(txt)
                self.folders_card_status_pill.setStyleSheet(style)
            else:
                style = (
                    "background-color: rgba(16, 185, 129, 0.15); color: #10B981; "
                    "border-radius: 10px; padding: 2px 8px; font-size: 11px; font-weight: 600;"
                )
                self.overview_folder_status_pill.setText(tr("folder_status_up_to_date"))
                self.overview_folder_status_pill.setStyleSheet(style)
                self.folders_card_status_pill.setText(tr("folder_status_up_to_date_check"))
                self.folders_card_status_pill.setStyleSheet(style)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def _get_useful_content_width(self, window_width: int | None = None) -> int:
        """Calcula a largura útil do conteúdo descontando barra lateral, margens e buffers."""
        total_w = window_width if window_width is not None else self.width()
        sidebar_w = self.sidebar.width() if hasattr(self, "sidebar") and self.sidebar.isVisible() else 230
        page_margins = 48  # 24px margem esquerda + 24px margem direita
        scrollbar_buffer = 16
        return max(0, total_w - sidebar_w - page_margins - scrollbar_buffer)

    def _apply_responsive_layout(self, width: int | None = None) -> None:
        """Adapta a disposição visual entre 2 colunas e 1 coluna empilhada com base na largura útil."""
        useful_w = self._get_useful_content_width(width)
        is_narrow = useful_w < 880
        is_sub_narrow = useful_w < 450

        if (
            is_narrow == self._is_narrow_mode
            and is_sub_narrow == self._is_sub_narrow_mode
            and not getattr(self, "_force_layout_refresh", False)
        ):
            return

        self._is_narrow_mode = is_narrow
        self._is_sub_narrow_mode = is_sub_narrow
        self._force_layout_refresh = False

        # Oculta a pílula global do cabeçalho em janelas estreitas para preservar espaço ao e-mail e opções
        if hasattr(self, "global_status_pill"):
            self.global_status_pill.setVisible(not is_narrow)

        # 1. Visão Geral
        if hasattr(self, "overview_grid_layout") and hasattr(self, "hero_banner_layout"):
            if is_narrow:
                self.overview_grid_layout.setDirection(QBoxLayout.Direction.TopToBottom)
                self.overview_grid_layout.setStretch(0, 0)
                self.overview_grid_layout.setStretch(1, 0)
                if hasattr(self, "top_hero_row") and hasattr(self, "hero_actions_container"):
                    if self.top_hero_row.indexOf(self.hero_actions_container) != -1:
                        self.top_hero_row.removeWidget(self.hero_actions_container)
                        self.hero_banner_layout.insertWidget(1, self.hero_actions_container)
                        self.hero_actions_row.setAlignment(Qt.AlignmentFlag.AlignLeft)
            else:
                self.overview_grid_layout.setDirection(QBoxLayout.Direction.LeftToRight)
                self.overview_grid_layout.setStretch(0, 3)
                self.overview_grid_layout.setStretch(1, 2)
                if hasattr(self, "top_hero_row") and hasattr(self, "hero_actions_container"):
                    if self.hero_banner_layout.indexOf(self.hero_actions_container) != -1:
                        self.hero_banner_layout.removeWidget(self.hero_actions_container)
                        self.top_hero_row.addWidget(self.hero_actions_container)
                        self.hero_actions_row.setAlignment(Qt.AlignmentFlag.AlignRight)

        # 2. Ajustes
        if hasattr(self, "settings_grid_layout"):
            if is_narrow:
                self.settings_grid_layout.setDirection(QBoxLayout.Direction.TopToBottom)
                self.settings_grid_layout.setStretch(0, 0)
                self.settings_grid_layout.setStretch(1, 0)
            else:
                self.settings_grid_layout.setDirection(QBoxLayout.Direction.LeftToRight)
                self.settings_grid_layout.setStretch(0, 1)
                self.settings_grid_layout.setStretch(1, 1)

        if (
            hasattr(self, "settings_theme_row")
            and hasattr(self, "settings_lang_row")
            and hasattr(self, "settings_int_row")
            and hasattr(self, "settings_tray_row")
        ):
            if useful_w < 450:
                self.settings_theme_row.setDirection(QBoxLayout.Direction.TopToBottom)
                self.settings_lang_row.setDirection(QBoxLayout.Direction.TopToBottom)
                self.settings_int_row.setDirection(QBoxLayout.Direction.TopToBottom)
                self.settings_tray_row.setDirection(QBoxLayout.Direction.TopToBottom)
            else:
                self.settings_theme_row.setDirection(QBoxLayout.Direction.LeftToRight)
                self.settings_lang_row.setDirection(QBoxLayout.Direction.LeftToRight)
                self.settings_int_row.setDirection(QBoxLayout.Direction.LeftToRight)
                self.settings_tray_row.setDirection(QBoxLayout.Direction.LeftToRight)

        # 3. Pastas
        if (
            hasattr(self, "folders_card_top_row")
            and hasattr(self, "folders_card_actions_container")
            and hasattr(self, "folders_card_layout")
        ):
            if is_narrow:
                if self.folders_card_top_row.indexOf(self.folders_card_actions_container) != -1:
                    self.folders_card_top_row.removeWidget(self.folders_card_actions_container)
                    self.folders_card_layout.insertWidget(1, self.folders_card_actions_container)
                    self.folders_card_actions_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            else:
                if self.folders_card_layout.indexOf(self.folders_card_actions_container) != -1:
                    self.folders_card_layout.removeWidget(self.folders_card_actions_container)
                    self.folders_card_top_row.addWidget(self.folders_card_actions_container)
                    self.folders_card_actions_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        # 4. Atualiza elipse da conta no cabeçalho
        if hasattr(self, "header_account_badge"):
            self._update_home_view()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._explicit_ui_quit_requested:
            self._status_timer.stop()
            self._stop_hero_sync_animation()
            self.tray_controller.hide_and_cleanup()
            event.accept()
            return

        if self._minimize_to_tray_on_close and self.tray_controller.is_available:
            event.ignore()
            self.hide()
            self.tray_controller.send_tray_message(
                f"{__app_name__} em Execução",
                "A janela foi ocultada. O serviço continua ativo em segundo plano.",
                is_warning=False,
            )
            return

        self._status_timer.stop()
        self._stop_hero_sync_animation()
        self.tray_controller.hide_and_cleanup()
        event.accept()

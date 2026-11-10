"""Script para captura de evidências visuais em alta resolução do BrisaSync v0.1.20.

Gera capturas de:
1. Ajustes em 820x620, 1055x790 e 1920x1080 nos temas Claro e Escuro,
   destacando os seletores estilizados com setas vetoriais SVG, proporções contidas (linhas horizontais)
   e o subtítulo do cabeçalho completo sem cortes.
2. Início, Pastas e Atividade em 1055x790 (Claro e Escuro).
3. Matriz visual dos 4 estados semânticos do ícone da bandeja:
   - TRAY_STATE_HEALTHY
   - TRAY_STATE_SYNCING
   - TRAY_STATE_PAUSED
   - TRAY_STATE_ATTENTION
   renderizados para barra escura (GNOME) e barra clara.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGridLayout,
    QFrame,
)
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont

if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

from brisasync.storage.database import BrisaDatabase
from brisasync.ui.styles import set_active_theme_preference
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.icons import (
    TRAY_STATE_HEALTHY,
    TRAY_STATE_SYNCING,
    TRAY_STATE_PAUSED,
    TRAY_STATE_ATTENTION,
    load_tray_state_icon,
)


def capture_widget(widget, output_path: Path):
    widget.show()
    app = QApplication.instance()
    app.processEvents()
    pix = widget.grab()
    pix.save(str(output_path), "PNG")
    print(f"Salvo: {output_path.name} ({pix.width()}x{pix.height()})")


def generate_tray_states_matrix(output_path: Path):
    """Gera uma imagem comparativa exibindo os 4 estados do ícone em barras escuras e claras."""
    container = QWidget()
    container.setObjectName("tray_matrix_container")
    container.setStyleSheet("""
        #tray_matrix_container {
            background-color: #1e232a;
            border-radius: 12px;
            border: 1px solid #333d4b;
        }
        QLabel {
            color: #f1f5f9;
            font-family: system-ui, sans-serif;
        }
    """)
    main_layout = QVBoxLayout(container)
    main_layout.setContentsMargins(24, 20, 24, 24)
    main_layout.setSpacing(16)

    title = QLabel("BrisaSync v0.1.20 — Estados Semânticos e Contraste da Bandeja")
    font = QFont()
    font.setPointSize(14)
    font.setBold(True)
    title.setFont(font)
    main_layout.addWidget(title)

    subtitle = QLabel("Ícones gerados dinamicamente com contraste independente e semântica de estado")
    sub_font = QFont()
    sub_font.setPointSize(10)
    subtitle.setFont(sub_font)
    subtitle.setStyleSheet("color: #94a3b8;")
    main_layout.addWidget(subtitle)

    grid = QGridLayout()
    grid.setHorizontalSpacing(20)
    grid.setVerticalSpacing(14)

    states = [
        ("Saudável (Em Espera)", TRAY_STATE_HEALTHY, "Tudo sincronizado e em repouso"),
        ("Sincronizando (Ativo)", TRAY_STATE_SYNCING, "Setas circulares de transferência ativa"),
        ("Pausado (Interrompido)", TRAY_STATE_PAUSED, "Sincronização temporariamente suspensa"),
        ("Atenção (Requer Ação)", TRAY_STATE_ATTENTION, "Triângulo âmbar de alerta operacional"),
    ]

    # Cabeçalho da grade
    grid.addWidget(QLabel("<b>Estado do Sistema</b>"), 0, 0)
    grid.addWidget(QLabel("<b>Painel Escuro (GNOME / Padrão)</b>"), 0, 1)
    grid.addWidget(QLabel("<b>Painel Claro (KDE / Custom)</b>"), 0, 2)
    grid.addWidget(QLabel("<b>Descrição Semântica</b>"), 0, 3)

    for row_idx, (name, state_key, desc) in enumerate(states, start=1):
        lbl_name = QLabel(f"<b>{name}</b>")
        grid.addWidget(lbl_name, row_idx, 0)

        # Barra Escura (#242424)
        box_dark = QFrame()
        box_dark.setFixedSize(140, 48)
        box_dark.setStyleSheet("background-color: #242424; border-radius: 6px; border: 1px solid #444;")
        h_dark = QHBoxLayout(box_dark)
        h_dark.setAlignment(Qt.AlignCenter)
        icon_dark = load_tray_state_icon(state_key, panel_is_dark=True)
        img_lbl_dark = QLabel()
        img_lbl_dark.setPixmap(icon_dark.pixmap(QSize(28, 28)))
        h_dark.addWidget(img_lbl_dark)
        grid.addWidget(box_dark, row_idx, 1)

        # Barra Clara (#e2e8f0)
        box_light = QFrame()
        box_light.setFixedSize(140, 48)
        box_light.setStyleSheet("background-color: #e2e8f0; border-radius: 6px; border: 1px solid #cbd5e1;")
        h_light = QHBoxLayout(box_light)
        h_light.setAlignment(Qt.AlignCenter)
        icon_light = load_tray_state_icon(state_key, panel_is_dark=False)
        img_lbl_light = QLabel()
        img_lbl_light.setPixmap(icon_light.pixmap(QSize(28, 28)))
        h_light.addWidget(img_lbl_light)
        grid.addWidget(box_light, row_idx, 2)

        lbl_desc = QLabel(desc)
        lbl_desc.setStyleSheet("color: #cbd5e1; font-size: 11px;")
        grid.addWidget(lbl_desc, row_idx, 3)

    main_layout.addLayout(grid)
    container.adjustSize()
    capture_widget(container, output_path)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    output_dir = Path("/home/agreles/.gemini/antigravity/brain/f563a160-5156-4b9f-bdd7-e6f83ee5154f")
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = Path("/tmp/brisasync_screenshots_v020.db")
    if db_path.exists():
        db_path.unlink()
    db = BrisaDatabase(db_path)

    test_local = Path("/tmp/BrisaSyncTestFolder")
    test_local.mkdir(parents=True, exist_ok=True)
    db.set_local_sync_folder(test_local)
    db.set_remote_sync_folder(folder_id="1A2B3C4D5E6F", folder_name="Documentos")
    db.set_last_confirmed_sync_at("2026-11-04T15:00:00Z")

    db.record_sync_run(
        started_at="2026-11-04T14:59:45Z",
        finished_at="2026-11-04T15:00:00Z",
        path1="/tmp/BrisaSyncTestFolder",
        path2="drive:Documentos",
        operation="bisync",
        status="SUCCESS",
        exit_code=0,
        summary="3 arquivos sincronizados com sucesso.",
    )

    # 1. Matriz dos estados semânticos da bandeja
    generate_tray_states_matrix(output_dir / "brisasync_v0.1.20_bandeja_estados_semanticos_matriz.png")

    window = BrisaMainWindow(database=db, enable_tray=False, allow_notify_send=False)
    window.show()
    app.processEvents()

    resolutions = [
        ("820x620", 820, 620),
        ("1055x790", 1055, 790),
        ("1920x1080", 1920, 1080),
    ]

    for theme_mode, label in (("light", "claro"), ("dark", "escuro")):
        print(f"\n=== Capturando BrisaSync v0.1.20 Tema {label.upper()} ({theme_mode}) ===")
        db.set_theme_preference(theme_mode)
        set_active_theme_preference(theme_mode)
        window.apply_theme()
        window.setMinimumSize(0, 0)
        window.setMaximumSize(16777215, 16777215)
        window.resize(820, 620)
        window.setFixedSize(820, 620)
        app.processEvents()

        # Captura da página Ajustes em todas as resoluções
        window.set_current_page(3)  # Ajustes
        for res_name, w, h in resolutions:
            window.setMinimumSize(0, 0)
            window.setMaximumSize(16777215, 16777215)
            window.resize(w, h)
            window.setFixedSize(w, h)
            window._apply_responsive_layout(w)
            app.processEvents()
            print(f"Target: {res_name} ({w}x{h}), Actual window size: ({window.width()}x{window.height()})")
            out_path = output_dir / f"brisasync_v0.1.20_{label}_ajustes_{res_name}.png"
            capture_widget(window, out_path)

        window.setMinimumSize(820, 600)
        window.setMaximumSize(16777215, 16777215)

        # Captura detalhada dos cartões de Ajustes em 1055x790
        window.setFixedSize(1055, 790)
        window._apply_responsive_layout(1055)
        app.processEvents()

        if hasattr(window, "theme_mode_combo"):
            pref_card = window.theme_mode_combo.parentWidget()
            if pref_card:
                capture_widget(pref_card, output_dir / f"brisasync_v0.1.20_{label}_detalhe_preferencias_seletores.png")

        # Captura do cabeçalho de Ajustes demonstrando o subtítulo completo sem cortes
        if hasattr(window, "page_title_label"):
            header_widget = window.page_title_label.parentWidget()
            if header_widget:
                capture_widget(header_widget, output_dir / f"brisasync_v0.1.20_{label}_detalhe_cabecalho_subtitulo.png")

        # Captura de Início em 1055x790
        window.setFixedSize(1055, 790)
        window._apply_responsive_layout(1055)
        window.set_current_page(0)  # Início
        app.processEvents()
        capture_widget(window, output_dir / f"brisasync_v0.1.20_{label}_inicio_1055x790.png")

        # Captura de Pastas em 1055x790
        window.set_current_page(1)  # Pastas
        app.processEvents()
        capture_widget(window, output_dir / f"brisasync_v0.1.20_{label}_pastas_1055x790.png")

        # Captura de Atividade em 1055x790
        window.set_current_page(2)  # Atividade
        app.processEvents()
        capture_widget(window, output_dir / f"brisasync_v0.1.20_{label}_atividade_1055x790.png")

    print("\nCapturas concluídas com sucesso!")


if __name__ == "__main__":
    main()


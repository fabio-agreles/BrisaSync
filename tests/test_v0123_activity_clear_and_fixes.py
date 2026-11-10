"""Testes de validação dos três pontos da v0.1.23 do BrisaSync:
1. Atividade: Limpeza de histórico com corte persistente, preservação de integridade e novos registros.
2. Tradução: Ciclo PT -> EN -> PT de contadores, resumos, cabeçalho, subtítulo e cartões de conta.
3. Caixas de seleção: Ícones de checkmark com alto contraste nos modos claro e escuro.
"""

from __future__ import annotations

import os
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from brisasync.i18n import get_current_language, set_current_language, tr
from brisasync.storage.database import BrisaDatabase, SyncRunRecord
from brisasync.ui.styles import get_brisasync_stylesheet
from brisasync.ui.main_window import (
    BrisaMainWindow,
    _format_summary_display,
)


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_1_database_history_display_cutoff(tmp_path: Path) -> None:
    db_file = tmp_path / "test_cutoff.db"
    db = BrisaDatabase(db_file)

    # Inicia com 0 registros
    assert db.count_recent_sync_runs() == 0
    assert db.list_recent_sync_runs() == []

    # Configura pasta e baseline para conferir preservação
    db.set_local_sync_folder(str(tmp_path / "local"))
    db.set_remote_sync_folder(folder_id="remote123", folder_name="RemoteDrive")
    db.mark_baseline_initialized(local_folder=str(tmp_path / "local"), remote_folder_id="remote123")
    db.set_auto_sync_paused(True)

    # Insere 60 execuções de teste (mais que as 50 visíveis na tabela)
    for i in range(1, 61):
        db.record_sync_run(
            started_at=f"2026-11-08T10:{i:02d}:00Z",
            finished_at=f"2026-11-08T10:{i:02d}:30Z",
            path1=str(tmp_path / "local"),
            path2="gdrive:RemoteDrive",
            operation="incremental_bisync",
            status="SUCCESS",
            exit_code=0,
            summary=f"Sincronização bidirecional concluída com sucesso.",
        )

    assert db.count_recent_sync_runs() == 60
    assert len(db.list_recent_sync_runs(limit=50)) == 50
    assert len(db.list_recent_sync_runs(limit=100)) == 60

    # Aplica a limpeza da exibição do histórico
    cutoff_id = db.clear_sync_history_display()
    assert cutoff_id == 60
    assert db.get_history_display_cutoff() == 60

    # Agora a listagem e contagem para exibição devem retornar 0
    assert db.count_recent_sync_runs() == 0
    assert db.list_recent_sync_runs(limit=50) == []

    # Dados brutos no banco continuam intactos para diagnósticos
    assert db.count_recent_sync_runs(include_hidden=True) == 60
    assert len(db.list_recent_sync_runs(limit=100, include_hidden=True)) == 60

    # Baselines, credenciais, pastas e preferências permanecem rigorosamente intactos
    assert db.get_local_sync_folder().folder_path == str(tmp_path / "local")
    assert db.get_remote_sync_folder().folder_id == "remote123"
    assert db.is_baseline_initialized(local_folder=str(tmp_path / "local"), remote_folder_id="remote123")
    assert db.is_auto_sync_paused() is True

    # Persistência após recriar a instância do Database (simulando reiniciar o app)
    db2 = BrisaDatabase(db_file)
    assert db2.get_history_display_cutoff() == 60
    assert db2.count_recent_sync_runs() == 0
    assert db2.list_recent_sync_runs(limit=50) == []

    # Uma nova execução (id 61) deve voltar a aparecer imediatamente na exibição
    new_id = db2.record_sync_run(
        started_at="2026-11-08T11:00:00Z",
        finished_at="2026-11-08T11:00:15Z",
        path1=str(tmp_path / "local"),
        path2="gdrive:RemoteDrive",
        operation="incremental_bisync",
        status="SUCCESS",
        exit_code=0,
        summary="Nova sincronização após limpeza.",
    )
    assert new_id == 61
    assert db2.count_recent_sync_runs() == 1
    recent = db2.list_recent_sync_runs(limit=50)
    assert len(recent) == 1
    assert recent[0].id == 61
    assert recent[0].summary == "Nova sincronização após limpeza."


def test_2_checkbox_styling_and_contrast_icons() -> None:
    # 1. Confere que os arquivos SVG dos checkmarks existem e são SVGs válidos
    base_dir = Path(__file__).resolve().parent.parent / "src" / "brisasync" / "resources" / "icons" / "checkbox"
    light_icon = base_dir / "checkmark-light.svg"
    dark_icon = base_dir / "checkmark-dark.svg"

    assert light_icon.is_file(), f"Arquivo não encontrado: {light_icon}"
    assert dark_icon.is_file(), f"Arquivo não encontrado: {dark_icon}"

    tree_light = ET.parse(light_icon)
    root_light = tree_light.getroot()
    assert "svg" in root_light.tag
    path_light = root_light.find("{http://www.w3.org/2000/svg}path")
    assert path_light is not None
    assert path_light.attrib.get("stroke") == "#FFFFFF"

    tree_dark = ET.parse(dark_icon)
    root_dark = tree_dark.getroot()
    assert "svg" in root_dark.tag
    path_dark = root_dark.find("{http://www.w3.org/2000/svg}path")
    assert path_dark is not None
    assert path_dark.attrib.get("stroke") == "#0F172A"

    # 2. Confere as regras QSS nos estilos Claro e Escuro
    qss_light = get_brisasync_stylesheet(dark_mode=False)
    assert "QCheckBox::indicator:unchecked" in qss_light
    assert "image: none;" in qss_light
    assert "QCheckBox::indicator:checked" in qss_light
    assert "checkmark-light.svg" in qss_light
    assert "QCheckBox::indicator:focus" in qss_light

    qss_dark = get_brisasync_stylesheet(dark_mode=True)
    assert "QCheckBox::indicator:unchecked" in qss_dark
    assert "QCheckBox::indicator:checked" in qss_dark
    assert "checkmark-dark.svg" in qss_dark
    assert "QCheckBox::indicator:focus" in qss_dark


def test_3_activity_clear_button_and_overview_update(tmp_path: Path, qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    db_file = tmp_path / "test_ui_clear.db"
    db = BrisaDatabase(db_file)
    db.set_language_preference("pt_BR")
    set_current_language("pt_BR")

    # Popula 55 registros
    for i in range(1, 56):
        db.record_sync_run(
            started_at=f"2026-11-08T12:{i:02d}:00Z",
            finished_at=f"2026-11-08T12:{i:02d}:10Z",
            path1="/home/user/Sync",
            path2="gdrive:Sync",
            operation="incremental_bisync",
            status="SUCCESS",
            exit_code=0,
            summary="Sincronização bidirecional concluída com sucesso.",
        )

    # Inicia a janela
    win = BrisaMainWindow(
        database=db,
        enable_tray=False,
        allow_notify_send=False,
    )
    try:
        # Confere botões da atividade
        assert hasattr(win, "refresh_history_button")
        assert hasattr(win, "clear_history_button")
        assert hasattr(win, "history_hint_label")
        assert win.clear_history_button.text() == "Limpar histórico"
        assert win.refresh_history_button.text() == "Atualizar Histórico"

        # Confere contagem inicial
        assert win.history_table.rowCount() == 50
        assert win.history_summary_label.text() == "Atividade recente (55 execuções registradas)"
        assert "Dica:" in win.history_hint_label.text()

        # Confere atividade recente na Visão Geral (tem itens)
        assert win.overview_recent_list_layout.count() > 0

        # Simula resposta 'Sim' na confirmação de exclusão
        monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)

        win.clear_history_button.click()

        # Tabela zerada, contagem 0, card de visão geral exibindo mensagem de vazio
        assert win.history_table.rowCount() == 0
        assert win.history_summary_label.text() == "Atividade recente (0 execuções registradas)"
        assert win.overview_recent_list_layout.count() == 1
        empty_lbl = win.overview_recent_list_layout.itemAt(0).widget()
        assert empty_lbl.text() == "Nenhuma atividade registrada ainda."

        # Insere uma nova execução e atualiza
        db.record_sync_run(
            started_at="2026-11-08T13:00:00Z",
            finished_at="2026-11-08T13:00:10Z",
            path1="/home/user/Sync",
            path2="gdrive:Sync",
            operation="incremental_bisync",
            status="SUCCESS",
            exit_code=0,
            summary="Execução posterior à limpeza.",
        )
        win.refresh_history_table()
        assert win.history_table.rowCount() == 1
        assert win.history_summary_label.text() == "Atividade recente (1 execuções registradas)"
    finally:
        win.close()


def test_4_i18n_pt_en_pt_cycle(tmp_path: Path, qapp: QApplication) -> None:
    db_file = tmp_path / "test_i18n_cycle.db"
    db = BrisaDatabase(db_file)
    db.set_language_preference("pt_BR")
    set_current_language("pt_BR")

    win = BrisaMainWindow(
        database=db,
        enable_tray=False,
        allow_notify_send=False,
    )
    try:
        # Estado inicial em Português
        assert win.sidebar_brand_sub.text() == "Sincronizador Google Drive"
        assert win.header_account_badge.text() == "○ Não conectado"
        assert "Atividade recente" in win.history_summary_label.text()
        assert win.refresh_history_button.text() == "Atualizar Histórico"
        assert win.clear_history_button.text() == "Limpar histórico"
        assert "Dica:" in win.history_hint_label.text()
        assert "Estado da Conta Google: [NÃO CONECTADA]" in win.account_status_label.text()
        assert win.connect_google_button.text() == "Conectar Conta Google"

        # Muda para Inglês
        set_current_language("en")
        win.retranslate_ui()

        assert win.sidebar_brand_sub.text() == "Google Drive Synchronizer"
        assert win.header_account_badge.text() == "○ Not connected"
        assert "Recent activity" in win.history_summary_label.text()
        assert win.refresh_history_button.text() == "Refresh History"
        assert win.clear_history_button.text() == "Clear History"
        assert "Tip:" in win.history_hint_label.text()
        assert "Google Account Status: [NOT CONNECTED]" in win.account_status_label.text()
        assert win.connect_google_button.text() == "Connect Google Account"

        # Executa refresh de histórico e refresh de estado da conta em inglês
        win.refresh_history_table()
        assert "Recent activity" in win.history_summary_label.text()

        win._refresh_account_state_from_vault()
        assert "Google Account Status: [NOT CONNECTED]" in win.account_status_label.text()
        assert win.connect_google_button.text() == "Connect Google Account"

        # Retorna para Português
        set_current_language("pt_BR")
        win.retranslate_ui()

        assert win.sidebar_brand_sub.text() == "Sincronizador Google Drive"
        assert win.header_account_badge.text() == "○ Não conectado"
        assert "Atividade recente" in win.history_summary_label.text()
        assert win.refresh_history_button.text() == "Atualizar Histórico"
        assert win.clear_history_button.text() == "Limpar histórico"
        assert "Dica:" in win.history_hint_label.text()
        assert "Estado da Conta Google: [NÃO CONECTADA]" in win.account_status_label.text()
        assert win.connect_google_button.text() == "Conectar Conta Google"
    finally:
        win.close()


def test_5_sync_summary_formatter_localization() -> None:
    # 1. Testa mensagens conhecidas em PT
    set_current_language("pt_BR")
    assert _format_summary_display("", "SUCCESS") == "Concluído sem conflitos."
    assert _format_summary_display("", "FAILED") == "Atenção necessária."
    assert _format_summary_display("Baseline inicial estabelecida com sucesso.", "SUCCESS") == "Baseline inicial estabelecida com sucesso."
    assert _format_summary_display("Initial baseline established successfully.", "SUCCESS") == "Baseline inicial estabelecida com sucesso."
    assert _format_summary_display("Sincronização bidirecional concluída com sucesso.", "SUCCESS") == "Sincronização bidirecional concluída com sucesso."
    assert _format_summary_display("Bidirectional synchronization completed successfully.", "SUCCESS") == "Sincronização bidirecional concluída com sucesso."

    # Com notas de conflito
    with_conflicts_pt = "Sincronização bidirecional concluída com sucesso. Conflitos preservados pelo backend (2): relatorio.txt.conflict, notas.txt.conflict."
    assert _format_summary_display(with_conflicts_pt, "SUCCESS") == with_conflicts_pt

    # 2. Testa as mesmas mensagens traduzidas em EN
    set_current_language("en")
    assert _format_summary_display("", "SUCCESS") == "Completed without conflicts."
    assert _format_summary_display("", "FAILED") == "Attention required."
    assert _format_summary_display("Baseline inicial estabelecida com sucesso.", "SUCCESS") == "Initial baseline established successfully."
    assert _format_summary_display("Initial baseline established successfully.", "SUCCESS") == "Initial baseline established successfully."
    assert _format_summary_display("Sincronização bidirecional concluída com sucesso.", "SUCCESS") == "Bidirectional synchronization completed successfully."
    assert _format_summary_display("Bidirectional synchronization completed successfully.", "SUCCESS") == "Bidirectional synchronization completed successfully."

    formatted_en = _format_summary_display(with_conflicts_pt, "SUCCESS")
    assert "Bidirectional synchronization completed successfully." in formatted_en
    assert "Conflicts preserved by backend (2): relatorio.txt.conflict, notas.txt.conflict" in formatted_en

    # 3. Preservação estrita de logs técnicos, paths e mensagens livres
    tech_err = "2026/11/08 14:15:20 ERROR : doc.pdf: corrupted file size mismatch 1024 != 2048"
    assert _format_summary_display(tech_err, "FAILED") == tech_err
    set_current_language("pt_BR")
    assert _format_summary_display(tech_err, "FAILED") == tech_err

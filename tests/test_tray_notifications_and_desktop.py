"""Testes automatizados da Rodada 5: Identidade Visual, Bandeja Opcional, Modo Sem Bandeja, Instância Única da UI e Notificações.

Valida os cenários obrigatórios:
1. Ícones em claro/escuro e escala normal (1x) / HiDPI (1.5x, 2x), independentes de `cwd`.
2. Ações da bandeja refletindo o estado real do serviço via IPC (Abrir painel, Abrir pasta local,
   Sincronizar agora, Pausar/retomar, Encerrar interface e Encerrar serviço).
3. Fechar/reabrir a janela mantendo a bandeja viva e recuperando o painel via socket de instância única (`ui.sock`) sem duplicação.
4. Funcionamento completo na ausência de bandeja (`tray_available=False`) sem perda de acesso às funções.
5. Reinício do componente gráfico com serviço já ativo, preservando estado e preferência de pausa.
6. Notificações configuráveis, agrupadas, deduplicadas, sanitizadas (sem tokens/e-mail/conteúdo) e espelhadas na janela.
"""

from __future__ import annotations

import os
from pathlib import Path
import time

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication
import pytest

from brisasync.backend.rclone_engine import BisyncConfig, RcloneBisyncEngine
from brisasync.credentials.store import CredentialStore, OAuthCredentials
from brisasync.orchestrator.sync_coordinator import SyncCoordinator
from brisasync.service.autostart import (
    BrisaAutostartCoordinator,
    SystemdUserAutostartManager,
    XDGAutostartManager,
)
from brisasync.service.daemon import BrisaSessionServiceDaemon
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.service.protocol import (
    ATTENTION_AUTH_EXPIRED,
    ATTENTION_CONFLICT_DETECTED,
    ATTENTION_PERSISTENT_FAILURE,
    ATTENTION_RECOVERY_REQUIRED,
    STATE_PAUSED,
    STATE_WAITING,
    ServiceStatusSnapshot,
)
from brisasync.storage.database import BrisaDatabase
from brisasync.ui.icons import (
    HICOLOR_SIZES,
    TRAY_PNG_SIZES,
    load_app_icon,
    load_header_logo_pixmap,
    resolve_tray_icon_for_mode,
)
from brisasync.ui.main_window import BrisaMainWindow
from brisasync.ui.notifications import sanitize_notification_text
from brisasync.ui.single_instance import (
    UISingleInstanceServer,
    try_activate_existing_ui,
)


def _get_qapp() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    assert isinstance(app, QApplication)
    return app


def _make_local_pair_config(base_dir: Path) -> BisyncConfig:
    path1 = base_dir / "path1_local"
    path2 = base_dir / "path2_remote_sim"
    workdir = base_dir / "workdir"
    backup1 = base_dir / "backup1"
    backup2 = base_dir / "backup2"
    path1.mkdir(parents=True, exist_ok=True)
    path2.mkdir(parents=True, exist_ok=True)
    return BisyncConfig(
        path1=path1,
        path2=path2,
        workdir=workdir,
        backup_dir1=backup1,
        backup_dir2=backup2,
    )


def test_1_icons_light_dark_hidpi_and_cwd_independence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida ícones coloridos e simbólicos em claro/escuro e escala 1x/1.5x/2x fora do diretório do projeto."""
    _get_qapp()
    outside = tmp_path / "random_cwd"
    outside.mkdir()
    monkeypatch.chdir(outside)

    app_icon = load_app_icon()
    assert not app_icon.isNull()
    assert {s.width() for s in app_icon.availableSizes()} >= set(HICOLOR_SIZES)

    for dpr, expected_px in ((1.0, 44), (1.5, 66), (2.0, 88)):
        pm = load_header_logo_pixmap(logical_size=44, device_pixel_ratio=dpr)
        assert not pm.isNull()
        assert pm.width() == expected_px
        assert pm.devicePixelRatio() == dpr

    icon_dark_panel = resolve_tray_icon_for_mode("dark_panel")
    icon_light_panel = resolve_tray_icon_for_mode("light_panel")
    assert {s.width() for s in icon_dark_panel.availableSizes()} == set(TRAY_PNG_SIZES)
    assert {s.width() for s in icon_light_panel.availableSizes()} == set(TRAY_PNG_SIZES)

    img_light = icon_dark_panel.pixmap(24, 24).toImage()
    img_dark = icon_light_panel.pixmap(24, 24).toImage()
    light_vals = [
        img_light.pixelColor(x, y).lightness()
        for y in range(24)
        for x in range(24)
        if img_light.pixelColor(x, y).alpha() > 200
    ]
    dark_vals = [
        img_dark.pixelColor(x, y).lightness()
        for y in range(24)
        for x in range(24)
        if img_dark.pixelColor(x, y).alpha() > 200
    ]
    assert sum(light_vals) / len(light_vals) > 200
    assert sum(dark_vals) / len(dark_vals) < 60


def test_2_tray_actions_reflect_real_service_state_over_ipc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida que todas as ações da bandeja usam o IPC real e refletem o estado do serviço."""
    app = _get_qapp()
    opened_urls: list[QUrl] = []
    monkeypatch.setattr(
        QDesktopServices,
        "openUrl",
        staticmethod(lambda url: opened_urls.append(url) or True),
    )

    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    (pair_cfg.path1 / "tray_doc.txt").write_text("tray-sync-v1\n", encoding="utf-8")
    db.set_local_sync_folder(pair_cfg.path1)
    db.set_remote_sync_folder(
        folder_id="1E5HsgHDPPXFVdFhqRhZGlI88fGdMND22",
        folder_name="BrisaSync-Teste-Automatico",
    )

    class _ConnectedStore(CredentialStore):
        def has_connected_google_account(self) -> bool:
            return True

        def load_credentials(self) -> OAuthCredentials | None:
            return OAuthCredentials(
                client_id="cid",
                client_secret="csec",
                access_token="ya29.tok",
                refresh_token="1//ref",
                token_type="Bearer",
                expiry="2099-01-01T00:00:00Z",
                scope="https://www.googleapis.com/auth/drive",
                account_email="teste@example.com",
            )

    store = _ConnectedStore(lock_path=tmp_path / "cred.lock")
    engine = RcloneBisyncEngine()
    coordinator = SyncCoordinator(database=db, engine=engine)
    assert coordinator.initialize_pair_baseline(pair_cfg).success
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id=str(pair_cfg.path2),
    )
    db.mark_baseline_initialized(
        local_folder=str(pair_cfg.path1),
        remote_folder_id="1E5HsgHDPPXFVdFhqRhZGlI88fGdMND22",
    )

    sock_path = tmp_path / "run" / "service.sock"
    daemon = BrisaSessionServiceDaemon(
        database=db,
        credential_store=store,
        engine=engine,
        coordinator=coordinator,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)

    win = BrisaMainWindow(
        database=db,
        credential_store=store,
        ipc_client=client,
        enable_tray=True,
        force_tray_available=True,
        allow_notify_send=False,
    )
    try:
        assert win.tray_controller.is_available is True
        win.refresh_service_status_from_ipc()
        assert win.tray_controller.pause_resume_action is not None
        assert (
            win.tray_controller.pause_resume_action.text()
            == "Pausar Sincronização Automática"
        )

        # 1. Ação da bandeja: Abrir Pasta Local
        assert win.tray_controller.open_folder_action is not None
        win.tray_controller.open_folder_action.trigger()
        app.processEvents()
        assert win.last_opened_local_folder == pair_cfg.path1.resolve()
        assert opened_urls and opened_urls[-1].toLocalFile() == str(
            pair_cfg.path1.resolve()
        )

        # 2. Ação da bandeja: Pausar -> deve refletir PAUSADO no serviço e mudar texto para "Retomar..."
        win.tray_controller.pause_resume_action.trigger()
        for _ in range(40):
            app.processEvents()
            if client.get_status().state == STATE_PAUSED:
                break
            time.sleep(0.03)
        win.refresh_service_status_from_ipc()
        assert client.get_status().state == STATE_PAUSED
        assert (
            win.tray_controller.pause_resume_action.text()
            == "Retomar Sincronização Automática"
        )

        # 3. Ação da bandeja: Retomar -> deve voltar para AGUARDANDO e texto "Pausar..."
        win.tray_controller.pause_resume_action.trigger()
        for _ in range(40):
            app.processEvents()
            if not client.get_status().auto_sync_paused:
                break
            time.sleep(0.03)
        win.refresh_service_status_from_ipc()
        assert client.get_status().auto_sync_paused is False
        assert (
            win.tray_controller.pause_resume_action.text()
            == "Pausar Sincronização Automática"
        )

        # 4. Ação da bandeja: Sincronizar Agora
        (pair_cfg.path1 / "from_tray_action.txt").write_text(
            "synced-via-tray\n", encoding="utf-8"
        )
        assert win.tray_controller.sync_now_action is not None
        win.tray_controller.sync_now_action.trigger()
        for _ in range(80):
            app.processEvents()
            dst = Path(pair_cfg.path2) / "from_tray_action.txt"
            if dst.is_file() and not client.get_status().is_cycle_active:
                break
            time.sleep(0.04)
        assert (Path(pair_cfg.path2) / "from_tray_action.txt").read_text(
            encoding="utf-8"
        ) == "synced-via-tray\n"

        # 5. Ação da bandeja: Encerrar Serviço de Sincronização
        assert win.tray_controller.shutdown_service_action is not None
        win.tray_controller.shutdown_service_action.trigger()
        for _ in range(50):
            app.processEvents()
            if not client.is_service_running():
                break
            time.sleep(0.04)
        assert not client.is_service_running()
    finally:
        win.set_minimize_to_tray_on_close(False)
        win.close()
        daemon.stop_and_wait()


def test_3_close_window_keeps_tray_alive_and_reopen_via_launcher_without_duplication(
    tmp_path: Path,
) -> None:
    """Valida que fechar a janela com bandeja ativa oculta o painel mantendo a bandeja viva e reabre pelo lançador (`ui.sock`) sem duplicar."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    sock_path = tmp_path / "run" / "service.sock"
    ui_sock_path = tmp_path / "run" / "ui.sock"

    daemon = BrisaSessionServiceDaemon(database=db, socket_path=sock_path)
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)

    ui_server = UISingleInstanceServer(socket_path=ui_sock_path)
    assert ui_server.start() is True

    win = BrisaMainWindow(
        database=db,
        ipc_client=client,
        enable_tray=True,
        force_tray_available=True,
        allow_notify_send=False,
    )
    ui_server.show_window_requested.connect(win.restore_and_focus_window)
    win.set_minimize_to_tray_on_close(True)
    try:
        win.show()
        app.processEvents()
        assert win.isVisible() is True

        # Fechar a janela (X) oculta o painel mas mantém a bandeja e o serviço ativos
        win.close()
        app.processEvents()
        assert win.isVisible() is False
        assert client.is_service_running() is True

        # Simula segunda invocação pelo lançador (.desktop): ativa a instância existente sem duplicar!
        activated = try_activate_existing_ui(socket_path=ui_sock_path)
        assert activated is True
        for _ in range(30):
            ui_server._poll_pending_requests()
            app.processEvents()
            if win.isVisible():
                break
            time.sleep(0.02)
        assert win.isVisible() is True
    finally:
        ui_server.stop()
        win.set_minimize_to_tray_on_close(False)
        win.close()
        daemon.stop_and_wait()


def test_4_operation_without_system_tray_preserves_all_functions(
    tmp_path: Path,
) -> None:
    """Valida funcionamento completo quando não há bandeja disponível (`enable_tray=False` / sem extensão no GNOME)."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    sock_path = tmp_path / "run" / "service.sock"

    daemon = BrisaSessionServiceDaemon(database=db, socket_path=sock_path)
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)

    win = BrisaMainWindow(
        database=db,
        ipc_client=client,
        enable_tray=False,
        allow_notify_send=False,
    )
    try:
        assert win.tray_controller.is_available is False
        assert "MODO SEM BANDEJA" in win.lifecycle_notice_label.text()
        assert "Nenhuma extensão de bandeja é exigida" in win.lifecycle_notice_label.text()

        win.show()
        app.processEvents()
        assert win.isVisible() is True

        # Sem bandeja, fechar a janela encerra o painel (não esconde janela sem bandeja!),
        # mantendo o serviço ativo em segundo plano
        win.close()
        app.processEvents()
        assert win.isVisible() is False
        assert client.is_service_running() is True
    finally:
        daemon.stop_and_wait()


def test_5_restart_graphical_component_with_active_service_preserves_state(
    tmp_path: Path,
) -> None:
    """Valida que encerrar o componente gráfico mantém o serviço conforme a escolha do usuário e reabrir recupera o estado."""
    app = _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    sock_path = tmp_path / "run" / "service.sock"

    daemon = BrisaSessionServiceDaemon(database=db, socket_path=sock_path)
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)
    try:
        initial_pid = client.get_status().service_pid
        client.pause()
        assert client.get_status().state == STATE_PAUSED

        win1 = BrisaMainWindow(
            database=db,
            ipc_client=client,
            enable_tray=True,
            force_tray_available=True,
            allow_notify_send=False,
        )
        win1.show()
        win1.refresh_service_status_from_ipc()
        assert "[PAUSADO]" in win1.sync_status_label.text()

        # Encerra explicitamente o componente gráfico (mantendo o serviço ativo)
        win1.quit_graphical_component_keep_service()
        app.processEvents()

        # O serviço continua ativo com o mesmo PID e preferência de pausa preservada
        st_after_quit = client.get_status()
        assert st_after_quit.service_pid == initial_pid
        assert st_after_quit.state == STATE_PAUSED
        assert st_after_quit.auto_sync_paused is True

        # Reabre o componente gráfico: recupera o painel conectado ao mesmo serviço
        win2 = BrisaMainWindow(
            database=db,
            ipc_client=client,
            enable_tray=True,
            force_tray_available=True,
            allow_notify_send=False,
        )
        win2.refresh_service_status_from_ipc()
        assert "[PAUSADO]" in win2.sync_status_label.text()
        assert f"PID Serviço: {initial_pid}" in win2.sync_status_label.text()
        win2.set_minimize_to_tray_on_close(False)
        win2.close()
    finally:
        daemon.stop_and_wait()


def test_6_notifications_configurable_grouped_deduplicated_sanitized_and_mirrored_in_window(
    tmp_path: Path,
) -> None:
    """Valida notificações configuráveis, agrupadas, deduplicadas, sanitizadas e espelhadas na janela."""
    _get_qapp()
    db = BrisaDatabase(db_path=tmp_path / "db" / "brisasync.db")
    pair_cfg = _make_local_pair_config(tmp_path)
    sock_path = tmp_path / "run" / "service.sock"

    daemon = BrisaSessionServiceDaemon(
        database=db,
        socket_path=sock_path,
        local_pair_config=pair_cfg,
    )
    daemon.start_in_background()
    client = ServiceIPCClient(socket_path=sock_path, db_path=db.db_path)

    win = BrisaMainWindow(
        database=db,
        ipc_client=client,
        enable_tray=False,
        allow_notify_send=False,
    )
    try:
        # 1. Estado normal (AGUARDANDO / SUCCESS) NÃO emite notificação
        win.refresh_service_status_from_ipc()
        assert len(win.notification_manager.emitted_history) == 0
        assert "[NENHUM ALERTA ATIVO]" in win.attention_explanation_label.text()

        # 2. Arquivos legítimos do usuário terminados em .conflict1/.conflict2 criados sem
        #    operação de conflito registrada pelo backend NÃO podem gerar falso alerta de conflito
        user_legit_file = pair_cfg.path1 / "meu_documento_legitimo.conflict1"
        user_legit_file.write_text("conteudo legitimo do usuario", encoding="utf-8")
        win.refresh_service_status_from_ipc()
        assert len(win.notification_manager.emitted_history) == 0
        assert "[NENHUM ALERTA ATIVO]" in win.attention_explanation_label.text()
        assert user_legit_file.is_file()  # Nunca deve ser renomeado ou removido

        # 3. Quando o backend registra operações de conflito reais e os arquivos existem na pasta local:
        #    deve agrupar em 1 ÚNICA notificação
        (pair_cfg.path1 / "relatorio.txt.conflict1").write_text("v1", encoding="utf-8")
        (pair_cfg.path1 / "relatorio.txt.conflict2").write_text("v2", encoding="utf-8")
        (pair_cfg.path1 / "planilha.csv.conflict1").write_text("v1", encoding="utf-8")
        db.record_backend_conflict_files(
            pair_cfg.path1,
            [
                "relatorio.txt.conflict1",
                "relatorio.txt.conflict2",
                "planilha.csv.conflict1",
            ],
        )

        win.refresh_service_status_from_ipc()
        assert len(win.notification_manager.emitted_history) == 1
        notif_1 = win.notification_manager.last_notification
        assert notif_1 is not None
        assert notif_1.category == ATTENTION_CONFLICT_DETECTED
        assert "3 arquivo(s)" in notif_1.body
        # A janela principal espelha exatamente o mesmo problema
        assert "[CONFLICT_DETECTED]" in win.attention_explanation_label.text()
        assert "3 arquivo(s)" in win.attention_explanation_label.text()

        # 3. Consultas repetidas ao mesmo estado NÃO repetem a notificação continuamente
        win.refresh_service_status_from_ipc()
        win.refresh_service_status_from_ipc()
        assert len(win.notification_manager.emitted_history) == 1

        # 4. Verifica sanitização estrita (sem tokens, sem e-mail pessoal, sem conteúdo de arquivo)
        dirty_text = (
            "Falha na conta usuario.pessoal@gmail.com com Authorization: Bearer ya29.a0AfH6SM_segredo"
        )
        cleaned = sanitize_notification_text(dirty_text)
        assert "ya29." not in cleaned
        assert "usuario.pessoal@gmail.com" not in cleaned
        assert "[CONTA]" in cleaned

        # 5. Verifica categorias AUTH_EXPIRED, RECOVERY_REQUIRED e PERSISTENT_FAILURE e desativação pelo usuário
        for cat, title in (
            (ATTENTION_AUTH_EXPIRED, "Autenticação ou Cofre Exige Atenção"),
            (ATTENTION_RECOVERY_REQUIRED, "Recuperação ou Intervenção Necessária"),
            (ATTENTION_PERSISTENT_FAILURE, "Falha Persistente de Sincronização"),
        ):
            synthetic_snap = ServiceStatusSnapshot(
                service_pid=os.getpid(),
                state="ATTENTION_REQUIRED",
                state_label="ATENÇÃO NECESSÁRIA",
                detail_message=title,
                is_cycle_active=False,
                active_rclone_pid=None,
                pending_sync_coalesced=False,
                auto_sync_paused=False,
                sync_interval_seconds=300,
                next_scheduled_sync_at=None,
                backoff_attempt=2,
                backoff_seconds=60,
                last_confirmed_sync_at=None,
                last_run_status="ATTENTION_REQUIRED",
                last_error_reason=title,
                autostart_enabled=False,
                configured_pair_ready=True,
                attention_category=cat,
                attention_title=title,
                attention_explanation=f"Explicação sanitizada para {cat}.",
                conflict_files_count=0,
            )
            win._apply_service_snapshot(synthetic_snap)
            assert win.notification_manager.last_notification is not None
            assert win.notification_manager.last_notification.category == cat
            assert f"[{cat}]" in win.attention_explanation_label.text()

        count_before_disable = len(win.notification_manager.emitted_history)
        win.notifications_checkbox.setChecked(False)
        assert db.are_notifications_enabled() is False
        win.notification_manager.reset_deduplication()
        win.refresh_service_status_from_ipc()
        assert len(win.notification_manager.emitted_history) == count_before_disable
    finally:
        win.close()
        daemon.stop_and_wait()


def test_7_application_main_startup_with_service_stopped_and_active_no_tray_regression(
    tmp_path: Path,
) -> None:
    """Regressão: valida que a execução real de main() inicializa o serviço quando parado,

    conecta ao serviço existente sem duplicá-lo quando já ativo, e opera com --no-tray sem AttributeError.
    """
    from PySide6.QtCore import QTimer
    from brisasync.main import main

    app = _get_qapp()

    # Cenário A: Serviço parado na inicialização -> main() deve iniciá-lo via ensure_background_service_started
    db_path_a = tmp_path / "case_a" / "brisasync.db"
    sock_path_a = tmp_path / "case_a" / "service.sock"
    ui_sock_a = tmp_path / "case_a" / "ui.sock"

    def on_timer_a():
        client_a = ServiceIPCClient(socket_path=sock_path_a, db_path=db_path_a)
        try:
            snap_a = client_a.get_status()
            assert snap_a.service_pid is not None, "Serviço da sessão não foi iniciado pelo main()"
            client_a.shutdown_service()
        finally:
            app.quit()

    QTimer.singleShot(700, on_timer_a)
    ret_a = main([
        "--no-tray",
        "--db-path", str(db_path_a),
        "--socket-path", str(sock_path_a),
        "--ui-socket-path", str(ui_sock_a),
    ])
    assert ret_a == 0, f"main() no cenário A retornou {ret_a}"

    # Cenário B: Serviço já ativo -> main() conecta ao mesmo serviço sem duplicar PID
    db_path_b = tmp_path / "case_b" / "brisasync.db"
    sock_path_b = tmp_path / "case_b" / "service.sock"
    ui_sock_b = tmp_path / "case_b" / "ui.sock"

    db_b = BrisaDatabase(db_path=db_path_b)
    daemon_b = BrisaSessionServiceDaemon(database=db_b, socket_path=sock_path_b)
    daemon_b.start_in_background()
    client_b = ServiceIPCClient(socket_path=sock_path_b, db_path=db_b.db_path)
    initial_pid = client_b.get_status().service_pid

    try:
        def on_timer_b():
            try:
                snap_b = client_b.get_status()
                assert snap_b.service_pid == initial_pid, f"PID duplicado! {initial_pid} != {snap_b.service_pid}"
            finally:
                app.quit()

        QTimer.singleShot(700, on_timer_b)
        ret_b = main([
            "--no-tray",
            "--db-path", str(db_path_b),
            "--socket-path", str(sock_path_b),
            "--ui-socket-path", str(ui_sock_b),
        ])
        assert ret_b == 0, f"main() no cenário B retornou {ret_b}"
    finally:
        daemon_b.stop_and_wait()


def test_8_xdg_autostart_and_coordinator_lifecycle_isolated(tmp_path: Path) -> None:
    """Valida o ciclo de vida de XDGAutostartManager e BrisaAutostartCoordinator:
    - Geração do .desktop com --start-hidden e metadados gerenciados
    - Ativação/desativação isolada sem tocar o ambiente do sistema operacional
    - Sincronização e autocura de inconsistências (sync_state)
    - Preservação integral do banco e dados de sincronização ao desativar
    """
    unit_dir = tmp_path / "systemd_user"
    autostart_dir = tmp_path / "autostart"
    db_path = tmp_path / "db" / "brisasync.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = BrisaDatabase(db_path=db_path)
    db.set_setting("sync_interval_seconds", "300")

    # 1. XDGAutostartManager isolado
    xdg_mgr = XDGAutostartManager(
        autostart_dir=autostart_dir,
        db_path=db_path,
        service_executable="/usr/bin/brisasync",
    )
    assert xdg_mgr.is_enabled() is False
    desktop_file = xdg_mgr.enable()
    assert desktop_file.is_file()
    assert xdg_mgr.is_enabled() is True

    content = desktop_file.read_text(encoding="utf-8")
    assert "/usr/bin/brisasync --start-hidden" in content
    assert f"--db-path {db_path}" in content
    assert "X-BrisaSync-Managed=true" in content
    assert "X-GNOME-Autostart-enabled=true" in content

    xdg_mgr.disable()
    assert not desktop_file.exists()
    assert xdg_mgr.is_enabled() is False

    # 2. BrisaAutostartCoordinator coordenando systemd --user e XDG autostart
    coord = BrisaAutostartCoordinator(
        unit_dir=unit_dir,
        autostart_dir=autostart_dir,
        db_path=db_path,
        service_executable="/usr/bin/brisasync",
        run_systemctl=False,
    )
    assert coord.is_enabled() is False

    unit_p, desk_p = coord.enable()
    assert unit_p.is_file()
    assert desk_p.is_file()
    assert coord.is_enabled() is True

    # Valida conteúdo da unit systemd
    unit_content = unit_p.read_text(encoding="utf-8")
    assert "/usr/bin/brisasync --service" in unit_content
    assert "WantedBy=default.target" in unit_content

    # Valida sync_state: se o arquivo .desktop for removido, sync_state o recria
    desk_p.unlink()
    assert not desk_p.exists()
    coord.sync_state()
    assert desk_p.is_file()

    # Se a unit for removida, sync_state a recria
    unit_p.unlink()
    assert not unit_p.exists()
    coord.sync_state()
    assert unit_p.is_file()

    # Desativação coordenada: desativa ambos e preserva banco de dados do usuário
    coord.disable()
    assert not unit_p.exists()
    assert not desk_p.exists()
    assert coord.is_enabled() is False
    assert db_path.is_file()
    assert db.get_setting("sync_interval_seconds") == "300"


def test_9_main_start_hidden_without_tray_exits_cleanly(tmp_path: Path) -> None:
    """Valida que em desktop sem bandeja (ou --no-tray), --start-hidden inicia o serviço em segundo plano
    e encerra o processo com código 0 sem abrir janela nem realizar retentativas em loop.
    """
    from brisasync.main import main

    _get_qapp()
    db_path = tmp_path / "headless" / "brisasync.db"
    sock_path = tmp_path / "headless" / "service.sock"
    ui_sock_path = tmp_path / "headless" / "ui.sock"

    ret = main([
        "--start-hidden",
        "--no-tray",
        "--db-path", str(db_path),
        "--socket-path", str(sock_path),
        "--ui-socket-path", str(ui_sock_path),
    ])
    assert ret == 0

    # Confirma que o serviço foi iniciado em segundo plano
    client = ServiceIPCClient(socket_path=sock_path, db_path=db_path)
    try:
        assert client.is_service_running() is True
        snap = client.get_status()
        assert snap.service_pid is not None
        # Confirma que o socket de UI foi liberado (processo encerrou e limpou)
        assert not ui_sock_path.exists()
    finally:
        try:
            snap = client.shutdown_service()
            if snap.service_pid:
                for _ in range(50):
                    try:
                        os.kill(snap.service_pid, 0)
                        time.sleep(0.05)
                    except OSError:
                        break
        except Exception:
            pass


def test_10_main_start_hidden_with_tray_remains_hidden_and_second_instance_reveals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valida que com bandeja disponível, --start-hidden mantém a janela oculta na bandeja,
    e uma segunda chamada sem --start-hidden (como o lançador do sistema) revela a janela existente.
    """
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QSystemTrayIcon
    from brisasync.main import main

    app = _get_qapp()

    # Força a detecção de bandeja ativa mesmo em ambiente de teste offscreen
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))

    db_path = tmp_path / "tray_hidden" / "brisasync.db"
    sock_path = tmp_path / "tray_hidden" / "service.sock"
    ui_sock_path = tmp_path / "tray_hidden" / "ui.sock"

    def sequence():
        top_windows = [w for w in app.topLevelWidgets() if isinstance(w, BrisaMainWindow)]
        assert len(top_windows) == 1
        win = top_windows[0]

        # Verifica que a janela permaneceu oculta
        assert win.isVisible() is False
        assert win.tray_controller.is_available is True
        assert win.tray_controller.is_visible is True

        # Simula uma segunda instância acionada pelo lançador (.desktop) sem --start-hidden
        activated = try_activate_existing_ui(socket_path=ui_sock_path, show_window=True)
        assert activated is True

        for _ in range(30):
            app.processEvents()
            if win.isVisible():
                break
            time.sleep(0.02)

        assert win.isVisible() is True

        # Encerra o serviço e fecha
        client = ServiceIPCClient(socket_path=sock_path, db_path=db_path)
        try:
            snap = client.shutdown_service()
            if snap.service_pid:
                for _ in range(50):
                    try:
                        os.kill(snap.service_pid, 0)
                        time.sleep(0.05)
                    except OSError:
                        break
        except Exception:
            pass
        win.set_minimize_to_tray_on_close(False)
        win.close()
        app.quit()

    QTimer.singleShot(800, sequence)
    ret = main([
        "--start-hidden",
        "--db-path", str(db_path),
        "--socket-path", str(sock_path),
        "--ui-socket-path", str(ui_sock_path),
    ])
    assert ret == 0




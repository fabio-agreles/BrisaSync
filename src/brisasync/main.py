"""Ponto de entrada da aplicação desktop e do serviço de sessão BrisaSync."""

from __future__ import annotations

import argparse
import json
import sys

from brisasync import __app_id__, __app_name__, __version__
from brisasync.orchestrator.diagnostics import collect_system_diagnostics
from brisasync.service.daemon import (
    BrisaSessionServiceDaemon,
    ServiceAlreadyRunningError,
)
from brisasync.service.ipc_client import ServiceIPCClient
from brisasync.storage.database import BrisaDatabase


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=__app_id__,
        description="BrisaSync — Sincronizador bidirecional Open Source para Linux Desktop",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} {__version__}",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Executa o diagnóstico real das dependências no terminal (JSON) e encerra.",
    )
    parser.add_argument(
        "--service",
        action="store_true",
        help="Executa o serviço sem root da sessão do usuário (proprietário único do agendamento e rclone bisync).",
    )
    parser.add_argument(
        "--no-tray",
        action="store_true",
        help="Inicia a interface gráfica sem bandeja do sistema (modo somente janela).",
    )
    parser.add_argument(
        "--start-hidden",
        "--minimized",
        action="store_true",
        dest="start_hidden",
        help="Inicia a interface gráfica oculta na bandeja do sistema sem exibir a janela principal.",
    )
    parser.add_argument(
        "--socket-path",
        type=str,
        default=None,
        help="Caminho opcional para o socket AF_UNIX do serviço IPC da sessão.",
    )
    parser.add_argument(
        "--ui-socket-path",
        type=str,
        default=None,
        help="Caminho opcional para o socket AF_UNIX de instância única da interface gráfica.",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=None,
        help="Caminho opcional para o arquivo SQLite de configuração.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.diagnose:
        diag = collect_system_diagnostics()
        payload = {
            "app": __app_name__,
            "version": __version__,
            "all_critical_ok": diag.all_critical_ok,
            "items": [
                {
                    "component": item.component,
                    "status_code": item.status_code,
                    "status_label": item.status_label,
                    "details": item.details,
                }
                for item in diag.items
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if diag.all_critical_ok else 1

    database = BrisaDatabase(db_path=args.db_path)

    if args.service:
        daemon = BrisaSessionServiceDaemon(
            database=database,
            socket_path=args.socket_path,
        )
        try:
            return daemon.serve_forever()
        except ServiceAlreadyRunningError as exc:
            print(str(exc), file=sys.stderr)
            return 0

    from brisasync.ui.single_instance import (
        UISingleInstanceServer,
        try_activate_existing_ui,
    )

    # Se o componente gráfico já estiver ativo na sessão (visível ou oculto na bandeja):
    # - Se o usuário abriu pelo lançador (sem --start-hidden), solicita reabertura e foco da janela existente.
    # - Se foi invocado com --start-hidden (ex: login repetido), apenas confirma presença sem abrir janela.
    if try_activate_existing_ui(
        socket_path=args.ui_socket_path,
        show_window=not args.start_hidden,
    ):
        return 0

    from PySide6.QtWidgets import QApplication

    from brisasync.i18n import set_current_language
    from brisasync.ui.icons import load_app_icon
    from brisasync.ui.main_window import BrisaMainWindow
    from brisasync.ui.styles import apply_brisasync_theme

    app = QApplication.instance() or QApplication(
        sys.argv if argv is None else [sys.argv[0], *argv]
    )
    saved_lang_pref = database.get_language_preference(default="pt_BR")
    set_current_language(saved_lang_pref)

    saved_theme_pref = database.get_theme_preference(default="system")
    apply_brisasync_theme(app, theme_preference=saved_theme_pref)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(__app_id__)
    app.setWindowIcon(load_app_icon())

    ui_server = UISingleInstanceServer(socket_path=args.ui_socket_path)
    if not ui_server.start():
        try_activate_existing_ui(
            socket_path=args.ui_socket_path,
            show_window=not args.start_hidden,
        )
        return 0

    ipc_client = ServiceIPCClient(
        socket_path=args.socket_path,
        db_path=database.db_path,
    )
    window = BrisaMainWindow(
        database=database,
        ipc_client=ipc_client,
        enable_tray=not args.no_tray,
    )
    ui_server.show_window_requested.connect(window.restore_and_focus_window)

    # Quando a bandeja está disponível e ativa, fechar a janela mantém a bandeja viva
    tray_active = window.tray_controller.is_available
    app.setQuitOnLastWindowClosed(not tray_active)
    window.set_minimize_to_tray_on_close(tray_active)

    window.ensure_background_service_started()

    try:
        if args.start_hidden:
            if not tray_active:
                # Em desktop sem bandeja disponível, mantém o serviço de sincronização
                # funcional em segundo plano e encerra a interface sem abrir janela inesperada
                # nem realizar retentativas em loop. O painel permanece acessível via lançador.
                return 0
            # Com bandeja disponível, não abre a janela principal; permanece oculta na bandeja
        else:
            window.show()
            window.raise_()
            window.activateWindow()

        return app.exec()
    finally:
        ui_server.stop()


if __name__ == "__main__":
    raise SystemExit(main())

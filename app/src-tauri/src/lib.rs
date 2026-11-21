// O autostart do Linux fala D-Bus com o portal do Flatpak; no Windows quem cuida
// disso é o plugin do Tauri (chave `Run` do registro), então o módulo é outro.
#[cfg(unix)]
#[path = "autostart.rs"]
mod autostart;
#[cfg(not(unix))]
#[path = "autostart_outro.rs"]
mod autostart;
mod autosync;
mod commands;
mod error;
mod idioma;
mod login_dropbox;
mod login_google;
mod login_microsoft;
mod models;
mod oauth;
mod monitor;
mod rclone;
mod remote_changes;
mod retry;
mod state;
mod tray;

use state::AppState;
use tauri::{Emitter, Manager};

pub fn run() {
    tauri::Builder::default()
        // Primeiro plugin da lista: se já existe um BrisaSync rodando, esta instância
        // avisa a outra e termina em vez de abrir um segundo motor de sincronização.
        .plugin(tauri_plugin_single_instance::init(|app, args, _cwd| {
            // Início automático com o app já aberto não deve trazer a janela à frente.
            if args.iter().any(|arg| arg == "--minimized") {
                return;
            }
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .setup(|app| {
            let dir = app.path().app_config_dir()?;
            std::fs::create_dir_all(&dir)?;
            let estado = AppState::load(dir);
            // Um `profiles.json`/`settings.json` ilegível não pode passar em
            // silêncio: vira uma entrada na atividade (com o caminho da cópia).
            let recuperacao = estado.recuperacao.clone();
            // A bandeja é montada aqui, antes de a interface ler os ajustes: o
            // idioma salvo precisa entrar antes dela.
            let idioma_salvo = estado
                .settings
                .try_lock()
                .map(|guardado| guardado.language.clone())
                .unwrap_or_else(|_| "pt".to_string());
            idioma::definir(&idioma_salvo);
            app.manage(estado);

            if !recuperacao.is_empty() {
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let estado = handle.state::<AppState>();
                    for aviso in recuperacao {
                        estado
                            .push_activity(
                                "error",
                                idioma::texto(
                                    "Configuração recuperada",
                                    "Configuration recovered",
                                ),
                                &aviso,
                                None,
                            )
                            .await;
                    }
                    let _ = handle.emit("sync://changed", ());
                });
            }

            tray::init(app)?;
            monitor::spawn(app.handle().clone());
            autosync::spawn(app.handle().clone());

            if std::env::args().any(|argument| argument == "--minimized") {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.hide();
                }
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let app = window.app_handle();
                // Ajuste "fechar a janela encerra o app": fecha de verdade e o
                // motor para junto (o `RunEvent::ExitRequested` desliga o rclone).
                if app.state::<AppState>().encerra_ao_fechar() {
                    app.exit(0);
                    return;
                }
                // O app continua sincronizando na bandeja.
                api.prevent_close();
                let _ = window.hide();
                // Explica para onde a janela foi — uma vez por instalação.
                tray::avisar_bandeja(app);
            }
        })
        .invoke_handler(tauri::generate_handler![
            commands::engine_status,
            commands::list_accounts,
            commands::connect_account,
            commands::list_profiles,
            commands::create_profile,
            commands::update_profile,
            commands::delete_profile,
            commands::delete_account,
            commands::start_sync,
            commands::set_paused,
            commands::stop_all,
            commands::sync_status,
            commands::list_remote,
            commands::folder_size,
            commands::upload_file,
            commands::download_file,
            commands::scan_conflicts,
            commands::resolve_conflict,
            commands::cancel_authorization,
            commands::account_emails,
            commands::account_usage,
            commands::recent_activity,
            commands::clear_activity,
            commands::set_tray_theme,
            commands::get_settings,
            commands::save_settings,
            commands::set_autostart,
            commands::autostart_enabled,
            commands::reveal_path,
            commands::open_config_folder,
            commands::save_diagnostics,
            commands::check_update,
            commands::install_update,
            commands::open_url,
        commands::oauth_info,
            commands::quit_app,
            commands::request_quit,
            commands::hide_window,
        ])
        .build(tauri::generate_context!())
        .expect("falha ao iniciar o BrisaSync")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { .. } = event {
                let state = app_handle.state::<AppState>();
                tauri::async_runtime::block_on(state.rclone.stop());
            }
        });
}

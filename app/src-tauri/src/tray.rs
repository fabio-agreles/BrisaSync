use std::{
    path::PathBuf,
    sync::atomic::{AtomicBool, AtomicU8, AtomicU16, Ordering},
};
use tauri::{
    image::Image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, TrayIconBuilder, TrayIconEvent},
    App, AppHandle, Emitter, Manager, Theme,
};

/// Ícones da bandeja embutidos no binário: nada para procurar em disco — e o
/// Flatpak não deixaria o app ler os ícones fora do sandbox.
///
/// São dois desenhos (traço escuro para painel claro, traço branco para painel
/// escuro) em seis estados: parado, sincronizando, em dia, pausado, erro e
/// offline. O painel do KDE/GNOME não recolore ícone de bandeja, então a cor e o
/// estado vêm daqui.
const LIGHT_IDLE: &[u8] = include_bytes!("../icons/tray/light-idle-64.png");
const LIGHT_SYNCING: &[u8] = include_bytes!("../icons/tray/light-syncing-64.png");
const LIGHT_SYNCED: &[u8] = include_bytes!("../icons/tray/light-synced-64.png");
const LIGHT_PAUSED: &[u8] = include_bytes!("../icons/tray/light-paused-64.png");
const LIGHT_ERROR: &[u8] = include_bytes!("../icons/tray/light-error-64.png");
const LIGHT_OFFLINE: &[u8] = include_bytes!("../icons/tray/light-offline-64.png");
const DARK_IDLE: &[u8] = include_bytes!("../icons/tray/dark-idle-64.png");
const DARK_SYNCING: &[u8] = include_bytes!("../icons/tray/dark-syncing-64.png");
const DARK_SYNCED: &[u8] = include_bytes!("../icons/tray/dark-synced-64.png");
const DARK_PAUSED: &[u8] = include_bytes!("../icons/tray/dark-paused-64.png");
const DARK_ERROR: &[u8] = include_bytes!("../icons/tray/dark-error-64.png");
const DARK_OFFLINE: &[u8] = include_bytes!("../icons/tray/dark-offline-64.png");

/// O que a bandeja está mostrando. `Erro` e `Offline` só aparecem quando o
/// monitor percebe a condição — não são estados da interface.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Estado {
    Parado = 0,
    Sincronizando = 1,
    EmDia = 2,
    Pausado = 3,
    Erro = 4,
    Offline = 5,
}

impl Estado {
    fn de_u8(valor: u8) -> Self {
        match valor {
            1 => Self::Sincronizando,
            2 => Self::EmDia,
            3 => Self::Pausado,
            4 => Self::Erro,
            5 => Self::Offline,
            _ => Self::Parado,
        }
    }
}

/// Pasta onde o ícone é gravado para o painel ler.
///
/// O `tray-icon` grava por padrão em `$XDG_RUNTIME_DIR/tray-icon` — e dentro do
/// Flatpak esse caminho é um tmpfs privado do sandbox: o painel do KDE/GNOME, do
/// lado de fora, não enxerga o arquivo e cai no ícone do aplicativo. Usando o
/// cache (que é visível no sistema) o painel lê o PNG certo.
fn pasta_dos_icones() -> PathBuf {
    let base = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")))
        // Windows não tem XDG: `%LOCALAPPDATA%` é o equivalente de cache.
        .or_else(|| std::env::var_os("LOCALAPPDATA").map(PathBuf::from))
        .unwrap_or_else(std::env::temp_dir);
    let dir = base.join("nuvem").join("bandeja");
    let _ = std::fs::create_dir_all(&dir);
    dir
}

/// Tema em uso (true = escuro) e estado atual. O front-end manda o tema ao
/// montar; o monitor manda o estado a cada varredura.
static ESCURO: AtomicBool = AtomicBool::new(false);
static ESTADO_U8: AtomicU8 = AtomicU8::new(0);
/// Combinação já aplicada (estado × tema) para não reescrever o PNG à toa: o
/// painel pisca quando o arquivo é regravado sem mudança.
static APLICADO: AtomicU16 = AtomicU16::new(u16::MAX);

fn bytes(escuro: bool, estado: Estado) -> &'static [u8] {
    // Se o tema/painel do sistema for escuro (escuro = true), o ícone da bandeja
    // precisa ser CLARO (LIGHT_*, branco) para dar contraste contra o fundo escuro.
    // Se o painel for claro (escuro = false), o ícone precisa ser ESCURO (DARK_*, preto).
    match (escuro, estado) {
        (true, Estado::Sincronizando) => LIGHT_SYNCING,
        (true, Estado::EmDia) => LIGHT_SYNCED,
        (true, Estado::Pausado) => LIGHT_PAUSED,
        (true, Estado::Erro) => LIGHT_ERROR,
        (true, Estado::Offline) => LIGHT_OFFLINE,
        (true, Estado::Parado) => LIGHT_IDLE,
        (false, Estado::Sincronizando) => DARK_SYNCING,
        (false, Estado::EmDia) => DARK_SYNCED,
        (false, Estado::Pausado) => DARK_PAUSED,
        (false, Estado::Erro) => DARK_ERROR,
        (false, Estado::Offline) => DARK_OFFLINE,
        (false, Estado::Parado) => DARK_IDLE,
    }
}

fn icone(escuro: bool, estado: Estado) -> Option<Image<'static>> {
    match Image::from_bytes(bytes(escuro, estado)) {
        Ok(icon) => Some(icon),
        Err(error) => {
            eprintln!("bandeja: ícone inválido ({estado:?}): {error}");
            None
        }
    }
}

fn aplicar(app: &AppHandle, escuro: bool, estado: Estado) {
    let chave = (estado as u16) * 2 + u16::from(escuro);
    if APLICADO.swap(chave, Ordering::Relaxed) == chave {
        return;
    }
    let Some(tray) = app.tray_by_id("main") else {
        return;
    };
    if let Some(icon) = icone(escuro, estado) {
        if let Err(error) = tray.set_icon(Some(icon)) {
            eprintln!("bandeja: não foi possível trocar o ícone: {error}");
        }
    }
}

/// Troca o ícone da bandeja conforme o tema em uso (preto no painel claro,
/// branco no escuro).
pub fn apply_theme(app: &AppHandle, escuro: bool) {
    ESCURO.store(escuro, Ordering::Relaxed);
    aplicar(app, escuro, Estado::de_u8(ESTADO_U8.load(Ordering::Relaxed)));
}

/// Troca o ícone conforme o estado da sincronização, mantendo o tema.
pub fn apply_estado(app: &AppHandle, estado: Estado) {
    ESTADO_U8.store(estado as u8, Ordering::Relaxed);
    aplicar(app, ESCURO.load(Ordering::Relaxed), estado);
}

/// Os três itens do menu, com os textos nos dois idiomas.
const ROTULOS: [(&str, &str, &str); 3] = [
    ("open", "Abrir BrisaSync", "Open BrisaSync"),
    ("sync", "Sincronizar agora", "Sync now"),
    ("quit", "Sair", "Quit"),
];

/// Monta o menu da bandeja no idioma em uso. Montar de novo (em vez de mexer
/// nos itens um a um) é o caminho que a API do Tauri 2 oferece: o ícone da
/// bandeja aceita `set_menu`, mas não devolve o menu que está lá.
fn montar_menu(app: &AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let open = MenuItem::with_id(
        app,
        ROTULOS[0].0,
        crate::idioma::texto(ROTULOS[0].1, ROTULOS[0].2),
        true,
        None::<&str>,
    )?;
    let sync = MenuItem::with_id(
        app,
        ROTULOS[1].0,
        crate::idioma::texto(ROTULOS[1].1, ROTULOS[1].2),
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(
        app,
        ROTULOS[2].0,
        crate::idioma::texto(ROTULOS[2].1, ROTULOS[2].2),
        true,
        None::<&str>,
    )?;
    Menu::with_items(app, &[&open, &sync, &quit])
}

/// Reescreve o menu da bandeja no idioma escolhido. Chamado quando o usuário
/// troca o idioma em Ajustes: a bandeja existe desde a abertura do app, antes
/// de a interface conseguir mudar qualquer coisa.
pub fn aplicar_idioma(app: &AppHandle) {
    let Some(tray) = app.tray_by_id("main") else {
        return;
    };
    match montar_menu(app) {
        Ok(menu) => {
            if let Err(error) = tray.set_menu(Some(menu)) {
                eprintln!("bandeja: não foi possível trocar os rótulos do menu: {error}");
            }
        }
        Err(error) => eprintln!("bandeja: não foi possível montar o menu traduzido: {error}"),
    }
}

/// "Sair" na bandeja e o botão de Ajustes passam por aqui.
///
/// Sem tarefa em andamento, encerra na hora: perguntar por nada só atrapalha.
/// Com sincronização rodando, a janela volta à frente com a pergunta — matar o
/// app no meio de um bisync é justamente o que obriga a ressincronização
/// completa na próxima abertura.
pub fn pedir_saida(app: &AppHandle) {
    let app = app.clone();
    tauri::async_runtime::spawn(async move {
        let ativo = {
            let estado = app.state::<crate::state::AppState>();
            !estado.running_job_ids().await.is_empty()
        };
        if !ativo {
            app.exit(0);
            return;
        }
        let escondida = app
            .get_webview_window("main")
            .and_then(|window| window.is_visible().ok())
            .map(|visivel| !visivel)
            .unwrap_or(false);
        if let Some(window) = app.get_webview_window("main") {
            let _ = window.show();
            let _ = window.unminimize();
            let _ = window.set_focus();
        }
        // A interface monta a pergunta (três botões, "Continuar em segundo
        // plano" no padrão). A bandeja não tem como oferecer três opções.
        let _ = app.emit("ui://confirm-exit", escondida);
    });
}

/// Primeiro fechamento da janela: explica uma única vez que o app não morreu,
/// só saiu da frente. Sem isso a impressão é de que ele "sumiu" — e a próxima
/// ideia é abrir uma segunda cópia.
pub fn avisar_bandeja(app: &AppHandle) {
    let estado = app.state::<crate::state::AppState>();
    if estado.bandeja_avisada() {
        return;
    }
    estado.marcar_bandeja_avisada();
    use tauri_plugin_notification::NotificationExt;
    let _ = app
        .notification()
        .builder()
        .title(crate::idioma::texto(
            "BrisaSync continua rodando",
            "BrisaSync keeps running",
        ))
        .body(crate::idioma::texto(
            "A janela fechou, mas a sincronização segue na bandeja. Clique no ícone para abrir de novo — ou use Sair na bandeja para encerrar.",
            "The window closed, but syncing continues in the tray. Click the tray icon to open it again — or use Quit in the tray to exit.",
        ))
        .show();
}

pub fn init(app: &mut App) -> tauri::Result<()> {
    let menu = montar_menu(app.handle())?;

    // Antes de a janela carregar o tema, usa o do sistema. O front-end confirma
    // (ou corrige) assim que monta, pelo comando `set_tray_theme`.
    let escuro = app
        .get_webview_window("main")
        .and_then(|window| window.theme().ok())
        .map(|theme| theme == Theme::Dark)
        .unwrap_or(true);

    let mut builder = TrayIconBuilder::with_id("main")
        .temp_dir_path(pasta_dos_icones())
        .tooltip("BrisaSync")
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
            "sync" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
                let _ = app.emit("ui://sync-all", ());
            }
            "quit" => pedir_saida(app),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                ..
            } = event
            {
                let app = tray.app_handle();
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
        });

    if let Some(icon) = icone(escuro, Estado::Parado) {
        builder = builder.icon(icon);
    }
    ESCURO.store(escuro, Ordering::Relaxed);
    ESTADO_U8.store(Estado::Parado as u8, Ordering::Relaxed);
    APLICADO.store(u16::from(escuro), Ordering::Relaxed);

    builder.build(app)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{bytes, icone, Estado};

    /// A bandeja é montada em `tray::init` — com menu, tema e estado. Um
    /// `app.trayIcon` no `tauri.conf.json` faria o Tauri criar **outro** ícone:
    /// no Windows apareciam dois na área de notificação.
    #[test]
    fn bandeja_e_criada_so_pelo_codigo() {
        let conf = include_str!("../tauri.conf.json");
        assert!(
            !conf.contains("\"trayIcon\""),
            "tire o bloco `trayIcon` do tauri.conf.json: ele cria um segundo ícone"
        );
    }

    /// Os doze PNGs viajam embutidos: se um deles quebrar (ou sumir do
    /// repositório), o `cargo test` avisa antes de o app abrir sem ícone.
    #[test]
    fn icones_da_bandeja_carregam() {
        let estados = [
            Estado::Parado,
            Estado::Sincronizando,
            Estado::EmDia,
            Estado::Pausado,
            Estado::Erro,
            Estado::Offline,
        ];
        for escuro in [false, true] {
            for estado in estados {
                let icon = icone(escuro, estado).expect("ícone embutido");
                assert_eq!((icon.width(), icon.height()), (64, 64));
                // O Tauri só aceita o ícone se o buffer RGBA tiver o tamanho
                // exato; caso contrário descarta em silêncio e a bandeja cai no
                // ícone do aplicativo.
                assert_eq!(icon.rgba().len(), 64 * 64 * 4);
            }
        }
    }

    /// Cada estado tem um desenho próprio: dois estados iguais seriam um erro de
    /// empacotamento que passa despercebido na tela.
    #[test]
    fn cada_estado_tem_desenho_proprio() {
        let estados = [
            Estado::Parado,
            Estado::Sincronizando,
            Estado::EmDia,
            Estado::Pausado,
            Estado::Erro,
            Estado::Offline,
        ];
        for escuro in [false, true] {
            let mut vistos: Vec<&[u8]> = Vec::new();
            for estado in estados {
                let desenho = bytes(escuro, estado);
                assert!(
                    !vistos.contains(&desenho),
                    "estado {estado:?} repete o desenho de outro (tema escuro: {escuro})"
                );
                vistos.push(desenho);
            }
        }
    }
}

use super::{list_accounts_inner, provider_label};
use crate::{
    autostart,
    error::{AppError, AppResult},
    models::*,
    oauth,
    rclone::{Rclone, SemConsole},
    state::AppState,
};
use serde_json::Value;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_autostart::ManagerExt;

#[tauri::command]
pub async fn recent_activity(state: State<'_, AppState>) -> AppResult<Vec<ActivityEntry>> {
    Ok(state.activity.lock().await.clone())
}

/// O tema do app manda no ícone da bandeja: o painel não recolore ícones.
#[tauri::command]
pub fn set_tray_theme(app: AppHandle, dark: bool) {
    crate::tray::apply_theme(&app, dark);
}

/// Apaga todo o histórico de atividade (memória + `activity.json`).
#[tauri::command]
pub async fn clear_activity(app: AppHandle, state: State<'_, AppState>) -> AppResult<()> {
    state.clear_activity().await;
    let _ = app.emit("sync://changed", ());
    Ok(())
}

#[tauri::command]
pub async fn get_settings(state: State<'_, AppState>) -> AppResult<Settings> {
    Ok(state.settings.lock().await.clone())
}

#[tauri::command]
pub async fn save_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    settings: Settings,
) -> AppResult<Settings> {
    {
        let mut stored = state.settings.lock().await;
        *stored = settings.clone();
        state.save_settings(&stored);
    }
    // Cópia atômica para o fechamento da janela, que não pode esperar o Mutex.
    state.guardar_close_quits(settings.close_quits);
    if state.rclone.set_proxy(&settings.proxy) && state.jobs.lock().await.is_empty() {
        state.rclone.stop().await;
    }
    // O idioma vale também para o que nasce no Rust: o menu da bandeja e as
    // notificações do sistema.
    crate::idioma::definir(&settings.language);
    crate::tray::aplicar_idioma(&app);
    let _ = app.emit("settings://changed", ());
    Ok(settings)
}

#[tauri::command]
pub async fn set_autostart(app: AppHandle, enabled: bool) -> AppResult<bool> {
    // Dentro do Flatpak o plugin escreveria no `~/.config/autostart` do sandbox,
    // que a sessão gráfica não lê: o pedido tem de ir pelo portal.
    if autostart::in_flatpak() {
        return autostart::request(enabled).await;
    }

    let autolaunch = app.autolaunch();
    let result = if enabled {
        autolaunch.enable()
    } else {
        autolaunch.disable()
    };
    result.map_err(|error| AppError::new(error.to_string()))?;
    Ok(enabled)
}

#[tauri::command]
pub async fn autostart_enabled(app: AppHandle) -> AppResult<bool> {
    if autostart::in_flatpak() {
        return Ok(autostart::enabled());
    }

    app.autolaunch()
        .is_enabled()
        .map_err(|error| AppError::new(error.to_string()))
}

/// Abre uma pasta/arquivo no gerenciador do sistema.
///
/// `xdg-open` no Linux, `explorer` no Windows (o WSL usa `wslview`; aqui não
/// interessa). O erro importa: no Flatpak sem portal de arquivos o comando
/// falha e a interface precisa dizer isso em vez de fingir que abriu.
pub(crate) fn abrir_no_sistema<P: AsRef<std::path::Path>>(path: P) -> std::io::Result<()> {
    #[cfg(windows)]
    let program = "explorer";
    #[cfg(not(windows))]
    let program = "xdg-open";
    let mut command = std::process::Command::new(program);
    #[cfg(target_os = "linux")]
    command.env_remove("LD_LIBRARY_PATH").env_remove("LD_PRELOAD");
    command.arg(path.as_ref()).sem_console();
    command.spawn().map(|_| ())
}

/// Abre um **endereço** no navegador padrão.
///
/// No Windows não serve o `explorer`: ele abre (ou só traz para a frente) a
/// janela do Explorer em vez do navegador — era o bug de "conectar conta →
/// Google Drive" na versão do Windows. Quem entrega um endereço ao navegador
/// padrão é o `ShellExecute`. Também não serve `cmd /C start`: o endereço de
/// autorização tem vários `&`, que o `cmd` interpretaria como separador de
/// comandos e cortaria a URL no primeiro deles.
///
/// No Linux e no macOS o `xdg-open`/`open` resolvem os dois casos (pasta ou
/// endereço), então a função só delega.
pub(crate) fn abrir_endereco(url: &str) -> std::io::Result<()> {
    #[cfg(windows)]
    {
        shell_do_windows::abrir(url)
    }
    #[cfg(not(windows))]
    {
        abrir_no_sistema(url)
    }
}

/// Chamada direta à `shell32` — o mesmo caminho que o menu "Abrir com" usa.
#[cfg(windows)]
mod shell_do_windows {
    use std::os::windows::ffi::OsStrExt;

    #[link(name = "shell32")]
    extern "system" {
        fn ShellExecuteW(
            janela: *mut core::ffi::c_void,
            operacao: *const u16,
            arquivo: *const u16,
            parametros: *const u16,
            pasta: *const u16,
            mostrar: i32,
        ) -> isize;
    }

    pub fn abrir(url: &str) -> std::io::Result<()> {
        let largo = |texto: &str| {
            std::ffi::OsStr::new(texto)
                .encode_wide()
                .chain(std::iter::once(0))
                .collect::<Vec<u16>>()
        };
        let operacao = largo("open");
        let arquivo = largo(url);
        // SW_SHOWNORMAL = 1: o navegador abre na frente, do tamanho normal.
        let resultado = unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                operacao.as_ptr(),
                arquivo.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
            )
        };
        // A API devolve um valor maior que 32 quando começou bem.
        if resultado > 32 {
            Ok(())
        } else {
            Err(std::io::Error::other(format!(
                "o Windows não conseguiu abrir o endereço (código {resultado})"
            )))
        }
    }
}

#[tauri::command]
pub fn reveal_path(path: String) -> AppResult<()> {
    abrir_no_sistema(&path)
        .map_err(|error| AppError::new(format!("não foi possível abrir {path}: {error}")))?;
    Ok(())
}

#[tauri::command]
pub fn quit_app(app: AppHandle) {
    app.exit(0);
}

/// "Sair" pedido pela interface (Ajustes e busca rápida). Mesma regra da
/// bandeja: com sincronização em andamento, pergunta antes de encerrar.
#[tauri::command]
pub fn request_quit(app: AppHandle) {
    crate::tray::pedir_saida(&app);
}

/// Leva a janela para a bandeja sem encerrar nada — o "Continuar em segundo
/// plano" da pergunta de saída.
#[tauri::command]
pub fn hide_window(app: AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.hide();
    }
}

#[tauri::command]
pub async fn open_config_folder(state: State<'_, AppState>) -> AppResult<String> {
    let path = state.dir.display().to_string();
    abrir_no_sistema(&state.dir)
        .map_err(|error| AppError::new(format!("não foi possível abrir {path}: {error}")))?;
    Ok(path)
}

pub(super) fn versao_mais_nova(atual: &str, remota: &str) -> bool {
    fn partes(versao: &str) -> [u64; 3] {
        let limpo = versao.trim().trim_start_matches('v');
        let mut saida = [0u64; 3];
        for (i, pedaco) in limpo.split(['.', '-', '+']).take(3).enumerate() {
            saida[i] = pedaco
                .chars()
                .take_while(char::is_ascii_digit)
                .collect::<String>()
                .parse()
                .unwrap_or(0);
        }
        saida
    }
    partes(remota) > partes(atual)
}

/// Monta o texto do relatório. Função pura (sem Tauri) para poder testar que
/// nenhum segredo escapa — `client_secret` e tokens nunca entram aqui.
pub(super) struct ContextoRelatorio<'a> {
    pub(super) versao_app: &'a str,
    pub(super) sistema: &'a str,
    /// Versão e caminho do rclone, quando encontrado.
    pub(super) rclone: Option<(&'a str, &'a str)>,
    pub(super) contas: &'a [Account],
    pub(super) profiles: &'a [Profile],
    pub(super) settings: &'a Settings,
    pub(super) atividade: &'a [ActivityEntry],
    pub(super) recuperacao: &'a [String],
}

pub(super) fn montar_relatorio(ctx: &ContextoRelatorio<'_>) -> String {
    let ContextoRelatorio {
        versao_app,
        sistema,
        rclone,
        contas,
        profiles,
        settings,
        atividade,
        recuperacao,
    } = *ctx;
    let mut texto = String::new();
    texto.push_str(&format!("BrisaSync {versao_app}\n"));
    texto.push_str(&format!("Sistema: {sistema}\n"));
    match rclone {
        Some((versao, caminho)) => {
            texto.push_str(&format!("rclone: {versao}\n"));
            texto.push_str(&format!("Binário do rclone: {caminho}\n"));
        }
        None => texto.push_str("rclone: não encontrado\n"),
    }
    texto.push_str(&format!("\nContas ({})\n", contas.len()));
    for conta in contas {
        texto.push_str(&format!("- {} ({})\n", conta.name, provider_label(&conta.provider)));
    }
    texto.push_str(&format!("\nPastas ({})\n", profiles.len()));
    for perfil in profiles {
        let estado = if perfil.enabled { "ligada" } else { "desligada" };
        texto.push_str(&format!(
            "- {}:{} -> {} [{estado}]\n",
            perfil.account, perfil.remote_path, perfil.local_path
        ));
        if let Some(erro) = &perfil.last_error {
            texto.push_str(&format!("  último erro: {}\n", resumir(erro, 200)));
        }
    }
    texto.push_str("\nAjustes\n");
    texto.push_str(&format!("- tema: {}\n", settings.theme));
    texto.push_str(&format!(
        "- sincronização automática: {} (a cada {} min)\n",
        if settings.auto_sync { "sim" } else { "não" },
        settings.sync_interval_min
    ));
    texto.push_str(&format!(
        "- tentar de novo sozinho: {}\n",
        if settings.auto_retry { "sim" } else { "não" }
    ));
    texto.push_str(&format!(
        "- notificações: {}\n",
        if settings.notifications { "sim" } else { "não" }
    ));
    texto.push_str(&format!(
        "- banda: subir '{}', descer '{}'\n",
        settings.bandwidth_up, settings.bandwidth_down
    ));
    texto.push_str(&format!("- proxy: '{}'\n", settings.proxy));
    texto.push_str(&format!(
        "- fechar a janela: {}\n",
        if settings.close_quits {
            "encerra o app"
        } else {
            "continua na bandeja"
        }
    ));
    texto.push_str(&format!("- regras de ignorar: {}\n", settings.ignore_rules.len()));
    texto.push_str(&format!(
        "- conversão de docs Google: {}, symlinks: {}\n",
        if settings.docs_conversion { "sim" } else { "não" },
        if settings.symlinks { "sim" } else { "não" }
    ));
    let credenciais = oauth::efetivas((&settings.drive_client_id, &settings.drive_client_secret));
    texto.push_str(&format!(
        "- credenciais OAuth: {}\n",
        credenciais.fonte.descricao()
    ));
    if let Some(id) = &credenciais.client_id {
        // Público por natureza (vai na URL de autorização); ajuda no suporte.
        texto.push_str(&format!("- client_id: {id}\n"));
    }

    if !recuperacao.is_empty() {
        texto.push_str("\nRecuperação na inicialização\n");
        for aviso in recuperacao {
            texto.push_str(&format!("- {}\n", resumir(aviso, 200)));
        }
    }

    texto.push_str(&format!("\nAtividade recente ({})\n", atividade.len()));
    for entrada in atividade.iter().take(20) {
        let quando = crate::state::formatar_quando(entrada.at).unwrap_or_default();
        texto.push_str(&format!(
            "- [{}] {} — {} ({quando})\n",
            entrada.kind,
            entrada.title,
            resumir(&entrada.detail, 200)
        ));
    }
    texto
}

fn resumir(texto: &str, limite: usize) -> String {
    let linha = texto.replace(['\r', '\n'], " ");
    if linha.chars().count() <= limite {
        return linha;
    }
    let cortado: String = linha.chars().take(limite).collect();
    format!("{cortado}…")
}

/// Grava um relatório de diagnóstico ao lado dos arquivos de estado e devolve o
/// caminho. A pasta abre no gerenciador: é o que a pessoa anexa ao abrir um
/// problema, com contas, pastas e últimos erros já no lugar.
#[tauri::command]
pub async fn save_diagnostics(app: AppHandle, state: State<'_, AppState>) -> AppResult<String> {
    let binary = Rclone::find_binary();
    let versao_rclone = match &binary {
        Some(path) => state.rclone.version(path).await,
        None => None,
    };
    let contas = list_accounts_inner(&state).await.unwrap_or_default();
    let profiles = state.profiles.lock().await.clone();
    let settings = state.settings.lock().await.clone();
    let atividade = state.activity.lock().await.clone();
    let sistema = format!(
        "{} {} · {}",
        std::env::consts::OS,
        std::env::consts::ARCH,
        sistema_legivel()
    );

    let rclone = binary
        .as_ref()
        .zip(versao_rclone.as_ref())
        .map(|(caminho, versao)| (versao.clone(), caminho.display().to_string()));
    let texto = montar_relatorio(&ContextoRelatorio {
        versao_app: env!("CARGO_PKG_VERSION"),
        sistema: &sistema,
        rclone: rclone
            .as_ref()
            .map(|(versao, caminho)| (versao.as_str(), caminho.as_str())),
        contas: &contas,
        profiles: &profiles,
        settings: &settings,
        atividade: &atividade,
        recuperacao: &state.recuperacao,
    });

    let quando = crate::state::agora_legivel();
    let arquivo = state.dir.join(format!("diagnostico-{quando}.txt"));
    crate::state::write_text(&arquivo, &texto)?;
    let caminho = arquivo.display().to_string();
    let _ = abrir_no_sistema(&state.dir);
    let _ = app.emit("sync://changed", ());
    Ok(caminho)
}

/// Nome da distro, quando dá para ler (`PRETTY_NAME` do `/etc/os-release`).
fn sistema_legivel() -> String {
    std::fs::read_to_string("/etc/os-release")
        .ok()
        .and_then(|texto| {
            texto.lines().find_map(|linha| {
                linha
                    .strip_prefix("PRETTY_NAME=")
                    .map(|valor| valor.trim_matches('"').to_string())
            })
        })
        .unwrap_or_else(|| "sistema desconhecido".to_string())
}

/// Consulta a última Release pública do repositório. Repositório privado (ou
/// rede fora) devolve `None` em vez de erro: não é falha do app.
#[tauri::command]
pub async fn check_update() -> AppResult<Option<UpdateInfo>> {
    const URL: &str = "https://api.github.com/repos/fabio-agreles/BrisaSync/releases/latest";
    let cliente = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(12))
        .build()
        .map_err(|erro| AppError::new(erro.to_string()))?;
    let resposta = cliente
        .get(URL)
        // A API do GitHub recusa requisição sem User-Agent.
        .header("User-Agent", format!("BrisaSync/{}", env!("CARGO_PKG_VERSION")))
        .header("Accept", "application/vnd.github+json")
        .send()
        .await
        .map_err(|erro| AppError::new(format!("não foi possível consultar a atualização: {erro}")))?;

    if !resposta.status().is_success() {
        return Ok(None);
    }
    let corpo: Value = resposta
        .json()
        .await
        .map_err(|erro| AppError::new(erro.to_string()))?;
    let remota = corpo
        .get("tag_name")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let url = corpo
        .get("html_url")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if url.is_empty() || !versao_mais_nova(env!("CARGO_PKG_VERSION"), remota) {
        return Ok(None);
    }
    let assets = corpo
        .get("assets")
        .and_then(Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let (asset_url, asset_name) = match escolher_asset_da_release(assets) {
        Some((u, n)) => (Some(u), Some(n)),
        None => (None, None),
    };
    Ok(Some(UpdateInfo {
        version: remota.trim_start_matches('v').to_string(),
        url: url.to_string(),
        asset_url,
        asset_name,
    }))
}

fn escolher_asset_da_release(assets: &[Value]) -> Option<(String, String)> {
    let sufixo = if cfg!(target_os = "windows") {
        ".exe"
    } else if std::path::Path::new("/.flatpak-info").exists() {
        return None;
    } else if std::env::var_os("APPIMAGE").is_some() {
        ".AppImage"
    } else {
        ".deb"
    };
    escolher_asset_por_sufixo(assets, sufixo)
}

fn escolher_asset_por_sufixo(assets: &[Value], sufixo: &str) -> Option<(String, String)> {
    for asset in assets {
        let name = asset.get("name").and_then(Value::as_str).unwrap_or_default();
        let url = asset
            .get("browser_download_url")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if name.ends_with(sufixo) && url.starts_with("https://") {
            return Some((url.to_string(), name.to_string()));
        }
    }
    None
}

fn url_de_atualizacao_valida(url: &str) -> bool {
    url.starts_with("https://github.com/fabio-agreles/BrisaSync/")
        || url.starts_with("https://objects.githubusercontent.com/")
}

/// Baixa o pacote da nova versão e inicia a instalação (ou abre o instalador).
#[tauri::command]
pub async fn install_update(
    app: AppHandle,
    url: String,
    file_name: String,
) -> AppResult<String> {
    if !url_de_atualizacao_valida(&url) {
        return Err(AppError::new("endereço de atualização não permitido"));
    }
    if file_name.is_empty() || file_name.contains(['/', '\\']) {
        return Err(AppError::new("nome de arquivo inválido"));
    }

    if !autostart::in_flatpak() {
        use tauri_plugin_updater::UpdaterExt as _;
        if let Ok(updater) = app.updater() {
            if let Ok(Some(update)) = updater.check().await {
                update
                    .download_and_install(|_, _| {}, || {})
                    .await
                    .map_err(|erro| AppError::new(format!("falha ao instalar atualização: {erro}")))?;
                app.restart();
            }
        }
    }

    let cliente = reqwest::Client::builder()
        .no_proxy()
        .timeout(Duration::from_secs(300))
        .build()
        .map_err(|erro| AppError::new(erro.to_string()))?;

    let resposta = cliente
        .get(&url)
        .header("User-Agent", format!("BrisaSync/{}", env!("CARGO_PKG_VERSION")))
        .send()
        .await
        .map_err(|erro| AppError::new(format!("não foi possível baixar a atualização: {erro}")))?;

    if !resposta.status().is_success() {
        return Err(AppError::new(format!(
            "falha ao baixar atualização (HTTP {})",
            resposta.status()
        )));
    }

    let bytes = resposta
        .bytes()
        .await
        .map_err(|erro| AppError::new(format!("erro ao ler pacote baixado: {erro}")))?;

    let dest = std::env::temp_dir().join(&file_name);
    std::fs::write(&dest, &bytes)
        .map_err(|erro| AppError::new(format!("não foi possível salvar o instalador: {erro}")))?;

    #[cfg(unix)]
    if file_name.ends_with(".AppImage") {
        use std::os::unix::fs::PermissionsExt;
        let _ = std::fs::set_permissions(&dest, std::fs::Permissions::from_mode(0o755));
    }

    let dest_str = dest.to_string_lossy().to_string();

    #[cfg(target_os = "windows")]
    {
        std::process::Command::new(&dest)
            .spawn()
            .map_err(|erro| AppError::new(format!("não foi possível abrir o instalador: {erro}")))?;
        app.exit(0);
    }

    #[cfg(not(target_os = "windows"))]
    {
        let _ = app;
        abrir_endereco(&dest_str)
            .map_err(|erro| AppError::new(format!("não foi possível abrir o pacote: {erro}")))?;
    }

    Ok(dest_str)
}

/// Abre um endereço no navegador (o `xdg-open` também serve para URLs).
#[tauri::command]
pub fn open_url(url: String) -> AppResult<()> {
    if !(url.starts_with("https://") || url.starts_with("http://")) {
        return Err(AppError::new("só abro endereços http(s)"));
    }
    abrir_endereco(&url)
        .map_err(|erro| AppError::new(format!("não foi possível abrir {url}: {erro}")))?;
    Ok(())
}

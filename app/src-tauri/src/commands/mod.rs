mod files;
mod system;

pub use files::*;
pub use system::*;

use crate::{
    error::{AppError, AppResult},
    models::*,
    oauth,
    rclone::{Rclone, SemConsole},
    state::{AppState, JobRecord},
};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    path::Path,
    sync::{
        atomic::{AtomicU64, Ordering},
        Mutex, OnceLock,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, State};
use tokio::time::sleep;

pub(super) fn provider_label(provider: &str) -> &str {
    match provider {
        "drive" => "Google Drive",
        "onedrive" => "OneDrive",
        "dropbox" => "Dropbox",
        "nextcloud" => "Nextcloud",
        other => other,
    }
}

/// Garante que a conta existe na configuração do rclone antes de falar com ela.
pub(super) async fn require_account(state: &AppState, account: &str) -> AppResult<()> {
    let known = list_accounts_inner(state)
        .await?
        .iter()
        .any(|item| item.name == account);
    if known {
        Ok(())
    } else {
        Err(AppError::new("conta não encontrada"))
    }
}

/// Separa "Pasta/Sub/arquivo.zip" em ("Pasta/Sub", "arquivo.zip").
pub(super) fn split_remote(remote_path: &str) -> AppResult<(String, String)> {
    let trimmed = remote_path.trim_end_matches('/');
    let name = trimmed
        .rsplit('/')
        .next()
        .filter(|name| !name.is_empty() && *name != ".." && *name != ".")
        .ok_or_else(|| AppError::new("caminho na nuvem inválido"))?;
    let parent = trimmed
        .rsplit_once('/')
        .map(|(dir, _)| dir.to_string())
        .unwrap_or_default();
    Ok((parent, name.to_string()))
}

/// Monta "conta:pastas" sem deixar "conta:/" nem barras duplas.
pub(super) fn remote_fs(account: &str, dir: &str) -> String {
    let clean = dir.trim_matches('/');
    if clean.is_empty() {
        format!("{account}:")
    } else {
        format!("{account}:{clean}")
    }
}

pub(super) fn new_id() -> String {
    static COUNTER: AtomicU64 = AtomicU64::new(0);
    format!(
        "{}-{}",
        now_ms(),
        COUNTER.fetch_add(1, Ordering::Relaxed)
    )
}

/// `rclone config dump` — a configuração inteira, com os tokens.
pub(crate) async fn dump_da_configuracao(state: &AppState) -> AppResult<HashMap<String, Value>> {
    let binary = state.rclone.binary().await?;
    // Roda a cada tela que lista contas: sem `sem_console` seria uma janela de
    // console piscando a cada navegação no Windows.
    let mut command = tokio::process::Command::new(binary);
    command.args(["config", "dump"]).sem_console();
    let output = command.output().await.map_err(|error| {
        AppError::new(format!(
            "não foi possível ler a configuração do rclone: {error}"
        ))
    })?;

    if !output.status.success() {
        return Err(AppError::new(format!(
            "rclone config dump falhou: {}",
            String::from_utf8_lossy(&output.stderr).trim()
        )));
    }

    Ok(serde_json::from_slice(&output.stdout)?)
}

pub async fn list_accounts_inner(state: &AppState) -> AppResult<Vec<Account>> {
    let dump = dump_da_configuracao(state).await?;
    let mut accounts: Vec<Account> = dump
        .into_iter()
        .map(|(name, config)| {
            let raw_type = config
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("desconhecido");
            let vendor = config
                .get("vendor")
                .and_then(Value::as_str)
                .unwrap_or_default();
            let provider = if raw_type == "webdav" && vendor == "nextcloud" {
                "nextcloud".to_string()
            } else {
                raw_type.to_string()
            };
            // Quem autorizou a conta: sem `client_id` é o projeto compartilhado
            // do rclone; igual ao do build é o projeto do BrisaSync; qualquer outro
            // é o par que a pessoa colou em Ajustes → Avançado.
            let client_origem = oauth::fonte_da_conta(
                config.get("client_id").and_then(Value::as_str),
                oauth::do_build().as_ref().map(|par| par.0.as_str()),
            )
            .id()
            .to_string();
            Account {
                name,
                label: provider_label(&provider).to_string(),
                provider,
                client_origem,
            }
        })
        .collect();
    accounts.sort_by(|left, right| left.name.cmp(&right.name));
    Ok(accounts)
}

pub async fn snapshot(state: &AppState) -> Snapshot {
    let paused = state.paused.load(Ordering::SeqCst);
    let until = state.pause_until.load(Ordering::SeqCst);
    let pause_until = if paused && until > 0 { Some(until) } else { None };
    if !state.rclone.is_running().await {
        return Snapshot {
            pause_until,
            ..Snapshot::stopped(paused)
        };
    }

    // O estado de execução vem apenas das tarefas que o app disparou. `job/list`
    // do rclone não serve: a própria chamada vira uma tarefa e se reporta como em
    // execução, então a lista nunca fica vazia.
    let running_ids = state.running_job_ids().await;
    let running = !running_ids.is_empty() && !paused;

    if !running {
        // Nada em andamento: não há progresso a mostrar, e pular o `core/stats`
        // também evita criar tarefas inúteis dentro do rclone.
        return Snapshot {
            engine_ready: true,
            pause_until,
            jobs: 0,
            ..Snapshot::stopped(paused)
        };
    }

    let stats = match state
        .rclone
        .call("core/stats", json!({}), Duration::from_secs(4))
        .await
    {
        Ok(stats) => stats,
        Err(_) => return Snapshot::stopped(paused),
    };

    let transfers: Vec<Transfer> = stats
        .get("transferring")
        .and_then(Value::as_array)
        .map(|items| items.iter().map(transfer_from).collect())
        .unwrap_or_default();

    Snapshot {
        engine_ready: true,
        paused,
        pause_until,
        running: true,
        speed: stats.get("speed").and_then(Value::as_f64).unwrap_or(0.0),
        bytes: stats.get("bytes").and_then(Value::as_u64).unwrap_or(0),
        total_bytes: stats
            .get("totalBytes")
            .and_then(Value::as_u64)
            .unwrap_or(0),
        errors: stats.get("errors").and_then(Value::as_u64).unwrap_or(0),
        transfers,
        jobs: running_ids.len(),
    }
}

fn transfer_from(value: &Value) -> Transfer {
    let size = value.get("size").and_then(Value::as_u64).unwrap_or(0);
    let bytes = value.get("bytes").and_then(Value::as_u64).unwrap_or(0);
    let percent = value
        .get("percentage")
        .and_then(Value::as_f64)
        .unwrap_or_else(|| {
            if size > 0 {
                bytes as f64 / size as f64 * 100.0
            } else {
                0.0
            }
        });

    Transfer {
        name: value
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or("arquivo")
            .to_string(),
        size,
        bytes,
        percent,
        speed: value.get("speed").and_then(Value::as_f64).unwrap_or(0.0),
        eta: value.get("eta").and_then(Value::as_f64),
    }
}

#[tauri::command]
pub async fn engine_status(state: State<'_, AppState>) -> AppResult<EngineStatus> {
    let binary = Rclone::find_binary();
    let version = match &binary {
        Some(path) => state.rclone.version(path).await,
        None => None,
    };
    let accounts = list_accounts_inner(&state)
        .await
        .map(|list| list.len())
        .unwrap_or(0);

    Ok(EngineStatus {
        available: binary.is_some(),
        version,
        binary: binary.map(|path| path.display().to_string()),
        accounts,
    })
}

#[tauri::command]
pub async fn list_accounts(state: State<'_, AppState>) -> AppResult<Vec<Account>> {
    list_accounts_inner(&state).await
}

/// Parâmetros iniciais do `config/create`.
///
/// No Google Drive eles trocam o projeto OAuth usado na autorização: com
/// `client_id`/`client_secret` do usuário, a cota de “consultas por minuto” deixa
/// de ser a do projeto compartilhado do rclone (que vive estourada) e passa a ser
/// a de um projeto que só ele usa. A conta é autorizada de novo no navegador.
///
/// Precedência: credenciais do usuário (Ajustes → Avançado) > projeto do BrisaSync
/// embutido no build > projeto compartilhado do rclone.
async fn parametros_do_provedor(state: &AppState, provider: &str) -> AppResult<Value> {
    if provider != "drive" {
        return Ok(json!({}));
    }

    let (id, secret) = {
        let settings = state.settings.lock().await;
        (
            settings.drive_client_id.trim().to_string(),
            settings.drive_client_secret.trim().to_string(),
        )
    };

    // Par do usuário incompleto é erro (ele começou a preencher e parou no meio);
    // par ausente cai para o projeto do BrisaSync, se o build tiver um.
    match (id.is_empty(), secret.is_empty()) {
        (true, true) => Ok(oauth::efetivas(("", "")).como_json()),
        (false, false) => {
            if !id.ends_with(oauth::SUFIXO_CLIENT_ID) {
                return Err(AppError::new(
                    "o client_id do Google termina em .apps.googleusercontent.com — confira se colou o valor certo.",
                ));
            }
            Ok(json!({ "client_id": id, "client_secret": secret }))
        }
        _ => Err(AppError::new(
            "preencha o client_id e o client_secret do Google — ou deixe os dois em branco para usar o projeto do BrisaSync.",
        )),
    }
}

/// Diz qual projeto OAuth está em vigor, para a interface e para o suporte.
///
/// Nunca devolve o `client_secret`: só a origem e o `client_id` (público).
#[tauri::command]
pub async fn oauth_info(state: State<'_, AppState>) -> AppResult<OAuthInfo> {
    let (id, secret) = {
        let settings = state.settings.lock().await;
        (
            settings.drive_client_id.clone(),
            settings.drive_client_secret.clone(),
        )
    };
    let credenciais = oauth::efetivas((&id, &secret));
    Ok(OAuthInfo {
        fonte: credenciais.fonte.id().to_string(),
        client_id: credenciais.client_id,
    })
}

fn normalizar_url_nextcloud(raw_url: &str, user: &str) -> AppResult<String> {
    let trimmed = raw_url.trim().trim_end_matches('/');
    if !(trimmed.starts_with("https://") || trimmed.starts_with("http://")) {
        return Err(AppError::new(
            "o endereço do Nextcloud precisa começar com https:// ou http://",
        ));
    }
    if trimmed.contains("/remote.php/dav") {
        Ok(trimmed.to_string())
    } else {
        Ok(format!("{trimmed}/remote.php/dav/files/{}/", user.trim()))
    }
}

#[tauri::command]
pub async fn connect_account(
    app: AppHandle,
    state: State<'_, AppState>,
    provider: String,
    name: String,
    url: Option<String>,
    user: Option<String>,
    pass: Option<String>,
) -> AppResult<Account> {
    if !matches!(
        provider.as_str(),
        "drive" | "onedrive" | "dropbox" | "nextcloud"
    ) {
        return Err(AppError::new("provedor não suportado nesta versão"));
    }

    state.rclone.ensure().await?;

    let existing = list_accounts_inner(&state).await?;
    let requested = name.trim();
    let account_name = if requested.is_empty() {
        let base = provider_label(&provider);
        let mut index = existing
            .iter()
            .filter(|account| account.provider == provider)
            .count()
            + 1;
        let mut candidate = format!("{base} {index}");
        while existing.iter().any(|account| account.name == candidate) {
            index += 1;
            candidate = format!("{base} {index}");
        }
        candidate
    } else {
        requested.to_string()
    };

    if existing.iter().any(|account| account.name == account_name) {
        return Err(AppError::new(format!(
            "já existe uma conta chamada \"{account_name}\""
        )));
    }

    // Contas Google podem ser autorizadas por um projeto OAuth do próprio
    // usuário: a cota de requisições passa a ser só dele, sem a fila mundial do
    // projeto compartilhado do rclone.
    let mut parametros = parametros_do_provedor(&state, &provider).await?;
    let mut opcoes = json!({});

    // Com um projeto OAuth em mãos (do usuário ou o do próprio BrisaSync), quem
    // autoriza é o app: ele abre o navegador, escuta o retorno em `127.0.0.1` e
    // mostra a página do BrisaSync. Com o token pronto, o remote é criado sem
    // passar pelo fluxo interativo do rclone — que terminava numa página dizendo
    // “All done. Please go back to rclone.”.
    if provider == "drive" {
        let par = (
            parametros
                .get("client_id")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
            parametros
                .get("client_secret")
                .and_then(Value::as_str)
                .unwrap_or_default()
                .to_string(),
        );
        if !par.0.is_empty() && !par.1.is_empty() {
            let token = crate::login_google::autorizar(&par.0, &par.1).await?;
            parametros["token"] = Value::String(token.to_string());
            // Sem isto o rclone pergunta “Token already configured - replace it?”
            // e o remote fica pela metade.
            parametros["config_refresh_token"] = Value::String("false".to_string());
            opcoes = json!({ "nonInteractive": true });
        }
    }

    // OneDrive pelo mesmo caminho: quem abre o navegador e recebe o retorno é o
    // app, então a última página é a do BrisaSync (era a do rclone, “All done.
    // Please go back to rclone.”). Com o token pronto, o remote é criado sem o
    // fluxo interativo.
    if provider == "onedrive" {
        let token = crate::login_microsoft::autorizar().await?;
        parametros["token"] = Value::String(token.to_string());
        parametros["config_refresh_token"] = Value::String("false".to_string());
        opcoes = json!({ "nonInteractive": true });
    }

    if provider == "dropbox" {
        if let Some((client_id, client_secret)) = crate::login_dropbox::credenciais_do_build() {
            let token = crate::login_dropbox::autorizar(&client_id, &client_secret).await?;
            parametros["client_id"] = Value::String(client_id);
            parametros["client_secret"] = Value::String(client_secret);
            parametros["token"] = Value::String(token.to_string());
            parametros["config_refresh_token"] = Value::String("false".to_string());
            opcoes = json!({ "nonInteractive": true });
        }
    }

    let mut rclone_type = provider.clone();
    if provider == "nextcloud" {
        let nc_user = user.unwrap_or_default().trim().to_string();
        let nc_pass = pass.unwrap_or_default();
        let nc_url = url.unwrap_or_default();
        if nc_url.trim().is_empty() || nc_user.is_empty() || nc_pass.is_empty() {
            return Err(AppError::new(
                "informe o endereço do servidor, usuário e senha de aplicativo do Nextcloud",
            ));
        }
        let endpoint = normalizar_url_nextcloud(&nc_url, &nc_user)?;
        rclone_type = "webdav".to_string();
        parametros = json!({
            "url": endpoint,
            "vendor": "nextcloud",
            "user": nc_user,
            "pass": nc_pass
        });
        opcoes = json!({ "nonInteractive": true, "obscure": true });
    }

    state
        .rclone
        .call(
            "config/create",
            json!({
                "name": account_name,
                "type": rclone_type,
                "parameters": parametros,
                "opt": opcoes
            }),
            Duration::from_secs(600),
        )
        .await
        .map_err(|error| {
            AppError::new(format!(
                "não foi possível conectar a conta. Autorize no navegador e tente novamente. ({error})"
            ))
        })?;

    if provider == "onedrive" {
        // Sem isso a conta fica só com o token: listar ou sincronizar falha com
        // "unable to get drive_id and drive_type".
        if let Err(error) = completar_onedrive(&state, &account_name).await {
            eprintln!("onedrive: não foi possível concluir a configuração: {error}");
        }
        // O `completar_onedrive` engole o erro (a conta pode ficar utilizável
        // depois, na próxima sincronização). Aqui a checagem é explícita: sem
        // `drive_id`, listar arquivos e sincronizar falham sempre.
        let pronto = dump_da_configuracao(&state)
            .await
            .ok()
            .and_then(|dump| dump.get(&account_name).cloned())
            .map(|config| !config.get("drive_id").and_then(Value::as_str).unwrap_or_default().is_empty())
            .unwrap_or(false);
        if !pronto {
            return Err(AppError::new(
                "a conta foi autorizada, mas não foi possível descobrir qual drive usar. Remova a conta em Visão geral → Contas e conecte de novo.",
            ));
        }
    }

    let accounts = list_accounts_inner(&state).await?;
    let account = accounts
        .into_iter()
        .find(|account| account.name == account_name)
        .ok_or_else(|| AppError::new("a conta não apareceu na configuração do rclone"))?;

    state
        .push_activity(
            "account",
            crate::idioma::texto("Conta conectada", "Account connected"),
            &format!("{} · {}", account.label, account.name),
            None,
        )
        .await;
    let _ = app.emit("sync://changed", ());
    Ok(account)
}

#[tauri::command]
pub async fn list_profiles(state: State<'_, AppState>) -> AppResult<Vec<Profile>> {
    Ok(state.profiles.lock().await.clone())
}

#[tauri::command]
pub async fn create_profile(
    app: AppHandle,
    state: State<'_, AppState>,
    input: NewProfile,
) -> AppResult<Profile> {
    let accounts = list_accounts_inner(&state).await?;
    if !accounts.iter().any(|account| account.name == input.account) {
        return Err(AppError::new("selecione uma conta conectada"));
    }
    if input.local_path.trim().is_empty() {
        return Err(AppError::new("escolha uma pasta local"));
    }

    std::fs::create_dir_all(&input.local_path).map_err(|error| {
        AppError::new(format!(
            "não foi possível criar a pasta local {}: {error}",
            input.local_path
        ))
    })?;

    let remote_path = input.remote_path.trim().trim_matches('/').to_string();
    let profile = Profile {
        id: new_id(),
        account: input.account,
        remote_path,
        local_path: input.local_path,
        enabled: input.enabled,
        resync_needed: true,
        last_sync: None,
        last_error: None,
        last_bytes: 0,
        excluded_folders: input.excluded_folders,
        sync_interval_min: None,
    };

    {
        let mut profiles = state.profiles.lock().await;
        profiles.push(profile.clone());
        state.save_profiles(&profiles);
    }

    state
        .push_activity(
            "info",
            crate::idioma::texto("Pasta adicionada", "Folder added"),
            &format!("{} → {}", profile.remote_path, profile.local_path),
            Some(&profile.id),
        )
        .await;
    let _ = app.emit("sync://changed", ());
    Ok(profile)
}

#[tauri::command]
pub async fn update_profile(
    app: AppHandle,
    state: State<'_, AppState>,
    profile: Profile,
) -> AppResult<Profile> {
    let updated = {
        let mut profiles = state.profiles.lock().await;
        let stored = profiles
            .iter_mut()
            .find(|stored| stored.id == profile.id)
            .ok_or_else(|| AppError::new("pasta não encontrada"))?;

        let paths_changed = stored.remote_path != profile.remote_path
            || stored.local_path != profile.local_path
            || stored.account != profile.account
            || stored.excluded_folders != profile.excluded_folders;

        stored.account = profile.account;
        stored.remote_path = profile.remote_path.trim().trim_matches('/').to_string();
        stored.local_path = profile.local_path;
        stored.enabled = profile.enabled;
        stored.excluded_folders = profile.excluded_folders;
        if paths_changed {
            stored.resync_needed = true;
            stored.last_sync = None;
            stored.last_error = None;
        }
        let updated = stored.clone();
        state.save_profiles(&profiles);
        updated
    };

    let _ = app.emit("sync://changed", ());
    Ok(updated)
}

#[tauri::command]
pub async fn delete_profile(
    app: AppHandle,
    state: State<'_, AppState>,
    id: String,
) -> AppResult<()> {
    {
        let mut profiles = state.profiles.lock().await;
        profiles.retain(|profile| profile.id != id);
        state.save_profiles(&profiles);
    }
    let _ = app.emit("sync://changed", ());
    Ok(())
}

/// Desconecta uma conta: apaga o remote do rclone e o cache do bisync dela.
///
/// Pastas que usam a conta precisam sair antes — apagar o remote com uma pasta
/// ativa deixaria o perfil apontando para um caminho inexistente.
#[tauri::command]
pub async fn delete_account(
    app: AppHandle,
    state: State<'_, AppState>,
    account: String,
) -> AppResult<()> {
    let usando: Vec<String> = {
        let profiles = state.profiles.lock().await;
        profiles
            .iter()
            .filter(|profile| profile.account == account)
            .map(|profile| profile.remote_path.clone())
            .collect()
    };

    if !usando.is_empty() {
        let lista = usando
            .iter()
            .map(|path| format!("“{path}”"))
            .collect::<Vec<_>>()
            .join(", ");
        return Err(AppError::new(format!(
            "remova antes a pasta {lista} — ela ainda usa esta conta."
        )));
    }

    // Pode ser o primeiro comando depois de abrir o app: garante o daemon.
    state.rclone.ensure().await?;
    state
        .rclone
        .call("config/delete", json!({ "name": account }), Duration::from_secs(20))
        .await?;

    limpar_cache_da_conta(&state, &account).await;

    state
        .push_activity(
            "account",
            crate::idioma::texto("Conta removida", "Account removed"),
            &account,
            None,
        )
        .await;
    let _ = app.emit("sync://changed", ());
    Ok(())
}

/// O bisync guarda as listas em `<cache>/bisync/<remote>_<caminho>..<pasta>`. Sem
/// isso, reconectar a mesma conta herdaria listas antigas e pediria resync.
async fn limpar_cache_da_conta(state: &AppState, account: &str) {
    let Ok(paths) = state
        .rclone
        .call("config/paths", json!({}), Duration::from_secs(5))
        .await
    else {
        return;
    };
    let Some(cache) = paths.get("cache").and_then(Value::as_str) else {
        return;
    };
    let Ok(entries) = std::fs::read_dir(Path::new(cache).join("bisync")) else {
        return;
    };
    let prefixo = format!("{account}_");
    for entry in entries.flatten() {
        if entry.file_name().to_string_lossy().starts_with(&prefixo) {
            let _ = std::fs::remove_file(entry.path());
        }
    }
}

/// Remove travas (`*.lck`) que sobraram de uma execução interrompida.
///
/// O bisync recusa começar com "prior lock file found" quando o app foi fechado
/// no meio de uma sincronização. Como só chamamos isto quando o app **não** tem
/// tarefa rodando, qualquer trava encontrada é resto — e travas com menos de um
/// minuto são respeitadas por via das dúvidas.
/// Qual lado está vazio quando o outro não está.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum LadoVazio {
    Nuvem,
    Local,
}

impl LadoVazio {
    pub(crate) fn mensagem(self) -> &'static str {
        match self {
            // O caso que já aconteceu de verdade: a pasta na nuvem foi esvaziada
            // (para a lixeira do Drive) e o bisync, sem esta trava, propagaria a
            // exclusão para os arquivos locais.
            Self::Nuvem => {
                "a pasta na nuvem está vazia e a local tem arquivos: sincronizar agora apagaria tudo o \
                 que está no computador. Nada foi apagado. Confira a pasta na nuvem (a lixeira do Drive \
                 guarda o que saiu de lá); se o vazio for intencional, clique neste erro e escolha \
                 Ressincronizar."
            }
            Self::Local => {
                "a pasta local está vazia e a na nuvem tem arquivos: sincronizar agora apagaria tudo o \
                 que está na nuvem. Nada foi apagado. Recrie a pasta local se ela sumiu sem querer; se \
                 o vazio for intencional, clique neste erro e escolha Ressincronizar."
            }
        }
    }
}

/// Decide se a rodada precisa ser barrada.
///
/// O bisync propaga exclusões **nos dois sentidos**: se um lado ficou vazio por
/// acidente, a próxima rodada transforma o outro lado em vazio também — e o
/// rclone só reclamaria depois, com um "bisync aborted" incompreensível. Com
/// `resync` o usuário está pedindo explicitamente para aceitar o estado atual,
/// então a trava não se aplica.
pub(crate) fn risco_de_apagar_tudo(
    resync: bool,
    nuvem_vazia: bool,
    local_vazio: bool,
) -> Option<LadoVazio> {
    if resync {
        return None;
    }
    match (nuvem_vazia, local_vazio) {
        // Os dois vazios é uma pasta nova: nada a perder.
        (true, true) => None,
        (true, false) => Some(LadoVazio::Nuvem),
        (false, true) => Some(LadoVazio::Local),
        (false, false) => None,
    }
}

/// Detecta diferença acentuada (>50%) entre os itens de topo dos dois lados
/// quando nenhum está totalmente vazio, para registrar aviso antes do bisync.
pub(crate) fn risco_parcial_de_apagar(
    resync: bool,
    remotos: usize,
    locais: usize,
) -> Option<LadoVazio> {
    if resync || remotos == 0 || locais == 0 {
        return None;
    }
    if locais >= 4 && remotos * 2 < locais {
        return Some(LadoVazio::Nuvem);
    }
    if remotos >= 4 && locais * 2 < remotos {
        return Some(LadoVazio::Local);
    }
    None
}

/// Conta quantos itens existem no topo da pasta local.
fn contar_itens_locais(dir: &Path) -> usize {
    std::fs::read_dir(dir)
        .map(|entradas| entradas.count())
        .unwrap_or(1)
}

/// Conta quantos itens existem no topo da pasta remota. `None` quando não deu
/// para saber (sem rede, por exemplo) — nesse caso a trava não opina.
async fn contar_itens_remotos(state: &AppState, account: &str, remote: &str) -> Option<usize> {
    let resposta = state
        .rclone
        .call(
            "operations/list",
            json!({ "fs": format!("{account}:"), "remote": remote }),
            Duration::from_secs(30),
        )
        .await
        .ok()?;
    Some(
        resposta
            .get("list")
            .and_then(Value::as_array)
            .map(Vec::len)
            .unwrap_or(1),
    )
}

pub(crate) async fn limpar_travas_do_bisync(state: &AppState) -> usize {    let Ok(paths) = state
        .rclone
        .call("config/paths", json!({}), Duration::from_secs(15))
        .await
    else {
        return 0;
    };
    let Some(cache) = paths.get("cache").and_then(Value::as_str) else {
        return 0;
    };
    remover_travas_antigas(&Path::new(cache).join("bisync"), Duration::from_secs(60))
}

/// Remove `*.lck` mais velhos que `idade_minima` em `dir`.
fn remover_travas_antigas(dir: &Path, idade_minima: Duration) -> usize {
    let Ok(entradas) = std::fs::read_dir(dir) else {
        return 0;
    };

    let agora = std::time::SystemTime::now();
    let mut removidas = 0;
    for entrada in entradas.flatten() {
        let caminho = entrada.path();
        if caminho.extension().and_then(|ext| ext.to_str()) != Some("lck") {
            continue;
        }
        let velha = entrada
            .metadata()
            .ok()
            .and_then(|meta| meta.modified().ok())
            .and_then(|modificado| agora.duration_since(modificado).ok())
            .map(|idade| idade >= idade_minima)
            .unwrap_or(true);
        if velha && std::fs::remove_file(&caminho).is_ok() {
            removidas += 1;
        }
    }
    removidas
}

async fn stop_running_jobs(state: &AppState) {
    // Só as tarefas
    // Só as tarefas que o app disparou: o `job/list` do rclone inclui as próprias
    // chamadas RC (inclusive esta), então parar tudo por ele derrubava o daemon.
    let ids = state.running_job_ids().await;

    for id in ids {
        // Interrompida pelo usuário não é falha: sai da fila sem atividade falsa.
        state.mark_job_done(id).await;
        let _ = state
            .rclone
            .call("job/stop", json!({ "jobid": id }), Duration::from_secs(5))
            .await;
    }
}

pub async fn start_profile(state: &AppState, id: &str, force_resync: bool) -> AppResult<Snapshot> {
    start_profile_with(state, id, force_resync, true).await
}

/// Pedido vindo do agendador: sem aviso de conclusão quando nada mudou.
pub async fn start_profile_auto(state: &AppState, id: &str) -> AppResult<Snapshot> {
    start_profile_with(state, id, false, false).await
}

async fn start_profile_with(
    state: &AppState,
    id: &str,
    force_resync: bool,
    manual: bool,
) -> AppResult<Snapshot> {
    // Um segundo pedido para a mesma pasta (bandeja + janela, dois cliques
    // rápidos) devolveria duas tarefas bisync concorrentes brigando pelo mesmo
    // arquivo de trava. Se já existe um pedido em preparação, devolvemos o
    // estado atual, que é exatamente o que o usuário pediu.
    if !state.begin_start(id).await {
        return Ok(snapshot(state).await);
    }
    let result = start_profile_inner(state, id, force_resync, manual).await;
    state.end_start(id).await;
    result
}

async fn start_profile_inner(
    state: &AppState,
    id: &str,
    force_resync: bool,
    manual: bool,
) -> AppResult<Snapshot> {
    if state.paused.load(Ordering::SeqCst) {
        return Err(AppError::new("a sincronização está pausada"));
    }

    let profile = state
        .profiles
        .lock()
        .await
        .iter()
        .find(|profile| profile.id == id)
        .cloned()
        .ok_or_else(|| AppError::new("pasta não encontrada"))?;

    if !profile.enabled {
        return Err(AppError::new("esta pasta está desativada"));
    }

    state.rclone.ensure().await?;

    std::fs::create_dir_all(&profile.local_path).map_err(|error| {
        AppError::new(format!(
            "não foi possível preparar a pasta local {}: {error}",
            profile.local_path
        ))
    })?;

    let remote = if profile.remote_path.is_empty() {
        format!("{}:", profile.account)
    } else {
        profile.remote()
    };

    if !profile.remote_path.is_empty() {
        state
            .rclone
            .call(
                "operations/mkdir",
                json!({ "fs": format!("{}:", profile.account), "remote": profile.remote_path }),
                Duration::from_secs(30),
            )
            .await?;
    }

    let resync = force_resync || profile.resync_needed;

    // Trava de segurança. Uma rodada de bisync propaga exclusões nos dois
    // sentidos: com a pasta na nuvem vazia (foi para a lixeira do Drive, por
    // exemplo) e a local cheia, a rodada apagaria os arquivos do computador e
    // só depois reclamaria com um "bisync aborted" incompreensível. Melhor
    // barrar antes de começar e dizer o que fazer.
    if !resync {
        if let Some(remotos) =
            contar_itens_remotos(state, &profile.account, &profile.remote_path).await
        {
            let locais = contar_itens_locais(Path::new(&profile.local_path));
            if let Some(lado) = risco_de_apagar_tudo(resync, remotos == 0, locais == 0) {
                return Err(AppError::new(lado.mensagem()));
            }
            if let Some(lado) = risco_parcial_de_apagar(resync, remotos, locais) {
                let (pt, en) = match lado {
                    LadoVazio::Nuvem => (
                        format!(
                            "A nuvem tem bem menos itens ({remotos}) que a pasta local ({locais}); o limite de segurança (50%) protege contra exclusões em massa."
                        ),
                        format!(
                            "Cloud has far fewer items ({remotos}) than local folder ({locais}); the 50% safety limit protects against mass deletions."
                        ),
                    ),
                    LadoVazio::Local => (
                        format!(
                            "A pasta local tem bem menos itens ({locais}) que a nuvem ({remotos}); o limite de segurança (50%) protege contra exclusões em massa."
                        ),
                        format!(
                            "Local folder has far fewer items ({locais}) than cloud ({remotos}); the 50% safety limit protects against mass deletions."
                        ),
                    ),
                };
                let detalhe = if crate::idioma::texto("pt", "en") == "en" {
                    &en
                } else {
                    &pt
                };
                state
                    .push_activity(
                        "info",
                        crate::idioma::texto(
                            "Diferença grande entre nuvem e computador",
                            "Large difference between cloud and computer",
                        ),
                        detalhe,
                        Some(&profile.id),
                    )
                    .await;
            }
        }
    }
    let mut filters: Vec<String> = state
        .settings
        .lock()
        .await
        .ignore_rules
        .iter()
        .map(|rule| format!("- {rule}"))
        .collect();
    for folder in &profile.excluded_folders {
        let clean = folder.trim().trim_matches('/');
        if !clean.is_empty() {
            filters.push(format!("- /{clean}/**"));
        }
    }
    // O "Cofre Pessoal" / "Personal Vault" do OneDrive Pessoal é bloqueado pela
    // API do Microsoft Graph e faz o bisync abortar com `ObjectHandle is Invalid`
    // ao sincronizar a raiz da conta.
    if profile.remote_path.is_empty() {
        let is_onedrive = list_accounts_inner(state)
            .await
            .map(|accs| accs.iter().any(|a| a.name == profile.account && a.provider == "onedrive"))
            .unwrap_or(false);
        if is_onedrive {
            filters.push("- /Cofre Pessoal/**".to_string());
            filters.push("- /Cofre Pessoal".to_string());
            filters.push("- /Personal Vault/**".to_string());
            filters.push("- /Personal Vault".to_string());
        }
    }

    let (bandwidth, conflict_resolve) = {
        let settings = state.settings.lock().await;
        let bw = match (settings.bandwidth_up.trim(), settings.bandwidth_down.trim()) {
            ("", "") => None,
            ("", down) => Some(down.to_string()),
            (up, "") => Some(up.to_string()),
            (up, down) => Some(format!("{up}:{down}")),
        };
        let resolve = match settings.conflict_policy.as_str() {
            "newer" => "newer",
            "remote" => "path1",
            "local" => "path2",
            _ => "none",
        };
        (bw, resolve)
    };

    // Trava de execução interrompida (app fechado no meio de um bisync) faria a
    // pasta falhar para sempre. Só limpa quando nada está rodando.
    if state.pending_jobs().await.is_empty() {
        let removidas = limpar_travas_do_bisync(state).await;
        if removidas > 0 {
            state
                .push_activity(
                    "info",
                    crate::idioma::texto(
                        "Trava antiga do bisync removida",
                        "Old bisync lock removed",
                    ),
                    &crate::idioma::escolhe(
                        format!("{removidas} arquivo(s) .lck de uma execução interrompida"),
                        format!("{removidas} .lck file(s) from an interrupted run"),
                    ),
                    Some(&profile.id),
                )
                .await;
        }
    }

    let trash_dir = state.dir.join("lixeira").join(&profile.id);
    let _ = std::fs::create_dir_all(&trash_dir);

    let mut params = json!({
        "path1": remote,
        "path2": profile.local_path,
        "resync": resync,
        "filters": filters,
        "backupDir2": trash_dir.to_string_lossy().to_string(),
        // Pela API RC o bisync *não* herda o padrão de 50% do CLI: sem este campo
        // `maxDelete` vale 0 e qualquer exclusão aborta com "too many deletes"
        // (o usuário apaga um arquivo e a pasta fica presa em erro).
        "maxDelete": 50,
        // Como o bisync guarda as duas versões de um arquivo que mudou dos dois
        // lados. O padrão do rclone (`--conflict-loser num`) gera
        // `nota.txt.conflict1` / `.conflict2`, que a aba Conflitos não reconhece;
        // com `pathname` + este sufixo saem `nota.txt..path1` (a da nuvem, que é
        // o path1) e `nota.txt..path2` (a deste computador) — os nomes que
        // `collect_conflict_files` procura e que `resolve_conflict` valida.
        "conflictResolve": conflict_resolve,
        "conflictLoser": "pathname",
        "conflictSuffix": ".path1,.path2",
        "_async": true
    });
    if let Some(limit) = bandwidth {
        params["bwlimit"] = Value::String(limit);
    }

    let response = state
        .rclone
        .call("sync/bisync", params, Duration::from_secs(60))
        .await?;

    let job_id = response
        .get("jobid")
        .and_then(Value::as_u64)
        .ok_or_else(|| AppError::new("o rclone não retornou um identificador de tarefa"))?;

    state.jobs.lock().await.insert(
        job_id,
        JobRecord {
            profile_id: profile.id.clone(),
            profile_name: if profile.remote_path.is_empty() {
                profile.account.clone()
            } else {
                profile.remote()
            },
            started_at: now_ms(),
            resync,
            done: false,
            misses: 0,
            manual,
        },
    );

    // Só o que o usuário pediu (ou uma ressincronização, que muda o estado das
    // listas) entra na atividade: verificações automáticas de minuto a minuto
    // poluiriam a linha do tempo.
    if manual || resync {
        state
            .push_activity(
                "sync",
                if resync {
                    crate::idioma::texto("Ressincronização iniciada", "Resync started")
                } else {
                    crate::idioma::texto("Sincronização iniciada", "Sync started")
                },
                &format!("{} ↔ {}", remote, profile.local_path),
                Some(&profile.id),
            )
            .await;
    }

    Ok(snapshot(state).await)
}

#[tauri::command]
pub async fn start_sync(
    app: AppHandle,
    state: State<'_, AppState>,
    id: String,
    resync: Option<bool>,
) -> AppResult<Snapshot> {
    // Um pedido manual recomeça a contagem de novas tentativas.
    state.reset_attempts(&id).await;
    let result = start_profile(&state, &id, resync.unwrap_or(false)).await?;
    let _ = app.emit("sync://changed", ());
    Ok(result)
}

#[tauri::command]
pub async fn set_paused(
    app: AppHandle,
    state: State<'_, AppState>,
    paused: bool,
    duration_min: Option<u64>,
) -> AppResult<Snapshot> {
    state.paused.store(paused, Ordering::SeqCst);
    let until = if paused {
        duration_min
            .filter(|&m| m > 0)
            .map(|m| now_ms().saturating_add(m.saturating_mul(60_000)))
            .unwrap_or(0)
    } else {
        0
    };
    state.pause_until.store(until, Ordering::SeqCst);

    if paused {
        stop_running_jobs(&state).await;
        state
            .push_activity(
                "info",
                crate::idioma::texto("Sincronização pausada", "Sync paused"),
                crate::idioma::texto(
                    "Todas as tarefas foram paradas.",
                    "All jobs were stopped.",
                ),
                None,
            )
            .await;
    } else {
        let profiles = state.profiles.lock().await.clone();
        for profile in profiles.into_iter().filter(|profile| profile.enabled) {
            if let Err(error) = start_profile(&state, &profile.id, false).await {
                state
                    .push_activity(
                        "error",
                        crate::idioma::texto("Falha ao retomar", "Could not resume"),
                        &error.message,
                        Some(&profile.id),
                    )
                    .await;
            }
        }
    }

    let snapshot = snapshot(&state).await;
    let _ = app.emit("sync://snapshot", snapshot.clone());
    Ok(snapshot)
}

#[tauri::command]
pub async fn stop_all(app: AppHandle, state: State<'_, AppState>) -> AppResult<Snapshot> {
    stop_running_jobs(&state).await;
    let snapshot = snapshot(&state).await;
    let _ = app.emit("sync://snapshot", snapshot.clone());
    Ok(snapshot)
}

#[tauri::command]
pub async fn sync_status(state: State<'_, AppState>) -> AppResult<Snapshot> {
    Ok(snapshot(&state).await)
}



/// E-mail de cada conta, para a janela poder mostrar *qual* conta está
/// conectada (`Google Drive 1` não diz nada a quem tem duas contas).
///
/// Silencioso por natureza: conta sem token, sem rede ou de provedor que não
/// seja o Google simplesmente não entra no mapa. O cache evita uma ida ao
/// Google a cada leitura de cota (30 s): só refaz quando o `access_token` muda.
#[tauri::command]
pub async fn account_emails(state: State<'_, AppState>) -> AppResult<HashMap<String, String>> {
    static CACHE: OnceLock<Mutex<HashMap<String, (String, String)>>> = OnceLock::new();
    let dump = dump_da_configuracao(&state).await?;
    // Sem par embutido (build sem `.env.oauth`), os campos vazios mandam o
    // Google recusar — e aí a interface só não mostra e-mail.
    let (id_do_app, segredo_do_app) = oauth::do_build().unwrap_or_default();

    let mut emails = HashMap::new();
    for (nome, config) in dump {
        let provider = config
            .get("type")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if provider != "drive" && provider != "onedrive" {
            continue;
        }
        let Some(bruto) = config.get("token").and_then(Value::as_str) else {
            continue;
        };
        let Ok(token) = serde_json::from_str::<Value>(bruto) else {
            continue;
        };
        let acesso = token
            .get("access_token")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if acesso.is_empty() {
            continue;
        }

        let anterior = {
            let cache = CACHE.get_or_init(|| Mutex::new(HashMap::new()));
            let guarda = cache.lock().unwrap_or_else(|erro| erro.into_inner());
            guarda.get(&nome).cloned()
        };
        if let Some((guardado, mesmo_token)) = anterior {
            if mesmo_token == acesso {
                emails.insert(nome, guardado);
                continue;
            }
        }

        let client_id = config
            .get("client_id")
            .and_then(Value::as_str)
            .filter(|valor| !valor.is_empty())
            .unwrap_or(&id_do_app);
        let client_secret = config
            .get("client_secret")
            .and_then(Value::as_str)
            .filter(|valor| !valor.is_empty())
            .unwrap_or(&segredo_do_app);

        let achado = if provider == "onedrive" {
            email_do_onedrive(&token).await
        } else {
            crate::login_google::email_da_conta(&token, client_id, client_secret).await
        };

        if let Some(email) = achado {
            let cache = CACHE.get_or_init(|| Mutex::new(HashMap::new()));
            let mut guarda = cache.lock().unwrap_or_else(|erro| erro.into_inner());
            guarda.insert(nome.clone(), (email.clone(), acesso));
            drop(guarda);
            emails.insert(nome, email);
        }
    }
    Ok(emails)
}

/// E-mail de uma conta OneDrive.
///
/// O `about` do rclone não traz nada disso. O caminho direto é o `/me` do
/// Graph (`User.Read`); se a permissão não estiver lá, o plano B é o dono do
/// drive (`Files.ReadWrite.All`, que o rclone já pede). Conta de empresa pode
/// vir sem `mail` — por isso o `userPrincipalName` também serve.
async fn email_do_onedrive(token: &Value) -> Option<String> {
    let acesso = token.get("access_token").and_then(Value::as_str)?;
    let cliente = reqwest::Client::new();

    // (endereço, campos do `$select`, o e-mail está no dono do drive?)
    let pedidos = [
        ("https://graph.microsoft.com/v1.0/me", "mail,userPrincipalName", false),
        ("https://graph.microsoft.com/v1.0/me/drive", "owner", true),
    ];

    for (endereco, campos, dono) in pedidos {
        let resposta = cliente
            .get(endereco)
            .query(&[("$select", campos)])
            .bearer_auth(acesso)
            .timeout(Duration::from_secs(20))
            .send()
            .await
            .ok()?;
        if !resposta.status().is_success() {
            continue;
        }
        let Ok(corpo) = resposta.json::<Value>().await else {
            continue;
        };
        let achado = if dono {
            email_do_dono(&corpo)
        } else {
            email_do_usuario(&corpo)
        };
        if achado.is_some() {
            return achado;
        }
    }
    None
}

/// `{"mail":"ana@outlook.com"}` (conta pessoal) ou
/// `{"userPrincipalName":"ana@contoso.com"}` (conta de empresa).
fn email_do_usuario(corpo: &Value) -> Option<String> {
    ["mail", "userPrincipalName"]
        .iter()
        .find_map(|chave| corpo.get(*chave).and_then(Value::as_str).and_then(email_valido))
}

/// `{"owner":{"user":{"email":"ana@outlook.com"}}}` → `Some("ana@outlook.com")`.
fn email_do_dono(corpo: &Value) -> Option<String> {
    let dono = corpo.get("owner")?.get("user")?;
    ["email", "userPrincipalName"]
        .iter()
        .find_map(|chave| dono.get(*chave).and_then(Value::as_str).and_then(email_valido))
}

/// Sem `@` não é e-mail: melhor nada do que lixo no cartão.
fn email_valido(valor: &str) -> Option<String> {
    let valor = valor.trim();
    if valor.contains('@') && !valor.chars().any(char::is_whitespace) {
        Some(valor.to_string())
    } else {
        None
    }
}

/// Botão Cancelar da janela "aguardando autorização": o laço local desiste na
/// hora, em vez de deixar a janela presa até o fim do prazo.
#[tauri::command]
pub fn cancel_authorization() {
    crate::login_google::cancelar();
}

#[tauri::command]
pub async fn account_usage(state: State<'_, AppState>) -> AppResult<Vec<AccountUsage>> {
    let accounts = list_accounts_inner(&state).await?;
    if accounts.is_empty() {
        return Ok(Vec::new());
    }
    state.rclone.ensure().await?;

    let mut usages = Vec::new();
    for account in accounts {
        let lido = ler_cota(&state, &account.name).await;
        let usage = match lido {
            Ok((total, used, free)) => {
                let usage = AccountUsage {
                    account: account.name.clone(),
                    label: account.label.clone(),
                    provider: account.provider.clone(),
                    total,
                    used,
                    free,
                    error: None,
                    stale: false,
                };
                state
                    .usage
                    .lock()
                    .await
                    .insert(account.name.clone(), usage.clone());
                usage
            }
            Err(error) => {
                // O Google responde 403 de cota em rajada; o OneDrive some por
                // alguns segundos quando o token é renovado. Em vez de trocar a
                // cota por “indisponível”, segue mostrando o último número lido
                // e sinaliza que está desatualizado.
                let anterior = state.usage.lock().await.get(&account.name).cloned();
                match anterior {
                    Some(mut usage) => {
                        usage.error = Some(error.message);
                        usage.stale = true;
                        usage
                    }
                    None => AccountUsage {
                        account: account.name.clone(),
                        label: account.label.clone(),
                        provider: account.provider.clone(),
                        total: None,
                        used: None,
                        free: None,
                        error: Some(error.message),
                        stale: false,
                    },
                }
            }
        };
        usages.push(usage);
    }

    Ok(usages)
}

/// Lê `operations/about` com uma segunda chance.
///
/// A primeira tentativa pode falhar porque o daemon acabou de subir ou porque o
/// provedor respondeu 403/limite — em ambos os casos repetir resolve.
async fn ler_cota(
    state: &AppState,
    account: &str,
) -> AppResult<(Option<u64>, Option<u64>, Option<u64>)> {
    let parametros = json!({ "fs": format!("{account}:") });
    let mut ultimo = None;
    for tentativa in 0..2 {
        match state
            .rclone
            .call("operations/about", parametros.clone(), Duration::from_secs(25))
            .await
        {
            Ok(value) => {
                return Ok((
                    value.get("total").and_then(Value::as_u64),
                    value.get("used").and_then(Value::as_u64),
                    value.get("free").and_then(Value::as_u64),
                ))
            }
            Err(error) => {
                ultimo = Some(error);
                if tentativa == 0 {
                    // Daemon caído no meio do caminho: sobe de novo antes de repetir.
                    let _ = state.rclone.ensure().await;
                    sleep(Duration::from_millis(700)).await;
                }
            }
        }
    }
    Err(ultimo.unwrap_or_else(|| AppError::new("não foi possível ler a cota")))
}



/// O `config/create` guarda o token, mas o OneDrive só ganha `drive_id` e
/// `drive_type` depois de escolher o drive — é uma “máquina de estados” de
/// perguntas (`config/update` com `nonInteractive`). Sem essas duas chaves, toda
/// listagem e toda sincronização falham com
/// “unable to get drive_id and drive_type”.
pub(crate) async fn completar_onedrive(state: &AppState, name: &str) -> AppResult<()> {
    const LIMITE: usize = 8;
    let mut resposta = state
        .rclone
        .call(
            "config/update",
            json!({
                "name": name,
                "parameters": {},
                "opt": { "nonInteractive": true }
            }),
            Duration::from_secs(120),
        )
        .await?;

    for _ in 0..LIMITE {
        let estado = resposta
            .get("State")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string();
        if estado.is_empty() {
            return Ok(());
        }
        let Some(opcao) = resposta.get("Option").filter(|opcao| !opcao.is_null()) else {
            return Ok(());
        };
        let Some(escolha) = resposta_para(opcao) else {
            return Ok(());
        };
        resposta = state
            .rclone
            .call(
                "config/update",
                json!({
                    "name": name,
                    "parameters": {},
                    "opt": {
                        "nonInteractive": true,
                        "continue": true,
                        "state": estado,
                        "result": escolha
                    }
                }),
                Duration::from_secs(120),
            )
            .await?;
    }
    Ok(())
}

/// Que resposta dar a cada pergunta da configuração do OneDrive.
pub(super) fn resposta_para(opcao: &Value) -> Option<String> {
    let nome = opcao.get("Name").and_then(Value::as_str).unwrap_or_default();
    let exemplos: Vec<&Value> = opcao
        .get("Examples")
        .and_then(Value::as_array)
        .map(|lista| lista.iter().collect())
        .unwrap_or_default();

    // Token já existe: não vale refazer a autorização no navegador.
    if nome == "config_refresh_token" {
        return Some("false".to_string());
    }

    // O padrão do rclone é o primeiro drive da lista, que na conta pessoal pode ser
    // o "ODCMetadataArchive" — um arquivo de metadados, não o OneDrive do usuário.
    if nome == "config_driveid" {
        let principal = exemplos.iter().find(|exemplo| {
            exemplo
                .get("Help")
                .and_then(Value::as_str)
                .map(|ajuda| ajuda.to_lowercase().starts_with("onedrive"))
                .unwrap_or(false)
        });
        if let Some(valor) = principal
            .and_then(|exemplo| exemplo.get("Value"))
            .and_then(Value::as_str)
        {
            return Some(valor.to_string());
        }
    }

    if let Some(padrao) = opcao
        .get("DefaultStr")
        .and_then(Value::as_str)
        .filter(|valor| !valor.is_empty())
    {
        return Some(padrao.to_string());
    }

    exemplos
        .first()
        .and_then(|exemplo| exemplo.get("Value"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

#[cfg(test)]
mod tests {
    use super::{
        contar_itens_locais, email_do_dono, email_do_usuario, montar_relatorio, resposta_para,
        risco_de_apagar_tudo, risco_parcial_de_apagar, versao_mais_nova, ContextoRelatorio,
        LadoVazio,
    };
    use crate::models::{Account, ActivityEntry, Profile, Settings};
    use serde_json::json;

    #[test]
    fn comparacao_de_versao_ignora_prefixo_e_complemento() {
        assert!(versao_mais_nova("1.0.0", "v1.0.1"));
        assert!(versao_mais_nova("1.0.0", "1.1"));
        assert!(versao_mais_nova("1.9.9", "2.0.0"));
        // O quarto componente não conta (semver tem três).
        assert!(!versao_mais_nova("1.0", "1.0.0.1"));
        assert!(!versao_mais_nova("1.0.0", "1.0.0"));
        assert!(!versao_mais_nova("2.0.0", "1.9.9"));
    }

    #[test]
    fn relatorio_nao_leva_o_segredo_do_cliente_oauth() {
        let settings = Settings {
            drive_client_id: "1234-abc.apps.googleusercontent.com".to_string(),
            drive_client_secret: "GOCSPX-nao-pode-vazar".to_string(),
            ..Settings::default()
        };

        let contas = [Account {
            name: "pessoal".to_string(),
            provider: "drive".to_string(),
            label: "Google Drive".to_string(),
            client_origem: "usuario".to_string(),
        }];
        let texto = montar_relatorio(&ContextoRelatorio {
            versao_app: "1.0.0",
            sistema: "linux x86_64 · Teste",
            rclone: Some(("v1.75.2", "/usr/bin/rclone")),
            contas: &contas,
            profiles: &[],
            settings: &settings,
            atividade: &[],
            recuperacao: &[],
        });

        assert!(!texto.contains("GOCSPX-nao-pode-vazar"), "segredo no relatório");
        assert!(
            texto.contains("credenciais OAuth: credenciais próprias do usuário"),
            "origem das credenciais não aparece no relatório"
        );
        // O relatório pode dizer a origem e o client_id (público), nunca o segredo.
        assert!(!texto.contains("GOCSPX"), "segredo do cliente no relatório");
        assert!(
            texto.contains("client_id: 1234-abc.apps.googleusercontent.com"),
            "client_id (público) deveria aparecer para o suporte"
        );
        assert!(texto.contains("BrisaSync 1.0.0"));
        assert!(texto.contains("pessoal (Google Drive)"));
    }

    #[test]
    fn relatorio_resume_erros_e_atividade() {
        let perfil = Profile {
            id: "p1".to_string(),
            account: "pessoal".to_string(),
            remote_path: "Documentos".to_string(),
            local_path: "/home/alguem/Documentos".to_string(),
            enabled: true,
            resync_needed: false,
            last_sync: None,
            last_error: Some("x".repeat(500)),
            last_bytes: 0,
            excluded_folders: Vec::new(),
            sync_interval_min: None,
        };

        let entrada = ActivityEntry {
            id: "1".to_string(),
            kind: "error".to_string(),
            title: "Falha".to_string(),
            detail: "y".repeat(500),
            at: 1_700_000_000_000,
            profile: None,
            files: Vec::new(),
        };

        let texto = montar_relatorio(&ContextoRelatorio {
            versao_app: "1.0.0",
            sistema: "linux",
            rclone: None,
            contas: &[],
            profiles: &[perfil],
            settings: &Settings::default(),
            atividade: &[entrada],
            recuperacao: &["profiles.json estava ilegível".to_string()],
        });

        assert!(texto.contains("rclone: não encontrado"));
        assert!(texto.contains("Recuperação na inicialização"));
        // Nada de linha de 500 caracteres: cada detalhe é resumido.
        assert!(texto.lines().all(|linha| linha.chars().count() < 260));
    }

    #[test]
    fn nao_refaz_a_autorizacao_quando_ja_existe_token() {
        let pergunta = json!({
            "Name": "config_refresh_token",
            "DefaultStr": "true",
            "Type": "bool"
        });
        assert_eq!(resposta_para(&pergunta), Some("false".to_string()));
    }

    #[test]
    fn usa_o_padrao_quando_nao_ha_regra_especial() {
        let pergunta = json!({ "Name": "config_type", "DefaultStr": "onedrive" });
        assert_eq!(resposta_para(&pergunta), Some("onedrive".to_string()));
    }

    #[test]
    fn escolhe_o_drive_onedrive_e_nao_o_arquivo_de_metadados() {
        let pergunta = json!({
            "Name": "config_driveid",
            "DefaultStr": "b!arquivo-de-metadados",
            "Examples": [
                { "Value": "b!arquivo-de-metadados", "Help": "ODCMetadataArchive (personal)" },
                { "Value": "7669343D0F52E211", "Help": "OneDrive (personal)" },
                { "Value": "b!outro", "Help": "C022FB8E (personal)" }
            ]
        });
        assert_eq!(
            resposta_para(&pergunta),
            Some("7669343D0F52E211".to_string())
        );
    }

    #[test]
    fn sem_drive_chamado_onedrive_fica_com_o_padrao() {
        let pergunta = json!({
            "Name": "config_driveid",
            "DefaultStr": "b!documents",
            "Examples": [
                { "Value": "b!documents", "Help": "Documents (business)" }
            ]
        });
        assert_eq!(resposta_para(&pergunta), Some("b!documents".to_string()));
    }

    #[test]
    fn trava_recente_e_respeitada() {
        use std::time::Duration;

        let dir = std::env::temp_dir().join(format!("brisasync-travas-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("pasta temporária");
        let trava = dir.join("conta_Documentos..home_Documentos.lck");
        std::fs::write(&trava, "pid").expect("trava");
        std::fs::write(dir.join("lista.path1.lst"), "x").expect("lista");

        // Recém-criada: pode ser uma sincronização de verdade rodando agora.
        assert_eq!(super::remover_travas_antigas(&dir, Duration::from_secs(60)), 0);
        assert!(trava.exists());

        // Sem idade mínima, a trava antiga sai — e só ela.
        assert_eq!(super::remover_travas_antigas(&dir, Duration::from_secs(0)), 1);
        assert!(!trava.exists());
        assert!(dir.join("lista.path1.lst").exists());

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn trava_barra_a_nuvem_vazia_com_a_pasta_local_cheia() {
        // O caso real de 30/10: `Documentos` esvaziada na nuvem (foi para a
        // lixeira) e os arquivos intactos no computador.
        let lado = risco_de_apagar_tudo(false, true, false).expect("devia barrar");
        assert_eq!(lado, LadoVazio::Nuvem);
        let texto = lado.mensagem();
        assert!(texto.contains("nuvem está vazia"));
        assert!(texto.contains("Nada foi apagado"));
        assert!(texto.contains("Ressincronizar"));
    }

    #[test]
    fn trava_barra_a_pasta_local_vazia_com_a_nuvem_cheia() {
        let lado = risco_de_apagar_tudo(false, false, true).expect("devia barrar");
        assert_eq!(lado, LadoVazio::Local);
        assert!(lado.mensagem().contains("pasta local está vazia"));
    }

    #[test]
    fn ressincronizar_e_o_jeito_de_aceitar_o_estado_atual() {
        // Ressincronizar é o pedido explícito do usuário: a trava não opina.
        assert_eq!(risco_de_apagar_tudo(true, true, false), None);
        assert_eq!(risco_de_apagar_tudo(true, false, true), None);
        assert_eq!(risco_de_apagar_tudo(true, true, true), None);
    }

    #[test]
    fn pasta_nova_ou_em_dia_segue_sem_trava() {
        // Pasta recém-criada, vazia dos dois lados: nada a perder.
        assert_eq!(risco_de_apagar_tudo(false, true, true), None);
        // Caso normal: os dois lados com conteúdo.
        assert_eq!(risco_de_apagar_tudo(false, false, false), None);
    }

    #[test]
    fn risco_parcial_detecta_queda_acima_de_50_por_cento() {
        assert_eq!(risco_parcial_de_apagar(false, 2, 10), Some(LadoVazio::Nuvem));
        assert_eq!(risco_parcial_de_apagar(false, 10, 2), Some(LadoVazio::Local));
        assert_eq!(risco_parcial_de_apagar(false, 5, 10), None);
        assert_eq!(risco_parcial_de_apagar(true, 2, 10), None);
        assert_eq!(risco_parcial_de_apagar(false, 0, 10), None);
    }

    #[test]
    fn email_do_onedrive_vem_do_usuario_ou_do_dono_do_drive() {
        // Caminho direto: `/me` (User.Read).
        let pessoal = json!({ "mail": "ana@outlook.com", "userPrincipalName": "ana@outlook.com" });
        assert_eq!(email_do_usuario(&pessoal), Some("ana@outlook.com".to_string()));
        // Conta de empresa costuma trazer só `userPrincipalName`.
        let empresa = json!({ "mail": null, "userPrincipalName": "ana@contoso.com" });
        assert_eq!(email_do_usuario(&empresa), Some("ana@contoso.com".to_string()));

        // Plano B: dono do drive (Files.ReadWrite.All).
        let dono = json!({ "owner": { "user": { "email": "ana@outlook.com" } } });
        assert_eq!(email_do_dono(&dono), Some("ana@outlook.com".to_string()));
        let dono_empresa = json!({
            "owner": { "user": { "email": "", "userPrincipalName": "ana@contoso.com" } }
        });
        assert_eq!(email_do_dono(&dono_empresa), Some("ana@contoso.com".to_string()));

        // Sem nada legível: o cartão segue com o nome do provedor.
        assert_eq!(email_do_usuario(&json!({})), None);
        assert_eq!(email_do_dono(&json!({ "owner": {} })), None);
        assert_eq!(email_do_dono(&json!({})), None);
    }

    #[test]
    fn sentinela_de_pasta_vazia_le_um_unico_item() {
        let dir = std::env::temp_dir().join(format!("brisasync-vazia-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("pasta temporária");

        assert_eq!(contar_itens_locais(&dir), 0);
        std::fs::write(dir.join("TABELA CLIENTES IPTV.xlsx"), b"x").expect("arquivo");
        assert_eq!(contar_itens_locais(&dir), 1);
        // Pasta que não existe não é "vazia": evita barrar por engano uma
        // pasta que ainda vai ser criada.
        assert!(contar_itens_locais(&dir.join("nao-existe")) > 0);

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn detector_de_conflitos_reconhece_o_sufixo_que_o_app_pede_ao_rclone() {
        use super::{collect_conflict_files, ConflictSlot};
        use std::collections::HashMap;

        let dir = std::env::temp_dir().join(format!("brisasync-conflitos-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let sub = dir.join("Documentos");
        std::fs::create_dir_all(&sub).expect("pasta temporária");

        // `start_sync` manda `conflictSuffix: ".path1,.path2"`; foi isso que o
        // rclone 1.75.2 gravou no teste de campo.
        std::fs::write(sub.join("nota.txt..path1"), "da nuvem").expect("nuvem");
        std::fs::write(sub.join("nota.txt..path2"), "daqui").expect("local");
        // Sobra de uma versão anterior do app (padrão `--conflict-loser num`).
        std::fs::write(dir.join("foto.jpg.conflict1"), "da nuvem").expect("nuvem");
        std::fs::write(dir.join("foto.jpg.conflict2"), "daqui").expect("local");
        // Arquivo comum não vira conflito.
        std::fs::write(dir.join("outra.txt"), "comum").expect("comum");

        let mut encontrados = HashMap::<String, ConflictSlot>::new();
        collect_conflict_files(&dir.to_string_lossy(), 0, &mut encontrados);
        assert_eq!(encontrados.len(), 2);

        let mut bases: Vec<String> = encontrados.values().map(|slot| slot.base.clone()).collect();
        bases.sort();
        assert_eq!(bases, vec!["foto.jpg".to_string(), "nota.txt".to_string()]);

        for slot in encontrados.values() {
            let nuvem = slot.path1.as_deref().expect("versão da nuvem");
            let local = slot.path2.as_deref().expect("versão local");
            assert!(nuvem.contains(&slot.base), "{nuvem}");
            assert!(local.contains(&slot.base), "{local}");
            assert!(nuvem.ends_with("..path1") || nuvem.ends_with(".conflict1"), "{nuvem}");
            assert!(local.ends_with("..path2") || local.ends_with(".conflict2"), "{local}");
        }

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn detector_de_conflitos_nao_confunde_arquivo_comum_com_sufixo() {
        use super::{collect_conflict_files, ConflictSlot};
        use std::collections::HashMap;

        let dir = std::env::temp_dir().join(format!("brisasync-sem-conflito-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("pasta temporária");
        std::fs::write(dir.join("relatorio..path1.bak"), "x").expect("arquivo");
        std::fs::write(dir.join("anotacoes.conflict1.txt"), "x").expect("arquivo");

        let mut encontrados = HashMap::<String, ConflictSlot>::new();
        collect_conflict_files(&dir.to_string_lossy(), 0, &mut encontrados);
        assert!(encontrados.is_empty(), "{:?}", encontrados.len());

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[tokio::test]
    async fn credenciais_do_drive_precisam_vir_em_par() {
        let dir = std::env::temp_dir().join(format!("brisasync-credenciais-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("pasta temporária");
        let state = crate::state::AppState::load(dir.clone());

        // Nada configurado: o rclone usa o projeto compartilhado.
        let vazio = super::parametros_do_provedor(&state, "drive")
            .await
            .expect("sem credenciais");
        assert!(vazio.as_object().map(|mapa| mapa.is_empty()).unwrap_or(false));

        {
            let mut settings = state.settings.lock().await;
            settings.drive_client_id = "123-abc.apps.googleusercontent.com".to_string();
        }
        assert!(super::parametros_do_provedor(&state, "drive").await.is_err());

        {
            let mut settings = state.settings.lock().await;
            settings.drive_client_secret = "GOCSPX-segredo".to_string();
        }
        let parametros = super::parametros_do_provedor(&state, "drive")
            .await
            .expect("credenciais completas");
        assert_eq!(
            parametros.get("client_id").and_then(serde_json::Value::as_str),
            Some("123-abc.apps.googleusercontent.com")
        );
        assert_eq!(
            parametros.get("client_secret").and_then(serde_json::Value::as_str),
            Some("GOCSPX-segredo")
        );

        // OneDrive não usa essas credenciais.
        let onedrive = super::parametros_do_provedor(&state, "onedrive")
            .await
            .expect("onedrive");
        assert!(onedrive.as_object().map(|mapa| mapa.is_empty()).unwrap_or(false));

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[tokio::test]
    async fn client_id_com_formato_errado_e_recusado() {
        let dir = std::env::temp_dir().join(format!("brisasync-credenciais-id-{}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("pasta temporária");
        let state = crate::state::AppState::load(dir.clone());
        {
            let mut settings = state.settings.lock().await;
            settings.drive_client_id = "colei-errado".to_string();
            settings.drive_client_secret = "GOCSPX-segredo".to_string();
        }
        assert!(super::parametros_do_provedor(&state, "drive").await.is_err());
        let _ = std::fs::remove_dir_all(&dir);
    }
}

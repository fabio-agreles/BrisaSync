use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Account {
    pub name: String,
    pub provider: String,
    pub label: String,
    /// Qual projeto OAuth autorizou a conta: `rclone` (o compartilhado, sem
    /// `client_id`), `brisasync` (o embutido no build) ou `usuario` (o que a pessoa
    /// colou em Ajustes → Avançado).
    pub client_origem: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Profile {
    pub id: String,
    pub account: String,
    pub remote_path: String,
    pub local_path: String,
    pub enabled: bool,
    pub resync_needed: bool,
    #[serde(default)]
    pub last_sync: Option<u64>,
    #[serde(default)]
    pub last_error: Option<String>,
    #[serde(default)]
    pub last_bytes: u64,
    #[serde(default)]
    pub excluded_folders: Vec<String>,
}

impl Profile {
    /// Caminho do rclone para a pasta na nuvem: `conta:Documentos`.
    pub fn remote(&self) -> String {
        format!("{}:{}", self.account, self.remote_path)
    }
}

#[derive(Debug, Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct NewProfile {
    pub account: String,
    pub remote_path: String,
    pub local_path: String,
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub excluded_folders: Vec<String>,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Transfer {
    pub name: String,
    pub size: u64,
    pub bytes: u64,
    pub percent: f64,
    pub speed: f64,
    pub eta: Option<f64>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub engine_ready: bool,
    pub paused: bool,
    pub running: bool,
    pub speed: f64,
    pub bytes: u64,
    pub total_bytes: u64,
    pub errors: u64,
    pub transfers: Vec<Transfer>,
    pub jobs: usize,
}

impl Snapshot {
    pub fn stopped(paused: bool) -> Self {
        Self {
            engine_ready: false,
            paused,
            running: false,
            speed: 0.0,
            bytes: 0,
            total_bytes: 0,
            errors: 0,
            transfers: Vec::new(),
            jobs: 0,
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RemoteEntry {
    pub name: String,
    pub path: String,
    pub size: u64,
    pub is_dir: bool,
    pub modified: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Conflict {
    pub id: String,
    pub folder: String,
    pub local_folder: String,
    pub base_name: String,
    pub path1: Option<String>,
    pub path2: Option<String>,
    pub path1_size: Option<u64>,
    pub path2_size: Option<u64>,
    pub path1_modified: Option<u64>,
    pub path2_modified: Option<u64>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AccountUsage {
    pub account: String,
    pub label: String,
    pub provider: String,
    pub total: Option<u64>,
    pub used: Option<u64>,
    pub free: Option<u64>,
    /// Motivo de a leitura ter falhado nesta rodada (fica também no tooltip).
    pub error: Option<String>,
    /// `true` quando os números vieram de uma leitura anterior — é o que evita
    /// trocar a cota por “indisponível” a cada solavanco da API.
    pub stale: bool,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct OAuthInfo {
    /// `usuario`, `brisasync` ou `rclone`.
    pub fonte: String,
    /// `client_id` do projeto em vigor (público; o segredo nunca sai daqui).
    pub client_id: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateInfo {
    /// Versão publicada, sem o `v` do tag.
    pub version: String,
    /// Página da release, para abrir no navegador.
    pub url: String,
    /// URL direta do pacote compatível com este sistema (quando disponível).
    pub asset_url: Option<String>,
    /// Nome do arquivo do pacote compatível.
    pub asset_name: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EngineStatus {
    pub available: bool,
    pub version: Option<String>,
    pub binary: Option<String>,
    pub accounts: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActivityEntry {
    pub id: String,
    pub kind: String,
    pub title: String,
    pub detail: String,
    pub at: u64,
    #[serde(default)]
    pub profile: Option<String>,
    /// O que cada arquivo fez nesta sincronização (vazio quando não houve
    /// movimento ou em registros gravados antes desta versão).
    #[serde(default)]
    pub files: Vec<FileChange>,
}

/// Uma linha do histórico por arquivo, já traduzida para o ponto de vista do
/// usuário: subiu, desceu ou foi apagado de um dos lados.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct FileChange {
    pub name: String,
    /// `sent` | `received` | `deletedRemote` | `deletedLocal`
    pub action: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Settings {
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default)]
    pub bandwidth_up: String,
    #[serde(default)]
    pub bandwidth_down: String,
    #[serde(default = "default_true")]
    pub notifications: bool,
    #[serde(default)]
    pub ignore_rules: Vec<String>,
    #[serde(default)]
    pub proxy: String,
    #[serde(default)]
    pub docs_conversion: bool,
    #[serde(default)]
    pub symlinks: bool,
    #[serde(default = "default_true")]
    pub auto_retry: bool,
    /// Sincroniza sozinho: por intervalo e ao detectar mudanças na pasta local.
    #[serde(default = "default_true")]
    pub auto_sync: bool,
    /// Intervalo da verificação automática, em minutos.
    #[serde(default = "default_interval")]
    pub sync_interval_min: u64,
    /// Credenciais OAuth próprias para o Google Drive (Google Cloud Console).
    /// Vazias = usa o projeto compartilhado do rclone.
    #[serde(default)]
    pub drive_client_id: String,
    #[serde(default)]
    pub drive_client_secret: String,
    /// Idioma da interface: "pt" (padrão) ou "en".
    #[serde(default = "default_language")]
    pub language: String,
    /// Fechar a janela encerra o app. Desligado (padrão): a janela some, o app
    /// continua na bandeja e a sincronização não é interrompida.
    #[serde(default)]
    pub close_quits: bool,
}

fn default_theme() -> String {
    "system".to_string()
}

fn default_language() -> String {
    "pt".to_string()
}

fn default_interval() -> u64 {
    5
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            theme: default_theme(),
            bandwidth_up: String::new(),
            bandwidth_down: String::new(),
            notifications: true,
            ignore_rules: vec![
                "*.tmp".to_string(),
                ".git/".to_string(),
                "node_modules/".to_string(),
            ],
            proxy: String::new(),
            docs_conversion: false,
            symlinks: false,
            auto_retry: true,
            auto_sync: true,
            sync_interval_min: default_interval(),
            drive_client_id: String::new(),
            drive_client_secret: String::new(),
            language: default_language(),
            close_quits: false,
        }
    }
}

/// Resultado de `operations/size`: quanto ocupa uma pasta na nuvem.
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FolderSize {
    pub count: u64,
    pub bytes: u64,
    /// Itens cujo tamanho o provedor não informa (docs nativos do Google, por exemplo).
    pub sizeless: u64,
}

pub fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_millis() as u64)
        .unwrap_or(0)
}

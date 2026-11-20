use crate::models::{now_ms, AccountUsage, ActivityEntry, FileChange, Profile, Settings};
use crate::rclone::Rclone;
use serde::de::DeserializeOwned;
use serde::Serialize;
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
};
use tokio::sync::Mutex;

#[derive(Debug, Clone)]
pub struct JobRecord {
    pub profile_id: String,
    pub profile_name: String,
    pub started_at: u64,
    pub resync: bool,
    pub done: bool,
    /// Quantas leituras seguidas de `job/status` falharam. Serve para não ficar
    /// preso em uma tarefa que o rclone já descartou.
    pub misses: u32,
    /// Pedida pelo usuário (ou ao adicionar a pasta). Sincronizações automáticas
    /// que não movem nada não viram atividade nem notificação.
    pub manual: bool,
}

pub struct AppState {
    pub rclone: Rclone,
    pub dir: PathBuf,
    pub profiles: Mutex<Vec<Profile>>,
    pub jobs: Mutex<HashMap<u64, JobRecord>>,
    pub activity: Mutex<Vec<ActivityEntry>>,
    /// Última cota lida com sucesso, por conta. Uma falha passageira da API não
    /// apaga o número que já estava na tela.
    pub usage: Mutex<HashMap<String, AccountUsage>>,
    pub settings: Mutex<Settings>,
    pub paused: AtomicBool,
    /// Cópia do ajuste "fechar a janela encerra o app". O fechamento da janela
    /// chega por um retorno de chamada síncrono, que não pode esperar o
    /// `Mutex` dos ajustes — e um `try_lock` que falhasse esconderia a janela
    /// justamente de quem pediu para encerrar.
    pub close_quits: AtomicBool,
    /// Quantas novas tentativas cada perfil já consumiu desde a última falha.
    pub attempts: Mutex<HashMap<String, u32>>,
    /// Pastas com um pedido de sincronização em preparação. Evita que dois
    /// cliques (ou bandeja + janela) disparem duas tarefas para a mesma pasta.
    starting: Mutex<HashSet<String>>,
    /// Avisos de leitura na inicialização (JSON corrompido, backup usado). O
    /// `lib.rs` transforma cada um em uma entrada da atividade.
    pub recuperacao: Vec<String>,
}

impl AppState {
    pub fn load(dir: PathBuf) -> Self {
        let mut recuperacao = Vec::new();
        let mut aviso = |leitura: Aviso| {
            if let Some(texto) = leitura {
                recuperacao.push(texto);
            }
        };

        let (profiles, texto) = read_json::<Vec<Profile>>(&dir.join("profiles.json"));
        aviso(texto);
        let profiles = profiles.unwrap_or_default();
        let (activity, texto) = read_json::<Vec<ActivityEntry>>(&dir.join("activity.json"));
        aviso(texto);
        let mut activity = activity.unwrap_or_default();
        activity.sort_by_key(|entry| std::cmp::Reverse(entry.at));
        let (settings, texto) = read_json::<Settings>(&dir.join("settings.json"));
        aviso(texto);
        let settings = settings.unwrap_or_default();
        // Lido antes de o `settings` ir para o `Mutex`: o fechamento da janela
        // consulta só a cópia atômica.
        let close_quits = settings.close_quits;

        Self {
            rclone: Rclone::new(),
            dir,
            profiles: Mutex::new(profiles),
            jobs: Mutex::new(HashMap::new()),
            activity: Mutex::new(activity),
            usage: Mutex::new(HashMap::new()),
            settings: Mutex::new(settings),
            paused: AtomicBool::new(false),
            close_quits: AtomicBool::new(close_quits),
            attempts: Mutex::new(HashMap::new()),
            starting: Mutex::new(HashSet::new()),
            recuperacao,
        }
    }

    /// Incrementa e devolve o número da tentativa atual do perfil.
    pub async fn bump_attempt(&self, profile_id: &str) -> u32 {
        let mut attempts = self.attempts.lock().await;
        let counter = attempts.entry(profile_id.to_string()).or_insert(0);
        *counter += 1;
        *counter
    }

    pub async fn attempts_used(&self, profile_id: &str) -> u32 {
        self.attempts
            .lock()
            .await
            .get(profile_id)
            .copied()
            .unwrap_or(0)
    }

    pub async fn reset_attempts(&self, profile_id: &str) {
        self.attempts.lock().await.remove(profile_id);
    }

    /// Reserva a pasta para um novo pedido. `false` significa que já existe um
    /// pedido em preparação para ela.
    pub async fn begin_start(&self, profile_id: &str) -> bool {
        self.starting
            .lock()
            .await
            .insert(profile_id.to_string())
    }

    pub async fn end_start(&self, profile_id: &str) {
        self.starting.lock().await.remove(profile_id);
    }

    /// Tarefas de sincronização que o app disparou e ainda não viu terminar.
    ///
    /// Deliberadamente **não** usa `job/list` do rclone: toda chamada RC também
    /// vira uma tarefa lá dentro e aparece em `runningIds`, inclusive a própria
    /// chamada que pediu a lista. O resultado nunca fica vazio, então o app
    /// achava que havia sincronização para sempre e nunca concluía nada.
    pub async fn running_job_ids(&self) -> Vec<u64> {
        let jobs = self.jobs.lock().await;
        let mut ids: Vec<u64> = jobs
            .iter()
            .filter(|(_, record)| !record.done)
            .map(|(id, _)| *id)
            .collect();
        ids.sort_unstable();
        ids
    }

    pub async fn pending_jobs(&self) -> Vec<(u64, JobRecord)> {
        let jobs = self.jobs.lock().await;
        let mut pending: Vec<(u64, JobRecord)> = jobs
            .iter()
            .filter(|(_, record)| !record.done)
            .map(|(id, record)| (*id, record.clone()))
            .collect();
        pending.sort_by_key(|(id, _)| *id);
        pending
    }

    pub async fn mark_job_done(&self, job_id: u64) {
        if let Some(record) = self.jobs.lock().await.get_mut(&job_id) {
            record.done = true;
        }
    }

    /// Conta mais uma leitura falha de `job/status` e devolve o total.
    pub async fn record_job_miss(&self, job_id: u64) -> u32 {
        let mut jobs = self.jobs.lock().await;
        match jobs.get_mut(&job_id) {
            Some(record) => {
                record.misses += 1;
                record.misses
            }
            None => 0,
        }
    }

    /// Mantém apenas as `keep` tarefas concluídas mais recentes.
    pub async fn prune_jobs(&self, keep: usize) {
        let mut jobs = self.jobs.lock().await;
        let mut done: Vec<u64> = jobs
            .iter()
            .filter(|(_, record)| record.done)
            .map(|(id, _)| *id)
            .collect();
        if done.len() <= keep {
            return;
        }
        done.sort_unstable();
        let excess = done.len() - keep;
        for id in done.into_iter().take(excess) {
            jobs.remove(&id);
        }
    }

    pub fn save_profiles(&self, profiles: &[Profile]) {
        write_json(&self.dir.join("profiles.json"), profiles);
    }

    pub fn save_settings(&self, settings: &Settings) {
        write_json(&self.dir.join("settings.json"), settings);
    }

    /// Ajuste "fechar a janela encerra o app", sincronizado com `settings`.
    pub fn guardar_close_quits(&self, encerra: bool) {
        self.close_quits.store(encerra, Ordering::Relaxed);
    }

    pub fn encerra_ao_fechar(&self) -> bool {
        self.close_quits.load(Ordering::Relaxed)
    }

    /// O aviso "a janela fechou, o app continua na bandeja" aparece uma vez na
    /// vida do perfil. O marcador fica num arquivo separado de propósito: o
    /// `settings.json` é regravado inteiro pelo front a cada mudança, e o aviso
    /// voltaria a aparecer na primeira vez que o campo fosse esquecido.
    fn arquivo_do_aviso(&self) -> PathBuf {
        self.dir.join("bandeja-aviso.visto")
    }

    pub fn bandeja_avisada(&self) -> bool {
        self.arquivo_do_aviso().exists()
    }

    pub fn marcar_bandeja_avisada(&self) {
        let _ = std::fs::write(self.arquivo_do_aviso(), b"1");
    }

    pub async fn push_activity(&self, kind: &str, title: &str, detail: &str, profile: Option<&str>) {
        self.push_activity_with_files(kind, title, detail, profile, Vec::new())
            .await;
    }

    /// Esvazia o histórico. O arquivo em disco é reescrito para que a limpeza
    /// sobreviva ao fechamento do app.
    pub async fn clear_activity(&self) {
        self.activity.lock().await.clear();
        write_json(&self.dir.join("activity.json"), &Vec::<ActivityEntry>::new());
    }

    /// Mesma atividade de `push_activity`, com a lista de arquivos que mudaram.
    pub async fn push_activity_with_files(
        &self,
        kind: &str,
        title: &str,
        detail: &str,
        profile: Option<&str>,
        files: Vec<FileChange>,
    ) {
        let entry = ActivityEntry {
            id: format!("{}-{:04}", now_ms(), rand_suffix()),
            kind: kind.to_string(),
            title: title.to_string(),
            detail: detail.to_string(),
            at: now_ms(),
            profile: profile.map(str::to_string),
            files,
        };

        let snapshot = {
            let mut activity = self.activity.lock().await;
            // Um erro que se repete (rede caindo por horas) viraria dezenas de
            // linhas idênticas na atividade. Mantém a primeira e ignora as cópias
            // próximas.
            if kind == "error" {
                if let Some(last) = activity.first() {
                    let repeticao = last.kind == "error"
                        && last.title == entry.title
                        && last.detail == entry.detail
                        && last.profile == entry.profile
                        && now_ms().saturating_sub(last.at) < 10 * 60 * 1000;
                    if repeticao {
                        return;
                    }
                }
            }
            activity.insert(0, entry);
            activity.truncate(200);
            activity.clone()
        };
        write_json(&self.dir.join("activity.json"), &snapshot);
    }
}

fn rand_suffix() -> u32 {
    use std::sync::atomic::{AtomicU32, Ordering};
    static COUNTER: AtomicU32 = AtomicU32::new(0);
    COUNTER.fetch_add(1, Ordering::Relaxed)
}

/// Aviso de leitura: texto para a atividade quando o arquivo estava ilegível.
type Aviso = Option<String>;

fn backup_de(path: &Path) -> PathBuf {
    path.with_extension("json.bak")
}

/// `0600` no Unix: `settings.json` guarda o `client_secret` do Google e os
/// ajustes; em máquina multiusuário ninguém além do dono precisa ler isso.
#[cfg(unix)]
fn restringir(path: &Path) {
    use std::os::unix::fs::PermissionsExt;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
}

#[cfg(not(unix))]
fn restringir(_path: &Path) {}

/// Lê um JSON do disco sem fingir que “arquivo quebrado” é “primeira execução”.
///
/// Se o arquivo existe mas não desserializa (queda de energia no meio da
/// gravação, disco cheio, edição manual), a cópia com problema é preservada como
/// `<arquivo>.corrompido`, o backup `<arquivo>.bak` é tentado e o resultado volta
/// com um aviso para a atividade. Antes disto o app abria com os valores padrão e
/// a próxima gravação apagava o resto — perda silenciosa de perfis e ajustes.
fn read_json<T: DeserializeOwned>(path: &Path) -> (Option<T>, Aviso) {
    let bytes = match std::fs::read(path) {
        Ok(bytes) => bytes,
        // Não existe: primeira execução, não há nada a avisar.
        Err(_) => return (None, None),
    };

    let nome = path
        .file_name()
        .map(|nome| nome.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.display().to_string());

    match serde_json::from_slice::<T>(&bytes) {
        Ok(value) => (Some(value), None),
        Err(error) => {
            let copia = path.with_extension("json.corrompido");
            let _ = std::fs::rename(path, &copia);
            let recuperado = std::fs::read(backup_de(path))
                .ok()
                .and_then(|bytes| serde_json::from_slice::<T>(&bytes).ok());

            match recuperado {
                Some(value) => {
                    // Devolve o arquivo bom ao lugar: a próxima gravação parte dele.
                    let _ = std::fs::copy(backup_de(path), path);
                    (
                        Some(value),
                        Some(format!(
                            "{nome} estava ilegível ({error}); recuperei o backup. \
                             A cópia com problema ficou em {}.",
                            copia.display()
                        )),
                    )
                }
                None => (
                    None,
                    Some(format!(
                        "{nome} estava ilegível ({error}) e não havia backup; \
                         comecei com os valores padrão. A cópia com problema ficou em {}.",
                        copia.display()
                    )),
                ),
            }
        }
    }
}

/// Grava de forma atômica, com permissão restrita e guardando a versão anterior.
pub fn write_json<T: Serialize + ?Sized>(path: &Path, value: &T) {
    let Ok(bytes) = serde_json::to_vec_pretty(value) else {
        return;
    };
    let temporary = path.with_extension("json.tmp");
    if std::fs::write(&temporary, &bytes).is_err() {
        return;
    }
    restringir(&temporary);
    // A versão anterior vira `.bak`: se a próxima leitura encontrar lixo (queda
    // no meio do `rename`, disco cheio), `read_json` ainda tem de onde voltar.
    if path.is_file() {
        let _ = std::fs::copy(path, backup_de(path));
    }
    let _ = std::fs::rename(&temporary, path);
}

/// Grava texto com a mesma garantia dos JSONs: temporário, `0600` e `rename`.
/// Usado pelo relatório de diagnóstico, que não é JSON.
pub fn write_text(path: &Path, texto: &str) -> std::io::Result<()> {
    let temporary = path.with_extension("txt.tmp");
    std::fs::write(&temporary, texto)?;
    restringir(&temporary);
    std::fs::rename(&temporary, path)
}

/// Data/hora local em `AAAA-MM-DD-HHMMSS`, para nome de arquivo.
pub fn agora_legivel() -> String {
    match std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH) {
        Ok(tempo) => {
            let segundos = tempo.as_secs();
            let (dias, resto) = (segundos / 86_400, segundos % 86_400);
            let (ano, mes, dia) = data_de_dias(dias as i64);
            format!(
                "{ano:04}-{mes:02}-{dia:02}-{:02}{:02}{:02}",
                resto / 3600,
                (resto % 3600) / 60,
                resto % 60
            )
        }
        Err(_) => "sem-data".to_string(),
    }
}

/// Carimbo de uma entrada de atividade, no mesmo formato (sem segundos).
pub fn formatar_quando(carimbo_ms: u64) -> Option<String> {
    if carimbo_ms == 0 {
        return None;
    }
    let segundos = carimbo_ms / 1000;
    let (dias, resto) = (segundos / 86_400, segundos % 86_400);
    let (ano, mes, dia) = data_de_dias(dias as i64);
    Some(format!(
        "{ano:04}-{mes:02}-{dia:02} {:02}:{:02}",
        resto / 3600,
        (resto % 3600) / 60
    ))
}

/// Dias desde 1970 → (ano, mês, dia), pelo algoritmo civil (Howard Hinnant).
fn data_de_dias(dias: i64) -> (i64, u32, u32) {
    let z = dias + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let ano = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let dia = (doy - (153 * mp + 2) / 5 + 1) as u32;
    let mes = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
    (if mes <= 2 { ano + 1 } else { ano }, mes, dia)
}

#[cfg(test)]
mod tests {
    use super::{read_json, write_json, AppState};
    use crate::models::{ActivityEntry, Settings};
    use std::path::PathBuf;

    fn pasta_temporaria(nome: &str) -> PathBuf {
        let carimbo = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|tempo| tempo.as_nanos())
            .unwrap_or_default();
        let dir = std::env::temp_dir().join(format!(
            "nuvem-teste-{nome}-{}-{carimbo}",
            std::process::id()
        ));
        std::fs::create_dir_all(&dir).expect("pasta temporária");
        dir
    }

    #[tokio::test]
    async fn limpar_atividade_apaga_memoria_e_arquivo() {
        let dir = pasta_temporaria("limpar-atividade");
        let state = AppState::load(dir.clone());
        state
            .push_activity("sync", "Sincronização concluída", "teste", None)
            .await;
        assert_eq!(state.activity.lock().await.len(), 1);

        state.clear_activity().await;
        assert!(state.activity.lock().await.is_empty());

        // A limpeza precisa sobreviver ao fechamento do app.
        let bytes = std::fs::read(dir.join("activity.json")).expect("activity.json");
        let salvo: Vec<ActivityEntry> = serde_json::from_slice(&bytes).expect("json válido");
        assert!(salvo.is_empty());

        let _ = std::fs::remove_dir_all(&dir);
    }

    /// Arquivo ilegível não pode virar “primeira execução”: o backup entra e a
    /// cópia quebrada fica guardada para inspeção.
    #[test]
    fn json_corrompido_usa_backup_e_avisa() {
        let dir = pasta_temporaria("json-backup");
        let path = dir.join("settings.json");

        let bom = Settings {

            sync_interval_min: 15,

            ..Settings::default()

        };
        write_json(&path, &bom);
        // Segunda gravação: a versão anterior passa a existir como `.bak`.
        write_json(&path, &bom);
        assert!(dir.join("settings.json.bak").is_file());

        std::fs::write(&path, b"{ isto nao e json").expect("corromper");

        let (lido, aviso) = read_json::<Settings>(&path);
        let lido = lido.expect("leu o backup");
        assert_eq!(lido.sync_interval_min, 15);
        let aviso = aviso.expect("aviso para a atividade");
        assert!(aviso.contains("ilegível"), "{aviso}");
        assert!(aviso.contains("recuperei o backup"), "{aviso}");

        // A cópia quebrada fica ao lado, e o arquivo bom volta ao lugar.
        assert!(dir.join("settings.json.corrompido").is_file());
        let (de_novo, _) = read_json::<Settings>(&path);
        assert_eq!(de_novo.map(|s| s.sync_interval_min), Some(15));

        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn json_corrompido_sem_backup_avisa_que_perdeu() {
        let dir = pasta_temporaria("json-sem-backup");
        let path = dir.join("settings.json");
        // `[]` não serve: o serde aceita struct a partir de sequência posicional
        // (daria os padrões). Lixo de verdade é o que uma queda no meio do write deixa.
        std::fs::write(&path, b"{\"sync_interval_min\": ").expect("lixo");

        let (lido, aviso) = read_json::<Settings>(&path);
        assert!(lido.is_none());
        let aviso = aviso.expect("aviso");
        assert!(aviso.contains("não havia backup"), "{aviso}");
        assert!(dir.join("settings.json.corrompido").is_file());

        let _ = std::fs::remove_dir_all(&dir);
    }

    /// O `settings.json` guarda o `client_secret` do Google: `0600`, como o
    /// `rclone.conf`. Antes ficava `0644` (legível por qualquer usuário da máquina).
    #[cfg(unix)]
    /// Um `settings.json` de versão anterior (sem `closeQuits`) continua
    /// carregando, e a janela segue indo para a bandeja — que é o que o app
    /// fazia antes de a opção existir.
    #[test]
    fn settings_antigo_continua_abrindo_na_bandeja() {
        let antigo = r#"{"theme":"system","autoSync":true,"syncIntervalMin":5}"#;
        let settings: Settings = serde_json::from_str(antigo).expect("json da versão anterior");
        assert!(!settings.close_quits);

        let dir = pasta_temporaria("close-quits-antigo");
        write_json(&dir.join("settings.json"), &settings);
        let state = AppState::load(dir.clone());
        assert!(!state.encerra_ao_fechar());
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// O ajuste chega ao `AppState` por uma cópia atômica: é ela que o
    /// fechamento da janela consulta.
    #[test]
    fn ajuste_de_fechar_vale_na_hora() {
        let dir = pasta_temporaria("close-quits");
        let state = AppState::load(dir.clone());
        assert!(!state.encerra_ao_fechar());
        state.guardar_close_quits(true);
        assert!(state.encerra_ao_fechar());
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// O aviso da bandeja aparece uma vez. O marcador é um arquivo próprio: se
    /// ficasse nos ajustes, o front (que regrava o `settings.json` inteiro)
    /// apagaria o campo e o aviso voltaria.
    #[test]
    fn aviso_da_bandeja_aparece_uma_vez() {
        let dir = pasta_temporaria("aviso-bandeja");
        let state = AppState::load(dir.clone());
        assert!(!state.bandeja_avisada());
        state.marcar_bandeja_avisada();
        assert!(state.bandeja_avisada());

        // Reabrir o app não pode mostrar o aviso de novo.
        let de_novo = AppState::load(dir.clone());
        assert!(de_novo.bandeja_avisada());
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn json_gravado_fica_so_para_o_dono() {
        use std::os::unix::fs::PermissionsExt;

        let dir = pasta_temporaria("json-permissao");
        let path = dir.join("settings.json");
        write_json(&path, &Settings::default());

        let modo = std::fs::metadata(&path).expect("arquivo").permissions().mode();
        assert_eq!(modo & 0o777, 0o600, "modo {:o}", modo & 0o777);

        let _ = std::fs::remove_dir_all(&dir);
    }
}

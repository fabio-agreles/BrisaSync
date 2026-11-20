//! Sincronização automática: intervalo fixo + observação das pastas locais.
//!
//! O usuário não deve precisar clicar em nada. Duas coisas disparam uma tarefa:
//!
//! * o relógio — a cada `syncIntervalMin` minutos, uma verificação de segurança
//!   que também pega mudanças remotas (o rclone não avisa quando alguém mexe na
//!   nuvem);
//! * o sistema de arquivos — `inotify` na pasta local, com silêncio mínimo para não
//!   disparar no meio de uma gravação grande.
//!
//! As próprias escritas do rclone aparecem como eventos, então tudo que chega
//! enquanto uma tarefa daquela pasta está rodando é descartado, e ainda há uma
//! carência depois da conclusão.

use crate::{commands::start_profile_auto, models::now_ms, state::AppState};
use notify::{Event, EventKind, RecursiveMode, Watcher};
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
    sync::{
        atomic::Ordering,
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager};

/// Cadência do supervisor: alinha watches e decide o que sincronizar.
const TICK: Duration = Duration::from_millis(800);
/// Silêncio necessário na pasta antes de sincronizar uma mudança local.
const QUIET: Duration = Duration::from_secs(4);
/// Carência depois da última sincronização: as escritas do rclone não podem
/// disparar outra tarefa em seguida.
const COOLDOWN: Duration = Duration::from_secs(12);

#[derive(Default)]
struct Shared {
    /// Perfis com tarefa em execução (escrito pelo supervisor, lido pelo observador).
    syncing: Mutex<HashSet<String>>,
    /// Primeiro evento recente de cada perfil.
    dirty: Mutex<HashMap<String, Instant>>,
    /// Última tentativa disparada pelo agendador.
    attempted: Mutex<HashMap<String, Instant>>,
    /// Pastas observadas → perfil dono.
    watched: Mutex<HashMap<PathBuf, String>>,
}

impl Shared {
    fn mark_dirty(&self, profile_id: &str) {
        let ocupado = self
            .syncing
            .lock()
            .map(|syncing| syncing.contains(profile_id))
            .unwrap_or(false);
        if ocupado {
            return;
        }
        if let Ok(mut dirty) = self.dirty.lock() {
            dirty.insert(profile_id.to_string(), Instant::now());
        }
    }

    /// Há quanto tempo o perfil recebeu um evento (se ainda estiver marcado).
    fn dirty_for(&self, profile_id: &str) -> Option<Duration> {
        self.dirty
            .lock()
            .ok()
            .and_then(|dirty| dirty.get(profile_id).map(Instant::elapsed))
    }

    fn take_dirty(&self, profile_id: &str) {
        if let Ok(mut dirty) = self.dirty.lock() {
            dirty.remove(profile_id);
        }
    }

    fn clear_dirty(&self) {
        if let Ok(mut dirty) = self.dirty.lock() {
            dirty.clear();
        }
    }

    fn idle_since_attempt(&self, profile_id: &str) -> Option<Duration> {
        self.attempted
            .lock()
            .ok()
            .and_then(|map| map.get(profile_id).map(Instant::elapsed))
    }

    fn note_attempt(&self, profile_id: &str) {
        if let Ok(mut attempted) = self.attempted.lock() {
            attempted.insert(profile_id.to_string(), Instant::now());
        }
    }
}

/// Eventos que interessam (criação, alteração, remoção, renomeação).
fn relevant(event: &Event) -> bool {
    matches!(
        event.kind,
        EventKind::Any | EventKind::Create(_) | EventKind::Modify(_) | EventKind::Remove(_)
    )
}

/// Arquivos que nunca devem acordar a sincronização: travas de escritório,
/// temporários de editor e o próprio marcador do bisync.
fn ignored(path: &Path) -> bool {
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default();
    name.starts_with(".~")
        || name.starts_with("~$")
        || name.starts_with(".goutputstream")
        || name.ends_with(".tmp")
        || name.ends_with(".swp")
        || name.ends_with(".lck")
        || name == ".brisasync_check"
        || path.components().any(|part| part.as_os_str() == ".git")
}

fn handle_event(shared: &Shared, event: Event) {
    if !relevant(&event) {
        return;
    }
    let Ok(watched) = shared.watched.lock() else {
        return;
    };
    for path in &event.paths {
        if ignored(path) {
            continue;
        }
        // A pasta observada mais específica é a dona do arquivo.
        let owner = watched
            .iter()
            .filter(|(root, _)| path.starts_with(root))
            .max_by_key(|(root, _)| root.as_os_str().len())
            .map(|(_, profile_id)| profile_id.clone());
        if let Some(profile_id) = owner {
            shared.mark_dirty(&profile_id);
        }
    }
}

/// Alinha as pastas observadas com os perfis ativos, criando e removendo watches.
fn sync_watches<W: Watcher + ?Sized>(
    watcher: &mut W,
    shared: &Shared,
    wanted: &HashMap<PathBuf, String>,
) {
    let atuais: Vec<PathBuf> = shared
        .watched
        .lock()
        .map(|watched| watched.keys().cloned().collect())
        .unwrap_or_default();

    for path in atuais {
        if wanted.contains_key(&path) {
            continue;
        }
        let _ = watcher.unwatch(&path);
        if let Ok(mut watched) = shared.watched.lock() {
            watched.remove(&path);
        }
    }

    for (path, profile_id) in wanted {
        let ja_observada = shared
            .watched
            .lock()
            .map(|watched| watched.contains_key(path))
            .unwrap_or(false);
        if ja_observada {
            continue;
        }
        if watcher.watch(path, RecursiveMode::Recursive).is_ok() {
            if let Ok(mut watched) = shared.watched.lock() {
                watched.insert(path.clone(), profile_id.clone());
            }
        }
    }
}

pub fn spawn(app: AppHandle) {
    tauri::async_runtime::spawn(async move {
        let shared = Arc::new(Shared::default());
        let callback_shared = shared.clone();

        let mut watcher = match notify::recommended_watcher(
            move |result: notify::Result<Event>| {
                if let Ok(event) = result {
                    handle_event(&callback_shared, event);
                }
            },
        ) {
            Ok(watcher) => watcher,
            Err(error) => {
                // Sem observador o app continua funcionando: o intervalo ainda
                // sincroniza, só que sem a reação imediata às mudanças locais.
                eprintln!("observador de arquivos indisponível: {error}");
                return;
            }
        };

        let mut remote_watcher = crate::remote_changes::RemoteWatcher::default();

        loop {
            let state = app.state::<AppState>();
            supervise(&app, &state, &shared, &mut watcher, &mut remote_watcher).await;
            tokio::time::sleep(TICK).await;
        }
    });
}

async fn supervise<W: Watcher + ?Sized>(
    app: &AppHandle,
    state: &AppState,
    shared: &Shared,
    watcher: &mut W,
    remote_watcher: &mut crate::remote_changes::RemoteWatcher,
) {
    if state.paused.load(Ordering::SeqCst) {
        shared.clear_dirty();
        return;
    }

    let settings = state.settings.lock().await.clone();
    if !settings.auto_sync {
        shared.clear_dirty();
        // Sem sincronização automática não há motivo para observar pastas.
        sync_watches(watcher, shared, &HashMap::new());
        return;
    }

    let profiles = state.profiles.lock().await.clone();
    let pending: HashSet<String> = state
        .pending_jobs()
        .await
        .into_iter()
        .map(|(_, record)| record.profile_id)
        .collect();

    if let Ok(mut syncing) = shared.syncing.lock() {
        *syncing = pending.clone();
    }

    let wanted: HashMap<PathBuf, String> = profiles
        .iter()
        .filter(|profile| profile.enabled)
        .filter_map(|profile| {
            let path = PathBuf::from(&profile.local_path);
            path.is_dir().then(|| (path, profile.id.clone()))
        })
        .collect();
    sync_watches(watcher, shared, &wanted);

    let interval = Duration::from_secs(settings.sync_interval_min.max(1) * 60);

    let active_accounts: HashSet<String> = profiles
        .iter()
        .filter(|profile| profile.enabled && !pending.contains(&profile.id))
        .map(|profile| profile.account.clone())
        .collect();
    let changed_accounts = remote_watcher.check_accounts(state, &active_accounts).await;

    for profile in profiles.iter().filter(|profile| profile.enabled) {
        if pending.contains(&profile.id) {
            shared.take_dirty(&profile.id);
            continue;
        }

        // Perfil nunca sincronizado conta como "muito tempo atrás".
        let since_sync = profile
            .last_sync
            .map(|at| Duration::from_millis(now_ms().saturating_sub(at)))
            .unwrap_or(interval);

        // Referência: o que aconteceu por último — a conclusão da sincronização ou
        // o pedido anterior do agendador. Evita repetir a cada tique quando a
        // tentativa anterior falhou.
        let ocioso = match shared.idle_since_attempt(&profile.id) {
            Some(attempt) => since_sync.min(attempt),
            None => since_sync,
        };

        let por_intervalo = ocioso >= interval;
        let por_mudanca = shared
            .dirty_for(&profile.id)
            .map(|parado| parado >= QUIET && ocioso >= COOLDOWN)
            .unwrap_or(false);
        let por_nuvem = changed_accounts.contains(&profile.account) && ocioso >= COOLDOWN;

        if !por_intervalo && !por_mudanca && !por_nuvem {
            continue;
        }

        shared.take_dirty(&profile.id);
        shared.note_attempt(&profile.id);

        if let Err(error) = start_profile_auto(state, &profile.id).await {
            // Se o pedido nem chegou ao rclone, a pasta precisa mostrar o erro —
            // senão o cartão continua “em dia” enquanto a atividade diz o contrário.
            {
                let mut profiles = state.profiles.lock().await;
                if let Some(alvo) = profiles.iter_mut().find(|item| item.id == profile.id) {
                    alvo.last_error = Some(error.to_string());
                }
                state.save_profiles(&profiles);
            }
            state
                .push_activity(
                    "error",
                    crate::idioma::texto("Sincronização automática", "Automatic sync"),
                    &format!("{}: {}", profile.local_path, error),
                    Some(&profile.id),
                )
                .await;
            let _ = app.emit("sync://changed", ());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{ignored, relevant};
    use notify::{event::ModifyKind, Event, EventKind};
    use std::path::Path;

    #[test]
    fn ignora_lixo_de_editor_e_de_escritorio() {
        assert!(ignored(Path::new("/p/.~TABELA.xls")));
        assert!(ignored(Path::new("/p/~$contrato.docx")));
        assert!(ignored(Path::new("/p/.goutputstream-ABC123")));
        assert!(ignored(Path::new("/p/nota.tmp")));
        assert!(ignored(Path::new("/p/.git/HEAD")));
        assert!(ignored(Path::new("/p/.brisasync_check")));
        assert!(!ignored(Path::new("/p/foto.jpg")));
        assert!(!ignored(Path::new("/p/pasta/relatorio.docx")));
    }

    #[test]
    fn considera_criacao_alteracao_e_remocao() {
        let evento = |kind| Event {
            kind,
            paths: vec![],
            attrs: Default::default(),
        };
        assert!(relevant(&evento(EventKind::Create(
            notify::event::CreateKind::File
        ))));
        assert!(relevant(&evento(EventKind::Modify(ModifyKind::Any))));
        assert!(relevant(&evento(EventKind::Remove(
            notify::event::RemoveKind::File
        ))));
        assert!(!relevant(&evento(EventKind::Access(
            notify::event::AccessKind::Any
        ))));
    }
}

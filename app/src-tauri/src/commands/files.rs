use super::{
    completar_onedrive, list_accounts_inner, remote_fs, require_account, snapshot, split_remote,
    start_profile,
};
use crate::{
    error::{AppError, AppResult},
    models::*,
    state::AppState,
};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    path::{Path, PathBuf},
    time::Duration,
};
use tauri::{AppHandle, Emitter, State};

#[tauri::command]
pub async fn list_remote(
    state: State<'_, AppState>,
    account: String,
    path: String,
) -> AppResult<Vec<RemoteEntry>> {
    if !list_accounts_inner(&state)
        .await?
        .iter()
        .any(|item| item.name == account)
    {
        return Err(AppError::new("conta não encontrada"));
    }
    state.rclone.ensure().await?;

    let params = json!({
        "fs": format!("{account}:"),
        "remote": path.trim_matches('/'),
        "opt": { "recurse": false }
    });
    let response = match state
        .rclone
        .call("operations/list", params.clone(), Duration::from_secs(45))
        .await
    {
        Ok(value) => value,
        // Conta OneDrive antiga, sem `drive_id`: conserta e tenta de novo.
        Err(error) if error.to_string().contains("drive_id and drive_type") => {
            completar_onedrive(&state, &account).await?;
            state
                .rclone
                .call("operations/list", params, Duration::from_secs(45))
                .await?
        }
        Err(error) => return Err(error),
    };

    let mut entries: Vec<RemoteEntry> = response
        .get("list")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .map(|item| RemoteEntry {
                    name: item
                        .get("Name")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    path: item
                        .get("Path")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    size: item.get("Size").and_then(Value::as_u64).unwrap_or(0),
                    is_dir: item.get("IsDir").and_then(Value::as_bool).unwrap_or(false),
                    modified: item
                        .get("ModTime")
                        .and_then(Value::as_str)
                        .map(str::to_string),
                })
                .collect()
        })
        .unwrap_or_default();

    entries.sort_by(|left, right| {
        right
            .is_dir
            .cmp(&left.is_dir)
            .then_with(|| left.name.to_lowercase().cmp(&right.name.to_lowercase()))
    });
    Ok(entries)
}

/// Detecta os arquivos de conflito gerados pelo bisync (`..path1` / `..path2`).
#[derive(Default)]
pub(super) struct ConflictSlot {
    pub(super) dir: String,
    pub(super) base: String,
    pub(super) path1: Option<String>,
    pub(super) path2: Option<String>,
}

async fn scan_conflicts_inner(state: &AppState) -> Vec<Conflict> {
    let profiles = state.profiles.lock().await.clone();
    let mut conflicts = Vec::new();

    for profile in profiles {
        let mut found = HashMap::<String, ConflictSlot>::new();
        collect_conflict_files(&profile.local_path, 0, &mut found);

        for slot in found.into_values() {
            let (path1_size, path1_modified) = file_meta(&slot.path1);
            let (path2_size, path2_modified) = file_meta(&slot.path2);
            conflicts.push(Conflict {
                id: format!("{}::{}::{}", profile.id, slot.dir, slot.base),
                folder: if profile.remote_path.is_empty() {
                    profile.account.clone()
                } else {
                    profile.remote()
                },
                local_folder: slot.dir,
                base_name: slot.base,
                path1: slot.path1,
                path2: slot.path2,
                path1_size,
                path2_size,
                path1_modified,
                path2_modified,
            });
        }
    }

    conflicts.sort_by(|left, right| left.base_name.cmp(&right.base_name));
    conflicts
}

fn file_meta(path: &Option<String>) -> (Option<u64>, Option<u64>) {
    let Some(path) = path else {
        return (None, None);
    };
    match std::fs::metadata(path) {
        Ok(metadata) => {
            let modified = metadata
                .modified()
                .ok()
                .and_then(|time| time.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|duration| duration.as_millis() as u64);
            (Some(metadata.len()), modified)
        }
        Err(_) => (None, None),
    }
}

/// Sufixos que o bisync usa para guardar as duas versões de um arquivo em
/// conflito, na ordem (nuvem, este computador).
///
/// O primeiro par é o que pedimos em `start_sync` (`conflictLoser: pathname`
/// com `conflictSuffix: ".path1,.path2"`). O segundo é o padrão do rclone
/// (`--conflict-loser num`), que fica para trás em pastas sincronizadas por
/// versões anteriores do app — sem ele, esses arquivos ficariam invisíveis na
/// aba Conflitos.
const SUFIXOS_DE_CONFLITO: [(&str, &str); 2] = [
    ("..path1", "..path2"),
    (".conflict1", ".conflict2"),
];

#[derive(Clone, Copy)]
enum LadoDoConflito {
    Nuvem,
    Local,
}

pub(super) fn collect_conflict_files(
    dir: &str,
    depth: usize,
    found: &mut HashMap<String, ConflictSlot>,
) {
    if depth > 6 {
        return;
    }
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            let name = entry.file_name().to_string_lossy().to_string();
            if name != ".git" && name != "node_modules" {
                collect_conflict_files(&path.to_string_lossy(), depth + 1, found);
            }
            continue;
        }

        let name = entry.file_name().to_string_lossy().to_string();
        let full = path.to_string_lossy().to_string();
        for (lado, suffix) in SUFIXOS_DE_CONFLITO.iter().flat_map(|(nuvem, local)| {
            [("nuvem", *nuvem), ("local", *local)]
        }) {
            if let Some(base) = name.strip_suffix(suffix) {
                let key = format!("{dir}\u{0}{base}");
                let slot = found.entry(key).or_insert_with(|| ConflictSlot {
                    dir: dir.to_string(),
                    base: base.to_string(),
                    ..Default::default()
                });
                if lado == "nuvem" {
                    slot.path1 = Some(full.clone());
                } else {
                    slot.path2 = Some(full.clone());
                }
            }
        }
    }
}

#[tauri::command]
pub async fn folder_size(
    state: State<'_, AppState>,
    account: String,
    path: String,
) -> AppResult<FolderSize> {
    require_account(&state, &account).await?;
    state.rclone.ensure().await?;

    let response = state
        .rclone
        .call(
            "operations/size",
            json!({ "fs": format!("{account}:"), "remote": path.trim_matches('/') }),
            Duration::from_secs(300),
        )
        .await?;

    Ok(FolderSize {
        count: response.get("count").and_then(Value::as_u64).unwrap_or(0),
        bytes: response.get("bytes").and_then(Value::as_u64).unwrap_or(0),
        sizeless: response.get("sizeless").and_then(Value::as_u64).unwrap_or(0),
    })
}

/// Envia um arquivo ou pasta local para a pasta que está aberta na aba Arquivos.
#[tauri::command]
pub async fn upload_file(
    app: AppHandle,
    state: State<'_, AppState>,
    account: String,
    remote_dir: String,
    local_path: String,
) -> AppResult<String> {
    require_account(&state, &account).await?;

    let source = PathBuf::from(&local_path);
    let is_dir = source.is_dir();
    if !source.is_file() && !is_dir {
        return Err(AppError::new(format!(
            "arquivo ou pasta local não encontrado: {local_path}"
        )));
    }
    let name = source
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .ok_or_else(|| AppError::new("nome de arquivo inválido"))?;

    let remote_path = if remote_dir.trim_matches('/').is_empty() {
        name.clone()
    } else {
        format!("{}/{}", remote_dir.trim_matches('/'), name)
    };

    state.rclone.ensure().await?;
    if is_dir {
        let dst_fs = remote_fs(&account, &remote_path);
        state
            .rclone
            .call(
                "sync/copy",
                json!({
                    "srcFs": local_path,
                    "dstFs": dst_fs
                }),
                Duration::from_secs(3600),
            )
            .await?;
    } else {
        let parent = source
            .parent()
            .map(|value| value.to_string_lossy().to_string())
            .ok_or_else(|| AppError::new("arquivo sem pasta de origem"))?;
        let destination = remote_fs(&account, &remote_dir);
        state
            .rclone
            .call(
                "operations/copyfile",
                json!({
                    "srcFs": parent,
                    "srcRemote": name,
                    "dstFs": destination,
                    "dstRemote": name
                }),
                Duration::from_secs(3600),
            )
            .await?;
    }

    state
        .push_activity_with_files(
            "upload",
            crate::idioma::texto("Enviado para a nuvem", "Uploaded to the cloud"),
            &format!("{} → {account}:{remote_path}", name),
            None,
            vec![FileChange {
                name: name.clone(),
                action: "sent".to_string(),
            }],
        )
        .await;
    let _ = app.emit("sync://changed", ());
    Ok(remote_path)
}

/// Baixa um arquivo da nuvem para a pasta local escolhida.
#[tauri::command]
pub async fn download_file(
    app: AppHandle,
    state: State<'_, AppState>,
    account: String,
    remote_path: String,
    local_dir: String,
) -> AppResult<String> {
    require_account(&state, &account).await?;
    let (parent, name) = split_remote(&remote_path)?;

    let target_dir = PathBuf::from(&local_dir);
    std::fs::create_dir_all(&target_dir).map_err(|error| {
        AppError::new(format!(
            "não foi possível criar a pasta {local_dir}: {error}"
        ))
    })?;
    let target = target_dir.join(&name);
    if target.exists() {
        return Err(AppError::new(format!(
            "já existe um arquivo em {}",
            target.display()
        )));
    }

    state.rclone.ensure().await?;
    state
        .rclone
        .call(
            "operations/copyfile",
            json!({
                "srcFs": remote_fs(&account, &parent),
                "srcRemote": name,
                "dstFs": local_dir,
                "dstRemote": name
            }),
            Duration::from_secs(3600),
        )
        .await?;

    state
        .push_activity_with_files(
            "download",
            crate::idioma::texto("Baixado da nuvem", "Downloaded from the cloud"),
            &format!("{account}:{remote_path} → {}", target.display()),
            None,
            vec![FileChange {
                name: name.clone(),
                action: "received".to_string(),
            }],
        )
        .await;
    let _ = app.emit("sync://changed", ());
    Ok(target.to_string_lossy().to_string())
}

#[tauri::command]
pub async fn scan_conflicts(state: State<'_, AppState>) -> AppResult<Vec<Conflict>> {
    Ok(scan_conflicts_inner(&state).await)
}

/// Resolve uma cópia do conflito. A versão descartada vai para a lixeira do
/// BrisaSync, nunca é apagada; a escolhida volta ao nome original. Em seguida,
/// dispara a sincronização imediata da pasta para propagar a resolução.
#[tauri::command]
pub async fn resolve_conflict(
    app: AppHandle,
    state: State<'_, AppState>,
    action: String,
    local_folder: String,
    base_name: String,
    path1: Option<String>,
    path2: Option<String>,
) -> AppResult<Vec<Conflict>> {
    if !matches!(action.as_str(), "remote" | "local" | "both") {
        return Err(AppError::new("ação de resolução inválida"));
    }

    let base = Path::new(&base_name);
    if base_name.is_empty()
        || base
            .file_name()
            .map(|name| name != std::ffi::OsStr::new(&base_name))
            .unwrap_or(true)
        || base_name.contains(['/', '\\'])
    {
        return Err(AppError::new("nome de arquivo inválido"));
    }

    let folder = std::fs::canonicalize(&local_folder)
        .map_err(|_| AppError::new("a pasta local do conflito não existe mais"))?;

    let profile_id = {
        let profiles = state.profiles.lock().await;
        profiles.iter().find(|profile| {
            std::fs::canonicalize(&profile.local_path)
                .map(|candidate| folder.starts_with(&candidate))
                .unwrap_or(false)
        }).map(|p| p.id.clone())
    };
    if profile_id.is_none() {
        return Err(AppError::new(
            "a pasta não pertence a nenhuma sincronização do BrisaSync",
        ));
    }

    let target = folder.join(&base_name);
    if target.exists() {
        return Err(AppError::new(format!(
            "já existe \"{base_name}\" nesta pasta; mova ou renomeie antes de resolver"
        )));
    }

    // `nuvem` = o arquivo que veio do path1; `local` = o do path2. Os sufixos
    // aceitos são os mesmos que `collect_conflict_files` reconhece, porque o
    // conflito pode ter sido criado por esta versão (`..path1`) ou por uma
    // anterior (`.conflict1`).
    let verify = |candidate: &Option<String>, lado: LadoDoConflito| -> AppResult<PathBuf> {
        let raw = candidate
            .as_ref()
            .ok_or_else(|| AppError::new("a versão escolhida não está mais disponível"))?;
        let path = std::fs::canonicalize(raw)
            .map_err(|_| AppError::new("a versão escolhida não está mais disponível"))?;
        if path.parent() != Some(folder.as_path()) {
            return Err(AppError::new("a versão escolhida não está na pasta esperada"));
        }
        let name = path
            .file_name()
            .map(|name| name.to_string_lossy().to_string())
            .unwrap_or_default();
        let conhecido = SUFIXOS_DE_CONFLITO.iter().any(|(nuvem, local)| {
            let sufixo = match lado {
                LadoDoConflito::Nuvem => nuvem,
                LadoDoConflito::Local => local,
            };
            name.ends_with(sufixo)
        });
        if !conhecido {
            return Err(AppError::new("arquivo de conflito inesperado"));
        }
        Ok(path)
    };

    let backup_dir = state
        .dir
        .join("lixeira")
        .join("conflitos")
        .join(now_ms().to_string());

    match action.as_str() {
        "remote" => {
            let winner = verify(&path1, LadoDoConflito::Nuvem)?;
            if let Ok(loser) = verify(&path2, LadoDoConflito::Local) {
                move_to_backup(&loser, &backup_dir)?;
            }
            std::fs::rename(&winner, &target)
                .map_err(|error| AppError::new(format!("não foi possível restaurar o arquivo: {error}")))?;
        }
        "local" => {
            let winner = verify(&path2, LadoDoConflito::Local)?;
            if let Ok(loser) = verify(&path1, LadoDoConflito::Nuvem) {
                move_to_backup(&loser, &backup_dir)?;
            }
            std::fs::rename(&winner, &target)
                .map_err(|error| AppError::new(format!("não foi possível restaurar o arquivo: {error}")))?;
        }
        _ => {
            let remote = verify(&path1, LadoDoConflito::Nuvem)?;
            let local = verify(&path2, LadoDoConflito::Local)?;
            let remote_target = unique_path(&folder, &variant_name(&base_name, "nuvem"));
            let local_target = unique_path(&folder, &variant_name(&base_name, "local"));
            std::fs::rename(&remote, &remote_target)
                .map_err(|error| AppError::new(format!("não foi possível renomear a versão da nuvem: {error}")))?;
            std::fs::rename(&local, &local_target)
                .map_err(|error| AppError::new(format!("não foi possível renomear a versão local: {error}")))?;
        }
    }

    state
        .push_activity(
            "conflict",
            crate::idioma::texto("Conflito resolvido", "Conflict resolved"),
            &format!("{base_name} · {}", action_label(&action)),
            None,
        )
        .await;

    // Dispara a sincronização imediata da pasta para propagar a resolução para a nuvem
    if let Some(id) = profile_id {
        state.reset_attempts(&id).await;
        let _ = start_profile(&state, &id, false).await;
    }
    let _ = app.emit("sync://changed", ());
    let _ = app.emit("sync://snapshot", snapshot(&state).await);

    Ok(scan_conflicts_inner(&state).await)
}

fn action_label(action: &str) -> &'static str {
    match action {
        "remote" => crate::idioma::texto(
            "mantida a versão da nuvem",
            "kept the cloud version",
        ),
        "local" => crate::idioma::texto("mantida a versão local", "kept the local version"),
        _ => crate::idioma::texto("mantidas as duas versões", "kept both versions"),
    }
}

fn move_to_backup(path: &Path, backup_dir: &Path) -> AppResult<()> {
    std::fs::create_dir_all(backup_dir)?;
    let name = path
        .file_name()
        .map(|name| name.to_string_lossy().to_string())
        .unwrap_or_else(|| "arquivo".to_string());
    let destination = backup_dir.join(name);
    if std::fs::rename(path, &destination).is_ok() {
        return Ok(());
    }
    std::fs::copy(path, &destination)?;
    std::fs::remove_file(path)?;
    Ok(())
}

fn variant_name(base: &str, label: &str) -> String {
    let path = Path::new(base);
    let stem = path
        .file_stem()
        .map(|stem| stem.to_string_lossy().to_string())
        .unwrap_or_else(|| base.to_string());
    match path.extension() {
        Some(extension) => format!("{stem} ({label}).{}", extension.to_string_lossy()),
        None => format!("{stem} ({label})"),
    }
}

fn unique_path(folder: &Path, name: &str) -> PathBuf {
    let mut candidate = folder.join(name);
    if !candidate.exists() {
        return candidate;
    }
    let path = Path::new(name);
    let stem = path
        .file_stem()
        .map(|stem| stem.to_string_lossy().to_string())
        .unwrap_or_else(|| name.to_string());
    let extension = path
        .extension()
        .map(|extension| format!(".{}", extension.to_string_lossy()))
        .unwrap_or_default();
    for index in 2..100 {
        candidate = folder.join(format!("{stem} {index}{extension}"));
        if !candidate.exists() {
            return candidate;
        }
    }
    candidate
}

const TRASH_TTL_MS: u64 = 30 * 24 * 60 * 60 * 1000;

fn collect_trash_items(
    root: &Path,
    dir: &Path,
    cutoff_ms: u64,
    items: &mut Vec<TrashItem>,
) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            collect_trash_items(root, &path, cutoff_ms, items);
            if std::fs::read_dir(&path)
                .map(|mut d| d.next().is_none())
                .unwrap_or(false)
            {
                let _ = std::fs::remove_dir(&path);
            }
            continue;
        }
        let Ok(meta) = entry.metadata() else {
            continue;
        };
        let modified_ms = meta
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        if modified_ms > 0 && modified_ms < cutoff_ms {
            let _ = std::fs::remove_file(&path);
            continue;
        }
        let Ok(rel) = path.strip_prefix(root) else {
            continue;
        };
        let rel_str = rel.to_string_lossy().replace('\\', "/");
        let profile_id = rel
            .components()
            .next()
            .map(|c| c.as_os_str().to_string_lossy().to_string())
            .filter(|s| s != "conflitos");
        let name = path
            .file_name()
            .map(|n| n.to_string_lossy().to_string())
            .unwrap_or_else(|| rel_str.clone());
        items.push(TrashItem {
            id: rel_str.clone(),
            name,
            relative_path: rel_str,
            size: meta.len(),
            deleted_at: modified_ms,
            profile_id,
        });
    }
}

#[tauri::command]
pub async fn list_trash(state: State<'_, AppState>) -> AppResult<Vec<TrashItem>> {
    let root = state.dir.join("lixeira");
    if !root.exists() {
        return Ok(Vec::new());
    }
    let cutoff = now_ms().saturating_sub(TRASH_TTL_MS);
    let mut items = Vec::new();
    collect_trash_items(&root, &root, cutoff, &mut items);
    items.sort_by(|a, b| b.deleted_at.cmp(&a.deleted_at));
    Ok(items)
}

#[tauri::command]
pub async fn restore_trash_item(
    state: State<'_, AppState>,
    id: String,
    destination_dir: String,
) -> AppResult<String> {
    let root = state
        .dir
        .join("lixeira")
        .canonicalize()
        .map_err(|_| AppError::new("lixeira vazia"))?;
    let candidate = root
        .join(&id)
        .canonicalize()
        .map_err(|_| AppError::new("item não encontrado na lixeira"))?;
    if !candidate.starts_with(&root) || !candidate.is_file() {
        return Err(AppError::new("caminho inválido na lixeira"));
    }
    let dest_folder = PathBuf::from(&destination_dir);
    if !dest_folder.is_dir() {
        return Err(AppError::new("pasta de destino inválida"));
    }
    let file_name = candidate
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .ok_or_else(|| AppError::new("nome de arquivo inválido"))?;
    let target = unique_path(&dest_folder, &file_name);
    if std::fs::rename(&candidate, &target).is_err() {
        std::fs::copy(&candidate, &target)
            .map_err(|e| AppError::new(format!("não foi possível restaurar: {e}")))?;
        let _ = std::fs::remove_file(&candidate);
    }
    Ok(target.to_string_lossy().to_string())
}

#[tauri::command]
pub async fn empty_trash(state: State<'_, AppState>) -> AppResult<()> {
    let root = state.dir.join("lixeira");
    if root.exists() {
        std::fs::remove_dir_all(&root)
            .map_err(|e| AppError::new(format!("não foi possível esvaziar a lixeira: {e}")))?;
    }
    Ok(())
}


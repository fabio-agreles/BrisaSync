//! Iniciar junto com o sistema.
//!
//! Fora do Flatpak, um arquivo em `~/.config/autostart` resolve — é o que o
//! plugin do Tauri faz. Dentro do Flatpak o pedido precisa passar pelo portal
//! `org.freedesktop.portal.Background`: só ele sabe montar a linha de comando
//! certa (`flatpak run ...`) e marcar o arquivo com `X-Flatpak`, para que o
//! sistema trate o item como um app sandboxed.
//!
//! O estado real é sempre o arquivo em `~/.config/autostart`: ele reflete tanto
//! o que fizemos aqui quanto o que o usuário mudou nas configurações do sistema.

use crate::error::{AppError, AppResult};
use std::{collections::HashMap, path::PathBuf, time::Duration};
use zbus::zvariant::{OwnedObjectPath, Value};

/// Identificador do app dentro do Flatpak (também é o nome do `.desktop` gerado).
const APP_ID: &str = "app.brisasync.BrisaSync";
const PORTAL_DEST: &str = "org.freedesktop.portal.Desktop";
const PORTAL_PATH: &str = "/org/freedesktop/portal/desktop";
const PORTAL_IFACE: &str = "org.freedesktop.portal.Background";
/// Quanto esperar: o portal pode abrir uma janela de permissão.
const ESPERA: Duration = Duration::from_secs(60);

pub fn in_flatpak() -> bool {
    std::path::Path::new("/.flatpak-info").exists()
}

/// Caminho do `.desktop` de autostart **do sistema** (`$HOME` real, não o do sandbox).
fn desktop_file() -> Option<PathBuf> {
    let home = std::env::var_os("HOME")?;
    Some(
        PathBuf::from(home)
            .join(".config")
            .join("autostart")
            .join(format!("{APP_ID}.desktop")),
    )
}

/// O arquivo existe e não está marcado como `Hidden=true`?
pub fn enabled() -> bool {
    desktop_file()
        .and_then(|path| std::fs::read_to_string(path).ok())
        .map(|text| ativo(&text))
        .unwrap_or(false)
}

/// Um `.desktop` de autostart só está ativo se não tiver `Hidden=true`
/// (é assim que o GNOME e o KDE "desligam" o item sem apagar o arquivo).
fn ativo(text: &str) -> bool {
    !text.lines().any(|line| {
        let Some((key, value)) = line.split_once('=') else {
            return false;
        };
        key.trim().eq_ignore_ascii_case("Hidden") && value.trim().eq_ignore_ascii_case("true")
    })
}

fn pedir_ao_portal(enable: bool) -> AppResult<()> {
    let reason = "Mantém as pastas sincronizadas mesmo com a janela do BrisaSync fechada.";
    let token = format!("nuvem_autostart_{}", if enable { "on" } else { "off" });

    let connection = zbus::blocking::Connection::session()
        .map_err(|error| AppError::new(format!("sem acesso ao barramento da sessão: {error}")))?;

    let mut options: HashMap<&str, Value<'_>> = HashMap::new();
    options.insert("handle_token", Value::from(token.as_str()));
    options.insert("reason", Value::from(reason));
    options.insert("autostart", Value::from(enable));
    // O portal monta `flatpak run --command=<1º item> <id> <resto>`, então o
    // primeiro item é o executável (dentro do sandbox, `/app/bin/nuvem`).
    let exe = std::env::current_exe()
        .map(|path| path.to_string_lossy().into_owned())
        .unwrap_or_else(|_| APP_ID.to_owned());
    if enable {
        options.insert("commandline", Value::from(vec![exe.as_str(), "--minimized"]));
    }

    let handle: OwnedObjectPath = connection
        .call_method(
            Some(PORTAL_DEST),
            PORTAL_PATH,
            Some(PORTAL_IFACE),
            "RequestBackground",
            &("", options),
        )
        .map_err(|error| AppError::new(format!("o sistema recusou o pedido: {error}")))?
        .body()
        .deserialize()
        .map_err(|error| AppError::new(format!("resposta inesperada do portal: {error}")))?;

    // Só para registro: o resultado que importa é o arquivo em `~/.config/autostart`.
    eprintln!("autostart: pedido registrado em {handle}");
    Ok(())
}

/// O portal não escreve `Icon=`, então o item aparece sem ícone na lista de
/// "aplicativos de inicialização" do sistema. Completamos só isso.
fn completar_icone() {
    let Some(path) = desktop_file() else {
        return;
    };
    let Ok(text) = std::fs::read_to_string(&path) else {
        return;
    };
    if text
        .lines()
        .any(|line| line.trim_start().starts_with("Icon="))
    {
        return;
    }
    let mut novo = text;
    if !novo.ends_with('\n') {
        novo.push('\n');
    }
    novo.push_str("Icon=");
    novo.push_str(APP_ID);
    novo.push('\n');
    let _ = std::fs::write(&path, novo);
}

async fn pedir(enable: bool) -> AppResult<()> {
    tauri::async_runtime::spawn_blocking(move || pedir_ao_portal(enable))
        .await
        .map_err(|error| AppError::new(format!("falha ao falar com o portal: {error}")))?
}

/// Espera o portal gravar (ou apagar) o arquivo, conferindo a cada 250 ms.
async fn aguardar(enable: bool) -> bool {
    let mut passos = (ESPERA.as_millis() / 250) as usize;
    while passos > 0 && enabled() != enable {
        tokio::time::sleep(Duration::from_millis(250)).await;
        passos -= 1;
    }
    enabled() == enable
}

/// Liga ou desliga o início automático pelo portal. Devolve o estado final.
pub async fn request(enable: bool) -> AppResult<bool> {
    if enabled() == enable {
        return Ok(enable);
    }

    if enable {
        pedir(true).await?;
        if aguardar(true).await {
            completar_icone();
            return Ok(true);
        }
        return Err(AppError::new(
            "o sistema não autorizou o início automático. Tente de novo e confirme o pedido do BrisaSync.",
        ));
    }

    // Desligar: o arquivo é nosso, então apagá-lo basta. O portal fica como
    // segunda tentativa caso o sandbox não deixe mexer no arquivo.
    if let Some(path) = desktop_file() {
        let _ = std::fs::remove_file(path);
    }
    if aguardar(false).await {
        return Ok(false);
    }

    pedir(false).await?;
    if aguardar(false).await {
        return Ok(false);
    }

    Err(AppError::new(
        "não foi possível desligar o início automático. Remova o BrisaSync dos aplicativos de inicialização do sistema.",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn caminho_aponta_para_o_autostart_do_sistema() {
        if std::env::var_os("HOME").is_none() {
            return;
        }
        let path = desktop_file().unwrap();
        assert!(path.ends_with(".config/autostart/app.brisasync.BrisaSync.desktop"));
    }

    #[test]
    fn hidden_desativa() {
        let padrao = "[Desktop Entry]\nType=Application\nName=BrisaSync\nExec=flatpak run app.brisasync.BrisaSync\n";
        assert!(ativo(padrao));
        assert!(!ativo(&format!("{padrao}Hidden=true\n")));
        // Espaços e maiúsculas não mudam a leitura.
        assert!(!ativo("  Hidden = TRUE  \n"));
    }
}

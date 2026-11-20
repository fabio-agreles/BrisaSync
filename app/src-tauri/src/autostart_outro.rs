//! Iniciar junto com o sistema fora do Unix (Windows).
//!
//! No Linux o caminho é um `.desktop` em `~/.config/autostart` — e, dentro do
//! Flatpak, o portal `org.freedesktop.portal.Background`. No Windows nada disso
//! existe: o plugin `tauri-plugin-autostart` grava a chave `Run` do registro
//! (`HKCU\Software\Microsoft\Windows\CurrentVersion\Run`), que é onde o próprio
//! Gerenciador de Tarefas lê a lista de inicialização.
//!
//! Este módulo existe para a API ser a mesma nos dois sistemas: os comandos
//! `set_autostart`/`autostart_enabled` chamam `in_flatpak()` antes de tudo e,
//! fora do Flatpak, falam direto com o plugin.

use crate::error::{AppError, AppResult};

/// Só existe Flatpak no Linux.
pub fn in_flatpak() -> bool {
    false
}

/// O estado real vem do plugin (registro do Windows), não daqui.
pub fn enabled() -> bool {
    false
}

/// No Windows o pedido nunca chega neste módulo — quem escreve é o plugin.
pub async fn request(_enable: bool) -> AppResult<bool> {
    Err(AppError::new(
        "o início automático no Windows é controlado pelo registro do sistema; \
         use o comando do aplicativo.",
    ))
}

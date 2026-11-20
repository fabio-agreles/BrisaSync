//! Idioma dos textos que nascem no Rust.
//!
//! A interface é traduzida no frontend (`src/lib/i18n.ts`), mas três coisas
//! nascem deste lado e aparecem para o usuário mesmo com a janela fechada:
//! a bandeja do sistema, as notificações nativas e o registro de atividade.
//! Este módulo guarda o idioma escolhido em Ajustes e oferece o par
//! português/inglês para essas frases.
//!
//! A escolha vem do `settings.json` na abertura e muda quando o usuário troca
//! o idioma (`save_settings` chama `definir` e `tray::aplicar_idioma`).
use std::sync::atomic::{AtomicU8, Ordering};

const PT: u8 = 0;
const EN: u8 = 1;

static IDIOMA: AtomicU8 = AtomicU8::new(PT);

/// Guarda o idioma a partir do código salvo nos ajustes (`"pt"`/`"en"`).
pub fn definir(codigo: &str) {
    let valor = if codigo == "en" { EN } else { PT };
    IDIOMA.store(valor, Ordering::Relaxed);
}

/// `true` quando a interface está em inglês.
pub fn ingles() -> bool {
    IDIOMA.load(Ordering::Relaxed) == EN
}

/// Escolhe entre a versão em português e a em inglês.
pub fn texto(pt: &'static str, en: &'static str) -> &'static str {
    if ingles() {
        en
    } else {
        pt
    }
}

/// Mesma ideia de [`texto`], para frases montadas com `format!`.
pub fn escolhe(pt: String, en: String) -> String {
    if ingles() {
        en
    } else {
        pt
    }
}

#[cfg(test)]
mod tests {
    use super::{definir, escolhe, ingles, texto};
    use std::sync::Mutex;

    // O idioma é global: os testes que o trocam não podem rodar ao mesmo tempo.
    static TRAVA: Mutex<()> = Mutex::new(());

    #[test]
    fn portugues_e_o_padrao() {
        let _guarda = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        definir("pt");
        assert!(!ingles());
        assert_eq!(texto("Sair", "Quit"), "Sair");
        definir("qualquer outra coisa");
        assert!(!ingles(), "código desconhecido volta para o português");
    }

    #[test]
    fn ingles_troca_as_frases() {
        let _guarda = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        definir("en");
        assert!(ingles());
        assert_eq!(texto("Sair", "Quit"), "Quit");
        assert_eq!(
            escolhe("2 arquivos".to_string(), "2 files".to_string()),
            "2 files"
        );
        definir("pt");
    }
}

//! Credenciais OAuth do Google.
//!
//! O rclone usa, por padrão, um projeto compartilhado por todos os usuários dele
//! — e a cota de requisições por minuto desse projeto vive estourada. O
//! BrisaSync pode embutir no binário o **seu próprio** projeto (o do app) e, por
//! cima disso, o usuário pode colar as credenciais dele em Ajustes → Avançado.
//!
//! Precedência: usuário > projeto do BrisaSync > projeto do rclone.
//!
//! De onde vêm as credenciais do build, em ordem:
//! 1. variável de ambiente em tempo de execução (`BRISASYNC_GOOGLE_CLIENT_ID` e
//!    `BRISASYNC_GOOGLE_CLIENT_SECRET`) — permite testar sem recompilar;
//! 2. variável de ambiente no momento da compilação (mesmos nomes), que é como
//!    o CI injeta o par a partir dos segredos do repositório.
//!
//! `client_secret` de aplicativo instalado não é segredo de verdade (o próprio
//! rclone publica o dele), mas ainda assim ele não fica no repositório: entra
//! pelo ambiente do build.

/// Sufixo obrigatório de um `client_id` do Google.
pub const SUFIXO_CLIENT_ID: &str = ".apps.googleusercontent.com";

/// De onde vêm as credenciais que o app vai usar.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Fonte {
    /// O usuário colou o par dele em Ajustes → Avançado.
    Usuario,
    /// Projeto OAuth embutido no build (o do próprio BrisaSync).
    BrisaSync,
    /// Projeto compartilhado do rclone (sem `client_id` nenhum).
    Rclone,
}

impl Fonte {
    /// Identificador usado na API com o frontend.
    pub fn id(self) -> &'static str {
        match self {
            Fonte::Usuario => "usuario",
            Fonte::BrisaSync => "brisasync",
            Fonte::Rclone => "rclone",
        }
    }

    /// Texto para o relatório de diagnóstico.
    pub fn descricao(self) -> &'static str {
        match self {
            Fonte::Usuario => "credenciais próprias do usuário",
            Fonte::BrisaSync => "projeto do BrisaSync",
            Fonte::Rclone => "projeto compartilhado do rclone",
        }
    }
}

/// Credenciais em vigor, já resolvidas.
#[derive(Debug, Clone)]
pub struct Credenciais {
    pub client_id: Option<String>,
    pub client_secret: Option<String>,
    pub fonte: Fonte,
}

impl Credenciais {
    /// Par no formato que o `config/create` do rclone espera.
    pub fn como_json(&self) -> serde_json::Value {
        match (&self.client_id, &self.client_secret) {
            (Some(id), Some(secret)) => serde_json::json!({
                "client_id": id,
                "client_secret": secret,
            }),
            _ => serde_json::json!({}),
        }
    }
}

/// Aceita o par só se o `client_id` tiver o formato do Google e o segredo vier
/// preenchido — par pela metade geraria erro confuso no navegador.
fn par_valido(id: &str, secret: &str) -> Option<(String, String)> {
    let id = id.trim();
    let secret = secret.trim();
    let formato_ok = id.ends_with(SUFIXO_CLIENT_ID);
    let segredo_ok = !secret.is_empty() && !secret.chars().any(char::is_whitespace);
    if formato_ok && segredo_ok {
        Some((id.to_string(), secret.to_string()))
    } else {
        None
    }
}

/// Escolhe o primeiro par válido da lista (na ordem de precedência).
fn primeiro_valido(
    candidatos: impl IntoIterator<Item = Option<(String, String)>>,
) -> Option<(String, String)> {
    candidatos.into_iter().flatten().next()
}

/// Credenciais do projeto embutidas no build (ou no ambiente de execução).
pub fn do_build() -> Option<(String, String)> {
    let ambiente = par_valido(
        &std::env::var("BRISASYNC_GOOGLE_CLIENT_ID").unwrap_or_default(),
        &std::env::var("BRISASYNC_GOOGLE_CLIENT_SECRET").unwrap_or_default(),
    );
    let compilado = match (
        option_env!("BRISASYNC_GOOGLE_CLIENT_ID"),
        option_env!("BRISASYNC_GOOGLE_CLIENT_SECRET"),
    ) {
        (Some(id), Some(secret)) => par_valido(id, secret),
        _ => None,
    };
    primeiro_valido([ambiente, compilado])
}

/// Qual projeto autorizou uma conta já conectada (o `client_id` gravado no
/// `rclone.conf`), comparando com o par embutido no build.
pub fn fonte_da_conta(client_id: Option<&str>, do_build: Option<&str>) -> Fonte {
    match client_id.map(str::trim) {
        Some(id) if !id.is_empty() => {
            if Some(id) == do_build.map(str::trim) {
                Fonte::BrisaSync
            } else {
                Fonte::Usuario
            }
        }
        _ => Fonte::Rclone,
    }
}

/// Resolve o par que vale agora: o do usuário ganha do embutido.
pub fn efetivas(do_usuario: (&str, &str)) -> Credenciais {
    com(do_usuario, do_build())
}

/// Mesma regra de precedência, com o par do build já resolvido (testável).
fn com(do_usuario: (&str, &str), do_build_par: Option<(String, String)>) -> Credenciais {
    let usuario = par_valido(do_usuario.0, do_usuario.1);

    match primeiro_valido([usuario.clone(), do_build_par]) {
        Some((client_id, client_secret)) => Credenciais {
            client_id: Some(client_id),
            client_secret: Some(client_secret),
            fonte: if usuario.is_some() {
                Fonte::Usuario
            } else {
                Fonte::BrisaSync
            },
        },
        None => Credenciais {
            client_id: None,
            client_secret: None,
            fonte: Fonte::Rclone,
        },
    }
}

#[cfg(test)]
mod testes {
    use super::*;

    const BOM: &str = "123-abc.apps.googleusercontent.com";

    #[test]
    fn par_pela_metade_nao_vale() {
        assert!(par_valido(BOM, "").is_none());
        assert!(par_valido("colei-errado", "GOCSPX-x").is_none());
        assert!(par_valido(BOM, "GOCSPX-com espaco").is_none());
        assert_eq!(
            par_valido(&format!(" {BOM} "), " GOCSPX-x ").unwrap(),
            (BOM.to_string(), "GOCSPX-x".to_string())
        );
    }

    /// Roda de verdade quando BRISASYNC_GOOGLE_CLIENT_ID/_SECRET estão no ambiente
    /// (é o teste que prova o par real do projeto do BrisaSync); em CI, sem as
    /// variáveis, ele não tem o que conferir e passa sem fazer nada.
    #[test]
    fn ambiente_com_o_par_do_projeto_vira_fonte_brisasync() {
        let (Ok(id), Ok(segredo)) = (
            std::env::var("BRISASYNC_GOOGLE_CLIENT_ID"),
            std::env::var("BRISASYNC_GOOGLE_CLIENT_SECRET"),
        ) else {
            return;
        };
        if par_valido(&id, &segredo).is_none() {
            return;
        }
        let credenciais = efetivas(("", ""));
        assert_eq!(credenciais.fonte, Fonte::BrisaSync);
        assert_eq!(credenciais.client_id.as_deref(), Some(id.trim()));
        assert_eq!(credenciais.como_json()["client_secret"], segredo.trim());
        // E o par do usuário continua ganhando, como manda a precedência.
        assert_eq!(efetivas((&id, &segredo)).fonte, Fonte::Usuario);
    }

    #[test]
    fn primeiro_valido_respeita_a_ordem() {
        let escolhido = primeiro_valido([
            None,
            Some(("a".to_string(), "1".to_string())),
            Some(("b".to_string(), "2".to_string())),
        ]);
        assert_eq!(escolhido.unwrap().0, "a");
    }

    #[test]
    fn sem_nada_o_app_fica_no_projeto_do_rclone() {
        // O ambiente de teste não define as variáveis do projeto do BrisaSync e o
        // binário de teste não foi compilado com elas.
        if do_build().is_none() {
            let credenciais = efetivas(("", ""));
            assert_eq!(credenciais.fonte, Fonte::Rclone);
            assert!(credenciais.client_id.is_none());
            assert_eq!(credenciais.como_json(), serde_json::json!({}));
        }
    }

    #[test]
    fn usuario_ganha_do_projeto_embutido() {
        let do_usuario = (BOM.to_string(), "GOCSPX-do-usuario".to_string());
        let credenciais = efetivas((&do_usuario.0, &do_usuario.1));
        assert_eq!(credenciais.fonte, Fonte::Usuario);
        assert_eq!(credenciais.como_json()["client_secret"], "GOCSPX-do-usuario");
    }

    #[test]
    fn projeto_embutido_no_build_vale_quando_o_usuario_nao_preencheu() {
        let do_build_par = Some((BOM.to_string(), "GOCSPX-do-brisasync".to_string()));
        let credenciais = com(("", ""), do_build_par.clone());
        assert_eq!(credenciais.fonte, Fonte::BrisaSync);
        assert_eq!(credenciais.como_json()["client_id"], BOM);

        // E o do usuário continua ganhando dele.
        let credenciais = com((BOM, "GOCSPX-meu"), do_build_par);
        assert_eq!(credenciais.fonte, Fonte::Usuario);
        assert_eq!(credenciais.como_json()["client_secret"], "GOCSPX-meu");
    }

    #[test]
    fn origem_da_conta_conectada() {
        assert_eq!(fonte_da_conta(None, Some(BOM)), Fonte::Rclone);
        assert_eq!(fonte_da_conta(Some("   "), Some(BOM)), Fonte::Rclone);
        assert_eq!(fonte_da_conta(Some(BOM), Some(BOM)), Fonte::BrisaSync);
        assert_eq!(fonte_da_conta(Some(BOM), None), Fonte::Usuario);
        assert_eq!(
            fonte_da_conta(Some("999-outro.apps.googleusercontent.com"), Some(BOM)),
            Fonte::Usuario
        );
    }

    #[test]
    fn credenciais_do_usuario_invalidas_sao_ignoradas() {
        let credenciais = efetivas(("sem-formato", "GOCSPX-x"));
        assert_ne!(credenciais.fonte, Fonte::Usuario);
    }
}

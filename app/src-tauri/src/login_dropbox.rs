//! Autorização do Dropbox feita pelo próprio BrisaSync.
//!
//! Quando `BRISASYNC_DROPBOX_CLIENT_ID` e `BRISASYNC_DROPBOX_CLIENT_SECRET`
//! estão definidos (no ambiente ou embutidos no build), o app abre o navegador,
//! escuta o retorno em `http://localhost:53682/`, mostra a página do BrisaSync
//! e entrega o token pronto ao rclone por `config/create` (`nonInteractive`).
//!
//! Sem essas credenciais, o `connect_account` cai no fluxo padrão do rclone.

use crate::error::AppResult;
use serde_json::{json, Value};
use std::time::Duration;
use tokio::net::TcpListener;

use crate::login_google::{
    agora_em_segundos, campo, campos_da_consulta, cancelada, codificar, consulta_do_pedido, falha,
    ler_pedido, limpar_cancelamento, motivo, pagina_de_erro, pagina_de_sucesso, responder, rfc3339,
    sorteio,
};

const PORTA: u16 = 53682;
const RETORNO: &str = "http://localhost:53682/";

const URL_AUTORIZACAO: &str = "https://www.dropbox.com/oauth2/authorize";
const URL_TOKEN: &str = "https://api.dropboxapi.com/oauth2/token";

const PRAZO_DO_NAVEGADOR: Duration = Duration::from_secs(600);

/// Credenciais do app Dropbox embutidas no build ou definidas no ambiente.
pub fn credenciais_do_build() -> Option<(String, String)> {
    let env_id = std::env::var("BRISASYNC_DROPBOX_CLIENT_ID").unwrap_or_default();
    let env_secret = std::env::var("BRISASYNC_DROPBOX_CLIENT_SECRET").unwrap_or_default();
    if !env_id.trim().is_empty() && !env_secret.trim().is_empty() {
        return Some((env_id.trim().to_string(), env_secret.trim().to_string()));
    }
    match (
        option_env!("BRISASYNC_DROPBOX_CLIENT_ID"),
        option_env!("BRISASYNC_DROPBOX_CLIENT_SECRET"),
    ) {
        (Some(id), Some(secret)) if !id.trim().is_empty() && !secret.trim().is_empty() => {
            Some((id.trim().to_string(), secret.trim().to_string()))
        }
        _ => None,
    }
}

/// Autoriza uma conta Dropbox e devolve o token no formato que o `rclone.conf` guarda.
pub async fn autorizar(client_id: &str, client_secret: &str) -> AppResult<Value> {
    limpar_cancelamento();
    let estado = sorteio(16)?;
    let ouvintes = abrir_porta().await?;
    let endereco = endereco_de_autorizacao(client_id, &estado);

    crate::commands::abrir_endereco(&endereco).map_err(|erro| {
        falha(
            &format!("não foi possível abrir o navegador para autorizar a conta: {erro}"),
            &format!("could not open the browser to authorize the account: {erro}"),
        )
    })?;

    let codigo = esperar_codigo(ouvintes, &estado).await?;
    trocar_codigo_por_token(&codigo, client_id, client_secret).await
}

/// Monta o endereço de consentimento do Dropbox (`token_access_type=offline` garante `refresh_token`).
pub fn endereco_de_autorizacao(client_id: &str, estado: &str) -> String {
    format!(
        "{URL_AUTORIZACAO}?client_id={}&response_type=code&redirect_uri={}&token_access_type=offline&state={}",
        codificar(client_id),
        codificar(RETORNO),
        codificar(estado),
    )
}

async fn abrir_porta() -> AppResult<Vec<TcpListener>> {
    let mut ouvintes = Vec::new();
    let v4 = TcpListener::bind(("127.0.0.1", PORTA)).await;
    match v4 {
        Ok(ouvinte) => ouvintes.push(ouvinte),
        Err(erro) => {
            let v6 = TcpListener::bind(("::1", PORTA)).await;
            return match v6 {
                Ok(ouvinte) => Ok(vec![ouvinte]),
                Err(_) => Err(falha(
                    &format!(
                        "a porta {PORTA} está ocupada — feche o outro aplicativo que a usa e tente de novo ({erro})."
                    ),
                    &format!(
                        "port {PORTA} is in use — close the other application using it and try again ({erro})."
                    ),
                )),
            };
        }
    }
    if let Ok(v6) = TcpListener::bind(("::1", PORTA)).await {
        ouvintes.push(v6);
    }
    Ok(ouvintes)
}

async fn esperar_codigo(ouvintes: Vec<TcpListener>, estado: &str) -> AppResult<String> {
    let espera = async {
        loop {
            let (mut fluxo, _) = receber(&ouvintes).await?;

            let pedido = ler_pedido(&mut fluxo).await;
            let Some(consulta) = pedido
                .as_deref()
                .and_then(consulta_do_pedido)
                .map(|consulta| consulta.to_string())
            else {
                responder(
                    &mut fluxo,
                    404,
                    &pagina_de_erro("Nada aqui.", "Nothing here."),
                )
                .await;
                continue;
            };

            let campos = campos_da_consulta(&consulta);

            if let Some(erro) = campo(&campos, "error") {
                let descricao = campo(&campos, "error_description").unwrap_or_default();
                let recusou = erro == "access_denied";
                responder(
                    &mut fluxo,
                    200,
                    &pagina_de_erro(
                        if recusou {
                            "Autorização cancelada"
                        } else {
                            "O Dropbox recusou a autorização"
                        },
                        if recusou {
                            "Authorization cancelled"
                        } else {
                            "Dropbox refused the authorization"
                        },
                    ),
                )
                .await;
                return Err(if recusou {
                    falha(
                        "a autorização foi cancelada no navegador — nada foi alterado.",
                        "the authorization was cancelled in the browser — nothing was changed.",
                    )
                } else {
                    falha(
                        &format!("o Dropbox recusou a autorização ({erro} {descricao})."),
                        &format!("Dropbox refused the authorization ({erro} {descricao})."),
                    )
                });
            }

            if campo(&campos, "state").as_deref() != Some(estado) {
                responder(
                    &mut fluxo,
                    400,
                    &pagina_de_erro("Tentativa antiga", "Outdated attempt"),
                )
                .await;
                return Err(falha(
                    "a resposta do Dropbox não confere com esta tentativa de conexão — tente de novo.",
                    "Dropbox's answer does not match this connection attempt — try again.",
                ));
            }

            let Some(codigo) = campo(&campos, "code") else {
                responder(
                    &mut fluxo,
                    400,
                    &pagina_de_erro("Faltou o código", "The code is missing"),
                )
                .await;
                return Err(falha(
                    "o Dropbox respondeu sem o código de autorização — tente de novo.",
                    "Dropbox answered without the authorization code — try again.",
                ));
            };

            responder(&mut fluxo, 200, &pagina_de_sucesso()).await;
            return Ok(codigo);
        }
    };

    let mut espera = Box::pin(espera);
    let prazo = tokio::time::sleep(PRAZO_DO_NAVEGADOR);
    tokio::pin!(prazo);
    loop {
        tokio::select! {
            resultado = &mut espera => return resultado,
            _ = &mut prazo => {
                return Err(falha(
                    "a autorização não terminou a tempo. Comece de novo e conclua no navegador.",
                    "the authorization did not finish in time. Start again and complete it in the browser.",
                ))
            }
            _ = tokio::time::sleep(Duration::from_millis(300)) => {
                if cancelada() {
                    return Err(falha(
                        "a autorização foi cancelada — nada foi alterado.",
                        "the authorization was cancelled — nothing was changed.",
                    ));
                }
            }
        }
    }
}

async fn receber(ouvintes: &[TcpListener]) -> AppResult<(tokio::net::TcpStream, std::net::SocketAddr)> {
    match ouvintes.len() {
        0 => Err(falha(
            "não há porta aberta para receber a autorização.",
            "there is no open port to receive the authorization.",
        )),
        1 => ouvintes[0].accept().await.map_err(|erro| {
            falha(
                &format!("falha ao esperar o retorno da autorização: {erro}"),
                &format!("failed while waiting for the authorization return: {erro}"),
            )
        }),
        _ => tokio::select! {
            aceito = ouvintes[0].accept() => aceito.map_err(|erro| {
                falha(
                    &format!("falha ao esperar o retorno da autorização: {erro}"),
                    &format!("failed while waiting for the authorization return: {erro}"),
                )
            }),
            aceito = ouvintes[1].accept() => aceito.map_err(|erro| {
                falha(
                    &format!("falha ao esperar o retorno da autorização: {erro}"),
                    &format!("failed while waiting for the authorization return: {erro}"),
                )
            }),
        },
    }
}

async fn trocar_codigo_por_token(
    codigo: &str,
    client_id: &str,
    client_secret: &str,
) -> AppResult<Value> {
    let resposta = reqwest::Client::new()
        .post(URL_TOKEN)
        .form(&[
            ("code", codigo),
            ("grant_type", "authorization_code"),
            ("client_id", client_id),
            ("client_secret", client_secret),
            ("redirect_uri", RETORNO),
        ])
        .timeout(Duration::from_secs(45))
        .send()
        .await
        .map_err(|erro| {
            falha(
                &format!(
                    "não foi possível falar com o Dropbox para concluir a autorização: {}",
                    motivo(&erro)
                ),
                &format!(
                    "could not reach Dropbox to finish the authorization: {}",
                    motivo(&erro)
                ),
            )
        })?;

    let situacao = resposta.status();
    let corpo: Value = resposta.json().await.map_err(|erro| {
        falha(
            &format!("o Dropbox respondeu algo inesperado: {}", motivo(&erro)),
            &format!("Dropbox answered something unexpected: {}", motivo(&erro)),
        )
    })?;

    if !situacao.is_success() {
        let erro = corpo
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("erro desconhecido");
        let descricao = corpo
            .get("error_description")
            .and_then(Value::as_str)
            .unwrap_or_default();
        return Err(falha(
            &format!("o Dropbox recusou a autorização: {erro} ({descricao})"),
            &format!("Dropbox refused the authorization: {erro} ({descricao})"),
        ));
    }

    let acesso = corpo
        .get("access_token")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            falha(
                "o Dropbox respondeu sem o token de acesso — tente de novo.",
                "Dropbox answered without the access token — try again.",
            )
        })?;
    let refresh = corpo
        .get("refresh_token")
        .and_then(Value::as_str)
        .unwrap_or_default();
    let segundos = corpo
        .get("expires_in")
        .and_then(Value::as_u64)
        .unwrap_or(14400);

    let mut token = json!({
        "access_token": acesso,
        "token_type": corpo
            .get("token_type")
            .and_then(Value::as_str)
            .unwrap_or("bearer"),
        "expiry": rfc3339(agora_em_segundos() + segundos),
    });
    if !refresh.is_empty() {
        token["refresh_token"] = Value::String(refresh.to_string());
    }
    Ok(token)
}

//! Autorização do OneDrive feita pelo próprio BrisaSync.
//!
//! O caminho antigo era o do rclone: ele abria o navegador, escutava o retorno e
//! terminava numa página dizendo “Success! All done. Please go back to rclone.”
//! — o nome de outro programa no meio da conexão do BrisaSync. Essa página é
//! HTML embutido no binário do rclone; não dá para trocar por configuração. A
//! saída é fazer o laço aqui, como já é feito com o Google: mesma página
//! (“BrisaSync · Conta conectada”), mesmo identificador sorteado a cada
//! tentativa, e o token pronto entregue ao rclone por `config/create`.
//!
//! O aplicativo é registrado no Microsoft Entra como **cliente público** (app
//! nativo): não existe `client_secret` — um segredo em binário distribuído não
//! seria segredo, e ainda expira em dois anos. O `client_id` abaixo é público
//! por natureza, como o do próprio rclone.
//!
//! Sem PKCE, de propósito: o rclone também não usa, e o código sai de um laço
//! que só escuta em `localhost` e vale por poucos minutos — é o mesmo desenho
//! que o Google recomenda para aplicativo instalado.

use crate::error::AppResult;
use serde_json::{json, Value};
use std::time::Duration;
use tokio::net::TcpListener;

use crate::login_google::{
    agora_em_segundos, campo, campos_da_consulta, cancelada, consulta_do_pedido, falha,
    ler_pedido, motivo, pagina_de_erro, pagina_de_sucesso, responder, rfc3339, sorteio,
};

/// Registro “BrisaSync” no Entra: cliente público. Não é segredo.
const CLIENTE: &str = "207c9f4b-9217-4761-a960-f36e8c5b0023";

/// A Microsoft casa o redirecionamento caractere por caractere: `localhost`
/// (não `127.0.0.1`) e com a barra no fim. Como a porta é fixa, não há plano B
/// para porta ocupada — quem estiver com ela presa recebe uma mensagem dizendo
/// o que fazer.
const PORTA: u16 = 53682;
const RETORNO: &str = "http://localhost:53682/";

const URL_AUTORIZACAO: &str = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize";
const URL_TOKEN: &str = "https://login.microsoftonline.com/common/oauth2/v2.0/token";

/// `Files.ReadWrite.All` é o que o rclone pede (ler e gravar os arquivos do
/// usuário); `User.Read` só serve para mostrar o e-mail da conta no cartão;
/// `offline_access` é o que garante o `refresh_token`.
const ESCOPOS: &str = "offline_access Files.ReadWrite.All User.Read";

const PRAZO_DO_NAVEGADOR: Duration = Duration::from_secs(600);

/// Autoriza uma conta Microsoft e devolve o token no formato que o
/// `rclone.conf` guarda (o mesmo JSON que o `rclone authorize` produziria).
pub async fn autorizar() -> AppResult<Value> {
    crate::login_google::limpar_cancelamento();
    let estado = sorteio(16)?;
    let ouvintes = abrir_porta().await?;
    let endereco = endereco_de_autorizacao(&estado);

    crate::commands::abrir_endereco(&endereco).map_err(|erro| {
        falha(
            &format!("não foi possível abrir o navegador para autorizar a conta: {erro}"),
            &format!("could not open the browser to authorize the account: {erro}"),
        )
    })?;

    let codigo = esperar_codigo(ouvintes, &estado).await?;
    trocar_codigo_por_token(&codigo).await
}

/// Monta o endereço de consentimento da Microsoft.
pub fn endereco_de_autorizacao(estado: &str) -> String {
    format!(
        "{URL_AUTORIZACAO}?client_id={}&response_type=code&redirect_uri={}\
         &response_mode=query&scope={}&state={}&prompt=consent",
        crate::login_google::codificar(CLIENTE),
        crate::login_google::codificar(RETORNO),
        crate::login_google::codificar(ESCOPOS),
        crate::login_google::codificar(estado),
    )
}

/// Escuta em `localhost` nas duas famílias: o navegador pode resolver o nome
/// para `127.0.0.1` ou para `::1`, e o retorno não pode se perder por isso.
async fn abrir_porta() -> AppResult<Vec<TcpListener>> {
    let mut ouvintes = Vec::new();
    let v4 = TcpListener::bind(("127.0.0.1", PORTA)).await;
    match v4 {
        Ok(ouvinte) => ouvintes.push(ouvinte),
        Err(erro) => {
            // `::1` pode ser a única família disponível; só desiste se a porta
            // estiver realmente presa.
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

/// Espera o navegador bater no laço com o código (ou com a recusa).
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
                            "A Microsoft recusou a autorização"
                        },
                        if recusou {
                            "Authorization cancelled"
                        } else {
                            "Microsoft refused the authorization"
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
                        &format!("a Microsoft recusou a autorização ({erro} {descricao})."),
                        &format!("Microsoft refused the authorization ({erro} {descricao})."),
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
                    "a resposta da Microsoft não confere com esta tentativa de conexão — tente de novo.",
                    "Microsoft's answer does not match this connection attempt — try again.",
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
                    "a Microsoft respondeu sem o código de autorização — tente de novo.",
                    "Microsoft answered without the authorization code — try again.",
                ));
            };

            responder(&mut fluxo, 200, &pagina_de_sucesso()).await;
            return Ok(codigo);
        }
    };

    // Mesmo desenho do Google: prazo e botão Cancelar param a espera aqui.
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

/// Aceita a conexão em qualquer um dos ouvintes (IPv4 e IPv6).
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

async fn trocar_codigo_por_token(codigo: &str) -> AppResult<Value> {
    trocar_codigo_em(URL_TOKEN, codigo).await
}

/// Troca o código pelo token, com o endereço do serviço explícito (os testes
/// usam uma Microsoft de mentira em `127.0.0.1`).
async fn trocar_codigo_em(endereco: &str, codigo: &str) -> AppResult<Value> {
    let resposta = reqwest::Client::new()
        .post(endereco)
        .form(&[
            ("client_id", CLIENTE),
            ("scope", ESCOPOS),
            ("code", codigo),
            ("redirect_uri", RETORNO),
            ("grant_type", "authorization_code"),
        ])
        .timeout(Duration::from_secs(45))
        .send()
        .await
        .map_err(|erro| {
            falha(
                &format!(
                    "não foi possível falar com a Microsoft para concluir a autorização: {}",
                    motivo(&erro)
                ),
                &format!(
                    "could not reach Microsoft to finish the authorization: {}",
                    motivo(&erro)
                ),
            )
        })?;

    let situacao = resposta.status();
    let corpo: Value = resposta.json().await.map_err(|erro| {
        falha(
            &format!("a Microsoft respondeu algo inesperado: {}", motivo(&erro)),
            &format!("Microsoft answered something unexpected: {}", motivo(&erro)),
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
            &format!("a Microsoft recusou a autorização: {erro} ({descricao})"),
            &format!("Microsoft refused the authorization: {erro} ({descricao})"),
        ));
    }

    let acesso = corpo
        .get("access_token")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            falha(
                "a Microsoft respondeu sem o token de acesso — tente de novo.",
                "Microsoft answered without the access token — try again.",
            )
        })?;
    let refresh = corpo
        .get("refresh_token")
        .and_then(Value::as_str)
        .ok_or_else(|| {
            falha(
                "a Microsoft não mandou o token de renovação, que é o que mantém a conta conectada depois de uma hora. Tente de novo e aceite a permissão de acesso contínuo.",
                "Microsoft did not send the refresh token, which is what keeps the account connected after an hour. Try again and accept the continuous access permission.",
            )
        })?;
    // Sem `expires_in` (improvável), assume a hora padrão da Microsoft.
    let segundos = corpo
        .get("expires_in")
        .and_then(Value::as_u64)
        .unwrap_or(3600);

    Ok(json!({
        "access_token": acesso,
        "token_type": corpo
            .get("token_type")
            .and_then(Value::as_str)
            .unwrap_or("Bearer"),
        "refresh_token": refresh,
        "expiry": rfc3339(agora_em_segundos() + segundos),
    }))
}

#[cfg(test)]
mod testes {
    #![allow(clippy::await_holding_lock)]

    use super::*;
    use std::sync::Mutex;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    static TRAVA: Mutex<()> = Mutex::new(());

    /// Microsoft de mentira: responde ao POST do token com o corpo combinado.
    async fn microsoft_de_mentira(codigo_http: u16, corpo: &'static str) -> String {
        let ouvinte = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let porta = ouvinte.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut fluxo, _) = ouvinte.accept().await.unwrap();
            let mut pedido = Vec::new();
            let mut pedaco = [0u8; 1024];
            loop {
                let lido = fluxo.read(&mut pedaco).await.unwrap();
                if lido == 0 {
                    break;
                }
                pedido.extend_from_slice(&pedaco[..lido]);
                if pedido.windows(4).any(|janela| janela == b"\r\n\r\n") {
                    break;
                }
            }
            let pedido = String::from_utf8_lossy(&pedido).to_string();
            assert!(pedido.starts_with("POST /token "), "{pedido}");
            assert!(pedido.contains("grant_type=authorization_code"), "{pedido}");
            assert!(pedido.contains(&format!("client_id={CLIENTE}")), "{pedido}");
            // O redirecionamento tem de ir igual ao registrado.
            assert!(
                pedido.contains("redirect_uri=http%3A%2F%2Flocalhost%3A53682%2F"),
                "{pedido}"
            );
            let resposta = format!(
                "HTTP/1.1 {codigo_http} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{corpo}",
                corpo.len()
            );
            fluxo.write_all(resposta.as_bytes()).await.unwrap();
            fluxo.flush().await.unwrap();
        });
        format!("http://127.0.0.1:{porta}/token")
    }

    #[test]
    fn endereco_pede_os_escopos_e_o_retorno_registrado() {
        let endereco = endereco_de_autorizacao("abc123");
        assert!(endereco.starts_with(URL_AUTORIZACAO), "{endereco}");
        assert!(endereco.contains(&format!("client_id={CLIENTE}")), "{endereco}");
        assert!(
            endereco.contains("redirect_uri=http%3A%2F%2Flocalhost%3A53682%2F"),
            "{endereco}"
        );
        assert!(endereco.contains("response_type=code"), "{endereco}");
        assert!(endereco.contains("response_mode=query"), "{endereco}");
        assert!(endereco.contains("state=abc123"), "{endereco}");
        // `prompt=consent` é o que garante o refresh token na resposta.
        assert!(endereco.contains("prompt=consent"), "{endereco}");
        for escopo in ["offline_access", "Files.ReadWrite.All", "User.Read"] {
            assert!(endereco.contains(escopo), "faltou {escopo}: {endereco}");
        }
    }

    #[tokio::test]
    async fn troca_do_codigo_vira_token_no_formato_do_rclone() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        let endereco = microsoft_de_mentira(
            200,
            r#"{"access_token":"EwB.teste","token_type":"Bearer","expires_in":3599,"refresh_token":"M.R3_BAY.teste","scope":"Files.ReadWrite.All User.Read"}"#,
        )
        .await;

        let token = trocar_codigo_em(&endereco, "M.R3_BAY.codigo").await.unwrap();
        assert_eq!(token["access_token"], "EwB.teste");
        assert_eq!(token["refresh_token"], "M.R3_BAY.teste");
        assert_eq!(token["token_type"], "Bearer");
        // O rclone espera RFC 3339 em `expiry`.
        let validade = token["expiry"].as_str().unwrap();
        assert_eq!(validade.len(), 20, "{validade}");
        assert!(validade.ends_with('Z'), "{validade}");
        assert!(validade.starts_with("20"), "{validade}");
    }

    #[tokio::test]
    async fn token_sem_renovacao_vira_erro_explicado() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");
        let endereco = microsoft_de_mentira(
            200,
            r#"{"access_token":"EwB.teste","token_type":"Bearer","expires_in":3599}"#,
        )
        .await;

        let erro = trocar_codigo_em(&endereco, "codigo")
            .await
            .unwrap_err()
            .to_string();
        assert!(erro.contains("token de renovação"), "{erro}");
        assert!(erro.contains("uma hora"), "{erro}");
    }

    #[tokio::test]
    async fn recusa_da_microsoft_mostra_o_codigo_e_a_descricao() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");
        let endereco = microsoft_de_mentira(
            400,
            r#"{"error":"invalid_grant","error_description":"AADSTS70008: The provided authorization code has expired."}"#,
        )
        .await;

        let erro = trocar_codigo_em(&endereco, "codigo")
            .await
            .unwrap_err()
            .to_string();
        assert!(erro.contains("invalid_grant"), "{erro}");
        assert!(erro.contains("expired"), "{erro}");
    }
}

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

/// Troca o `refresh_token` do Dropbox por um `access_token` novo.
pub async fn renovar_token(
    token: &Value,
    client_id: Option<&str>,
    client_secret: Option<&str>,
) -> Option<String> {
    let refresh = token.get("refresh_token").and_then(Value::as_str)?;
    let (build_id, build_secret) = credenciais_do_build().unwrap_or_default();
    let id = client_id.filter(|s| !s.is_empty()).unwrap_or(&build_id);
    if id.is_empty() {
        return None;
    }
    let secret = client_secret
        .filter(|s| !s.is_empty())
        .unwrap_or(&build_secret);
    let mut form = vec![
        ("grant_type", "refresh_token"),
        ("refresh_token", refresh),
        ("client_id", id),
    ];
    if !secret.is_empty() {
        form.push(("client_secret", secret));
    }
    let resposta = reqwest::Client::new()
        .post(URL_TOKEN)
        .form(&form)
        .timeout(Duration::from_secs(30))
        .send()
        .await
        .ok()?;
    let corpo: Value = resposta.json().await.ok()?;
    corpo
        .get("access_token")
        .and_then(Value::as_str)
        .map(str::to_string)
}

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
    let verificador = sorteio(32)?;
    let desafio = desafio_pkce(&verificador);
    let ouvintes = abrir_porta().await?;
    let endereco = endereco_de_autorizacao(client_id, &estado, &desafio);

    crate::commands::abrir_endereco(&endereco).map_err(|erro| {
        falha(
            &format!("não foi possível abrir o navegador para autorizar a conta: {erro}"),
            &format!("could not open the browser to authorize the account: {erro}"),
        )
    })?;

    let codigo = esperar_codigo(ouvintes, &estado).await?;
    trocar_codigo_por_token(&codigo, client_id, client_secret, &verificador).await
}

/// Monta o endereço de consentimento do Dropbox (`token_access_type=offline` garante `refresh_token`,
/// e PKCE `S256` protege o código de autorização no retorno local).
pub fn endereco_de_autorizacao(client_id: &str, estado: &str, desafio: &str) -> String {
    format!(
        "{URL_AUTORIZACAO}?client_id={}&response_type=code&redirect_uri={}&token_access_type=offline&state={}&code_challenge={}&code_challenge_method=S256",
        codificar(client_id),
        codificar(RETORNO),
        codificar(estado),
        codificar(desafio),
    )
}

/// Calcula `BASE64URL_NO_PAD(SHA256(verificador))` conforme RFC 7636 (PKCE S256).
pub fn desafio_pkce(verificador: &str) -> String {
    let resumo = sha256(verificador.as_bytes());
    base64url_sem_padding(&resumo)
}

fn sha256(dados: &[u8]) -> [u8; 32] {
    const K: [u32; 64] = [
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
        0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
        0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
        0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
        0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
        0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
        0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
    ];
    let mut h: [u32; 8] = [
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
    ];

    let bit_len = (dados.len() as u64) * 8;
    let mut msg = dados.to_vec();
    msg.push(0x80);
    while (msg.len() % 64) != 56 {
        msg.push(0);
    }
    msg.extend_from_slice(&bit_len.to_be_bytes());

    for bloco in msg.chunks_exact(64) {
        let mut w = [0u32; 64];
        for (i, chunk) in bloco.chunks_exact(4).enumerate() {
            w[i] = u32::from_be_bytes([chunk[0], chunk[1], chunk[2], chunk[3]]);
        }
        for i in 16..64 {
            let s0 = w[i - 15].rotate_right(7) ^ w[i - 15].rotate_right(18) ^ (w[i - 15] >> 3);
            let s1 = w[i - 2].rotate_right(17) ^ w[i - 2].rotate_right(19) ^ (w[i - 2] >> 10);
            w[i] = w[i - 16]
                .wrapping_add(s0)
                .wrapping_add(w[i - 7])
                .wrapping_add(s1);
        }

        let [mut a, mut b, mut c, mut d, mut e, mut f, mut g, mut hh] = h;
        for i in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let ch = (e & f) ^ ((!e) & g);
            let temp1 = hh
                .wrapping_add(s1)
                .wrapping_add(ch)
                .wrapping_add(K[i])
                .wrapping_add(w[i]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let maj = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(maj);

            hh = g;
            g = f;
            f = e;
            e = d.wrapping_add(temp1);
            d = c;
            c = b;
            b = a;
            a = temp1.wrapping_add(temp2);
        }

        h[0] = h[0].wrapping_add(a);
        h[1] = h[1].wrapping_add(b);
        h[2] = h[2].wrapping_add(c);
        h[3] = h[3].wrapping_add(d);
        h[4] = h[4].wrapping_add(e);
        h[5] = h[5].wrapping_add(f);
        h[6] = h[6].wrapping_add(g);
        h[7] = h[7].wrapping_add(hh);
    }

    let mut saida = [0u8; 32];
    for (i, palavra) in h.iter().enumerate() {
        saida[i * 4..(i + 1) * 4].copy_from_slice(&palavra.to_be_bytes());
    }
    saida
}

fn base64url_sem_padding(bytes: &[u8]) -> String {
    const ALFABETO: &[u8; 64] =
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut saida = String::with_capacity((bytes.len() * 4).div_ceil(3));
    for bloco in bytes.chunks(3) {
        let b0 = bloco[0] as u32;
        let b1 = if bloco.len() > 1 { bloco[1] as u32 } else { 0 };
        let b2 = if bloco.len() > 2 { bloco[2] as u32 } else { 0 };
        let n = (b0 << 16) | (b1 << 8) | b2;
        saida.push(ALFABETO[((n >> 18) & 0x3f) as usize] as char);
        saida.push(ALFABETO[((n >> 12) & 0x3f) as usize] as char);
        if bloco.len() > 1 {
            saida.push(ALFABETO[((n >> 6) & 0x3f) as usize] as char);
        }
        if bloco.len() > 2 {
            saida.push(ALFABETO[(n & 0x3f) as usize] as char);
        }
    }
    saida
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
    verificador: &str,
) -> AppResult<Value> {
    trocar_codigo_em(URL_TOKEN, codigo, client_id, client_secret, verificador).await
}

async fn trocar_codigo_em(
    url_token: &str,
    codigo: &str,
    client_id: &str,
    client_secret: &str,
    verificador: &str,
) -> AppResult<Value> {
    let resposta = reqwest::Client::new()
        .post(url_token)
        .form(&[
            ("code", codigo),
            ("grant_type", "authorization_code"),
            ("client_id", client_id),
            ("client_secret", client_secret),
            ("redirect_uri", RETORNO),
            ("code_verifier", verificador),
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

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    static TRAVA: Mutex<()> = Mutex::new(());

    async fn dropbox_de_mentira(codigo_http: u16, corpo: &'static str) -> String {
        let ouvinte = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let porta = ouvinte.local_addr().unwrap().port();
        tokio::spawn(async move {
            let (mut fluxo, _) = ouvinte.accept().await.unwrap();
            let mut pedido = Vec::new();
            let mut pedaco = [0u8; 1024];
            let mut tamanho_corpo = None;
            let mut fim_cabecalho = None;
            loop {
                let lido = fluxo.read(&mut pedaco).await.unwrap();
                if lido == 0 {
                    break;
                }
                pedido.extend_from_slice(&pedaco[..lido]);
                if fim_cabecalho.is_none() {
                    if let Some(pos) = pedido.windows(4).position(|j| j == b"\r\n\r\n") {
                        fim_cabecalho = Some(pos + 4);
                        let cab = String::from_utf8_lossy(&pedido[..pos]);
                        for linha in cab.lines() {
                            if let Some((k, v)) = linha.split_once(':') {
                                if k.eq_ignore_ascii_case("content-length") {
                                    tamanho_corpo = v.trim().parse::<usize>().ok();
                                }
                            }
                        }
                    }
                }
                if let Some(inicio) = fim_cabecalho {
                    let esperado = tamanho_corpo.unwrap_or(0);
                    if pedido.len() >= inicio + esperado {
                        break;
                    }
                }
            }
            let pedido = String::from_utf8_lossy(&pedido).to_string();
            assert!(pedido.starts_with("POST /oauth2/token "), "{pedido}");
            assert!(pedido.contains("grant_type=authorization_code"), "{pedido}");
            assert!(pedido.contains("client_id=app_teste"), "{pedido}");
            assert!(pedido.contains("client_secret=segredo_teste"), "{pedido}");
            assert!(
                pedido.contains("redirect_uri=http%3A%2F%2Flocalhost%3A53682%2F"),
                "{pedido}"
            );
            assert!(pedido.contains("code_verifier=verificador_teste"), "{pedido}");
            let resposta = format!(
                "HTTP/1.1 {codigo_http} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{corpo}",
                corpo.len()
            );
            fluxo.write_all(resposta.as_bytes()).await.unwrap();
            fluxo.flush().await.unwrap();
        });
        format!("http://127.0.0.1:{porta}/oauth2/token")
    }

    #[test]
    fn pkce_s256_bate_com_vetor_rfc7636() {
        // Vetor oficial do Apêndice B da RFC 7636.
        let verificador = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk";
        assert_eq!(
            desafio_pkce(verificador),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
    }

    #[test]
    fn endereco_inclui_redirect_uri_e_pkce() {
        let desafio = desafio_pkce("verificador_teste");
        let endereco = endereco_de_autorizacao("6vxxvzvuep5o8p4", "estado123", &desafio);
        assert!(endereco.starts_with(URL_AUTORIZACAO), "{endereco}");
        assert!(endereco.contains("client_id=6vxxvzvuep5o8p4"), "{endereco}");
        assert!(
            endereco.contains("redirect_uri=http%3A%2F%2Flocalhost%3A53682%2F"),
            "{endereco}"
        );
        assert!(endereco.contains("response_type=code"), "{endereco}");
        assert!(endereco.contains("token_access_type=offline"), "{endereco}");
        assert!(endereco.contains("state=estado123"), "{endereco}");
        assert!(endereco.contains("code_challenge_method=S256"), "{endereco}");
        assert!(
            endereco.contains(&format!("code_challenge={}", codificar(&desafio))),
            "{endereco}"
        );
    }

    #[tokio::test]
    async fn troca_do_codigo_envia_redirect_uri_e_pkce_e_gera_token_rclone() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        let endereco = dropbox_de_mentira(
            200,
            r#"{"access_token":"sl.teste","token_type":"bearer","expires_in":14400,"refresh_token":"rt.teste"}"#,
        )
        .await;

        let token = trocar_codigo_em(
            &endereco,
            "codigo_teste",
            "app_teste",
            "segredo_teste",
            "verificador_teste",
        )
        .await
        .unwrap();

        assert_eq!(token["access_token"], "sl.teste");
        assert_eq!(token["refresh_token"], "rt.teste");
        assert_eq!(token["token_type"], "bearer");
        let validade = token["expiry"].as_str().unwrap();
        assert_eq!(validade.len(), 20, "{validade}");
        assert!(validade.ends_with('Z'), "{validade}");
    }

    #[tokio::test]
    async fn troca_do_codigo_recusada_nao_vaza_segredo() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        let endereco = dropbox_de_mentira(
            400,
            r#"{"error":"invalid_grant","error_description":"code has expired"}"#,
        )
        .await;

        let erro = trocar_codigo_em(
            &endereco,
            "codigo_teste",
            "app_teste",
            "segredo_teste",
            "verificador_teste",
        )
        .await
        .unwrap_err();

        let msg = erro.to_string();
        assert!(msg.contains("invalid_grant"), "{msg}");
        assert!(!msg.contains("segredo_teste"), "{msg}");
    }
}

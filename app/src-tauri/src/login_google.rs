//! Autorização do Google feita pelo próprio BrisaSync.
//!
//! Antes, quem abria o navegador e recebia o retorno era o `rclone authorize`:
//! o laço em `127.0.0.1:53682` é dele, e a última página dizia
//! “All done. Please go back to rclone.” — o nome de outro programa no meio da
//! autorização do BrisaSync.
//!
//! Aqui o laço é nosso: o app abre o navegador com `state` sorteado, escuta o
//! retorno em `127.0.0.1`, mostra uma página com a cara do BrisaSync e troca o
//! código pelo token. Com o token na mão, o remote é criado no rclone por
//! `config/create` (`nonInteractive`), sem passar pelo fluxo interativo dele.
//!
//! O laço em `127.0.0.1` é o recomendado pelo Google para aplicativo instalado
//! (a porta pode variar). O `client_secret` de app instalado não é segredo: o
//! próprio rclone publica o dele.

use crate::error::{AppError, AppResult};
use serde_json::{json, Value};
use std::sync::atomic::{AtomicBool, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpListener;

/// Escopo pedido: o mesmo `drive` que o rclone usa por padrão.
const ESCOPO: &str = "https://www.googleapis.com/auth/drive";

/// Porta que o Google já conhece do rclone. Se estiver ocupada (outra
/// autorização em andamento), o laço cai numa porta livre qualquer — para
/// aplicativo instalado o Google aceita qualquer porta em `127.0.0.1`.
const PORTA_PREFERIDA: u16 = 53682;

/// Quanto tempo esperamos a pessoa terminar no navegador.
pub const PRAZO_DO_NAVEGADOR: Duration = Duration::from_secs(600);

/// Pedido de cancelamento da janela “aguardando autorização”.
///
/// Só existe uma autorização por vez (a segunda conexão espera a trava do
/// `connect_account`), então um sinal global basta: o laço local desiste na
/// hora em vez de deixar a pessoa esperando até o prazo acabar.
static CANCELAR: AtomicBool = AtomicBool::new(false);

pub fn cancelar() {
    CANCELAR.store(true, Ordering::SeqCst);
}

pub(crate) fn limpar_cancelamento() {
    CANCELAR.store(false, Ordering::SeqCst);
}

/// O laço da autorização da Microsoft usa o mesmo sinal de cancelamento.
pub(crate) fn cancelada() -> bool {
    CANCELAR.load(Ordering::SeqCst)
}

const URL_AUTORIZACAO: &str = "https://accounts.google.com/o/oauth2/auth";
const URL_TOKEN: &str = "https://oauth2.googleapis.com/token";

/// O `about` do rclone devolve só total/usado/livre da cota. O e-mail da conta
/// está no mesmo endpoint da API do Drive, que já está coberto pelo escopo
/// `drive` que o app pede — daí dá para dizer *qual* conta está conectada.
const URL_CONTA: &str = "https://www.googleapis.com/drive/v3/about";

/// Erro que segue o idioma do app: estas mensagens aparecem na janela de
/// conectar conta, então precisam falar a mesma língua da interface.
pub(crate) fn falha(portugues: &str, ingles: &str) -> AppError {
    AppError::new(crate::idioma::escolhe(
        portugues.to_string(),
        ingles.to_string(),
    ))
}

/// O `reqwest` esconde o motivo real (DNS, TLS, rede) na cadeia de `source`.
/// Sem ela, uma falha de transporte vira só "error sending request for url".
pub(crate) fn motivo(erro: &reqwest::Error) -> String {
    let mut texto = erro.to_string();
    let mut fonte = std::error::Error::source(erro);
    while let Some(causa) = fonte {
        let causa_texto = causa.to_string();
        if !texto.contains(&causa_texto) {
            texto.push_str(" · ");
            texto.push_str(&causa_texto);
        }
        fonte = causa.source();
    }
    texto
}

/// Autoriza uma conta Google e devolve o token no formato que o `rclone.conf`
/// guarda (o mesmo JSON que o `rclone authorize` produziria).
pub async fn autorizar(client_id: &str, client_secret: &str) -> AppResult<Value> {
    CANCELAR.store(false, Ordering::SeqCst);
    let estado = sorteio(16)?;
    let (ouvinte, porta) = abrir_porta().await?;
    let retorno = format!("http://127.0.0.1:{porta}/");
    let endereco = endereco_de_autorizacao(client_id, &retorno, &estado);

    // O navegador é aberto pelo app: é ele que recebe o retorno.
    crate::commands::abrir_endereco(&endereco).map_err(|erro| {
        falha(
            &format!("não foi possível abrir o navegador para autorizar a conta: {erro}"),
            &format!("could not open the browser to authorize the account: {erro}"),
        )
    })?;

    let codigo = esperar_codigo(ouvinte, &estado).await?;
    trocar_codigo_por_token(&codigo, client_id, client_secret, &retorno).await
}

/// Monta o endereço de consentimento do Google.
pub fn endereco_de_autorizacao(client_id: &str, retorno: &str, estado: &str) -> String {
    format!(
        "{URL_AUTORIZACAO}?client_id={}&redirect_uri={}&response_type=code&scope={}\
         &access_type=offline&prompt=consent&include_granted_scopes=true&state={}",
        codificar(client_id),
        codificar(retorno),
        codificar(ESCOPO),
        codificar(estado),
    )
}

/// Escuta no laço local. A porta preferida é a do rclone; se estiver ocupada,
/// qualquer porta livre serve.
async fn abrir_porta() -> AppResult<(TcpListener, u16)> {
    match TcpListener::bind(("127.0.0.1", PORTA_PREFERIDA)).await {
        Ok(ouvinte) => Ok((ouvinte, PORTA_PREFERIDA)),
        Err(_) => {
            let ouvinte = TcpListener::bind(("127.0.0.1", 0)).await.map_err(|erro| {
                falha(
                    &format!("não foi possível abrir o retorno da autorização em 127.0.0.1: {erro}"),
                    &format!("could not open the authorization return server on 127.0.0.1: {erro}"),
                )
            })?;
            let porta = ouvinte
                .local_addr()
                .map(|endereco| endereco.port())
                .unwrap_or(0);
            Ok((ouvinte, porta))
        }
    }
}

/// Espera o navegador bater no laço com o código (ou com a recusa).
async fn esperar_codigo(ouvinte: TcpListener, estado: &str) -> AppResult<String> {
    let espera = async {
        loop {
            let (mut fluxo, _) = ouvinte.accept().await.map_err(|erro| {
                falha(
                    &format!("falha ao esperar o retorno da autorização: {erro}"),
                    &format!("failed while waiting for the authorization return: {erro}"),
                )
            })?;

            let pedido = ler_pedido(&mut fluxo).await;
            let Some(consulta) = pedido
                .as_deref()
                .and_then(consulta_do_pedido)
                .map(|consulta| consulta.to_string())
            else {
                // favicon.ico e outros pedidos do navegador não interessam.
                responder(&mut fluxo, 404, &pagina_de_erro("Nada aqui.", "Nothing here.")).await;
                continue;
            };

            let campos = campos_da_consulta(&consulta);

            if let Some(erro) = campo(&campos, "error") {
                let recusou = erro == "access_denied";
                responder(
                    &mut fluxo,
                    200,
                    &pagina_de_erro(
                        if recusou {
                            "Autorização cancelada"
                        } else {
                            "O Google recusou a autorização"
                        },
                        if recusou {
                            "Authorization cancelled"
                        } else {
                            "Google refused the authorization"
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
                        &format!("o Google recusou a autorização ({erro})."),
                        &format!("Google refused the authorization ({erro})."),
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
                    "a resposta do Google não confere com esta tentativa de conexão — tente de novo.",
                    "Google's answer does not match this connection attempt — try again.",
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
                    "o Google respondeu sem o código de autorização — tente de novo.",
                    "Google answered without the authorization code — try again.",
                ));
            };

            responder(&mut fluxo, 200, &pagina_de_sucesso()).await;
            return Ok(codigo);
        }
    };

    // O prazo e o botão Cancelar param a espera pelo mesmo lugar: aqui. Sem
    // isso, quem fechava o navegador ficava com a janela presa até o fim dos
    // dez minutos.
    let mut espera = Box::pin(espera);
    let prazo = tokio::time::sleep(PRAZO_DO_NAVEGADOR);
    tokio::pin!(prazo);
    loop {
        tokio::select! {
            resultado = &mut espera => return resultado,
            _ = &mut prazo => {
                return Err(falha(
                    "a autorização não terminou a tempo. Comece de novo e conclua no navegador. Se a página do Google mostrou \"acesso bloqueado\", o projeto do app atingiu o limite de usuários: use um projeto OAuth seu em Ajustes → Avançado.",
                    "the authorization did not finish in time. Start again and complete it in the browser. If the Google page said \"access blocked\", the app's project reached its user limit: use your own OAuth project in Settings → Advanced.",
                ))
            }
            _ = tokio::time::sleep(Duration::from_millis(300)) => {
                if CANCELAR.load(Ordering::SeqCst) {
                    return Err(falha(
                        "a autorização foi cancelada — nada foi alterado.",
                        "the authorization was cancelled — nothing was changed.",
                    ));
                }
            }
        }
    }
}

/// Troca o código pelo token e devolve o JSON que o rclone guarda.
async fn trocar_codigo_por_token(
    codigo: &str,
    client_id: &str,
    client_secret: &str,
    retorno: &str,
) -> AppResult<Value> {
    trocar_codigo_em(URL_TOKEN, codigo, client_id, client_secret, retorno).await
}

/// Mesma troca, com o endereço do serviço de token explícito (os testes usam um
/// Google de mentira em `127.0.0.1`).
async fn trocar_codigo_em(
    endereco: &str,
    codigo: &str,
    client_id: &str,
    client_secret: &str,
    retorno: &str,
) -> AppResult<Value> {
    let resposta = reqwest::Client::new()
        .post(endereco)
        .form(&[
            ("code", codigo),
            ("client_id", client_id),
            ("client_secret", client_secret),
            ("redirect_uri", retorno),
            ("grant_type", "authorization_code"),
        ])
        .timeout(Duration::from_secs(45))
        .send()
        .await
        .map_err(|erro| {
            falha(
                &format!(
                    "não foi possível falar com o Google para concluir a autorização: {}",
                    motivo(&erro)
                ),
                &format!(
                    "could not reach Google to finish the authorization: {}",
                    motivo(&erro)
                ),
            )
        })?;

    let situacao = resposta.status();
    let corpo: Value = resposta.json().await.map_err(|erro| {
        falha(
            &format!("o Google respondeu algo inesperado: {}", motivo(&erro)),
            &format!("Google answered something unexpected: {}", motivo(&erro)),
        )
    })?;

    if !situacao.is_success() || corpo.get("access_token").is_none() {
        let erro = corpo
            .get("error")
            .and_then(Value::as_str)
            .unwrap_or("erro desconhecido");
        let detalhe = corpo
            .get("error_description")
            .and_then(Value::as_str)
            .unwrap_or_default();
        let (explicacao, explanation) = match erro {
            "invalid_client" | "unauthorized_client" => (
                "o Google não aceitou as credenciais do projeto OAuth — confira o client_id e o client_secret em Ajustes → Avançado.",
                "Google did not accept the OAuth project credentials — check client_id and client_secret in Settings → Advanced.",
            ),
            "invalid_grant" => (
                "o Google não aceitou o código devolvido (ele vale uma vez só e por poucos minutos) — tente de novo.",
                "Google did not accept the returned code (it is single use and short lived) — try again.",
            ),
            "redirect_uri_mismatch" => (
                "o endereço de retorno não foi aceito pelo projeto OAuth — ele precisa ser do tipo “App para computador”.",
                "the return address was not accepted by the OAuth project — it must be a “Desktop app” client.",
            ),
            _ => (
                "não foi possível concluir a autorização com o Google.",
                "could not finish the authorization with Google.",
            ),
        };
        let detalhe = if detalhe.is_empty() {
            erro.to_string()
        } else {
            format!("{erro}: {detalhe}")
        };
        return Err(falha(
            &format!("{explicacao} ({detalhe})"),
            &format!("{explanation} ({detalhe})"),
        ));
    }

    let access_token = corpo
        .get("access_token")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    let token_type = corpo
        .get("token_type")
        .and_then(Value::as_str)
        .unwrap_or("Bearer")
        .to_string();
    let refresh_token = corpo.get("refresh_token").and_then(Value::as_str);
    let Some(refresh_token) = refresh_token else {
        // Sem refresh token a conta para de sincronizar em uma hora. Só acontece
        // se o Google já tinha dado o acesso a este app (ou se o pedido não pediu
        // acesso offline), e a saída é revogar o acesso e tentar de novo.
        return Err(falha(
            "o Google devolveu um acesso válido por uma hora só. Remova o acesso do BrisaSync em myaccount.google.com/permissions e conecte a conta de novo.",
            "Google returned an access valid for one hour only. Remove BrisaSync's access at myaccount.google.com/permissions and connect the account again.",
        ));
    };

    let expira_em = corpo
        .get("expires_in")
        .and_then(Value::as_u64)
        .unwrap_or(3600);
    let validade = agora_em_segundos().saturating_add(expira_em);

    Ok(json!({
        "access_token": access_token,
        "token_type": token_type,
        "refresh_token": refresh_token,
        "expiry": rfc3339(validade),
    }))
}

/// Lê o pedido HTTP até a linha em branco (o bastante para a primeira linha).
pub(crate) async fn ler_pedido(fluxo: &mut tokio::net::TcpStream) -> Option<String> {
    let mut buffer = Vec::with_capacity(1024);
    let mut pedaco = [0u8; 1024];
    loop {
        let lido = fluxo.read(&mut pedaco).await.ok()?;
        if lido == 0 {
            break;
        }
        buffer.extend_from_slice(&pedaco[..lido]);
        if buffer.windows(4).any(|janela| janela == b"\r\n\r\n") || buffer.len() > 8192 {
            break;
        }
    }
    Some(String::from_utf8_lossy(&buffer).to_string())
}

/// Devolve a consulta (`?code=…&state=…`) da primeira linha do pedido.
pub(crate) fn consulta_do_pedido(pedido: &str) -> Option<&str> {
    let primeira = pedido.lines().next()?;
    let mut partes = primeira.split_whitespace();
    let metodo = partes.next()?;
    if metodo != "GET" {
        return None;
    }
    let alvo = partes.next()?;
    alvo.split_once('?').map(|(_, consulta)| consulta)
}

/// Separa `a=1&b=2` em pares já decodificados.
pub(crate) fn campos_da_consulta(consulta: &str) -> Vec<(String, String)> {
    consulta
        .split('&')
        .filter(|par| !par.is_empty())
        .map(|par| match par.split_once('=') {
            Some((nome, valor)) => (decodificar(nome), decodificar(valor)),
            None => (decodificar(par), String::new()),
        })
        .collect()
}

pub(crate) fn campo(campos: &[(String, String)], nome: &str) -> Option<String> {
    campos
        .iter()
        .find(|(chave, _)| chave == nome)
        .map(|(_, valor)| valor.clone())
        .filter(|valor| !valor.is_empty())
}

pub(crate) async fn responder(fluxo: &mut tokio::net::TcpStream, codigo: u16, corpo: &str) {
    let motivo = match codigo {
        200 => "OK",
        400 => "Bad Request",
        _ => "Not Found",
    };
    let resposta = format!(
        "HTTP/1.1 {codigo} {motivo}\r\nContent-Type: text/html; charset=utf-8\r\n\
         Content-Length: {}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n{corpo}",
        corpo.len()
    );
    let _ = fluxo.write_all(resposta.as_bytes()).await;
    let _ = fluxo.flush().await;
}

/// Página final: é a última coisa que a pessoa vê da autorização, então fala do
/// BrisaSync — não do motor que faz a sincronização por baixo.
pub fn pagina_de_sucesso() -> String {
    let titulo = crate::idioma::texto("Conta conectada", "Account connected");
    let texto = crate::idioma::texto(
        "Pode fechar esta aba e voltar ao BrisaSync.",
        "You can close this tab and go back to BrisaSync.",
    );
    pagina(titulo, texto, "#1f9d55")
}

pub(crate) fn pagina_de_erro(titulo_pt: &str, titulo_en: &str) -> String {
    let titulo = crate::idioma::escolhe(titulo_pt.to_string(), titulo_en.to_string());
    let texto = crate::idioma::texto(
        "Volte ao BrisaSync e tente de novo.",
        "Go back to BrisaSync and try again.",
    );
    pagina(&titulo, texto, "#c2410c")
}

/// Página única, sem nada externo: funciona offline, no escuro e no claro.
fn pagina(titulo: &str, texto: &str, cor: &str) -> String {
    let marca = crate::idioma::texto("BrisaSync", "BrisaSync");
    format!(
        r#"<!doctype html>
<html lang="{idioma}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{titulo} · {marca}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #f4f5f7; color: #14181f; padding: 24px;
    font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  }}
  .cartao {{
    width: 100%; max-width: 420px; background: #fff; border-radius: 18px;
    padding: 32px 28px; text-align: center;
    box-shadow: 0 18px 40px rgba(15, 23, 42, .12), 0 1px 2px rgba(15, 23, 42, .08);
  }}
  .marca {{ font-size: 12px; letter-spacing: .12em; text-transform: uppercase; color: #6b7280; }}
  .selo {{
    width: 56px; height: 56px; margin: 18px auto 14px; border-radius: 50%;
    display: grid; place-items: center; background: {cor}1a; color: {cor};
  }}
  h1 {{ font-size: 20px; margin: 0 0 8px; }}
  p {{ margin: 0; color: #4b5563; line-height: 1.55; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0f1218; color: #eef1f6; }}
    .cartao {{ background: #171c24; box-shadow: none; border: 1px solid #262d38; }}
    p {{ color: #a8b1bf; }}
    .marca {{ color: #8c96a6; }}
  }}
</style>
</head>
<body>
  <div class="cartao">
    <div class="marca">{marca}</div>
    <div class="selo">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor"
           stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
        <path d="M20 6 9 17l-5-5"/>
      </svg>
    </div>
    <h1>{titulo}</h1>
    <p>{texto}</p>
  </div>
</body>
</html>
"#,
        idioma = if crate::idioma::ingles() { "en" } else { "pt-BR" },
        titulo = escapar(titulo),
        marca = escapar(marca),
        texto = escapar(texto),
        cor = cor,
    )
}

/// Sorteio hexadecimal do `state` (evita CSRF na resposta do laço).
pub(crate) fn sorteio(bytes: usize) -> AppResult<String> {
    let mut valores = vec![0u8; bytes];
    getrandom::fill(&mut valores).map_err(|erro| {
        falha(
            &format!("não foi possível sortear o identificador da autorização: {erro}"),
            &format!("could not draw the authorization identifier: {erro}"),
        )
    })?;
    Ok(valores.iter().map(|byte| format!("{byte:02x}")).collect())
}

/// `%XX` e `+` de volta ao texto original.
pub fn decodificar(texto: &str) -> String {
    let bytes = texto.as_bytes();
    let mut saida = Vec::with_capacity(bytes.len());
    let mut indice = 0;
    while indice < bytes.len() {
        match bytes[indice] {
            b'+' => {
                saida.push(b' ');
                indice += 1;
            }
            b'%' if indice + 2 < bytes.len() => {
                let hex = std::str::from_utf8(&bytes[indice + 1..indice + 3]).ok();
                match hex.and_then(|hex| u8::from_str_radix(hex, 16).ok()) {
                    Some(byte) => {
                        saida.push(byte);
                        indice += 3;
                    }
                    None => {
                        saida.push(bytes[indice]);
                        indice += 1;
                    }
                }
            }
            byte => {
                saida.push(byte);
                indice += 1;
            }
        }
    }
    String::from_utf8_lossy(&saida).to_string()
}

/// Percent-encoding de tudo que não é seguro em consulta de URL.
pub fn codificar(texto: &str) -> String {
    let mut saida = String::with_capacity(texto.len());
    for byte in texto.bytes() {
        match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                saida.push(byte as char)
            }
            outro => saida.push_str(&format!("%{outro:02X}")),
        }
    }
    saida
}

pub(crate) fn agora_em_segundos() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duracao| duracao.as_secs())
        .unwrap_or(0)
}

fn escapar(texto: &str) -> String {
    texto
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// `expiry` do rclone é RFC 3339 em UTC: `2026-11-08T20:00:00Z`.
pub fn rfc3339(segundos: u64) -> String {
    let dias = (segundos / 86_400) as i64;
    let resto = segundos % 86_400;
    let (ano, mes, dia) = data_civil(dias);
    format!(
        "{ano:04}-{mes:02}-{dia:02}T{:02}:{:02}:{:02}Z",
        resto / 3_600,
        (resto % 3_600) / 60,
        resto % 60
    )
}

/// Dias desde 1970 → (ano, mês, dia), no calendário gregoriano proléptico
/// (algoritmo `civil_from_days` de Howard Hinnant).
fn data_civil(dias: i64) -> (i64, u32, u32) {
    let z = dias + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let dia_da_era = (z - era * 146_097) as u64; // [0, 146096]
    let ano_da_era =
        (dia_da_era - dia_da_era / 1_460 + dia_da_era / 36_524 - dia_da_era / 146_096) / 365;
    let ano = ano_da_era as i64 + era * 400;
    let dia_do_ano = dia_da_era - (365 * ano_da_era + ano_da_era / 4 - ano_da_era / 100);
    let mes_ajustado = (5 * dia_do_ano + 2) / 153; // [0, 11], março = 0
    let dia = (dia_do_ano - (153 * mes_ajustado + 2) / 5 + 1) as u32;
    let mes = if mes_ajustado < 10 {
        mes_ajustado + 3
    } else {
        mes_ajustado - 9
    } as u32;
    (if mes <= 2 { ano + 1 } else { ano }, mes, dia)
}

/// E-mail da conta dona de um token guardado pelo rclone.
///
/// `None` quando não dá para saber (conta sem `access_token`, sem rede, token
/// recusado): a janela simplesmente não mostra o e-mail, sem virar erro na cara
/// de quem só queria ver a cota.
pub async fn email_da_conta(
    token: &Value,
    client_id: &str,
    client_secret: &str,
) -> Option<String> {
    let acesso = token.get("access_token").and_then(Value::as_str)?;
    match email_em(URL_CONTA, acesso).await {
        Ok(Some(email)) => Some(email),
        // Respondeu, mas sem `user`: nada a mostrar e nada a renovar.
        Ok(None) => None,
        // O caso comum de falha aqui é token vencido (o rclone só renova quando
        // usa a conta). Uma renovação pelo `refresh_token` resolve.
        Err(_) => {
            let novo = renovar_token(token, client_id, client_secret).await?;
            email_em(URL_CONTA, &novo).await.ok().flatten()
        }
    }
}

/// Busca o e-mail com um `access_token` já pronto (os testes usam um Google de
/// mentira em `127.0.0.1`).
async fn email_em(endereco: &str, acesso: &str) -> AppResult<Option<String>> {
    let resposta = reqwest::Client::new()
        .get(endereco)
        .query(&[("fields", "user(emailAddress)")])
        .bearer_auth(acesso)
        .timeout(Duration::from_secs(20))
        .send()
        .await
        .map_err(|erro| {
            falha(
                &format!("não foi possível perguntar ao Google qual é a conta: {}", motivo(&erro)),
                &format!("could not ask Google which account this is: {}", motivo(&erro)),
            )
        })?;

    let situacao = resposta.status();
    if !situacao.is_success() {
        return Err(AppError::new(format!(
            "o Google respondeu {} ao perguntar pela conta",
            situacao.as_u16()
        )));
    }

    let corpo: Value = resposta.json().await.map_err(|erro| {
        falha(
            &format!("o Google respondeu algo inesperado: {}", motivo(&erro)),
            &format!("Google answered something unexpected: {}", motivo(&erro)),
        )
    })?;
    Ok(email_da_resposta(&corpo))
}

/// Troca o `refresh_token` por um `access_token` novo.
async fn renovar_token(
    token: &Value,
    client_id: &str,
    client_secret: &str,
) -> Option<String> {
    let refresh = token.get("refresh_token").and_then(Value::as_str)?;
    let resposta = reqwest::Client::new()
        .post(URL_TOKEN)
        .form(&[
            ("client_id", client_id),
            ("client_secret", client_secret),
            ("refresh_token", refresh),
            ("grant_type", "refresh_token"),
        ])
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

/// `{"user":{"emailAddress":"ana@gmail.com"}}` → `Some("ana@gmail.com")`.
///
/// Sem `@` não é e-mail: melhor não mostrar nada do que mostrar lixo.
pub fn email_da_resposta(corpo: &Value) -> Option<String> {
    let email = corpo.get("user")?.get("emailAddress")?.as_str()?.trim();
    if email.contains('@') && !email.chars().any(char::is_whitespace) {
        Some(email.to_string())
    } else {
        None
    }
}

#[cfg(test)]
mod testes {
    // Os testes de rede seguram a trava do idioma (global no processo) através
    // de `await`. Em teste isso é seguro: a trava só serializa os testes e não
    // há outra tarefa disputando o idioma no meio.
    #![allow(clippy::await_holding_lock)]

    use super::*;
    use std::sync::Mutex;

    /// O idioma é global no processo; estes testes mexem nele.
    static TRAVA: Mutex<()> = Mutex::new(());

    #[test]
    fn endereco_pede_acesso_offline_com_retorno_local() {
        let endereco = endereco_de_autorizacao(
            "123-abc.apps.googleusercontent.com",
            "http://127.0.0.1:53682/",
            "abc123",
        );
        assert!(endereco.starts_with("https://accounts.google.com/o/oauth2/auth?"));
        assert!(endereco.contains("client_id=123-abc.apps.googleusercontent.com"));
        assert!(endereco.contains("redirect_uri=http%3A%2F%2F127.0.0.1%3A53682%2F"));
        assert!(endereco.contains("scope=https%3A%2F%2Fwww.googleapis.com%2Fauth%2Fdrive"));
        assert!(endereco.contains("response_type=code"));
        // Sem `access_type=offline` o Google não manda refresh token.
        assert!(endereco.contains("access_type=offline"));
        assert!(endereco.contains("state=abc123"));
    }

    #[test]
    fn consulta_do_pedido_ignora_o_resto_da_linha() {
        let pedido = "GET /?state=x&code=4/0Ab HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n";
        assert_eq!(consulta_do_pedido(pedido), Some("state=x&code=4/0Ab"));
        assert_eq!(consulta_do_pedido("GET /favicon.ico HTTP/1.1\r\n\r\n"), None);
        assert_eq!(consulta_do_pedido("POST /?code=1 HTTP/1.1\r\n\r\n"), None);
        assert_eq!(consulta_do_pedido(""), None);
    }

    #[test]
    fn campos_sao_decodificados() {
        let campos = campos_da_consulta("code=4%2F0Ab%20x&state=abc&scope=drive+file&vazio=");
        assert_eq!(campo(&campos, "code").as_deref(), Some("4/0Ab x"));
        assert_eq!(campo(&campos, "state").as_deref(), Some("abc"));
        assert_eq!(campo(&campos, "scope").as_deref(), Some("drive file"));
        assert_eq!(campo(&campos, "vazio"), None);
        assert_eq!(campo(&campos, "naoexiste"), None);
    }

    #[test]
    fn codificar_e_decodificar_sao_inversos() {
        let original = "http://127.0.0.1:53682/ + /*ç*/ a&b=c";
        assert_eq!(decodificar(&codificar(original)), original);
        assert_eq!(codificar("a-b_c.d~e"), "a-b_c.d~e");
        assert_eq!(decodificar("%zz"), "%zz");
        assert_eq!(decodificar("%"), "%");
    }

    #[test]
    fn validade_vira_rfc3339() {
        assert_eq!(rfc3339(0), "1970-01-01T00:00:00Z");
        assert_eq!(rfc3339(1_000_000_000), "2001-09-09T01:46:40Z");
        // 29 de fevereiro existe em 2024 (ano bissexto).
        assert_eq!(rfc3339(1_709_164_800), "2024-02-29T00:00:00Z");
        assert_eq!(rfc3339(1_762_560_000), "2025-11-08T00:00:00Z");
    }

    #[test]
    fn pagina_fala_do_nuvem_sync_nos_dois_idiomas() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());

        crate::idioma::definir("pt");
        let portugues = pagina_de_sucesso();
        assert!(portugues.contains("BrisaSync"));
        assert!(portugues.contains("Conta conectada"));
        assert!(portugues.contains("voltar ao BrisaSync"));

        crate::idioma::definir("en");
        let ingles = pagina_de_sucesso();
        assert!(ingles.contains("Account connected"));
        assert!(ingles.contains("go back to BrisaSync"));
        assert!(!ingles.contains("Conta conectada"));
        assert!(ingles.contains(r#"lang="en""#));

        crate::idioma::definir("pt");
    }

    /// O laço de verdade, com um navegador de mentira: o pedido do favicon não
    /// atrapalha, o retorno com `state` certo vira código e a página é a do
    /// BrisaSync.
    #[tokio::test]
    async fn laco_local_entrega_o_codigo_e_a_pagina_do_nuvem() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");

        let ouvinte = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let porta = ouvinte.local_addr().unwrap().port();
        let espera = tokio::spawn(async move { esperar_codigo(ouvinte, "estado-1").await });

        let mut favicon = tokio::net::TcpStream::connect(("127.0.0.1", porta))
            .await
            .unwrap();
        favicon
            .write_all(b"GET /favicon.ico HTTP/1.1\r\nHost: local\r\n\r\n")
            .await
            .unwrap();
        let mut resposta_favicon = Vec::new();
        favicon.read_to_end(&mut resposta_favicon).await.unwrap();
        assert!(String::from_utf8_lossy(&resposta_favicon).contains("404"));

        let mut navegador = tokio::net::TcpStream::connect(("127.0.0.1", porta))
            .await
            .unwrap();
        navegador
            .write_all(b"GET /?state=estado-1&code=4%2F0Ab%20x HTTP/1.1\r\nHost: local\r\n\r\n")
            .await
            .unwrap();
        let mut resposta = Vec::new();
        navegador.read_to_end(&mut resposta).await.unwrap();
        let resposta = String::from_utf8_lossy(&resposta);
        assert!(resposta.contains("200 OK"));
        assert!(resposta.contains("Conta conectada"));
        assert!(resposta.contains("voltar ao BrisaSync"));

        assert_eq!(espera.await.unwrap().unwrap(), "4/0Ab x");
    }

    #[tokio::test]
    async fn retorno_com_state_errado_e_recusado() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");
        let ouvinte = TcpListener::bind(("127.0.0.1", 0)).await.unwrap();
        let porta = ouvinte.local_addr().unwrap().port();
        let espera = tokio::spawn(async move { esperar_codigo(ouvinte, "estado-1").await });

        let mut navegador = tokio::net::TcpStream::connect(("127.0.0.1", porta))
            .await
            .unwrap();
        navegador
            .write_all(b"GET /?state=outro&code=abc HTTP/1.1\r\nHost: local\r\n\r\n")
            .await
            .unwrap();
        let mut resposta = Vec::new();
        navegador.read_to_end(&mut resposta).await.unwrap();
        assert!(String::from_utf8_lossy(&resposta).contains("400"));

        let erro = espera.await.unwrap().unwrap_err().to_string();
        assert!(erro.contains("não confere"));
    }

    /// Servidor de mentira no lugar do Google: responde ao POST do token com o
    /// corpo combinado, para exercitar o fluxo inteiro sem tocar na internet.
    async fn google_de_mentira(codigo_http: u16, corpo: &'static str) -> String {
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
            let pedido = String::from_utf8_lossy(&pedido);
            assert!(pedido.starts_with("POST /token "));
            assert!(pedido.contains("grant_type=authorization_code"));
            assert!(pedido.contains("code=4%2F0Ab"));
            let resposta = format!(
                "HTTP/1.1 {codigo_http} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{corpo}",
                corpo.len()
            );
            fluxo.write_all(resposta.as_bytes()).await.unwrap();
            fluxo.flush().await.unwrap();
        });
        format!("http://127.0.0.1:{porta}/token")
    }

    #[tokio::test]
    async fn troca_do_codigo_vira_token_no_formato_do_rclone() {
        let endereco = google_de_mentira(
            200,
            r#"{"access_token":"ya29.teste","expires_in":3599,"refresh_token":"1//refresh","scope":"https://www.googleapis.com/auth/drive","token_type":"Bearer"}"#,
        )
        .await;

        let token = trocar_codigo_em(
            &endereco,
            "4/0Ab",
            "123-abc.apps.googleusercontent.com",
            "GOCSPX-segredo",
            "http://127.0.0.1:53682/",
        )
        .await
        .unwrap();

        assert_eq!(token["access_token"], "ya29.teste");
        assert_eq!(token["refresh_token"], "1//refresh");
        assert_eq!(token["token_type"], "Bearer");
        // O rclone espera RFC 3339 em `expiry`.
        let validade = token["expiry"].as_str().unwrap();
        assert_eq!(validade.len(), 20, "{validade}");
        assert!(validade.ends_with('Z'));
        assert!(validade.starts_with("20"));
    }

    #[tokio::test]
    async fn token_sem_refresh_vira_erro_explicado() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");
        let endereco = google_de_mentira(
            200,
            r#"{"access_token":"ya29.teste","expires_in":3599,"token_type":"Bearer"}"#,
        )
        .await;

        let erro = trocar_codigo_em(
            &endereco,
            "4/0Ab",
            "123-abc.apps.googleusercontent.com",
            "GOCSPX-segredo",
            "http://127.0.0.1:53682/",
        )
        .await
        .unwrap_err()
        .to_string();
        assert!(erro.contains("uma hora só"), "{erro}");
        assert!(erro.contains("myaccount.google.com/permissions"), "{erro}");
    }

    #[tokio::test]
    async fn credenciais_recusadas_pelo_google_explicam_o_que_conferir() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");
        let endereco = google_de_mentira(
            400,
            r#"{"error":"invalid_client","error_description":"Unauthorized"}"#,
        )
        .await;

        let erro = trocar_codigo_em(
            &endereco,
            "4/0Ab",
            "123-abc.apps.googleusercontent.com",
            "GOCSPX-errado",
            "http://127.0.0.1:53682/",
        )
        .await
        .unwrap_err()
        .to_string();
        assert!(erro.contains("Ajustes → Avançado"), "{erro}");
        assert!(erro.contains("invalid_client"), "{erro}");
    }

    /// A mensagem que aparece na janela segue o idioma do app — e leva a causa
    /// real junto (o `reqwest` sozinho só diz "error sending request").
    #[tokio::test]
    async fn erro_de_transporte_sai_no_idioma_do_app() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        // Porta fechada de propósito: a conexão é recusada na hora.
        let falhar = || {
            trocar_codigo_em(
                "http://127.0.0.1:9/token",
                "4/0Ab",
                "123-abc.apps.googleusercontent.com",
                "GOCSPX-segredo",
                "http://127.0.0.1:53682/",
            )
        };

        crate::idioma::definir("pt");
        let portugues = falhar().await.unwrap_err().to_string();
        assert!(
            portugues.contains("não foi possível falar com o Google"),
            "{portugues}"
        );
        assert!(
            portugues.contains("onnection refused"),
            "a causa real precisa aparecer: {portugues}"
        );

        crate::idioma::definir("en");
        let ingles = falhar().await.unwrap_err().to_string();
        assert!(
            ingles.contains("could not reach Google to finish the authorization"),
            "{ingles}"
        );

        crate::idioma::definir("pt");
    }

    /// Prova de verdade que o HTTPS funciona (TLS ligado, raízes embutidas) e
    /// que o par do projeto é aceito pelo Google: um código falso tem de voltar
    /// como `invalid_grant`, e não como "error sending request" nem
    /// `invalid_client`. Fica `#[ignore]` porque depende da rede e do par do
    /// projeto no ambiente:
    ///
    /// ```text
    /// cargo test --lib -- --ignored fala_https_com_o_google
    /// ```
    #[tokio::test]
    #[ignore]
    async fn fala_https_com_o_google() {
        let Some((id, segredo)) = crate::oauth::do_build() else {
            eprintln!("sem par OAuth no ambiente: nada para conferir");
            return;
        };
        let erro = trocar_codigo_por_token("codigo-falso", &id, &segredo, "http://127.0.0.1:53682/")
            .await
            .unwrap_err()
            .to_string();
        assert!(!erro.contains("error sending request"), "{erro}");
        assert!(!erro.contains("invalid_client"), "{erro}");
        assert!(erro.contains("invalid_grant"), "{erro}");
    }

    #[test]
    fn email_da_resposta_le_a_conta_do_about_do_drive() {
        let corpo = serde_json::json!({
            "user": { "emailAddress": "  ana@gmail.com " }
        });
        assert_eq!(email_da_resposta(&corpo), Some("ana@gmail.com".to_string()));
    }

    #[test]
    fn email_da_resposta_nao_inventa_quando_o_campo_falta() {
        // Conta de serviço, resposta sem `user`, campo vazio: nada a mostrar.
        assert_eq!(email_da_resposta(&serde_json::json!({})), None);
        assert_eq!(email_da_resposta(&serde_json::json!({ "user": {} })), None);
        assert_eq!(
            email_da_resposta(&serde_json::json!({ "user": { "emailAddress": "" } })),
            None
        );
        assert_eq!(
            email_da_resposta(&serde_json::json!({ "user": { "emailAddress": "sem arroba" } })),
            None
        );
    }

    /// Servidor de mentira no lugar do `about` do Drive.
    async fn drive_de_mentira(codigo_http: u16, corpo: &'static str) -> String {
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
            assert!(pedido.starts_with("GET /about?"), "{pedido}");
            // Só o e-mail: não pedimos a árvore inteira da conta.
            assert!(pedido.contains("fields=user"), "{pedido}");
            assert!(
                pedido.to_lowercase().contains("authorization: bearer ya29.teste"),
                "{pedido}"
            );
            let resposta = format!(
                "HTTP/1.1 {codigo_http} OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{corpo}",
                corpo.len()
            );
            fluxo.write_all(resposta.as_bytes()).await.unwrap();
            fluxo.flush().await.unwrap();
        });
        format!("http://127.0.0.1:{porta}/about")
    }

    #[tokio::test]
    async fn email_em_pergunta_ao_drive_qual_e_a_conta() {
        let endereco = drive_de_mentira(
            200,
            r#"{"user":{"emailAddress":"fabioagreles@gmail.com"}}"#,
        )
        .await;

        let email = email_em(&endereco, "ya29.teste").await.unwrap();
        assert_eq!(email, Some("fabioagreles@gmail.com".to_string()));
    }

    #[tokio::test]
    async fn email_em_trata_recusa_do_google_como_falha() {
        let endereco = drive_de_mentira(403, r#"{"error":{"code":403}}"#).await;
        assert!(email_em(&endereco, "ya29.teste").await.is_err());
    }

    /// Conta sem token (remote criado à mão, por exemplo) não vira erro nem
    /// tentativa de rede: apenas nada a mostrar.
    #[tokio::test]
    async fn email_da_conta_sem_token_devolve_nada() {
        let token = serde_json::json!({ "token_type": "Bearer" });
        assert_eq!(email_da_conta(&token, "id", "segredo").await, None);
    }

    /// Prova de ponta a ponta contra o Google de verdade: mesmo `about`, mesmo
    /// HTTPS. Precisa de um token no ambiente (`BRISASYNC_TOKEN_DE_TESTE` = o JSON
    /// guardado no `rclone.conf`), por isso fica `#[ignore]`:
    ///
    /// ```text
    /// BRISASYNC_TOKEN_DE_TESTE="$(...)"; cargo test --lib -- --ignored le_o_email_da_conta
    /// ```
    #[tokio::test]
    #[ignore]
    async fn le_o_email_da_conta() {
        let Ok(bruto) = std::env::var("BRISASYNC_TOKEN_DE_TESTE") else {
            eprintln!("sem BRISASYNC_TOKEN_DE_TESTE: nada para conferir");
            return;
        };
        let token: Value = serde_json::from_str(&bruto).expect("token em JSON");
        let (id, segredo) = crate::oauth::do_build().unwrap_or_default();
        let email = email_da_conta(&token, &id, &segredo)
            .await
            .expect("devia ler o e-mail da conta");
        eprintln!("conta conectada: {email}");
        assert!(email.contains('@'), "{email}");
    }
    #[test]
    fn pagina_de_erro_nao_mostra_marca_de_outro_programa() {
        let _trava = TRAVA.lock().unwrap_or_else(|erro| erro.into_inner());
        crate::idioma::definir("pt");
        let pagina = pagina_de_erro("Autorização cancelada", "Authorization cancelled");
        assert!(pagina.contains("Autorização cancelada"));
        assert!(!pagina.contains("rclone"));
    }
}

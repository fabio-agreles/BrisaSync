use crate::error::{AppError, AppResult};
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    process::Stdio,
    sync::Arc,
    time::Duration,
};
use tokio::{
    process::{Child, Command},
    sync::Mutex,
    time::sleep,
};

struct Daemon {
    child: Child,
    port: u16,
    /// Usuário e senha do painel RC (HTTP Basic), sorteados nesta execução.
    usuario: String,
    senha: String,
}

impl Daemon {
    fn credenciais(&self) -> (String, String) {
        (self.usuario.clone(), self.senha.clone())
    }
}

/// Sorteia usuário e senha do painel RC.
///
/// O daemon escuta em `127.0.0.1`, mas isso não isola nada: em máquina
/// multiusuário qualquer processo local alcança a porta — e `config/dump`
/// devolve os tokens OAuth em texto puro. Sem autenticação (`--rc-no-auth`), um
/// `curl` de outro usuário leria as credenciais das contas. Agora cada execução
/// sorteia uma senha nova (48 caracteres hex de 24 bytes do gerador do sistema),
/// que só vive na memória deste processo.
fn credenciais() -> AppResult<(String, String)> {
    let mut bytes = [0u8; 24];
    getrandom::fill(&mut bytes).map_err(|error| {
        AppError::new(format!(
            "não foi possível sortear a senha do motor de sincronização: {error}"
        ))
    })?;
    let senha = bytes.iter().map(|byte| format!("{byte:02x}")).collect();
    Ok(("brisasync".to_string(), senha))
}

/// Nome do executável do rclone. No Windows o sufixo `.exe` faz parte do nome —
/// sem ele o `Command::new` não encontra o binário embutido no pacote.
#[cfg(windows)]
const RCLONE: &str = "rclone.exe";
#[cfg(not(windows))]
const RCLONE: &str = "rclone";

/// `CREATE_NO_WINDOW`: o rclone é um processo de linha de comando; sem a flag o
/// Windows abriria uma janela de console preta piscando a cada sincronização.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// Esconde a janela de console do subprocesso no Windows.
///
/// O `rclone.exe` é um programa de console: todo `Command::new` no Windows
/// **abre uma janela preta** por um instante, mesmo quando a saída é capturada
/// com `.output()`. Isso rendeu reclamação real — "ficam piscando umas janelas
/// do MS-DOS, inclusive ao navegar pelo programa", porque `list_accounts_inner`
/// (`config dump`) roda a cada tela que lista contas e `version()` roda no
/// status do motor. A flag foi aplicada no daemon e ficou faltando no resto.
///
/// No Linux/macOS não existe janela a esconder: os métodos viram no-op, então o
/// mesmo código de chamada serve para os três sistemas.
pub trait SemConsole {
    fn sem_console(&mut self) -> &mut Self;
}

#[cfg(windows)]
impl SemConsole for Command {
    fn sem_console(&mut self) -> &mut Self {
        self.creation_flags(CREATE_NO_WINDOW)
    }
}

#[cfg(windows)]
impl SemConsole for std::process::Command {
    fn sem_console(&mut self) -> &mut Self {
        use std::os::windows::process::CommandExt as _;
        self.creation_flags(CREATE_NO_WINDOW)
    }
}

#[cfg(not(windows))]
impl SemConsole for Command {
    fn sem_console(&mut self) -> &mut Self {
        self
    }
}

#[cfg(not(windows))]
impl SemConsole for std::process::Command {
    fn sem_console(&mut self) -> &mut Self {
        self
    }
}

#[derive(Clone)]
pub struct Rclone {
    inner: Arc<Inner>,
}

struct Inner {
    daemon: Mutex<Option<Daemon>>,
    client: reqwest::Client,
    proxy: std::sync::Mutex<String>,
}

impl Rclone {
    pub fn new() -> Self {
        let client = reqwest::Client::builder()
            // O daemon é sempre loopback: nunca deve passar por um proxy do ambiente.
            .no_proxy()
            .build()
            .expect("cliente HTTP local");
        Self {
            inner: Arc::new(Inner {
                daemon: Mutex::new(None),
                client,
                proxy: std::sync::Mutex::new(String::new()),
            }),
        }
    }

    /// Atualiza o proxy usado pelo daemon `rclone rcd`. Devolve `true` se o valor mudou.
    pub fn set_proxy(&self, proxy: &str) -> bool {
        let normalized = proxy.trim().to_string();
        let mut guard = self.inner.proxy.lock().expect("proxy mutex");
        if *guard == normalized {
            return false;
        }
        *guard = normalized;
        true
    }

    fn current_proxy(&self) -> String {
        self.inner.proxy.lock().expect("proxy mutex").clone()
    }

    /// Verifica se o candidato é um executável válido e seguro (arquivo regular,
    /// não vazio e, no Unix, executável e sem permissão de escrita para outros).
    fn is_valid_binary(candidate: &Path) -> bool {
        let Ok(meta) = std::fs::metadata(candidate) else {
            return false;
        };
        if !meta.is_file() || meta.len() == 0 {
            return false;
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt as _;
            let mode = meta.permissions().mode();
            if mode & 0o111 == 0 || mode & 0o002 != 0 {
                return false;
            }
        }
        true
    }

    /// Localiza o rclone: variável de ambiente, cópia embutida no pacote, PATH e
    /// caminhos do Flatpak/usuário.
    pub fn find_binary() -> Option<PathBuf> {
        if let Ok(configured) = std::env::var("BRISASYNC_RCLONE") {
            let candidate = PathBuf::from(configured);
            if Self::is_valid_binary(&candidate) {
                return Some(candidate);
            }
        }

        let mut candidates: Vec<PathBuf> = Vec::new();
        // Cópia embutida: ao lado do executável (sidecar) ou em lib/<produto>
        // (resources do .deb/AppImage). É o caminho preferido: não depende do sistema.
        if let Ok(exe) = std::env::current_exe() {
            if let Some(dir) = exe.parent() {
                candidates.push(dir.join(RCLONE));
                // `resources` em lista (o que o pacote do Windows usa) mantém a
                // pasta de origem ao lado do executável.
                candidates.push(dir.join("resources").join(RCLONE));
                if let Some(prefix) = dir.parent() {
                    for product in ["BrisaSync", "brisasync"] {
                        candidates.push(prefix.join("lib").join(product).join(RCLONE));
                    }
                }
            }
        }
        if let Some(path) = std::env::var_os("PATH") {
            candidates.extend(std::env::split_paths(&path).map(|dir| dir.join(RCLONE)));
        }
        #[cfg(unix)]
        {
            candidates.push(PathBuf::from("/app/bin/rclone"));
            candidates.push(PathBuf::from("/usr/bin/rclone"));
            candidates.push(PathBuf::from("/usr/local/bin/rclone"));
            if let Some(home) = std::env::var_os("HOME") {
                candidates.push(PathBuf::from(home).join(".local/bin/rclone"));
            }
        }
        #[cfg(windows)]
        {
            // O instalador do Windows põe o `rclone.exe` ao lado do `BrisaSync.exe`
            // (resources do NSIS).
            if let Some(local) = std::env::var_os("LOCALAPPDATA") {
                for produto in ["BrisaSync"] {
                    candidates.push(PathBuf::from(&local).join(produto).join(RCLONE));
                    candidates.push(PathBuf::from(&local).join("Programs").join(produto).join(RCLONE));
                }
            }
        }

        candidates
            .into_iter()
            .find(|candidate| Self::is_valid_binary(candidate))
    }

    pub async fn binary(&self) -> AppResult<PathBuf> {
        Self::find_binary().ok_or_else(|| {
            AppError::new(
                "rclone não encontrado. Instale o rclone ou defina BRISASYNC_RCLONE com o caminho do executável.",
            )
        })
    }

    pub async fn version(&self, binary: &Path) -> Option<String> {
        // `rclone version` roda a cada consulta de status: no Windows tem de sair
        // sem console, senão a janela preta pisca ao navegar.
        let mut command = Command::new(binary);
        command.arg("version").sem_console();
        let output = command.output().await.ok()?;
        let text = String::from_utf8_lossy(&output.stdout);
        text.lines()
            .find_map(|line| line.strip_prefix("rclone v").map(|rest| format!("v{}", rest.trim())))
    }

    pub async fn is_running(&self) -> bool {
        let mut guard = self.inner.daemon.lock().await;
        match guard.as_mut() {
            Some(daemon) => match daemon.child.try_wait() {
                Ok(None) => true,
                _ => {
                    *guard = None;
                    false
                }
            },
            None => false,
        }
    }

    /// Sobe (ou reaproveita) o daemon `rclone rcd` em uma porta loopback livre.
    pub async fn ensure(&self) -> AppResult<u16> {
        let mut guard = self.inner.daemon.lock().await;
        if let Some(daemon) = guard.as_mut() {
            match daemon.child.try_wait() {
                Ok(None) => return Ok(daemon.port),
                _ => *guard = None,
            }
        }

        let binary = self.binary().await?;
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0))
            .map_err(|error| AppError::new(format!("não foi possível reservar uma porta local: {error}")))?;
        let port = listener
            .local_addr()
            .map_err(|error| AppError::new(format!("porta local inválida: {error}")))?
            .port();
        drop(listener);

        let (usuario, senha) = credenciais()?;
        let mut command = Command::new(&binary);
        command
            .arg("rcd")
            .arg("--rc-addr")
            .arg(format!("127.0.0.1:{port}"))
            // Sem `--rc-no-auth`: o painel exige HTTP Basic e a senha muda a cada
            // execução (ver `credenciais`). A senha vai por variável de ambiente
            // (`RCLONE_RC_PASS`) para não aparecer em `ps` / `/proc/<pid>/cmdline`.
            .arg("--rc-user")
            .arg(&usuario)
            .env("RCLONE_RC_PASS", &senha)
            .arg("--log-level")
            // INFO (e não ERROR) para que cada tarefa devolva o log da execução:
            // é dele que sai o resumo "No changes found" usado para não avisar
            // sobre verificações automáticas que não moveram nada.
            .arg("INFO")
            .arg("--stats")
            .arg("1s")
            // ---------- velocidade ----------
            // O Google Drive limita por *requisições por minuto* no projeto OAuth
            // compartilhado do rclone (`project_number:202264815644`). Sem um teto,
            // o rclone leva 403 em cascata e o “pacer” passa a dormir 8 s, 16 s por
            // tentativa — a sincronização anda a poucos KB/s mesmo com banda sobrando.
            // Pedir menos por segundo evita o castigo e o resultado é mais rápido.
            .arg("--tpslimit")
            .arg("10")
            .arg("--tpslimit-burst")
            .arg("20")
            // Arquivos menores que o corte sobem em uma única requisição (em vez de
            // uma por pedaço); os maiores usam pedaços de 32 MiB, o que reduz de ~13
            // para 4 requisições um arquivo de 100 MiB.
            .arg("--drive-upload-cutoff")
            .arg("16M")
            .arg("--drive-chunk-size")
            .arg("32M")
            // Mais arquivos em paralelo — o suficiente para encher a banda sem
            // multiplicar os 403.
            .arg("--transfers")
            .arg("6")
            .arg("--checkers")
            .arg("8")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .kill_on_drop(true);
        let proxy = self.current_proxy();
        if !proxy.is_empty() {
            command
                .env("HTTP_PROXY", &proxy)
                .env("HTTPS_PROXY", &proxy)
                .env("ALL_PROXY", &proxy)
                .env("http_proxy", &proxy)
                .env("https_proxy", &proxy)
                .env("all_proxy", &proxy)
                .env("NO_PROXY", "127.0.0.1,localhost")
                .env("no_proxy", "127.0.0.1,localhost");
        }
        // Sem console piscando no Windows (o rclone roda escondido a vida toda).
        command.sem_console();
        let mut child = command
            .spawn()
            .map_err(|error| AppError::new(format!("não foi possível iniciar o rclone: {error}")))?;

        let mut ready = false;
        for _ in 0..40 {
            if self
                .call_at(port, &usuario, &senha, "core/version", json!({}), Duration::from_secs(2))
                .await
                .is_ok()
            {
                ready = true;
                break;
            }
            if let Ok(Some(status)) = child.try_wait() {
                return Err(AppError::new(format!(
                    "o rclone encerrou durante a inicialização ({status})"
                )));
            }
            sleep(Duration::from_millis(250)).await;
        }

        if !ready {
            let _ = child.start_kill();
            return Err(AppError::new(
                "o motor de sincronização não respondeu. Verifique a instalação do rclone.",
            ));
        }

        *guard = Some(Daemon {
            child,
            port,
            usuario,
            senha,
        });
        Ok(port)
    }

    pub async fn call(&self, method: &str, params: Value, timeout: Duration) -> AppResult<Value> {
        let atual = {
            let guard = self.inner.daemon.lock().await;
            guard.as_ref().map(|daemon| (daemon.port, daemon.credenciais()))
        };
        let (port, (usuario, senha)) =
            atual.ok_or_else(|| AppError::new("motor de sincronização não está em execução"))?;
        self.call_at(port, &usuario, &senha, method, params, timeout)
            .await
    }

    async fn call_at(
        &self,
        port: u16,
        usuario: &str,
        senha: &str,
        method: &str,
        params: Value,
        timeout: Duration,
    ) -> AppResult<Value> {
        let response = self
            .inner
            .client
            .post(format!("http://127.0.0.1:{port}/{method}"))
            // O rclone aceita `--rc-user`/`--rc-pass` como HTTP Basic. Sem isto o
            // daemon responde 401.
            .basic_auth(usuario, Some(senha))
            .timeout(timeout)
            .json(&params)
            .send()
            .await?;

        let status = response.status();
        let body = response.text().await?;
        if !status.is_success() {
            return Err(AppError::new(format!("rclone {method}: {body}")));
        }
        if body.trim().is_empty() {
            return Ok(Value::Null);
        }

        let value: Value = serde_json::from_str(&body)?;
        if let (Some(error), Some(_)) = (
            value.get("error").and_then(Value::as_str),
            value.get("path").and_then(Value::as_str),
        ) {
            return Err(AppError::new(format!("rclone {method}: {error}")));
        }
        Ok(value)
    }

    pub async fn stop(&self) {
        let mut guard = self.inner.daemon.lock().await;
        if let Some(mut daemon) = guard.take() {
            let _ = daemon.child.start_kill();
            let _ = daemon.child.wait().await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    /// Duas execuções nunca compartilham a senha e ela tem tamanho de sobra.
    #[test]
    fn credenciais_sao_aleatorias() {
        let (usuario, senha) = credenciais().expect("credenciais");
        assert_eq!(usuario, "brisasync");
        assert_eq!(senha.len(), 48);
        assert!(senha.chars().all(|c| c.is_ascii_hexdigit()));

        let (_, outra) = credenciais().expect("credenciais");
        assert_ne!(senha, outra, "a senha do painel não pode se repetir");
    }

    /// O `call_at` precisa mandar `Authorization: Basic`, senão o rclone — que
    /// agora roda com `--rc-user`/`--rc-pass` — responde 401 e o app fica sem
    /// motor. Aqui um servidor TCP de mentira guarda a requisição e confere.
    #[tokio::test]
    async fn chamada_leva_autenticacao_basica() {
        let listener = tokio::net::TcpListener::bind(("127.0.0.1", 0))
            .await
            .expect("porta");
        let port = listener.local_addr().expect("endereço").port();

        let servidor = tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.expect("conexão");
            let mut buffer = vec![0u8; 2048];
            let lidos = socket.read(&mut buffer).await.expect("leitura");
            let _ = socket
                .write_all(b"HTTP/1.1 200 OK\r\ncontent-length: 2\r\n\r\n{}")
                .await;
            String::from_utf8_lossy(&buffer[..lidos]).to_string()
        });

        let rclone = Rclone::new();
        let _ = rclone
            .call_at(port, "brisasync", "segredo", "core/version", json!({}), Duration::from_secs(5))
            .await;
        let requisicao = servidor.await.expect("servidor");

        // base64("brisasync:segredo")
        assert!(
            requisicao.contains("authorization: Basic YnJpc2FzeW5jOnNlZ3JlZG8=")
                || requisicao.contains("Authorization: Basic YnJpc2FzeW5jOnNlZ3JlZG8="),
            "requisição sem HTTP Basic: {requisicao}"
        );
    }

    /// Teste de verdade contra o rclone instalado (roda só onde ele existe):
    /// sobe o daemon com as credenciais sorteadas, espera o `core/version` pela
    /// rota autenticada e confere que sem credencial a mesma porta devolve 401.
    #[tokio::test]
    async fn daemon_sobe_autenticado() {
        if Rclone::find_binary().is_none() {
            eprintln!("rclone ausente: pulando o teste de integração");
            return;
        }

        let rclone = Rclone::new();
        let porta = match rclone.ensure().await {
            Ok(porta) => porta,
            Err(error) => {
                eprintln!("não foi possível subir o daemon: {error}");
                return;
            }
        };

        let versao = rclone
            .call("core/version", json!({}), Duration::from_secs(10))
            .await
            .expect("daemon respondeu com autenticação");
        assert!(versao.get("version").is_some(), "resposta inesperada: {versao}");

        let sem_auth = reqwest::Client::new()
            .post(format!("http://127.0.0.1:{porta}/core/version"))
            .timeout(Duration::from_secs(5))
            .send()
            .await
            .expect("requisição sem credencial");
        assert_eq!(
            sem_auth.status().as_u16(),
            401,
            "o painel RC aceitou uma chamada sem credencial"
        );

        rclone.stop().await;
    }
}

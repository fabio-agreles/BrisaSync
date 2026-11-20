# Política de segurança do BrisaSync

O BrisaSync é um aplicativo de desktop de código aberto que sincroniza pastas entre este computador e **Google Drive**, **OneDrive**, **Dropbox** e **Nextcloud**. Ele **não tem servidor**: os tokens e os arquivos ficam na máquina de quem usa.

## Como relatar uma vulnerabilidade

**Não abra uma issue pública** para falhas de segurança. Escreva para `fabioagreles@gmail.com` com o assunto `[segurança] BrisaSync`.

Se preferir o canal privado do GitHub (Settings → *Private vulnerability reporting* precisa estar ligado no repositório):
<https://github.com/fabio-agreles/BrisaSync/security/advisories/new>

Inclua, se possível: versão do app (Ajustes → Sobre), sistema operacional, o que acontece, como reproduzir e o impacto que você imagina.

## O que esperar

| Etapa | Prazo |
| --- | --- |
| Confirmação de recebimento | até 5 dias |
| Avaliação inicial e classificação | até 10 dias |
| Correção e versão publicada | depende da gravidade: falhas críticas o quanto antes; o restante entra na versão seguinte |

Você será avisado quando a correção sair e, se quiser, será creditado na nota da versão. Não há programa de recompensa financeira.

## O que está no escopo

- O aplicativo e o motor de sincronização embutido (rclone 1.75.2).
- O fluxo de autorização (OAuth) do próprio app: `login_google.rs`, `login_microsoft.rs` e `oauth.rs`.
- O armazenamento local de credenciais (`rclone.conf`, `0600`) e dos ajustes.
- Os pacotes publicados (`.deb`, AppImage, Flatpak, instalador e portátil do Windows) e os scripts de build.

## O que está fora do escopo

- Falhas no rclone que já tenham correção em versão mais nova (avise mesmo assim; atualizamos).
- Falhas nas APIs do Google, Microsoft, Dropbox ou Nextcloud.
- Ataques que exijam acesso físico à máquina ou um usuário já comprometido.
- Engenharia social e spam.
- Relatos automáticos de scanner sem impacto demonstrado.

## Práticas do projeto

- Dependências travadas em `Cargo.lock`; o Flatpak usa fontes vendorizadas com verificação de checksum (`app/flatpak/cargo-sources.json`).
- CI em cada push: `tsc`, checagem de i18n, `clippy --all-targets -D warnings` e testes; build de release por workflow com os pacotes publicados no GitHub.
- Nenhum segredo no repositório: o `client_secret` do OAuth não vai para o binário e os segredos de build ficam nos *repository secrets*.
- Nenhuma telemetria. O relatório de diagnóstico é gerado localmente e só sai se quem usa decidir enviar; ele nunca inclui tokens ou senhas.
- A política de privacidade e as práticas de dados estão em [`PRIVACIDADE.md`](PRIVACIDADE.md).

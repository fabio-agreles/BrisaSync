# Política de privacidade do BrisaSync

Última atualização: 20 de novembro de 2026.

O BrisaSync é um aplicativo de desktop que mantém pastas deste computador em
sincronização bidirecional com o Google Drive, OneDrive, Dropbox e Nextcloud. **Não existe servidor
do BrisaSync**: nada do seu conteúdo passa por máquinas nossas, porque não temos
nenhuma.

## Que dados o aplicativo acessa

| Dado | Para quê | Onde fica |
| --- | --- | --- |
| Arquivos e pastas da nuvem **que você escolhe sincronizar** | Copiar de/para a pasta local que você indicou (bisync) | No seu computador e no provedor que você conectou |
| Nome, e-mail e cota da sua conta (Google, OneDrive, Dropbox ou Nextcloud) | Mostrar o card da conta e o uso de armazenamento | No seu computador |
| Tokens de acesso (OAuth) | Falar com a API do provedor sem pedir sua senha a cada vez | `~/.config/rclone/rclone.conf` (`%APPDATA%\rclone`), permissão `0600` |
| Ajustes e histórico de atividade | Manter as preferências e mostrar o que foi sincronizado | `~/.config/app.brisasync.BrisaSync` (`%APPDATA%\app.brisasync.BrisaSync`) |

O aplicativo **não** lê arquivos fora das pastas que você adicionou, **não**
acessa Gmail, contatos, calendário ou fotos, e **não** guarda cópia do seu
conteúdo em lugar nenhum além do computador e da conta que você conectou.

## Escopo do Google Drive

O BrisaSync pede o escopo `https://www.googleapis.com/auth/drive` porque a
sincronização precisa ler e gravar arquivos que **já existem** na sua conta —
é o caso de uma pasta de trabalho que você quer manter igual nos dois lados. O
escopo mais restrito (`drive.file`) só enxerga arquivos criados pelo próprio
aplicativo, o que impediria a sincronização de pastas existentes. O acesso é
usado exclusivamente para transferir os arquivos das pastas que você escolheu.

## O que sai do seu computador

- Requisições para as APIs do **Google**, **Microsoft**, **Dropbox** ou do seu servidor **Nextcloud** (as mesmas que o seu navegador faria ao usar o serviço na web), autenticadas com o token ou credencial da sua conta.
- Se você pedir "Verificar atualização" em Ajustes → Sobre: uma requisição para
  `https://api.github.com` perguntando a última versão publicada. Ela não leva
  identificador seu, arquivos, nomes de pastas nem token.

Não há telemetria, análise de uso, crash reporting remoto nem publicidade.

## Como os dados são usados

Os dados do Google têm uma única finalidade: transferir os arquivos das pastas
que você escolheu entre o Drive e o seu computador, e mostrar no aplicativo o
nome, o e-mail e a cota da conta. Não há outra finalidade, não há análise de uso
e não há uso publicitário.

## Com quem os dados são compartilhados

**Com ninguém.** O BrisaSync não tem servidor e não envia seus arquivos, seu
token ou seu e-mail para terceiros. Só veem os dados: você, o computador onde o
aplicativo roda e o provedor que você conectou (Google, Microsoft, Dropbox ou seu servidor Nextcloud) — este
último porque é ele quem hospeda a sua pasta. Nada é vendido, alugado ou cedido a
corretores de dados, anunciantes ou qualquer outro terceiro.

## Como os dados são protegidos

- O token OAuth fica só no seu computador, em `rclone.conf`, com permissão
  `0600` (só o seu usuário lê).
- Todo o tráfego com os provedores vai por HTTPS, com verificação de
  certificado.
- Não existe servidor do BrisaSync, então não existe base de dados nossa para
  vazar: o que não é coletado não pode ser perdido.
- O código é aberto (licença MIT): qualquer pessoa pode conferir o que o
  aplicativo faz com os dados.

## Uso limitado dos dados do Google (Limited Use)

O uso das informações recebidas das APIs do Google pelo BrisaSync está em
conformidade com a
[Política de Dados do Usuário dos Serviços de API do Google](https://developers.google.com/terms/api-services-user-data-policy),
incluindo os requisitos de Uso Limitado.

O BrisaSync não usa dados do Google para desenvolver, melhorar ou treinar
modelos de inteligência artificial ou de aprendizado de máquina, e não os
transfere para serviços de terceiros que façam isso — o aplicativo não usa IA/ML
em nenhuma função.

## Relatório de diagnóstico

O relatório (Ajustes → Sobre → Salvar) é gerado **localmente** e só é enviado
se você mesmo enviar. Ele contém versão do app, sistema, versão do rclone,
nomes das contas e das pastas, ajustes e os últimos erros — nunca senhas,
tokens ou o `client_secret` do OAuth.

## Por quanto tempo os dados ficam e como apagá-los

**Retenção:** nada é guardado em servidores nossos, porque não temos nenhum. No
seu computador, o token da conta fica até você desconectar a conta no aplicativo;
os ajustes e o histórico ficam até você desinstalar e apagar as pastas de
configuração; os arquivos sincronizados ficam na pasta local e no Drive, e apagar
de um lado apaga do outro, como em qualquer sincronização.

1. **Desconectar uma conta** (Visão geral → Contas): apaga as credenciais dela
   do `rclone.conf` e o estado do bisync daquelas pastas.
2. **Desinstalar** o aplicativo: os arquivos ficam em `~/.config/app.brisasync.BrisaSync`
   e `~/.config/rclone` (Windows: `%APPDATA%`). Apague essas duas pastas para
   remover tudo. Seus arquivos na nuvem não são tocados.
3. **Revogar o acesso** direto no provedor:
   [myaccount.google.com/permissions](https://myaccount.google.com/permissions)
   (Google) ou [account.live.com/consent/Manage](https://account.live.com/consent/Manage)
   (Microsoft).

## Contato

Dúvidas sobre privacidade: abra uma issue em
<https://github.com/fabio-agreles/BrisaSync/issues>.

## Privacy policy — English summary

BrisaSync is an open-source desktop application (MIT) that keeps folders on
your computer in two-way sync with Google Drive, OneDrive, Dropbox, or Nextcloud. It has **no
server**: your files and credentials never reach us.

The application only accesses the files and folders you explicitly add to it,
plus your account name, e-mail and storage quota (to show them in the
interface). OAuth tokens and settings are stored locally with `0600`
permissions. The `https://www.googleapis.com/auth/drive` scope is requested
because syncing an existing folder requires reading and writing files the app
did not create — the narrower `drive.file` scope would only cover app-created
files. Data received from Google APIs is used solely to transfer the files in
the folders you selected.

Network requests go only to the Google, Microsoft, Dropbox, or your Nextcloud server APIs, and — if you press
"Check for updates" — to `api.github.com`. There is no telemetry, analytics,
remote crash reporting or advertising.

**Data use:** Google user data is used for one purpose only — transferring the
files of the folders you selected between your Drive and your computer, and
showing your account name, e-mail and quota in the app. No analytics, no
advertising.

**Data transfer:** nothing is shared with third parties. There is no server of
ours; data is never sold, rented or handed to data brokers, advertisers or any
other party.

**Data protection:** the OAuth token stays on your machine in `rclone.conf` with
`0600` permissions, all traffic to your cloud providers uses HTTPS with
certificate validation, and there is no server-side database of ours that could
leak.

**Retention and deletion:** nothing is retained on our side. The account token
stays on your computer until you disconnect the account; settings and history
stay until you uninstall and remove the configuration folders; synced files stay
in your local folder and in your Drive, and deleting one side deletes the other,
as in any sync tool.

**Limited Use:** BrisaSync's use and transfer to any other app of information
received from Google APIs will adhere to the
[Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy),
including the Limited Use requirements. Google user data is not used to develop,
improve or train AI/ML models and is not transferred to third-party AI/ML
services; the app does not use AI/ML at all.

To delete your data: disconnect the account in the app, remove `~/.config/app.brisasync.BrisaSync` and `~/.config/rclone`,
and revoke access at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).
Contact: open an issue at
[github.com/fabio-agreles/BrisaSync/issues](https://github.com/fabio-agreles/BrisaSync/issues).

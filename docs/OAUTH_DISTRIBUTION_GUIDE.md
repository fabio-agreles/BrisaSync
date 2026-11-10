# Guia do Mantenedor: Configuração do Cliente OAuth Google para Distribuição Oficial

Este documento orienta o mantenedor do **BrisaSync** sobre como configurar a infraestrutura de autenticação Google OAuth 2.0 oficial da distribuição, garantindo que o usuário comum possa utilizar o fluxo:
```text
Instalar pacote -> Abrir BrisaSync -> Conectar Conta Google (1 clique) -> Autorizar no Navegador -> Sincronizar
```
sem precisar criar contas no Google Cloud Console ou manipular arquivos JSON manualmente.

---

## 1. Princípio Fundamental de Segurança: Metadados vs Tokens Pessoais

É imprescindível diferenciar duas classes de dados:

| Categoria | Descrição | Nível de Sigilo | Onde Reside |
| :--- | :--- | :--- | :--- |
| **Metadados do Cliente OAuth Desktop** | Identificadores públicos do aplicativo (`client_id`, `client_secret` de aplicativo desktop, `auth_uri`, `token_uri`). | **Público por natureza** (aplicativos nativos para desktop não podem manter segredo confidencial; a segurança é garantida por PKCE S256 e loopback 127.0.0.1). | Embutido no pacote (`/usr/share/brisasync/google_oauth_client.json`). |
| **Tokens Pessoais de Cada Usuário** | Credenciais individuais resultantes do consentimento do usuário (`access_token`, `refresh_token`, e-mail pessoal, chaves de cifragem da ponte rclone). | **Altamente Confidencial**. | **Nunca embutido em pacotes**. Salvo exclusivamente no cofre da sessão do usuário (`Secret Service` / `KWallet`). |

> [!CAUTION]
> **Regra de Ouro**: Nenhum pacote instalável, repositório ou artefato distribuído pode conter arquivos de banco de dados (`.db`), tokens, sessões ativas ou credenciais pessoais de usuários.

---

## 2. Passo a Passo para o Mantenedor no Google Cloud Console

Para disponibilizar o cliente oficial da distribuição:

### 2.1. Criar o Projeto no Google Cloud
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto denominado **BrisaSync Desktop**.
3. No menu lateral, acerte em **APIs e Serviços > Biblioteca**.
4. Procure por **Google Drive API** e clique em **Ativar** (*Enable*).

### 2.2. Configurar a Tela de Consentimento OAuth (OAuth Consent Screen)
1. Acesse **APIs e Serviços > Tela de consentimento OAuth**.
2. Selecione o tipo de usuário: **Externo** (*External*).
3. Preencha as informações do aplicativo:
   - **Nome do app**: `BrisaSync`
   - **E-mail de suporte do usuário**: Seu e-mail ou lista comunitária do projeto.
   - **Logotipo do app**: Utilize o ícone oficial `resources/icons/master/brisasync_512.png`.
   - **Página inicial do aplicativo**: URL do repositório GitHub do projeto.
4. Na etapa **Escopos** (*Scopes*), adicione:
   - `https://www.googleapis.com/auth/drive` (Escopo restrito para criação e sincronização de arquivos e pastas no Drive).
   - `https://www.googleapis.com/auth/userinfo.email` e `openid` (Para identificar o e-mail conectado na interface).

### 2.3. Criar a Credencial OAuth 2.0 (Desktop App)
1. Acesse **APIs e Serviços > Credenciais > Criar Credenciais > ID do cliente OAuth**.
2. Em **Tipo de aplicativo**, selecione estritamente: **Aplicativo para Computador** (*Desktop app*).
   > [!WARNING]
   > Não escolha "Aplicativo da Web". O BrisaSync rejeitará clientes com formato Web por não suportarem o fluxo nativo loopback com PKCE S256.
3. Nomeie como: `BrisaSync Linux Client`.
4. Clique em **Criar** e em seguida baixe o arquivo JSON gerado.

---

## 3. Estado de Publicação: "Em Teste" vs "Em Produção" (Verificação Google)

No Google Cloud Console, todo aplicativo inicia no status **Em Teste** (*Testing*):

### 3.1. Modo de Teste (*Testing*)
- **Limitação**: Apenas contas de e-mail cadastradas manualmente na lista de **Usuários de Teste** (*Test users*) — até o limite de 100 contas — conseguirão autorizar o login.
- Contas não listadas receberão erro `403: access_denied` (*User not listed as test user*).
- **Adequado para**: Testes internos de pré-lançamento entre mantenedores e colaboradores.

### 3.2. Modo de Produção (*In Production*) e Verificação de Escopo Restrito
- Para que **qualquer usuário final** possa instalar e usar o BrisaSync sem mensagens de bloqueio:
  1. No painel de consentimento OAuth, clique em **Publicar Aplicativo** (*Publish App*).
  2. Submeta o aplicativo ao processo de verificação de aplicativos da Google (*Google App Verification*):
     - Forneça uma Política de Privacidade (pública no repositório GitHub).
     - Grave um vídeo curto demonstrando o fluxo da aplicação (conforme exigido pela Google para o escopo `drive`).
     - Explique por que o escopo `https://www.googleapis.com/auth/drive` é necessário (sincronização bidirecional offline de pastas selecionadas pelo usuário).
  3. Após a aprovação da Google, o aplicativo é considerado verificado e não exibirá a tela de aviso *"O Google não verificou este app"*.

---

## 4. Empacotamento do Cliente na Distribuição Oficial

Quando o mantenedor tiver o JSON oficial do cliente desktop:

1. Salve o arquivo em:
   `src/brisasync/resources/oauth/google_oauth_client.json`
2. O script de compilação `packaging/build_packages.sh` ou o `PKGBUILD` instalará o arquivo no caminho padrão do sistema:
   `/usr/share/brisasync/google_oauth_client.json` (permissões `0644`).
3. O código do BrisaSync (`OAuthClientConfig.load_available()`) detectará automaticamente esse arquivo no primeiro uso:
   - O assistente inicial na aba **Início** exibirá diretamente o botão `"Conectar Conta Google"`.
   - O usuário clica no botão, autoriza no navegador padrão e conclui a configuração sem nenhum arquivo manual.

---

## 5. Impedimentos Restantes para a Primeira Versão Pública

1. **Criação do Projeto Oficial de Produção pelo Mantenedor**: Depende de decisão externa e conta administradora do projeto no Google Cloud Console.
2. **Submissão à Verificação de Marca e Escopo**: Processo de análise da Google LLC para remover a limitação de usuários de teste.
3. **Inclusão do JSON Oficial no Build**: Uma vez gerado o JSON pelo mantenedor, basta compilar o pacote com o cliente integrado.


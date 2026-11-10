# Configuração do Cliente Google OAuth 2.0 Desktop — BrisaSync (`docs/GOOGLE_OAUTH_SETUP.md`)

Este guia descreve exatamente o que o mantenedor ou testador precisa configurar no **Google Cloud Console** para conectar uma conta Google real ao **BrisaSync**, bem como a justificativa técnica dos escopos e os requisitos para distribuição pública futura.

> **Regra de Segurança**: Nunca envie arquivos `client_secret_*.json`, `access_token`, `refresh_token` ou senhas no chat nem comite esses arquivos no repositório Git.

---

## 1. Avaliação Técnica dos Escopos OAuth

O BrisaSync solicita os seguintes escopos durante a autorização OAuth 2.0:

1. **`https://www.googleapis.com/auth/drive`**:
   - **Por que não usar apenas `drive.file`?** O escopo `https://www.googleapis.com/auth/drive.file` concede acesso **exclusivamente** a arquivos que foram criados pelo próprio aplicativo ou selecionados individualmente por meio de um widget web *Google Picker* hospedado em domínio web verificado. Com `drive.file`, o aplicativo **não consegue** listar pastas preexistentes no "Meu Drive" do usuário nem baixar/sincronizar arquivos que o usuário tenha colocado dentro da pasta sincronizada pelo navegador web ou pelo celular.
   - Para um sincronizador bidirecional de pastas que deve enxergar pastas preexistentes e arquivos adicionados em qualquer dispositivo dentro da pasta escolhida, o escopo exigido pela Google Drive API v3 é `https://www.googleapis.com/auth/drive`.
2. **`openid` e `https://www.googleapis.com/auth/userinfo.email`**:
   - Utilizados exclusivamente para consultar e exibir na interface o endereço de e-mail real da conta autenticada antes de iniciar qualquer operação.

---

## 2. Passo a Passo no Google Cloud Console (Modo Desenvolvimento / Teste)

### Passo 1 — Criar o Projeto e Ativar a API
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/).
2. Crie um novo projeto (ex.: `BrisaSync-Dev`).
3. Em **APIs & Services > Library** (*Biblioteca*), pesquise por **Google Drive API** e clique em **Enable** (*Ativar*).

### Passo 2 — Configurar a Tela de Consentimento OAuth (*OAuth consent screen*)
1. Acesse **APIs & Services > OAuth consent screen**.
2. Selecione **External** (*Externo*) e clique em **Create**.
3. Preencha:
   - **App name**: `BrisaSync (Dev)` (nunca utilize nomes que sugiram produto oficial do Google).
   - **User support email** e **Developer contact information**: seu e-mail de mantenedor.
4. Na etapa **Scopes** (*Escopos*), clique em **Add or Remove Scopes** e adicione:
   - `https://www.googleapis.com/auth/drive`
   - `https://www.googleapis.com/auth/userinfo.email`
   - `openid`
5. Na etapa **Test users** (*Usuários de teste*):
   - Clique em **+ Add Users** e adicione o endereço de e-mail da **conta Google dedicada a testes** que você usará no BrisaSync.
   - Enquanto o aplicativo estiver com *Publishing status: Testing*, apenas os e-mails listados em *Test users* poderão concluir o login no navegador.

### Passo 3 — Criar a Credencial do Tipo Aplicativo Desktop (*Desktop app*)
1. Acesse **APIs & Services > Credentials** (*Credenciais*).
2. Clique em **+ Create Credentials > OAuth client ID**.
3. Em **Application type** (*Tipo de aplicativo*), selecione obrigatoriamente **Desktop app** (*Aplicativo para computador*).
   - *Nota*: O BrisaSync valida o JSON e rejeita credenciais do tipo *Web application*.
4. Dê um nome (ex.: `BrisaSync Linux Desktop`) e clique em **Create**.
5. Clique em **Download JSON** e salve o arquivo em:
   ```text
   ~/.config/brisasync/google_oauth_client.json
   ```
   (com permissão restrita: `chmod 600 ~/.config/brisasync/google_oauth_client.json`), ou selecione-o diretamente pelo botão **"Selecionar JSON..."** na janela do BrisaSync.

---

## 3. Como Executar o Primeiro Fluxo Real com Pasta de Testes

1. Abra o BrisaSync (`.venv/bin/brisasync`).
2. Na seção **1. Conta Google**, confira o caminho do arquivo JSON do cliente OAuth e clique em **"Conectar Conta Google"**.
3. O navegador padrão abrirá com o desafio **PKCE (`S256`)** e listener loopback local (`127.0.0.1:<porta_efêmera>`). Autorize a conta de testes.
4. Após a confirmação, a interface mostrará `[CONECTADA] <seu-email-de-teste>` e salvará os tokens no Cofre de Segredos da sessão (`secret-tool` / `kwallet`).
5. Na seção **2. Pasta Remota Dedicada a Testes**, digite um nome dedicado (ex.: `BrisaSync-Teste`) e clique em **"Criar Pasta de Teste"** (ou clique em **"Listar Pastas do Drive"** para selecionar uma pasta de testes existente pelo seu **ID**).
6. Na seção **3. Configuração da Pasta Local Dedicada**, escolha uma **pasta local vazia** (ex.: `~/BrisaSyncTeste`) e clique em **"Salvar e Validar Pasta"**.
7. Confira o resumo em **4. Conferência de Destinos** e clique em **"Sincronizar Agora"**.

---

## 4. Exigências para Futura Distribuição Pública

Para publicar o aplicativo fora do modo *Testing* (*In production*) com um `client_id` compartilhado pelo projeto:
1. **Verificação de Marca e Domínio**: Site público do projeto Open Source com Política de Privacidade clara explicando que o BrisaSync roda localmente na máquina do usuário e não coleta nem transmite dados para servidores de terceiros.
2. **Verificação de Escopo Restrito (`drive`)**: Como `https://www.googleapis.com/auth/drive` é classificado pelo Google como *Restricted Scope*, a publicação para usuários gerais exige revisão de segurança do Google (incluindo vídeo demonstrativo do fluxo OAuth PKCE e avaliação de segurança CASA Tier 2).
3. **Alternativa "Bring Your Own Client ID" (BYOC)**: Assim como o próprio `rclone` recomenda oficialmente, o BrisaSync permite que qualquer usuário ou organização carregue seu próprio arquivo `google_oauth_client.json` Desktop criado em seu projeto pessoal do Google Cloud Console.


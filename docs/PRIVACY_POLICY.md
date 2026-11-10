# Política de Privacidade — BrisaSync

**Última atualização**: 4 de novembro de 2026  
**Versão de Referência**: BrisaSync v0.1.21 (Release Candidate)  
**Mantenedor**: Fábio Agreles Bezerra  
**E-mail de Suporte ao Usuário**: [fabioagreles@gmail.com](mailto:fabioagreles@gmail.com)  
**Domínio Oficial**: `brisasync.com.br`  
**Página Oficial (Publicação Pendente)**: [https://brisasync.com.br/](https://brisasync.com.br/)  
**URL da Política de Privacidade (Publicação Pendente)**: [https://brisasync.com.br/privacy/](https://brisasync.com.br/privacy/)  
**Repositório Oficial**: [https://github.com/brisasync/brisasync](https://github.com/brisasync/brisasync)  

> [!NOTE]
> As páginas sob o domínio `brisasync.com.br` encontram-se atualmente com **publicação pendente** até que a configuração de zona DNS, hospedagem web com certificado TLS/HTTPS e a verificação de propriedade no Google Search Console sejam concluídas pelo mantenedor. O presente texto constitui a versão integral e oficial mantida no repositório do projeto.

---

## 1. Visão Geral e Princípios Fundamentais

O **BrisaSync** é um aplicativo desktop de código aberto (*open-source*) para distribuições Linux projetado para permitir a sincronização bidirecional e backup local entre pastas do computador pessoal do usuário e o **Google Drive**.

A privacidade e a soberania dos dados do usuário são princípios centrais do BrisaSync:
- O BrisaSync opera como uma **aplicação cliente pura** (*client-side native application*).
- **Não operamos servidores intermediários, nuvens de terceiros ou serviços de backend próprios**.
- Toda transferência de dados e autenticação ocorre diretamente entre a estação de trabalho do usuário e os serviços oficiais da Google LLC.
- O aplicativo não inclui qualquer ferramenta de telemetria, rastreamento analítico, publicidade ou coleta oculta de informações.

---

## 2. Comunicações de Rede e Arquitetura de Conexões

O BrisaSync realiza exclusivamente as seguintes interações de rede:

### 2.1 Comunicações Externas via HTTPS
Todas as comunicações com a internet são direcionadas exclusivamente aos endpoints oficiais de API da Google, utilizando conexões seguras criptografadas por TLS (**HTTPS**):

1. **Autenticação e Consentimento**:
   - `https://accounts.google.com/o/oauth2/v2/auth`: Carregado no navegador web padrão do usuário para permitir o login direto na conta Google e a aprovação das permissões de acesso.
2. **Obtenção e Atualização de Tokens**:
   - `https://oauth2.googleapis.com/token`: Requisições diretas de troca e renovação de credenciais OAuth 2.0 (código de autorização e *refresh token*).
   - `https://oauth2.googleapis.com/revoke`: Revogação voluntária de tokens ao desconectar a conta.
3. **Identificação do Perfil Básico**:
   - `https://www.googleapis.com/oauth2/v3/userinfo`: Requisição para obtenção do e-mail e nome público associados à conta para exibição na interface local.
4. **Operações de Arquivos e Metadados do Google Drive**:
   - Endpoints da Google Drive API v3 (executados pelo motor de sincronização integrado `rclone` sob canal HTTPS) para verificação de alterações, upload, download e reconciliação bidirecional das pastas e arquivos configurados pelo usuário.

### 2.2 Callback Local HTTP em Loopback
Em estrita conformidade com a norma [RFC 8252 (OAuth 2.0 for Native Apps)](https://tools.ietf.org/html/rfc8252), durante o momento em que o usuário inicia a conexão com sua conta Google, o BrisaSync abre um ouvinte HTTP temporário e efêmero na interface de loopback:
- **Endereço**: `http://127.0.0.1:<porta>/callback` (com porta atribuída dinamicamente pelo sistema operacional).
- **Função**: Receber de forma pontual o código de autorização redirecionado pelo navegador web após a autorização do usuário na página da Google.
- **Isolamento**: O servidor local vincula-se exclusivamente à interface `127.0.0.1` (não acessível pela rede local ou externa) e é imediatamente destruído e encerrado assim que o callback é processado ou quando ocorre tempo limite (*timeout*).

### 2.3 Ausência de Telemetria e Subprocessos
A verificação estrita do código-fonte, subprocessos locais e dependências do BrisaSync confirma:
- **Zero Telemetria**: Nenhum dado analítico, métrica de uso, registro de falhas (*crash reports*) ou identificador de dispositivo é enviado a desenvolvedores ou terceiros.
- **Subprocessos Restritos ao Ambiente Local**: Os subprocessos invocados pelo BrisaSync restringem-se a ferramentas do sistema operacional hospedeiro:
  - O motor `rclone` local (`/usr/lib/brisasync/bin/rclone`) para transferência de arquivos via HTTPS diretamente com o Google Drive;
  - Ferramentas de cofre da sessão (`libsecret`, `secret-tool`, `kwallet-query` ou chamadas D-Bus do sistema);
  - Gerenciador `systemd --user` para automação do serviço em segundo plano;
  - Utilitários de notificação (`notify-send` / FreeDesktop Notifications) e abertura de navegador padrão (`xdg-open`).

---

## 3. Armazenamento de Dados na Estação do Usuário

O BrisaSync armazena informações estritamente locais no computador do usuário, necessárias para o funcionamento da aplicação:

1. **Chaveiro Criptografado da Sessão (*System Keyring*)**:
   - Os tokens de acesso (*access token*), tokens de renovação (*refresh token*) e a chave de ofuscação/cifragem da ponte rclone (`RCLONE_ENCRYPT_V0:`) são gravados com segurança no serviço de cofre ativo do usuário (**GNOME Keyring** ou **KWallet**).
   - O BrisaSync não salva tokens de autenticação em texto puro no disco rígido.
2. **Memória Temporária Cifrada (`/dev/shm`)**:
   - A configuração transitória necessária para a execução pontual dos ciclos do motor rclone é montada em arquivo efêmero em memória volátil (`/dev/shm`), protegido com permissões restritas de leitura/escrita exclusivas do usuário (`0600`) e cifrado com a chave da sessão.
   - O arquivo em `/dev/shm` é sumariamente excluído ao término de cada ciclo de sincronização ou encerramento do processo.
3. **Banco de Dados Local SQLite**:
   - Localizado em `~/.local/share/brisasync/brisasync.db`.
   - Armazena metadados de configuração dos pares de sincronização (caminho local, caminho no Google Drive, frequência de sincronização), histórico de execuções anteriores, registro de conflitos e lista recente de eventos de sincronização.
4. **Backups e Versões Locais**:
   - Caso o usuário utilize as opções de retenção de versões anteriores para proteger-se de sobreescritas acidentais, os arquivos modificados ou deletados são preservados na pasta de backup local (por padrão em `~/.local/share/brisasync/backups/` ou local personalizado).
5. **Preferências da Interface**:
   - Localizadas em `~/.config/brisasync/settings.json`.
   - Armazena opções de interface (tema visual, modo de contraste da bandeja, inicialização minimizada, etc.).

---

## 4. Compromisso de Uso Limitado do Google (*Limited Use Disclosure*)

O BrisaSync cumpre integralmente a Política de Dados do Usuário dos Serviços de API do Google (*Google API Services User Data Policy*), assumindo o compromisso formal abaixo:

> **O uso e a transferência pelo BrisaSync para qualquer outro aplicativo de informações recebidas das APIs do Google obedecerão à [Política de Dados do Usuário dos Serviços de API do Google](https://developers.google.com/terms/api-services-user-data-policy), incluindo os requisitos de Uso Limitado (*Limited Use*).**

Em consonância com as exigências de Uso Limitado para escopos restritos:
1. **Finalidade Estrita**: O acesso aos dados do Google Drive é utilizado exclusivamente para fornecer a funcionalidade explícita de backup e sincronização de arquivos para a máquina local do usuário.
2. **Não Transferência de Dados**: Os dados obtidos das APIs do Google **nunca** são transmitidos a servidores externos, desenvolvedores, empresas parceiras ou serviços terceiros.
3. **Não Utilização para Publicidade**: Dados de arquivos e e-mail do usuário **nunca** são usados para veiculação de anúncios, marketing direcionado, rastreamento de perfil ou venda para corretores de dados (*data brokers*).
4. **Não Utilização para Treinamento de Inteligência Artificial**: Os dados de arquivos do usuário **não** são utilizados para treinar modelos de inteligência artificial ou aprendizagem de máquina (*machine learning*).
5. **Sem Acesso Humano aos Dados**: Nenhum ser humano tem acesso aos arquivos do usuário, às credenciais ou aos dados de sincronização. Toda a leitura, gravação e cálculo de diferenças ocorre de forma automatizada e confidencial dentro do dispositivo do próprio usuário.

---

## 5. Controle do Usuário e Exclusão de Dados

O usuário detém controle total sobre suas informações e pode interromper o acesso a qualquer instante:

1. **Desconectar a Conta pelo Aplicativo**:
   - Ao acessar o menu de opções do BrisaSync e clicar em "Desconectar conta", o aplicativo solicita a revogação do token diretamente aos servidores da Google (`https://oauth2.googleapis.com/revoke`), apaga os tokens gravados no chaveiro do sistema e destrói quaisquer credenciais ativas em memória.
2. **Revogação pelo Painel de Segurança do Google**:
   - O usuário pode revogar as permissões de acesso do BrisaSync a qualquer momento através do painel de segurança de sua conta Google:  
     [https://myaccount.google.com/permissions](https://myaccount.google.com/permissions).
3. **Remoção de Arquivos e Históricos Locais**:
   - Para remover todos os rastros de metadados e bancos de dados locais mantidos na máquina, basta excluir os diretórios:
     ```bash
     rm -rf ~/.local/share/brisasync
     rm -rf ~/.config/brisasync
     ```
   - Os arquivos pessoais mantidos na pasta local sincronizada e no Google Drive continuam íntegros e sob controle total do usuário.

---

## 6. Alterações nesta Política

Por ser um projeto de código aberto, quaisquer alterações futuras nesta Política de Privacidade serão documentadas no histórico do repositório público do projeto e disponibilizadas nas notas de lançamento oficiais.

---

## 7. Contato e Responsabilidade

Em caso de dúvidas sobre esta Política de Privacidade, solicitações de suporte, questões de segurança ou auditoria do código-fonte:

- **Desenvolvedor e Mantenedor**: Fábio Agreles Bezerra
- **E-mail de Suporte ao Usuário**: [fabioagreles@gmail.com](mailto:fabioagreles@gmail.com)
- **Página Oficial (Publicação Pendente)**: [https://brisasync.com.br/](https://brisasync.com.br/)
- **Repositório do Código-Fonte e Rastreamento de Questões**: [https://github.com/brisasync/brisasync](https://github.com/brisasync/brisasync)
- **Licença do Software**: GNU General Public License v3.0 or later (GPL-3.0-or-later)


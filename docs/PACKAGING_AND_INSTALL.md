# BrisaSync — Guia de Empacotamento, Instalação e Testes Isolados

Este documento detalha o processo de empacotamento, instalação, atualização e desinstalação do **BrisaSync 0.1.6** (e históricos 0.1.5, 0.1.4, 0.1.3, 0.1.2, 0.1.1 e 0.1.0), artefatos empacotados para testes locais.

> [!NOTE]
> Esta entrega é um **pacote de teste para validação local**, não uma distribuição pública estável em repositórios oficiais ou lojas de aplicativos.

---

## 1. Identificação do Sistema-Alvo e Arquitetura

O pacote nativo foi gerado para distribuições Linux baseadas em **Arch Linux / ALPM** (ex.: BigLinux, Manjaro, Arch Linux) com arquitetura **x86_64**.

- **Python Runtime**: Python `>= 3.14` (desenvolvido e testado em 3.14.7)
- **Interface Gráfica**: PySide6 / Qt6 `>= 6.11`
- **Sessão do Usuário**: Wayland ou X11 (KDE Plasma, GNOME, etc.)
- **Cofre de Credenciais**: Freedesktop Secret Service (`secret-tool` / `libsecret`, KWallet)
- **Notificações**: Notificações nativas via Desktop Portal / `libnotify` (`notify-send`)

---

## 2. Artefatos Gerados em `dist/`

Os pacotes foram gerados via `./packaging/build_packages.sh` e validados:

### Versão Atual (0.1.6 — Rodada 14 — Nova Interface com Barra Lateral, Painel em Cartões e Hero Status Banner)
| Arquivo | Tamanho | SHA-256 Sum | Finalidade |
| :--- | :--- | :--- | :--- |
| `brisasync-0.1.6-1-x86_64.pkg.tar.zst` | 31.9 MB | `5f1dca53c60ffe46bb7b113e80b66b87db08ae5cb6711431fcdf8e46d7ce481e` | Pacote instalável principal ALPM (interface moderna v0.1.6) |
| `brisasync-0.1.6-2-x86_64.pkg.tar.zst` | 31.9 MB | `dce9ade23b3ebe0bbfd67b0e74677c17282f61b23e85bca7d7e6a9df8869b611` | Pacote para teste de atualização (upgrade test) |
| `brisasync-0.1.6-py3-none-any.whl` | 2.29 MB | `853f299022192d4b146d8b055c794938490dca5df27ace5cdd57395aec2d5862` | Distribuição Python Wheel padrão com recursos |
| `brisasync-0.1.6.tar.gz` | 2.31 MB | `b79d4bdf1fe9de7c868c444573b68fa762493bc25a36df9868a981887e700f93` | Arquivo fonte (sdist) utilizado pelo PKGBUILD |

### Versões Históricas Preservadas (0.1.5, 0.1.4, 0.1.3, 0.1.2, 0.1.1 e 0.1.0)
| Arquivo | Tamanho | SHA-256 Sum | Finalidade |
| :--- | :--- | :--- | :--- |
| `brisasync-0.1.5-1-x86_64.pkg.tar.zst` | 31.9 MB | `5b97226c4b02fc0b1f63624150dce72a039a4437726d1dfc6de714bf12b6578f` | Pacote histórico Rodada 13 (reorganização visual) |
| `brisasync-0.1.5-2-x86_64.pkg.tar.zst` | 31.9 MB | `64d50c202bd03d80d4a2f95c7d9a216113a7ac52dc159d624854603350053a5b` | Pacote histórico upgrade Rodada 13 |
| `brisasync-0.1.5-py3-none-any.whl` | 2.29 MB | `a13839897a20e3ea82aa37740a943b0808310a1770b5dbefc495f4b093cff8a4` | Wheel Python histórico Rodada 13 |
| `brisasync-0.1.5.tar.gz` | 2.31 MB | `7d9bc60158a5cef6da76a3a2ecec323820aa1681a1ca610209e85581d3d2d7c2` | Código-fonte sdist Rodada 13 |
| `brisasync-0.1.4-1-x86_64.pkg.tar.zst` | 31.9 MB | `d0e8a9f5121298a1f90f9a6d3bb9f0012b00eeef0db2394b4daca4f570d6fe91` | Pacote histórico Rodada 12 (correção de abertura) |
| `brisasync-0.1.4-2-x86_64.pkg.tar.zst` | 31.9 MB | `fcb1d98732f44f30367d8a0e280974a452d8efe92bc9a4f6d17a3fec8af403a6` | Pacote histórico upgrade Rodada 12 |
| `brisasync-0.1.4-py3-none-any.whl` | 2.29 MB | `dbe6170a31721ee533040ec78537e9dd6ce841ffdb15078285d2f55393a1acb7` | Wheel Python histórico Rodada 12 |
| `brisasync-0.1.4.tar.gz` | 2.31 MB | `fd6d747dfe306bd7c1d36a548c99c71a6858cbf03c744cf6162d84fd803009db` | Código-fonte sdist Rodada 12 |
| `brisasync-0.1.3-1-x86_64.pkg.tar.zst` | 31.9 MB | `d774290c5d00c5c80163be2abb6d99dc3f20e674dc10beb4741747f3c95ece66` | Pacote histórico Rodada 10 |
| `brisasync-0.1.3-2-x86_64.pkg.tar.zst` | 31.9 MB | `51fcfe1ee8dd66bfe0d43f44aded63d7e554db9944a0ee8638753e34c5e0b4a4` | Pacote histórico upgrade Rodada 10 |
| `brisasync-0.1.3-py3-none-any.whl` | 2.29 MB | `4c7fcb62d0efe73d1586ab3cb02bbf2ce1c05d8327f0f495c6b24aeb6c263eb9` | Wheel Python histórico Rodada 10 |
| `brisasync-0.1.3.tar.gz` | 2.31 MB | `47bb0a960ce3fda7b550d7d14737576758402b90fe140e9574d03f72cd1d2642` | Código-fonte sdist Rodada 10 |
| `brisasync-0.1.2-1-x86_64.pkg.tar.zst` | 31.9 MB | `984c8b7b5a23c5a0ceda166e320b9783530a2db32a29e1f8427af2f014f4080e` | Pacote histórico Rodada 9 |
| `brisasync-0.1.2-2-x86_64.pkg.tar.zst` | 31.9 MB | `06f797c92949a69827cebf4be4237b3b37b434352faff6c0aa7b11f0551ef5e5` | Pacote histórico upgrade Rodada 9 |
| `brisasync-0.1.2-py3-none-any.whl` | 2.29 MB | `9a7658cb576aa7ebd130f78896593c4c4aee949983e7db0637ea82109ecb557e` | Wheel Python histórico Rodada 9 |
| `brisasync-0.1.2.tar.gz` | 2.31 MB | `3dc2e02e510a376c8fa8baf8319e6aca839c8ef54e92f5e21e1650744cf9f6b0` | Código-fonte sdist Rodada 9 |
| `brisasync-0.1.1-1-x86_64.pkg.tar.zst` | 31.9 MB | `446d10c5664883398bf4fe82a08c07406ad3c2b9c9270a9056bab8acdbf29cea` | Pacote histórico Rodada 8 |
| `brisasync-0.1.1-2-x86_64.pkg.tar.zst` | 31.9 MB | `6d50e59eaa0c87c33f8d3de3bbf4d43803bcd0b3f53697484e07138559f15da6` | Pacote histórico upgrade Rodada 8 |
| `brisasync-0.1.1-py3-none-any.whl` | 2.29 MB | `36de7f8530ebad081aa0bb70ca3f243d5f725a7eb7e5f6c758b863d76cf467f2` | Wheel Python histórico Rodada 8 |
| `brisasync-0.1.1.tar.gz` | 2.31 MB | `c2c12426331713a50aa45f5c435df004dfdfe10ab63f3a5de99f008d9cdeebbf` | Código-fonte sdist Rodada 8 |
| `brisasync-0.1.0-1-x86_64.pkg.tar.zst` | 31.9 MB | `5e98840c9a60e17f9ed2343d283e453bc9993caa1acedb6bc44febc7c7dcf157` | Pacote histórico inicial ALPM |
| `brisasync-0.1.0-2-x86_64.pkg.tar.zst` | 31.9 MB | `ddcc5ca5259298fe8628d7c4f5ddd427ee638456bb64796addda5536eaf64410` | Pacote histórico de teste de atualização |
| `brisasync-0.1.0-py3-none-any.whl` | 2.29 MB | `9374fc53ea8bea3092b13ed544d696d08b4c569fa639d77a92a709e4c170ab1e` | Distribuição Python Wheel 0.1.0 |
| `brisasync-0.1.0.tar.gz` | 2.31 MB | `3269c4543bc7215050507082091e66a3149a96f3e60985e668ca06dd1f0fb745` | Arquivo fonte original 0.1.0 |

---

## 3. Estrutura de Arquivos Instalados pelo Pacote

O pacote instala exclusivamente em locais padrão do sistema, sem qualquer dependência da pasta de desenvolvimento:

```text
/usr/bin/brisasync                          # Wrapper executável principal
/usr/lib/brisasync/bin/rclone               # Binário verificado rclone v1.75.2 (linux/amd64)
/usr/lib/python3.14/site-packages/brisasync # Pacote Python instalado
/usr/lib/systemd/user/brisasync.service      # Unit systemd --user de referência
/usr/share/applications/brisasync.desktop   # Lançador do menu de aplicativos
/usr/share/brisasync/google_oauth_client.json # Cliente OAuth Desktop oficial do projeto (higienizado)
/usr/share/icons/hicolor/.../brisasync.png  # Ícones coloridos em 11 resoluções (16px a 1024px)
/usr/share/icons/hicolor/scalable/...svg    # Ícone simbólico escalável
/usr/share/licenses/brisasync/LICENSE       # Licença GNU GPL-3.0-or-later
/usr/share/licenses/brisasync/LICENSE-rclone.txt # Licença MIT do rclone
/usr/share/licenses/brisasync/THIRD_PARTY_NOTICES.md # Avisos de terceiros
/usr/share/doc/brisasync/README.md          # Documentação do projeto
```

---

## 4. Instruções de Instalação, Uso e Remoção

### 4.1 Instalação do Pacote ALPM (`.pkg.tar.zst`)
Para instalar no sistema operacional hospedeiro:

```bash
sudo pacman -U /home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.6-1-x86_64.pkg.tar.zst
```

### 4.2 Execução
- **Pelo Menu de Aplicativos**: Procure por **BrisaSync** no lançador (KDE Kickoff, GNOME Dash, etc.).
- **Pelo Terminal**:
  ```bash
  # Diagnósticos prévios
  brisasync --diagnose

  # Abrir a interface gráfica (com bandeja se disponível)
  brisasync

  # Abrir forçando modo sem bandeja
  brisasync --no-tray

  # Iniciar apenas o serviço da sessão (usado pelo systemd)
  brisasync --service
  ```

### 4.3 Atualização (Upgrade)
Para atualizar da versão `0.1.6-1` para `0.1.6-2`:

```bash
sudo pacman -U /home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.6-2-x86_64.pkg.tar.zst
```
> [!IMPORTANT]
> A atualização **preserva integralmente** todos os dados do usuário em `~/.local/share/brisasync/` (banco de dados SQLite) e as pastas sincronizadas.

### 4.4 Remoção (Uninstall)
Para desinstalar o pacote:

```bash
sudo pacman -R brisasync
```
> [!NOTE]
> A remoção do pacote remove apenas os arquivos instalados em `/usr/`. Arquivos do usuário em `$HOME`, configurações e o histórico local **não são apagados**.

---

## 5. Cliente OAuth Google Oficial Empacotado (Rodadas 9 e 10) vs Override para Forks/Testes

O pacote **BrisaSync 0.1.4** (e históricos 0.1.3 e 0.1.2) embute oficialmente os metadados públicos do cliente OAuth Desktop do projeto em:
`/usr/share/brisasync/google_oauth_client.json` (permissão `0644`).

- **Experiência do Usuário Comum**: Ao abrir o aplicativo pela primeira vez, o assistente inicial detecta automaticamente o cliente embutido, exibindo **"1. Conectar conta Google"** e o botão **"Conectar Conta Google"**. O usuário não precisa obter ou selecionar manualmente nenhum arquivo JSON para autorizar no navegador.
- **Modo do Cliente no Google Cloud Platform**: O cliente oficial permanece registrado sob o status **Testing** no Google Cloud Console. Isso significa que apenas contas explicitamente adicionadas à lista de *Test users* (como `fabioagreles@gmail.com`) têm autorização para autenticar. **Não se trata de liberação pública geral nem aprovação de verificação do Google**.
- **Preservação de Override para Desenvolvedores e Forks**: Caso o usuário queira utilizar suas próprias credenciais OAuth independentes:
  1. Pode salvar seu arquivo JSON em `~/.config/brisasync/google_oauth_client.json` (prioridade sobre o cliente do sistema).
  2. Pode especificar o caminho em **Configurações > Seção Avançada (Desenvolvimento e Forks)**.
  3. Pode definir a variável de ambiente `BRISASYNC_GOOGLE_CLIENT_CONFIG_FILE`.
- Consulte o guia completo para o mantenedor em [docs/OAUTH_DISTRIBUTION_GUIDE.md](file:///home/agreles/Aplicativos/BrisaSync/docs/OAUTH_DISTRIBUTION_GUIDE.md) para detalhes de publicação pública futura.

---

## 6. Procedimento de Validação em Ambiente Isolado (Reprodução)

A suíte automatizada `tests/test_installed_package_verification.py` valida o artefato de forma totalmente independente:

1. **Isolamento de Checkout**: Utiliza `bwrap` (Bubblewrap) montando um `--tmpfs` sobre o diretório de desenvolvimento, tornando impossível qualquer importação da árvore de fontes ou do `.venv`.
2. **HOME Limpo**: Utiliza um diretório temporário isolado como `$HOME`, desprovido de configurações prévias, rclone particular em `~/.local/bin` ou tokens antigos.
3. **Instalação ALPM em Fakeroot**: Executa `fakeroot pacman -r <ROOT> -U ...` para testar integridade de pacotes, arquivos empacotados, verificação de conflitos, atualização de versão e remoção limpa.

Para reproduzir os testes automatizados da suíte:
```bash
.venv/bin/pytest tests/test_installed_package_verification.py -v
```

Para executar o roteiro de testes em máquina virtual ou contêiner limpo com resolução real de dependências, consulte o playbook em [docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md](file:///home/agreles/Aplicativos/BrisaSync/docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md).

---

## 7. Conclusões e Limites da Validação de Empacotamento

Com base nas verificações das Rodadas 6 e 7, registram-se os seguintes limites objetivos da validação:

1. **Testes com `--nodeps` / Root Isolado**:
   - As verificações com `--nodeps` (ou instalação via `fakeroot pacman -r` sem banco de sincronização oficial configurado) atestam rigorosamente a **integridade interna dos arquivos, hierarquia de diretórios, permissões e isolamento do runtime**.
   - **Não validam a resolução de dependências no gerenciador de pacotes**: não comprovam que os repositórios oficiais da distribuição conseguirão resolver automaticamente pacotes como `python>=3.14` e `pyside6` sem intervenção manual do usuário.
2. **Diferença entre Sandbox no Host e Instalação Limpa de SO**:
   - O ambiente de testes com Bubblewrap (`bwrap`) isola a árvore de código e o `$HOME`, mas compartilha a `/usr` do host (utilizando bibliotecas dinâmicas C/C++, Qt e Python já presentes no sistema do desenvolvedor).
   - Um sandbox local no host **não substitui** uma validação em instalação limpa do sistema operacional (clean-slate OS install em VM ou contêiner zerado do Arch Linux / Manjaro / BigLinux).
3. **Status do Artefato**:
   - Os pacotes gerados em `dist/` são **artefatos de teste do próprio projeto BrisaSync**.
   - A geração destes arquivos no formato ALPM **não implica nem sugere aprovação, homologação ou distribuição oficial** por parte das equipes do Arch Linux, Manjaro ou BigLinux.
4. **Login e Fluxo Inicial**:
   - Conforme destacado no item 5, o cliente OAuth Desktop do projeto está devidamente embutido em `/usr/share/brisasync/google_oauth_client.json`, permitindo autorização direta no navegador sem JSON manual para contas registradas como usuárias de teste (ex: `fabioagreles@gmail.com`). Para liberação geral ao público sem tela de consentimento de desenvolvimento do Google, permanece pendente o processo externo de verificação OAuth pelo Google Trust & Safety.


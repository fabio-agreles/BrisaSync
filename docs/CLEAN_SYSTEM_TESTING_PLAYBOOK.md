# Playbook de Testes em Sistema Operacional Limpo (Clean-Slate OS Testing)

Este guia estabelece os requisitos técnicos, distinções de ambiente e o roteiro reproduzível para testar a instalação, resolução de dependências e execução do **BrisaSync** em um sistema operacional limpo.

---

## 1. Distinção Crucial de Ambientes de Teste

| Aspecto | Sandbox no Host (`bwrap` / Bubblewrap) | Contêiner Headless (`docker`/`podman`/`nspawn`) | Máquina Virtual com Sessão Desktop (KDE/GNOME) |
| :--- | :--- | :--- | :--- |
| **Isolamento de Diretórios** | Mascara checkout git e `$HOME`. | Sistema de arquivos zerado (`archlinux:base`). | Sistema operacional completo e independente. |
| **Compartilhamento de Bibliotecas** | **Sim**: herda `/usr/lib` e bibliotecas dinâmicas do host. | **Não**: usa apenas o que for instalado via repositório. | **Não**: SO 100% isolado. |
| **Resolução de Dependências** | Parcial (executa binários já resolvidos no host). | **Total**: testa resolução nativa pelo `pacman`. | **Total**: testa resolução nativa pelo `pacman`. |
| **Sessão Gráfica (X11/Wayland)** | Herda a sessão do host (se configurado). | **Ausente**: apenas modo texto/headless. | **Presente**: display server, compositor e shell. |
| **D-Bus da Sessão do Usuário** | Compartilhado com o usuário atual. | Ausente ou emulado artificialmente. | **Real**: `dbus-user-session` completo. |

---

## 2. Por que Certas Integrações Exigem uma Sessão Gráfica Real?

Um contêiner headless em CI (ou um chroot mínimo) **não é suficiente** para comprovar a experiência do usuário final, pois as seguintes integrações dependem de barramentos e subsistemas gráficos:

1. **Autenticação OAuth 2.0 no Navegador**:
   - O BrisaSync inicia um listener HTTP local em `127.0.0.1:<porta>` e invoca `xdg-open` / `QDesktopServices.openUrl()` para abrir o navegador padrão do usuário.
   - Sem display server ou navegador gráfico instalado na sessão, o fluxo não pode ser concluído de ponta a ponta.
2. **Cofre de Senhas da Sessão (`Secret Service` / `KWallet`)**:
   - `libsecret` e `kwallet` comunicam-se via D-Bus com o daemon de segredos (`org.freedesktop.secrets`). No primeiro acesso, o subsistema solicita a senha do chaveiro através de um prompt gráfico (polkit/pinentry).
   - Sem uma sessão gráfica de usuário autenticada no login pelo display manager (SDDM, GDM), o cofre permanece bloqueado.
3. **Bandeja do Sistema (`StatusNotifierItem` / AppIndicator)**:
   - A bandeja do Qt comunica-se com o compositor/painel via `org.freedesktop.StatusNotifierWatcher` no barramento D-Bus da sessão.
   - Em contêineres sem painel desktop, `QSystemTrayIcon.isSystemTrayAvailable()` retornará `False` (o BrisaSync funcionará normalmente no modo sem bandeja, mas o comportamento visual da bandeja não pode ser atestado).
4. **Notificações do Desktop (`org.freedesktop.Notifications`)**:
   - Notificações de conflitos e alertas dependem do daemon de notificações da sessão desktop para renderização visual.
5. **Autoinício na Sessão do Usuário (`systemd --user`)**:
   - A ativação automática ocorre vinculada a `graphical-session.target` ou `default.target` da sessão do usuário iniciada pelo PAM/systemd no login.

---

## 3. Roteiro Reproduzível para Validação em Sistema Limpo

### Fase 1: Validação de Resolução de Dependências em Contêiner Limpo (Headless)

Este teste comprova que o pacote ALPM instala sem `--nodeps` e que todos os pacotes necessários existem nos repositórios da distribuição:

```bash
# 1. Iniciar contêiner Arch Linux oficial limpo
podman run --rm -it -v ./dist:/dist:ro archlinux:base /bin/bash

# 2. Atualizar repositórios e instalar dependências básicas
pacman -Syu --noconfirm

# 3. Testar a instalação direta do pacote (SEM --nodeps!)
pacman -U --noconfirm /dist/brisasync-0.1.9-1-x86_64.pkg.tar.zst

# 4. Verificar se todas as dependências foram satisfeitas
pacman -Qi brisasync
which brisasync
which /usr/lib/brisasync/bin/rclone

# 5. Executar o CLI e o diagnóstico interno
brisasync --version
brisasync --help
brisasync --diagnose
```

**Resultado Comprovado da Fase 1 (Contêiner Headless Arch Linux)**:
- **Resolução de Dependências**: O `pacman -U` sem `--nodeps` resolveu e instalou com sucesso todas as dependências declaradas (`python`, `pyside6`, `libsecret`, `libnotify`, `hicolor-icon-theme`).
- **Versões Operacionais**: Python `3.14.8`, Qt/PySide6 `6.12.0`, SQLite `3.54.0` e `rclone v1.75.2` embutido operacional em `/usr/lib/brisasync/bin/rclone`.
- **Limitações Técnicas Inerentes**:
  - Sessão gráfica reportada como `DESCONHECIDA`.
  - Cofre inacessível (`VaultUnavailableError`) por ausência de `/etc/machine-id` e do barramento D-Bus da sessão de usuário no contêiner headless.
- **Ressalva de Homologação**: Aprovadas estritamente a resolução de dependências e a integridade CLI/rclone. Interface gráfica (GUI), autenticação OAuth via navegador, cofre de segredos da sessão, bandeja do sistema e autoinício (`systemd --user`) **não** foram declarados como testados neste ambiente headless.

---

## 4. Fase 2: Roteiro Objetivo para Homologação em VM com GNOME (ALPM)

Esta fase valida a experiência do usuário final em um ambiente desktop completo com **GNOME Shell**, utilizando uma distribuição compatível com o formato de pacote ALPM (**Arch Linux GNOME** ou **Manjaro GNOME**).

### 4.1 Recursos Necessários no Host

Antes de iniciar a criação da VM, certifique-se de que o computador hospedeiro dispõe dos seguintes recursos:

* **Processador**: Suporte a virtualização por hardware ativo no BIOS/UEFI (`AMD-V` ou `Intel VT-x`).
  *(No host atual: AMD-V ativado e módulos `kvm_amd` carregados)*.
* **Memória RAM Livre**: Mínimo de **4 GiB** dedicados à máquina virtual.
  *(No host atual: 31 GiB totais com ~22 GiB disponíveis)*.
* **Espaço em Disco**: Mínimo de **25 a 30 GiB** livres para o disco virtual dinâmico.
  *(No host atual: 79 GiB disponíveis no volume raiz `/`)*.
* **Hipervisor**: VirtualBox 7.2 (`/usr/sbin/VBoxManage`) já instalado no host, ou QEMU/KVM (`virt-manager`).

---

### 4.2 Preparação da Máquina Virtual

1. **Imagem de Instalação Recomendada**:
   - **Manjaro GNOME Oficial** (base Arch Linux / ALPM pronta para uso) ou **Arch Linux com perfil de instalação GNOME** (`archinstall` selecionando `profile: desktop -> gnome`).
2. **Configuração da VM no VirtualBox / QEMU**:
   - **Memória RAM**: 4096 MB (4 GiB).
   - **Processadores (vCPUs)**: 2 vCPUs.
   - **Disco Rígido**: 30 GiB (alocação dinâmica).
   - **Controlador Gráfico**: VMSVGA com aceleração 3D habilitada (se suportado).
   - **Rede**: Modo NAT (ou Bridge) para permitir acesso à Internet durante os testes OAuth.
3. **Transferência do Pacote para a VM**:
   Após instalar o sistema operacional na VM e configurar o usuário:
   ```bash
   # No host (substitua pelo IP da VM):
   scp dist/brisasync-0.1.9-1-x86_64.pkg.tar.zst usuario@<ip-da-vm>:~/
   ```

---

### 4.3 Roteiro de Testes Passo a Passo na VM GNOME

#### Teste 1: Instalação Limpa do Pacote Oficial
Na VM, abra o terminal do GNOME:
```bash
# Atualizar a base de pacotes da VM
sudo pacman -Syu

# Instalar o BrisaSync COM resolução total de dependências
sudo pacman -U ~/brisasync-0.1.9-1-x86_64.pkg.tar.zst

# Conferir metadados e integridade
pacman -Qi brisasync
brisasync --diagnose
```
*Critério de Aprovação*: Diagnóstico reporta `all_critical_ok: true`, detecta `XDG_CURRENT_DESKTOP=GNOME` e motor rclone operacional.

---

#### Teste 2: Operação no GNOME Padrão SEM Extensão de Bandeja
O GNOME Shell padrão não possui suporte nativo a ícones de bandeja do sistema (Systray/AppIndicator) sem extensões de terceiros.

1. **Abertura pelo Lançador**:
   - Pressione a tecla `Super` (Windows) para abrir a visão geral (*Activities/Dash*).
   - Digite `BrisaSync` e pressione Enter.
   - Verifique se a janela principal abre no centro da tela com proporção adequada (~820×600) e ícones nítidos.
2. **Comportamento Sem Bandeja**:
   - Feche a janela principal clicando no botão de fechar (X).
   - Como o GNOME puro não possui área de notificação clássica, confira que o BrisaSync detecta `isSystemTrayAvailable() == False` e:
     - **Não encerra** o serviço de sincronização em segundo plano.
     - **Não trava** nem gera erro de ponteiro D-Bus.
   - Abra o terminal da VM e verifique se o daemon continua ativo:
     ```bash
     pgrep -a -f brisasync
     ```
3. **Reabertura pelo Dash**:
   - Pressione `Super`, digite `BrisaSync` e abra novamente.
   - Comprove que a interface conecta instantaneamente ao serviço existente **sem duplicar o daemon**.

---

#### Teste 3: Autenticação OAuth em Navegador Web Real
1. Na janela do BrisaSync na VM, vá para a tela inicial ou *Ajustes*.
2. Clique em **"Conectar Conta Google"**.
3. O BrisaSync deve iniciar o servidor HTTP local em loopback (`127.0.0.1:<porta>`) e abrir automaticamente o navegador web padrão (Firefox/Chromium).
4. Conclua a autorização no Google: a página de sucesso local deve ser exibida e o BrisaSync deve transitar para o estado `[CONECTADA]`.
5. Comprove que os tokens OAuth foram salvos com segurança no **GNOME Keyring** (verificável via aplicativo `seahorse` / *Senhas e Chaves*).

---

#### Teste 4: Comportamento com Cofre Bloqueado (GNOME Keyring)
Este teste valida a proteção contra loops de autenticação e popups indesejados quando o cofre do sistema estiver trancado.

1. **Trancar o Chaveiro**:
   - No GNOME, abra o aplicativo **Senhas e Chaves** (`seahorse`).
   - Clique com o botão direito no chaveiro *Padrão* (ou *Login*) e selecione **Bloquear**.
   *(Alternativamente, altere temporariamente a senha do usuário sem atualizar o chaveiro de login, ou execute `pkill -STOP gnome-keyring-daemon`)*.
2. **Disparar ou Aguardar Ciclo do BrisaSync**:
   - No BrisaSync ou pelo terminal, verifique o estado do serviço:
     ```bash
     brisasync --diagnose
     ```
   - O daemon deve identificar que o cofre está inacessível (`VaultUnavailableError`) e entrar no estado **`STATE_ATTENTION_REQUIRED`** com a mensagem:
     *"Cofre da sessão bloqueado ou indisponível (...). Aguardando desbloqueio sem abrir navegador."*
   - **Critérios Cruciais de Aprovação**:
     - O BrisaSync **não abre popups** do navegador web solicitando novo login.
     - O agendador **não entra em loop** infinito de retentativas.
3. **Destrancar o Chaveiro**:
   - No aplicativo *Senhas e Chaves*, destranque o chaveiro fornecendo a senha.
   - Acione a sincronização (ou aguarde o próximo ciclo): o BrisaSync deve carregar os tokens automaticamente e retornar ao estado saudável `Tudo em dia` sem exigir intervenção no navegador.

---

#### Teste 5: Autoinício na Sessão GNOME (`systemd --user`)
1. Na aba **Ajustes** do BrisaSync, marque a opção:
   `[x] Iniciar automaticamente ao fazer login`
2. Encerre a sessão do GNOME (*Encerrar Sessão / Log Out*).
3. Faça login novamente no GNOME.
4. Antes de abrir qualquer janela, abra o terminal e confira:
   ```bash
   systemctl --user status brisasync.service
   pgrep -a -f brisasync
   ```
   *Resultado esperado*: O serviço `brisasync.service` deve estar ativo em segundo plano em conjunto com a sessão do GNOME.
5. Abra o BrisaSync pelo Dash e confirme que a janela se conecta ao daemon existente sem gerar processos duplicados.

---

#### Teste 6 (Opcional): Comportamento COM Extensão de Bandeja
1. Instale a extensão oficial de AppIndicator no GNOME:
   ```bash
   sudo pacman -S gnome-shell-extension-appindicator
   ```
2. Habilite a extensão via aplicativo *Extensões* do GNOME ou comando:
   ```bash
   gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
   ```
3. Abra o BrisaSync: o ícone simbólico de nuvem do BrisaSync deve surgir na barra superior do GNOME.
4. Feche a janela principal: o ícone deve permanecer na barra superior, e o menu de contexto (clique direito) deve oferecer as ações *Abrir Painel*, *Pausar/Retomar* e *Sair...*.

---

#### Teste 7: Desinstalação Limpa e Preservação de Dados
```bash
sudo pacman -R brisasync
```
*Critérios de Aprovação*:
- Os arquivos do sistema em `/usr/bin/brisasync` e `/usr/lib/brisasync` são removidos.
- A pasta local de sincronização e o banco SQLite em `~/.local/share/brisasync/` são **preservados** intactos.


# BrisaSync — Registro de Progresso e Decisões Arquiteturais (`docs/PROGRESS.md`)

## Status Geral
- **Fase Atual**: Rodada 31 — Apoio Voluntário via Pix no Diálogo Sobre e Empacotamento v0.1.21:
  1. **Centralização e Manutenibilidade do Recurso de Apoio**:
     - *Arquivo Central de Dados*: Criado [`src/brisasync/resources/support.json`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/resources/support.json) e módulo gestor [`src/brisasync/support.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/support.py) para centralizar título, mensagem voluntária, beneficiário ("Fábio Agreles Bezerra"), chave Pix ("`e4bf0532-8016-42bf-bf2a-fd81326b6621`") e payload do Pix Copia e Cola (EMVCo). Facilita manutenção e forks.
     - *Eliminação da Chave Anterior*: Chave descontinuada (`0ac6e30b-d087-40b8-8b5f-a9269f875546`) totalmente purgada de toda a base.
     - *Validação Criptográfica do Payload*: Checksum CRC16-CCITT validado (`6D9B`) e confirmada a ausência de valor fixo (campo 54), garantindo contribuição voluntária com valor livre definido no app bancário.
  2. **Geração Local e Offline do QR Code**:
     - *Autonomia e Privacidade*: QR Code gerado localmente via utilitário nativo `qrencode` durante a compilação do pacote, sem chamadas a serviços externos de internet.
     - *Decodificação e Correspondência Exata*: Validada via `zbarimg` e `cv2.QRCodeDetector`, confirmando correspondência de 100% dos bytes com o payload oficial.
     - *Contraste e Geometria*: Renderizado em preto sobre container com fundo branco (`#FFFFFF`) e margem livre (quiet zone) preservada mesmo sob o tema Escuro.
  3. **Interface Gráfica do Diálogo Sobre (`BrisaAboutDialog`)**:
     - *Seção Discreta*: Cartão subordinado `support_card` com classe `brisaInnerCard`.
     - *Dados e Seleção*: Beneficiário e chave Pix em campo `QLineEdit` somente-leitura com seleção confortável.
     - *Ações Dedicadas*: Dois botões distintos ("Copiar chave Pix" e "Copiar Pix Copia e Cola") com feedback visual instantâneo ("✓ Chave copiada!", "✓ Copiado!") e restauração temporizada via `QTimer.singleShot(2500, ...)`.
     - *Rolagem em Telas Pequenas*: Conteúdo envolto em `QScrollArea` fluida com botão "Fechar" fixo na barra inferior, mantendo uso confortável a partir de 540×440.
  4. **Verificação Automatizada e Empacotamento Oficial**:
     - Nova suíte de testes [`tests/test_pix_support_and_about_dialog.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_pix_support_and_about_dialog.py) (4/4 aprovados).
     - Verificação em sandbox Bubblewrap aprovada via [`tests/test_installed_package_verification.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_installed_package_verification.py) (6/6 aprovados), confirmando a inclusão de `support.json` e `pix_qr.png` no pacote instalado.
     - Pacote oficial gerado: [`dist/brisasync-0.1.21-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.21-1-x86_64.pkg.tar.zst) (31.951.000 bytes) com SHA-256 `8933be39f7f4c5b047e5ec6a446d8eee8fbfbb2ef41e4bbf2a56893258f4c894`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Apoio Voluntário via Pix no Diálogo Sobre** | **Aprovado (Auto / Capturado)** | Beneficiário, chave selecionável, botões com feedback e QR Code em fundo branco. |
| **Integridade e Checksum do Pix Copia e Cola** | **Aprovado (Auto)** | CRC16 `6D9B` verificado, chave atual presente, chave anterior ausente, valor livre. |
| **Decodificação do QR Code Gerado Localmente** | **Aprovado (Auto)** | Decodificação por `zbarimg` confere byte-a-byte com o payload EMVCo. |
| **Ações de Cópia e Área de Transferência** | **Aprovado (Auto)** | Botões copiam chave e payload separadamente com feedback temporizado de 2,5s. |
| **Rolagem e Conforto em Telas Pequenas** | **Aprovado (Auto / Capturado)** | `QScrollArea` permite rolagem fluida e botão Fechar permanece sempre visível. |
| **Contraste da Bandeja Independente do Tema** | **Aprovado (Auto / Capturado)** | GNOME mantém ícone claro em janela Clara e Escura; overrides estáveis persistidos. |
| **Eliminação de Exclamações Indevidas** | **Aprovado (Auto)** | Notificações de fechar/minimizar usam `Information`, sem falso alerta de atenção. |
| **4 Estados Semânticos da Bandeja** | **Aprovado (Auto / Capturado)** | Saudável, Sincronizando, Pausado e Atenção com iconografia multi-resolução dedicada. |
| **Setas Vetoriais nos QComboBox (SVG)** | **Aprovado (Auto / Capturado)** | Ícones SVG nítidos com padding de 32px nos modos Claro, Escuro, hover e disabled. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Pronto para Atualização v0.1.21** | Pacote `0.1.21-1` pronto para validação de leitura pelo app bancário na VM. |

---

## Histórico de Versões Anteriores

- **Histórico — Rodada 30**: Independência de Contraste da Bandeja, Semântica dos 4 Estados do Ícone, Seletores Vetoriais e Otimização de Ajustes (v0.1.20):
  1. **Diagnóstico e Correção da Independência de Contraste da Bandeja vs. Janela**:
     - *Causa Raiz*: Em [`src/brisasync/ui/icons.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/icons.py), a função `is_dark_palette_active()` consultava `app.palette().color(Window).lightness() < 128`. Como `app.palette()` reflete o tema da janela da aplicação, mudar o BrisaSync para o tema Claro fazia com que o ícone da bandeja fosse invertido para escuro (`brisasync-dark`), ficando invisível sobre a barra superior do GNOME (que é escura por padrão).
     - *Desacoplamento e Detecção do Host da Bandeja (`detect_desktop_panel_is_dark`)*:
       - Implementada detecção contextual: no GNOME (onde o painel superior do Shell é sempre escuro), o modo `auto` adota `panel_is_dark = True` (ícone claro de alto contraste). No KDE Plasma, consulta o esquema de cores ativo do desktop via `styleHints().colorScheme()`. Em ambientes desconhecidos, adota barra escura como fallback seguro.
       - A preferência do ícone da bandeja foi totalmente isolada da preferência da janela: opções `auto` (*Automático (adapta ao sistema)*), `dark_panel` (*Claro (para barra escura)*) e `light_panel` (*Escuro (para barra clara)*).
       - Persistência sincronizada no SQLite via [`database.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/storage/database.py) (`tray_icon_theme_mode` e chave de compatibilidade `tray_theme_mode`), permanecendo estável após trocas de tema da janela, atualizações de estado e reinicializações.
  2. **Semântica dos Estados da Bandeja e Eliminação de Exclamações Indevidas**:
     - *Causa Raiz da Falsa Exclamação*: Em [`main_window.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/main_window.py) `closeEvent`, o fechamento/minimização para a bandeja disparava `send_tray_message(..., is_warning=True)`, passando `MessageIcon.Warning` para o AppIndicator/SNI, o que levava a barra do GNOME a exibir permanentemente um triângulo de advertência com exclamação amarela no ícone.
     - *Correção*: `send_tray_message` agora utiliza `MessageIcon.Information` por padrão (`is_warning=False`).
     - *4 Estados Semânticos Estritos*:
       - `TRAY_STATE_HEALTHY`: Ícone BrisaSync padrão em repouso.
       - `TRAY_STATE_SYNCING`: Ícone com setas circulares dinâmicas de sincronização.
       - `TRAY_STATE_PAUSED`: Ícone com barras verticais de pausa solicitada pelo usuário.
       - `TRAY_STATE_ATTENTION`: Triângulo âmbar de alerta operacional (`attention_required`/`offline`) com descrição no tooltip.
       - Ícone multi-resolução gerado via [`load_tray_state_icon`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/icons.py) com restauração automática imediata para saudável ao concluir ou normalizar.
  3. **Indicador Vetorial Robusto nos `QComboBox` (SVG)**:
     - *Causa Raiz*: Os seletores combobox dependiam de caracteres Unicode ou desenho padrão inconsistente entre os estilos do Qt nos modos Claro e Escuro.
     - *Solução Vetorial*: Adicionados ativos SVG nítidos em `src/brisasync/resources/icons/arrows/` (`arrow-down-dark.svg`, `arrow-down-light.svg`, hover e disabled). Em [`styles.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/styles.py), configurado `QComboBox::drop-down` e `QComboBox::down-arrow` com `padding: 7px 32px 7px 12px`, `subcontrol-origin: padding` e posicionamento preciso à direita sem sobrepor o texto em qualquer tema.
  4. **Aproveitamento de Espaço em Ajustes e Subtítulo Completo**:
     - *Seletores Contidos*: Reorganizados os seletores de tema, intervalo e bandeja em linhas horizontais contidas (`settings_theme_row`, `settings_int_row`, `settings_tray_row`) com larguras entre 160px e 270px em modo amplo, e empilhamento responsivo vertical em larguras úteis < 450px.
     - *Subtítulo do Cabeçalho*: Política de tamanho de `page_subtitle_label` ajustada para `Preferred`, exibindo `"Contas, sincronização e preferências do sistema"` sem cortes em todas as resoluções.
  5. **Verificação Automatizada e Empacotamento Oficial**:
     - 59 testes automatizados passando: [`tests/test_tray_and_settings_refinements.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_tray_and_settings_refinements.py) (4/4), [`tests/test_tray_notifications_and_desktop.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_tray_notifications_and_desktop.py) (10/10), [`tests/test_v017_ui_refinements.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_v017_ui_refinements.py) (4/4), [`tests/test_theme_preference_and_visual_consistency.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_theme_preference_and_visual_consistency.py) (6/6), regressão de OAuth/Sessão/Vault (35/35).
     - Verificação em sandbox Bubblewrap aprovada via [`tests/test_installed_package_verification.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_installed_package_verification.py) (6/6).
     - Pacote oficial gerado: [`dist/brisasync-0.1.20-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.20-1-x86_64.pkg.tar.zst) com SHA-256 `9d7d0e3d3cb497ac05a3e5b252d73ed1f09db796bb0948a3e9e175308c59ec4a`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Contraste da Bandeja Independente do Tema** | **Aprovado (Auto / Capturado)** | GNOME mantém ícone claro em janela Clara e Escura; overrides estáveis persistidos. |
| **Eliminação de Exclamações Indevidas** | **Aprovado (Auto)** | Notificações de fechar/minimizar usam `Information`, sem falso alerta de atenção. |
| **4 Estados Semânticos da Bandeja** | **Aprovado (Auto / Capturado)** | Saudável, Sincronizando, Pausado e Atenção com iconografia multi-resolução dedicada. |
| **Setas Vetoriais nos QComboBox (SVG)** | **Aprovado (Auto / Capturado)** | Ícones SVG nítidos com padding de 32px nos modos Claro, Escuro, hover e disabled. |
| **Disposição e Proporção em Ajustes** | **Aprovado (Auto / Capturado)** | Linhas horizontais com seletores compactos (160-270px) e reflow vertical em telas estreitas. |
| **Subtítulo do Cabeçalho sem Cortes** | **Aprovado (Auto / Capturado)** | Política `Preferred` exibe o subtítulo descritivo integralmente em todas as resoluções. |
| **Responsividade Contínua (820x620 a 1920x1080)** | **Aprovado (Auto / Capturado)** | Sem overflow, sem cortes laterais e com rolagem fluida em todas as páginas. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Pronto para Atualização v0.1.20** | Pacote `0.1.20-1` pronto para validação de contraste e seletores na VM. |

---

## Histórico de Versões Anteriores

- **Histórico — Rodada 29**: Responsividade Completa (Reflow Adaptativo em Largura Útil, Janelas 820×620 a 1920×1080), Contraste do Cartão Sobre e Empacotamento v0.1.19:
  1. **Diagnóstico da Causa Raiz dos Problemas em ~1055 × 790 (v0.1.18)**:
     - *Corte dos Cartões da Direita em Visão Geral*: O breakpoint responsivo anterior verificava a largura total da janela (`width() < 980`). Em uma janela de 1055px, a largura total ultrapassava 980px, mantendo o layout em duas colunas (`LeftToRight`). Contudo, descontando a barra lateral (230px), margens da página (48px) e espaço da barra de rolagem (16px), a largura útil real do conteúdo era de apenas ~761px, insuficiente para abrigar dois cartões completos lado a lado (que exigem no mínimo ~880px de largura útil). Isso empurrava e cortava os cartões da direita.
     - *Corte dos Botões no Hero Banner*: Os botões de ação do Hero (`hero_sync_now_btn` e `hero_pause_btn`) estavam alinhados horizontalmente na mesma linha do título e subtítulo dentro de `hero_top_row_layout`. Com largura útil menor, o título expandia empurrando o container de botões para além da borda direita do banner, resultando no corte do botão de pausa.
     - *Coluna Sistema e Menu Opções Ultrapassando a Área Visível em Ajustes*: Em Ajustes, a coluna "Sistema" permanecia em layout de duas colunas pela mesma falha de cálculo da largura útil. No cabeçalho, o botão `Opções ▾` e o e-mail não possuíam elipse dinâmica e políticas de tamanho elásticas, permitindo que textos longos de conta empurrassem o botão do menu para fora da área visível.
     - *Texto Quase Branco sobre Fundo Claro no Cartão Sobre*: O rótulo da versão (`v_lbl`) no cartão Sobre em Ajustes possuía um estilo inline hardcoded `color: #FFFFFF; font-weight: 700;`. No Modo Escuro o fundo é escuro (ficava legível), mas no Modo Claro o fundo é branco/cinza muito claro, resultando em contraste ilegível (~1:1, texto branco sobre fundo quase branco).
  2. **Correções Arquiteturais e de Layout Aplicadas na v0.1.19**:
     - *Cálculo de Adaptação pela Largura Útil Real do Conteúdo (`_get_useful_content_width`)*: Implementado cálculo dinâmico que deduz a largura da barra lateral (`sidebar_panel.width()`), margens laterais da página e margem de rolagem:
       `useful_width = self.centralWidget().width() - sidebar_w - 48 - 16`.
     - *Breakpoint de Reflow Unificado em `useful_width < 880`*:
       - Em modo estreito (`useful_width < 880`, acionado tanto em 820×620 quanto em 1055×790):
         - `overview_grid_layout` e `settings_grid_layout` transicionam suavemente para `TopToBottom` (empilhamento vertical de coluna única), e os fatores de esticamento são zerados (`setStretch(0, 0)` e `setStretch(1, 0)`) para prevenir distorção vertical artificial dos cartões.
         - Os botões do Hero Banner são movidos para uma linha dedicada própria (`hero_actions_container` movido para `hero_banner_layout` abaixo das descrições), garantindo 100% de visibilidade e conforto de clique sem qualquer corte.
         - As ações do cartão de pastas são reposicionadas em linha dedicada abaixo dos caminhos.
         - A pílula de status global do cabeçalho é ocultada para priorizar o menu `Opções ▾`.
         - A elipse de e-mail é recalculada para 15 caracteres preservando a identificação do domínio, com tooltip exibindo sempre o e-mail integral.
       - Em modo largo (`useful_width >= 880`, acionado em 1280×720 e 1920×1080):
         - Restaura orientação `LeftToRight` em duas colunas com proporções ideais (3:2 na Visão geral e 1:1 em Ajustes).
         - Retorna as ações do Hero para o alinhamento superior com o título.
         - Exibe a pílula de status global no cabeçalho e elipse expandida de 22 caracteres no e-mail.
     - *Políticas de Tamanho e Quebra de Linha Resilientes*:
       - Rótulos de nome de pasta e e-mail configurados com `setWordWrap(True)`.
       - Pílulas de status e botões de ação configurados com política `Fixed` ou `Preferred`, prevenindo compressão inadequada.
       - Cabeçalho configurado com `page_subtitle_label.setSizePolicy(Ignored, Preferred)` para ceder espaço prontamente aos controles do lado direito.
       - Tabela de Atividade configurada com barra de rolagem horizontal sob demanda (`ScrollBarAsNeeded`) e última coluna expansível (`setStretchLastSection(True)`).
     - *Correção de Contraste no Cartão Sobre (WCAG AAA)*:
       - Removido estilo inline hardcoded `#FFFFFF`.
       - Aplicada a classe semântica `overviewItemTitle` ao rótulo da versão (`v_lbl`), `overviewItemSub` ao subtítulo de licença e adicionada a classe `overviewItemMuted` em `styles.py` para textos secundários neutros (`#64748B` no claro, `#94A3B8` no escuro), garantindo contraste superior a 7:1 em ambos os temas.
  3. **Verificação Automatizada e Evidências Reais**:
     - Bateria de testes em [`tests/test_v017_ui_refinements.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_v017_ui_refinements.py): teste `test_3_responsive_layout_reflow_narrow_vs_wide` valida transições bidirecionais contínuas em 1280×720, 1055×790, 820×620 e 1920×1080 sem perda de controles.
     - Captura real de 42 telas e diálogos em alta resolução nas 4 geometrias alvo em Modo Claro e Modo Escuro.
     - Suíte de empacotamento ALPM em sandbox Bubblewrap aprovada via [`tests/test_installed_package_verification.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_installed_package_verification.py).
     - Pacote oficial gerado: [`dist/brisasync-0.1.19-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.19-1-x86_64.pkg.tar.zst) com SHA-256 `16e7414ef8835f4edce1c1252f8b74ac47e3938f8670ff5b91dde62403c31825`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Responsividade em Janela 1055×790** | **Aprovado (Auto / Capturado)** | Reflow de coluna única, Hero actions em linha própria, cartões sem corte lateral. |
| **Responsividade em Janela 820×620** | **Aprovado (Auto / Capturado)** | Layout compacto, rolagem vertical fluida, sem scroll horizontal e sem perda de botões. |
| **Responsividade em 1280×720 e 1920×1080** | **Aprovado (Auto / Capturado)** | Duas colunas proporcionais, pílula global visível, ações do Hero na linha superior. |
| **Redimensionamento Bidirecional Contínuo** | **Aprovado (Auto)** | Transições repetidas estreito <-> largo sem vazamento de estado ou distorção de widgets. |
| **Contraste do Cartão Sobre (Claro e Escuro)** | **Aprovado (Auto / Capturado)** | Eliminação de `#FFFFFF` fixo; uso de tokens semânticos com contraste WCAG AAA (>7:1). |
| **Menu Opções e Elipse de E-mail** | **Aprovado (Auto / Capturado)** | Botão `Opções ▾` 100% visível em todas as resoluções; elipse adaptativa com tooltip integral. |
| **Autoinício Completo com Presença na Bandeja** | **Aprovado (Auto)** | Coordenador gerencia unit `systemd --user` e XDG autostart com `--start-hidden`. |
| **Instância Única e Revelação pelo Lançador** | **Aprovado (Auto)** | Lançador revela janela oculta via `ui.sock` sem duplicar daemon, UI ou ícone de bandeja. |
| **Recuperação de Cofre Bloqueado** | **Aprovado (Auto)** | Sem loops interativos de senha; detecção não-interativa de desbloqueio externo. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Pronto para Atualização v0.1.19** | Pacote `0.1.19-1` disponível para validação da responsividade em ~1055×790 e 820×620. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |

- **Histórico — Rodada 27**: Autoinício Completo com Presença na Bandeja (`--start-hidden`), Coordenação XDG Autostart + systemd --user e Empacotamento v0.1.16:
  1. **Diagnóstico e Correção do Estado "Sincronizando..." Persistente (Timer IPC e Ciclo de Vida da Janela)**:
     - *Causa Raiz*: Em `src/brisasync/ui/main_window.py` linha 970, o timer de status IPC (`self._status_timer = QTimer(self)`) era configurado com intervalo de 1200ms e conectado ao método `refresh_service_status_from_ipc`, mas `self._status_timer.start(1200)` nunca era executado. Como consequência, após o disparo da sincronização pelo usuário, a interface exibia o snapshot imediato retornado pelo comando IPC (`STATE_SYNCING`) e nunca mais consultava o socket AF_UNIX. Embora o daemon concluísse a transferência bidirecional em poucos segundos, gravasse a baseline no SQLite e transicionasse para `STATE_WAITING`, a interface permanecia estática e permanentemente em "Sincronizando...".
     - *Ciclo de Vida Reativo e Econômico*: O timer é iniciado ativamente quando a janela está visível (`showEvent` e `restore_and_focus_window`). Ao ocultar ou minimizar a janela para a bandeja (`hideEvent`), o timer é interrompido de forma limpa (`_status_timer.stop()`), eliminando consumo desnecessário de CPU e prevenindo interferência de callbacks em janelas minimizadas. Ao reabrir a interface, o timer é reativado imediatamente, garantindo que o Hero Banner, a pílula global e os cartões de pasta reflitam o estado real e atual do daemon sem necessidade de reiniciar a aplicação.
  2. **Centralização e Consistência do Botão Primário do Hero Banner (`_update_hero_primary_button`)**:
     - *Causa Raiz*: O texto e ícone do botão branco de ação principal (`hero_sync_now_btn`) eram configurados apenas durante a construção e no ramo `if not is_configured:` ("Conectar conta" / "Concluir conexão"). Quando a sincronização iniciava ou quando o par ativo retornava ao estado saudável/espera (`STATE_WAITING`), o botão nunca era atualizado de volta para "Sincronizar agora" nem seu ícone restaurado para `sync`, mantendo o rótulo "Conectar conta" mesmo com a conta conectada e sincronizando.
     - *Atualização Unificada Baseada no Estado Operacional*: Implementado o método centralizado `_update_hero_primary_button(snapshot)`:
       - Par não configurado: exibe "Conectar conta" (ou "Concluir conexão"), habilitado, ícone Google Drive.
       - Par configurado e sincronização ativa (`STATE_SYNCING`, `STATE_VERIFYING` ou `is_cycle_active`): exibe "Sincronizando...", desabilitado, cursor padrão, tooltip indicativo, prevenindo cliques concorrentes.
       - Par configurado em espera/repouso (`STATE_WAITING`): exibe "Sincronizar agora", habilitado, ícone `sync`, cursor apontador.
       - Par configurado em pausa ou atenção: exibe "Sincronizar agora", habilitado, permitindo retentativa direta pelo usuário.
       - Guarda de concorrência em `_on_sync_now_clicked`: rejeita requisições repetidas se um ciclo já estiver ativo, exibindo mensagem amigável na barra de status.
  3. **Correção de Contraste e Geometria da Edição Inline em Diálogos de Seleção (`QFileDialog`)**:
     - *Causa Raiz*:
       1. A folha de estilos geral para `QLineEdit` continha `padding: 8px 12px`. Na criação de nova pasta pelo botão do diálogo (`QFileDialog`), o Qt cria um editor inline dentro da linha do `QTreeView`/`QListView`. Como a linha do item tem altura típica de 20-24px, os 16px de padding vertical causavam o corte do texto visível.
       2. Em `create_brisasync_palette` para Modo Escuro, a cor `HighlightedText` estava fixada em `#0B0F15` (quase preto). Ao criar a pasta, o Qt selecionava automaticamente o nome sugerido (`selectAll()`), fazendo com que o texto selecionado ficasse preto sobre fundo escuro, tornando-se invisível.
     - *Correção Visual de Alto Contraste (WCAG AAA)*:
       - Em `styles.py`, `HighlightedText` foi configurado para `#FFFFFF` e `Highlight` para `#5446CF` no Modo Escuro (e `#6355DE` / `#FFFFFF` no Modo Claro), proporcionando contraste nítido (> 7:1) em qualquer seleção.
       - Adicionada regra específica para `QAbstractItemView QLineEdit`, `QTreeView QLineEdit`, `QListView QLineEdit`, `QFileDialog QAbstractItemView QLineEdit` com `padding: 1px 4px; margin: 0px; min-height: 20px; border: 1.5px solid {focus_outline}`, permitindo que o campo inline caiba confortavelmente na linha do diálogo sem cortar o texto.
       - Adicionadas regras para `QTreeView`, `QListView` e `QFileDialog` com cores de seleção harmônicas, preservando a identidade visual e sem alterar o espaçamento confortável dos formulários e tabelas principais.
     - *Melhoria Futura Registrada*: Inclusão futura de um seletor manual de tema em Ajustes (Claro / Escuro / Sistema), mantendo o escopo objetivo da rodada.
  4. **Suíte de Testes Automatizados e Empacotamento Oficial ALPM v0.1.14**:
     - Acrescentados 3 testes automatizados robustos em [`tests/test_oauth_buttons_and_theme_regression.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_oauth_buttons_and_theme_regression.py):
       - `test_hero_primary_button_and_status_timer_lifecycle`: validação do ciclo de vida do timer, transição automática de "Sincronizando..." para "Tudo em dia", desabilitação durante o ciclo ativo e pausa/retomada ao esconder/restaurar a janela.
       - `test_hero_primary_button_states_unconfigured_and_paused_and_attention`: validação de que o botão Hero nunca oferece "Conectar conta" quando configurado, tratando pausa e atenção adequadamente.
       - `test_inline_editor_and_file_dialog_contrast_in_both_themes`: validação de contraste WCAG AAA para `HighlightedText`, regras de QSS para editor inline e medidas compactas em `QTreeView`.
     - Suíte completa de testes executada com 100% de aprovação (todos os 20 testes em `test_oauth_buttons_and_theme_regression.py` e 24 testes nas demais suítes).
     - Testes em sandbox Bubblewrap/ALPM aprovados via [`tests/test_installed_package_verification.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_installed_package_verification.py) (6 testes aprovados).
     - Pacote oficial gerado: [`dist/brisasync-0.1.14-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.14-1-x86_64.pkg.tar.zst) com SHA-256 `04c1f96f1ef6d824557e44eee1715f9bc846d6a77686cfd359b43ae91bc8fcde`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Autoinício Completo com Presença na Bandeja** | **Aprovado (Auto)** | Coordenador gerencia unit `systemd --user` e XDG autostart com `--start-hidden`. |
| **Instância Única e Revelação pelo Lançador** | **Aprovado (Auto)** | Lançador revela janela oculta via `ui.sock` sem duplicar daemon, UI ou ícone de bandeja. |
| **Comportamento Limpo sem Bandeja** | **Aprovado (Auto)** | Com `--no-tray`, `--start-hidden` assegura daemon e sai com código 0 sem janela indesejada. |
| **Animação Discreta de Rotação (Hero Button)** | **Aprovado (Auto / Homologado)** | Rotação suave a 25 FPS vinculada ao daemon, pausada em background. |
| **Ciclo Reativo de Status IPC (`_status_timer`)** | **Aprovado (Auto / Homologado)** | Transição automática de "Sincronizando..." para "Tudo em dia" em 1.2s. |
| **Contraste e Geometria no Diálogo de Pasta Local (`QFileDialog`)** | **Aprovado (Auto / Homologado)** | Editor inline compacto (<=22px) sem clipping e seleção WCAG AAA. |
| **Instalação Limpa Sem `--nodeps` (Fase 1)** | **Aprovado** | `pacman -U` sem `--nodeps` em contêiner `archlinux:base` resolveu dependências oficiais com sucesso. |
| **Autoinício na Sessão KDE (`systemd --user`)** | **Aprovado** | Daemon PID 2636 iniciou no login; interface PID 5019 conectou sem duplicar serviço. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Pronto para Atualização v0.1.16** | Pacote `0.1.16-1` disponível para validação de autoinício com bandeja oculta. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |

- **Histórico — Rodada 24**: Correção do Contrato de Pastas Remotas (`RemoteDirectoryEntry`), Sincronização Precisa do Home View/Wizard, Eliminação de Strings de Demonstração e Empacotamento v0.1.13.
  1. **Diagnóstico e Correção da Falha de Listagem de Pastas no Google Drive (`AttributeError: 'RemoteDirectoryEntry' object has no attribute 'folder_name'`)**:
     - *Causa Raiz*: Em `src/brisasync/ui/main_window.py` linha 3802 (`_on_remote_folders_loaded`), a interface tentava acessar `entry.folder_name`, enquanto a dataclass `RemoteDirectoryEntry` em `src/brisasync/backend/rclone_engine.py` definia nativamente o atributo como `name`. Isso causava uma exceção não tratada na thread principal, interrompendo o fluxo antes do desbloqueio de sinais dos comboboxes e deixando a interface permanentemente travada em *"Consultando pastas no Google Drive…"*.
     - *Harmonização do Contrato*: Em `RemoteDirectoryEntry`, foi adicionada a propriedade `@property def folder_name(self) -> str: return self.name` e suporte transparente no construtor para `folder_name` ou `name`, garantindo compatibilidade total com qualquer código legado ou futuro.
     - *Consumo Seguro e Resiliente*: Em `_on_remote_folders_loaded`, a extração de atributos foi blindada com fallback seguro (`getattr(entry, "name", getattr(entry, "folder_name", ""))` e `getattr(entry, "folder_id", "")`). O processamento foi encapsulado em bloco `try ... finally` irrestrito, garantindo que `blockSignals(False)` e a reativação de todos os botões (`list_remote_folders_button`, `wizard_list_remote_btn`, `create_remote_folder_button`, `wizard_create_remote_btn`) ocorram sob qualquer circunstância.
     - *Tratamento de Sucesso, Lista Vazia e Falha*:
       - Caso haja pastas: comboboxes de Ajustes e Assistente são populados com `Nome [ID: id]` e o feedback reporta `✓ N pasta(s) localizada(s) no Google Drive.`
       - Caso o Drive esteja vazio (0 pastas): o feedback orienta claramente *"Nenhuma pasta encontrada no Google Drive. Use '+ Nova Pasta...' para criar uma."* com estilo visual informativo (`#F59E0B`).
       - Caso ocorra falha de rede ou de autorização: `_on_remote_folders_failed` reativa imediatamente todos os botões e atualiza ambos os rótulos de feedback com mensagem de erro detalhada em vermelho (`#EF4444`).
  2. **Eliminação de Dados de Demonstração e Consistência Visual do Cartão de Pastas**:
     - *Remoção de Strings de Desenvolvimento*: Substituídos todos os textos estáticos nos construtores de widgets (`Documentos`, `fabioagreles@gmail.com`, `/home/agreles/Android/brisa`) por padrões neutros e profissionais (`Nenhuma conta vinculada`, `Google Drive`, `Configuração pendente`, `Nenhuma pasta sincronizada configurada`).
     - *Atualização Rigorosa do Home View para Configurações Parciais*: Quando o usuário possui apenas uma pasta local definida sem pasta remota (cenário real reproduzido na VM Manjaro GNOME), a interface agora reflete explicitamente o estado real:
       - Título do cartão: `Configuração pendente`.
       - Caminho exibido: `[Caminho local] (Falta pasta remota)`.
       - Pílula de status: `○ pendente` (âmbar), nunca `"em dia"`.
     - *Condição de Confirmação para "em dia"*: O status `"em dia"` foi condicionado estritamente à existência do par completo (`local_cfg and remote_cfg`) E à confirmação operacional verificada (ou baseline inicial registrada no banco SQLite para o par exato via `is_baseline_initialized`, ou confirmação operacional de execução bem-sucedida pelo daemon com `last_confirmed_sync_at` e `last_run_status == "SUCCESS"`). Pares recém-configurados antes do primeiro ciclo exibem `"● Aguardando 1ª sincronização"`.
     - *Sincronização Bidirecional Home View <-> Assistente*: A seleção de pasta remota no assistente (`_on_wizard_remote_combo_changed`) dispara imediatamente a atualização do `Home View`, mantendo toda a tela consistente em tempo real sem exigir reinício da aplicação.
  3. **Suíte de Testes de Regressão e Validação Rigorosa**:
     - Acrescentados 3 testes automatizados robustos em [`tests/test_oauth_buttons_and_theme_regression.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_oauth_buttons_and_theme_regression.py):
       - `test_remote_directory_entry_contract_and_attributes`: validação completa dos atributos, construtores e propriedades de `RemoteDirectoryEntry`.
       - `test_remote_folders_loaded_success_empty_and_failure_restoration`: validação de sucesso com múltiplas pastas, tratamento de lista vazia (0 pastas) e restauração imediata de botões em falhas.
       - `test_partial_configuration_shows_pending_and_no_stale_demo_data`: validação do estado parcial (pasta local sem remota), ausência de dados obsoletos/demo, badge `"○ pendente"`, persistência no assistente e transição para `"em dia"` somente após confirmação da baseline.
     - Suíte completa do projeto executada: **69 testes aprovados** (100% de sucesso).
  4. **Empacotamento Oficial ALPM v0.1.13 e Preservação de Artefatos**:
     - Versão elevada para **0.1.13** em `pyproject.toml`, `src/brisasync/__init__.py`, `packaging/build_packages.sh`, `packaging/arch/PKGBUILD` e `tests/test_installed_package_verification.py`.
     - Todos os pacotes anteriores em `dist/` (0.1.0 a 0.1.12) permanecem estritamente preservados com seus checksums íntegros.
     - Pacote oficial gerado: [`dist/brisasync-0.1.13-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.13-1-x86_64.pkg.tar.zst) com SHA-256 `f3ba17780e7c69847dc6dd8398782df53aedd693ed75c35de2dc64b70153aeda`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Contrato `RemoteDirectoryEntry` e Listagem de Pastas** | **Aprovado (Auto)** | Atributos `name`, `folder_name`, `folder_id` harmonizados; combos populados sem travamento de UI. |
| **Resiliência contra Lista Vazia e Falhas de Listagem** | **Aprovado (Auto)** | Feedback claro para 0 pastas e restauração imediata dos botões em caso de erro. |
| **Fidelidade Visual do Cartão de Pastas e Home View** | **Aprovado (Auto)** | Eliminação de strings demo; par incompleto exibe `Configuração pendente` e `○ pendente`. |
| **Transição de Status das Pastas ("em dia")** | **Aprovado (Auto)** | Status `"em dia"` condicionado à confirmação operacional verificada e baseline inicial. |
| **Contrato Completo de Workers e Sinais** | **Aprovado (Auto)** | Validado com `OAuthConnectWorker`, `RemoteFoldersWorker` e `ServiceCommandWorker`. |
| **Instalação Limpa Sem `--nodeps` (Fase 1)** | **Aprovado** | `pacman -U` sem `--nodeps` em contêiner `archlinux:base` resolveu dependências oficiais com sucesso. |
| **Autoinício na Sessão KDE (`systemd --user`)** | **Aprovado** | Daemon PID 2636 iniciou no login; interface PID 5019 conectou sem duplicar serviço. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Pronto para Reinstalação v0.1.13** | Pacote `0.1.13-1` disponível para validação da listagem de pastas e seleção do par. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |

- **Histórico — Rodada 23**: Correção da Conclusão de Autenticação e Resolução Consistente do Binário rclone (v0.1.12).
- **Histórico — Rodada 22**: Correção do Contrato Completo de Workers/Sinais, Resiliência na Preparação da Thread e Empacotamento v0.1.11.
  1. **Diagnóstico da Regressão na VM Manjaro GNOME (`AttributeError: 'OAuthConnectWorker' object has no attribute 'oauth_succeeded'`)**:
     - *Causa Raiz*: Na `BrisaMainWindow`, a conexão de sinais utilizava `worker.oauth_succeeded.connect` e `worker.oauth_failed.connect`, enquanto a classe `OAuthConnectWorker` definia os sinais canônicos `succeeded = Signal(object)` e `failed = Signal(str)`. Além disso, a chamada de cancelamento invocava `worker.cancel()` em vez de `worker.request_cancel()`.
     - *Descoberta Adicional Proativa*: Verificada a existência do mesmo desalinhamento de sinais e construtores em `RemoteFoldersWorker` (`folders_loaded`/`operation_failed` vs `succeeded`/`failed`, e assinatura de inicialização `engine`/`bridge`) e em `ServiceCommandWorker` (`command_succeeded`/`command_failed` vs `succeeded`/`failed`), eliminando proativamente falhas sequenciais nas telas seguintes de listagem e criação de pastas.
  2. **Harmonização Completa do Contrato Interface <-> Workers**:
     - *Sinais e Métodos em `src/brisasync/ui/workers.py`*:
       - `OAuthConnectWorker`: Sinais canônicos `succeeded` e `failed`, com aliases de compatibilidade `oauth_succeeded = succeeded` e `oauth_failed = failed`. Método `cancel()` disponibilizado como alias de `request_cancel()`.
       - `RemoteFoldersWorker`: Sinais `succeeded`, `failed`, `folders_loaded`, `operation_failed`. Construtor flexível que aceita tanto argumentos posicionais quanto `bridge=self.bridge, action="list"/"create", folder_name=name`.
       - `ServiceCommandWorker`: Sinais `succeeded`, `failed`, `command_succeeded`, `command_failed`.
     - *Proteção Global e Recuperação de Falhas em `src/brisasync/ui/main_window.py`*:
       - A preparação, instanciação, conexão de sinais e início do worker (`worker.start()`) foram envelopadas em bloco `try...except`.
       - Qualquer exceção prévia ou durante a inicialização restaura imediatamente os botões (`_set_oauth_in_progress(False)`), limpa o ponteiro `self._oauth_worker = None` e apresenta um diálogo instrutivo (`QMessageBox.critical`) sem deixar a interface bloqueada.
       - A finalização normal ou por erro do worker limpa cooperativamente o ponteiro `_oauth_worker`, permitindo novas tentativas imediatas após falha.
       - Cancelamento pelo usuário (`_on_cancel_oauth_clicked`) encerra a thread de forma cooperativa sem popup modal desnecessário de erro.
  3. **Validação com a Classe Real `OAuthConnectWorker` (Sem Mock de Sinais)**:
     - Testes automatizados executados na suíte [`tests/test_oauth_buttons_and_theme_regression.py`](file:///home/agreles/Aplicativos/BrisaSync/tests/test_oauth_buttons_and_theme_regression.py) utilizando a classe real `OAuthConnectWorker` e interceptando apenas as operações externas do navegador (`GoogleOAuthDesktopClient.authorize_interactive`).
     - Validados 9 cenários: contrato de sinais e métodos, início pelos dois botões, bloqueio de concorrência, fluxo de sucesso com emissão de credenciais, erro com restauração de botões e retentativa bem-sucedida subsequente, cancelamento pelo usuário sem diálogo modal crítico, falha de preparação antes da thread, tokens visuais claro/escuro e renderização vetorial.
     - Execução isolada em sandbox Bubblewrap/ALPM aprovada via `tests/test_installed_package_verification.py` (6 testes aprovados).
  4. **Empacotamento e Preservação de Artefatos**:
     - Versão elevada para **0.1.11**. Todos os pacotes anteriores em `dist/` (0.1.0 a 0.1.10) permanecem estritamente preservados com seus checksums íntegros.
     - Pacote oficial gerado: [`dist/brisasync-0.1.11-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.11-1-x86_64.pkg.tar.zst) com SHA-256 `d56f226f741e42fc65c5327ecf76110c6722a42536a179e162c2bed7b1ce987a`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Contrato Completo de Workers e Sinais** | **Aprovado (Auto)** | Validado com `OAuthConnectWorker` real: `succeeded`/`failed`, aliases, `request_cancel`/`cancel`, sem mock de sinais. |
| **Proteção e Recuperação de Falhas Pré-Thread** | **Aprovado (Auto)** | Exceções na preparação restauram botões, limpam estado ocupado e apresentam diálogo útil. |
| **Fluxo Completo de Sucesso, Erro, Cancelamento e Retentativa** | **Aprovado (Auto)** | Sucesso conecta e lista pastas; erro restaura botões e permite novo clique; cancelamento opera sem modal. |
| **Integração Visual com GNOME/Wayland e KDE** | **Aprovado (Auto)** | Suporte a temas Claro/Escuro (`colorScheme()`), tipografia Cantarell e foco de acessibilidade 2px. |
| **Instalação Limpa Sem `--nodeps` (Fase 1)** | **Aprovado** | `pacman -U` sem `--nodeps` em contêiner `archlinux:base` resolveu dependências oficiais com sucesso. |
| **Autoinício na Sessão KDE (`systemd --user`)** | **Aprovado** | Daemon PID 2636 iniciou no login; interface PID 5019 conectou sem duplicar serviço. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Pronto para Reinstalação v0.1.11** | Teste manual do navegador real e cofre bloqueado a ser executado com o pacote `0.1.11-1`. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |

- **Histórico — Rodada 21**: Correção do Contrato OAuth Desktop, Unificação de Botões de Conexão, Harmonização Visual Adaptativa (GNOME / KDE) e Empacotamento v0.1.10.
  1. **Correção do Fluxo OAuth e Resolução do Traceback no Manjaro GNOME/Wayland**:
     - *Diagnóstico*: Na homologação em VM Manjaro GNOME/Wayland, o botão do assistente falhou com `AttributeError: type object 'OAuthClientConfig' has no attribute 'load'`. A classe implementava `load_available(explicit_path=...)`, enquanto chamadas legadas esperavam `load()`. Adicionado `load()` como alias de compatibilidade direta para `load_available()`, garantindo que ambos os métodos operem identicamente.
     - *Descoberta automática do cliente Desktop empacotado*: Preservada e confirmada a resolução em cadeia: argumentos explícitos -> variáveis de ambiente -> override do usuário em `~/.config/brisasync/google_oauth_client.json` -> caminhos de distribuição do pacote (`/usr/share/brisasync/google_oauth_client.json` e `resources/oauth/google_oauth_client.json`). Não há exigência de intervenção ou JSON manual por parte do usuário final.
  2. **Unificação Funcional dos Botões de Conexão e Proteção de Concorrência**:
     - *Convergência dos Botões*: O botão branco do Hero Banner ("Conectar conta" em estado não configurado) e o botão "Conectar Conta Google" do assistente de boas-vindas acionam exatamente a mesma rotina funcional (`_on_connect_google_clicked`).
     - *Bloqueio de Autorizações Simultâneas*: Implementada trava cooperativa (`if self._oauth_worker and self._oauth_worker.isRunning(): return`). Durante a autorização, os botões Hero, Conectar e Ajustes são desabilitados via `_set_oauth_in_progress(True)`, e o botão Cancelar é ativado.
     - *Tratamento de Erros e Feedback Visual*: Erros de inicialização (`OAuthConfigurationError` ou exceções de protocolo) exibem diálogo informativo (`QMessageBox.critical`) com orientação clara, sem travamento da aplicação, reabilitando os botões imediatamente.
  3. **Harmonização Visual Nativa com GNOME e KDE (Light e Dark Modes)**:
     - *Integração com a Preferência do Desktop*: Detecção dinâmica de tema claro/escuro via `QGuiApplication.styleHints().colorScheme()`, reagindo ao sinal `colorSchemeChanged`.
     - *Motor e Paleta*: Enforçamento do estilo `Fusion` nativo do Qt (imune à falta de módulos GTK externos) combinado com `QPalette` completa e regras QSS refinadas para ambos os modos:
       - **Modo Escuro**: Fundo `#0B0F15`, superfícies de cards `#131923`, controles `#1A2230`, bordas `#273140`, destaque lavanda `#9189FF`.
       - **Modo Claro**: Fundo `#F8FAFC`, superfícies de cards `#FFFFFF`, controles `#FFFFFF` / `#F1F5F9`, bordas `#E2E8F0`, destaque lavanda profundo `#6355DE`.
     - *Tipografia e Acessibilidade*: Inclusão de `Cantarell` (fonte padrão do GNOME) na pilha tipográfica (`system-ui, Cantarell, "Segoe UI", Roboto, Ubuntu, -apple-system, sans-serif`) e contorno de foco nítido de 2px (`outline: 2px solid`, `border: 2px solid`) em botões, campos e tabelas, garantindo excelente navegabilidade por teclado e alto contraste.
  4. **Suíte de Testes Automatizados e Empacotamento v0.1.10**:
     - *Testes de Regressão Criados*: `tests/test_oauth_buttons_and_theme_regression.py` (5 testes novos cobrindo alias `load`/`load_available`, disparo unificado e bloqueio de concorrência, apresentação de erro em QMessageBox, tokens claro/escuro e renderização vetorial de `BrisaSidebarNavItem`).
     - *Validação de Pacotes em Sandbox Bubblewrap*: `tests/test_installed_package_verification.py` atualizado para v0.1.10 (6 testes aprovados com instalação, upgrade, remoção e diagnósticos isolados).
     - *Preservação Estrita de Versões Históricas*: Todas as versões em `dist/` (0.1.0 a 0.1.9) mantidas inalteradas.
     - *Novo Pacote*: `dist/brisasync-0.1.10-1-x86_64.pkg.tar.zst` gerado com SHA-256 `ad617c4aaba38453acdd6d28924ca0b9d686665b6ae344cd0b5569b84f1b6bee`.

### Matriz de Homologação Consolidada

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Contrato OAuth Desktop (`load` / `load_available`)** | **Aprovado (Auto)** | Alias implementado e validado em `test_oauth_buttons_and_theme_regression.py`; cliente empacotado resolvido automaticamente. |
| **Unificação dos Botões de Conexão** | **Aprovado (Auto)** | Botão Hero e Assistente disparam a mesma rotina; cliques concorrentes bloqueados. |
| **Integração Visual com GNOME/Wayland e KDE** | **Aprovado (Auto)** | Suporte a temas Claro/Escuro (`colorScheme()`), tipografia Cantarell e foco de acessibilidade 2px. |
| **Instalação Limpa Sem `--nodeps` (Fase 1)** | **Aprovado** | `pacman -U` sem `--nodeps` em contêiner `archlinux:base` resolveu dependências oficiais com sucesso. |
| **Autoinício na Sessão KDE (`systemd --user`)** | **Aprovado** | Daemon PID 2636 iniciou no login; interface PID 5019 conectou sem duplicar serviço. |
| **Homologação em VM Manjaro GNOME/Wayland** | **Em Andamento (Reinstalação v0.1.10)** | Teste manual do navegador real e cofre bloqueado a ser executado com o pacote `0.1.10-1`. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |
  1. **Resultado Aprovado da Instalação em Contêiner Arch Linux Limpo (Fase 1)**:
     - *Ambiente*: Contêiner oficial `archlinux:base`, após `pacman -Syu`, instalação direta do pacote oficial [`brisasync-0.1.9-1-x86_64.pkg.tar.zst`](file:///home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.9-1-x86_64.pkg.tar.zst) via `pacman -U` **sem a flag `--nodeps`**.
     - *Resolução nativa de dependências*: O `pacman` resolveu, baixou e instalou automaticamente todas as dependências declaradas (`python`, `pyside6`, `libsecret`, `libnotify`, `hicolor-icon-theme`) a partir dos repositórios oficiais `core` e `extra`.
     - *Verificações básicas aprovadas*:
       - `brisasync --version`: `BrisaSync 0.1.9`.
       - `brisasync --help`: sintaxe e opções de inicialização exibidas corretamente.
       - `brisasync --diagnose`: diagnósticos de dependências operacionais com Python 3.14.8, Qt/PySide6 6.12.0 e SQLite 3.54.0.
       - Motor `rclone` embutido (`/usr/lib/brisasync/bin/rclone` v1.75.2) detectado e executado com sucesso.
     - *Limitações registradas no contêiner headless*:
       - Sessão gráfica desconhecida (`UNKNOWN`).
       - Cofre inacessível (`VaultUnavailableError`) por ausência de `/etc/machine-id` e do barramento de sessão D-Bus no contêiner headless.
     - *Escopo rigoroso de aprovação*: Declarada como aprovada estritamente a resolução de dependências e a execução CLI básica. Interface gráfica (GUI), autenticação OAuth via navegador, cofre de segredos da sessão, bandeja do sistema e autoinício (`systemd --user`) **não** foram declarados como testados neste ambiente headless.
  2. **Preparação para a Fase 2: Homologação em VM com GNOME e Distribuição ALPM**:
     - *Recursos de hardware verificados no host*:
       - Virtualização por hardware: Suporte AMD-V ativo (`kvm_amd` carregado no kernel).
       - Memória RAM: 31 GiB totais (22 GiB disponíveis).
       - Espaço em disco: 79 GiB livres no sistema de arquivos raiz (`/`).
       - Hipervisores disponíveis: VirtualBox 7.2.20 (`/usr/sbin/VBoxManage`) já instalado no host; KVM/QEMU disponível via repositórios oficiais caso preferido.
     - *Distribuições recomendadas*: Arch Linux com GNOME puro ou Manjaro GNOME (base Arch / pacman).
     - *Cenários cruciais a homologar na VM GNOME*:
       1. **Operação Padrão no GNOME sem Extensão de Bandeja**: Validar o comportamento nativo do BrisaSync no GNOME Shell puro (sem extensões de AppIndicator), comprovando que `isSystemTrayAvailable() == False` é tratado com segurança, a janela fecha mantendo a sincronização ativa em segundo plano, as notificações são exibidas pelo daemon do GNOME e a interface pode ser reaberta pelo Dash sem duplicar processos.
       2. **Comportamento com Cofre Bloqueado (GNOME Keyring)**: Iniciar a sessão com o chaveiro padrão do GNOME trancado; comprovar que o daemon entra em `STATE_ATTENTION_REQUIRED` de forma resiliente, sem popups repetidos nem loops de autenticação no navegador, retomando o carregamento suavemente assim que o usuário destrancar o chaveiro.
       3. **Autenticação OAuth Completa em Navegador Real**: Validação de ponta a ponta do fluxo loopback abrindo o navegador padrão (Firefox/Chromium) na VM.
       4. **Autoinício na Sessão GNOME (`systemd --user`)**: Validação de `brisasync.service` iniciando em simbiose com `graphical-session.target` sob o GNOME.
  3. **Matriz de Homologação Consolidada**:

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Instalação Limpa Sem `--nodeps` (Fase 1)** | **Aprovado** | `pacman -U` sem `--nodeps` em contêiner `archlinux:base` resolveu Python 3.14.8, PySide6 6.12.0, libsecret, libnotify e rclone v1.75.2. |
| **Autoinício na Sessão KDE (`systemd --user`)** | **Aprovado** | `systemd --user` iniciou daemon PID 2636 no login; `systemctl --user is-active` reportou `active`. |
| **Instância Única e Conexão da UI** | **Aprovado** | UI PID 5019 abriu pelo lançador conectando-se ao PID 2636 sem duplicação de processos. |
| **Integridade de Configurações e Dados** | **Aprovado** | Banco SQLite, credenciais da sessão e pastas pessoais 100% íntegras; estado `WAITING` (em dia). |
| **Homologação em GNOME Real (Fase 2)** | **Pronto para Execução** | Roteiro estruturado no playbook para teste sem extensão de bandeja e chaveiro bloqueado em VM ALPM. |
| **Cofre Bloqueado na Inicialização** | **Pendente para VM** | Não declarado como testado no host pessoal; será validado no ambiente GNOME Keyring da VM. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |

- **Histórico — Rodada 19**: Homologação do Autoinício na Sessão (`systemd --user`) e Preparação de Sistema Limpo:
  1. **Auditoria Pré-Logout da Versão e dos Processos**:
     - *Identificação rigorosa*: Pacote oficial `brisasync-0.1.9-1-x86_64.pkg.tar.zst` instalado no sistema hospedeiro via `pacman -U`.
     - *Configuração persistida*: Caixa *"Iniciar automaticamente ao fazer login"* habilitada pelo mantenedor na aba *Ajustes*, ativando a unit `brisasync.service` no `systemd --user`.
  2. **Resultado Real Aprovado Pós-Logout/Login (Sessão KDE Plasma / Wayland)**:
     - *Autoinício do Daemon*: Comprovado antes da abertura da interface. O serviço `brisasync.service` iniciou automaticamente em segundo plano sob PID `2636` (`/usr/bin/python3 /usr/bin/brisasync --service --db-path /home/agreles/.local/share/brisasync/brisasync.db`).
     - *Abertura da Interface sem Duplicação*: Ao clicar no lançador do sistema, a interface abriu sob PID `5019` (`/usr/bin/python3 /usr/sbin/brisasync`), conectando-se ao daemon já em execução via socket AF_UNIX (`/run/user/1000/brisasync/service.sock`). O daemon manteve estritamente o PID `2636`, comprovando o contrato de processo único e simbiose sem concorrência.
     - *Estado Operacional Consolidado*: IPC ativo com `State: WAITING`, `Attention category: None`, `Last run status: SUCCESS`, `Autostart enabled: True` e `Auto sync paused: False`.
     - *Ressalva de Escopo*: O caso de cofre bloqueado na inicialização permanece **não testado** no desktop pessoal (para evitar bloqueio acidental da sessão do usuário) e será homologado em perfil descartável ou VM.
  3. **Preparação para o Próximo Teste: Instalação Limpa com Dependências Reais (Sem `--nodeps`)**:
     - *Diagnóstico de Recursos do Host*:
       - Presentes: `bubblewrap 0.13.0`, `fakeroot 1.37.2`, `systemd-nspawn` (`systemd 261.3`).
       - Não instalados: `podman`, `docker`, `distrobox`, `arch-install-scripts` (`pacstrap`), `qemu`.
     - *Proposta de Ambiente Mínimo Adequado*:
       - Utilização da **Fase 1 de [`docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md`](file:///home/agreles/Aplicativos/BrisaSync/docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md)** via contêiner headless Arch Linux oficial (`archlinux:base`).
       - *O que será comprovado*: Resolução completa de dependências pelo `pacman` (`python>=3.14`, `pyside6>=6.11`, `libsecret`, `libnotify`, `hicolor-icon-theme`) a partir dos repositórios oficiais `core` e `extra` sem `--nodeps`; integridade de metadados ALPM; execução de CLI (`--version`, `--help`, `--diagnose`) e integridade do `rclone v1.75.2` embutido.
       - *O que não pode ser comprovado em contêiner headless*: Fluxo gráfico OAuth no navegador, desbloqueio gráfico de chaveiro (pinentry/KWallet), ícone na bandeja do sistema (StatusNotifierItem) e notificações visuais na tela (demandam a Fase 2 / VM com desktop).
  4. **Matriz de Homologação Consolidada**:

| Cenário / Verificação | Estado | Evidência / Observações |
|---|---|---|
| **Autoinício na Sessão do Usuário** | **Aprovado** | `systemd --user` iniciou daemon PID 2636 no login; `systemctl --user is-active` reporta `active`. |
| **Instância Única e Conexão da UI** | **Aprovado** | UI PID 5019 abriu pelo lançador conectando-se ao PID 2636 sem duplicação de processos. |
| **Integridade de Configurações e Dados** | **Aprovado** | Banco SQLite, credenciais da sessão e pastas pessoais 100% íntegras; estado `WAITING` (em dia). |
| **Cofre Bloqueado na Inicialização** | **Não Testado** | Não declarado como testado no host para proteger a sessão pessoal; pendente para perfil isolado/VM. |
| **Instalação Limpa Sem `--nodeps`** | **Pronto para Execução** | Requisitos auditados; roteiro baseado no playbook entregue para validação em contêiner limpo. |
| **Homologação em GNOME Real** | **Pendente** | Validação de AppIndicator / libayatana e comportamento de bandeja no GNOME Shell. |
| **Publicação e Verificação OAuth** | **Pendente** | Submissão e aprovação da tela de consentimento junto ao Google Cloud Console. |

- **Histórico — Rodada 18**: Associação Contextual de Feedback Visual (Par Ativo vs Tentativa vs Histórico Superado) e Pacote v0.1.9:
  1. **Diagnóstico da Rejeição Residual de Itens Removidos**:
     - *Causa comprovada*: O usuário tentou parear a pasta local `/home/agreles/Músicas/Mensagens` com o Drive às 16:35, gerando `[REJEITADA]` em `remote_folder_feedback_label` devido aos 23 itens pré-existentes (incluindo `Mario`). Posteriormente, o usuário selecionou e salvou uma pasta válida (`/home/agreles/Músicas/Mensagem para um Dia Melhor`), e a sincronização concluiu com sucesso às 16:53 (Run 4, status `SUCCESS`), seguida de sincronizações incrementais automáticas às 16:59 (Run 5) e 17:04 (Run 6).
     - *Defeito visual*: O rótulo `remote_folder_feedback_label` na aba *Pastas* não era recalculado ou sincronizado quando a pasta local era salva ou quando o ciclo era bem-sucedido. Como o processo da UI permaneceu aberto sem reiniciar, a mensagem estática de rejeição continuou visível, citando arquivos antigos que já não existiam ou não pertenciam ao par ativo.
     - *Comportamento do Hero Banner, Pílula Global e Badge de Pasta*: Na captura de tela das 16:35 enviada pelo usuário, todos esses componentes estavam vermelhos com precisão operacional legítima, pois naquele exato momento o daemon encontrava-se em `ATTENTION_REQUIRED` devido à pasta não vazia. Assim que a nova pasta válida foi salva e sincronizada, o daemon transitou para `WAITING` (saudável), e todos esses componentes passaram para o estado verde ("Tudo em dia"). Apenas o rótulo local de feedback de seleção da pasta remota ficou desatualizado.
  2. **Tratamento Contextual de Feedback Sem Limpeza Genérica**:
     - Implementado em `BrisaMainWindow` rastreamento contextual via `_pending_remote_rejection` e `_pending_local_rejection` associados ao `(local_path, remote_folder_id)` e texto de erro de cada tentativa.
     - Distinção estrita entre:
       1. **Par ativo salvo**: refletido com precisão baseando-se nas configurações persistidas no banco e no estado operacional do daemon.
       2. **Nova seleção ainda não confirmada**: caso inválida, mantém seu feedback de rejeição isolado sem ser apagado por execuções bem-sucedidas do par ativo.
       3. **Erro histórico superado**: quando uma seleção válida é salva e substitui a tentativa anterior rejeitada (ou quando a baseline é inicializada com sucesso), os rótulos contextuais são atualizados automaticamente sem exigir fechamento ou reabertura da janela.
     - Preservação integral do histórico no SQLite: nenhum registro de erro anterior em `sync_runs` foi apagado ou alterado.
  3. **Regressão Automatizada (Ciclo de 5 Etapas)**:
     - Adicionado teste `test_feedback_labels_distinguish_saved_pair_overcome_errors_and_new_rejections` em `tests/test_attention_diagnostics_and_precheck.py` cobrindo o ciclo completo:
       1. Rejeição de um destino inadequado (pasta populada).
       2. Configuração e salvamento de destino válido.
       3. Conclusão de sincronização com sucesso.
       4. Atualização imediata de toda a interface sem reabertura da janela.
       5. Tentativa de nova escolha inválida mantendo a rejeição intacta a despeito do sucesso do par ativo.
  4. **Novo Pacote v0.1.9 e Integridade dos Artefatos**:
     - Incremento de versão para `0.1.9` em `pyproject.toml`, `src/brisasync/__init__.py`, `packaging/build_packages.sh`, `packaging/arch/PKGBUILD` e testes.
     - Todos os artefatos anteriores (`0.1.0` a `0.1.8`) estritamente preservados em `dist/`.
     - Novos pacotes gerados em `dist/`:
       - `dist/brisasync-0.1.9-1-x86_64.pkg.tar.zst` (SHA-256: `065a786b06ec604db63e77bf732d117c014df8e1644309469c4090e85125fe02`)
       - `dist/brisasync-0.1.9-2-x86_64.pkg.tar.zst` (SHA-256: `bb1a0fe349c793d529411d479c75b362779363a41669b7f524e86216f40d9ff0`)
       - `dist/brisasync-0.1.9-py3-none-any.whl` (SHA-256: `09d6aab5f93fdd8c580574f975cb99aabb7b505a59a4ac901762aeb0ad8cd99d`)
       - `dist/brisasync-0.1.9.tar.gz` (SHA-256: `13b712222a769851bdbd3210eb440a36dad592637243ba1688c39dce831f47b3`)
     - Validação completa do pacote ALPM em sandbox `bwrap` + `fakeroot` com ciclo install -> upgrade -> remove aprovado em 100%.

- **Histórico — Rodada 17**: Homologação da Instalação Real (v0.1.8-1) no Ambiente do Mantenedor:
  1. **Auditoria de Processos e Desacoplamento da Checkout**:
     - Pacote instalado comprovado via `pacman -Qi brisasync`: versão `0.1.8-1`, compilado em `sex 30 out 2026 16:03:47` e instalado no sistema em `sex 30 out 2026 16:20:12`.
     - Mapeamento de processos ativos na sessão: UI (PID `4907`) e Daemon (PID `5066`), ambos executando sob `/usr/bin/python3` com cwd `/home/agreles` e carregando módulos exclusivamente de `/usr/lib/python3.14/site-packages/brisasync/`, sem nenhuma dependência da pasta de desenvolvimento nem de ambiente virtual (`.venv`).
     - Comunicação inter-processos saudável e unificada via sockets AF_UNIX (`/run/user/1000/brisasync/service.sock` e `ui.sock`).
  2. **Verificação do Funcionamento Cotidiano e Instância Única**:
     - Lançador `.desktop` íntegro em `/usr/share/applications/brisasync.desktop` com metadados `StartupWMClass=brisasync` e categorias adequadas.
     - Invocação única testada: chamadas subsequentes ao executável `/usr/bin/brisasync` ativam a janela existente via `try_activate_existing_ui` e encerram imediatamente (código 0), sem gerar processos duplicados ou conflito de concorrência.
     - Operações de controle via IPC testadas: pausa (`auto_sync_paused: True`) e retomada (`auto_sync_paused: False`) funcionando em tempo real.
     - Contrato do diálogo "Sair..." preservado com as 3 ações (Cancelar, Manter sincronização e Encerrar tudo).
  3. **Diagnóstico do Estado de Atenção e Preservação de Dados**:
     - Comprovada a atuação da v0.1.8 na instalação real: estado `ATTENTION_REQUIRED` com diagnóstico específico `Pasta Local Não Dedicada ou Não Vazia` para o par remanescente, com agendador periódico pausado de forma segura (`next_scheduled_sync_at: None`), eliminando retentativas destrutivas em loop.
     - Dados do usuário rigorosamente preservados: `/home/agreles/Android/brisa`, `/home/agreles/Músicas/Mensagens` e banco SQLite `~/.local/share/brisasync/brisasync.db` intactos.
  4. **Matriz Objetiva de Homologação**:

| Componente / Cenário | Status | Evidência / Justificativa |
|---|---|---|
| **Pacote Instalado ALPM** | **Aprovado** | `brisasync 0.1.8-1` instalado pelo `pacman`, com `rclone v1.75.2` em `/usr/lib/brisasync/bin/`. |
| **Diagnóstico CLI do Sistema** | **Aprovado** | `/usr/bin/brisasync --diagnose` com `all_critical_ok: true`, Python 3.14.7, Qt 6.11.2, Secret Service validado. |
| **Mapeamento de Processos** | **Aprovado** | UI (PID 4907) e Daemon (PID 5066) ativos, comunicando via `service.sock` e `ui.sock`, sem duplicações. |
| **Instância Única da UI** | **Aprovado** | Invocação de `/usr/bin/brisasync` ativa UI existente e encerra (código 0) sem processos duplicados. |
| **Controle de Serviço (Pausa/Retomada)** | **Aprovado** | Comandos `pause` e `resume` via IPC executados com alternância do estado `auto_sync_paused`. |
| **Proteção de Dados e Configuração** | **Aprovado** | Pastas pessoais e banco SQLite 100% íntegros; credenciais seguras no cofre da sessão. |
| **Diagnóstico Específico de Bloqueio** | **Aprovado** | Daemon reporta com precisão `Pasta Local Não Dedicada ou Não Vazia` e pausa agendamento. |
| **Autoinício `systemd --user`** | **Pendente de Ação Manual** | Unit validada em `/usr/lib/systemd/user/`; aguarda teste voluntário de logout/login do mantenedor. |
| **Sincronização em Nuvem Isolada** | **Bloqueado por Config. Externa** | Sem perfil secundário com credenciais de teste na nuvem; dados pessoais protegidos contra testes. |

  5. **Próximos Passos**:
     - Realização do teste manual de logout/login pelo mantenedor usando o roteiro fornecido.
     - Homologação em sistema limpo (VM / Arch Linux / GNOME) conforme [`docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md`](file:///home/agreles/Aplicativos/BrisaSync/docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md).
     - Verificação e submissão da tela de consentimento Google OAuth como etapa administrativa externa separada.

- **Histórico — Rodada 16**: Diagnóstico de Bloqueio em Novo Par com Destino Local Não Vazio, Pré-checagem e Entrega v0.1.8.
  1. **Diagnóstico do Bloqueio RECOVERY_REQUIRED**:
     - Causa identificada e comprovada: configuração de um novo par de sincronização (`local_sync_folder`: `/home/agreles/Android/brisa` com `remote_sync_folder`: `1dNg_DGIOwbditFPulWldEjMUjdVcTe_n` — *"Mensagens para Um dia Melhor"*) sobre uma pasta local preexistente que continha 6 itens remanescentes da baseline anterior (*"Documentos"*).
     - Comprovação de segurança: a proteção `validate_directory_empty_for_initial_sync` bloqueou a operação antes do disparo de qualquer subprocesso do rclone bisync, mantendo os arquivos locais e remotos 100% intactos e sem execução de resync ou dedupe.
  2. **Validação Prévia e Rejeição Proativa Antes de Ativar Agendamento**:
     - `BrisaMainWindow._on_remote_folder_selection_changed`: quando o usuário seleciona uma nova pasta remota cuja baseline ainda não foi inicializada com a pasta local configurada, se a pasta local contiver itens, a seleção é imediatamente rejeitada. O combobox reverte para a pasta remota anterior sem disparar sinais espúrios, o banco de dados preserva a configuração válida e uma mensagem orienta: *"Status da pasta remota: [REJEITADA] Configuração rejeitada: Para iniciar a sincronização com '<pasta>', a pasta local deve estar dedicada e vazia (...). Escolha outra pasta local vazia antes de alterar a pasta remota."*
     - `BrisaMainWindow.save_and_validate_folder`: validação simétrica ao alterar a pasta local para um diretório povoado quando o par remoto selecionado não possui baseline prévia. A alteração é rejeitada, o campo reverte para o caminho anterior válido, o banco é preservado e orienta a escolher outra pasta vazia.
     - `BrisaSessionServiceDaemon._check_preconditions_before_cycle`: verificação no daemon antes do início de qualquer ciclo ou ativação do agendador periódico. Se o par não inicializado contiver arquivos locais, o ciclo é bloqueado, o agendamento periódico é pausado (`_next_scheduled_epoch = None`) e o estado é classificado precisamente como `STATE_ATTENTION_REQUIRED`.
     - `SyncCoordinator.synchronize_google_drive_pair`: auditoria de pré-checagem registrada no banco SQLite (`operation="baseline_precheck"`, `status="ATTENTION_REQUIRED"`), viabilizando inspeção detalhada pelo usuário no histórico.
  3. **Classificação Específica de Causas de Atenção**:
     - Substituição do texto genérico com lista de hipóteses especulativas por diagnósticos técnicos individualizados (pasta não vazia, limite de exclusão atingido, marcador ausente, erro de permissão ou motivo desconhecido com detalhe técnico real).
     - Botão *"Inspecionar"* no Hero Banner e *"Ver Detalhes..."* no banner de atenção abrem diálogo modal dedicado (`SyncRunDetailsDialog`).
  4. **Versionamento e Integridade dos Pacotes (v0.1.8)**:
     - Versionamento `0.1.8` definido em `pyproject.toml`, `src/brisasync/__init__.py`, `packaging/build_packages.sh`, `packaging/arch/PKGBUILD` e suíte de testes.
     - Preservação estrita de todos os artefatos anteriores existentes em `dist/` (0.1.0 a 0.1.7).
     - Construção dos artefatos oficiais 0.1.8 em `dist/` com `uv` e `makepkg` (rel 1 e rel 2) e geração de somas SHA-256 criptograficamente verificadas.
     - 100% dos 51 testes automatizados aprovados (incluindo isolamento completo em sandbox Bubblewrap com ALPM pacman nativo).
- **Histórico — Rodada 15**: Refinamento de Interface, Encerramento Unificado e Responsividade (v0.1.7).
  1. **Botões da Barra Lateral Atômicos e Foco Unificado**:
     - Implementado widget customizado `BrisaSidebarNavItem(QAbstractButton)` em `src/brisasync/ui/main_window.py`.
     - Desenho vetorial direto com `QPainter` e `QPainterPath`, eliminando a moldura retangular de foco (`PE_FrameFocusRect`) sobre o texto dos itens selecionados.
     - Padronização: altura 42px, cantos arredondados de 10px, ícones vetoriais alinhados de 18-20px, texto claro, fundo lavanda suave com indicador lateral de 3px para seleção ativa, hover sutil e foco de teclado nítido envolvendo o botão por inteiro (`QRectF` com pen `#9189FF`).
     - Badge/contador perfeitamente integrado na mesma linha sem alterar a altura do botão nem parecer botão separado.
  2. **Diálogo Unificado de Encerramento ("Sair…")**:
     - Substituição dos botões duplos de saída na bandeja, menu de opções e configurações por uma ação única "Sair…".
     - Diálogo modal dedicado `BrisaExitDialog` ("Sair do BrisaSync" / "Deseja manter a sincronização em segundo plano?"), com escolhas claras e consequências explícitas:
       - *"Manter sincronização"*: Fecha janela e bandeja, mantendo o serviço ativo em segundo plano (com aviso de que o painel pode ser reaberto pelo lançador).
       - *"Encerrar tudo"*: Interrompe ciclos ativos de forma controlada (`stop_current` com polling de até 4s) e finaliza o serviço de sessão, interface e bandeja sem recorrer a `SIGKILL` destrutivo.
       - *"Cancelar"*: Fecha o diálogo sem nenhuma alteração no estado.
     - Proteção de instância única (`open_exit_dialog`), trazendo o diálogo em primeiro plano se a janela gráfica estiver minimizada na bandeja.
  3. **Responsividade e Adaptação Dinâmica (Breakpoint 960px)**:
     - Implementado `_apply_responsive_layout(width)` em `BrisaMainWindow` reagindo ao `resizeEvent`.
     - Transição suave entre layout de 2 colunas e 1 coluna empilhada em larguras menores que 960px.
     - Reorganização do cabeçalho do Hero Status Banner (ações passam para linha dedicada abaixo do título/subtítulo quando a largura é estreita) e ocultação da pílula global do topo em telas estreitas para não truncar e-mail ou opções.
     - Eliminação de rolagem horizontal desnecessária com `ScrollBarAlwaysOff`.
  4. **Coerência de Estados e Eliminação de Mensagens Contraditórias**:
     - Ocultação imediata do quadro ocioso ("Nada para transferir") quando o serviço entra em estado de atenção ou recuperação.
     - Substituição dinâmica por banner de alerta detalhado com categoria de atenção, causas e botão "Inspecionar".
     - Atualização coerente das pílulas de status das pastas (`overview_folder_status_pill` e `folders_card_status_pill`), refletindo `● Bloqueado` ou `● Recuperação pendente` em vermelho durante falhas de integridade ou exclusão em massa.
  5. **Diagnóstico Preciso de Bloqueios e Auditoria de Pré-checagens**:
     - Eliminada a enumeração de hipóteses especulativas `(limite de exclusão em massa atingido, marcador .brisasync_check ausente ou pasta inacessível)` em `BrisaSessionServiceDaemon._classify_attention_details_locked`.
     - Implementada classificação precisa para motivos conhecidos:
       - *Pasta Local Não Dedicada ou Não Vazia*: Exibe detalhe exato dos itens encontrados na pasta local quando um novo par remoto é configurado.
       - *Proteção contra Exclusão em Massa*: Exibe o número de arquivos detectados e o limite de corte.
       - *Marcador de Integridade Ausente*: Indica explicitamente `.brisasync_check` ausente ou ilegível.
       - *Pasta Inacessível ou Inexistente*: Apresenta erro de acesso e caminho.
       - *Motivo Desconhecido*: Exibe expressamente *"Motivo ainda não identificado. Detalhe técnico: <erro>"*, sem hipóteses especulativas.
     - `SyncCoordinator.synchronize_google_drive_pair` agora registra falhas de validação prévia na tabela `sync_runs` com status `ATTENTION_REQUIRED`, permitindo auditoria no histórico e abertura do diálogo técnico `SyncRunDetailsDialog`.
     - Na interface gráfica, adicionado botão *"Ver Detalhes..."* no banner de atenção e suporte a diálogo técnico dedicado [`_show_attention_details_dialog`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/main_window.py).
  6. **Empacotamento e Entrega v0.1.7**:
     - Versionamento `0.1.7` em `pyproject.toml`, `src/brisasync/__init__.py`, `packaging/build_packages.sh`, `packaging/arch/PKGBUILD` e testes.
     - Novos pacotes gerados em `dist/`: `brisasync-0.1.7-1-x86_64.pkg.tar.zst`, `brisasync-0.1.7-2-x86_64.pkg.tar.zst`, wheel e sdist com checksums SHA-256 calculados e validados.
     - Suíte completa de testes automatizados com novos testes dedicados em `tests/test_attention_diagnostics_and_precheck.py` e `tests/test_v017_ui_refinements.py` (49 testes aprovados com 100% de sucesso).
- **Histórico — Rodada 14**: Redesenho Visual Completo do BrisaSync (v0.1.6 — Barra Lateral + Painel em Cartões).
- **Histórico — Rodada 13**: Reorganização Visual e Minimalismo (v0.1.5).
- **Histórico — Rodada 12**: Correção da Abertura Gráfica e Inicialização do Serviço de Sessão (v0.1.4).
  1. **Assistente Inicial Guiado com Fluxo Passo a Passo**:
     - Substituição da apresentação estática por um assistente guiado em `QStackedWidget` com uma etapa ativa por vez: `1. Conectar Conta → 2. Pasta do Drive → 3. Pasta Local → 4. Revisar e Iniciar`.
     - Indicador discreto de progresso (*breadcrumb*) com destaque na etapa ativa e indicação de etapas concluídas.
     - Navegação completa entre etapas (`[← Voltar]` e `[Avançar →]`), preservando as escolhas sem reconectar conta nem reinicializar o banco de dados.
     - Na etapa 4 (Revisão): resumo dos dados (conta, pasta remota com ID, pasta local) e quadro explicativo sobre sincronização bidirecional, propagação de exclusões para a lixeira e segurança de integridade em conflitos.
  2. **Remoção de Jargões Técnicos do Assistente**:
     - Removida a frase "Origem do cliente OAuth..." e caminhos de arquivos JSON da tela inicial (mantidos exclusivamente em *Ajuda > Diagnóstico* e *Configurações > Avançado*).
     - Com o cliente embutido disponível, o fluxo normal exibe simplesmente o botão "Conectar Conta Google".
     - Subtítulo atualizado para descrição objetiva e sem promessas infladas de backup: *"Mantenha seus arquivos sincronizados e disponíveis offline."*
  3. **Cabeçalho Compacto, Dimensões e Prevenção de Truncamento**:
     - Implementada elipse deliberada no e-mail do cabeçalho com preservação de domínio (`_format_elided_email(email, 20)`) e tooltip completa (`Conta conectada: <email>`), sem truncamento acidental contra o botão "Configurar".
     - Dimensões padrão ajustadas para ~750 × 510 (mínimo 660 × 440), preenchendo harmoniosamente a janela sem o grande vazio inferior das versões anteriores.
  4. **Tela de Uso Diário Refinada e Sem Redundâncias**:
     - Exibição de *"✓ Tudo atualizado"* estritamente condicionada a uma conclusão de sincronização confirmada com horário local formatado (*"Hoje às HH:MM:SS"* ou data completa). Quando configurado antes da 1ª execução, exibe *"● Aguardando primeira sincronização"*.
     - Botões de ação simplificados: exibe *"Sincronizar Agora"* e apenas *"Pausar"* OU *"Retomar"*, alternando conforme o estado operacional.
     - Parada controlada (*"Parar Sincronização"*) disponibilizada como ação secundária exibida exclusivamente durante operações ativas (`STATE_SYNCING` / `STATE_VERIFYING`), permanecendo oculta na operação normal em repouso.
     - Remoção de repetições desnecessárias da conta no corpo da tela inicial cotidiana.
  5. **Versionamento e Construção dos Pacotes v0.1.3**:
     - Versão incrementada para `0.1.3` em `src/brisasync/__init__.py`, `pyproject.toml`, `packaging/arch/PKGBUILD`, `packaging/build_packages.sh` e testes de verificação.
     - Gerados pacotes `brisasync-0.1.3-1-x86_64.pkg.tar.zst`, `brisasync-0.1.3-2-x86_64.pkg.tar.zst`, `brisasync-0.1.3-py3-none-any.whl` e `brisasync-0.1.3.tar.gz`, mantendo todos os artefatos históricos das Rodadas 6 a 9 em `dist/`.
     - Todos os 41 testes automatizados aprovados com 100% de sucesso.
- **Nota de Escopo e Distinção de Ambientes**:
  - **Validado automaticamente (`pytest` — 41 testes)**: Cobrindo integridade `rclone bisync`, OAuth/PKCE/cofre/ponte cifrada, serviço de sessão/IPC/backoff/autostart, ícones claro/escuro e 1x/HiDPI independentes de `cwd`, bandeja via IPC, modo sem bandeja, notificações deduplicadas/sanitizadas, sanidade e pureza do pacote ALPM (zero segredos/testes/tokens/bancos), ciclo de vida ALPM via `fakeroot pacman -r`, execução em sandbox Bubblewrap (`bwrap`) com checkout mascarada por `--tmpfs` e `$HOME` limpo (CLI, `--diagnose`, serviço IPC, `--no-tray`, autostart e preservação de dados do usuário).
  - **Validado visualmente na sessão gráfica (750 × 510, HiDPI e temas)**: 8 telas capturadas da interface v0.1.3 comprovando:
    1. Início Cotidiano — Tudo Atualizado (sessão real, horário local, sem redundâncias).
    2. Início Cotidiano — Sincronizando (com ação secundária "Parar Sincronização" visível).
    3. Início Cotidiano — Pausado (com botão "Retomar" visível e "Pausar" oculto).
    4. Início Cotidiano — Atenção Necessária (com banner acionável e botão "Ver no Histórico").
    5. Assistente Inicial — Etapa 1: Conectar Conta Google (sem menção a JSON).
    6. Assistente Inicial — Etapa 2: Pasta no Google Drive (dropdown com IDs e criação de pasta).
    7. Assistente Inicial — Etapa 3: Pasta Local (validação de pasta vazia e dedicated).
    8. Assistente Inicial — Etapa 4: Revisar e Iniciar (resumo dos destinos e explicação sobre bidirecionalidade e exclusões).
- **Limites da validação de pacotes registrados expressamente**:
  1. Testes com `--nodeps` / root isolado validam estrutura interna de arquivos, mas não garantem resolução automática de dependências em repositórios de terceiros.
  2. O sandbox Bubblewrap no host compartilha bibliotecas dinâmicas do sistema e não substitui uma instalação em máquina virtual/contêiner de SO zerado (clean-slate OS install).
  3. Os artefatos em `dist/` são pacotes de teste do próprio projeto BrisaSync, sem homologação ou distribuição oficial do Arch Linux, Manjaro ou BigLinux.
  4. O aplicativo permanece em status **Testing** no Google Cloud Console para contas cadastradas. Não há declaração de login público geral irrestrito nem aprovação de verificação do Google.

---

## 1. Implementado

### 1.1. Garantias de Integridade e Orquestração (`backend/` e `orchestrator/`)
- **Sincronização Bidirecional Real (`RcloneBisyncEngine`)**:
  - Uso exclusivo de `rclone bisync` com `--compare size,modtime,checksum`, `--conflict-resolve none`, `--conflict-loser num`, `--check-access` (`.brisasync_check`), `--recover`, `--resilient` e `--max-lock 2m`.
  - Proibição explícita de `--force` e de `--resync` implícito após falhas.
  - Execução via `subprocess.Popen` com registro do processo ativo para parada controlada via `SIGTERM` único (`request_graceful_stop`), registrando `STOPPED_BY_USER` sem atualizar o timestamp de `"Atualizado"`.
- **Proteção Dupla contra Exclusões em Massa (Limite Percentual + Limite Absoluto)**:
  - No `rclone v1.75.2`, `--max-delete` no `bisync` aceita apenas porcentagem inteira (`0–100%`).
  - O `RcloneBisyncEngine` impõe tanto `max_delete_percent = 50` (`%`) quanto o limite absoluto explícito `max_delete_abs = 25` (arquivos excluídos em um único ciclo), inspecionando as listagens `bisync listing v1` (`*.path1.lst` e `*.path2.lst`) antes de propagar qualquer exclusão.
- **Identificação Forte do Proprietário de Lock (Contra Reutilização de PID)**:
  - `SyncCoordinator._check_active_rclone_lock_owner()` verifica `/proc/<pid>/stat` (estado não-zumbi e `starttime` no campo 22 convertido para epoch) e `/proc/<pid>/cmdline` / `comm`.
  - Um lock `.lck` só bloqueia por processo ativo se o `PID` pertencer genuinamente a um processo `rclone` iniciado antes ou no momento da gravação do `.lck`, protegendo contra reciclagem de PID pelo kernel e expirando/liberando travas órfãs após o encerramento do proprietário, sem jamais remover o lock de um processo `rclone` ativo.
- **Isolamento de `backup_dir2` e Validação contra `root_folder_id`**:
  - `validate_paths_non_overlapping()` e `verify_remote_backup_outside_selected_tree()` garantem que `backup_dir2` pertence ao mesmo backend remoto (`brisasync_gdrive:`) e permanece fora da árvore remota selecionada, rejeitando configurações em que `root_folder_id` mude a raiz visível do remote para a própria pasta sincronizada.

### 1.2. OAuth 2.0 Google Desktop, Cofre da Sessão e Ponte Cifrada (`credentials/`)
- **Cliente OAuth Desktop (`GoogleOAuthDesktopClient`)**:
  - Normaliza `auth_uri` para o endpoint v2 (`https://accounts.google.com/o/oauth2/v2/auth`), usa Authorization Code + PKCE `S256`, `state` de 256 bits (`hmac.compare_digest`), `prompt=consent`, listener HTTP estrito em `127.0.0.1:0` com timeout, cancelamento e `server_close()`, renovação via `refresh_token` e tratamento de `access_denied` e `invalid_grant`.
  - Valida explicitamente os escopos concedidos na resposta de tokens: se faltar `https://www.googleapis.com/auth/drive`, revoga o token parcial e informa claramente `"Acesso ao Google Drive não concedido"`, sem iniciar sincronização nem marcar a conta como pronta.
- **Cofre da Sessão (`CredentialStore`) e Diagnóstico Operacional**:
  - Persistência no Secret Service (`secret-tool`) / KDE Wallet (`kwallet-query`) com lock reentrante por thread e exclusivo entre processos (`acquire_credentials_lock()`).
  - Diagnóstico distingue explicitamente *"utilitário instalado"* de *"cofre acessível e operação validada"* mediante ciclo real com segredo descartável (`probe_<uuid4>`).
- **Ponte Cifrada (`RcloneEncryptedBridge`)**:
  - Criptografia de configuração nativa do `rclone` (`RCLONE_ENCRYPT_V0:` em `fs/config/crypt.go`), que deriva uma chave de 32 bytes via `SHA-256` (`sha256.Sum256`) e autentica/cifra o arquivo com NaCl `secretbox` (`XSalsa20-Poly1305`) — distinta do backend de armazenamento `crypt` (que usa `scrypt`). Por usar `SHA-256` direto, o BrisaSync alimenta `RCLONE_ENCRYPT_V0:` com uma chave aleatória de 256 bits gerada por CSPRNG e guardada no cofre da sessão.
  - Montagem transitória em `/dev/shm` (`tmpfs`) com criação exclusiva (`mkstemp` / `O_CREAT | O_EXCL`, permissões `0700`/`0600`) e sobrescrita com zeros + remoção imediata em `finally`. Documentado que `/dev/shm` (`tmpfs`) reduz exposição em disco, mas não impede paginação para swap caso o sistema tenha swap ativo sem criptografia.
  - Tratamento de falha ao devolver tokens renovados ao cofre (`CredentialSyncBackError`): se a gravação no cofre falhar após o `rclone` renovar o token no `rclone.conf` cifrado, a operação registra `FAILED_CREDENTIAL_PERSISTENCE` (nunca sucesso), preserva o `rclone.conf` cifrado com a única credencial atualizada e reconcilia o token mais recente para o cofre na sessão seguinte.

### 1.3. Serviço da Sessão do Usuário, Controle IPC Local e Agendamento (`service/`)
- **Propriedade Única da Execução (`BrisaSessionServiceDaemon` em `src/brisasync/service/daemon.py`)**:
  - O serviço sem root (`brisasync --service`) é o único proprietário do agendamento periódico e dos processos `rclone bisync`. A interface gráfica (`BrisaMainWindow`) e a bandeja (`BrisaTrayController`) não executam `rclone bisync` diretamente; consultam e controlam o serviço exclusivamente via `ServiceIPCClient`.
  - Lock exclusivo de instância única (`fcntl.flock(LOCK_EX | LOCK_NB)`) impede que duas interfaces ou invocações iniciem serviços concorrentes (`ServiceAlreadyRunningError`).
- **IPC Local Restrito ao Usuário da Sessão (`src/brisasync/service/protocol.py` e `ipc_client.py`)**:
  - Socket Unix (`socket.AF_UNIX`) em `$XDG_RUNTIME_DIR/brisasync/service.sock` (diretório `0700`, socket `0600`), sem expor nenhuma porta TCP na rede.
  - Verificação de credenciais no kernel via `SO_PEERCRED` (`verify_peer_credentials`), aceitando conexões somente quando `peer_uid == os.getuid()`.
- **Ciclos Automáticos, Coalescência e Espera Progressiva**:
  - Reconciliação periódica configurável (`sync_interval_seconds`, padrão `300s` / 5 minutos).
  - Coalescência: solicitações repetidas de `sync_now` durante um ciclo ativo são agrupadas em uma única flag (`pending_sync_coalesced = True`), garantindo no máximo 1 ciclo subsequente sem concorrência.
  - Espera progressiva exponencial (`SEM CONEXÃO`): falhas transitórias/rede dobram progressivamente o tempo de espera (`base * 2^(n-1)` até o teto de `900s`), evitando consultas contínuas ao Google Drive.
- **Pausar, Retomar e Parada Controlada**:
  - Distinção real entre **`PAUSANDO` (`PAUSING`)** (quando a pausa é solicitada durante um ciclo ativo, aguardando término seguro sem usar `SIGSTOP`) e **`PAUSADO` (`PAUSED`)** (quando nenhum ciclo está em execução).
  - Preferência `auto_sync_paused` persistida no SQLite (`app_settings`) para que reiniciar o serviço ou a janela nunca retome contra a escolha do usuário.
  - Parada controlada (`stop_current`) envia um único `SIGTERM` ao processo `rclone bisync`, preservando estado recuperável para o próximo ciclo (`--recover`).
- **Autoinício Opcional (`SystemdUserAutostartManager` em `src/brisasync/service/autostart.py`)**:
  - Ativa exclusivamente um mecanismo reversível sem `sudo`: a unit `systemd --user` em `~/.config/systemd/user/brisasync.service`, verificando ausência de arquivos `.desktop` concorrentes em `~/.config/autostart`.
  - Se o cofre da sessão estiver bloqueado (`VaultUnavailableError`), o serviço permanece em `ATENÇÃO NECESSÁRIA` sem abrir o navegador repetidamente.

### 1.4. Identidade Visual, Bandeja Opcional, Modo Sem Bandeja e Notificações (`ui/`)
- **Identidade Visual Oficial (`src/brisasync/ui/icons.py` e `resources/`)**:
  - Ícone colorido oficial (`brisasync.png` em `hicolor` `16, 24, 32, 48, 64, 128, 256, 512, 1024px`) aplicado em `QApplication.setWindowIcon()`, `BrisaMainWindow.setWindowIcon()`, logo do cabeçalho com suporte a escala normal (`1x`) e HiDPI (`1.5x`, `2x`) e lançador `resources/desktop/brisasync.desktop` (`Icon=brisasync`, `StartupWMClass=brisasync`).
  - Adaptação simbólica para a bandeja (`resolve_tray_icon_for_mode` e `load_tray_icon`): como o `QtSvg` (`PySide6 6.11.2 / Qt 6.11.2`) renderiza `fill="currentColor"` no `brisasync-symbolic.svg` como preto estático (`#000000`), o BrisaSync carrega as variantes PNG fixas multi-resolução (`16, 22, 24, 32, 48px`): variante `light` (`#eff0f1`) para painéis escuros e variante `dark` (`#232629`) para painéis claros, com detecção automática ou seleção explícita na interface (`auto`, `dark_panel`, `light_panel`) sem alterar o tema global do desktop.
  - Resolução de caminhos baseada em `Path(__file__).resolve()`, garantindo carregamento independentemente do diretório de trabalho (`os.getcwd()`).
- **Bandeja Opcional (`BrisaTrayController` em `src/brisasync/ui/tray.py`) e Instância Única da UI (`UISingleInstanceServer` em `src/brisasync/ui/single_instance.py`)**:
  - Mantida viva exclusivamente pelo processo gráfico (`QApplication` com `setQuitOnLastWindowClosed(False)` quando a bandeja está ativa), sem adicionar qualquer dependência gráfica ao daemon `brisasync --service`.
  - Menu real da bandeja contendo:
    1. Cabeçalhos informativos (`Estado: [...]` e `Atualizado: [...]`).
    2. **Abrir Painel** (`restore_and_focus_window`).
    3. **Abrir Pasta Local** (`open_configured_local_folder` via `QDesktopServices.openUrl`).
    4. **Sincronizar Agora** (`sync_now` via IPC).
    5. **Pausar / Retomar Sincronização Automática** (`pause` / `resume` via IPC).
    6. **Encerrar Interface / Bandeja (Manter Serviço)** (`quit_graphical_component_keep_service`).
    7. **Encerrar Serviço de Sincronização** (`shutdown_service` via IPC).
  - Ao reabrir o aplicativo pelo lançador enquanto a janela está oculta na bandeja, `try_activate_existing_ui()` envia `{"action": "show_window"}` ao socket local `$XDG_RUNTIME_DIR/brisasync/ui.sock` (protegido por `SO_PEERCRED`), fazendo o processo gráfico existente restaurar e focar a janela sem duplicar janelas, ícones de bandeja ou serviços.
- **Funcionamento Completo Sem Bandeja**:
  - Detecta disponibilidade real via `QSystemTrayIcon.isSystemTrayAvailable()` e aceita `--no-tray`.
  - Quando não há bandeja disponível, não exige nenhuma extensão do GNOME e jamais esconde a única janela em segundo plano sem bandeja (`setQuitOnLastWindowClosed(True)`).
  - Diferencia explicitamente na interface as três ações de ciclo de vida: (1) Fechar a janela e manter sincronização; (2) Encerrar o componente gráfico mantendo o serviço; (3) Encerrar o serviço de sincronização.
- **Notificações Configuráveis, Agrupadas, Deduplicadas e Sanitizadas (`NotificationManager` em `src/brisasync/ui/notifications.py`)**:
  - Controladas pela preferência persistida `notifications_enabled` no SQLite.
  - Emitidas exclusivamente para as 4 categorias de atenção classificados pelo serviço (`BrisaSessionServiceDaemon._classify_attention_details_locked`):
    1. `AUTH_EXPIRED` (autenticação expirada/revogada ou cofre da sessão bloqueado).
    2. `CONFLICT_DETECTED` (arquivos `.conflict*` preservados lado a lado, agrupados em um único alerta por contagem).
    3. `PERSISTENT_FAILURE` (falhas consecutivas de rede/remoto com espera progressiva ativa).
    4. `RECOVERY_REQUIRED` (bloqueio preventivo de exclusão em massa, falha ao persistir token renovado no cofre ou erro de configuração/recuperação).
  - Nunca emite notificação por arquivo individual nem por ciclo concluído com sucesso (`SUCCESS`).
  - Deduplica por chave de estado `(attention_category, conflict_files_count, bool(backoff_attempt >= 2))` para evitar repetição contínua do mesmo erro, rearmando apenas quando a condição é resolvida (`attention_category is None`) ou muda de categoria/contagem.
  - Sanitiza título e corpo via `sanitize_notification_text()` (removendo tokens OAuth, chaves `RCLONE_ENCRYPT_V0:`, endereços de e-mail e caminhos completos) e espelha exatamente o mesmo alerta no quadro **"Status de Atenção"** da janela principal (`attention_explanation_label`).

### 1.5. Primeiro Pacote Instalável (ALPM), Sanidade e Validação Isolada (`packaging/` e `tests/`)
- **Classificação Precisa de Conflitos (`_count_local_conflict_files`)**:
  - Conflitos agora são vinculados estritamente às operações registradas pelo backend `rclone bisync` durante a execução (`extract_recorded_conflict_files` e persistência em `recorded_conflicts::<hash>` no banco SQLite).
  - Um arquivo legítimo do usuário com nome contendo `.conflict1` ou `.conflict2` jamais dispara sozinho um alerta falso de conflito.
  - Arquivos do usuário nunca são renomeados ou excluídos com base em suposições sintáticas de nome.
- **Separação entre Verificação Programática e Observação Visual**:
  - `QSystemTrayIcon.isVisible()` reflete apenas o estado do objeto no Qt; o status do painel do sistema (`isSystemTrayAvailable()`) e a observação humana visual foram formalmente separados na documentação e testes.
- **Empacotamento Nativo Arch/ALPM (`PKGBUILD` + `makepkg` em `packaging/arch/`)**:
  - Construção oficial de `brisasync-0.1.0-1-x86_64.pkg.tar.zst` e `brisasync-0.1.0-2-x86_64.pkg.tar.zst` para teste de atualização.
  - Inclusão do motor de sincronização `rclone v1.75.2` (linux/amd64, SHA-256 `ed7ab1f17876bb006c3df3949a3044959671afd9112362dacaa5dd1647735bc1`) instalado em `/usr/lib/brisasync/bin/rclone`, com licença MIT incluída em `/usr/share/licenses/brisasync/LICENSE-rclone.txt`.
  - Inclusão de `LICENSE` (GPL-3.0-or-later) e `THIRD_PARTY_NOTICES.md`.
  - Lançador `.desktop` instalado em `/usr/share/applications/brisasync.desktop` e ícones hicolor em 11 resoluções (`16x16` até `1024x1024`) em `/usr/share/icons/hicolor/`.
  - Unit `systemd --user` pré-configurada em `/usr/lib/systemd/user/brisasync.service` e resolução de autoinício gerando `ExecStart=/usr/bin/brisasync --service` e `WorkingDirectory=%h` sem referências à checkout de desenvolvimento.
- **Pureza e Segurança do Pacote**:
  - Zero credenciais, tokens, segredos, banco de dados local `.sqlite`, diretórios `.venv`, `.git` ou arquivos de testes empacotados.
  - Estrutura hierárquica para OAuth: oficial em `/usr/share/brisasync/google_oauth_client.json` vs override do usuário em `~/.config/brisasync/google_oauth_client.json` para compilações locais, forks ou testes.
- **Validação em Sandbox Bubblewrap (`bwrap`) e Fakeroot (`tests/test_installed_package_verification.py`)**:
  - Mascaramento da árvore de desenvolvimento com `--tmpfs /home/agreles/Aplicativos/BrisaSync` e uso de `$HOME` limpo e temporário para comprovar independência completa da checkout.
  - Ciclo de vida ALPM nativo verificado via `fakeroot pacman -r`: instalação, consulta de metadados (`pacman -Qi`), atualização para release 2 e remoção limpa com preservação integral dos arquivos do usuário e banco de dados.

### 1.6. Nova Apresentação Simples para Uso Cotidiano (Rodada 7)
- **Janela Confortável e Responsiva (~820 × 600)**:
  - Eliminação do painel vertical denso e saturado de dados técnicos em favor de uma janela amigável (`820 × 600`, mínimo `760 × 520`) organizada em 5 abas com ícones e rótulos claros: **Início**, **Atividade**, **Configurações**, **Ajuda** e **Sobre**.
- **Tela Inicial Focada no Usuário Comum**:
  - Exibe exclusivamente: (1) Cabeçalho com ícone e nome BrisaSync; (2) Badge compacto da conta conectada (`● usuario@gmail.com`); (3) Card com estado principal amigável (`✓ Sincronizado e pronto`, `⏸ Sincronização pausada`, `🔄 Sincronizando arquivos...`) e horário local formatado da última sincronização (`Hoje às 14:35:10`); (4) Pasta sincronizada e ação direta **"Abrir Pasta Local"**; (5) Ações principais **"Sincronizar Agora"** e **"Pausar/Retomar"**; (6) Banner de atenção acionável exibido **apenas quando houver problema real** (oculto na operação normal).
  - Ocultação estrita de jargões técnicos da tela inicial: zero exibição de PID, socket Unix, IDs remotos alfanuméricos brutos, flags rclone, PKCE, comandos ou caminhos de SQLite no uso cotidiano.
- **Assistente Guiado para Primeira Instalação (Estado Não Configurado)**:
  - Quando a conta ou as pastas ainda não foram associadas, a Tela Inicial substitui os cards de operação por um assistente limpo em 4 etapas:
    `1. Conectar conta Google` → `2. Escolher pasta no Google Drive` → `3. Escolher pasta local (vazia na 1ª vez)` → `4. Revisar e iniciar sincronização`.
- **Tratamento de Caminhos Longos**:
  - Formatação inteligente com elipse central (`_format_elided_path`) sem deformar ou esticar horizontalmente o layout, mantendo o caminho completo acessível via tooltip.
- **Aba Atividade (Histórico Auditável)**:
  - Tabela completa dos últimos 50 ciclos com início formatado no fuso horário local do usuário, tipo de operação, estado com realce cromático (verde para sucesso, amarelo para atenção/pausa, vermelho para erro) e resumo claro das alterações.
- **Aba Configurações**:
  - Gestão visual da Conta Google, seleção da pasta remota (identificada por ID imutável), pasta local dedicada, intervalo de verificação, autoinício `systemd --user`, notificações e modo do ícone da bandeja.
  - Seção Avançada retrátil para desenvolvimento, compilações independentes e forks, permitindo indicar o caminho de um arquivo JSON de cliente OAuth personalizado.
- **Aba Ajuda (Diagnóstico Técnico Isolado)**:
  - Tabela completa de diagnóstico real dos componentes (`collect_system_diagnostics`), botão para reavaliação instantânea, painel do serviço em segundo plano (exibindo live status e PID do daemon) e dicas práticas para resolução de problemas (KDE Wallet/Keyring, backoff e arquivos `.conflict`).
- **Aba Sobre (Identidade Livre e Independência do Google)**:
  - Identidade visual oficial com logo em alta resolução, licença GNU GPL-3.0-or-later, agradecimentos aos componentes de terceiros (`rclone` MIT, Qt/PySide6 LGPLv3, Python PSF, libsecret, libnotify) e declaração expressa e inequívoca:
    > *"O BrisaSync é um projeto independente de código aberto desenvolvido exclusivamente pela comunidade para o ecossistema Linux Desktop. Este software NÃO é desenvolvido, mantido, endossado ou de qualquer forma afiliado à Google LLC. 'Google', 'Google Drive' e marcas associadas são marcas comerciais registradas de propriedade da Google LLC."*
- **Ajustes de Conclusões de Empacotamento**:
  - Documentação atualizada em `docs/PACKAGING_AND_INSTALL.md` registrando que verificações com `--nodeps` não comprovam resolução de dependências em repositórios remotos, diferenciando sandbox Bubblewrap de instalação limpa de SO, identificando os pacotes como artefatos de teste do projeto e alertando que o cliente OAuth de produção não está embutido.

### 1.7. Experiência de Instalação, Login e Transparência do Pacote (Rodada 8)
- **Conferência Real da Interface Instalada**:
  - Capturas reais realizadas diretamente a partir da sessão autêntica do desenvolvedor/usuário (`fabioagreles@gmail.com`, pasta remota `Documentos`, pasta local `/home/agreles/Android/brisa`, última sincronização realizada em 28/10/2026 às 23:07:22).
  - Distinção explícita entre dados autênticos de produção e dados fictícios de teste (`usuario.teste@gmail.com`) utilizados em testes visuais da Rodada 7.
- **Preparação da Distribuição OAuth sem JSON Manual (`OAuthClientConfig`)**:
  - Adição de `OAuthClientConfig.is_distribution_client_available()` e `OAuthClientConfig.get_active_client_source()` para detecção em cascata: (1) Arquivo do usuário em `~/.config/brisasync/google_oauth_client.json` (ou caminho explícito); (2) Arquivo do pacote do sistema em `/usr/share/brisasync/google_oauth_client.json` ou `/etc/brisasync/google_oauth_client.json`.
  - Tratamento honesto e transparente no assistente inicial: se não houver cliente de distribuição embutido, a Etapa 1 exibe uma caixa explicativa informando que este é um pacote de teste e fornece um botão direto *"Configurar Cliente de Teste..."* que navega para Configurações Avançadas, sem falhar silenciosamente nem dar falsa impressão de prontidão pública.
  - Documentação completa em `docs/OAUTH_DISTRIBUTION_GUIDE.md` separando metadados públicos do cliente de distribuição (`client_id`, `client_secret`) de credenciais privadas do usuário (`access_token`, `refresh_token`), além das etapas de configuração do Google Cloud Console.
- **Roteiro e Limites de Testes em Sistema Limpo (`docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md`)**:
  - Mapeamento detalhado dos limites técnicos de ambientes isolados: contêineres Docker/Podman ou chroots headless não validam o navegador para consentimento OAuth, desbloqueio de chaveiro gráfico (KWallet / Secret Service), bandeja `StatusNotifierItem` e inicialização de sessão gráfica.
  - Disponibilização do playbook com comandos reproduzíveis para validação em máquinas virtuais Arch/Manjaro com interface gráfica.
- **Atualização de Versão e Preservação de Pacotes Anteriores**:
  - Nova versão `0.1.1` (`brisasync-0.1.1-1-x86_64.pkg.tar.zst`, `brisasync-0.1.1-2-x86_64.pkg.tar.zst`, `brisasync-0.1.1-py3-none-any.whl`, `brisasync-0.1.1.tar.gz`).
  - Preservação intacta de todos os artefatos `0.1.0` em `dist/`.
  - Atualização da suíte de teste `test_installed_package_verification.py` para testar formalmente o pacote `0.1.1`.

### 1.8. Empacotamento do Cliente OAuth Desktop Oficial e Conexão sem JSON Manual (Rodada 9)
- **Higienização e Inclusão Oficial de Metadados (`packaging/sanitize_oauth_client.py`)**:
  - Criação de utilitário de validação estrita que extrai exclusivamente metadados públicos de Desktop App (`installed` com `client_id`, `project_id: brisasync`, `client_secret`, endpoints PKCE e `redirect_uris=['http://localhost']`), rejeitando sumariamente quaisquer tokens (`access_token`, `refresh_token`), senhas ou segredos de sessão.
  - Instalação oficial do cliente higienizado em `/usr/share/brisasync/google_oauth_client.json` (permissão `0644`) via PKBUILD e inclusão como recurso em `brisasync/resources/oauth/google_oauth_client.json`.
- **Comprovação do Fluxo sem JSON Manual em Perfil Isolado (`tests/verify_distribution_oauth_flow.py`)**:
  - Teste executado em ambiente temporário sem JSON em `~/.config/brisasync`, sem banco SQLite e com chaves de cofre isoladas via variáveis de ambiente (`BRISASYNC_VAULT_ACCOUNT_KEY="test_round9_isolated_account"`), sem tocar na sessão pessoal do usuário.
  - O assistente inicial detecta automaticamente o cliente embutido, exibindo *"1. Conectar conta Google"* e botão *"Conectar Conta Google"* sem aviso de versão de testes pendente de JSON.
  - Comprovada a geração correta de URL de autorização PKCE S256 (`https://accounts.google.com/o/oauth2/v2/auth`) e a transição bem-sucedida para *"✓ 1. Conta conectada: fabioagreles@gmail.com"*.
  - Capturas visuais arquivadas: `brisasync_v0.1.2_wizard_with_distribution_client.png`, `brisasync_v0.1.2_wizard_account_connected.png` e `brisasync_v0.1.2_home_account_connected.png`.
- **Esclarecimento Formal da Contagem de Testes**:
  - Correção do sumário do relatório: os testes coletados pelo pytest somam rigorosamente **41 testes** distribuídos em:
    - `test_bisync_integrity_rehearsal.py`: **12 testes** (cenários 1, 2, 3, 4a, 4b, 5a, 5b, 6, 7, 8, 9, 10).
    - `test_installed_package_verification.py`: **6 testes** (pureza, ALPM, bwrap cli/diagnose, bwrap service/ipc, bwrap no-tray/autostart, preservação de dados).
    - `test_oauth_vault_and_bridge.py`: **6 testes** (PKCE S256, cofre crud, cofre indisponível, bridge rclone, loopback PKCE, rejeição de web client).
    - `test_session_service_and_lifecycle.py`: **7 testes** (ciclo ativo, 2 interfaces/único serviço, pausa/retomada persistida, parada controlada, backoff rede, cofre bloqueado, autostart systemd).
    - `test_tray_notifications_and_desktop.py`: **6 testes** (ícones hicolor/dark/light/HiDPI, ações da bandeja via IPC, manter bandeja viva, modo sem bandeja, reinício UI, notificações deduplicadas/sanitizadas).
    - `test_ui_and_storage.py`: **4 testes** (rejeição de segredos no SQLite, pasta local vazia, reconexão de conta/ID remoto, carregamento de ícones).
    - **Total Real**: 12 + 6 + 6 + 7 + 6 + 4 = **41 testes**.
- **Novo Versionamento 0.1.2 e Preservação**:
  - Novos pacotes gerados em `dist/`: `brisasync-0.1.2-1-x86_64.pkg.tar.zst`, `brisasync-0.1.2-2-x86_64.pkg.tar.zst`, `brisasync-0.1.2-py3-none-any.whl`, `brisasync-0.1.2.tar.gz`.
  - Preservação intacta de todos os artefatos históricos `0.1.0` e `0.1.1`.

### 1.9. Refinamento Visual e Assistente Guiado em 4 Etapas (Rodada 10 — v0.1.3)
- **Assistente Guiado Passo a Passo (`QStackedWidget`)**:
  - Etapa 0: Conectar Conta (botão direto sem jargões de JSON);
  - Etapa 1: Pasta no Google Drive (dropdown com IDs imutáveis e botão de criação de pasta);
  - Etapa 2: Pasta Local (validação de pasta vazia e dedicada);
  - Etapa 3: Revisão e Iniciar (resumo dos caminhos e explicação concisa de integridade e propagação de exclusões para a lixeira).
- **Proporções da Janela e Cabeçalho sem Truncamento**:
  - Dimensão padrão ajustada para ~750 × 510 (mínimo 660 × 440).
  - Elipse de e-mail no cabeçalho com tooltip completa (`_format_elided_email(email, 20)`).
  - Tela de uso cotidiano limpa: "✓ Tudo atualizado" com horário local confirmado, exibindo apenas "Sincronizar Agora" e "Pausar" ou "Retomar". Parada controlada restrita à operação ativa.
- **Construção dos Artefatos 0.1.3**:
  - Pacotes `brisasync-0.1.3-1-x86_64.pkg.tar.zst`, `brisasync-0.1.3-2-x86_64.pkg.tar.zst`, `brisasync-0.1.3-py3-none-any.whl` e `brisasync-0.1.3.tar.gz` gerados em `dist/`.

### 1.10. Preparação da Homologação da Versão Instalada (Rodada 11)
- **Conferência de Procedência das Capturas Visuais**:
  - Identificado formalmente que as capturas de tela da versão 0.1.3 foram geradas por execução em desenvolvimento (`.venv/bin/python`) em modo offscreen. Os dados cotidianos refletem a sessão real (`fabioagreles@gmail.com`), enquanto o assistente reflete perfil isolado.
  - Constatado que o host ainda possui instalado o pacote `0.1.0-1` (`pacman -Q brisasync`).
- **Instruções Exatas de Instalação para o Mantenedor**:
  - Pacote principal: `/home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.3-1-x86_64.pkg.tar.zst` (SHA-256: `d774290c5d00c5c80163be2abb6d99dc3f20e674dc10beb4741747f3c95ece66`).
  - Upgrade test: `/home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.3-2-x86_64.pkg.tar.zst` (SHA-256: `51fcfe1ee8dd66bfe0d43f44aded63d7e554db9944a0ee8638753e34c5e0b4a4`).
- **Roteiro Manual de Homologação em 7 Passos**:
  - Lançador desktop fora da checkout, login embutido sem JSON, sincronização em pasta exclusiva, fechar/reabrir janela mantendo serviço, pausar/retomar, logout/login com autostart e cofre bloqueado, atualização mantendo configurações.
- **Reutilização do Playbook para Sistema Limpo e GNOME**:
  - Reutilização de `docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md`, especificando a distinção entre sandbox/offscreen e ambientes gráficos reais.

---

## 2. Integração Local, Bandeja, Notificações e Ciclo de Vida Comprovados

Ambiente verificado: Linux (`kernel 6.18.49-1-MANJARO`), KDE Plasma (Wayland), `systemd 261`, Python `3.14.7`, PySide6 `6.11.2`, `rclone v1.75.2`, `SQLite 3.53.4`, `secret-tool`, `notify-send`, `bwrap 0.11.0`, `pacman v7.1.0`.

Comando executado:
```bash
.venv/bin/pytest -v
```
Resultado: **`41 passed in 52.98s`** (todas as 41 verificações automatizadas locais aprovadas).

1. **Integridade do Backend `rclone bisync` Real (12 testes em `tests/test_bisync_integrity_rehearsal.py`)**:
   - `test_1` a `test_10` (incluindo `test_4a`, `test_4b`, `test_5a`, `test_5b`).
2. **Pacote Instalado, Pureza, Ciclo ALPM e Isolamento Sandbox (6 testes em `tests/test_installed_package_verification.py`)**:
   - `test_package_archive_contents_and_purity`
   - `test_alpm_package_lifecycle_install_upgrade_remove`
   - `test_bwrap_isolated_execution_diagnostics_and_cli`
   - `test_bwrap_isolated_service_daemon_and_ipc`
   - `test_bwrap_isolated_no_tray_and_autostart_paths`
   - `test_upgrade_and_removal_preserves_user_data`
3. **Cofre da Sessão, Ponte Cifrada e Protocolo OAuth (6 testes em `tests/test_oauth_vault_and_bridge.py`)**.
4. **Serviço da Sessão, IPC Local, Agendamento, Pausa/Retomada, Backoff e Autostart (7 testes em `tests/test_session_service_and_lifecycle.py`)**.
5. **Identidade Visual, Bandeja Opcional, Modo Sem Bandeja, Instância Única da UI e Notificações (6 testes em `tests/test_tray_notifications_and_desktop.py`)**:
   - `test_1_icons_light_dark_hidpi_and_cwd_independence`
   - `test_2_tray_actions_reflect_real_service_state_over_ipc`
   - `test_3_close_window_keeps_tray_alive_and_reopen_via_launcher_without_duplication`
   - `test_4_operation_without_system_tray_preserves_all_functions`
   - `test_5_restart_graphical_component_with_active_service_preserves_state`
   - `test_6_notifications_configurable_grouped_deduplicated_sanitized_and_mirrored_in_window`
6. **Interface PySide6, SQLite e Ícones (4 testes em `tests/test_ui_and_storage.py`)**.

---

## 3. Integração Google Comprovada

Comando executado com `~/.config/brisasync/google_oauth_client.json` (`0600`) e consentimento interativo no navegador:
```bash
.venv/bin/python tests/live_google_drive_rehearsal.py
```
Resultado: **`9/9 cenários reais contra os servidores do Google Drive aprovados`** (operando exclusivamente na pasta dedicada `BrisaSync-Teste-Automatico`, `folder_id='1E5HsgHDPPXFVdFhqRhZGlI88fGdMND22'`).

---

## 4. Roteiro Curto para Teste Manual de Encerrar/Iniciar Sessão (Logout/Login) pelo Usuário

Como o encerramento real da sessão gráfica encerraria o ambiente de trabalho ativo do usuário, o teste de logout/login real com `systemd --user` pode ser executado pelo mantenedor seguindo estes passos curtos:

1. **Ativar o autoinício**:
   - Abra o BrisaSync (`.venv/bin/brisasync`) e marque a caixa **"Autoinício (systemd --user)"** (ou execute `systemctl --user is-enabled brisasync.service` para confirmar `enabled`).
2. **Encerrar e iniciar novamente a sessão gráfica (Logout / Login)**:
   - Faça logout da sessão desktop atual e faça login novamente com o mesmo usuário.
3. **Verificar o serviço após o login**:
   - Em um terminal, execute:
     ```bash
     systemctl --user status brisasync.service
     ```
   - Abra a janela do BrisaSync (`.venv/bin/brisasync`):
     - Se o cofre da sessão (KDE Wallet / Keyring) já tiver sido desbloqueado no login, o serviço estará em `[AGUARDANDO]` ou `[PAUSADO]` (respeitando sua preferência anterior).
     - Se o cofre da sessão estiver bloqueado, o serviço exibirá `[ATENÇÃO NECESSÁRIA] — Cofre da sessão bloqueado ou indisponível`, aguardando o desbloqueio sem abrir o navegador repetidamente.
4. **Reverter o autoinício (opcional)**:
   - Desmarque a caixa **"Autoinício (systemd --user)"** na interface para remover `~/.config/systemd/user/brisasync.service`.

---

## 5. Dependências Externas e Pendências para Próximas Rodadas

1. **Validação Presencial em Sessão GNOME Real**:
   - A validação real de bandeja (`StatusNotifierItem`) e do modo sem bandeja (`--no-tray`) foi executada na sessão atual **KDE Plasma (Wayland)**. Embora o modo sem bandeja (`QSystemTrayIcon.isSystemTrayAvailable() == False`) tenha sido testado automatizadamente, a validação visual presencial em uma sessão **GNOME** real permanece pendente para um ambiente com GNOME instalado.
2. **Observação Local por Eventos (`inotify`) e Empacotamento/Instaladores**:
   - A detecção instantânea de alterações locais via `inotify` (complementando a reconciliação periódica) e a geração de pacotes distribuíveis (`.deb`, `.rpm`, Flatpak/AppImage) permanecem para as próximas etapas.
3. **Distribuição Pública OAuth Geral (*In Production* / Verificação Google)**:
   - O cliente de Desktop App oficial do projeto `brisasync` foi devidamente embutido no pacote `0.1.2` (`/usr/share/brisasync/google_oauth_client.json`). Na GCP, o projeto permanece em modo **Testing**, permitindo login direto e sem JSON para as contas cadastradas como *Test users* (como a conta autorizada de testes `fabioagreles@gmail.com`). Para publicação ampla a qualquer usuário final sem aviso de app não verificado, permanece pendente a submissão e aprovação formal do aplicativo e do escopo sensível `https://www.googleapis.com/auth/drive` junto ao Google Trust & Safety.
4. **Execução do Playbook em Máquina Virtual Limpa**:
   - Conforme detalhado em `docs/CLEAN_SYSTEM_TESTING_PLAYBOOK.md`, a validação de resolução de dependências através de repositórios oficiais e a interação gráfica completa (KWallet / Secret Service, loopback OAuth no navegador e autostart na inicialização da sessão) requerem execução em uma máquina virtual dedicada com instalação limpa do Arch Linux / Manjaro / BigLinux com desktop ativo.

---

## 6. Tabela Consolidada de Homologação (Atualizada com Rodada 14 — v0.1.6)

| Item / Funcionalidade | Status | Evidência / Justificativa |
| :--- | :--- | :--- |
| **Nova Interface com Barra Lateral e Painel em Cartões (v0.1.6)** | **Aprovado com evidência técnica** | Interface redesenhada inspirada nas 4 referências visuais com barra lateral fixa (~230px), paleta escura (#0B0F15 / #131923 / #273140 / #9189FF), cantos 16px/8px, biblioteca vetorial nativa em `vector_icons.py`, Hero Status Banner dinâmico (verde/azul/âmbar/vermelho/neutro) com métricas verídicas e 4 páginas completas (`Visão geral`, `Pastas`, `Atividade`, `Ajustes`). 14 telas reais capturadas. |
| **Abertura Gráfica do Pacote Instalado (v0.1.6 / v0.1.5 / v0.1.4)** | **Aprovado com evidência técnica** | `ensure_background_service_started` em `BrisaMainWindow` acionando `ipc_client.ensure_service_running()`. Regressões aprovadas em `test_tray_notifications_and_desktop.py` (cenários com serviço parado, serviço ativo sem duplicação e `--no-tray`) e `test_installed_package_verification.py` via `bwrap` isolado fora da checkout. Total de 42 testes locais aprovados em 59.86s. |
| **Integridade de Sincronização (`rclone bisync`)** | **Aprovado com evidência** | 12 testes em `test_bisync_integrity_rehearsal.py` e 9/9 cenários reais no Google Drive (`live_google_drive_rehearsal.py`), com travas anti-PID reciclado e proteção dupla contra exclusão em massa. |
| **Cofre da Sessão, Ponte Cifrada e Protocolo OAuth** | **Aprovado com evidência** | 6 testes em `test_oauth_vault_and_bridge.py`, PKCE S256, Secret Service/KWallet, tmpfs em `/dev/shm` com `RCLONE_ENCRYPT_V0:`. |
| **Serviço da Sessão, IPC Local e Autostart** | **Aprovado com evidência** | 7 testes em `test_session_service_and_lifecycle.py`, socket UNIX verificado via `SO_PEERCRED`, parada controlada e unit `systemd --user`. |
| **Empacotamento ALPM 0.1.6 e Pureza** | **Aprovado com evidência** | Pacotes construídos em `dist/`, cliente embutido em `/usr/share/brisasync/google_oauth_client.json`, zero segredos/dev empacotados, verificado via `fakeroot` e `bwrap`. SHA-256 de `brisasync-0.1.6-1-x86_64.pkg.tar.zst`: `5f1dca53c60ffe46bb7b113e80b66b87db08ae5cb6711431fcdf8e46d7ce481e`. |
| **Homologação Manual do Pacote Instalado v0.1.6 no Host** | **Pronto para teste pelo mantenedor** | Requer instalação deliberada pelo mantenedor via `sudo pacman -U /home/agreles/Aplicativos/BrisaSync/dist/brisasync-0.1.6-1-x86_64.pkg.tar.zst` e validação com lançador de aplicativos ou terminal. |
| **Resolução de Dependências em Contêiner Limpo** | **Pendente de teste manual** | Roteiro estruturado no playbook (Fase 1 via Podman com `archlinux:base`), sem `--nodeps`. |
| **Homologação Gráfica Presencial em GNOME** | **Bloqueado por ambiente atual** | O ambiente atual é KDE Plasma (Wayland). Testes em GNOME requerem máquina virtual ou partição com GNOME Shell. |
| **Verificação OAuth Pública no Google Trust & Safety** | **Bloqueado por configuração externa (Pendente de Submissão)** | O cliente desktop oficial está embutido e opera em modo *Testing* para os usuários autorizados. Publicação geral sem aviso exige processo externo de auditoria do Google. |

---

## 7. Correção da Resolução do Motor rclone e Unificação do Estado Operacional (Rodada 23 — v0.1.12)

### Diagnóstico e Causa Raiz
Na homologação real do pacote `0.1.11-1` em ambiente Manjaro GNOME limpo, foi observado:
1. O usuário autorizou no navegador e o callback local recebeu o código com sucesso.
2. Em seguida, a materialização da configuração cifrada falhou com `[Errno 2] Arquivo ou diretório inexistente: '/home/fabio/.local/bin/rclone'`.
3. A tela de diagnóstico apontava `/usr/lib/brisasync/bin/rclone` corretamente, pois utilizava `RcloneBisyncEngine._resolve_rclone_binary`.
4. Em contrapartida, `RcloneEncryptedBridge` continha um fallback codificado para `~/.local/bin/rclone` quando `rclone` não estava no `PATH` do sistema.
5. Em razão disso, as credenciais ficaram salvas no cofre da sessão, mas o arquivo cifrado `rclone.conf` não foi criado.
6. A interface exibia estados divergentes: o assistente considerava apenas a presença de credenciais no cofre e mostrava "Conta Google conectada" liberando o botão Avançar, enquanto a listagem de pastas falhava silenciosamente e exibia "Conecte sua conta Google".

### Correções Implementadas
1. **Resolvedor Canônico Único (`resolve_rclone_binary`)**:
   - Centralizado em `src/brisasync/backend/rclone_engine.py` e utilizado de forma unificada por `RcloneBisyncEngine`, `RcloneEncryptedBridge`, `diagnostics.py`, `RemoteFoldersWorker` e `SyncCoordinator`.
   - Precedência rigorosa: override explícito > `BRISASYNC_RCLONE_BINARY` > locais empacotados (`/usr/lib/brisasync/bin/rclone`, `sys.prefix`, caminhos relativos ao pacote) > `PATH`.
   - Overrides inválidos levantam exceções específicas (`FileNotFoundError` ou `PermissionError`).
   - Removido qualquer fallback falso para `~/.local/bin/rclone` e proibida a criação de links simbólicos ou cópias para contornar a resolução.
2. **Unificação do Estado Operacional da Conta (`_get_account_operational_state`)**:
   - Distingue com rigor quatro estados operacionais: `VAULT_LOCKED`, `NOT_CONNECTED`, `CONFIG_PENDING` e `READY`.
   - O estado `READY` exige que as credenciais estejam presentes no cofre **e** que o arquivo de configuração cifrada rclone esteja plenamente materializado no disco.
   - Enquanto em `CONFIG_PENDING`, o cabeçalho exibe aviso pendente, o assistente indica configuração pendente e bloqueia o avanço para a etapa de seleção de pastas remotas, e o botão de ação exibe "Concluir Conexão".
3. **Recuperação Transparente Sem Reabertura de Navegador**:
   - Em caso de credenciais válidas já presentes no cofre, o clique em "Concluir Conexão" (ou nos botões Hero/Ajustes) materializa a configuração cifrada diretamente a partir do cofre, sem abrir o navegador e sem exigir reautenticação do usuário.
   - Em caso de falha de materialização, os tokens no cofre são integralmente preservados (sem exclusão para mascarar erros) e o erro técnico real é apresentado ao usuário.
4. **Regressões Automatizadas e Build da Versão 0.1.12**:
   - Acrescentados 5 novos testes de regressão em `tests/test_oauth_buttons_and_theme_regression.py`.
   - Versão incrementada para `0.1.12` em `pyproject.toml`, `__init__.py`, `build_packages.sh`, `PKGBUILD` e `test_installed_package_verification.py`.
   - Pacotes construídos em `dist/`: `brisasync-0.1.12-1-x86_64.pkg.tar.zst` (SHA-256: `3caf058986ebab861cd78e270296f9821ee4df704bf368deea1b0b993ee9c7ac`). Todos os pacotes anteriores (0.1.0 a 0.1.11) preservados intactos.

---

## 8. Correção de Contrato de Pastas Remotas e Apresentação do Par (Rodada 24 — v0.1.13)

- **Correção do Contrato `RemoteDirectoryEntry`**:
  - Ajustado o acesso aos atributos do objeto de retorno de listagem do Google Drive para `entry.folder_name` e `entry.folder_id`.
  - Ajustada a criação e vinculação de pastas remotas garantindo persistência atômica no banco de dados SQLite.
- **Limpeza de Apresentação de Dados Não Configurados**:
  - Corrigido o cartão da pasta na tela inicial para exibir "Não configurada" em vez de caminhos de demonstração desatualizados quando o usuário ainda não associou um par.
- **Pacotes da Versão 0.1.13**:
  - Construídos e validados em `dist/`: `brisasync-0.1.13-1-x86_64.pkg.tar.zst`.

---

## 9. Atualização Dinâmica de Estado e Contraste Inline no Tema Escuro (Rodada 25 — v0.1.14)

- **Atualização Dinâmica de Estado sem Reabrir a Janela**:
  - Corrigida a gestão do timer periódico de status IPC (`_status_timer`) para ser iniciado no `showEvent` e suspenso no `hideEvent`.
  - Centralizada a atualização do botão primário do Hero (`_update_hero_primary_button`) para refletir instantaneamente a transição de "Sincronizando..." para "Sincronizar agora" / "Tudo em dia" assim que o ciclo é concluído pelo daemon.
- **Contraste no Editor de Renomeação e Diálogos (`QFileDialog`)**:
  - Ajustadas as propriedades de estilo de `QTreeView` e `QListView` garantindo `HighlightedText = #FFFFFF` e `Highlight = #5446CF`, tornando legível a edição de nome de pastas no tema escuro.
- **Pacotes da Versão 0.1.14**:
  - Construídos e validados em `dist/`: `brisasync-0.1.14-1-x86_64.pkg.tar.zst`.

---

## 10. Animação Discreta do Botão de Sincronização (Rodada 26 — v0.1.15)

### Diagnóstico e Requisitos
Durante sincronização ativa, o usuário deve receber confirmação visual em tempo real através da rotação contínua e suave das setas do ícone de sincronização no botão primário do Hero, respeitando:
1. Sincronização estrita com o daemon: a animação só roda enquanto o daemon confirmar ciclo ativo (`STATE_SYNCING`, `STATE_VERIFYING` ou `is_cycle_active=True`), inclusive para ciclos automáticos de fundo. O clique manual isolado não inicia animação sem confirmação do daemon.
2. Não introdução de atrasos artificiais: operações rápidas concluem normalmente sem retenção forçada da animação.
3. Desabilitação e prevenção de cliques duplicados durante o ciclo.
4. Suspensão imediata em segundo plano: ao ocultar a janela (`hideEvent`), a animação é suspensa para economizar CPU. Ao reabrir (`showEvent`), retoma apenas se a sincronização ainda estiver em andamento.
5. Preservação de contraste e geometria: ícone com tamanho 16px, preservando alto contraste `#0B0F15` e fundo branco `#FFFFFF` mesmo com o botão desabilitado (`QPushButton#heroPrimaryBtn:disabled`).
6. Uso exclusivo de mecanismos nativos de PySide6/Qt (`QTimer`, `QPainterPath`, `QPainter.rotate`), sem dependências externas adicionais.

### Implementação
1. **Renderização Vetorial com Rotação em `vector_icons.py`**:
   - Função `render_rotated_sync_pixmap(size=16, color="#0B0F15", angle_degrees=0.0, dpr=1.0)`: translada para o centro, rotaciona no sentido horário e desenha os arcos e pontas das setas de sincronização.
   - Função `render_rotated_sync_icon(size=16, color="#0B0F15", angle_degrees=0.0)` com cache `_ROTATED_SYNC_ICON_CACHE`: associa explicitamente os pixmaps aos modos `Normal`, `Active`, `Selected` e `Disabled`, evitando o fading automático do Qt quando o botão está desabilitado.
2. **Ciclo de Vida da Animação em `main_window.py`**:
   - `_hero_anim_timer = QTimer(self)` com intervalo de 40 ms (25 FPS) e passo angular de 12° por quadro.
   - `_start_hero_sync_animation()` e `_stop_hero_sync_animation()`.
   - `_update_hero_primary_button()` dispara `_start_hero_sync_animation()` quando `is_active` for verdadeiro e a janela visível; caso contrário, chama `_stop_hero_sync_animation()` e restaura o ícone padrão.
   - `showEvent` e `hideEvent` gerenciam a ativação e suspensão do timer de animação de acordo com a visibilidade e o estado operacional.
   - `closeEvent` garante a parada da animação ao encerrar a interface.
3. **Estilos em `styles.py`**:
   - Regra `QPushButton#heroPrimaryBtn:disabled { background-color: #FFFFFF; color: #0B0F15; border: none; }` adicionada para manter a legibilidade máxima e fidelidade visual.
4. **Regressões e Pacote ALPM 0.1.15**:
   - Adicionados 2 novos testes automatizados em `tests/test_oauth_buttons_and_theme_regression.py` (total de 22 testes passando).
   - Teste de isolamento de pacote em sandbox Bubblewrap `tests/test_installed_package_verification.py` (6 testes passando).
   - Pacotes construídos em `dist/`:
     - `brisasync-0.1.15-1-x86_64.pkg.tar.zst` (SHA-256: `9ebf23e043e14ac8d7e4f4cf40f20ffe3f1955771eea09c31e8e70c7991873f3`)
     - `brisasync-0.1.15-2-x86_64.pkg.tar.zst` (SHA-256: `02a7a47cea307a5c9b71670d2796654eb3255e04551a33858def29ccaca16e04`)
     - `brisasync-0.1.15-py3-none-any.whl` (SHA-256: `6aed1b0a9c5bd94b6e0379ffdf0f15ff64fd945d4e0f02cbb6847a3f76160e65`)
     - `brisasync-0.1.15.tar.gz` (SHA-256: `f37969345395e61948adec6b01da1be958e76be25460eafa3686b2baa349042d`)
   - Todos os pacotes das versões 0.1.0 a 0.1.14 preservados intactos no diretório `dist/`.

---

## 11. Autoinício Completo com Presença na Bandeja (Rodada 27 — v0.1.16)

### Diagnóstico e Requisitos
Na homologação real do BrisaSync na máquina virtual Manjaro GNOME/Wayland:
- A opção *"Iniciar automaticamente ao fazer login"* estava marcada.
- Ao reiniciar a VM, o serviço `brisasync.service` iniciava corretamente e mantinha um único daemon ativo.
- O ícone da bandeja não aparecia automaticamente até o usuário abrir a interface pelo lançador do sistema.
- Ao abrir pelo lançador, o ícone da bandeja sempre aparecia, comprovando que a extensão e o suporte à bandeja estavam plenamente funcionais.

*Causa Raiz*: A unit `systemd --user` (`brisasync.service`) foi concebida exclusivamente para o serviço de sessão headless (`brisasync --service`). No ecossistema Linux Desktop (especialmente Wayland/GNOME), serviços gerenciados pelo `systemd --user` rodam isolados da sessão gráfica (`DISPLAY`/`WAYLAND_DISPLAY`/`DBUS_SESSION_BUS_ADDRESS`), não devendo instanciar janelas ou ícones gráficos diretamente. O mecanismo canônico para autoinício gráfico em ambientes XDG/Freedesktop é o diretório `~/.config/autostart/*.desktop`.

### Arquitetura de Autoinício Coordenado (`BrisaAutostartCoordinator`)
1. **Separação Canônica de Responsabilidades**:
   - `systemd --user` (`~/.config/systemd/user/brisasync.service`): responsável único pelo agendamento, monitoramento, coalescência e execução do motor `rclone bisync` em segundo plano (`brisasync --service`).
   - XDG Autostart (`~/.config/autostart/brisasync.desktop`): responsável por iniciar a interface gráfica após a disponibilização da sessão gráfica do usuário, invocando `brisasync --start-hidden`.
2. **Gerenciador XDG (`XDGAutostartManager`)**:
   - Cria e mantém `~/.config/autostart/brisasync.desktop` com comando instalado (`/usr/bin/brisasync --start-hidden`), permissões seguras (0o644) e metadados `X-BrisaSync-Managed=true` e `X-GNOME-Autostart-enabled=true`.
   - `SystemdUserAutostartManager.has_competing_xdg_autostart()` foi atualizado para reconhecer entradas gerenciadas (`X-BrisaSync-Managed=true` ou `--start-hidden`) como legítimas e não concorrentes, bloqueando apenas entradas não gerenciadas que tentem rodar `--service`.
3. **Coordenador Unificado (`BrisaAutostartCoordinator`)**:
   - Unifica `enable()`, `disable()` e `is_enabled()` para ambos os componentes.
   - Implementa `sync_state()`: auto-cura inconsistências parciais (por exemplo, quando o usuário já possuía a unit do systemd ativada, ativando automaticamente a entrada XDG na inicialização da interface).
   - Ao desativar o autoinício na interface ou via IPC, remove ambos os arquivos de inicialização sem afetar banco SQLite, credenciais ou arquivos locais.

### Instância Única e Parâmetro `--start-hidden`
1. **CLI `main.py` e Modo Oculto**:
   - Flags `--start-hidden` e `--minimized` adicionadas ao parser CLI (`dest="start_hidden"`).
   - `try_activate_existing_ui(socket_path, show_window=True)`: aceita o booleano `show_window`. Se falso, realiza apenas uma sonda ("ping") sem exibir a janela.
   - Em ambiente com bandeja disponível (`window.tray_controller.is_available`): inicia com a janela principal oculta (`isVisible() == False`), mantendo o ícone ativo na bandeja.
   - Se o usuário clicar posteriormente no lançador do sistema (`brisasync` sem `--start-hidden`), a nova invocação envia sinal via `ui.sock` e a instância existente executa `restore_and_focus_window()`, trazendo o painel para o primeiro plano sem duplicar processos ou ícones.
   - Em ambiente sem bandeja disponível (`--no-tray` ou desktop sem AppIndicator): `--start-hidden` garante que o serviço de sincronização está ativo em segundo plano via `ensure_background_service_started()` e encerra a interface com código 0, sem abrir janela inesperada e sem laços de repetição.
2. **Ciclo de Fechamento**:
   - Fechar a janela principal (X) oculta a interface na bandeja (`tray_active=True`).
   - Opções "Manter sincronização em segundo plano" e "Encerrar tudo" continuam operando de forma previsível e sem retentativas indevidas.

### Suíte de Testes e Empacotamento ALPM v0.1.16
1. **Novos Testes Automatizados em `tests/test_tray_notifications_and_desktop.py`**:
   - `test_8_xdg_autostart_and_coordinator_lifecycle_isolated`: ciclo de vida isolado de XDG e Coordinator, conteúdo de unit e .desktop, sync_state e preservação de banco de dados.
   - `test_9_main_start_hidden_without_tray_exits_cleanly`: inicialização do serviço em segundo plano e saída limpa com código 0 em desktops sem bandeja.
   - `test_10_main_start_hidden_with_tray_remains_hidden_and_second_instance_reveals`: janela oculta na bandeja no login e revelação em primeiro plano pelo lançador sem duplicação.
2. **Validação de Sandbox Bubblewrap / ALPM em `tests/test_installed_package_verification.py`**:
   - 6 testes aprovados validando o ciclo de vida ALPM completo, `--version` (0.1.16), `--help` (incluindo `--start-hidden`), `--diagnose` e rotas instaladas de `XDGAutostartManager` e `BrisaAutostartCoordinator`.
3. **Artefatos Gerados em `dist/`**:
   - `brisasync-0.1.16-1-x86_64.pkg.tar.zst` (SHA-256: `314009015b0940fd1dd656b8235ad2865355505a6b42df5a117c7a159cec5bb0`)
   - `brisasync-0.1.16-2-x86_64.pkg.tar.zst` (SHA-256: `304d271fc92c851a83341ea71af7d66edc52c06664f4224bc83eb8f9bb098918`)
   - `brisasync-0.1.16-py3-none-any.whl` (SHA-256: `620e4bfc6f851c78c19d723f644e268fea07a3e9c3d627e7cb24dcae75d1f8aa`)
   - `brisasync-0.1.16.tar.gz` (SHA-256: `81bd445ba72809a22e29b4b575bcc2453330f997b4cb53362425ec0360553b75`)
   - Todos os pacotes das versões 0.1.0 a 0.1.15 preservados intactos no diretório `dist/`.


---

## 12. Tratamento Não Interativo de Cofre Bloqueado e Prevenção de Prompts Repetidos (Rodada 28 — v0.1.17)

### Diagnóstico e Causa Raiz
Na homologação real do BrisaSync 0.1.16 na máquina virtual Manjaro GNOME/Wayland:
1. Ao encerrar o aplicativo, bloquear o chaveiro "Login" do GNOME Keyring via aplicativo *Senhas e Chaves* (Seahorse) e reabrir o BrisaSync, o sistema exibia a caixa de diálogo modal de senha.
2. Ao cancelar a solicitação de senha, a caixa de diálogo reaparecia repetidamente em laço, a interface gráfica congelava e o terminal registrava:
   `secret-tool lookup [...] timed out after 8 seconds.`
3. Adicionalmente, quando um par de pastas já estava configurado no SQLite, a interface chegava a renderizar incorretamente "Tudo em dia" com o cofre bloqueado.

**Causa Raiz Identificada**:
1. No arquivo `src/brisasync/ui/main_window.py`, o timer de atualização periódica (`_status_timer`, executado a cada 1.2 segundos) chamava `_update_hero_primary_button()`, que invocava `_get_account_operational_state()`.
2. Essa rotina chamava diretamente `credential_store.load_credentials()` na thread principal do Qt (`main thread`) sem verificar previamente se o chaveiro estava bloqueado.
3. Como a CLI `secret-tool` aciona o prompt interativo do Secret Service e bloqueia o processo aguardando entrada ou timeout de 8 segundos, o cancelamento da caixa pelo usuário retornava falha, e o próximo tick do timer (1.2s depois) reexecutava a consulta, gerando uma tempestade ininterrupta de janelas modais de senha e congelando a UI.
4. Na tela inicial (`_apply_service_snapshot`), a existência de um par de pastas configurado no banco local avaliava `is_configured = True` e exibia o estado "Tudo em dia" mesmo sem acesso às credenciais do cofre.

---

### Arquitetura de Detecção Não Interativa do Cofre
1. **Exceção de Domínio `VaultLockedError`**:
   - Criada a exceção especializada `VaultLockedError(VaultUnavailableError)` no módulo `src/brisasync/credentials/store.py` e exportada em `src/brisasync/credentials/__init__.py`.
2. **Sonda In-Process e Não Interativa via D-Bus (`is_vault_locked`)**:
   - Implementado o método `CredentialStore.is_vault_locked()`, que avalia o estado de bloqueio em sub-milissegundos via D-Bus (`QtDBus.QDBusInterface`) sem invocar subprocessos externos e sem acionar janelas do sistema:
     - **Secret Service (GNOME Keyring)**: consulta a propriedade `org.freedesktop.Secret.Collection.Locked` no caminho `/org/freedesktop/secrets/aliases/default` da interface `org.freedesktop.DBus.Properties`.
     - **KDE Wallet**: consulta o método `org.kde.KWallet.isOpen` via D-Bus.
   - Suporte a emulação de cofre bloqueado em testes através de `set_mock_vault_locked()` e da variável de ambiente `BRISASYNC_TEST_VAULT_LOCKED`.
3. **Contrato de Carregamento Não Interativo (`load_credentials(interactive=False)`)**:
   - `load_credentials(self, *, interactive: bool = False)`: se `interactive=False` (padrão utilizado por timers de UI, verificações de background e pré-checagens do daemon), consulta previamente `is_vault_locked()`. Se estiver bloqueado, levanta imediatamente `VaultLockedError` sem rodar `secret-tool` nem invocar diálogos gráficos.
   - Em chamadas interativas explícitas (`interactive=True`), as invocações de subprocesso (`secret-tool`) são isoladas com `start_new_session=True`. Em caso de timeout ou cancelamento, todo o grupo de processos é finalizado (`os.killpg(p.pid, signal.SIGTERM)` seguido de `SIGKILL`), eliminando prompters órfãos.

---

### Desacoplamento da UI e Desbloqueio sob Demanda
1. **Worker Assíncrono `UnlockVaultWorker(QThread)`**:
   - Criado em `src/brisasync/ui/workers.py` com sinais `succeeded` e `failed`.
   - Toda tentativa de desbloqueio interativo solicitada pelo usuário é delegada para essa thread secundária, impedindo completamente o congelamento da interface do Qt durante o diálogo de senha do sistema.
   - Caso o usuário cancele a solicitação de senha, o worker falha suavemente, restaura os botões da UI e mantém o estado estável de "Cofre bloqueado", sem repetições automáticas.
2. **Ações do Usuário e Transições de Estado**:
   - **Hero Card**:
     - Quando o cofre está bloqueado, exibe título *"Cofre bloqueado"*, mensagem amigável *"O cofre de senhas da sua sessão de usuário está bloqueado. Desbloqueie-o para retomar a sincronização com o Google Drive."* e pílula de status cromática *"✕ Cofre bloqueado"*.
     - O botão de ação rápida exibe *"Desbloquear"*, e o botão primário do Hero assume o rótulo *"Desbloquear cofre"* acompanhado do ícone vetorial nativo de cadeado (`lock`).
     - Ações de clique em "Sincronizar agora" ou no botão primário redirecionam para `_on_unlock_vault_clicked()`, iniciando o worker sob demanda.
   - **Aba Configurações e Diálogo de Atenção**:
     - O botão de conta é reconfigurado para *"Desbloquear Cofre"* com estilo chamativo em vez de ficar desabilitado ou induzir a uma nova autorização no Google.
     - O diálogo de detalhes de atenção (`_show_attention_details_dialog`) apresenta botão de ação direta *"Desbloquear Cofre"*.
   - **Recusa Estrita de "Tudo em dia"**:
     - Se `is_locked` ou a categoria de atenção do daemon for `ATTENTION_VAULT_LOCKED`, a exibição de "Tudo em dia" é terminantemente vetada, mesmo que haja registros passados de sincronização concluída com sucesso.
   - **Preservação de Conta e Pastas**:
     - Ao detectar cofre bloqueado com pasta já configurada no SQLite, o cartão da pasta configurada é mantido visível, sem substituir indevidamente a tela inicial pelo assistente de configuração em branco.
3. **Detecção e Recuperação Automática de Desbloqueio Externo**:
   - Se o usuário desbloquear o chaveiro fora do BrisaSync (ex: pelo Seahorse, pelo navegador ou por outro aplicativo desktop), o timer periódico de status (`_status_timer`) detecta `is_vault_locked() == False` na próxima avaliação não interativa.
   - A interface recarrega as credenciais e retoma a sincronização normal automaticamente, **sem exigir que o usuário reautorize o acesso no navegador Google**.
4. **Comunicação IPC do Daemon**:
   - Protocolo atualizado com a constante de atenção `ATTENTION_VAULT_LOCKED = "VAULT_LOCKED"`.
   - O daemon monitora o estado de bloqueio de forma não interativa e expõe a nova ação IPC `vault_unlocked` para reconciliação instantânea após o desbloqueio via UI.

---

### Suíte de Testes e Empacotamento ALPM v0.1.17
1. **Nova Suíte de Testes `tests/test_vault_locked_handling.py`**:
   - 6 testes automatizados cobrindo:
     - `test_1_is_vault_locked_detection_and_non_interactive_load_credentials`: detecção D-Bus in-process e rejeição de chamadas não interativas quando bloqueado.
     - `test_2_ui_status_timer_does_not_prompt_when_locked`: comprovação de que o timer de status e snapshot não invocam prompters nem congelam a UI.
     - `test_3_unlock_vault_worker_interactive_flow`: execução do worker em thread secundária e emissão dos sinais de sucesso/falha.
     - `test_4_main_window_locked_presentation_and_no_all_in_order`: validação visual impedindo "Tudo em dia", exibindo "Desbloquear cofre" e preservando pares configurados.
     - `test_5_external_unlock_detection_and_seamless_recovery`: recuperação automática de desbloqueio externo sem reautorização web no Google.
     - `test_6_daemon_non_interactive_precheck_and_scheduler_poll`: tratamento gracioso pelo serviço em segundo plano com transição para `STATE_ATTENTION_REQUIRED` e reconciliação via IPC.
2. **Aprovação Integral da Suíte Existente**:
   - `tests/test_vault_locked_handling.py`: 6 testes aprovados (100%).
   - `tests/test_oauth_buttons_and_theme_regression.py`: 22 testes aprovados (100%).
   - `tests/test_attention_diagnostics_and_precheck.py` + `tests/test_v017_ui_refinements.py`: 10 testes aprovados (100%).
   - `tests/test_tray_notifications_and_desktop.py`: 10 testes aprovados (100%).
   - `tests/test_session_service_and_lifecycle.py`: 7 testes aprovados (100%).
   - `tests/test_bisync_integrity_rehearsal.py` + `tests/test_ui_and_storage.py`: 16 testes aprovados (100%).
   - `tests/test_installed_package_verification.py`: 6 testes aprovados em sandbox Bubblewrap com ALPM install, upgrade (0.1.17-1 para 0.1.17-2) e remove (100%).
3. **Artefatos Gerados em `dist/`**:
   - `brisasync-0.1.17-1-x86_64.pkg.tar.zst` (SHA-256: `0dabfbbc6cd4a5937e31eec3cfe12ca5f2c24369579998c114ef5d6bef66f27e`)
   - `brisasync-0.1.17-2-x86_64.pkg.tar.zst` (SHA-256: `04d443085d052cc7257b0a095e780a95a420029b454509bcd81752549b6a49c3`)
   - `brisasync-0.1.17-py3-none-any.whl` (SHA-256: `7815a45cf047b3fac99ee01d2de038bd69bed82cf7dd74937158be1b9245f80a`)
   - `brisasync-0.1.17.tar.gz` (SHA-256: `0a5c3fb3ffab5ff224cb11fb2b301e4a9f1ea382eab66b043fce7ff4bf63cb0d`)
   - Todos os pacotes das versões 0.1.0 a 0.1.16 preservados intactos no diretório `dist/`.


---

## 13. Preferência Manual de Tema e Refinamento Visual (Rodada 29 — v0.1.18)

### Registro da Homologação Manual da Versão 0.1.17
Na máquina virtual Manjaro GNOME/Wayland, o mantenedor confirmou os seguintes resultados manuais:
- **Sincronização Bidirecional**: Envio e recebimento de arquivos entre a máquina virtual e o Google Drive funcionando normalmente com integridade comprovada.
- **Operação em Segundo Plano**: Fechamento da janela principal não interrompe os ciclos de sincronização nem o daemon.
- **Autoinício na Bandeja**: Presença automática do ícone na bandeja do sistema após o login sem exibição forçada da janela principal.
- **Instância Única**: Abertura pelo lançador restaura e foca a janela existente sem duplicar instâncias da interface, do daemon ou do ícone da bandeja.
- **Cofre Bloqueado**: Eliminação completa dos laços contínuos de solicitação de senha do GNOME Keyring. O aplicativo permanece estável e responsivo em estado "Cofre bloqueado", permitindo desbloqueio sob demanda pelo botão "Desbloquear cofre" ou auto-recuperação imediata quando desbloqueado externamente (via Seahorse ou navegador).

---

### Diagnóstico e Objetivos da Rodada 29
Apesar do tema escuro ter boa apresentação, o tema claro apresentava inconsistências visuais localizadas:
1. Ausência de seletor manual de tema: a aplicação dependia estritamente da detecção do desktop via Qt `styleHints().colorScheme()`.
2. Textos e ícones fixados em cores claras (`#F0F4F8`) sobre cartões e botões claros no tema claro, tornando-os invisíveis ou com baixo contraste.
3. Menus (`QMenu`) e dicas de contexto (`QToolTip`) sem estilização formal no QSS, ficando à mercê de plugins de tema GTK externos sob Wayland.
4. Molduras de foco duplicadas (contorno pontilhado interno somado à borda externa do controle) em seletores e tabelas.
5. Diálogo de detalhes de atenção (`_show_attention_details_dialog`) forçando fundo escuro rígido.

---

### Implementação Arquitetural

1. **Seletor de Tema ("Aparência")**:
   - Adicionada a preferência em **Ajustes → Sistema**: `QComboBox` com as opções **Sistema**, **Claro** e **Escuro**.
   - Persistência implementada em [`SyncDatabase`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/storage/database.py) através dos métodos `get_theme_preference(default="system")` e `set_theme_preference(mode)`.
   - Inicialização no [`main.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/main.py) carrega o tema salvo antes de instanciar a interface.
   - Aplicação imediata em tempo de execução sem reiniciar o processo ou o serviço em segundo plano.
2. **Modo Reativo vs Estabilidade Manual**:
   - Quando a preferência for **Sistema**, o aplicativo escuta o sinal `QGuiApplication.styleHints().colorSchemeChanged` e atualiza a interface instantaneamente ao alternar o tema do desktop.
   - Quando a preferência for **Claro** ou **Escuro**, a escolha manual permanece estritamente estável, ignorando alterações no tema do desktop.
3. **Consistência Visual e Classes Semânticas**:
   - Em [`styles.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/styles.py), foram introduzidas regras completas para `QToolTip` e `QMenu`.
   - Adicionadas classes semânticas adaptativas: `.settingFieldLabel`, `.footerCardTitle`, `.footerCardValue`, `.idleStateTitle`, `.idleStateSub`, `.overviewItemTitle`, `.overviewItemSub`.
   - Eliminação de contornos pontilhados duplicados via `QAbstractItemView { outline: none; }`.
   - No [`main_window.py`](file:///home/agreles/Aplicativos/BrisaSync/src/brisasync/ui/main_window.py), método `_update_theme_dependent_icons()` atualiza as cores dos ícones em botões neutros (`overview_verify_again_btn`, `overview_open_folder_btn`, `folders_page_open_btn`, `folders_page_sync_btn`, `refresh_history_button`, `sidebar_diag_btn`, `sidebar_about_btn`) garantindo alto contraste tanto no fundo escuro (`#131923`) quanto no claro (`#FFFFFF`).
   - O botão primário do Hero (`heroPrimaryBtn`) e sua rotação vetorial continuam com contraste máximo e fixo (`#FFFFFF` com ícone `#0B0F15`).
   - Diálogo de detalhes de atenção atualizado para herdar o estilo do tema corrente.

---

### Suíte de Testes e Empacotamento ALPM v0.1.18

1. **Nova Suíte de Testes `tests/test_theme_preference_and_visual_consistency.py`**:
   - 6 testes cobrindo persistência SQLite, detecção de modo escuro/claro, comutação imediata via combo, estabilidade manual vs reatividade de sistema, herança de estilos em diálogos e contraste do Hero Button (100% aprovados em 36.17s).
2. **Suíte Completa de Regressão**:
   - `tests/test_vault_locked_handling.py`: 6 testes aprovados (100%).
   - `tests/test_oauth_buttons_and_theme_regression.py`: 22 testes aprovados (100%).
   - `tests/test_installed_package_verification.py`: 6 testes aprovados em sandbox Bubblewrap com ALPM install/upgrade/remove (100%).
3. **Capturas de Evidências Visuais (18 Capturas PNG)**:
   - Geradas via `scripts/capture_theme_screens.py` cobrindo todas as 4 abas (normal e maximizada) e os 4 diálogos principais nos temas Claro e Escuro.
4. **Artefatos Gerados em `dist/`**:
   - `brisasync-0.1.18-1-x86_64.pkg.tar.zst` (SHA-256: `695a840967039a7bdb43b6dd04ad8065c1cccf07a6529d90211c4030eb9a4262`)
   - `brisasync-0.1.18-2-x86_64.pkg.tar.zst` (SHA-256: `1318b026d5e8b0cd304493d16e613eb13b5e23d2aa3702d8528fba521f74276f`)
   - `brisasync-0.1.18-py3-none-any.whl` (SHA-256: `7f5cd94e7ac963d910155795d36c01a202d781307dc2902037fba0aa5e019fcd`)
   - `brisasync-0.1.18.tar.gz` (SHA-256: `32760d06cd86c9d97d6c63c2ffab1331f2b4af2cab4fd42e27406ca046333203`)
   - Todos os pacotes das versões anteriores (0.1.0 a 0.1.17) preservados intactos no diretório `dist/`.

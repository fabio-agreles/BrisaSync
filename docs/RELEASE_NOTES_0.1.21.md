# Notas de Lançamento — BrisaSync v0.1.21 (Release Candidate)

**Data de Lançamento**: 4 de novembro de 2026  
**Status da Versão**: Candidata à Distribuição Pública e Transição (*Release Candidate* / RC)  
**Ambiente de Referência**: Manjaro Linux (GNOME 47 / Wayland / x86_64) e Arch Linux  
**Licença**: GNU General Public License v3.0 or later (GPL-3.0-or-later)  
**Mantenedor**: Fábio Agreles Bezerra  
**E-mail de Suporte ao Usuário**: [fabioagreles@gmail.com](mailto:fabioagreles@gmail.com)  
**Domínio Oficial**: `brisasync.com.br`  
**Página Oficial (Publicação Pendente)**: [https://brisasync.com.br/](https://brisasync.com.br/)  
**Política de Privacidade (Publicação Pendente)**: [https://brisasync.com.br/privacy/](https://brisasync.com.br/privacy/)  
**Repositório Oficial**: [https://github.com/brisasync/brisasync](https://github.com/brisasync/brisasync)

---

## Visão Geral da Versão 0.1.21

A versão **0.1.21** do BrisaSync consolida os refinamentos de interface, estabilidade de temas, persistência e a seção de apoio voluntário implementados no ciclo recente, preparando o projeto para a fase de distribuição e homologação pública.

Esta versão é classificada formalmente como **Release Candidate**, servindo de transição para validação em ambiente real antes da publicação estável definitiva. Os escopos OAuth e o código-fonte permanecem estritamente congelados nesta etapa, focando na integridade do empacotamento, documentação técnica e transparência das salvaguardas operacionais.

---

## Evidências Reais de Homologação

Para total transparência com os usuários e revisores, as evidências de validação do BrisaSync são estritamente categorizadas entre **testes manuais seletivos homologados pelo mantenedor em máquina virtual** e **testes automatizados de regressão em ambiente de engenharia**.

### 1. Homologação Manual Seletiva (Mantenedor na VM Manjaro GNOME/Wayland)

Os seguintes fluxos e comportamentos foram testados, observados e aprovados manualmente pelo mantenedor na máquina virtual de referência:

- **Sincronização Bidirecional Ativa**: Sincronização entre pastas locais e o Google Drive via motor `rclone`, com detecção de novos arquivos, alterações e downloads.
- **Operação com Janela Fechada**: Fechar a janela principal oculta a interface sem interromper os ciclos periódicos de sincronização gerenciados pelo serviço de segundo plano.
- **Autoinício e Presença na Bandeja**: Inicialização da sessão com `--start-hidden`, integração com o painel do sistema e menu de contexto da bandeja.
- **Garantia de Instância Única**: Tentar abrir uma nova instância pelo terminal ou pelo lançador restaura suavemente a janela ativa sem instanciar processos concorrentes ou corromper travas.
- **Recuperação de Cofre Bloqueado**: Comportamento resiliente na inicialização quando o chaveiro (GNOME Keyring / KWallet) está inacessível ou bloqueado, evitando travamentos da interface ou solicitações infinitas de senha.
- **Seletor e Persistência de Temas**: Alternância entre tema do Sistema, Claro e Escuro com aplicação imediata de estilos (QSS) sem necessidade de reiniciar a aplicação, mantendo estabilidade visual em todos os painéis.
- **Responsividade da Interface**: Comportamento responsivo verificado em diferentes larguras de janela (de 820×620 até 1920×1080 px), garantindo que botões do Hero, cartões de Ajustes e menus não sofram corte de conteúdo.
- **Apoio Voluntário via Pix no Diálogo Sobre**: Exibição nítida do QR Code gerado localmente em preto e branco sobre fundo branco (inclusive no tema escuro), botões de cópia rápida para "Chave Pix" e "Pix Copia e Cola" com confirmação visual temporária.

### 2. Validação via Testes Automatizados de Regressão

Comportamentos críticos de segurança e de borda foram homologados formalmente através de testes automatizados dedicados, garantindo que cenários destrutivos ou de infraestrutura sejam validados com rigor determinístico:

- **Proteção Contra Exclusão em Massa (*Mass Deletion Safeguard*)**: Validada na suíte de testes (`tests/`). A salvaguarda impede a propagação inadvertida de exclusões em larga escala (`max_delete_percent = 50%`, limite absoluto `max_delete_abs = 25`), abortando o ciclo e alertando o usuário caso um volume elevado de arquivos locais seja apagado acidentalmente, sem passar `--force` ao motor `rclone`.
- **Contrato OAuth 2.0 PKCE (RFC 7636 / RFC 8252)**: Testes de geração do desafio criptográfico S256 (`code_verifier` e `code_challenge`), parsing dos parâmetros na URL de redirecionamento em loopback e tratamento de erro de acesso negado.
- **Decodificação e Integridade do QR Code Pix**: Teste automatizado com o leitor zbar (`zbarimg`) confirmando que o SVG/PNG gerado localmente decodifica com precisão de 100% o payload oficial EMV do Banco Central do Brasil.
- **Ciclo de Vida do Pacote ALPM em Sandbox**: Validação em container Bubblewrap isolado sem acesso à rede, verificando a presença do executável `/usr/lib/brisasync/bin/rclone`, integridade dos ícones vetoriais SVG de status e seletores, e funcionamento do comando `--diagnose`.
- **Heurística de Bandeja e Resiliência a Temas**: Testes cobrindo a seleção das variantes de ícone (`brisasync-light`, `brisasync-dark`, `brisasync-symbolic`) e a preservação dos overrides manuais em preferências.

---

## Modificações e Melhorias Consolidadas na 0.1.21

- **Refinamento de Usabilidade**:
  - Introdução da seção "Apoie o BrisaSync" no diálogo Sobre com chave e código de pagamento Pix, totalmente voluntário e mantendo 100% das funções do aplicativo livres e irrestritas.
  - Correção de contraste e legibilidade das setas dos seletores de opções (ComboBox) nos temas Claro e Escuro, utilizando ativos vetoriais dedicados.
  - Harmonização de contraste do cabeçalho da janela, cartões de Ajustes e menus suspensos.
- **Distribuição e Empacotamento**:
  - Inclusão e validação do motor `rclone` (v1.73.0) pré-instalado em `/usr/lib/brisasync/bin/rclone` dentro do pacote nativo `.pkg.tar.zst` para distribuições Arch/Manjaro/BigLinux.
  - Revisão rigorosa de dependências de sistema no `PKGBUILD` (`python>=3.11`, `pyside6`, `python-gobject`, `libsecret`).
- **Documentação de Sistema**:
  - Revisão do `README.md` com instruções detalhadas de instalação (`pacman -U`), atualização limpa de processos e desinstalação segura com garantia de preservação de dados pessoais.

---

## Limitações Conhecidas e Estado do OAuth

1. **Google OAuth em Modo de Teste (*Testing Mode*)**:
   - A credencial pública de aplicativo desktop configurada no projeto opera sob o modo de testes no Google Cloud Console.
   - **Janela de Expiração**: De acordo com as políticas do Google, tokens de atualização emitidos para aplicações em modo de teste expiram a cada **7 dias**, exigindo reautenticação periódica até que a verificação pública em produção seja concluída.
   - **Limite de Usuários**: Restrito aos e-mails previamente cadastrados como testadores no console do projeto.
2. **Ambiente GNOME Shell Padrão**:
   - O GNOME Shell não fornece suporte nativo a ícones na bandeja do sistema sem extensões de terceiros (*AppIndicator/KStatusNotifierItem Support*). O BrisaSync funciona normalmente sem a bandeja, operando o serviço de sincronização em segundo plano e permitindo reabrir a interface pelo lançador a qualquer momento.
3. **Detecção Automática do Painel do Desktop**:
   - A detecção de contraste do ícone da bandeja em modo Automático baseia-se em heurísticas de ambiente de desktop (barra escura por padrão no GNOME e verificação de `colorScheme` no KDE). Usuários que utilizem extensões de barra clara no GNOME ou temas mistos no KDE podem selecionar manualmente o modo "Claro (para barra escura)" ou "Escuro (para barra clara)" na aba Ajustes → Sistema.

---

## Arquivos e Pacotes da Versão 0.1.21

Os artefatos compilados e validados para esta versão encontram-se no diretório `dist/`:

| Arquivo | Tamanho | Descrição |
| :--- | :--- | :--- |
| `brisasync-0.1.21-1-x86_64.pkg.tar.zst` | 31.951.000 bytes | Pacote binário nativo ALPM (Revisão 1) com rclone embutido |
| `brisasync-0.1.21-2-x86_64.pkg.tar.zst` | 31.950.995 bytes | Pacote binário nativo ALPM (Revisão 2) com rclone embutido |
| `brisasync-0.1.21-py3-none-any.whl` | 2.340.265 bytes | Pacote Wheel Python padrão para instalação via pip/uv |
| `brisasync-0.1.21.tar.gz` | 2.383.676 bytes | Arquivo fonte completo (*sdist*) com suíte de testes e metadados |

Os hashes criptográficos SHA-256 oficiais estão registrados no arquivo `dist/SHA256SUMS.txt`.

# Empacotamento Flatpak do BrisaSync

Este diretório contém o manifesto Flatpak (`org.brisasync.BrisaSync.yml`) e scripts de suporte para o BrisaSync.

---

## 1. Justificativa Estrutural de Permissões

O BrisaSync é um aplicativo de sincronização contínua em segundo plano de pastas locais com o Google Drive via `rclone bisync`. Para operar com fidelidade, requer permissões específicas:

| Permissão | Finalidade e Justificativa |
| :--- | :--- |
| `--filesystem=home` | **Mandatória**. Um sincronizador de pastas locais contínuo em segundo plano opera sobre pastas arbitrárias selecionadas pelo usuário na sua `$HOME` (ex.: `~/Documentos`, `~/Trabalho`, `~/Projetos`). Portais pontuais (`FileChooser`) fornecem descritores efêmeros para abertura de arquivos únicos, sendo tecnicamente incompatíveis com monitoramento de diretórios em segundo plano por um daemon desatendido. |
| `--share=network` | **Mandatória**. Comunicação HTTPS com as APIs do Google Drive e transferência de arquivos via motor `rclone`. |
| `--talk-name=org.freedesktop.secrets` | **Mandatória**. Armazenamento seguro de tokens OAuth 2.0 no cofre de segredos da sessão do usuário (GNOME Keyring / KWallet), impedindo que segredos sejam salvos em texto claro em disco. |
| `--talk-name=org.freedesktop.Notifications` | Notificações nativas de conclusão de sincronização, detecção de conflitos e alertas de rede. |
| `--talk-name=org.kde.StatusNotifierWatcher` | Integração com a bandeja do sistema (System Tray) para operação contínua com a janela principal minimizada ou fechada. |

---

## 2. Restrições e Políticas do Flathub

As diretrizes oficiais do Flathub restringem severamente concessões amplas de acesso ao sistema de arquivos como `--filesystem=home` ou `--filesystem=host` para novas submissões, exigindo o uso de Portals da Freedesktop sempre que possível.

Como o ecossistema de Flatpak Portals ainda não oferece uma API padronizada para *concessão persistente e contínua de monitoramento de pastas para daemons em segundo plano*, a distribuição recomendada via Flatpak para o BrisaSync é:
1. **Bundle Autônomo Flatpak (`.flatpak`)**: Usuários podem instalar localmente com comando `flatpak install --user brisasync.flatpak`.
2. **Submissão Formal ao Flathub**: Proposta acompanhada de justificativa formal de exceção (categoria similar a clientes de sincronização como Nextcloud, Syncthing e Insync).

---

## 3. Instruções de Compilação Local

Para compilar o Flatpak localmente (requer `flatpak-builder` instalado):

```bash
# 1. Instalar runtime e SDK da plataforma KDE (se ainda não instalados)
flatpak install --user flathub org.kde.Platform//6.7 org.kde.Sdk//6.7

# 2. Compilar e instalar para o usuário atual
flatpak-builder --user --install --force-clean build-dir packaging/flatpak/org.brisasync.BrisaSync.yml

# 3. Executar o aplicativo empacotado
flatpak run org.brisasync.BrisaSync
```

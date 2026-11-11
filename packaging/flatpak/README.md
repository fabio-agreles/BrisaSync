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
| `--talk-name=org.freedesktop.portal.Background` | **Mandatória**. Permite ao daemon de sincronização continuar em execução e gerenciar ciclos após o fechamento da janela gráfica principal. |
| `--talk-name=org.freedesktop.Notifications` | Notificações nativas de conclusão de sincronização, detecção de conflitos e alertas de rede. |
| `--talk-name=org.kde.StatusNotifierWatcher` | Integração com a bandeja do sistema (System Tray) para operação contínua com a janela principal minimizada ou fechada. |

---

## 2. Restrições Arquiteturais Concretas e Status Pendente

O formato Flatpak permanece atualmente classificado como **Pendente** devido a quatro impedimentos técnicos concretos inerentes ao modelo de sandbox:

1. **Ciclo de vida do Daemon em Segundo Plano**: O sandbox do Flatpak por padrão encerra todos os subprocessos e cgroups assim que a janela principal da aplicação é fechada pelo usuário. Manter o daemon de sincronização ativo e desatendido exige a concessão explícita do portal `org.freedesktop.portal.Background`, cuja aceitação automática varia conforme a interface de desktop do usuário.
2. **Acesso Não Interativo a Pastas Arbitrárias**: O motor `rclone bisync` precisa de acesso contínuo e desatendido às pastas configuradas. O Flathub rejeita formalmente `--filesystem=home` ou `--filesystem=host` para novas inclusões, exigindo portais `FileChooser` interativos que não sustentam operações de sincronização agendadas.
3. **Isolamento de D-Bus e Cofre de Sessão**: O acesso direto ao `org.freedesktop.secrets` através de proxy D-Bus pode apresentar restrições de permissão em distribuições Linux com políticas estritas de sandbox (ex.: Ubuntu AppArmor / SELinux).
4. **Compilação Estrita Offline**: O build do Flatpak é executado em ambiente estritamente desconectado (`--no-network`). Dependências Python volumosas como `PySide6` e bibliotecas Qt associadas requerem um manifesto exaustivo com dezenas de wheels individuais e hashes criptográficos mapeados via geradores de manifestos. Todas as salvaguardas de mascaramento de erros (`|| true`) foram removidas do manifesto para garantir falha estrita caso alguma dependência esteja ausente.

Por essas razões concretas, os usuários em Linux devem priorizar os formatos de distribuição validados: **Arch Linux (.pkg.tar.zst)**, **Universal AppImage (.AppImage)** e **Debian/Ubuntu (.deb)**.

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


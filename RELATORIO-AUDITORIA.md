# Relatório de auditoria técnica — BrisaSync

Data da validação: 21 de novembro de 2026.

## A. Resumo executivo

A auditoria técnica, funcional, de integrações, segurança, persistência, nomenclatura e documentação do BrisaSync foi concluída. O aplicativo é uma aplicação desktop Tauri 2, com frontend React/TypeScript e backend Rust, usando rclone bisync como motor de sincronização.

Foram corrigidos resíduos da antiga marca “Nuvem Sync” e um problema funcional no manifesto Flatpak: o manifesto definia `NUVEM_RCLONE`, enquanto o código procura `BRISASYNC_RCLONE`. Também foram corrigidos referências antigas em documentação, scripts, título do modo navegador, comentários, metadados AppStream e nomes de testes.

O estado final é: **Pronto com ressalvas**. A verificação TypeScript, o build Vite, a sintaxe dos scripts e as verificações de identidade/nomenclatura passaram. Os testes Rust e o build nativo Tauri não puderam ser executados neste ambiente porque `cargo`/`rustc` não estão instalados e as bibliotecas nativas GTK/WebKitGTK também não estão disponíveis.

## B. Bugs e correções

O problema funcional confirmado foi a divergência entre o manifesto Flatpak e o backend. O manifesto usava `NUVEM_RCLONE=/app/bin/rclone`, mas `rclone.rs` lê `BRISASYNC_RCLONE`. Isso tornava a variável documentada no Flatpak ineficaz. A correção foi aplicada em `app/flatpak/app.brisasync.BrisaSync.json`, usando `BRISASYNC_RCLONE`.

Também foram corrigidos resíduos de marca que não causavam necessariamente falha em execução, mas produziam comportamento/documentação inconsistente: o título HTML de fallback, caminhos simulados no backend de demonstração, comentários do binário, comentários dos modelos OAuth, nomes de testes, o `<binary>` do AppStream e os scripts auxiliares de domínio, vídeo e narração.

A implementação já existente inclui proteções importantes contra perda de dados: limite explícito de exclusões no bisync, bloqueio quando um lado está vazio e o outro cheio, recuperação de JSON corrompido por backup, gravação atômica, permissões restritas nos arquivos de estado e autenticação Basic no painel RC local. Essas áreas foram mantidas sem refatoração desnecessária.

## C. Auditoria funcional

A superfície funcional foi revisada nas telas Visão geral, Arquivos, Pastas, Atividade, Conflitos e Ajustes, incluindo modais, paleta de comandos, atalhos, bandeja, OAuth, autostart, upload/download, resolução de conflitos, diagnóstico, atualização e persistência.

As 36 commands Tauri estão registradas no backend e correspondem às chamadas de `bridge.ts`. As ações principais possuem atualização de estado, persistência e tratamento de erro. Não foi identificado botão principal sem implementação ou chamada desconectada durante a auditoria estática.

A validação funcional já registrada no projeto cobre sincronização bidirecional, atividade, autostart Flatpak, remoção protegida de conta, reparo de OneDrive, conflitos, cota, limpeza de atividade, bandeja, recuperação de estado, prevenção de concorrência e modo demonstração. A execução real desses cenários não foi repetida nesta sessão por falta do toolchain Rust e das dependências nativas.

## D. Referências a “Nuvem Sync”

As referências antigas de produto foram classificadas antes da correção. Foram atualizadas as referências obsoletas em código, manifesto, documentação e scripts. Foram preservados deliberadamente os usos genéricos de “nuvem” como tradução de cloud, as palavras-chave de busca, o histórico de migração no AppStream e os campos Debian `replaces`, `conflicts` e `provides` relacionados ao pacote antigo.

Uma busca final não encontrou referências obsoletas de produto, nomes antigos de variável, app-id antigo, binário antigo ou domínio antigo fora dos usos genéricos e de compatibilidade intencional.

## E. Limpeza

Foram removidas somente entradas obsoletas do `.gitignore` e corrigidas referências documentais. Não foram removidos módulos, telas, recursos ou arquivos de runtime sem comprovação de que fossem dispensáveis. Os binários rclone presentes como artefatos de build continuam ignorados pelo Git, conforme esperado.

O arquivo `.env.oauth` não está rastreado pelo Git. Nenhum valor de credencial, token, segredo ou dado sensível é reproduzido neste relatório.

## F. Documentação

Foram atualizados `app/README.md`, `app/flatpak/README.md`, scripts de demonstração, script de narração, script de montagem de vídeo e script de verificação do domínio. Os caminhos, comandos, variáveis de ambiente, nomes de pacotes, app-id e executável agora refletem BrisaSync.

Os usos de “nuvem” que descrevem o provedor remoto foram preservados por serem terminologia funcional, não marca antiga.

## G. Testes e validações

**Aprovado:** `npm run check` — TypeScript sem erros.

**Aprovado:** build frontend com TypeScript e Vite usando diretório de saída limpo — bundle gerado com sucesso.

**Aprovado:** `bash -n scripts/*.sh app/scripts/*.sh` — sintaxe dos scripts shell válida.

**Aprovado:** `node --check app/scripts/capture-previews.mjs` — sintaxe JavaScript válida.

**Aprovado:** verificação de identidade — nome do pacote, product name, identifier, app-id e comando Flatpak coerentes.

**Aprovado:** `git diff --check` — nenhuma falha de whitespace no diff.

**Aprovado:** busca final por referências obsoletas de produto — nenhum resultado fora de usos genéricos ou de compatibilidade intencional.

**Não executado:** `cargo test` e build Rust/Tauri nesta sessão. `cargo` e `rustc` não estão disponíveis no ambiente atual.

**Não foi possível validar:** execução nativa do aplicativo, instalação limpa de `.deb`, execução do Flatpak recém-corrigido, teste real de OAuth, teste em Windows e teste com contas/provedores reais nesta sessão.

## H. Pendências

A principal pendência técnica para uma validação de release é executar `cargo test` e o build Tauri em uma máquina com Rust, GTK 3, WebKitGTK 4.1 e demais dependências nativas instaladas. Em seguida, deve ser repetido o build Flatpak para incorporar e testar o nome atualizado da variável `BRISASYNC_RCLONE`.

Também permanecem válidas as limitações já documentadas no projeto: testes em Windows real, instalação limpa do `.deb`, fluxo completo de credenciais OAuth próprias, conflito real entre edições simultâneas, teste ARM e publicação/verificação do projeto OAuth de distribuição.

## I. Estado final

**Pronto com ressalvas.**

O código frontend e a documentação corrigida passaram pelas validações disponíveis. A aplicação não deve ser declarada como totalmente validada para release até que os testes Rust, o build Tauri nativo e a execução do pacote Flatpak corrigido sejam realizados em ambiente com as dependências apropriadas.

## J. Segunda passagem de release — 21/11/2026

Validações executadas nesta passagem:

- `app/package-lock.json` alinhado a `package.json` (`brisasync` / `1.0.0`), sem alteração de versões de dependências; `npm ci`, `npm run check` e `npm run build` aprovados.
- `cargo test`: 88 testes aprovados, 0 falhas, 2 ignorados.
- `cargo build --release --features custom-protocol`: concluído.
- Flatpak reconstruído a partir do código atual, com `BRISASYNC_RCLONE=/app/bin/rclone` confirmado dentro do sandbox e `rclone v1.75.2` executando.
- Bundle `BrisaSync-1.0.0-x86_64.flatpak` reinstalado a partir do próprio bundle e validado (abertura, bandeja via StatusNotifierItem, rclone e encerramento).
- Teste de perfil limpo: com `~/.config/app.brisasync.BrisaSync` e `~/.local/share/app.brisasync.BrisaSync` movidos para backup, o app iniciou sem configuração prévia; o perfil original foi restaurado com os mesmos hashes e permissões.
- Autostart: o portal `org.freedesktop.portal.Background` criou o `.desktop` correto com `Exec=flatpak run --command=/app/bin/brisasync app.brisasync.BrisaSync --minimized`; o arquivo de teste foi removido depois.
- Segredos antigos removidos de caches do Flatpak e de artefatos nativos antigos (`app/src-tauri/target`). O binário instalado e o bundle novo não contêm os valores antigos.

Pendências que impedem o release final:

- Rotação das credenciais OAuth do Google e do Dropbox ainda depende de ação manual nos painéis dos provedores e de atualização do `app/.env.oauth`.
- O bundle atual foi construído diretamente do manifesto, sem embutir o projeto OAuth do BrisaSync; ele serve para validação estrutural, mas não é o artefato final. Após a rotação, reconstruir com `app/scripts/build-flatpak.sh`.
- Login OAuth real, criação de pasta no Drive, sincronização bidirecional, remoção de conta e teste em usuário Linux separado não foram executados nesta passagem; exigem conta de teste e autorização.

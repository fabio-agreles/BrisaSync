#!/usr/bin/env bash
# Prepara a pasta local de demonstração usada no vídeo de verificação do Google.
#
# O vídeo não pode mostrar seus arquivos reais: o revisor vê o conteúdo. Este
# script cria uma pasta com três arquivos fictícios, todos com o nome do app
# dentro, para o vídeo ficar autoexplicativo e sem dado pessoal nenhum.
#
# Uso: scripts/demo-video.sh [destino]      (padrão: ~/Downloads/nuvem-demo-video)
set -euo pipefail

destino="${1:-$HOME/Downloads/nuvem-demo-video}"

rm -rf "$destino"
mkdir -p "$destino"

cat > "$destino/nota.txt" <<'TXT'
Nuvem Sync — arquivo de demonstração
===================================

Este arquivo existe só para o vídeo de verificação do Google.

Se você está vendo este texto dentro do Google Drive, o upload funcionou.
Agora edite a linha abaixo no Drive (pela web) e observe o app baixar a versão
nova sem você pedir nada:

versao: 1 (criada no computador)
TXT

cat > "$destino/planilha-demo.csv" <<'CSV'
dia,arquivo,direcao
1,nota.txt,local -> nuvem
2,nota.txt,nuvem -> local
3,exemplo.md,local -> nuvem
CSV

cat > "$destino/exemplo.md" <<'MD'
# Exemplo do Nuvem Sync

Sincronização **bidirecional** entre esta pasta e o Google Drive.

- o app não fala com servidor nenhum
- o token fica no computador do usuário
- o rclone bisync é o motor
MD

echo "demo-video: pasta criada em $destino"
ls -l "$destino"
cat <<TXT

Próximos passos do vídeo
------------------------
1. No Google Drive (navegador), crie uma pasta chamada  Nuvem-demo
   e envie os três arquivos de $destino para dentro dela.
2. Grave o roteiro de docs/video-verificacao.md (2–3 min, sem cortes).
3. Suba no YouTube como "Não listado" e cole o link no formulário de verificação.

Dica: use uma conta Google reserva para o vídeo. Cada conta nova que autoriza o
app consome uma das 97 autorizações que restam até a verificação passar.
TXT

#!/usr/bin/env bash
# Gera a narração em inglês do vídeo de verificação do Google (escopo `drive`).
#
# Por que existe: o revisor é anglófono e precisa entender o que acontece na
# tela. Este script sintetiza o roteiro de docs/narracao-video-en.md em áudio,
# um arquivo por trecho — assim você grava a tela tocando o trecho da vez, sem
# precisar editar vídeo depois (e o vídeo pode ficar sem cortes, como o Google
# exige).
#
# Voz: en-US-AndrewNeural (Microsoft Edge, neural) — masculina, calma, boa para
# narração técnica. Vem do pacote `edge-tts`, rodado via `uvx` (sem instalar
# nada). Trocar a voz: VOZ=en-US-AvaNeural bash scripts/narracao-video.sh
#
# Uso: scripts/narracao-video.sh [destino]     (padrão: ~/Downloads/nuvem-video/narracao)
set -euo pipefail

voz="${VOZ:-en-US-AndrewNeural}"
ritmo="${RITMO:-+0%}"
destino="${1:-$HOME/Downloads/nuvem-video/narracao}"

for ferramenta in uvx ffmpeg; do
  command -v "$ferramenta" >/dev/null || {
    echo "narracao-video: falta '$ferramenta'." >&2
    exit 1
  }
done

rm -rf "$destino"
mkdir -p "$destino"

# Um trecho por momento da tela (os tempos batem com docs/video-verificacao.md).
textos=(
  "This is Nuvem Sync, an open-source desktop application that keeps a folder on my computer in two-way sync with a folder in my own Google Drive."
  "There is no server component. The sync engine and the OAuth token stay on this computer."
  "I'm adding a Google Drive account. The authorization request is about to open in the browser, and it will show the app name and the single permission it needs."
  "Here is the Google consent screen. The app name is Nuvem Sync, exactly as on the website. The only permission requested is access to Google Drive files, the drive scope. The app is not verified yet, and that is what I'm applying for. I'll allow it."
  "Back in the app, the account is connected, with its name, e-mail address and Drive quota."
  "Now I'm adding a folder. I browse my existing Google Drive and select Nuvem-demo. A narrower permission, drive dot file, could not see a folder the app did not create itself. That is the reason the full drive scope is required."
  "I'll create a file on the computer, inside the synced folder. The activity list shows it being uploaded, and here it is in the Drive web interface."
  "Now the other direction. I edit the same file in the Drive web interface, and the app brings the change back down to the computer on its own."
  "Only the folders I add are touched. The rest of my Drive is untouched. And access can be revoked at any time: here is the app in my Google account permissions. Once revoked, syncing stops immediately."
  "That's Nuvem Sync. It is open source, MIT licensed, at github dot com slash fabio dash agreles slash nuvem. Thank you."
)

# A API pública do Edge às vezes devolve vazio quando recebe várias chamadas
# seguidas; três tentativas com pausa resolvem.
sintetizar() {
  local texto="$1" arquivo="$2" tentativa
  for tentativa in 1 2 3; do
    if uvx edge-tts --voice "$voz" --rate="$ritmo" --text "$texto" \
        --write-media "$arquivo" >/dev/null 2>&1 && [[ -s "$arquivo" ]]; then
      return 0
    fi
    rm -f "$arquivo"
    sleep 2
  done
  echo "narracao-video: falhou ao sintetizar ($arquivo)" >&2
  return 1
}

indice=0
for texto in "${textos[@]}"; do
  indice=$((indice + 1))
  arquivo="$(printf '%s/%02d.mp3' "$destino" "$indice")"
  sintetizar "$texto" "$arquivo"
  printf '%s  %s\n' "$(printf '%02d' "$indice")" "$texto" >> "$destino/roteiro.txt"
done

# Faixa contínua, com 1,2 s entre os trechos (para quem preferir tocar de uma vez).
ffmpeg -v error -f lavfi -i anullsrc=r=24000:cl=mono -t 1.2 -q:a 9 "$destino/silencio.mp3" -y
lista="$destino/lista.txt"
: > "$lista"
for arquivo in "$destino"/[0-9][0-9].mp3; do
  printf "file '%s'\n" "$arquivo" >> "$lista"
  printf "file '%s'\n" "$destino/silencio.mp3" >> "$lista"
done
# Reencoda em vez de copiar: o `-c copy` em mp3 monta dts fora de ordem e o
# arquivo sai com estalos.
ffmpeg -v error -f concat -safe 0 -i "$lista" \
  -c:a libmp3lame -b:a 96k -ar 24000 -ac 1 "$destino/narracao-completa.mp3" -y
rm -f "$lista" "$destino/silencio.mp3"

echo "narracao-video: voz $voz · ritmo $ritmo"
echo "narracao-video: $indice trechos em $destino"
ffprobe -v error -show_entries format=duration -of csv=p=0 "$destino/narracao-completa.mp3" |
  awk '{ printf "narracao-video: faixa completa com %.0f s (%d min %.0f s)\n", $1, $1/60, $1%60 }'

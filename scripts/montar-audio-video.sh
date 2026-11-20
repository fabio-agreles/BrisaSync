#!/usr/bin/env bash
# Cola a narração sobre a gravação de tela SEM tocar no vídeo.
#
# O vídeo do Google precisa sair sem cortes. Adicionar uma faixa de áudio é
# permitido — o que reprova é cortar/emendar para esconder etapa. Este script
# muxa a faixa de narração e deixa o vídeo exatamente como foi gravado:
# `-c:v copy`, sem reencode, sem corte, sem mudança de velocidade.
#
# Uso:
#   scripts/montar-audio-video.sh <gravacao.mp4> <tempos.txt> [saida.mp4]
#
# tempos.txt: um trecho por linha — quando ele começa e qual arquivo tocar.
# Aceita 0:11, 00:01:40 ou segundos (75). Linhas em branco e com # são ignoradas:
#
#   # início   arquivo
#   0:02       ~/Downloads/nuvem-video/narracao/01.mp3
#   0:18       ~/Downloads/nuvem-video/narracao/02.mp3
#
# Dica: abra a gravação no player, ache o instante em que cada ação começa e
# anote. Errou? Rode de novo — o vídeo original não é alterado.
set -euo pipefail

uso() {
  sed -n '2,23p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-1}"
}

[[ $# -ge 2 ]] || uso 1
gravacao="$1"
tempos="$2"
saida="${3:-${gravacao%.*}-narrado.mp4}"

command -v ffmpeg >/dev/null || { echo "montar-audio-video: falta o ffmpeg" >&2; exit 1; }
[[ -f "$gravacao" ]] || { echo "montar-audio-video: gravação não encontrada: $gravacao" >&2; exit 1; }
[[ -f "$tempos" ]] || { echo "montar-audio-video: lista não encontrada: $tempos" >&2; exit 1; }

# "0:11" / "1:02:03" / "75" → milissegundos.
em_ms() {
  local bruto="$1" horas=0 minutos=0 segundos=0
  local -a partes
  IFS=: read -r -a partes <<< "$bruto"
  case ${#partes[@]} in
    1) segundos=${partes[0]} ;;
    2) minutos=${partes[0]}; segundos=${partes[1]} ;;
    3) horas=${partes[0]}; minutos=${partes[1]}; segundos=${partes[2]} ;;
    *) echo "montar-audio-video: tempo inválido '$bruto'" >&2; return 1 ;;
  esac
  echo $(( (10#${horas} * 3600 + 10#${minutos} * 60 + 10#${segundos%%.*}) * 1000 ))
}

duracao="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$gravacao")"

# Monta as entradas (0 = vídeo) e o grafo de filtros.
entradas=("$gravacao")
trechos=()
indice=0
while read -r inicio arquivo _resto; do
  [[ -z "${inicio:-}" || "$inicio" == \#* ]] && continue
  arquivo="${arquivo/#\~/$HOME}"
  [[ -f "$arquivo" ]] || { echo "montar-audio-video: áudio não encontrado: $arquivo" >&2; exit 1; }
  atraso="$(em_ms "$inicio")"
  indice=$((indice + 1))
  entradas+=("$arquivo")
  # aresample antes do adelay: amix exige todos na mesma taxa/canais.
  trechos+=("[$indice:a]aresample=48000,aformat=channel_layouts=stereo,adelay=${atraso}|${atraso}[t${indice}]")
done < "$tempos"

[[ $indice -gt 0 ]] || { echo "montar-audio-video: nenhum trecho na lista" >&2; exit 1; }

rotulos=""
for n in $(seq 1 "$indice"); do rotulos+="[t${n}]"; done

# amix soma as faixas (cada uma atrasada); apad completa com silêncio até o fim
# do vídeo e o -shortest corta no último quadro — quem manda na duração é o
# vídeo, nunca o áudio.
filtro="$(printf '%s;' "${trechos[@]}")"
filtro+="${rotulos}amix=inputs=${indice}:normalize=0:duration=longest,apad[saida]"

argumentos=()
for entrada in "${entradas[@]}"; do argumentos+=(-i "$entrada"); done

echo "montar-audio-video: vídeo de $(LC_ALL=C printf '%.1f' "$duracao")s · ${indice} trechos de áudio"
ffmpeg -hide_banner -v warning \
  "${argumentos[@]}" \
  -filter_complex "$filtro" \
  -map 0:v:0 -map "[saida]" \
  -c:v copy -c:a libmp3lame -b:a 128k -ar 48000 \
  -shortest -movflags +faststart "$saida" -y

echo "montar-audio-video: gravado em $saida"
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,width,height \
  -of default=nw=1 "$saida" | sed 's/^/  v: /'
ffprobe -v error -show_entries format=duration -of csv=p=0 "$saida" |
  awk -v original="$duracao" '{ printf "  duração: %.1fs (gravação tinha %.1fs)\n", $1, original }'
echo "  o vídeo não foi recodificado: confira com 'ffmpeg -i $saida' que o stream de vídeo é o original."

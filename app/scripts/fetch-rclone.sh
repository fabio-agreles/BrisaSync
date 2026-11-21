#!/usr/bin/env bash
# Baixa as cópias do rclone que vão embutidas nos pacotes.
#
# Os binários (~82 MB cada) não ficam no repositório: este script busca a versão
# fixada em `src-tauri/resources/` na hora do build. `tauri build` precisa do
# arquivo da plataforma alvo; o Flatpak monta o seu próprio
# (`flatpak/app.brisasync.BrisaSync.json`).
#
# Uso: scripts/fetch-rclone.sh [versão] [linux|windows|todos]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
versao="${1:-1.75.2}"
alvo="${2:-todos}"
recursos="${BRISASYNC_RESOURCES:-$root/src-tauri/resources}"
mkdir -p "$recursos"

baixar() {
  local sistema="$1" destino="$2"
  local pasta="rclone-v$versao-$sistema-amd64"

  if [[ -f "$destino" ]]; then
    echo "fetch-rclone: $destino já existe"
    return 0
  fi

  echo "fetch-rclone: baixando rclone v$versao para $sistema…"
  local tmp
  tmp="$(mktemp -d)"

  if ! curl -fsSL -o "$tmp/rclone.zip" "https://downloads.rclone.org/v$versao/$pasta.zip"; then
    rm -rf "$tmp"
    echo "fetch-rclone: não consegui baixar $pasta.zip" >&2
    return 1
  fi

  unzip -q "$tmp/rclone.zip" -d "$tmp"
  if [[ "$sistema" == "windows" ]]; then
    cp "$tmp/$pasta/rclone.exe" "$destino"
  else
    cp "$tmp/$pasta/rclone" "$destino"
    chmod +x "$destino"
  fi
  rm -rf "$tmp"
}

case "$alvo" in
  linux) baixar linux "$recursos/rclone" ;;
  windows) baixar windows "$recursos/rclone.exe" ;;
  todos)
    baixar linux "$recursos/rclone"
    baixar windows "$recursos/rclone.exe"
    ;;
  *)
    echo "fetch-rclone: alvo desconhecido '$alvo' (use linux, windows ou todos)" >&2
    exit 1
    ;;
esac

ls -lh "$recursos" | sed 's/^/  /'

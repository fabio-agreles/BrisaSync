#!/usr/bin/env bash
# Builda o Flatpak e anexa o bundle na Release do tag indicado.
#
# Por que não está no CI: construir Flatpak no GitHub Actions exige baixar o
# runtime org.gnome.Platform (~1 GB) e o SDK, o que deixa o job lento e sujeito
# a estouro de memória; o Tauri e o NSIS já saem prontos lá. Então este passo é
# local e explícito — e é fácil de esquecer, que é justamente o motivo do script.
#
# Uso (de dentro de app/):
#   scripts/publicar-flatpak.sh v1.2.1
set -euo pipefail

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "uso: scripts/publicar-flatpak.sh <tag>   ex.: scripts/publicar-flatpak.sh v1.2.1" >&2
  exit 2
fi

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

versao="$(python3 -c 'import json;print(json.load(open("package.json"))["version"])')"
bundle="$raiz/../Nuvem-Sync-$versao-x86_64.flatpak"

echo "publicar-flatpak: construindo a $versao (par OAuth de .env.oauth, se existir)"
scripts/build-flatpak.sh

if [[ ! -f "$bundle" ]]; then
  echo "publicar-flatpak: esperava o bundle em $bundle" >&2
  exit 1
fi

# Confere o anexo do lado do servidor depois de enviar.
gh release upload "$tag" "$bundle" --clobber
gh release view "$tag" --json assets \
  -q '.assets[] | "\(.name)  \(.size)"' | grep -F "$(basename "$bundle")" \
  || { echo "publicar-flatpak: o anexo não apareceu na Release $tag" >&2; exit 1; }

echo "publicar-flatpak: $(basename "$bundle") publicado na Release $tag"

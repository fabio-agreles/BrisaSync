#!/usr/bin/env bash
# Build do Flatpak com o projeto OAuth do BrisaSync embutido.
#
# `flatpak-builder` não tem `--env`: o par só entra no build pelo
# `build-options.env` do manifesto. Este script gera um manifesto temporário
# com o par (a partir de `.env.oauth`) e apaga o arquivo ao terminar — assim o
# segredo nunca vai para o git nem para o repositório público.
#
# Uso:
#   scripts/build-flatpak.sh            # build + instala + gera o .flatpak
#   scripts/build-flatpak.sh --sem-bundle
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifesto="$raiz/flatpak/app.brisasync.BrisaSync.json"
temporario="$raiz/flatpak/app.brisasync.BrisaSync.build.json"
repo="$raiz/../flatpak-repo"
builddir="$raiz/../builddir"
versao="$(python3 -c 'import json;print(json.load(open("'"$raiz"'/package.json"))["version"])')"
bundle="$raiz/../BrisaSync-$versao-x86_64.flatpak"

limpar() { rm -f "$temporario"; }
trap limpar EXIT

# Par do projeto (opcional: sem ele o build sai com o projeto do rclone).
par_id=""; par_segredo=""
if [[ -f "$raiz/.env.oauth" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$raiz/.env.oauth"; set +a
  par_id="${BRISASYNC_GOOGLE_CLIENT_ID:-}"
  par_segredo="${BRISASYNC_GOOGLE_CLIENT_SECRET:-}"
fi

python3 - "$manifesto" "$temporario" "$par_id" "$par_segredo" <<'PY'
import json, sys

origem, destino, client_id, segredo = sys.argv[1:5]
manifesto = json.load(open(origem))
for modulo in manifesto["modules"]:
    if isinstance(modulo, dict) and modulo.get("name") == "brisasync" and client_id and segredo:
        modulo["build-options"].setdefault("env", {}).update({
            "BRISASYNC_GOOGLE_CLIENT_ID": client_id,
            "BRISASYNC_GOOGLE_CLIENT_SECRET": segredo,
        })
json.dump(manifesto, open(destino, "w"), indent=2, ensure_ascii=False)
PY

if [[ -n "$par_id" && -n "$par_segredo" ]]; then
  echo "build-flatpak: embutindo o projeto OAuth ${par_id:0:14}…"
else
  echo "build-flatpak: sem par do .env.oauth — o app vai usar o projeto do rclone."
fi

rm -rf "$builddir/.flatpak-builder"
flatpak run --user org.flatpak.Builder \
  --force-clean --user --install \
  --install-deps-from=flathub \
  --repo="$repo" \
  "$builddir" "$temporario"

if [[ "${1:-}" != "--sem-bundle" ]]; then
  rm -f "$bundle"
  flatpak build-bundle --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
    "$repo" "$bundle" app.brisasync.BrisaSync master
  ls -lh "$bundle"
fi

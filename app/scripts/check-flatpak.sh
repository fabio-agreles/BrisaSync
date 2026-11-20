#!/usr/bin/env bash
# Confere o que o Flathub cobra antes de um PR: manifesto com JSON válido,
# .desktop e metainfo sem avisos, capturas de tela que existem de verdade e
# versão das <releases> igual à do app.
#
# Roda de qualquer diretório:   scripts/check-flatpak.sh
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

manifesto="flatpak/app.brisasync.BrisaSync.json"
metainfo="flatpak/app.brisasync.BrisaSync.metainfo.xml"
desktop="flatpak/app.brisasync.BrisaSync.desktop"
falhou=0

erro() { echo "✘ $*" >&2; falhou=1; }
ok() { echo "✔ $*"; }

# 1) Manifesto é JSON válido e cita o metainfo, o .desktop e a licença.
if python3 -m json.tool "$manifesto" > /dev/null; then
  ok "$manifesto é JSON válido"
else
  erro "$manifesto não é JSON válido"
fi
for exigido in "$metainfo" "$desktop" "LICENSE"; do
  if grep -q "${exigido##*/}" "$manifesto"; then
    ok "manifesto instala ${exigido##*/}"
  else
    erro "manifesto não instala ${exigido##*/}"
  fi
done

# 2) .desktop e metainfo, se as ferramentas estiverem instaladas.
if command -v desktop-file-validate > /dev/null; then
  if saida=$(desktop-file-validate "$desktop" 2>&1); then
    ok "$desktop sem avisos"
  else
    erro "$desktop: $saida"
  fi
else
  echo "· desktop-file-validate ausente (desktop-file-utils); pulei o .desktop"
fi

if command -v appstreamcli > /dev/null; then
  if saida=$(appstreamcli validate --no-net "$metainfo" 2>&1); then
    ok "$metainfo validado pela AppStream"
    echo "$saida" | grep -E "^(W|E):" && erro "avisos da AppStream acima"
  else
    erro "$metainfo: $saida"
  fi
else
  echo "· appstreamcli ausente; pulei o metainfo"
fi

# 3) Toda captura citada no metainfo existe em docs/previews.
mapfile -t imagens < <(grep -o 'docs/previews/[a-z0-9-]*\.png' "$metainfo" | sort -u)
for imagem in "${imagens[@]}"; do
  if [[ -f "$imagem" ]]; then
    ok "captura presente: $imagem"
  else
    erro "captura citada no metainfo não existe: $imagem"
  fi
done

# 4) A versão da <release> mais nova é a do package.json.
versao_app=$(python3 -c 'import json;print(json.load(open("package.json"))["version"])')
versao_appstream=$(grep -o 'release version="[^"]*"' "$metainfo" | head -1 | cut -d'"' -f2)
if [[ "$versao_app" == "$versao_appstream" ]]; then
  ok "versão $versao_app no metainfo e no package.json"
else
  erro "metainfo anuncia $versao_appstream, package.json diz $versao_app"
fi

if [[ $falhou -ne 0 ]]; then
  echo "check-flatpak: há pendências acima." >&2
  exit 1
fi
echo "check-flatpak: tudo certo."

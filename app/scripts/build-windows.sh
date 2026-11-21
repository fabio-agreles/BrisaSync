#!/usr/bin/env bash
# Monta a versão do Windows (x64) a partir do Linux.
#
# O Tauri gera o `.exe` sem problema (cargo-xwin + MSVC no alvo), mas o
# instalador NSIS usa `makensis.exe` — ou seja, só é gerado no próprio Windows.
# O que sai daqui é o pacote **portátil**: `Nuvem.exe` (nome do binário, o
# mesmo desde a 1.0) + `rclone.exe` na mesma
# pasta, que é exatamente onde o app procura o motor de sincronização.
#
# Pré-requisitos (Linux):
#   rustup target add x86_64-pc-windows-msvc
#   cargo install cargo-xwin
#   clang, e `llvm-rc`/`llvm-lib` no PATH (pacote `llvm` ou a toolchain
#   llvm-mingw: https://github.com/mstorsjo/llvm-mingw/releases)
#
# Uso: scripts/build-windows.sh [versão-do-rclone]
set -euo pipefail

# Ferramentas do alvo MSVC: o `cargo-xwin` chama clang-cl e o `embed-resource`
# precisa de llvm-rc/llvm-lib para montar o manifesto do `.exe`.
for tool in clang llvm-rc llvm-lib; do
  if ! command -v "$tool" >/dev/null; then
    echo "build-windows: falta '$tool' no PATH." >&2
    echo "  Arch: sudo pacman -S llvm | Debian/Ubuntu: sudo apt install llvm" >&2
    echo "  ou use a toolchain llvm-mingw (https://github.com/mstorsjo/llvm-mingw/releases)" >&2
    exit 1
  fi
done

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rclone_version="${1:-1.75.2}"
recursos="$root/src-tauri/resources"
rclone_exe="$recursos/rclone.exe"
alvo="x86_64-pc-windows-msvc"
# A versão vem do package.json: assim o zip nunca sai com nome de versão velha.
versao="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["version"])' "$root/package.json")"
produto="BrisaSync-$versao-windows-x64"

# O par do projeto OAuth do BrisaSync entra embutido (`option_env!`) quando existe:
# sem ele o portátil sai com o projeto do rclone, mais lento e sujeito a
# "Rate limited". Mesmo padrão do build-flatpak.sh, e o .env.oauth não é
# versionado.
if [[ -f "$root/.env.oauth" ]]; then
  # shellcheck disable=SC1091
  set -a; source "$root/.env.oauth"; set +a
  echo "build-windows: par OAuth do BrisaSync embutido (${NUVEM_GOOGLE_CLIENT_ID:0:20}…)"
else
  echo "build-windows: sem .env.oauth — o portátil vai usar o projeto do rclone." >&2
fi

if [[ ! -f "$rclone_exe" ]]; then
  echo "build-windows: baixando rclone v$rclone_version para Windows…"
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  url="https://downloads.rclone.org/v$rclone_version/rclone-v$rclone_version-windows-amd64.zip"
  curl -fsSL -o "$tmp/rclone.zip" "$url"
  unzip -q "$tmp/rclone.zip" -d "$tmp"
  cp "$tmp/rclone-v$rclone_version-windows-amd64/rclone.exe" "$rclone_exe"
fi

echo "build-windows: compilando ($alvo)…"
cd "$root"
# `--no-bundle` deixa de lado o NSIS (que exigiria um Windows); o .exe sai igual.
npx tauri build --runner cargo-xwin --target "$alvo" --no-bundle

saida="$root/src-tauri/target/$alvo/release"
destino="$saida/bundle/windows-portatil/$produto"
rm -rf "$destino"
mkdir -p "$destino"

# Binário do Tauri: brisasync.exe
if [[ -f "$saida/brisasync.exe" ]]; then
  cp "$saida/brisasync.exe" "$destino/BrisaSync.exe"
elif [[ -f "$saida/nuvem.exe" ]]; then
  cp "$saida/nuvem.exe" "$destino/BrisaSync.exe"
fi
cp "$rclone_exe" "$destino/rclone.exe"
# A licença viaja junto: o pacote é o que o usuário recebe, não o repositório.
cp "$root/../LICENSE" "$destino/LICENSE"
cat > "$destino/LEIA-ME.txt" <<'TXT'
BrisaSync — pacote portátil para Windows
====================================

Como usar
---------
1. Extraia esta pasta em qualquer lugar (ex.: C:\Program Files\BrisaSync
   ou %LOCALAPPDATA%\BrisaSync).
2. Execute BrisaSync.exe.

Não precisa instalar o rclone: o rclone.exe desta pasta é o motor de
sincronização e o BrisaSync o encontra sozinho. Se quiser usar outro, defina a
variável de ambiente NUVEM_RCLONE com o caminho do executável.

Requisitos
----------
* Windows 10 ou 11 (64 bits).
* WebView2 — já vem no Windows 11 e no Windows 10 atualizado. Se a janela abrir
  em branco, instale o "Evergreen Bootstrapper" em
  https://developer.microsoft.com/microsoft-edge/webview2/

Dados e configuração
--------------------
Ficam em %APPDATA%\app.brisasync.BrisaSync (perfis, ajustes, histórico de atividade) e
%APPDATA%\rclone (rclone.conf, com os tokens das contas). Nada é enviado para
servidores externos.

Iniciar com o Windows
---------------------
Ajustes → "Abrir com o sistema". Isso grava a entrada na chave Run do registro
do usuário (HKCU\Software\Microsoft\Windows\CurrentVersion\Run), a mesma que o
Gerenciador de Tarefas mostra na aba "Inicializar".
TXT

echo "build-windows: empacotando…"
# `zip` não existe em toda distro; o zipfile do Python escreve o mesmo formato
# (e preserva as pastas do jeito que o Explorador do Windows espera).
python3 - "$destino" "$destino.zip" <<'PY'
import pathlib, sys, zipfile

origem = pathlib.Path(sys.argv[1])
alvo = pathlib.Path(sys.argv[2])
raiz = origem.name
with zipfile.ZipFile(alvo, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for caminho in sorted(origem.rglob("*")):
        if caminho.is_file():
            z.write(caminho, pathlib.Path(raiz) / caminho.relative_to(origem))
PY
ls -lh "$destino.zip"

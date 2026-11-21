#!/usr/bin/env bash
# Script unificado para compilar todas as versões do BrisaSync
# (Execute no terminal do seu computador)
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$raiz"

echo "============================================="
echo "   Iniciando compilação do BrisaSync v1.0.0"
echo "============================================="

# 1. Compilar Frontend
echo ""
echo "[1/4] Compilando Frontend (React/Vite)..."
npm run build

# 2. Compilar Pacotes Linux (.deb e .AppImage)
echo ""
echo "[2/4] Gerando .deb e .AppImage..."
if command -v cargo >/dev/null; then
  npm run tauri:build
  echo "✓ Linux (.deb e .AppImage) gerados em src-tauri/target/release/bundle/"
else
  echo "⚠️ 'cargo' não encontrado. Pulei o build de .deb/.AppImage."
fi

# 3. Compilar Pacote Windows Portátil
echo ""
echo "[3/4] Gerando pacote portátil para Windows (.zip)..."
if command -v cargo-xwin >/dev/null && command -v clang >/dev/null; then
  bash scripts/build-windows.sh
  echo "✓ Windows portátil gerado!"
else
  echo "ℹ️ Ferramentas cargo-xwin/clang não detectadas para Windows cross-compile. Para gerar Windows, instale cargo-xwin ou rode scripts/build-windows.sh."
fi

# 4. Compilar Flatpak
echo ""
echo "[4/4] Gerando Flatpak (.flatpak)..."
if command -v flatpak-builder >/dev/null || flatpak info org.flatpak.Builder >/dev/null 2>&1; then
  bash scripts/build-flatpak.sh
  echo "✓ Pacote Flatpak gerado na raiz do projeto!"
else
  echo "ℹ️ flatpak-builder não detectado. Para gerar o Flatpak, rode scripts/build-flatpak.sh."
fi

echo ""
echo "============================================="
echo "   Processo concluído!"
echo "============================================="

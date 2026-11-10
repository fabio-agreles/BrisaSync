#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
APPDIR="${SCRIPT_DIR}/AppDir"
VERSION="0.1.26"
OUTPUT_APPIMAGE="${DIST_DIR}/BrisaSync-${VERSION}-x86_64.AppImage"

echo "=== 1. Preparando estrutura do AppDir para BrisaSync v${VERSION} ==="
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/lib/brisasync/bin"
mkdir -p "${APPDIR}/usr/lib/brisasync/src"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/512x512/apps"

# 1. Copiar código-fonte da aplicação
cp -a "${REPO_ROOT}/src/brisasync" "${APPDIR}/usr/lib/brisasync/src/"

# 2. Copiar binário rclone
RCLONE_SRC="${HOME}/.local/bin/rclone"
if [ ! -f "${RCLONE_SRC}" ]; then
    RCLONE_SRC="$(which rclone || true)"
fi
if [ -z "${RCLONE_SRC}" ] || [ ! -x "${RCLONE_SRC}" ]; then
    echo "ERRO: rclone não encontrado em ~/.local/bin/rclone nem no PATH." >&2
    exit 1
fi
cp -f "${RCLONE_SRC}" "${APPDIR}/usr/lib/brisasync/bin/rclone"
chmod +x "${APPDIR}/usr/lib/brisasync/bin/rclone"

# 3. Criar lançador interno /usr/bin/brisasync
cat > "${APPDIR}/usr/bin/brisasync" << 'EOF'
#!/usr/bin/env sh
HERE="$(dirname "$(readlink -f "${0}")")/.."
export PYTHONPATH="${HERE}/lib/brisasync/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HERE}/lib/brisasync/bin:${PATH}"
exec /usr/bin/python3 -m brisasync.main "$@"
EOF
chmod +x "${APPDIR}/usr/bin/brisasync"

# 4. Criar AppRun na raiz do AppDir
cat > "${APPDIR}/AppRun" << 'EOF'
#!/usr/bin/env sh
HERE="$(dirname "$(readlink -f "${0}")")"
export APPDIR="${HERE}"
export PATH="${HERE}/usr/bin:${HERE}/usr/lib/brisasync/bin:${PATH}"
export PYTHONPATH="${HERE}/usr/lib/brisasync/src${PYTHONPATH:+:$PYTHONPATH}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

# Se Python local do sistema existir, usa; caso contrário, executa python3 disponível
PYTHON_BIN="$(which python3 || echo "/usr/bin/python3")"
if [ ! -x "${PYTHON_BIN}" ]; then
    echo "ERRO: Python 3 não foi localizado no sistema hospedeiro." >&2
    exit 1
fi

exec "${PYTHON_BIN}" -m brisasync.main "$@"
EOF
chmod +x "${APPDIR}/AppRun"

# 5. Ícones e arquivos de desktop
DESKTOP_SRC="${REPO_ROOT}/packaging/brisasync.desktop"
cp -f "${DESKTOP_SRC}" "${APPDIR}/brisasync.desktop"
cp -f "${DESKTOP_SRC}" "${APPDIR}/usr/share/applications/brisasync.desktop"

mkdir -p "${APPDIR}/usr/share/metainfo"
cp -f "${REPO_ROOT}/packaging/org.brisasync.BrisaSync.metainfo.xml" "${APPDIR}/usr/share/metainfo/org.brisasync.BrisaSync.metainfo.xml"

# Copiar ícones de todas as resoluções
cp -a "${REPO_ROOT}/src/brisasync/resources/icons/hicolor" "${APPDIR}/usr/share/icons/"
ICON_256="${REPO_ROOT}/src/brisasync/resources/icons/hicolor/256x256/apps/brisasync.png"
if [ -f "${ICON_256}" ]; then
    cp -f "${ICON_256}" "${APPDIR}/brisasync.png"
    cp -f "${ICON_256}" "${APPDIR}/.DirIcon"
fi

echo "=== 2. Construindo AppImage ==="
TOOL_PATH="$(which appimagetool || true)"

if [ -z "${TOOL_PATH}" ]; then
    DOWNLOAD_DIR="${SCRIPT_DIR}/.tools"
    mkdir -p "${DOWNLOAD_DIR}"
    APPIMAGETOOL_BIN="${DOWNLOAD_DIR}/appimagetool-x86_64.AppImage"
    if [ ! -f "${APPIMAGETOOL_BIN}" ]; then
        echo "Baixando appimagetool..."
        curl -fSL -o "${APPIMAGETOOL_BIN}" "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage" || \
        curl -fSL -o "${APPIMAGETOOL_BIN}" "https://github.com/AppImage/AppImageKit/releases/download/13/appimagetool-x86_64.AppImage"
        chmod +x "${APPIMAGETOOL_BIN}"
    fi
    TOOL_PATH="${APPIMAGETOOL_BIN}"
fi

mkdir -p "${DIST_DIR}"

# Executa appimagetool (usando --appimage-extract-and-run se for um AppImage)
echo "Executando appimagetool..."
ARCH=x86_64 "${TOOL_PATH}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_APPIMAGE}" || \
ARCH=x86_64 "${TOOL_PATH}" "${APPDIR}" "${OUTPUT_APPIMAGE}"

echo "✓ AppImage gerado com sucesso em: ${OUTPUT_APPIMAGE}"
ls -lh "${OUTPUT_APPIMAGE}"

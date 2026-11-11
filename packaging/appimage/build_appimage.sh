#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"
APPDIR="${SCRIPT_DIR}/AppDir"
BUILD_TMP="${SCRIPT_DIR}/.build_tmp"
VERSION="0.1.28"
OUTPUT_APPIMAGE="${DIST_DIR}/BrisaSync-${VERSION}-x86_64.AppImage"

echo "=== 1. Localizando ambiente de compilação PyInstaller ==="
PYINSTALLER=""
if [ -x "${REPO_ROOT}/.venv/bin/pyinstaller" ]; then
    PYINSTALLER="${REPO_ROOT}/.venv/bin/pyinstaller"
elif which pyinstaller >/dev/null 2>&1; then
    PYINSTALLER="$(which pyinstaller)"
elif python3 -m PyInstaller --version >/dev/null 2>&1; then
    PYINSTALLER="python3 -m PyInstaller"
else
    echo "ERRO: PyInstaller não encontrado. Instale com 'pip install pyinstaller'." >&2
    exit 1
fi

echo "Usando PyInstaller: ${PYINSTALLER}"

echo "=== 2. Compilando runtime Python + PySide6/Qt6 standalone para AppImage ==="
rm -rf "${BUILD_TMP}"
mkdir -p "${BUILD_TMP}"

${PYINSTALLER} --noconfirm --onedir --name brisasync \
    --paths "${REPO_ROOT}/src" \
    --add-data "${REPO_ROOT}/src/brisasync/resources:brisasync/resources" \
    --add-data "${REPO_ROOT}/src/brisasync/i18n:brisasync/i18n" \
    --hidden-import "brisasync" \
    --hidden-import "brisasync.platform_compat" \
    --hidden-import "brisasync.credentials.oauth_google" \
    --hidden-import "brisasync.credentials.rclone_bridge" \
    --hidden-import "brisasync.credentials.store" \
    --hidden-import "brisasync.service.daemon" \
    --hidden-import "brisasync.service.ipc_client" \
    --hidden-import "brisasync.service.autostart" \
    --hidden-import "brisasync.orchestrator.sync_coordinator" \
    --hidden-import "brisasync.orchestrator.diagnostics" \
    --hidden-import "brisasync.backend.rclone_engine" \
    --hidden-import "brisasync.storage.database" \
    --hidden-import "brisasync.ui.main_window" \
    --hidden-import "brisasync.ui.tray" \
    --hidden-import "brisasync.ui.single_instance" \
    --hidden-import "PySide6.QtCore" \
    --hidden-import "PySide6.QtGui" \
    --hidden-import "PySide6.QtWidgets" \
    --hidden-import "PySide6.QtSvg" \
    --hidden-import "PySide6.QtDBus" \
    --hidden-import "PySide6.QtNetwork" \
    --exclude-module "PySide6.QtWebEngine" \
    --exclude-module "PySide6.QtWebEngineCore" \
    --exclude-module "PySide6.QtWebEngineWidgets" \
    --exclude-module "PySide6.QtQuick3D" \
    --exclude-module "PySide6.Qt3DCore" \
    --exclude-module "PySide6.Qt3DAnimation" \
    --exclude-module "PySide6.Qt3DRender" \
    --exclude-module "PySide6.QtSensors" \
    --exclude-module "PySide6.QtMultimedia" \
    --exclude-module "PySide6.QtMultimediaWidgets" \
    --exclude-module "PySide6.QtPositioning" \
    --exclude-module "PySide6.QtLocation" \
    --exclude-module "PySide6.QtCharts" \
    --exclude-module "PySide6.QtBluetooth" \
    --exclude-module "PySide6.QtNfc" \
    --exclude-module "PySide6.QtSpatialAudio" \
    --exclude-module "PySide6.QtSerialPort" \
    --exclude-module "PySide6.QtSerialBus" \
    --exclude-module "PySide6.QtTest" \
    --distpath "${BUILD_TMP}/dist" \
    --workpath "${BUILD_TMP}/build" \
    "${REPO_ROOT}/src/brisasync/main.py"

echo "=== 3. Preparando estrutura do AppDir para BrisaSync v${VERSION} ==="
rm -rf "${APPDIR}"
mkdir -p "${APPDIR}/usr/bin"
mkdir -p "${APPDIR}/usr/lib/brisasync/bin"
mkdir -p "${APPDIR}/usr/share/applications"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/scalable/apps"
mkdir -p "${APPDIR}/usr/share/icons/hicolor/512x512/apps"

# 1. Copiar a pasta standalone gerada pelo PyInstaller
cp -a "${BUILD_TMP}/dist/brisasync/." "${APPDIR}/usr/lib/brisasync/"

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
cp -f "${RCLONE_SRC}" "${APPDIR}/usr/bin/rclone"
chmod +x "${APPDIR}/usr/lib/brisasync/bin/rclone" "${APPDIR}/usr/bin/rclone"

# 3. Criar executável no PATH padrão do AppDir
cat > "${APPDIR}/usr/bin/brisasync" << 'EOF'
#!/usr/bin/env sh
HERE="$(dirname "$(readlink -f "${0}")")/.."
export APPDIR="${HERE}"
export PATH="${HERE}/bin:${HERE}/lib/brisasync/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/lib/brisasync/_internal:${HERE}/lib:${LD_LIBRARY_PATH:-}"
export QT_PLUGIN_PATH="${HERE}/lib/brisasync/_internal/PySide6/Qt/plugins:${QT_PLUGIN_PATH:-}"
export XDG_DATA_DIRS="${HERE}/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"
exec "${HERE}/lib/brisasync/brisasync" "$@"
EOF
chmod +x "${APPDIR}/usr/bin/brisasync"

# 4. Criar AppRun na raiz do AppDir
cat > "${APPDIR}/AppRun" << 'EOF'
#!/usr/bin/env sh
HERE="$(dirname "$(readlink -f "${0}")")"
export APPDIR="${HERE}"
export PATH="${HERE}/usr/bin:${HERE}/usr/lib/brisasync/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/lib/brisasync/_internal:${HERE}/usr/lib:${LD_LIBRARY_PATH:-}"
export QT_PLUGIN_PATH="${HERE}/usr/lib/brisasync/_internal/PySide6/Qt/plugins:${QT_PLUGIN_PATH:-}"
export XDG_DATA_DIRS="${HERE}/usr/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}"

exec "${HERE}/usr/lib/brisasync/brisasync" "$@"
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

# Limpeza temporária
rm -rf "${BUILD_TMP}"

echo "=== 4. Construindo AppImage ==="
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

# Executa appimagetool
echo "Executando appimagetool..."
ARCH=x86_64 "${TOOL_PATH}" --appimage-extract-and-run "${APPDIR}" "${OUTPUT_APPIMAGE}" || \
ARCH=x86_64 "${TOOL_PATH}" "${APPDIR}" "${OUTPUT_APPIMAGE}"

echo "[OK] AppImage gerado com sucesso em: ${OUTPUT_APPIMAGE}"
ls -lh "${OUTPUT_APPIMAGE}"

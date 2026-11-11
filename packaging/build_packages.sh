#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION="0.1.27"
OAUTH_CLIENT_SRC="${BRISASYNC_DIST_OAUTH_CLIENT_JSON:-}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-oauth-client)
            OAUTH_CLIENT_SRC="$2"
            shift 2
            ;;
        *)
            echo "Opção desconhecida: $1" >&2
            echo "Uso: $0 [--with-oauth-client <caminho_json>]" >&2
            exit 1
            ;;
    esac
done

echo "=== 1. Preparando metadados públicos de cliente OAuth Desktop ==="
ARCH_DIR="${REPO_ROOT}/packaging/arch"
mkdir -p "${ARCH_DIR}"

if [ -n "${OAUTH_CLIENT_SRC}" ] && [ -f "${OAUTH_CLIENT_SRC}" ]; then
    echo "Higienizando cliente explicitamente fornecido: ${OAUTH_CLIENT_SRC}"
    python3 "${SCRIPT_DIR}/sanitize_oauth_client.py" "${OAUTH_CLIENT_SRC}" \
        "${ARCH_DIR}/google_oauth_client.json" \
        "${REPO_ROOT}/src/brisasync/resources/oauth/google_oauth_client.json"
elif [ -f "${ARCH_DIR}/google_oauth_client.json" ]; then
    echo "Revalidando cliente já presente em packaging/arch/google_oauth_client.json..."
    python3 "${SCRIPT_DIR}/sanitize_oauth_client.py" "${ARCH_DIR}/google_oauth_client.json" \
        "${ARCH_DIR}/google_oauth_client.json" \
        "${REPO_ROOT}/src/brisasync/resources/oauth/google_oauth_client.json"
else
    echo "AVISO: Nenhum cliente OAuth Desktop fornecido. Pacote será construído sem cliente oficial embutido."
fi

echo "=== 1.1 Gerando recurso local do Pix QR Code ==="
python3 -c "
import sys
sys.path.insert(0, '${REPO_ROOT}/src')
from brisasync.support import generate_pix_qr_code
qr = generate_pix_qr_code()
print(f'✓ Pix QR Code gerado em: {qr}')
"

echo "=== 2. Construindo sdist e wheel oficiais (${VERSION}) em dist/ ==="
cd "${REPO_ROOT}"
mkdir -p dist
uv build --no-build-isolation -o dist/

TARBALL="${REPO_ROOT}/dist/brisasync-${VERSION}.tar.gz"
WHEEL="${REPO_ROOT}/dist/brisasync-${VERSION}-py3-none-any.whl"

if [ ! -f "${TARBALL}" ] || [ ! -f "${WHEEL}" ]; then
    echo "ERRO: Artefatos dist/ não foram gerados corretamente." >&2
    exit 1
fi

echo "=== 3. Preparando fontes para PKGBUILD em packaging/arch/ ==="
cp -f "${TARBALL}" "${ARCH_DIR}/brisasync-${VERSION}.tar.gz"
cp -f "${REPO_ROOT}/LICENSE" "${ARCH_DIR}/LICENSE"
cp -f "${REPO_ROOT}/THIRD_PARTY_NOTICES.md" "${ARCH_DIR}/THIRD_PARTY_NOTICES.md"

RCLONE_SRC="${HOME}/.local/bin/rclone"
if [ ! -f "${RCLONE_SRC}" ]; then
    RCLONE_SRC="$(which rclone || true)"
fi

if [ -z "${RCLONE_SRC}" ] || [ ! -x "${RCLONE_SRC}" ]; then
    echo "ERRO: Binário rclone não encontrado em ${HOME}/.local/bin/rclone nem no PATH." >&2
    exit 1
fi

cp -f "${RCLONE_SRC}" "${ARCH_DIR}/rclone-v1.75.2-linux-amd64.bin"
chmod +x "${ARCH_DIR}/rclone-v1.75.2-linux-amd64.bin"

# Atualizar somas de verificação reais no PKGBUILD com updpkgsums
cd "${ARCH_DIR}"
sed -i "s/pkgver=.*/pkgver=${VERSION}/" "${ARCH_DIR}/PKGBUILD"
sed -i 's/pkgrel=.*/pkgrel=1/' "${ARCH_DIR}/PKGBUILD"
updpkgsums

echo "=== 4. Construindo brisasync-${VERSION}-1-x86_64.pkg.tar.zst com makepkg ==="
export PKGEXT='.pkg.tar.zst'
sed -i 's/pkgrel=.*/pkgrel=1/' "${ARCH_DIR}/PKGBUILD"
makepkg -f --nodeps
PKG1="$(PKGEXT='.pkg.tar.zst' makepkg --packagelist)"
cp -f "${PKG1}" "${REPO_ROOT}/dist/"

echo "=== 5. Construindo brisasync-${VERSION}-2-x86_64.pkg.tar.zst para teste de atualização ==="
sed -i 's/pkgrel=.*/pkgrel=2/' "${ARCH_DIR}/PKGBUILD"
makepkg -f --nodeps
PKG2="$(PKGEXT='.pkg.tar.zst' makepkg --packagelist)"
cp -f "${PKG2}" "${REPO_ROOT}/dist/"
sed -i 's/pkgrel=.*/pkgrel=1/' "${ARCH_DIR}/PKGBUILD"

echo "=== 6. Construindo pacote Debian/Ubuntu amd64 (.deb) ==="
cd "${REPO_ROOT}"
python3 "${REPO_ROOT}/packaging/deb/build_deb.py"

echo "=== 7. Construindo pacote AppImage x86_64 (.AppImage) ==="
"${REPO_ROOT}/packaging/appimage/build_appimage.sh"

echo "=== 8. Atualizando somas de verificação SHA-256 específicas da release em dist/SHA256SUMS.txt ==="
cd "${REPO_ROOT}/dist"
# Gera checksum específico para os anexos da release atual
rm -f SHA256SUMS.txt
sha256sum \
    "brisasync-${VERSION}-1-x86_64.pkg.tar.zst" \
    "brisasync-${VERSION}-2-x86_64.pkg.tar.zst" \
    "brisasync_${VERSION}-1_amd64.deb" \
    "BrisaSync-${VERSION}-x86_64.AppImage" \
    "brisasync-${VERSION}-py3-none-any.whl" \
    "brisasync-${VERSION}.tar.gz" > SHA256SUMS.txt
cp -f SHA256SUMS.txt "SHA256SUMS-${VERSION}.txt"
echo "✓ SHA256SUMS.txt específico da v${VERSION} atualizado com sucesso:"
cat SHA256SUMS.txt

echo "=== 9. Resumo dos artefatos em dist/ ==="
ls -lh "${REPO_ROOT}/dist"

echo "=== Construção de pacotes ${VERSION} concluída com sucesso! ==="

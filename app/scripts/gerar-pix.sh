#!/usr/bin/env bash
# Gera o QR code do Pix e o texto do "copia e cola" usados na tela de doações.
#
# O Pix não aceita qualquer QR: é preciso um BR Code (EMV, padrão do Banco
# Central) com os campos na ordem certa e um CRC16 no fim. Este script monta o
# BR Code estático, desenha o QR com o qrencode e grava:
#
#   src/assets/pix-qr.svg   → o QR (fundo branco, área de silêncio de 2 módulos)
#   src/lib/pix.ts          → a chave e o BR Code, importados pelo app
#
# Uso:
#   bash scripts/gerar-pix.sh                    # usa os valores abaixo
#   PIX_CHAVE=... PIX_RECEBEDOR=... PIX_CIDADE=... bash scripts/gerar-pix.sh
#
# Trocar a chave, o recebedor ou a cidade = editar as três variáveis e rodar de
# novo. Os dois arquivos andam juntos: o QR e o "copia e cola" sempre apontam
# para a mesma chave.
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ---------------------------------------------------------------- dados do Pix
CHAVE="${PIX_CHAVE:-e4bf0532-8016-42bf-bf2a-fd81326b6621}"
RECEBEDOR="${PIX_RECEBEDOR:-Fábio Agreles Bezerra}"
CIDADE="${PIX_CIDADE:-SAO PAULO}"

if ! command -v qrencode >/dev/null 2>&1; then
  echo "gerar-pix: falta o qrencode (sudo apt install qrencode)" >&2
  exit 1
fi

# ------------------------------------------------------------------- BR Code
# Campos do padrão: 00 payload format · 26 conta do recebedor (Pix) · 52 MCC ·
# 53 moeda · 58 país · 59 nome · 60 cidade · 62 dados adicionais (txid) ·
# 63 CRC16. Cada campo é "ID + tamanho em 2 dígitos + valor".
payload="$(python3 - "$CHAVE" "$RECEBEDOR" "$CIDADE" <<'PY'
import sys
import unicodedata

chave, nome, cidade = sys.argv[1:4]


def campo(id_, valor):
    return f"{id_}{len(valor.encode('utf-8')):02d}{valor}"


def crc16(texto):
    """CRC16/CCITT-FALSE: polinômio 0x1021, inicial 0xFFFF."""
    crc = 0xFFFF
    for byte in texto.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def limpar(texto, limite):
    """O BR Code só aceita ASCII maiúsculo sem acento nos campos de texto."""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())[:limite]


nome = limpar(nome, 25)
cidade = limpar(cidade, 15)
if not nome or not cidade:
    sys.exit("gerar-pix: nome do recebedor e cidade são obrigatórios")

conta = campo("00", "br.gov.bcb.pix") + campo("01", chave.strip())
# txid "***" = cobrança sem identificador, o caso do Pix doação.
payload = (
    campo("00", "01")
    + campo("26", conta)
    + campo("52", "0000")
    + campo("53", "986")
    + campo("58", "BR")
    + campo("59", nome)
    + campo("60", cidade)
    + campo("62", campo("05", "***"))
    + "6304"
)
print(payload + crc16(payload))
PY
)"

if [[ ${#payload} -gt 400 ]]; then
  echo "gerar-pix: BR Code com ${#payload} caracteres — chave longa demais?" >&2
  exit 1
fi

# ------------------------------------------------------------------------- QR
mkdir -p "$raiz/src/assets"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

# -l M: correção de erro média (a leitura no app do banco agradece).
# -m 2: área branca de silêncio em volta, exigida pela especificação.
qrencode -t SVG -l M -s 6 -m 2 -o "$tmp/pix.svg" "$payload"

# O qrencode escreve width/height em centímetros. Trocamos por nada e ficamos só
# com o viewBox, para o CSS mandar no tamanho (o QR é exibido em 220×220).
sed -E 's/ width="[0-9.]+cm" height="[0-9.]+cm"//' "$tmp/pix.svg" \
  > "$raiz/src/assets/pix-qr.svg"

# ------------------------------------------------------- módulo do TypeScript
python3 - "$raiz/src/lib/pix.ts" "$CHAVE" "$payload" <<'PY'
import sys

destino, chave, payload = sys.argv[1:4]


def aspas(texto):
    return texto.replace("\\", "\\\\").replace('"', '\\"')


with open(destino, "w", encoding="utf-8") as arquivo:
    arquivo.write(
        "// GERADO por scripts/gerar-pix.sh — não edite à mão.\n"
        "// Para trocar a chave do Pix, edite o script e rode de novo: o QR e o\n"
        "// texto do \"copia e cola\" saem sempre do mesmo BR Code.\n"
        "\n"
        "/// Chave Pix do projeto (aparece no diálogo de doações).\n"
        f'export const CHAVE_PIX = "{aspas(chave)}";\n'
        "\n"
        "/// BR Code completo, no formato que os bancos chamam de \"Pix copia e cola\".\n"
        f'export const PIX_COPIA_E_COLA = "{aspas(payload)}";\n'
    )
PY

# ------------------------------------------------------- conferência do QR
# Lê o QR gerado de volta (se houver zbarimg) e compara com o BR Code. Um QR
# desenhado errado só aparece na hora da doação — melhor descobrir aqui.
if command -v zbarimg >/dev/null 2>&1; then
  lido="$(zbarimg --quiet --raw "$raiz/src/assets/pix-qr.svg" 2>/dev/null | head -n 1 || true)"
  if [[ "$lido" != "$payload" ]]; then
    echo "gerar-pix: o QR não voltou igual ao BR Code" >&2
    echo "  esperado: $payload" >&2
    echo "  lido:     $lido" >&2
    exit 1
  fi
  echo "gerar-pix: QR conferido (lido de volta com zbarimg)"
fi

echo "gerar-pix: QR em src/assets/pix-qr.svg ($(wc -c < "$raiz/src/assets/pix-qr.svg") bytes)"
echo "gerar-pix: BR Code com ${#payload} caracteres"
echo "gerar-pix: recebedor \"$RECEBEDOR\" · cidade \"$CIDADE\" · chave \"$CHAVE\""

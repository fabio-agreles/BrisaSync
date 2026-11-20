#!/usr/bin/env bash
# Corrige o control do .deb gerado pelo Tauri:
#   - remove duplicatas em Depends (o bundler mescla o autodetectado com o configurado);
#   - tira `libappindicator3-1` do Depends e deixa `libayatana-appindicator3-1` em
#     Recommends, porque a bandeja usa dlopen (libappindicator-sys) e o pacote
#     `libappindicator3-1` não existe em distros novas (ex.: Ubuntu 24.04+).
#
# Uso: scripts/fix-deb.sh [caminho/do/arquivo.deb]
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
deb="${1:-}"

# Sem argumento, pega o .deb mais recente do bundle — o nome carrega a versão,
# então não dá para fixar `Nuvem_0.1.0_amd64.deb` aqui.
if [[ -z "$deb" ]]; then
  deb="$(ls -t "$root"/src-tauri/target/release/bundle/deb/*.deb 2>/dev/null | head -1)"
fi

if [[ -z "$deb" || ! -f "$deb" ]]; then
  echo "fix-deb: nenhum .deb em src-tauri/target/release/bundle/deb/ (rode 'npx tauri build --bundles deb')" >&2
  exit 1
fi

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
cd "$work"

ar x "$deb"
mkdir -p control
tar xzf control.tar.gz -C control

python3 - "$work" <<'PY'
import pathlib, sys

base = pathlib.Path(sys.argv[1]) / "control"
path = base / "control"
lines = path.read_text().splitlines()

OPTIONAL = {"libappindicator3-1", "libayatana-appindicator3-1"}


def clean(value, drop_optional):
    deps, seen = [], set()
    for dep in (part.strip() for part in value.split(",")):
        if not dep or dep in seen:
            continue
        if drop_optional and dep in OPTIONAL:
            continue
        seen.add(dep)
        deps.append(dep)
    return deps


depends, recommends = [], []
out, emitted = [], set()
for line in lines:
    key = line.split(":", 1)[0] if ":" in line and not line.startswith(" ") else None
    if key == "Depends":
        depends = clean(line.split(":", 1)[1], drop_optional=True)
        if "Depends" not in emitted and depends:
            emitted.add("Depends")
            out.append("Depends: " + ", ".join(depends))
        continue
    if key == "Recommends":
        recommends = clean(line.split(":", 1)[1], drop_optional=False)
        if "Recommends" not in emitted:
            emitted.add("Recommends")
            merged = recommends + (
                [] if "libayatana-appindicator3-1" in recommends else ["libayatana-appindicator3-1"]
            )
            out.append("Recommends: " + ", ".join(merged))
        continue
    out.append(line)

if "Recommends" not in emitted:
    out.append("Recommends: libayatana-appindicator3-1")

path.write_text("\n".join(out) + "\n")

# Mantém o pacote limpo do ambiente de build.
junk = base / "md5sums"
if junk.exists():
    junk.unlink()
PY

tar --owner=0 --group=0 -czf control.tar.gz -C control .
ar rc "$deb.new" debian-binary control.tar.gz data.tar.gz
mv "$deb.new" "$deb"

echo "fix-deb: $deb"
sed -n '/^Depends:/p;/^Recommends:/p' control/control

#!/usr/bin/env bash
# Confere a zona do domínio próprio antes de mesclar o docs/CNAME.
#
# Uso: scripts/checar-dominio.sh [dominio]     (padrão: nuvem-sync.app.br)
#
# Não precisa de `dig`. A conferência pergunta ao resolvedor público quem são os
# servidores da zona e depois fala DIRETO com eles: resolvedor guarda cache e já
# mostrou registro que a zona não tinha mais — e o contrário também acontece
# (registro recém-criado que o cache ainda não viu). O que vale é o que os
# servidores autoritativos respondem; a visão do 1.1.1.1 aparece como
# "propagação", só informativa.
#
# Sai com código 1 enquanto faltar registro obrigatório.
set -euo pipefail

dominio="${1:-nuvem-sync.app.br}"
usuario_github="fabio-agreles"

python3 - "$dominio" "$usuario_github" <<'PY'
import random
import socket
import struct
import sys

dominio, usuario = sys.argv[1], sys.argv[2]
TIPOS = {"A": 1, "NS": 2, "CNAME": 5, "TXT": 16, "AAAA": 28}
ESPERADOS_A = {"185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"}
ESPERADOS_AAAA = {"2606:50c0:8000::153", "2606:50c0:8001::153",
                  "2606:50c0:8002::153", "2606:50c0:8003::153"}
ALVO_WWW = "fabio-agreles.github.io"


def ler_nome(data, off):
    partes, saltou, fim = [], False, off
    while True:
        tam = data[off]
        if tam == 0:
            off += 1
            if not saltou:
                fim = off
            return ".".join(partes), fim
        if tam & 0xC0 == 0xC0:
            ponteiro = struct.unpack(">H", data[off:off + 2])[0] & 0x3FFF
            if not saltou:
                fim, saltou = off + 2, True
            off = ponteiro
            continue
        partes.append(data[off + 1:off + 1 + tam].decode(errors="replace"))
        off += 1 + tam
        if not saltou:
            fim = off


def consulta(nome, tipo, servidor="1.1.1.1", recursivo=True):
    """Devolve (rcode, [respostas], [NS da seção de autoridade]).

    A terceira lista é o que interessa para descobrir a delegação: o TLD
    responde um "referral" — o nome do domínio não vem na resposta, os NS
    vêm na seção de autoridade.
    """
    tid = random.randint(0, 65535)
    flags = 0x0100 if recursivo else 0
    pergunta = b"".join(bytes([len(p)]) + p.encode() for p in nome.split(".")) + b"\x00"
    pacote = struct.pack(">HHHHHH", tid, flags, 1, 0, 0, 0) + pergunta
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(6)
    try:
        sock.sendto(pacote + struct.pack(">HH", TIPOS[tipo], 1), (servidor, 53))
        data, _ = sock.recvfrom(4096)
    except OSError as erro:
        return None, [f"sem resposta ({erro})"], []
    rcode = data[3] & 0x0F
    qd, an, nscount = struct.unpack(">HHH", data[4:10])
    off = 12
    for _ in range(qd):
        _, off = ler_nome(data, off)
        off += 4

    def registros(quantidade):
        nonlocal off
        valores = []
        for _ in range(quantidade):
            _, off = ler_nome(data, off)
            t, _classe, _ttl, tamanho = struct.unpack(">HHIH", data[off:off + 10])
            off += 10
            dado = data[off:off + tamanho]
            off += tamanho
            if t == 1:
                valores.append(socket.inet_ntoa(dado))
            elif t == 28:
                valores.append(socket.inet_ntop(socket.AF_INET6, dado))
            elif t == 2 or t == 5:
                valores.append(ler_nome(data, off - tamanho)[0])
            elif t == 16:
                partes, i = [], 0
                while i < len(dado):
                    n = dado[i]
                    partes.append(dado[i + 1:i + 1 + n].decode(errors="replace"))
                    i += 1 + n
                valores.append("".join(partes))
        return valores

    respostas = registros(an)
    autoridade = registros(nscount)
    return rcode, respostas, autoridade


def delegacao(dominio):
    """Quem responde pela zona, segundo o domínio PAI.

    Não serve o RRset de NS do próprio domínio: o Registro.br publica nele o par
    `a.auto.dns.br`/`b.auto.dns.br`, que é o servidor de transferência de zona do
    painel, não o que atende as consultas do mundo.
    """
    pai = dominio.split(".", 1)[1]
    _rcode, ns_pai, _ = consulta(pai, "NS")
    for nome_ns in ns_pai:
        if nome_ns.startswith("sem resposta"):
            continue
        try:
            ip = socket.gethostbyname(nome_ns)
        except OSError:
            continue
        _rcode, _resp, autoridade = consulta(dominio, "NS", ip, recursivo=False)
        if autoridade:
            return autoridade
    # Plano B: o que o próprio domínio publica.
    _rcode, ns_proprio, _ = consulta(dominio, "NS")
    return ns_proprio


def linha(ok, titulo, detalhe="", opcional=False):
    marca = "✅" if ok else ("⬜" if not opcional else "·")
    if opcional and not ok:
        marca = "⬜"
    print(f"{marca} {titulo}")
    if detalhe:
        for pedaco in detalhe.split("\n"):
            print(f"      {pedaco}")
    return ok or opcional


tudo = True

# 1. Delegação: quem responde pela zona de verdade (o NS do domínio PAI, não o
#    RRset do próprio domínio — o Registro.br publica um par "auto" que só serve
#    à transferência de zona do painel).
nameservers = delegacao(dominio)
if nameservers and not nameservers[0].startswith("sem resposta"):
    autoritativos = []
    for nome_ns in nameservers:
        try:
            autoritativos.append((nome_ns, socket.gethostbyname(nome_ns)))
        except OSError:
            print(f"      aviso: {nome_ns} não resolveu")
    print("✅ Delegação do domínio")
    print("      " + " | ".join(f"{nome} ({ip})" for nome, ip in autoritativos))
else:
    autoritativos = [("1.1.1.1", "1.1.1.1")]
    print("⬜ Delegação do domínio (não consegui listar os NS)")
    tudo = False

if not autoritativos:
    print("Nada a conferir: nenhum servidor autoritativo respondeu.")
    sys.exit(1)

# 2. Registros, direto no autoritativo (é o que GitHub e Google enxergam).
ns_nome, ns_ip = autoritativos[0]


def autoritativo(nome, tipo):
    return consulta(nome, tipo, ns_ip, recursivo=False)[1]


a = autoritativo(dominio, "A")
tudo &= linha(ESPERADOS_A.issubset(set(a)), f"A no apex ({len(set(a) & ESPERADOS_A)}/4)",
              "encontrados: " + (" ".join(a) if a else "nenhum"))

aaaa = autoritativo(dominio, "AAAA")
tudo &= linha(ESPERADOS_AAAA.issubset(set(aaaa)), f"AAAA no apex ({len(set(aaaa) & ESPERADOS_AAAA)}/4, opcional)",
              "encontrados: " + (" ".join(aaaa) if aaaa else "nenhum"), opcional=True)

www = autoritativo(f"www.{dominio}", "CNAME")
alvo = (www[0] if www else "").rstrip(".")
tudo &= linha(alvo == ALVO_WWW, "www → GitHub Pages",
              f"CNAME: {alvo or 'nenhum'}" + ("" if alvo == ALVO_WWW else f" (esperado {ALVO_WWW})"))

txts = autoritativo(dominio, "TXT")
tem_google = any(t.startswith("google-site-verification=") for t in txts)
linha_google = " " + (" | ".join(txts) if txts else "nenhum TXT no apex")
tudo &= linha(tem_google, "TXT do Search Console no apex (propriedade de Domínio)", linha_google)

desafio = autoritativo(f"_github-pages-challenge-{usuario}.{dominio}", "TXT")
tudo &= linha(bool(desafio), "TXT de verificação do GitHub (anti-takeover)",
              " " + (" | ".join(desafio) if desafio else "nenhum"))

# 3. Propagação: o que um resolvedor público já devolve (informativo).
_rcode, vista, _ = consulta(dominio, "A")
print(f"\nPropagação no 1.1.1.1: {len(set(vista) & ESPERADOS_A)}/4 A" +
      (" · já propagado" if ESPERADOS_A.issubset(set(vista)) else " · ainda em cache antigo"))
if a and not ESPERADOS_A.issubset(set(vista)):
    print("      (a zona está certa; é só esperar o cache — GitHub e Google consultam o autoritativo)")

if tudo:
    print("\nZona completa — pode seguir para o GitHub Pages e o Search Console.")
    sys.exit(0)

print("\nAinda falta registro — complete no painel DNS do Registro.br e rode de novo.")
sys.exit(1)
PY

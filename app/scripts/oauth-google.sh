#!/usr/bin/env bash
# Projeto OAuth do Google para o Nuvem.
#
# O Google cobra a cota de requisições por minuto no *projeto OAuth* usado na
# autorização. O projeto compartilhado do rclone vive estourado; com um projeto
# só do Nuvem a fila é do aplicativo. O usuário ainda pode colar o projeto dele
# em Ajustes → Avançado, e aí o dele ganha.
#
# Uso:
#   scripts/oauth-google.sh                    # passo a passo do console
#   scripts/oauth-google.sh --conferir         # valida o par do ambiente
#   scripts/oauth-google.sh --salvar           # grava .env.oauth (0600)
#   scripts/oauth-google.sh --build [args…]    # valida e roda `tauri build`
#
# O par vem de NUVEM_GOOGLE_CLIENT_ID e NUVEM_GOOGLE_CLIENT_SECRET, ou do
# arquivo app/.env.oauth (não versionado).
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
arquivo="$raiz/.env.oauth"
sufixo=".apps.googleusercontent.com"

passos() {
  cat <<'TXT'
Projeto OAuth do Nuvem — o que fazer no console
===============================================

Só a pessoa com acesso à conta Google pode fazer estes cliques. Leva ~10 min.

1. Projeto
   https://console.cloud.google.com/projectcreate
   Nome: "Nuvem" · Organização: nenhuma (pessoal).

2. Drive API
   https://console.cloud.google.com/apis/library/drive.googleapis.com
   → "Ativar". (Só a Drive API: Gmail/Docs ficam desligadas.)

3. Tela de consentimento (Google Auth Platform → Branding)
   https://console.cloud.google.com/auth/branding
   - Nome do app: Nuvem
   - E-mail de suporte e e-mail do desenvolvedor: o seu
   - Público: **Externo** (usuários com qualquer conta Google)
   - Logotipo: app/src-tauri/icons/128x128.png (opcional por enquanto)
   - Domínio autorizado: deixe vazio (app instalado não tem site)
   - Link da política de privacidade:
     https://github.com/fabio-agreles/nuvem/blob/main/PRIVACIDADE.md
     (o arquivo já existe; o link só responde quando o repositório for público)

4. Escopos (Google Auth Platform → Data Access)
   https://console.cloud.google.com/auth/scopes
   Adicione: https://www.googleapis.com/auth/drive
   É escopo **restrito** do Drive: dá acesso às pastas que o usuário escolher,
   e é o que o bisync precisa para ler e escrever arquivos existentes.
   Alternativa `drive.file` só enxerga arquivos criados pelo próprio app — não
   serve para sincronizar uma pasta que já existe.

5. Cliente OAuth (Google Auth Platform → Clients)
   https://console.cloud.google.com/auth/clients
   → "Criar cliente" → Tipo: **App para computador** (Desktop app)
   Nome: "Nuvem desktop"
   Copie o client_id (termina em .apps.googleusercontent.com) e o client_secret.
   *Não* precisa de URI de redirecionamento: app instalado usa o laço local
   http://127.0.0.1:53682/ que o rclone abre sozinho.

6. Publicar (Google Auth Platform → Audience)
   https://console.cloud.google.com/auth/audience
   → "Publicar app" (sai de Testing para In production).
   **Isto é obrigatório**: em Testing a autorização — inclusive o refresh
   token — expira em 7 dias e a sincronização para de funcionar toda semana.

7. Embutir no build
   export NUVEM_GOOGLE_CLIENT_ID='....apps.googleusercontent.com'
   export NUVEM_GOOGLE_CLIENT_SECRET='GOCSPX-...'
   scripts/oauth-google.sh --conferir
   scripts/oauth-google.sh --build          # ou use os segredos no CI

   Sem recompilar, dá para testar com variável de ambiente em tempo de execução:
   NUVEM_GOOGLE_CLIENT_ID=... NUVEM_GOOGLE_CLIENT_SECRET=... nuvem
   No Flatpak: flatpak override --user --env=NUVEM_GOOGLE_CLIENT_ID=...

Depois disso, Ajustes → Avançado mostra "projeto do Nuvem" e o client_id em uso.

Verificação do Google (para distribuir de verdade)
--------------------------------------------------
Enquanto o app não passa pela verificação, quem autoriza vê a tela
"O Google não verificou este aplicativo" e o projeto tem um teto **de 100
usuários novos, para sempre** (não dá para zerar). Para o público em geral é
preciso enviar o app para verificação: marca, escopos, vídeo de demonstração e,
se houver servidor, avaliação de segurança CASA anual. O Nuvem não tem servidor
(tokens ficam na máquina do usuário), então a avaliação CASA não se aplica —
mas a verificação de escopo restrito, sim. Detalhes em docs/oauth-google.md.
TXT
}

ler_arquivo() {
  if [[ -f "$arquivo" ]]; then
    # shellcheck disable=SC1090
    set -a; source "$arquivo"; set +a
  fi
}

conferir() {
  local id="${NUVEM_GOOGLE_CLIENT_ID:-}" segredo="${NUVEM_GOOGLE_CLIENT_SECRET:-}"
  if [[ -z "$id" && -z "$segredo" ]]; then
    echo "oauth-google: nenhum par definido (NUVEM_GOOGLE_CLIENT_ID/_SECRET)." >&2
    echo "  O build sai com o projeto compartilhado do rclone." >&2
    return 1
  fi
  if [[ "$id" != *"$sufixo" ]]; then
    echo "oauth-google: o client_id precisa terminar em $sufixo" >&2
    return 1
  fi
  if [[ -z "$segredo" || "$segredo" == *" "* ]]; then
    echo "oauth-google: client_secret vazio ou com espaço" >&2
    return 1
  fi
  printf 'oauth-google: par válido — client_id %s…%s (segredo com %d caracteres)\n' \
    "${id:0:12}" "${id: -24}" "${#segredo}"
}

salvar() {
  ler_arquivo
  conferir
  umask 077
  {
    printf '# Projeto OAuth do Google usado no build do Nuvem.\n'
    printf '# Não versionado: entra no .gitignore.\n'
    printf 'export NUVEM_GOOGLE_CLIENT_ID=%q\n' "${NUVEM_GOOGLE_CLIENT_ID}"
    printf 'export NUVEM_GOOGLE_CLIENT_SECRET=%q\n' "${NUVEM_GOOGLE_CLIENT_SECRET}"
  } > "$arquivo"
  chmod 600 "$arquivo"
  echo "oauth-google: gravado em $arquivo (0600)"
}

build() {
  ler_arquivo
  if ! conferir; then
    echo "oauth-google: o build continuaria com o projeto do rclone; abortando." >&2
    echo "  Rode sem --build se é isso mesmo que você quer." >&2
    return 1
  fi
  cd "$raiz"
  echo "oauth-google: compilando com o projeto do Nuvem embutido…"
  NUVEM_GOOGLE_CLIENT_ID="$NUVEM_GOOGLE_CLIENT_ID" \
  NUVEM_GOOGLE_CLIENT_SECRET="$NUVEM_GOOGLE_CLIENT_SECRET" \
    npx tauri build "$@"
}

case "${1:-}" in
  --conferir) shift; ler_arquivo; conferir "$@" ;;
  --salvar) shift; salvar "$@" ;;
  --build) shift; build "$@" ;;
  --passos|--help|-h|"") passos ;;
  *) echo "oauth-google: opção desconhecida: $1" >&2; passos; exit 2 ;;
esac

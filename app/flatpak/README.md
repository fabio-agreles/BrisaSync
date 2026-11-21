# Flatpak

Manifesto: `app.brisasync.BrisaSync.json` — id `app.brisasync.BrisaSync`, runtime **GNOME 50**
(base `freedesktop-sdk 25.08`), extensões de SDK `rust-stable`, `node22` e `golang`.

Construído e instalado localmente (Flatpak 1.18.2, x86_64), com build 100% offline.
Tamanho instalado: **91,5 MB** (90,7 MB de conteúdo no commit).

## Construir e instalar

`flatpak-builder` não acompanha o Flatpak no Ubuntu/Debian; o caminho oficial é o
app `org.flatpak.Builder`.

```bash
# 1) builder + runtime/SDK/extensões (uma vez)
flatpak install --user -y flathub org.flatpak.Builder \
  org.gnome.Platform//50 org.gnome.Sdk//50 \
  org.freedesktop.Sdk.Extension.rust-stable//25.08 \
  org.freedesktop.Sdk.Extension.node22//25.08 \
  org.freedesktop.Sdk.Extension.golang//25.08

# 2) construir a partir da raiz do repositório (BrisaSync/)
flatpak run --user org.flatpak.Builder \
  --force-clean --user --install-deps-from=flathub \
  --repo=flatpak-repo builddir app/flatpak/app.brisasync.BrisaSync.json

# 3) instalar o resultado no repositório local
flatpak remote-add --user --if-not-exists --no-gpg-verify \
  brisasync-origin "$PWD/flatpak-repo"
flatpak install --user --reinstall -y \
  brisasync-origin app.brisasync.BrisaSync

# 4) rodar
flatpak run app.brisasync.BrisaSync
```

Instalar por caminho (`flatpak install --user ./flatpak-repo app.brisasync.BrisaSync`)
também funciona, mas o remoto `brisasync-origin` deixa `flatpak update` enxergar os
commits novos.

Antes de enviar mudanças, o lint local (o mesmo que o CI roda em
`.github/workflows/flatpak-lint.yml`):

```bash
cd app && scripts/check-flatpak.sh
```

Ele confere JSON do manifesto, `desktop-file-validate`, `appstreamcli validate`,
se toda captura citada existe em `docs/previews/` e se a `<release>` mais nova tem
a versão do `package.json`.

Rode o comando de build **da raiz do repositório**, não de `app/`: `--repo` e `--builddir`
são relativos ao diretório atual, e apontá-los para fora de `app/` faz o
flatpak-builder criar `flatpak-repo/` e `builddir/` no lugar errado (o app
instalado continua no commit antigo). Os dois já estão no `.gitignore` da raiz.

A fonte `type: dir` do módulo `brisasync` aponta para `..` (o diretório `app/`) e
ignora `node_modules`, `dist`, `src-tauri/target`, `src-tauri/gen`,
`src-tauri/resources`, `flatpak/repo`, `builddir` e `.flatpak-builder`.

## O que o manifesto faz

1. **`libayatana-appindicator`** (módulo compartilhado de
   `flathub/shared-modules`, copiado para `shared-modules/`) → compila
   `intltool`, `libdbusmenu`, `ayatana-ido`, `libayatana-indicator` e
   `libayatana-appindicator`. Sem isso a bandeja não funciona no sandbox: o
   `tray-icon` do Tauri carrega `libayatana-appindicator3.so.1` via `dlopen` em
   tempo de execução (o build passa, o ícone não aparece).
2. **rclone v1.75.2** a partir do tarball oficial (sha256 fixo), com as dependências
   Go vendorizadas (`rclone-sources.json` + `modules.txt`), `CGO_ENABLED=0`,
   `GOFLAGS=-mod=vendor`, instalado em `/app/bin/rclone`. O app o encontra por
   `BRISASYNC_RCLONE=/app/bin/rclone` (finish-arg).
3. **BrisaSync**: `npm ci --offline` + `npm run build` (Vite) e
   `cargo --offline build --release --features custom-protocol`, com Node 22 e Rust
   stable das extensões de SDK e as dependências vendorizadas
   (`cargo-sources.json`, `node-sources.json`); instala binário, `.desktop`,
   metainfo, ícones e a licença em `/app`.
   **A feature `custom-protocol` é obrigatória**: sem ela o binário abre a `devUrl`
   (`localhost:1420`) e a janela mostra “Could not connect to localhost”. Bandeja e
   rclone continuam funcionando, o que esconde o problema.
4. **Permissões** (`finish-args`): rede, ipc, Wayland/X11, dri, `--filesystem=home`,
   notificações, `StatusNotifierWatcher` e `org.freedesktop.portal.Background`
   (para inicialização em segundo plano via portal).

## Build offline (vendorização)

O Flathub constrói **sem rede**: nenhuma etapa pode baixar crates, pacotes npm ou
módulos Go. As dependências viajam como fontes no manifesto, em quatro arquivos
gerados (versionados neste diretório, ~470 KB no total):

| Arquivo | Origem | Conteúdo |
| --- | --- | --- |
| `cargo-sources.json` (262 KB, 963 fontes) | `flatpak-cargo-generator.py src-tauri/Cargo.lock` | cada crate em `vendor/cargo/vendor/<crate>` com seu `.cargo-checksum.json` + config apontando `[source.vendored-sources]` |
| `node-sources.json` (75 KB, 128 fontes) | `flatpak-node-generator npm app/package-lock.json` | tarballs npm dentro de `flatpak-node/npm-cache/_cacache` (cache do npm) + cabeçalhos do Node do SDK |
| `rclone-sources.json` (75 KB, 274 fontes) | `flatpak-go-mod -json` (dentro do SDK golang) | `go.mod`-equivalente: `vendor/modules.txt` + 273 zips de `proxy.golang.org` extraídos no `vendor/` |
| `modules.txt` (65 KB, 1743 linhas) | `CGO_ENABLED=0 go mod vendor` no rclone 1.75.2 | o `vendor/modules.txt` completo |

No manifesto eles entram como **strings** na lista `sources` — o flatpak-builder
expande o JSON e mescla as fontes:

```json
"sources": [
  { "type": "archive", "url": "https://downloads.rclone.org/v1.75.2/rclone-v1.75.2.tar.gz", "sha256": "fa64…eb67" },
  "rclone-sources.json"
]
```

`{"type": "file", "path": "cargo-sources.json"}` **não** funciona: isso só copia o
JSON para dentro do build; as fontes de dentro dele nunca são aplicadas (e o
`cargo build` falha tentando acessar o crates.io).

As três variáveis que fecham a porta da rede:

```json
"rclone": { "GOFLAGS": "-mod=vendor", "CGO_ENABLED": "0" }
"brisasync":  { "CARGO_NET_OFFLINE": "true",
            "npm_config_cache": "/run/build/brisasync/flatpak-node/npm-cache",
            "npm_config_offline": "true" }
```

e nos comandos: `go build -mod=vendor`, `npm ci --offline`, `cargo --offline
build`. Sem `--share=network` nas `build-options`.

### Como regenerar

Depois de mexer em `Cargo.lock` ou `package-lock.json`, rode a partir de `app/`:

```bash
# ferramenta (uma vez; o clone não é versionado)
(cd app && git clone --depth 1 https://github.com/flatpak/flatpak-builder-tools)

# crates
python3 app/flatpak-builder-tools/cargo/flatpak-cargo-generator.py \
  app/src-tauri/Cargo.lock -o app/flatpak/cargo-sources.json

# npm
flatpak-node-generator npm ./package-lock.json -o flatpak/node-sources.json
```

Para o rclone só é preciso mexer quando a **versão** mudar:

```bash
# dentro do SDK golang
flatpak run --user --command=sh --devel org.gnome.Sdk//50
#  >>> instale flatpak-go-mod e rode sobre o rclone extraído
go install github.com/dennwc/flatpak-go-mod@main
cd rclone-v1.75.2 && CGO_ENABLED=0 go mod vendor
flatpak-go-mod -json -o rclone-sources.json .
cp vendor/modules.txt .
```

O `go mod vendor` **sem `CGO_ENABLED=0`** falha em módulos que dependem de cgo, e o
`modules.txt` gerado pelo `flatpak-go-mod` sai incompleto (800 linhas em vez de
1743): o `go build -mod=vendor` então para com
`github.com/pkg/errors@v0.9.1: is explicitly required in go.mod, but not marked as
explicit in vendor/modules.txt`. Use o `modules.txt` do próprio `go mod vendor`.

### Detalhes do rclone vendorizado

- `-ldflags '-s -w -X github.com/rclone/rclone/fs.Version=v1.75.2'` fixa a versão:
  sem isso o binário se apresenta como `v1.75.2-DEV` (é o que aparece no rodapé da
  barra lateral do app).
- `GOBIN`/`GOPATH` apontam para `/app/bin` e `/run/build/rclone/go`; o
  `modules.txt` também funciona como cache de build dentro do sandbox.
- O binário final fica em **84 MB** (`/app/bin/rclone`); é o preço de compilar o
  rclone com todos os backends. Compilar só `drive`/`onedrive` economizaria ~40 MB,
  mas exigiria manter uma lista de tags (`-tags "drive onedrive"`).

## Detalhes que custaram tempo (e ficam documentados)

- **Build vendorizado não cria cache de módulos Go**: a nota histórica de
  `GOFLAGS=-modcacherw` só vale para builds antigos com `--share=network`. Ainda
  assim, se um build interrompido deixar o cache em `0555`, resolva com
  `chmod -R u+w .flatpak-builder && rm -rf .flatpak-builder`.
- **Não use `NODE_ENV=production`** no módulo: o `npm ci` passa a omitir
  `devDependencies` e o `vite`/`tsc` somem (`tsc: command not found`).
- **Build interrompido deixa `rofiles-fuse` pendurado** → o próximo build falha com
  `opendir(rofiles-xxxx): Ponto final de transporte não está conectado`. Solução:
  `fusermount3 -u .flatpak-builder/rofiles/rofiles-xxxx`.
- **GNOME 48 está EOL** (março/2026). O manifesto usa GNOME 50 + extensões `25.08`.
- **`src-tauri/resources/rclone`** (usado pelo `.deb`/AppImage) é ignorado na fonte
  e o manifesto cria um arquivo vazio no lugar: o `tauri-build` valida a existência
  do recurso em tempo de compilação, mas aqui o rclone vem do código-fonte.

## Verificado neste ambiente

| Item | Resultado |
| --- | --- |
| Build + export para `flatpak-repo` (offline) | ✅ commit `ed74456`, 90,7 MB de conteúdo |
| Instalação local (`flatpak install --user`) | ✅ 91,5 MB |
| App abre (GTK + WebKitGTK 2.54 no runtime) | ✅ interface renderizada (após o ajuste de `custom-protocol`) |
| `rclone` embutido | ✅ `rclone v1.75.2` em `/app/bin/rclone` (84 MB, compilado do fonte) |
| `rclone rcd` dentro do sandbox | ✅ `core/version` respondido na porta loopback |
| Painel RC autenticado | ✅ `POST /core/version` sem credencial → `401`; com HTTP Basic → `200` |
| Build sem rede nas etapas | ✅ `-mod=vendor`, `cargo --offline`, `npm ci --offline`; nenhum `--share=network` |
| Bandeja (SNI) | ✅ registra `org/ayatana/NotificationItem/tray_icon_tray_app_main` |
| Ícone simbólico da bandeja | ✅ painel escuro mostra a nuvem em traço branco; PNG entregue em `~/.var/app/app.brisasync.BrisaSync/cache/brisasync/bandeja/` |
| Bibliotecas de bandeja em `/app/lib` | ✅ `libayatana-appindicator3`, `libdbusmenu`, `libayatana-indicator` |
| Sincronização real com conta Google/OneDrive | ✅ verificada com conta real |
| Início automático (`org.freedesktop.portal.Background`) | ✅ escreve `~/.config/autostart` do sistema |
| Credenciais OAuth próprias (`Ajustes → Avançado · Google Drive`) | ✅ cartão presente no binário instalado (`client_id`/`client_secret` compilados); validação coberta por teste |
| Projeto OAuth do próprio BrisaSync embutido no build | ✅ código; no Flatpak o par entra por `flatpak override --user --env=BRISASYNC_GOOGLE_CLIENT_ID=… --env=BRISASYNC_GOOGLE_CLIENT_SECRET=…` (o app lê em tempo de execução) ou `build-options.env` no manifesto |
| Trava do bisync removida após fechar o app no meio | ✅ observado no app instalado (“Trava antiga do bisync removida — 1 arquivo(s)”) |

### Início automático

O `tauri-plugin-autostart` grava em `~/.var/app/app.brisasync.BrisaSync/config/autostart`,
que a sessão gráfica não lê. Dentro do Flatpak o switch de **Ajustes** passa por
`org.freedesktop.portal.Background` (`RequestBackground`), e o portal escreve
`~/.config/autostart/app.brisasync.BrisaSync.desktop`:

```ini
[Desktop Entry]
Type=Application
Name=BrisaSync
X-XDP-Autostart=app.brisasync.BrisaSync
Exec=flatpak run --command=/app/bin/brisasync app.brisasync.BrisaSync --minimized
X-Flatpak=app.brisasync.BrisaSync
Icon=app.brisasync.BrisaSync
```

O `Icon=` é acrescentado pelo app — o portal não escreve essa linha, e sem ela o
item aparece sem ícone na lista de aplicativos de inicialização. Precisa do `--talk-name=org.freedesktop.portal.Desktop` (já no manifesto) e de um
backend de portal com `Background` — KDE e GNOME têm.

### Ícone da bandeja

O `tray-icon` grava o PNG em `$XDG_RUNTIME_DIR/tray-icon` por padrão. Dentro do
Flatpak esse diretório é um tmpfs privado do sandbox: o painel do lado de fora
recebe um `IconName` que não existe e cai no ícone do `.desktop` (o quadrado azul).
Por isso o app configura `TrayIconBuilder::temp_dir_path` para o cache
(`XDG_CACHE_HOME`, visível no sistema), e os dois PNGs simbólicos — preto e branco —
vão embutidos no binário (`include_bytes!`), trocados por `set_icon` quando o tema
muda.

### Credenciais OAuth próprias

O cartão **Ajustes → Avançado · Google Drive** grava `driveClientId` e
`driveClientSecret` no `settings.json` do sandbox
(`~/.var/app/app.brisasync.BrisaSync/config/app.brisasync.BrisaSync/settings.json`). Na conexão de
uma conta Drive esses valores viram `parameters` do `config/create`, então o token
nasce no projeto Google do usuário — fora do projeto compartilhado do rclone, que é
quem vive estourado em “Queries per minute”.

Como o token pertence ao projeto que o emitiu, contas criadas antes disso precisam
ser removidas e conectadas de novo; o cartão avisa e as contas aparecem com o selo
*cota própria* ou *projeto do rclone*. Nada precisa ser copiado para dentro do
sandbox: o `settings.json` e o `rclone.conf` ficam sob `~/.var/app`, que o app lê
normalmente.

## Situação para o Flathub

O texto de submissão (descrição, justificativa das permissões e a nota sobre o
projeto OAuth) está em [`docs/flathub-pr.md`](../../docs/flathub-pr.md).

| Requisito | Situação |
| --- | --- |
| Build sem rede | ✅ crates, npm e Go vendorizados (seção *Build offline*) |
| Metainfo completo (`developer`, `url`, screenshots, `releases`) | ✅ `appstreamcli validate` limpo (só o aviso pedante de maiúsculas no ID) |
| `.desktop` válido, uma categoria principal | ✅ `desktop-file-validate` sem avisos |
| Capturas de tela 4:3 em 2x | ✅ 2480×1800, geradas por `app/scripts/capture-previews.mjs` |
| Lint automático no CI | ✅ `app/scripts/check-flatpak.sh` em `.github/workflows/flatpak-lint.yml` |
| Ícones | ✅ 32, 64, 128 e 256 px em `hicolor`, com o nome igual ao app-id |
| Licença | ✅ MIT no `project_license`, `LICENSE` instalada em `/app/share/licenses` |
| `--filesystem=home` justificado | ⚠️ ver abaixo |
| `aarch64` | ⚠️ não testado (sem máquina ARM aqui) |
| Repositório público com as URLs do metainfo | ⚠️ `github.com/fabio-agreles/BrisaSync` existe, mas está **privado** por ora: as URLs e as capturas respondem 404 para quem não tem acesso |

### O que falta antes de abrir o PR no Flathub

1. **Repositório público**: enquanto `github.com/fabio-agreles/BrisaSync` estiver
   privado, `<url type="homepage">`, `bugtracker`, `vcs-browser` e as seis capturas
   dão 404 para a revisão. Basta `gh repo edit fabio-agreles/BrisaSync --visibility
   public` antes de abrir o PR (a AppStream local valida igual, então o lint não
   acusa nada).
2. **`aarch64`**: as fontes são independentes de arquitetura (zips do
   `proxy.golang.org`, crates e tarballs npm são universais), então o build deve
   passar; se falhar, o `flathub.json` com `"only-arches": ["x86_64"]` resolve
   temporariamente.
3. **PR** em `flathub/flathub` com o manifesto na raiz, o `shared-modules` como
   submódulo e o texto de justificativa abaixo.

### Justificativa de `--filesystem=home`

O BrisaSync é um cliente de sincronização no modelo do Insync e do Dropbox: o usuário
aponta **qualquer** pasta do disco para espelhar com a nuvem, e o espelhamento é
feito pelo `rclone` como processo filho, em segundo plano, sem interface. O portal
de documentos (`xdg-document-portal`) só dá acesso a arquivos escolhidos numa janela
aberta, e o acesso some quando o app é reiniciado — o `rclone` não tem como usá-lo
para um bisync contínuo. `xdg-documents`, `xdg-download` e `xdg-pictures` cobririam
só parte dos casos (o app também sincroniza, por exemplo, `~/Projetos` ou uma pasta
dentro de `~/.local/share`), e obrigariam o usuário a escolher entre o portal e uma
mensagem de erro.

Limitar a `xdg-documents`/`xdg-download` é possível se o Flathub preferir: o app
passaria a recusar pastas fora desses diretórios com uma explicação. O que não dá
para fazer hoje é acesso arbitrário sem `--filesystem=home`. Pastas em `/mnt` e
`/media` (unidades externas) continuam fora do sandbox mesmo com `home` — para
essas, o usuário precisa de `flatpak override --user --filesystem=/media
app.brisasync.BrisaSync`.

### Pendências conhecidas

1. **Somente `$HOME`**: pastas em `/mnt`, `/media` ou unidades externas não
   aparecem no sandbox (ver a justificativa acima).
2. **Credenciais próprias**: o caminho é validado por teste unitário e o cartão está
   no binário, mas o fluxo completo (autorizar no navegador com um `client_id`
   próprio e sincronizar) ainda não foi exercitado — depende de criar o projeto no
   Google Cloud. Enquanto o build do Flathub não tiver o par do projeto (que exigiria
   pô-lo no manifesto, e o Flathub prefere que segredos não fiquem lá), o caminho
   para o usuário do Flatpak é Ajustes → Avançado ou o `flatpak override --env`
   descrito acima.

## Por que Flatpak

- Sandbox com permissões explícitas (`--filesystem=home`, rede).
- Runtime isolado da distro: o WebKitGTK vem do GNOME 50, não do sistema.
- Uma build só para todas as distros; atualização via Flathub quando publicada.

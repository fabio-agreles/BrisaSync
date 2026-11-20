# resources

Aqui entram os binários do motor de sincronização, `rclone` (Linux) e
`rclone.exe` (Windows). Eles **não ficam no repositório** — cada um tem ~82 MB —
e são baixados na hora do build pela versão fixada:

```bash
app/scripts/fetch-rclone.sh            # Linux + Windows
app/scripts/fetch-rclone.sh 1.75.2 linux
```

O `tauri.conf.json` (Linux) e o `tauri.windows.conf.json` apontam para estes
arquivos:

- `resources/rclone` → `.deb` e AppImage embutem em `usr/lib/Nuvem/rclone`
- `resources/rclone.exe` → instalador/portátil do Windows copia ao lado do `Nuvem.exe`

Sem o arquivo da plataforma alvo, `tauri build` falha na etapa de empacotamento
(a compilação em si não precisa dele). O Flatpak não usa esta pasta: ele compila
o rclone dentro do sandbox e o deixa em `/app/bin/rclone`.

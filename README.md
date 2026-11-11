# BrisaSync

[![CI](https://github.com/fabio-agreles/BrisaSync/actions/workflows/ci.yml/badge.svg)](https://github.com/fabio-agreles/BrisaSync/actions/workflows/ci.yml)
[![Release Multiplataforma](https://github.com/fabio-agreles/BrisaSync/actions/workflows/release.yml/badge.svg)](https://github.com/fabio-agreles/BrisaSync/actions/workflows/release.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-lightgrey.svg)]()

**BrisaSync** is a modern, native, and efficient open-source desktop client designed for safe, continuous bidirectional synchronization between **Google Drive** and **local folders** for offline and desktop access.

Available in **English** and **Português (Brasil)**. Para a versão em português deste documento, consulte o [README.pt-BR.md](README.pt-BR.md).

> [!NOTE]
> **Independence Notice**: BrisaSync is an independent open-source community project and is **not** affiliated with, endorsed by, or an official product of Google LLC. "Google", "Google Drive", and related marks are registered trademarks of Google LLC.

---

## Highlights & Features

- **True Bidirectional Synchronization**: Powered by `rclone bisync` with rigorous checksum, file size, and timestamp comparison (`--compare size,modtime,checksum`).
- **Mass Deletion Protection**: Built-in percentage-based and absolute threshold safeguards preventing accidental loss propagation without ever resorting to dangerous `--force` overrides.
- **Strict Baseline Integrity**: No automated blind `--resync` masking sync failures; corrupted states require explicit resolution or recovery.
- **Session Vault Credential Isolation**: OAuth tokens and keys are never stored in SQLite, plain files, command line arguments, or logs. On Linux, credentials use Freedesktop Secret Service (GNOME Keyring) or KDE Wallet; on Windows, Windows Credential Manager (`Advapi32.dll`) is used natively.
- **Seamless System Integration**:
  - **Linux**: Desktop launcher, system tray integration, and optional `systemd --user` background sync service.
  - **Windows**: Modern single-instance IPC, `%APPDATA%` data persistence, Windows Registry autostart, and clean user-level installer.
- **Bilingual Interface**: 100% catalog parity between Português (Brasil) and English, switchable dynamically without restarting the background engine.
- **Voluntary Pix Support**: Transparent open-source development supported by voluntary contributions.

---

## Platform Support Matrix

| Platform / Format | Status | Package / Delivery | Notes |
| :--- | :---: | :--- | :--- |
| **Arch / Manjaro / BigLinux** | **Verified** | `brisasync-0.1.27-1-x86_64.pkg.tar.zst` | Native package with bundled `rclone` binary and `systemd --user` service. |
| **Debian / Ubuntu / Mint** | **Verified** | `brisasync_0.1.27-1_amd64.deb` | Standard `.deb` package targeting Ubuntu 24.04+ / Debian 13+ with native `python3-pyside6`. |
| **AppImage (Universal Linux)** | **Verified** | `BrisaSync-0.1.27-x86_64.AppImage` | Truly standalone, relocatable bundle with embedded Python runtime, PySide6/Qt6, and `rclone`. |
| **Windows 10/11 x64** | **Verified** | `BrisaSync-0.1.27-Setup-x64.exe` & `.zip` | Native NSIS installer and portable bundle with Windows Credential Manager. |
| **Flatpak** | **Pending** | `packaging/flatpak/org.brisasync.BrisaSync.yml` | Requires `--filesystem=home` and background portal; offline dependency bundle pending. |

---

## Installation & Usage

### 1. Arch Linux / Manjaro / BigLinux (`.pkg.tar.zst`)

Download the package from [Releases](https://github.com/fabio-agreles/BrisaSync/releases) and install via `pacman`:

```bash
sudo pacman -U brisasync-0.1.27-1-x86_64.pkg.tar.zst
```

To update from an existing installation:
```bash
systemctl --user stop brisasync.service || true
sudo pacman -U brisasync-0.1.27-2-x86_64.pkg.tar.zst
```

### 2. Debian / Ubuntu / Linux Mint (`.deb`)

> [!NOTE]
> The native `.deb` package targets systems with official `python3-pyside6` in APT repositories (Ubuntu 24.04+ Noble and Debian 13+ Trixie). For Debian 12 (Bookworm) and Ubuntu 22.04 LTS (Jammy), use the **Universal AppImage** below.

```bash
sudo apt-get update
sudo apt-get install ./brisasync_0.1.27-1_amd64.deb
```

### 3. AppImage (Universal Linux x86_64)

The AppImage is fully standalone and bundles its own Python runtime, PySide6, Qt6 platform plugins, and `rclone`:

```bash
chmod +x BrisaSync-0.1.27-x86_64.AppImage
./BrisaSync-0.1.27-x86_64.AppImage
```

### 4. Windows 10 & 11 (64-bit)

Download `BrisaSync-0.1.27-Setup-x64.exe` and run the installer. The installer runs at the user level into `%LOCALAPPDATA%\Programs\BrisaSync` without requiring administrator privileges.

> [!TIP]
> **Windows SmartScreen Note**: As an independent free software project without a commercial EV code signing certificate, Windows SmartScreen may display an "Unrecognized app" prompt on initial launch. Click **"More info"** and **"Run anyway"** to proceed. You can verify SHA-256 hashes against `SHA256SUMS.txt`.

---

## Google Drive OAuth & Privacy

- **Desktop Client Metadata**: BrisaSync includes default open desktop OAuth client identifiers for straightforward desktop sign-in.
- **Custom Client Keys**: You can also supply your own Google Cloud OAuth 2.0 client credentials via **Settings → Accounts**.
- **Verification Status**: Google's public verification process for this open-source client ID is underway. During testing, new users may see a standard Google confirmation screen noting the app is pending verification.
- **Privacy Policy**: Our full, publicly accessible privacy declaration is published at [https://brisasync.com.br/privacy/](https://brisasync.com.br/privacy/).

---

## Voluntary Contributions (Pix)

BrisaSync is 100% free and open-source software (FLOSS). If the application is helpful to your daily routine, consider making a voluntary contribution:

- **Beneficiary**: Fábio Agreles Bezerra
- **Pix Key**: `e4bf0532-8016-42bf-bf2a-fd81326b6621`
- **Contact Email**: `fabioagreles@gmail.com`
- **Official Website**: [https://brisasync.com.br/](https://brisasync.com.br/)

---

## License

BrisaSync is licensed under the [GNU General Public License v3.0 or later (GPL-3.0-or-later)](LICENSE).
Third-party component notices and licenses (including `rclone` and `PySide6`) are documented in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

# BrisaSync — Avisos de Licenças e Softwares de Terceiros (`THIRD_PARTY_NOTICES.md`)

O **BrisaSync** é um software livre distribuído sob os termos da licença **GNU General Public License v3.0 or later (GPL-3.0-or-later)**.
Este documento relaciona os componentes de terceiros utilizados, integrados ou empacotados, com seus respectivos autores e termos de licenciamento.

---

## 1. rclone (`v1.75.2`)

- **Função**: Motor de sincronização bidirecional em nuvem (`rclone bisync`).
- **Autores**: Nick Craig-Wood e colaboradores do projeto rclone (<https://rclone.org/>).
- **Licença**: **MIT License**
- **Texto da Licença**:
  ```text
  The MIT License (MIT)

  Copyright (C) 2012 by Nick Craig-Wood <nick@craig-wood.com>

  Permission is hereby granted, free of charge, to any person obtaining a copy
  of this software and associated documentation files (the "Software"), to deal
  in the Software without restriction, including without limitation the rights
  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
  copies of the Software, and to permit persons to whom the Software is
  furnished to do so, subject to the following conditions:

  The above copyright notice and this permission notice shall be included in
  all copies or substantial portions of the Software.

  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
  THE SOFTWARE.
  ```

---

## 2. Qt6 / PySide6 (`v6.11.2`)

- **Função**: Biblioteca de interface gráfica desktop (GUI, Wayland, StatusNotifierItem e Widgets).
- **Autores**: The Qt Company Ltd. e colaboradores (<https://www.qt.io/>).
- **Licença**: **GNU Lesser General Public License version 3 (LGPL-3.0-only)** e **GNU General Public License version 3 (GPL-3.0-only)**.
- **Conformidade**: O BrisaSync utiliza as bibliotecas e bindings PySide6 de forma dinâmica (`import PySide6`), permitindo substituição das bibliotecas compartilhadas da distribuição.

---

## 3. Python Runtime (`v3.14`)

- **Função**: Interpretador e biblioteca padrão da linguagem Python.
- **Autores**: Python Software Foundation (<https://www.python.org/>).
- **Licença**: **Python Software Foundation License Version 2 (PSF-2.0)**.

---

## 4. libsecret (`secret-tool`)

- **Função**: Utilitário e biblioteca client para armazenamento seguro no Freedesktop Secret Service.
- **Autores**: GNOME Project (<https://gitlab.gnome.org/GNOME/libsecret>).
- **Licença**: **GNU Lesser General Public License version 2.1 or later (LGPL-2.1-or-later)**.

---

## 5. libnotify (`notify-send`)

- **Função**: Utilitário para envio de notificações desktop de acordo com a especificação Freedesktop Desktop Notifications.
- **Autores**: GNOME Project / Freedesktop (<https://gitlab.gnome.org/GNOME/libnotify>).
- **Licença**: **GNU Lesser General Public License version 2.1 or later (LGPL-2.1-or-later)**.


#!/usr/bin/env python3
"""Utilitário de validação e higienização de credenciais de cliente OAuth Desktop para empacotamento.

Garante que o arquivo empacotado contenha EXCLUSIVAMENTE metadados públicos de cliente Desktop:
- Exige o tipo 'installed' (Desktop App). Rejeita 'web'.
- Valida client_id, client_secret, auth_uri e token_uri.
- Bloqueia estritamente quaisquer tokens (access_token, refresh_token), senhas, emails ou segredos privados.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

FORBIDDEN_KEY_PATTERNS = (
    "token",
    "access_token",
    "refresh_token",
    "password",
    "secret_key",
    "private_key",
    "email",
    "account",
)


def sanitize_oauth_desktop_client(input_path: Path | str) -> dict[str, dict[str, str | list[str]]]:
    src = Path(input_path).expanduser().resolve()
    if not src.is_file():
        raise FileNotFoundError(f"Arquivo de cliente OAuth de entrada não encontrado: {src}")

    try:
        raw_data = json.loads(src.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ValueError(f"Falha ao ler JSON em {src}: {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ValueError(f"Estrutura JSON inválida em {src}: esperado objeto raiz.")

    if "web" in raw_data and "installed" not in raw_data:
        raise ValueError(
            "O arquivo fornecido é do tipo 'Web application'. "
            "A distribuição exige uma credencial do tipo 'Desktop app' ('installed')."
        )

    installed_section = raw_data.get("installed")
    if installed_section is None and "client_id" in raw_data:
        installed_section = raw_data

    if not isinstance(installed_section, dict):
        raise ValueError("Chave 'installed' ausente ou inválida no cliente OAuth.")

    # Validação de campos obrigatórios
    client_id = str(installed_section.get("client_id", "")).strip()
    client_secret = str(installed_section.get("client_secret", "")).strip()

    if not client_id:
        raise ValueError("Campo 'client_id' ausente ou vazio no cliente OAuth.")
    if not client_secret:
        raise ValueError("Campo 'client_secret' ausente ou vazio no cliente OAuth.")

    project_id = str(installed_section.get("project_id", "brisasync")).strip()
    raw_auth_uri = str(installed_section.get("auth_uri", "")).strip()
    if not raw_auth_uri or raw_auth_uri == "https://accounts.google.com/o/oauth2/auth":
        auth_uri = "https://accounts.google.com/o/oauth2/v2/auth"
    else:
        auth_uri = raw_auth_uri

    token_uri = str(installed_section.get("token_uri", "https://oauth2.googleapis.com/token")).strip()
    cert_url = str(installed_section.get("auth_provider_x509_cert_url", "https://www.googleapis.com/oauth2/v1/certs")).strip()

    raw_redirects = installed_section.get("redirect_uris", ["http://localhost"])
    if isinstance(raw_redirects, list):
        redirect_uris = [str(u).strip() for u in raw_redirects if str(u).strip()]
    else:
        redirect_uris = ["http://localhost"]
    if not redirect_uris:
        redirect_uris = ["http://localhost"]

    # Verificação estrita de ausência de tokens ou dados confidenciais de sessão
    all_keys = list(raw_data.keys()) + list(installed_section.keys())
    for key in all_keys:
        k_lower = key.lower()
        if k_lower in ("client_secret", "client_id", "project_id", "auth_uri", "token_uri", "installed",
                       "redirect_uris", "auth_provider_x509_cert_url"):
            continue
        for forbidden in FORBIDDEN_KEY_PATTERNS:
            if forbidden in k_lower:
                raise ValueError(
                    f"Chave proibida detectada no arquivo de credencial: '{key}'. "
                    "Arquivos de distribuição pública jamais podem conter tokens pessoais ou segredos de sessão."
                )

    sanitized = {
        "installed": {
            "client_id": client_id,
            "project_id": project_id,
            "auth_uri": auth_uri,
            "token_uri": token_uri,
            "auth_provider_x509_cert_url": cert_url,
            "client_secret": client_secret,
            "redirect_uris": redirect_uris,
        }
    }
    return sanitized


def main() -> int:
    if len(sys.argv) < 2:
        print("Uso: python3 sanitize_oauth_client.py <input_client.json> [output_path1 [output_path2 ...]]", file=sys.stderr)
        return 1

    input_file = Path(sys.argv[1])
    try:
        sanitized = sanitize_oauth_desktop_client(input_file)
    except Exception as exc:
        print(f"ERRO DE HIGIENIZAÇÃO: {exc}", file=sys.stderr)
        return 2

    formatted = json.dumps(sanitized, indent=2, ensure_ascii=False) + "\n"

    output_paths = sys.argv[2:]
    if not output_paths:
        print(formatted)
        return 0

    for out_str in output_paths:
        out_path = Path(out_str)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted, encoding="utf-8")
        out_path.chmod(0o644)
        print(f"✓ Metadados OAuth higienizados salvos em: {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())


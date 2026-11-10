"""Motor de sincronização bidirecional real baseado em `rclone bisync`.

Princípios arquiteturais e semântica validada no `rclone v1.75.2`:
1. Usa exclusivamente `rclone bisync` (nunca dois comandos unilaterais `sync`/`copy`).
2. Nunca executa `--resync` automaticamente para mascarar falhas de sincronização.
3. Nunca utiliza `--force` para contornar bloqueios de segurança.
4. Proteção dupla contra exclusões em massa (Limite Percentual + Limite Absoluto):
   - No subcomando `rclone bisync` (validado em `v1.75.2`), `--max-delete` recebe apenas
     um inteiro de `0` a `100` representando a **porcentagem máxima (`%`)** de arquivos
     que podem ser excluídos em um único ciclo (padrão: `50`%).
   - Além do limite percentual (`max_delete_percent = 50`), o `RcloneBisyncEngine`
     impõe um **limite absoluto explícito (`max_delete_abs = 25` arquivos)** e verifica
     ambos os limites contra as listagens da baseline (`*.path1.lst` e `*.path2.lst`)
     **antes** de propagar exclusões.
5. Usa `--compare size,modtime,checksum` para detectar alterações mesmo quando arquivos
   possuem tamanho e timestamp (`mtime`) idênticos.
6. Usa `--conflict-resolve none` e `--conflict-loser num` para preservar ambas as versões
   em caso de conflito simultâneo.
7. Usa `--backup-dir1` e `--backup-dir2` no mesmo backend e fora da árvore sincronizada
   para exclusão recuperável, validando inclusive que `root_folder_id` nunca mude a raiz
   visível do remote para a própria pasta selecionada.
8. Usa `--check-access` com arquivo sentinela `.brisasync_check` para impedir propagação
   de exclusões quando uma pasta desaparece ou fica inacessível. O marcador é criado
   SOMENTE na inicialização explícita da base (`initialize_baseline`), nunca em ciclos normais.
9. Usa `--recover`, `--resilient` e `--max-lock 2m` para tolerância a falhas e proteção
   contra locks órfãos.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
from typing import Callable

def resolve_rclone_binary(explicit_path: str | Path | None = None) -> str | None:
    """Resolve o executável do motor rclone de forma consistente em todo o BrisaSync.

    Ordem de precedência:
    1. Caminho explícito fornecido programaticamente (valida existência e permissão de execução).
    2. Variável de ambiente `BRISASYNC_RCLONE_BINARY` (valida existência e permissão de execução).
    3. Locais empacotados oficiais (/usr/lib/brisasync/bin/rclone, sys.prefix, caminhos relativos ao pacote).
    4. Binário disponível no PATH do sistema (`shutil.which("rclone")`).

    Lança:
        FileNotFoundError: Se um override explícito ou variável de ambiente for configurado mas não existir.
        PermissionError: Se um override explícito for encontrado mas não possuir permissão de execução.
    """
    if explicit_path is not None:
        raw_str = str(explicit_path).strip()
        if not raw_str:
            raise FileNotFoundError("Caminho explícito para o rclone foi fornecido vazio.")
        candidate = Path(raw_str).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(
                f"Executável do rclone especificado no override explícito não foi encontrado: '{candidate}'"
            )
        if not candidate.is_file():
            raise FileNotFoundError(
                f"Caminho especificado para o rclone não é um arquivo regular: '{candidate}'"
            )
        if not os.access(candidate, os.X_OK):
            raise PermissionError(
                f"Executável do rclone especificado no override explícito não possui permissão de execução: '{candidate}'"
            )
        return str(candidate.resolve())

    env_bin = os.environ.get("BRISASYNC_RCLONE_BINARY", "").strip()
    if env_bin:
        candidate = Path(env_bin).expanduser()
        if not candidate.exists():
            raise FileNotFoundError(
                f"Executável do rclone especificado na variável BRISASYNC_RCLONE_BINARY não foi encontrado: '{candidate}'"
            )
        if not candidate.is_file():
            raise FileNotFoundError(
                f"Caminho especificado em BRISASYNC_RCLONE_BINARY não é um arquivo regular: '{candidate}'"
            )
        if not os.access(candidate, os.X_OK):
            raise PermissionError(
                f"Executável do rclone especificado em BRISASYNC_RCLONE_BINARY não possui permissão de execução: '{candidate}'"
            )
        return str(candidate.resolve())

    # Locais empacotados oficiais do BrisaSync (/usr/lib/brisasync/bin/rclone, prefixo ativo ou relativo ao pacote)
    pkg_path = Path(__file__).resolve()
    bin_name = "rclone.exe" if sys.platform == "win32" else "rclone"
    rel_packaged = (
        pkg_path.parents[4] / "brisasync" / "bin" / bin_name
        if len(pkg_path.parents) >= 5
        else None
    )

    packaged_candidates = (
        rel_packaged,
        Path(sys.executable).parent / bin_name,
        Path(sys.executable).parent / "bin" / bin_name,
        Path(sys.prefix) / "Scripts" / bin_name,
        Path(sys.prefix) / "lib" / "brisasync" / "bin" / bin_name,
        Path("/usr/lib/brisasync/bin/rclone"),
        Path("/usr/local/lib/brisasync/bin/rclone"),
        pkg_path.parent.parent / "resources" / "bin" / bin_name,
    )
    for pkg_bin in packaged_candidates:
        if pkg_bin is not None and pkg_bin.is_file() and os.access(pkg_bin, os.X_OK):
            return str(pkg_bin.resolve())

    found = shutil.which("rclone") or shutil.which("rclone.exe")
    if found:
        return str(Path(found).resolve())

    return None


from brisasync.credentials.store import redact_secrets

SENTINEL_FILENAME = ".brisasync_check"
SENTINEL_CONTENT = "brisasync-access-sentinel-v1\n"
DEFAULT_MAX_DELETE_PERCENT = 50
DEFAULT_MAX_DELETE_ABS = 25


def is_remote_spec(target: Path | str) -> bool:
    """Retorna True se `target` for uma especificação de remote do rclone (ex.: `brisasync_gdrive:Pasta`)."""
    if isinstance(target, Path):
        return False
    text = str(target).strip()
    if (
        text.startswith("/")
        or text.startswith("./")
        or text.startswith("../")
        or text.startswith("~")
    ):
        return False
    return ":" in text


def _split_remote_spec(spec: str) -> tuple[str, str]:
    prefix, _, subpath = spec.strip().partition(":")
    norm_sub = str(PurePosixPath(subpath.strip("/"))) if subpath.strip("/") else ""
    if norm_sub == ".":
        norm_sub = ""
    return f"{prefix}:", norm_sub


def _extract_remote_name(spec: str) -> str:
    prefix, _ = _split_remote_spec(spec)
    base_name = prefix.rstrip(":")
    # Caso haja parâmetros inline `remote,param=val:`, extrai o nome base e rejeita root_folder_id inline conflitante
    return base_name.split(",", 1)[0].strip()


@dataclass(frozen=True)
class RemoteDirectoryEntry:
    """Representa uma pasta remota no Google Drive identificada por seu ID imutável."""

    folder_id: str
    name: str
    path: str = ""

    def __init__(
        self,
        folder_id: str,
        name: str | None = None,
        path: str = "",
        *,
        folder_name: str | None = None,
    ) -> None:
        resolved_name = (name if name is not None else folder_name) or ""
        resolved_path = path or resolved_name
        object.__setattr__(self, "folder_id", str(folder_id))
        object.__setattr__(self, "name", str(resolved_name))
        object.__setattr__(self, "path", str(resolved_path))

    @property
    def folder_name(self) -> str:
        return self.name


@dataclass(frozen=True)
class BisyncConfig:
    """Configuração de um par de sincronização bidirecional para o rclone bisync."""

    path1: Path
    path2: Path | str
    workdir: Path
    backup_dir1: Path
    backup_dir2: Path | str
    check_filename: str = SENTINEL_FILENAME
    conflict_resolve: str = "none"
    conflict_loser: str = "num"
    conflict_suffix: str = "conflict"
    max_lock: str = "2m"
    max_delete_percent: int = DEFAULT_MAX_DELETE_PERCENT
    max_delete_abs: int = DEFAULT_MAX_DELETE_ABS
    remote_folder_id: str | None = None
    remote_root_folder_id: str | None = None


@dataclass(frozen=True)
class BisyncExecutionResult:
    """Resultado auditável da execução do comando `rclone bisync`."""

    success: bool
    exit_code: int
    command: list[str]
    stdout: str
    stderr: str
    was_resync: bool
    error_reason: str | None = None
    stopped_by_user: bool = False
    conflict_files: tuple[str, ...] = ()


def extract_recorded_conflict_files(
    stderr: str,
    path1: Path,
    conflict_suffix: str = "conflict",
) -> tuple[str, ...]:
    """Extrai os caminhos relativos dos arquivos de conflito efetivamente gerados pelo `rclone bisync`.

    Relaciona exclusivamente operações reais de resolução de conflito registradas pelo backend
    (`WARNING  New or changed in both paths` seguido de `Renaming Path1/Path2 copy` /
    `Queue copy to Path1` / `Moved (server-side) to:`). Um arquivo legítimo do usuário cujo nome
    apenas termine em `.conflict1`/`.conflict2` sem conflito registrado pelo `rclone bisync`
    jamais é classificado como conflito.
    """
    clean_stderr = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", stderr or "")
    if not clean_stderr or "New or changed in both paths" not in clean_stderr:
        return ()

    p1_resolved = path1.expanduser().resolve()
    p1_prefix = p1_resolved.as_posix().rstrip("/") + "/"
    conflicted_bases: list[str] = []
    recorded_rel_paths: list[str] = []
    seen: set[str] = set()
    suffix_marker = f".{conflict_suffix}"

    for raw_line in clean_stderr.splitlines():
        line = raw_line.strip()
        if "New or changed in both paths" in line and " - " in line:
            rel_base = line.rsplit(" - ", 1)[-1].strip().lstrip("/")
            if rel_base and rel_base not in conflicted_bases:
                conflicted_bases.append(rel_base)
            continue

        if not conflicted_bases:
            continue

        candidate_rel: str | None = None
        if (
            "Renaming Path1 copy" in line or "Queue copy to Path1" in line
        ) and " - " in line:
            raw_target = line.rsplit(" - ", 1)[-1].strip()
            if raw_target.startswith(p1_prefix):
                candidate_rel = raw_target[len(p1_prefix) :].lstrip("/")
            elif not raw_target.startswith("/") and ":" not in raw_target:
                candidate_rel = raw_target.lstrip("/")
        elif "Moved (server-side) to:" in line:
            moved_target = line.split("Moved (server-side) to:", 1)[-1].strip().lstrip("/")
            if moved_target and not moved_target.startswith("/") and ":" not in moved_target:
                candidate_rel = moved_target

        if candidate_rel and suffix_marker in candidate_rel:
            if any(
                candidate_rel.startswith(f"{base}{suffix_marker}")
                for base in conflicted_bases
            ):
                if candidate_rel not in seen:
                    seen.add(candidate_rel)
                    recorded_rel_paths.append(candidate_rel)

    # Caso o rclone tenha registrado a linha de conflito e o arquivo exista em path1
    for base in conflicted_bases:
        parent_dir = p1_resolved / PurePosixPath(base).parent
        base_name = PurePosixPath(base).name
        if parent_dir.is_dir():
            for child in sorted(parent_dir.iterdir()):
                if child.is_file() and child.name.startswith(f"{base_name}{suffix_marker}"):
                    rel_str = child.relative_to(p1_resolved).as_posix()
                    if rel_str not in seen:
                        seen.add(rel_str)
                        recorded_rel_paths.append(rel_str)

    return tuple(recorded_rel_paths)


class RcloneBisyncEngine:
    """Wrapper para o binário `rclone` focado em `bisync` seguro local e remoto."""

    def __init__(self, rclone_binary: str | Path | None = None) -> None:
        self.rclone_binary = resolve_rclone_binary(rclone_binary)

    @staticmethod
    def _resolve_rclone_binary(explicit_path: str | Path | None = None) -> str | None:
        return resolve_rclone_binary(explicit_path)

    def is_available(self) -> bool:
        return self.rclone_binary is not None

    def get_version(self) -> str | None:
        if not self.rclone_binary:
            return None
        try:
            proc = subprocess.run(
                [self.rclone_binary, "version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                first_line = proc.stdout.strip().splitlines()[0].strip()
                return first_line
        except (OSError, subprocess.SubprocessError):
            return None
        return None

    def ensure_sentinel_files(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
    ) -> None:
        """Cria os arquivos sentinela `.brisasync_check` em Path1 e Path2 com o mesmo mtime.

        ATENÇÃO: Este método só pode ser chamado durante `initialize_baseline`.
        Jamais deve ser chamado em ciclos normais de sincronização para não mascarar
        perda de acesso.
        """
        config.path1.mkdir(parents=True, exist_ok=True)
        sentinel1 = config.path1 / config.check_filename
        if not sentinel1.exists():
            sentinel1.write_text(SENTINEL_CONTENT, encoding="utf-8")

        if is_remote_spec(config.path2):
            if not self.rclone_binary:
                raise RuntimeError("Binário 'rclone' não encontrado no sistema.")
            remote_target = str(config.path2).rstrip("/") + "/" + config.check_filename
            proc = subprocess.run(
                [
                    self.rclone_binary,
                    "copyto",
                    str(sentinel1),
                    remote_target,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    "Falha ao gravar arquivo marcador de acesso na pasta remota: "
                    f"{redact_secrets(proc.stderr or '')}"
                )
        else:
            p2 = Path(config.path2)
            p2.mkdir(parents=True, exist_ok=True)
            sentinel2 = p2 / config.check_filename
            if not sentinel2.exists():
                sentinel2.write_text(SENTINEL_CONTENT, encoding="utf-8")
            stat1 = sentinel1.stat()
            os.utime(sentinel2, ns=(stat1.st_atime_ns, stat1.st_mtime_ns))

    def check_remote_sentinel_exists(
        self,
        remote_path: str,
        check_filename: str = SENTINEL_FILENAME,
        *,
        env: dict[str, str] | None = None,
    ) -> bool:
        """Verifica se o arquivo sentinela `.brisasync_check` existe na pasta remota."""
        if not self.rclone_binary:
            raise RuntimeError("Binário 'rclone' não encontrado no sistema.")
        target = f"{remote_path.rstrip('/')}/{check_filename}"
        proc = subprocess.run(
            [self.rclone_binary, "lsjson", target, "--files-only"],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        if proc.returncode != 0:
            return False
        try:
            items = json.loads(proc.stdout or "[]")
            return any(
                isinstance(item, dict) and item.get("Name") == check_filename
                for item in items
            )
        except json.JSONDecodeError:
            return False

    def list_remote_directories(
        self,
        remote_root: str,
        *,
        env: dict[str, str] | None = None,
    ) -> list[RemoteDirectoryEntry]:
        """Lista as pastas de primeiro nível no remote retornando Nome e ID real do Google Drive."""
        if not self.rclone_binary:
            raise RuntimeError("Binário 'rclone' não encontrado no sistema.")
        proc = subprocess.run(
            [
                self.rclone_binary,
                "lsjson",
                remote_root,
                "--dirs-only",
                "--max-depth",
                "1",
                "--no-modtime",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Falha ao listar pastas remotas: {redact_secrets((proc.stderr or '').strip())}"
            )
        try:
            raw_items = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise RuntimeError("Saída inválida do rclone lsjson.") from exc

        entries: list[RemoteDirectoryEntry] = []
        for item in raw_items:
            if not isinstance(item, dict) or not item.get("IsDir", False):
                continue
            name = str(item.get("Name", "")).strip()
            # Ignora pasta oculta interna de recuperação do BrisaSync
            if not name or name.startswith(".brisasync"):
                continue
            folder_id = str(item.get("ID", "")).strip() or name
            path = str(item.get("Path", name)).strip()
            entries.append(
                RemoteDirectoryEntry(folder_id=folder_id, name=name, path=path)
            )
        return sorted(entries, key=lambda e: e.name.lower())

    def resolve_remote_directory_by_id(
        self,
        remote_root: str,
        folder_id: str,
        *,
        env: dict[str, str] | None = None,
    ) -> RemoteDirectoryEntry:
        """Localiza a pasta remota pelo seu ID imutável, rejeitando ambiguidades de nome."""
        entries = self.list_remote_directories(remote_root, env=env)
        matches = [e for e in entries if e.folder_id == folder_id]
        if not matches:
            raise RuntimeError(
                f"Pasta remota com ID '{folder_id}' não foi encontrada ou está inacessível no Google Drive."
            )
        target = matches[0]
        same_name_count = sum(1 for e in entries if e.name == target.name)
        if same_name_count > 1:
            raise RuntimeError(
                f"Detectadas múltiplas pastas remotas com o mesmo nome {target.name!r} no mesmo nível. "
                "Renomeie a pasta duplicada no Google Drive antes de sincronizar."
            )
        return target

    def create_remote_directory(
        self,
        remote_root: str,
        folder_name: str,
        *,
        env: dict[str, str] | None = None,
    ) -> RemoteDirectoryEntry:
        """Cria uma pasta remota dedicada a testes e retorna seu Nome e ID confirmado."""
        if not self.rclone_binary:
            raise RuntimeError("Binário 'rclone' não encontrado no sistema.")
        clean_name = folder_name.strip().strip("/")
        if not clean_name or "/" in clean_name or clean_name.startswith("."):
            raise ValueError(
                "Informe um nome simples e válido para a pasta remota de testes (sem barras ou ponto inicial)."
            )
        target_spec = f"{remote_root.rstrip(':')}:{clean_name}"
        proc = subprocess.run(
            [self.rclone_binary, "mkdir", target_spec],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"Falha ao criar pasta remota {clean_name!r}: "
                f"{redact_secrets((proc.stderr or '').strip())}"
            )
        entries = self.list_remote_directories(remote_root, env=env)
        for entry in entries:
            if entry.name == clean_name:
                return entry
        raise RuntimeError(
            f"Pasta remota {clean_name!r} foi criada, mas não pôde ser confirmada na listagem por ID."
        )

    @staticmethod
    def validate_paths_non_overlapping(config: BisyncConfig) -> None:
        """Garante que backup_dir1/backup_dir2 e workdir pertencem ao backend correto e não se sobrepõem às pastas sincronizadas."""
        if not (0 <= config.max_delete_percent <= 100):
            raise ValueError(
                f"max_delete_percent deve ser uma porcentagem inteira entre 0 e 100 (recebido: {config.max_delete_percent})."
            )
        if config.max_delete_abs < 1:
            raise ValueError(
                f"max_delete_abs deve ser um limite absoluto inteiro >= 1 (recebido: {config.max_delete_abs})."
            )

        p1 = config.path1.resolve()
        b1 = config.backup_dir1.resolve()
        wd = config.workdir.resolve()

        for name, aux_path in (("backup_dir1", b1), ("workdir", wd)):
            if aux_path == p1 or p1 in aux_path.parents or aux_path in p1.parents:
                raise ValueError(
                    f"{name} ({aux_path}) não pode coincidir nem se sobrepor a Path1 ({p1})."
                )

        if is_remote_spec(config.path2) or is_remote_spec(config.backup_dir2):
            if not (is_remote_spec(config.path2) and is_remote_spec(config.backup_dir2)):
                raise ValueError(
                    "Quando Path2 é um remote do rclone, backup_dir2 também deve estar no mesmo remote."
                )
            rem2, sub2 = _split_remote_spec(str(config.path2))
            rem_b2, sub_b2 = _split_remote_spec(str(config.backup_dir2))
            if rem2 != rem_b2:
                raise ValueError(
                    f"backup_dir2 ({rem_b2}) deve pertencer exatamente ao mesmo remote/backend de Path2 ({rem2})."
                )
            if "root_folder_id=" in rem2 or "root_folder_id=" in rem_b2:
                raise ValueError(
                    "Proibido alterar root_folder_id inline no especificador do remote: "
                    "isso mudaria a raiz visível do remote e colocaria backup_dir2 dentro da árvore selecionada."
                )
            if (
                config.remote_root_folder_id
                and config.remote_folder_id
                and config.remote_root_folder_id.strip() == config.remote_folder_id.strip()
            ):
                raise ValueError(
                    f"Conflito de árvore remota: root_folder_id ({config.remote_root_folder_id!r}) "
                    f"coincide com a pasta selecionada ({config.remote_folder_id!r}), o que colocaria "
                    f"backup_dir2 ({config.backup_dir2}) dentro da árvore sincronizada."
                )
            if not sub2 or not sub_b2:
                raise ValueError(
                    "Path2 remoto e backup_dir2 remoto devem especificar subpastas dedicadas não vazias "
                    "(nunca a raiz do remote, garantindo que backup_dir2 fique fora da árvore remota selecionada)."
                )
            p_sub2 = PurePosixPath(sub2)
            p_sub_b2 = PurePosixPath(sub_b2)
            if (
                p_sub2 == p_sub_b2
                or p_sub2 in p_sub_b2.parents
                or p_sub_b2 in p_sub2.parents
            ):
                raise ValueError(
                    f"backup_dir2 ({config.backup_dir2}) não pode se sobrepor a Path2 ({config.path2})."
                )
        else:
            p2 = Path(config.path2).resolve()
            b2 = Path(config.backup_dir2).resolve()
            if p1 == p2:
                raise ValueError("Path1 e Path2 não podem ser o mesmo diretório.")
            for name, aux_path in (("backup_dir1", b1), ("backup_dir2", b2), ("workdir", wd)):
                if aux_path == p2 or p2 in aux_path.parents or aux_path in p2.parents:
                    raise ValueError(
                        f"{name} ({aux_path}) não pode coincidir nem se sobrepor a Path2 ({p2})."
                    )
                if name == "backup_dir2" and (
                    aux_path == p1 or p1 in aux_path.parents or aux_path in p1.parents
                ):
                    raise ValueError(
                        f"backup_dir2 ({aux_path}) não pode coincidir nem se sobrepor a Path1 ({p1})."
                    )

    def verify_remote_backup_outside_selected_tree(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
    ) -> None:
        """Confirma na configuração do rclone que `backup_dir2` está no backend correto e fora da árvore selecionada, mesmo se `root_folder_id` estiver definido."""
        self.validate_paths_non_overlapping(config)
        if not is_remote_spec(config.path2):
            return
        if not self.rclone_binary or not env or "RCLONE_CONFIG" not in env:
            return

        rem_name = _extract_remote_name(str(config.path2))
        backup_rem_name = _extract_remote_name(str(config.backup_dir2))
        if rem_name != backup_rem_name:
            raise ValueError(
                f"backup_dir2 ({backup_rem_name}) não pertence ao mesmo backend de Path2 ({rem_name})."
            )

        proc = subprocess.run(
            [self.rclone_binary, "config", "dump"],
            env=env,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return
        try:
            dumped = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return

        remote_section = dumped.get(rem_name)
        if not isinstance(remote_section, dict):
            raise ValueError(
                f"Backend remoto {rem_name!r} não encontrado na configuração ativa do rclone."
            )

        configured_root_id = str(remote_section.get("root_folder_id", "")).strip()
        if configured_root_id:
            if (
                config.remote_folder_id
                and configured_root_id == config.remote_folder_id.strip()
            ):
                raise ValueError(
                    f"root_folder_id ({configured_root_id!r}) na configuração do remote {rem_name!r} "
                    f"muda a raiz visível para a própria pasta selecionada ({config.remote_folder_id!r}), "
                    f"o que colocaria backup_dir2 ({config.backup_dir2}) dentro da árvore sincronizada."
                )

    @staticmethod
    def _load_baseline_listing_paths(lst_file: Path, check_filename: str) -> set[str]:
        """Extrai os caminhos relativos de arquivos rastreados em um arquivo `.lst` (`bisync listing v1`) do rclone bisync."""
        paths: set[str] = set()
        try:
            for raw_line in lst_file.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                # Formato bisync listing v1:
                # <flag> <size> <hash> <id> <modtime> "<json_quoted_path>"
                parts = line.split(None, 5)
                if len(parts) < 6:
                    continue
                flag = parts[0]
                if flag == "d":
                    continue
                quoted_path = parts[5].strip()
                try:
                    rel_path = str(json.loads(quoted_path)).strip()
                except json.JSONDecodeError:
                    rel_path = quoted_path.strip('"')
                if rel_path and rel_path != check_filename:
                    paths.add(rel_path)
        except OSError:
            return set()
        return paths

    def _list_current_files_on_target(
        self,
        target: Path | str,
        check_filename: str,
        *,
        env: dict[str, str] | None = None,
    ) -> set[str] | None:
        """Retorna o conjunto de arquivos relativos atualmente presentes em `target` (exceto sentinela)."""
        if is_remote_spec(target):
            if not self.rclone_binary:
                return None
            proc = subprocess.run(
                [
                    self.rclone_binary,
                    "lsjson",
                    str(target),
                    "--recursive",
                    "--files-only",
                    "--no-modtime",
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0:
                return None
            try:
                items = json.loads(proc.stdout or "[]")
            except json.JSONDecodeError:
                return None
            result: set[str] = set()
            for item in items:
                if isinstance(item, dict):
                    rel = str(item.get("Path", "")).strip()
                    if rel and rel != check_filename:
                        result.add(rel)
            return result

        root = Path(target)
        if not root.is_dir():
            return None
        local_files: set[str] = set()
        for p in root.rglob("*"):
            if p.is_file():
                rel = p.relative_to(root).as_posix()
                if rel != check_filename:
                    local_files.add(rel)
        return local_files

    def check_mass_deletion_limits(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
    ) -> str | None:
        """Verifica limites absoluto (`max_delete_abs`) e percentual (`max_delete_percent`) antes de propagar exclusões.

        Retorna uma mensagem de bloqueio caso qualquer limite seja excedido, ou `None` se seguro.
        """
        if not config.workdir.is_dir():
            return None

        path1_lsts = sorted(config.workdir.glob("*.path1.lst"))
        path2_lsts = sorted(config.workdir.glob("*.path2.lst"))
        if not path1_lsts or not path2_lsts:
            return None

        checks = (
            ("Path1", path1_lsts[0], config.path1),
            ("Path2", path2_lsts[0], config.path2),
        )
        for side_label, lst_file, target in checks:
            baseline_user_files = self._load_baseline_listing_paths(
                lst_file, config.check_filename
            )
            if not baseline_user_files:
                continue

            current_user_files = self._list_current_files_on_target(
                target, config.check_filename, env=env
            )
            if current_user_files is None:
                continue

            deleted_files = baseline_user_files - current_user_files
            deleted_count = len(deleted_files)
            if deleted_count == 0:
                continue

            # 1. Verificação do limite absoluto explícito (max_delete_abs)
            if deleted_count > config.max_delete_abs:
                return (
                    f"Safety abort: too many deletes on {side_label} — "
                    f"limite absoluto excedido ({deleted_count} arquivo(s) excluído(s) > "
                    f"max_delete_abs={config.max_delete_abs}). Nenhuma exclusão foi propagada."
                )

            # 2. Verificação do limite percentual (considerando total rastreado com sentinela, igual ao rclone bisync,
            #    e também sobre os arquivos de usuário)
            total_with_sentinel = len(baseline_user_files) + 1
            delete_pct = (deleted_count * 100.0) / total_with_sentinel
            if delete_pct > config.max_delete_percent:
                return (
                    f"Safety abort: too many deletes on {side_label} — "
                    f"limite percentual excedido ({deleted_count} de {total_with_sentinel} = "
                    f"{delete_pct:.1f}% > max_delete_percent={config.max_delete_percent}%). "
                    "Nenhuma exclusão foi propagada."
                )

        return None

    def build_command(
        self,
        config: BisyncConfig,
        *,
        resync: bool = False,
        extra_args: list[str] | None = None,
    ) -> list[str]:
        """Monta o comando `rclone bisync` com todas as flags de integridade validadas."""
        if not self.rclone_binary:
            raise RuntimeError("Binário 'rclone' não encontrado no sistema.")

        self.validate_paths_non_overlapping(config)

        if extra_args:
            for forbidden in ("--force",):
                if forbidden in extra_args:
                    raise ValueError(
                        f"O uso de {forbidden!r} é proibido pela política de integridade do BrisaSync."
                    )

        cmd: list[str] = [
            self.rclone_binary,
            "bisync",
            str(config.path1),
            str(config.path2),
            "--workdir",
            str(config.workdir),
            "--compare",
            "size,modtime,checksum",
            "--conflict-resolve",
            config.conflict_resolve,
            "--conflict-loser",
            config.conflict_loser,
            "--conflict-suffix",
            config.conflict_suffix,
            "--backup-dir1",
            str(config.backup_dir1),
            "--backup-dir2",
            str(config.backup_dir2),
            "--check-access",
            "--check-filename",
            config.check_filename,
            "--max-delete",
            str(config.max_delete_percent),
            "--recover",
            "--resilient",
            "--create-empty-src-dirs",
            "--verbose",
            "--color=never",
        ]

        if config.max_lock and config.max_lock != "0":
            cmd.extend(["--max-lock", config.max_lock])

        if resync:
            cmd.append("--resync")

        if extra_args:
            cmd.extend(extra_args)

        return cmd

    def initialize_baseline(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
        on_process_started: Callable[[subprocess.Popen[str]], None] | None = None,
        stop_requested_check: Callable[[], bool] | None = None,
    ) -> BisyncExecutionResult:
        """Estabelece a linha de base inicial (`--resync`) de forma explícita e controlada.

        Só deve ser chamado na configuração inicial do par de pastas ou por ação
        explícita do usuário, nunca automaticamente após um erro.
        Cria os marcadores `.brisasync_check` e preserva snapshots `.lst-old` no `workdir`.
        """
        self.verify_remote_backup_outside_selected_tree(config, env=env)
        self.ensure_sentinel_files(config, env=env)
        config.workdir.mkdir(parents=True, exist_ok=True)
        config.backup_dir1.mkdir(parents=True, exist_ok=True)
        if not is_remote_spec(config.backup_dir2):
            Path(config.backup_dir2).mkdir(parents=True, exist_ok=True)

        result = self._execute(
            config,
            resync=True,
            env=env,
            on_process_started=on_process_started,
            stop_requested_check=stop_requested_check,
        )
        if result.success:
            for lst_file in config.workdir.glob("*.lst"):
                backup_lst = lst_file.with_name(f"{lst_file.name}-old")
                if not backup_lst.exists():
                    shutil.copy2(lst_file, backup_lst)
        return result

    def run_bisync(
        self,
        config: BisyncConfig,
        *,
        env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
        on_process_started: Callable[[subprocess.Popen[str]], None] | None = None,
        stop_requested_check: Callable[[], bool] | None = None,
    ) -> BisyncExecutionResult:
        """Executa sincronização bidirecional incremental sem permitir `--resync` implícito."""
        self.verify_remote_backup_outside_selected_tree(config, env=env)
        config.workdir.mkdir(parents=True, exist_ok=True)
        config.backup_dir1.mkdir(parents=True, exist_ok=True)
        if not is_remote_spec(config.backup_dir2):
            Path(config.backup_dir2).mkdir(parents=True, exist_ok=True)

        cmd = self.build_command(config, resync=False, extra_args=extra_args)
        mass_delete_abort = self.check_mass_deletion_limits(config, env=env)
        if mass_delete_abort is not None:
            return BisyncExecutionResult(
                success=False,
                exit_code=2,
                command=cmd,
                stdout="",
                stderr=mass_delete_abort,
                was_resync=False,
                error_reason=mass_delete_abort,
            )

        return self._execute(
            config,
            resync=False,
            env=env,
            extra_args=extra_args,
            on_process_started=on_process_started,
            stop_requested_check=stop_requested_check,
        )

    def _execute(
        self,
        config: BisyncConfig,
        *,
        resync: bool,
        env: dict[str, str] | None = None,
        extra_args: list[str] | None = None,
        on_process_started: Callable[[subprocess.Popen[str]], None] | None = None,
        stop_requested_check: Callable[[], bool] | None = None,
    ) -> BisyncExecutionResult:
        cmd = self.build_command(config, resync=resync, extra_args=extra_args)
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if on_process_started is not None:
            on_process_started(proc)
        raw_stdout, raw_stderr = proc.communicate()
        safe_stdout = redact_secrets(raw_stdout or "")
        safe_stderr = redact_secrets(raw_stderr or "")
        was_stopped = bool(stop_requested_check and stop_requested_check())
        if was_stopped:
            return BisyncExecutionResult(
                success=False,
                exit_code=proc.returncode if proc.returncode != 0 else -15,
                command=cmd,
                stdout=safe_stdout,
                stderr=safe_stderr,
                was_resync=resync,
                error_reason=(
                    "Operação interrompida de forma controlada pelo usuário (SIGTERM graceful shutdown). "
                    "Estado recuperável preservado para o próximo ciclo."
                ),
                stopped_by_user=True,
            )
        success = proc.returncode == 0
        error_reason = (
            None if success else (safe_stderr.strip() or f"Exit code {proc.returncode}")
        )
        recorded_conflicts = extract_recorded_conflict_files(
            safe_stderr, config.path1, conflict_suffix=config.conflict_suffix
        )
        return BisyncExecutionResult(
            success=success,
            exit_code=proc.returncode,
            command=cmd,
            stdout=safe_stdout,
            stderr=safe_stderr,
            was_resync=resync,
            error_reason=error_reason,
            stopped_by_user=False,
            conflict_files=recorded_conflicts,
        )

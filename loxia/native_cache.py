# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cache content-addressed de binários nativos (ADR-0149, #244).

Duas superfícies usam este módulo:

- `loxia run` — compila o fonte e executa o binário; o cache é **só desempenho**
  (não muda bytes, não entra na saída, nunca esconde erro);
- `loxia test --native` — reusa a mesma infraestrutura de diretório/atomicidade.

A chave é composta por: fontes do closure (o que o loader realmente resolveu),
manifesto/lock, flags de dependência, flags de build (`debug`, `max_heap`),
identidade do compilador, plataforma e um *fingerprint* da toolchain Python/C.
O fingerprint é um digest de `mtime_ns`/tamanho — nunca lê o conteúdo dos ~700
arquivos da toolchain a cada execução (o custo cairia no caminho quente).
A identidade do `cc` fica memoizada em `toolchain.json`, validada pelo `mtime`
do binário do compilador: um hit não roda `cc --version`.

Invalidação é conservadora na direção segura: qualquer edição na toolchain muda
o `mtime`/tamanho e derruba o cache; o pior caso é recompilar, nunca um binário
velho. O limite de tamanho (`LOX_BUILD_CACHE_MAX`, default 1 GiB) e o
`loxia cache prune` cuidam do crescimento em `$TMPDIR`.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MAX_BYTES = 1024**3
MIN_SIZE_BYTES = 1024**2
MAX_SIZE_BYTES = 1024**4

_TOOLCHAIN_DIRS = ("loxia", "loxia_core", "runtime")
_TOOLCHAIN_SUFFIXES = (".py", ".c", ".h", ".lx")
_SIZE_PATTERN = re.compile(r"^(\d+)([kmg]?)$")

MEMO_NAME = "toolchain.json"


# -- tamanho ---------------------------------------------------------------


def parse_size(text: str) -> int:
    """Interpreta `750M`, `2G` ou bytes puros (K/M/G, base 1024)."""
    match = _SIZE_PATTERN.match(text.strip().lower())
    if match is None:
        raise ValueError(f"invalid size '{text}' (use bytes, K, M or G)")
    value = int(match.group(1), 10) * {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[match.group(2)]
    if not MIN_SIZE_BYTES <= value <= MAX_SIZE_BYTES:
        raise ValueError(
            f"size must be between {MIN_SIZE_BYTES // 1024}K and {MAX_SIZE_BYTES // 1024**3}G"
        )
    return value


def max_bytes_from_env() -> int | None:
    """Limite configurado em `LOX_BUILD_CACHE_MAX` (None = default)."""
    raw = os.environ.get("LOX_BUILD_CACHE_MAX")
    if not raw:
        return None
    try:
        return parse_size(raw)
    except ValueError:
        return None


# -- diretório -------------------------------------------------------------


def cache_root() -> Path | None:
    """Raiz do cache (`$LOX_BUILD_CACHE` ou `$TMPDIR/loxia-build-<uid>`)."""
    configured = os.environ.get("LOX_BUILD_CACHE")
    if configured:
        base = Path(configured)
    else:
        user = str(os.getuid()) if hasattr(os, "getuid") else "user"
        base = Path(tempfile.gettempdir()) / f"loxia-build-{user}"
    try:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    return base


def directory(kind: str) -> Path | None:
    """Subdiretório do cache (`run`, `tests`); `None` se não dá para criar."""
    root = cache_root()
    if root is None:
        return None
    target = root / kind
    try:
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        return None
    return target


# -- toolchain -------------------------------------------------------------


def _package_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _walk_toolchain() -> list[Path]:
    root = _package_root()
    files: list[Path] = []
    for name in _TOOLCHAIN_DIRS:
        base = root / name
        if not base.is_dir():
            continue
        for current, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                item for item in dirnames if item != "__pycache__" and not item.startswith(".")
            )
            for filename in sorted(filenames):
                if filename.endswith(_TOOLCHAIN_SUFFIXES):
                    files.append(Path(current) / filename)
    return files


def toolchain_fingerprint() -> str:
    """Digest `caminho + mtime_ns + tamanho` da toolchain (sem ler conteúdo)."""
    root = _package_root()
    digest = hashlib.sha256()
    for path in _walk_toolchain():
        try:
            stat = path.stat()
        except OSError:
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - defensivo
            relative = path.as_posix()
        digest.update(f"{relative}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode())
    return digest.hexdigest()[:32]


def _compiler() -> str:
    """Mesma escolha do driver: `$CC`, depois cc/clang/gcc (fallback: `cc`)."""
    configured = os.environ.get("CC")
    if configured:
        return configured
    for candidate in ("cc", "clang", "gcc"):
        found = shutil.which(candidate)
        if found is not None:
            return found
    return "cc"


def _compiler_version(compiler: str) -> str:
    try:
        process = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return compiler
    line = process.stdout.splitlines()[0] if process.stdout else ""
    return f"{compiler}\0{line}"


def _read_memo(root: Path) -> dict[str, object]:
    try:
        data = json.loads((root / MEMO_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_memo(root: Path, data: dict[str, object]) -> None:
    temporary = root / f".{MEMO_NAME}.{os.getpid()}.tmp"
    try:
        temporary.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        os.replace(temporary, root / MEMO_NAME)
    except OSError:
        temporary.unlink(missing_ok=True)


def toolchain_stamp() -> str:
    """Identidade completa da toolchain, com memo do `cc --version`.

    O fingerprint é sempre recalculado (stat é barato e é o que invalida); o
    memo evita o subprocesso do compilador no caminho quente.
    """
    from loxia import __version__

    fingerprint = toolchain_fingerprint()
    compiler = _compiler()
    try:
        compiler_stat = os.stat(compiler)
    except OSError:
        compiler_stamp = "missing"
    else:
        compiler_stamp = f"{compiler_stat.st_mtime_ns}:{compiler_stat.st_size}"

    root = cache_root()
    identity = ""
    if root is not None:
        memo = _read_memo(root)
        if (
            memo.get("version") == __version__
            and memo.get("fingerprint") == fingerprint
            and memo.get("compiler") == compiler
            and memo.get("compiler_stamp") == compiler_stamp
            and isinstance(memo.get("identity"), str)
        ):
            identity = str(memo["identity"])
    if not identity:
        identity = _compiler_version(compiler)
        if root is not None:
            _write_memo(
                root,
                {
                    "version": __version__,
                    "platform": sys.platform,
                    "machine": platform.machine(),
                    "fingerprint": fingerprint,
                    "compiler": compiler,
                    "compiler_stamp": compiler_stamp,
                    "identity": identity,
                },
            )

    # CPATH/LIBRARY_PATH mudam o que o `cc` enxerga (headers/bibliotecas, ex.:
    # libgc) e, portanto, o binário; o `test --native` já os incluía na chave.
    return "\0".join(
        (
            __version__,
            sys.platform,
            platform.machine(),
            fingerprint,
            identity,
            os.environ.get("CPATH", ""),
            os.environ.get("LIBRARY_PATH", ""),
        )
    )


# -- chave e entradas ------------------------------------------------------


@dataclass(frozen=True)
class BuildRequest:
    """Tudo que muda o binário, exceto o código do programa."""

    entry: Path
    flags: tuple[str, ...] = ()
    stamp: str = ""


def build_key(
    request: BuildRequest,
    texts: dict[str, str],
    *,
    watched: Iterable[Path] = (),
) -> str:
    """Hash do closure + manifesto/lock + flags + identidade da toolchain."""
    digest = hashlib.sha256()
    digest.update(request.stamp.encode("utf-8", "replace"))
    digest.update(b"\0entry\0")
    digest.update(str(request.entry.resolve()).encode("utf-8", "replace"))
    digest.update(b"\0flags\0")
    digest.update("\0".join(request.flags).encode("utf-8", "replace"))
    digest.update(b"\0sources\0")
    for path in sorted(texts):
        digest.update(path.encode("utf-8", "replace"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(texts[path].encode("utf-8", "replace")).digest())
    # Manifesto/lock ficam fora do `SourceMap`: o lock fixa as dependências.
    for extra in sorted({Path(item) for item in watched}):
        if extra.suffix not in (".toml", ".lock"):
            continue
        try:
            payload = extra.read_bytes()
        except OSError:
            continue
        digest.update(str(extra.resolve()).encode("utf-8", "replace"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()[:32]


def entry_name(entry: Path) -> str:
    prefix = hashlib.sha256(str(entry.resolve()).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{entry.stem}"


def locate(directory_path: Path | None, key: str, name: str) -> Path | None:
    if directory_path is None:
        return None
    target = directory_path / key / name
    try:
        if target.is_file() and target.stat().st_size > 0 and os.access(target, os.X_OK):
            return target
    except OSError:
        return None
    return None


def store(
    directory_path: Path | None,
    key: str,
    name: str,
    build: Callable[[Path], str | None],
    *,
    fallback: Path,
) -> tuple[str | None, str | None]:
    """Builda uma vez por conteúdo; devolve `(binário, erro)`.

    O build escreve num temporário no mesmo diretório e o `os.replace` publica o
    binário completo — dois `run` concorrentes não veem arquivo pela metade.
    Qualquer falha de cache cai no build fora do cache (o cache é desempenho).
    """
    if directory_path is None:
        error = build(fallback)
        return (str(fallback) if error is None else None), error
    existing = locate(directory_path, key, name)
    if existing is not None:
        return str(existing), None
    target = directory_path / key / name
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        error = build(temporary)
        if error is None:
            temporary.chmod(0o755)
            os.replace(temporary, target)
            return str(target), None
        return None, error
    except OSError:
        error = build(fallback)
        return (str(fallback) if error is None else None), error
    finally:
        temporary.unlink(missing_ok=True)


# -- tamanho / prune -------------------------------------------------------


@dataclass(frozen=True)
class PruneResult:
    removed: int
    freed: int
    remaining: int

    @property
    def megabytes(self) -> float:
        return self.freed / 1024**2


def _entries(base: Path) -> list[tuple[Path, int, int]]:
    found: list[tuple[Path, int, int]] = []
    for current, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(dirnames)
        for filename in filenames:
            if filename.startswith("."):
                continue
            path = Path(current) / filename
            try:
                stat = path.stat()
            except OSError:
                continue
            if stat.st_size > 0:
                found.append((path, stat.st_size, stat.st_mtime_ns))
    return found


def cache_size(base: Path | None = None) -> int:
    target = base if base is not None else cache_root()
    if target is None or not target.is_dir():
        return 0
    return sum(size for _, size, _ in _entries(target))


def prune(
    base: Path | None = None,
    *,
    max_bytes: int | None = None,
    dry_run: bool = False,
    protect: Iterable[Path] = (),
) -> PruneResult:
    """Remove os binários mais antigos até o cache caber em `max_bytes`."""
    target = base if base is not None else cache_root()
    limit = max_bytes if max_bytes is not None else (max_bytes_from_env() or DEFAULT_MAX_BYTES)
    if target is None or not target.is_dir():
        return PruneResult(0, 0, 0)
    keep = {item.resolve() for item in protect}
    entries = _entries(target)
    total = sum(size for _, size, _ in entries)
    if total <= limit:
        return PruneResult(0, 0, total)
    removed = 0
    freed = 0
    for path, size, _ in sorted(entries, key=lambda item: item[2]):
        if total <= limit:
            break
        if path.resolve() in keep:
            continue
        if not dry_run:
            try:
                path.unlink()
            except OSError:
                continue
        removed += 1
        freed += size
        total -= size
    if not dry_run:
        _remove_empty(target)
    return PruneResult(removed, freed, total)


def enforce_limit(*, protect: Iterable[Path] = ()) -> PruneResult | None:
    """Aplica o limite depois de um build; nunca falha o `run`."""
    try:
        return prune(protect=protect)
    except OSError:  # pragma: no cover - defensivo
        return None


def _remove_empty(base: Path) -> None:
    for current, _dirnames, filenames in os.walk(base, topdown=False):
        if Path(current) == base or filenames:
            continue
        try:
            Path(current).rmdir()
        except OSError:
            continue


def summarize(result: PruneResult, *, dry_run: bool = False) -> str:
    if result.removed == 0:
        return f"cache is within the limit ({result.remaining / 1024**2:.1f} MiB)."
    verb = "would remove" if dry_run else "removed"
    return (
        f"{verb} {result.removed} binarie(s), freed {result.megabytes:.1f} MiB; "
        f"{result.remaining / 1024**2:.1f} MiB left."
    )


__all__ = [
    "DEFAULT_MAX_BYTES",
    "BuildRequest",
    "PruneResult",
    "build_key",
    "cache_root",
    "cache_size",
    "directory",
    "enforce_limit",
    "entry_name",
    "locate",
    "max_bytes_from_env",
    "parse_size",
    "prune",
    "store",
    "summarize",
    "toolchain_stamp",
]

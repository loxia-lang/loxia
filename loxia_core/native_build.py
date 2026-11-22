# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build sob demanda do crate Rust do motor de regex (ADR-0131).

O interpretador carrega a `cdylib` por `ctypes`; o binário linka a `staticlib`
(ver `loxia_core/backend/driver.py`). Aqui ficam só: achar o `cargo`, calcular a
chave do cache, compilar uma vez e devolver o caminho da biblioteca.

O build é sempre `--locked --offline` contra `native/regex/vendor`: nada de
rede, nada de descoberta de ambiente além do próprio toolchain.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from loxia_core.bundle import bundle_dir
from loxia_core.diagnostics.errors import NativeError

CARGO_ENV = "LOX_CARGO"
CACHE_ENV = "LOX_BUILD_CACHE"
BUILD_TIMEOUT_SECONDS = 600

E3022_MESSAGE = (
    "regex requires the Rust toolchain (cargo). Install Rust or point LOX_CARGO at "
    "the cargo binary; see docs/adr/0131-regex-motor-rust-dois-modos.md."
)

_LIBRARY_NAME = "liblox_regex.dylib" if sys.platform == "darwin" else "liblox_regex.so"
_SOURCE_FILES = ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo/config.toml")
_SOURCE_DIRS = ("src", "include")


def cargo_binary() -> str | None:
    """Caminho do `cargo`, ou `None` quando o toolchain não está instalado."""
    override = os.environ.get(CARGO_ENV)
    if override:
        path = Path(override)
        return str(path) if path.is_file() else None
    return shutil.which("cargo")


def crate_dir() -> Path:
    return bundle_dir("native") / "regex"


def library() -> Path:
    """Compila (se preciso) e devolve o caminho da `cdylib` do motor."""
    cargo = cargo_binary()
    if cargo is None:
        raise NativeError(E3022_MESSAGE)

    directory = _cache_root() / _cache_key(cargo)
    target = directory / _LIBRARY_NAME
    if target.is_file():
        return target

    try:
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    except OSError as error:
        raise NativeError("regex: could not create the native build cache.") from error

    with _locked(directory):
        if target.is_file():
            return target
        _build(cargo, directory)

    if not target.is_file():
        raise NativeError("regex: the native build did not produce a library.")
    return target


def _cache_root() -> Path:
    override = os.environ.get(CACHE_ENV)
    if override:
        return Path(override) / "regex"

    candidates: list[Path] = []
    xdg = os.environ.get("XDG_CACHE_HOME")
    if xdg:
        candidates.append(Path(xdg) / "loxia" / "regex")
    with contextlib.suppress(RuntimeError):  # sem HOME
        candidates.append(Path.home() / ".cache" / "loxia" / "regex")
    uid = os.getuid() if hasattr(os, "getuid") else 0
    candidates.append(Path(tempfile.gettempdir()) / f"loxia-build-{uid}" / "regex")

    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, mode=0o700, exist_ok=True)
        except OSError:
            continue
        if os.access(candidate, os.W_OK):
            return candidate
    raise NativeError("regex: no writable cache directory for the native build.")


def _cache_key(cargo: str) -> str:
    digest = hashlib.sha256()
    digest.update(_sources_digest().encode())
    digest.update(_toolchain_id(cargo).encode())
    digest.update(sys.platform.encode())
    digest.update(platform.machine().encode())
    return digest.hexdigest()[:32]


def _sources_digest() -> str:
    crate = crate_dir()
    digest = hashlib.sha256()
    for name in _SOURCE_FILES:
        path = crate / name
        if path.is_file():
            digest.update(name.encode())
            digest.update(path.read_bytes())
    for directory in _SOURCE_DIRS:
        for path in sorted((crate / directory).rglob("*")):
            if path.is_file():
                digest.update(str(path.relative_to(crate)).encode())
                digest.update(path.read_bytes())
    return digest.hexdigest()


def _toolchain_id(cargo: str) -> str:
    parts = [cargo]
    for tool in (cargo, shutil.which("rustc")):
        if tool is None:
            continue
        try:
            completed = subprocess.run(
                [tool, "--version"], capture_output=True, text=True, timeout=10, check=False
            )
        except (OSError, subprocess.SubprocessError):
            continue
        parts.append(completed.stdout.strip() or completed.stderr.strip())
    return "|".join(parts)


@contextmanager
def _locked(directory: Path) -> Iterator[None]:
    import fcntl

    handle = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def _build(cargo: str, directory: Path) -> None:
    crate = crate_dir()
    environment = dict(os.environ)
    environment["CARGO_TARGET_DIR"] = str(directory / "target")
    environment["CARGO_HOME"] = str(directory / "cargo-home")

    # O aviso só aparece em TTY: stdout e stderr são canais do I1 (ADR-0131 §4).
    if sys.stderr.isatty():
        sys.stderr.write("[loxia] building the regex engine (first run only)...\n")
        sys.stderr.flush()

    try:
        completed = subprocess.run(
            [cargo, "build", "--release", "--locked", "--offline"],
            cwd=crate,
            env=environment,
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise NativeError("regex: could not run cargo to build the native engine.") from error

    if completed.returncode != 0:
        raise NativeError(
            f"regex: building the native engine failed (cargo exit {completed.returncode})."
        )

    built = directory / "target" / "release" / _LIBRARY_NAME
    if not built.is_file():
        raise NativeError("regex: cargo finished without producing the native library.")

    temporary = directory / f".{_LIBRARY_NAME}.{os.getpid()}.tmp"
    shutil.copyfile(built, temporary)
    os.replace(temporary, directory / _LIBRARY_NAME)

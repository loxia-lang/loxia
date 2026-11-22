# SPDX-License-Identifier: MIT OR Apache-2.0
"""Build sob demanda do crate Rust do motor de regex (ADR-0131).

Dois consumidores: o interpretador carrega a `cdylib` por `ctypes`, e o backend
linka a `staticlib` em `--emit=exe`. Aqui ficam só: achar o `cargo`, calcular a
chave do cache, compilar uma vez e devolver os artefatos (e as libs nativas que o
Rust exige no link estático).

O build é sempre `--locked --offline` contra `native/regex/vendor`: nada de rede,
nada de descoberta de ambiente além do próprio toolchain.
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

TOOLCHAIN_MESSAGE = "regex requires the Rust toolchain (cargo); install Rust or set LOX_CARGO."

E3022_MESSAGE = f"{TOOLCHAIN_MESSAGE} See docs/adr/0131-regex-motor-rust-dois-modos.md."

_LIBRARY_NAME = "liblox_regex.dylib" if sys.platform == "darwin" else "liblox_regex.so"
_STATIC_NAME = "liblox_regex.a"
_NATIVE_LIBS_NAME = "native-libs.txt"
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
    directory, cargo = _prepare()
    target = directory / _LIBRARY_NAME
    if target.is_file():
        return target

    with _locked(directory):
        if target.is_file():
            return target
        _build(cargo, directory)

    if not target.is_file():
        raise NativeError("regex: the native build did not produce a library.")
    return target


def static_library() -> tuple[Path, tuple[str, ...]]:
    """Devolve a `staticlib` e as libs nativas do Rust para o link final."""
    directory, cargo = _prepare()
    archive = directory / _STATIC_NAME
    native_libs = directory / _NATIVE_LIBS_NAME

    if not (archive.is_file() and native_libs.is_file()):
        with _locked(directory):
            if not archive.is_file():
                _build(cargo, directory)
            if not native_libs.is_file():
                _capture_native_libs(cargo, directory, native_libs)

    if not archive.is_file():
        raise NativeError("regex: the native build did not produce a static library.")
    return archive, tuple(native_libs.read_text(encoding="utf-8").split())


def _prepare() -> tuple[Path, str]:
    cargo = cargo_binary()
    if cargo is None:
        raise NativeError(E3022_MESSAGE)
    directory = _cache_root() / _cache_key(cargo)
    try:
        directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    except OSError as error:
        raise NativeError("regex: could not create the native build cache.") from error
    return directory, cargo


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


def _cargo_environment(directory: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["CARGO_TARGET_DIR"] = str(directory / "target")
    environment["CARGO_HOME"] = str(directory / "cargo-home")
    return environment


def _build(cargo: str, directory: Path) -> None:
    # O aviso só aparece em TTY: stdout e stderr são canais do I1 (ADR-0131 §4).
    if sys.stderr.isatty():
        sys.stderr.write("[loxia] building the regex engine (first run only)...\n")
        sys.stderr.flush()

    try:
        completed = subprocess.run(
            [cargo, "build", "--release", "--locked", "--offline"],
            cwd=crate_dir(),
            env=_cargo_environment(directory),
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

    release = directory / "target" / "release"
    for built, name in (
        (release / _LIBRARY_NAME, _LIBRARY_NAME),
        (release / _STATIC_NAME, _STATIC_NAME),
    ):
        if not built.is_file():
            continue
        temporary = directory / f".{name}.{os.getpid()}.tmp"
        shutil.copyfile(built, temporary)
        os.replace(temporary, directory / name)

    if not (directory / _LIBRARY_NAME).is_file():
        raise NativeError("regex: cargo finished without producing the native library.")


def _capture_native_libs(cargo: str, directory: Path, target: Path) -> None:
    """Pergunta ao toolchain quais libs nativas a `staticlib` exige (ADR-0131 §5)."""
    try:
        completed = subprocess.run(
            [
                cargo,
                "rustc",
                "--release",
                "--locked",
                "--offline",
                "--",
                "--print",
                "native-static-libs",
            ],
            cwd=crate_dir(),
            env=_cargo_environment(directory),
            capture_output=True,
            text=True,
            timeout=BUILD_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise NativeError("regex: could not query native-static-libs.") from error

    if completed.returncode != 0:
        raise NativeError(
            f"regex: cargo could not report native-static-libs (exit {completed.returncode})."
        )

    libraries: list[str] = []
    for line in completed.stderr.splitlines():
        _, separator, tail = line.partition("native-static-libs:")
        if separator:
            libraries = tail.split()

    if not libraries:
        raise NativeError("regex: cargo did not report native-static-libs.")

    temporary = target.with_suffix(".tmp")
    temporary.write_text(" ".join(libraries) + "\n", encoding="utf-8")
    os.replace(temporary, target)

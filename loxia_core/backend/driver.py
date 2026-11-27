# SPDX-License-Identifier: MIT OR Apache-2.0
"""Pipeline de build: AST → IR → objeto → executável.

O link é feito pelo compilador C do sistema (`cc`, `clang` ou `gcc`): o `llvmlite` emite
o object file com o LLVM que ele mesmo embarca, e o C compiler só faz o que sabe fazer —
linkar. Assim não há descompasso entre a versão do LLVM que gera o `.ll` e a que linka.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

from loxia_core.backend import llvm_ir
from loxia_core.backend.lower import BackendError, lower_program
from loxia_core.bundle import bundle_dir
from loxia_core.execution.limits import (
    DEFAULT_HEAP_BYTES,
    MAX_CALL_DEPTH,
    MAX_FS_HANDLES,
    NATIVE_STACK_RESERVE_BYTES,
    TRACE_HEAD,
    TRACE_TAIL,
)
from loxia_core.frontend.expr import Expr
from loxia_core.frontend.stmt import Function, Stmt
from loxia_core.frontend.ty import Ty
from loxia_core.native_build import static_library as regex_static_library
from loxia_core.semantics.layers import REGEX_PRIMITIVES, uses_primitive

Emit = Literal["ll", "obj", "exe"]

# O runtime é dividido por domínio; a lista é explícita para um arquivo novo não
# entrar no build por acidente (o teste `test_runtime_sources` cobre isso).
RUNTIME_DIR = bundle_dir("runtime")
RUNTIME_NAMES = (
    "core.c",
    "objects.c",
    "strings.c",
    "containers.c",
    "numeric.c",
    "kernel.c",
    "proc.c",
    "digest.c",
    "bytes.c",
)
RUNTIME_SOURCES = tuple(RUNTIME_DIR / name for name in RUNTIME_NAMES)
RUNTIME_HEADERS = tuple(sorted(RUNTIME_DIR.glob("*.h")))

# Unidades que só entram no link quando o programa usa a capacidade (ADR-0126).
# `regex.c` chama o motor Rust (ADR-0131) e só é compilado com `regex_engine.*`.
REGEX_UNIT = "regex.c"
REGEX_SOURCE = RUNTIME_DIR / REGEX_UNIT
# Capacidade → unidades extras. Lista explícita (ADR-0126): um `.c` novo não entra
# no link por acidente.
MODULE_RUNTIME_UNITS: dict[str, tuple[str, ...]] = {"regex": (REGEX_UNIT,)}
REGEX_ABI_HEADER = bundle_dir("native") / "regex" / "include" / "lox_regex.h"
REGEX_CRATE_LOCK = bundle_dir("native") / "regex" / "Cargo.lock"

# Flags base do runtime; o cap de heap e o teto de pilha entram por build.
RUNTIME_FLAGS = ("-O2", "-std=c11")


def _runtime_flags(heap_bytes: int) -> tuple[str, ...]:
    return (
        *RUNTIME_FLAGS,
        f"-DLOX_GC_MAX_HEAP_BYTES={heap_bytes}ull",
        f"-DLOX_MAX_CALL_DEPTH={MAX_CALL_DEPTH}",
        f"-DLOX_TRACE_HEAD={TRACE_HEAD}",
        f"-DLOX_TRACE_TAIL={TRACE_TAIL}",
        f"-DLOX_STACK_RESERVE_BYTES={NATIVE_STACK_RESERVE_BYTES}ull",
        f"-DLOX_MAX_FS_HANDLES={MAX_FS_HANDLES}",
    )


def build(
    statements: list[Stmt],
    *,
    emit: Emit,
    output: Path | None,
    stem: str,
    types: dict[Expr, Ty],
    depths: dict[Expr, int],
    flow_types: dict[Expr, Ty] | None = None,
    generic_instances: Any = None,
    generic_classes: Any = None,
    generic_class_sites: Any = None,
    type_aliases: dict[str, Ty] | None = None,
    function_types: dict[Any, Any] | None = None,
    source_path: str = "<lox>",
    max_heap: int | None = None,
    debug: bool = False,
    entry: Function | None = None,
) -> Path | None:
    """Gera a saída pedida. Devolve o arquivo criado (ou `None` quando foi o stdout)."""
    try:
        module = lower_program(
            statements,
            types=types,
            depths=depths,
            flow_types=flow_types,
            generic_instances=generic_instances,
            generic_classes=generic_classes,
            generic_class_sites=generic_class_sites,
            type_aliases=type_aliases,
            function_types=function_types,
            source_path=source_path,
            debug=debug,
            entry=entry,
        )
        _verify(module)

        if emit == "ll":
            text = llvm_ir.emit_text(module)
            if output is None:
                sys.stdout.write(text if text.endswith("\n") else f"{text}\n")
                return None
            output.write_text(text, encoding="utf-8")
            return output

        object_bytes = llvm_ir.emit_object(module)
    except BackendError:
        raise
    except Exception as error:
        raise BackendError(
            f"internal error: LLVM lowering/emission failed: {type(error).__name__}: {error}"
        ) from error

    if emit == "obj":
        target = output or Path(f"{stem}.o")
        target.write_bytes(object_bytes)
        return target

    target = output or Path(stem)
    heap_bytes = DEFAULT_HEAP_BYTES if max_heap is None else max_heap
    regex_used = uses_primitive(statements, depths, REGEX_PRIMITIVES)
    try:
        _link(object_bytes, target, heap_bytes, regex_used)
    except BackendError:
        raise
    except Exception as error:
        raise BackendError(
            f"internal error: native link failed: {type(error).__name__}: {error}"
        ) from error
    return target


def _verify(module: Any) -> None:
    """Rede de segurança: IR inválido é erro interno, não binário quebrado."""
    try:
        llvm_ir.verify(module)
    except llvm_ir.LLVMVerificationError as error:
        raise BackendError(f"internal error: generated invalid LLVM IR: {error}") from error


def runtime_sources(regex: bool) -> tuple[Path, ...]:
    """Unidades do runtime para um build: as base e, se usada, a do regex."""
    names = RUNTIME_NAMES + (MODULE_RUNTIME_UNITS["regex"] if regex else ())
    return tuple(RUNTIME_DIR / name for name in names)


def _link(object_bytes: bytes, target: Path, heap_bytes: int, regex: bool) -> None:
    compiler = _compiler()
    sources = runtime_sources(regex)

    with tempfile.TemporaryDirectory(prefix="lox-build-") as directory:
        build_dir = Path(directory)
        program_object = build_dir / "program.o"
        program_object.write_bytes(object_bytes)
        runtime_objects = _runtime_objects(compiler, build_dir, heap_bytes, sources, regex)

        command = [
            compiler,
            str(program_object),
            *(str(object_) for object_ in runtime_objects),
            "-o",
            str(target),
        ]
        if regex:
            archive, native_libs = regex_static_library()
            command.extend([str(archive), *native_libs])
        command.extend(["-lgc", "-lm"])

        try:
            _run(command)
        except BackendError as error:
            raise _with_gc_hint(_sanitize_compiler_error(error, build_dir)) from error


def _runtime_objects(
    compiler: str, build_dir: Path, heap_bytes: int, sources: tuple[Path, ...], regex: bool
) -> tuple[Path, ...]:
    """Compila as unidades do runtime uma vez por (fontes, compilador, flags).

    O runtime não depende do programa do usuário; recompilá-lo a cada `--emit=exe`
    custava a maior parte da suíte de testes. O cache é só de desempenho: nenhum
    caminho dele aparece na saída e qualquer falha cai no caminho antigo (compilar
    dentro do diretório temporário do build).
    """
    cache = _runtime_cache_dir()
    if cache is not None:
        key = _runtime_key(compiler, heap_bytes, sources, regex)
        directory = cache / f"runtime-{key}"
        objects = tuple(directory / f"{source.stem}.o" for source in sources)
        if all(object_.is_file() and object_.stat().st_size > 0 for object_ in objects):
            return objects

        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            for source, object_ in zip(sources, objects, strict=True):
                if object_.is_file() and object_.stat().st_size > 0:
                    continue
                temporary = directory / f"{source.stem}.{os.getpid()}.tmp.o"
                try:
                    _compile_runtime_unit(compiler, source, temporary, directory, heap_bytes)
                    os.replace(temporary, object_)
                finally:
                    temporary.unlink(missing_ok=True)
            return objects
        except (BackendError, OSError):
            pass

    fallback: list[Path] = []
    for source in sources:
        object_ = build_dir / f"runtime_{source.stem}.o"
        _compile_runtime_unit(compiler, source, object_, build_dir, heap_bytes)
        fallback.append(object_)
    return tuple(fallback)


def _compile_runtime_unit(
    compiler: str,
    source: Path,
    output: Path,
    sanitized_dir: Path,
    heap_bytes: int,
) -> None:
    try:
        _run(
            [
                compiler,
                *_runtime_flags(heap_bytes),
                "-c",
                str(source),
                "-o",
                str(output),
            ]
        )
    except BackendError as error:
        raise _with_gc_hint(
            _sanitize_compiler_error(error, sanitized_dir, output=output)
        ) from error


def _runtime_key(compiler: str, heap_bytes: int, sources: tuple[Path, ...], regex: bool) -> str:
    digest = hashlib.sha256()
    for path in (*sources, *RUNTIME_HEADERS):
        try:
            source = path.read_bytes()
        except OSError as error:
            raise BackendError(f"internal error: can't read runtime source: {error}") from error
        # O nome entra na chave: renomear/remover arquivo muda o build.
        digest.update(path.name.encode("utf-8"))
        digest.update(source)
    digest.update(compiler.encode("utf-8"))
    digest.update(_compiler_version(compiler).encode("utf-8"))
    digest.update(" ".join(_runtime_flags(heap_bytes)).encode("utf-8"))
    # `CPATH` muda de onde vem o `gc.h`; incluir evita cache de header trocado.
    digest.update(os.environ.get("CPATH", "").encode("utf-8"))
    if regex:
        # O adaptador inclui o ABI do crate; a versão do motor entra pelo lock.
        for path in (REGEX_ABI_HEADER, REGEX_CRATE_LOCK):
            try:
                digest.update(path.read_bytes())
            except OSError as error:
                raise BackendError(
                    f"internal error: can't read the native regex sources: {error}"
                ) from error
    return digest.hexdigest()[:32]


def _compiler_version(compiler: str) -> str:
    try:
        process = subprocess.run(
            [compiler, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return process.stdout.splitlines()[0] if process.stdout else ""


def _runtime_cache_dir() -> Path | None:
    """Diretório de cache por usuário; `LOX_BUILD_CACHE` permite isolar/testar."""
    configured = os.environ.get("LOX_BUILD_CACHE")
    if configured:
        base = Path(configured)
    else:
        user = str(os.getuid()) if hasattr(os, "getuid") else "user"
        base = Path(tempfile.gettempdir()) / f"loxia-build-{user}"
    try:
        base.mkdir(mode=0o700, parents=True, exist_ok=True)
        if hasattr(os, "getuid") and base.stat().st_uid != os.getuid():
            return None
    except OSError:
        return None
    return base


def _sanitize_compiler_error(
    error: BackendError, build_dir: Path, *, output: Path | None = None
) -> BackendError:
    """Remove caminhos temporários/absolutos do stderr do C compiler (I3)."""
    message = error.message
    if output is not None:
        # O nome do `.o` da cache carrega o PID do processo; nunca pode vazar.
        message = message.replace(str(output), "<build>/runtime.o")
    message = message.replace(str(build_dir), "<build>")
    for source in (*RUNTIME_SOURCES, REGEX_SOURCE):
        message = message.replace(str(source), f"runtime/{source.name}")
    message = message.replace(str(RUNTIME_DIR), "runtime")
    message = message.replace(str(RUNTIME_DIR.parent), "<repo>")
    return BackendError(message, error.line, code=error.code)


def _with_gc_hint(error: BackendError) -> BackendError:
    """Explica a dependência de build quando o erro é falta de `libgc`."""
    message = error.message
    if "gc.h" in message or "lgc" in message or "libgc" in message:
        message = (
            f"{message}\n"
            "The native backend requires libgc (bdw-gc). Install libgc-dev "
            "(Debian/Ubuntu), gc-devel (Fedora) or bdw-gc (macOS/Homebrew)."
        )
    return BackendError(message, error.line)


def _compiler() -> str:
    for candidate in ("cc", "clang", "gcc"):
        found = shutil.which(candidate)
        if found is not None:
            return found

    raise BackendError("no C compiler found (tried cc, clang and gcc).")


def _run(command: list[str]) -> None:
    try:
        process = subprocess.run(command, capture_output=True, text=True, check=False)
    except OSError as error:
        raise BackendError(
            f"internal error: failed to run {Path(command[0]).name}: {error}"
        ) from error
    if process.returncode == 0:
        return

    detail = process.stderr.strip() or process.stdout.strip()
    # O detalhe é do compilador; o driver sanitiza os caminhos no chamador.
    raise BackendError(f"{Path(command[0]).name} failed: {detail}")

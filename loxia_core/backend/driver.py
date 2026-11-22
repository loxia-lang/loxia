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
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.ty import Ty

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
    generic_instances: Any = None,
    generic_classes: Any = None,
    generic_class_sites: Any = None,
    type_aliases: dict[str, Ty] | None = None,
    source_path: str = "<lox>",
    max_heap: int | None = None,
    debug: bool = False,
) -> Path | None:
    """Gera a saída pedida. Devolve o arquivo criado (ou `None` quando foi o stdout)."""
    try:
        module = lower_program(
            statements,
            types=types,
            depths=depths,
            generic_instances=generic_instances,
            generic_classes=generic_classes,
            generic_class_sites=generic_class_sites,
            type_aliases=type_aliases,
            source_path=source_path,
            debug=debug,
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
    try:
        _link(object_bytes, target, heap_bytes)
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


def _link(object_bytes: bytes, target: Path, heap_bytes: int) -> None:
    compiler = _compiler()

    with tempfile.TemporaryDirectory(prefix="lox-build-") as directory:
        build_dir = Path(directory)
        program_object = build_dir / "program.o"
        program_object.write_bytes(object_bytes)
        runtime_objects = _runtime_objects(compiler, build_dir, heap_bytes)

        try:
            _run(
                [
                    compiler,
                    str(program_object),
                    *(str(object_) for object_ in runtime_objects),
                    "-o",
                    str(target),
                    "-lm",
                    "-lgc",
                ]
            )
        except BackendError as error:
            raise _with_gc_hint(_sanitize_compiler_error(error, build_dir)) from error


def _runtime_objects(compiler: str, build_dir: Path, heap_bytes: int) -> tuple[Path, ...]:
    """Compila as unidades do runtime uma vez por (fontes, compilador, flags).

    O runtime não depende do programa do usuário; recompilá-lo a cada `--emit=exe`
    custava a maior parte da suíte de testes. O cache é só de desempenho: nenhum
    caminho dele aparece na saída e qualquer falha cai no caminho antigo (compilar
    dentro do diretório temporário do build).
    """
    cache = _runtime_cache_dir()
    if cache is not None:
        key = _runtime_key(compiler, heap_bytes)
        directory = cache / f"runtime-{key}"
        objects = tuple(directory / f"{source.stem}.o" for source in RUNTIME_SOURCES)
        if all(object_.is_file() and object_.stat().st_size > 0 for object_ in objects):
            return objects

        try:
            directory.mkdir(mode=0o700, parents=True, exist_ok=True)
            for source, object_ in zip(RUNTIME_SOURCES, objects, strict=True):
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
    for source in RUNTIME_SOURCES:
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


def _runtime_key(compiler: str, heap_bytes: int) -> str:
    digest = hashlib.sha256()
    for path in (*RUNTIME_SOURCES, *RUNTIME_HEADERS):
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
    for source in RUNTIME_SOURCES:
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

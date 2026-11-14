"""Pipeline de build: AST → IR → objeto → executável.

O link é feito pelo compilador C do sistema (`cc`, `clang` ou `gcc`): o `llvmlite` emite
o object file com o LLVM que ele mesmo embarca, e o C compiler só faz o que sabe fazer —
linkar. Assim não há descompasso entre a versão do LLVM que gera o `.ll` e a que linka.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

from src.backend import llvm_ir
from src.backend.lower import BackendError, lower_program
from src.frontend.expr import Expr
from src.frontend.stmt import Stmt
from src.frontend.ty import Ty

Emit = Literal["ll", "obj", "exe"]

RUNTIME_SOURCE = Path(__file__).resolve().parents[2] / "runtime" / "runtime.c"


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
    source_path: str = "<lox>",
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
            source_path=source_path,
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
            "internal error: LLVM lowering/emission failed: "
            f"{type(error).__name__}: {error}"
        ) from error

    if emit == "obj":
        target = output or Path(f"{stem}.o")
        target.write_bytes(object_bytes)
        return target

    target = output or Path(stem)
    try:
        _link(object_bytes, target)
    except BackendError:
        raise
    except Exception as error:
        raise BackendError(
            "internal error: native link failed: "
            f"{type(error).__name__}: {error}"
        ) from error
    return target


def _verify(module: Any) -> None:
    """Rede de segurança: IR inválido é erro interno, não binário quebrado."""
    try:
        llvm_ir.verify(module)
    except llvm_ir.LLVMVerificationError as error:
        raise BackendError(
            f"internal error: generated invalid LLVM IR: {error}"
        ) from error


def _link(object_bytes: bytes, target: Path) -> None:
    compiler = _compiler()

    with tempfile.TemporaryDirectory(prefix="lox-build-") as directory:
        build_dir = Path(directory)
        program_object = build_dir / "program.o"
        runtime_object = build_dir / "runtime.o"
        program_object.write_bytes(object_bytes)

        try:
            _run(
                [
                    compiler,
                    "-O2",
                    "-std=c11",
                    "-c",
                    str(RUNTIME_SOURCE),
                    "-o",
                    str(runtime_object),
                ]
            )
        except BackendError as error:
            raise _with_gc_hint(_sanitize_compiler_error(error, build_dir)) from error
        try:
            _run(
                [
                    compiler,
                    str(program_object),
                    str(runtime_object),
                    "-o",
                    str(target),
                    "-lm",
                    "-lgc",
                ]
            )
        except BackendError as error:
            raise _with_gc_hint(_sanitize_compiler_error(error, build_dir)) from error


def _sanitize_compiler_error(error: BackendError, build_dir: Path) -> BackendError:
    """Remove caminhos temporários/absolutos do stderr do C compiler (I3)."""
    message = error.message.replace(str(build_dir), "<build>")
    message = message.replace(str(RUNTIME_SOURCE), "runtime/runtime.c")
    message = message.replace(str(RUNTIME_SOURCE.parent.parent), "<repo>")
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
        process = subprocess.run(
            command, capture_output=True, text=True, check=False
        )
    except OSError as error:
        raise BackendError(
            f"internal error: failed to run {Path(command[0]).name}: {error}"
        ) from error
    if process.returncode == 0:
        return

    detail = process.stderr.strip() or process.stdout.strip()
    # O detalhe é do compilador; o driver sanitiza os caminhos no chamador.
    raise BackendError(f"{Path(command[0]).name} failed: {detail}")

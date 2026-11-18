# SPDX-License-Identifier: MIT OR Apache-2.0
"""Medição do orçamento de monomorfização (ADR-0063, M8).

Replay do corpus pelo checker (quantas instanciações cada caso realmente pede) e um caso
sintético de N classes/instanciações para medir tempo e tamanho do `.ll` até o teto. Não é
um gate: rode com `make monomorph` e registre os números no `bench/README.md`.
"""

from __future__ import annotations

import io
import tempfile
import time
from contextlib import redirect_stderr
from dataclasses import dataclass
from pathlib import Path

from loxia.cli import Loxia
from loxia_core.backend.lower_generics import (
    MAX_GENERIC_FUNCTIONS,
    MAX_GENERIC_TYPE_DEPTH,
    MAX_MANGLED_BYTES,
    _type_depth,
)
from loxia_core.frontend.ty import display

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "tests" / "cases"


@dataclass(frozen=True)
class Stats:
    functions: int
    classes: int
    depth: int
    mangled: int


def _stats(source: str) -> Stats | None:
    lox = Loxia(error_format="short")
    with redirect_stderr(io.StringIO()):
        lox.check(source)
    checker = lox.last_checker
    if lox.reporter.had_error or checker is None:
        return None
    functions = {
        (instance.name, tuple(display(arg) for arg in instance.type_args)): instance.type_args
        for instance in checker.generic_fn_instances.values()
    }
    classes = {
        (ty.name, tuple(display(arg) for arg in ty.args)): ty.args
        for ty in checker.concrete_class_types()
    }
    depths = [_type_depth(arg) for type_args in functions.values() for arg in type_args] + [
        _type_depth(arg) for args in classes.values() for arg in args
    ]
    mangled = [
        len(("lox." + name + "$" + "$".join(text for text in args)).encode("utf-8"))
        for name, args in functions
    ] + [
        len((name + "$" + "$".join(text for text in args)).encode("utf-8"))
        for name, args in classes
    ]
    return Stats(
        functions=len(functions),
        classes=len(classes),
        depth=max(depths, default=0),
        mangled=max(mangled, default=0),
    )


def _corpus() -> None:
    files = sorted(CASES.rglob("*.lx"))
    skipped = 0
    total = 0
    maxima: dict[str, tuple[int, str]] = {
        "funções": (0, "-"),
        "classes": (0, "-"),
        "profundidade": (0, "-"),
        "mangled": (0, "-"),
    }
    started = time.perf_counter()
    for path in files:
        stats = _stats(path.read_text(encoding="utf-8"))
        if stats is None:
            skipped += 1
            continue
        total += 1
        relative = path.relative_to(ROOT).as_posix()
        for key, value in (
            ("funções", stats.functions),
            ("classes", stats.classes),
            ("profundidade", stats.depth),
            ("mangled", stats.mangled),
        ):
            if value > maxima[key][0]:
                maxima[key] = (value, relative)
    elapsed = time.perf_counter() - started
    print(f"Corpus: {total} casos medidos, {skipped} pulados, {elapsed * 1000:.0f} ms\n")
    print("| máximo | valor | caso |")
    print("| --- | ---: | --- |")
    for key, (value, case) in maxima.items():
        print(f"| {key} | {value} | `{case}` |")
    print()


def _synthetic_source(count: int) -> str:
    lines = ["fn id[T](x: T) -> T { return x }"]
    lines.extend(f"class C{index} {{ }}" for index in range(count))
    lines.extend(f"print(id(C{index}()))" for index in range(count))
    return "\n".join(lines) + "\n"


def _synthetic(count: int) -> None:
    source = _synthetic_source(count)
    with tempfile.TemporaryDirectory(prefix="lox-monomorph-") as directory:
        output = Path(directory) / "synthetic.ll"
        lox = Loxia(error_format="short")
        errors = io.StringIO()
        started = time.perf_counter()
        with redirect_stderr(errors):
            built = lox.build(source, emit="ll", output=output, stem="synthetic")
        elapsed = time.perf_counter() - started
        size = output.stat().st_size if built and output.is_file() else 0
    status = f"ok ({size / 1024:.0f} KiB)" if built else "recusado"
    detail = "" if built else errors.getvalue().strip().splitlines()[-1]
    print(f"| {count} | {elapsed * 1000:.0f} ms | {status} | {detail} |")


def main() -> int:
    print(
        "Limites: "
        f"{MAX_GENERIC_FUNCTIONS} funções, {MAX_GENERIC_TYPE_DEPTH} de profundidade, "
        f"{MAX_MANGLED_BYTES} bytes de nome mangled.\n"
    )
    _corpus()
    print("| instanciações | tempo | resultado | detalhe |")
    print("| ---: | ---: | --- | --- |")
    for count in (16, 64, 128, 256, 257):
        _synthetic(count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

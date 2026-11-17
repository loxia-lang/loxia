"""Gera `runtime/kernel_gen.h` a partir da tabela única de primitivas (ADR-0071).

O header gerado declara o símbolo C de cada primitiva com a assinatura que o lowering
espera (`params`/`result`/`site`). O `kernel.c` o inclui: se a tabela e a definição C
divergirem, o build falha em compilação em vez de em teste.

Uso: `python runtime/gen_kernel.py --write` (ou `--check`, que só compara).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loxia_core.execution.primitives import PRIMITIVES, Primitive  # noqa: E402
from loxia_core.frontend.ty import (  # noqa: E402
    BOOL,
    FLOAT,
    INT,
    NIL,
    STRING,
    ListTy,
    Ty,
    UnionTy,
)

OUT = ROOT / "runtime" / "kernel_gen.h"


def _c_type(ty: Ty, *, result: bool) -> str:
    if ty is STRING or isinstance(ty, ListTy):
        return "void *" if result else "const void *"
    if isinstance(ty, UnionTy):
        return "void *"
    if ty is INT:
        return "int64_t"
    if ty is BOOL:
        return "int32_t"
    if ty is FLOAT:
        return "double"
    if ty is NIL:
        return "void"
    raise SystemExit(f"tipo sem mapeamento C: {ty!r}")


def _signature(primitive: Primitive) -> str:
    result = _c_type(primitive.result, result=True)
    params = [_c_type(param, result=False) for param in primitive.params]
    if primitive.site:
        params.extend(["int32_t", "int32_t"])
    joined = ", ".join(params) if params else "void"
    return f"{result} {primitive.c_symbol}({joined});"


def render() -> str:
    lines = [
        "/*",
        " * Gerado por `runtime/gen_kernel.py` a partir de",
        " * `loxia_core/execution/primitives.py`. NÃO EDITE À MÃO.",
        " *",
        " * Cada declaração é a assinatura que o lowering usa; o `kernel.c` inclui este",
        " * header, então tabela e definição C não podem divergir sem quebrar o build",
        " * (ADR-0071, ADR-0094).",
        " */",
        "#ifndef LOX_KERNEL_GEN_H",
        "#define LOX_KERNEL_GEN_H",
        "",
        "#include <stdint.h>",
        "",
    ]
    for primitive in PRIMITIVES:
        lines.append(f"/* {primitive.lox} */")
        lines.append(_signature(primitive))
    lines.extend(["", "#endif /* LOX_KERNEL_GEN_H */", ""])
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    text = render()
    current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    if "--write" in argv:
        OUT.write_text(text, encoding="utf-8")
        print(f"{OUT.relative_to(ROOT)}: {len(PRIMITIVES)} primitivas")
        return 0
    if "--check" in argv:
        if current != text:
            print(f"desatualizado: {OUT.relative_to(ROOT)}")
            print("Rode: make primitives")
            return 1
        return 0
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

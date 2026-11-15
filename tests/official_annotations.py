"""Anotação dinâmica da suíte oficial para o `--check`.

Os `.lx` de `tests/official/cases` são mantidos como no original (MIT). O
`test_official_suite` já adapta sintaxe; este módulo aplica uma camada de
anotações **em cima da fonte adaptada**, só para o checker. Como os testes
oficiais são dinâmicos, a anotação é `Any` (o escape explícito da linguagem):
o runtime não muda e os tipos precisos ficam para quando L4/L5 permitirem
testar o nativo.

Casos negativos (que esperam erro de compilação/runtime) não passam por aqui:
eles provam justamente o erro. Os `xfail` de campos dinâmicos também ficam de
fora.
"""

from __future__ import annotations

import re
from collections.abc import Callable

_CONTROL = {
    "if",
    "for",
    "while",
    "switch",
    "else",
    "fn",
    "return",
    "print",
    "var",
    "val",
    "class",
    "try",
    "catch",
}

_SPECIAL: dict[str, Callable[[str], str]] = {
    # O teste reatribui uma classe (`Base = OtherBase`); o checker nominal recusa
    # a troca. O `as Any` é só anotação: o runtime do teste oficial não muda.
    "super/reassign_superclass.lx": lambda source: source.replace(
        "Base = OtherBase;", "Base = OtherBase as Any;"
    ),
}


def _typed_params(params: str) -> str:
    if not params.strip():
        return params

    typed: list[str] = []
    for raw in params.split(","):
        param = raw.strip()
        if param and ":" not in param and "=" not in param:
            param += ": Any"
        typed.append(param)

    return ", ".join(typed)


def annotate(source: str) -> str:
    """Adiciona `: Any` em parâmetros/campos e `-> Any` em retornos ausentes."""
    lines: list[str] = []

    for line in source.splitlines():
        indent = line[: len(line) - len(line.lstrip())]
        body = line[len(indent) :]

        match = re.match(r"fn\s+(\w+)\s*\(([^)]*)\)(\s*)(.*)$", body)
        if match is not None:
            name, params, _space, tail = match.groups()
            prefix = f"fn {name}({_typed_params(params)}) "
            if "->" not in tail.split("{", 1)[0]:
                prefix += "-> Any "
            lines.append(indent + prefix + tail)
            continue

        match = re.match(r"([A-Za-z_]\w*)\s*\(([^)]*)\)(\s*)(.*)$", body)
        if (
            match is not None
            and indent
            and match.group(1) not in _CONTROL
            and (match.group(4).startswith("{") or match.group(4).startswith("->"))
        ):
            name, params, _space, tail = match.groups()
            prefix = f"{name}({_typed_params(params)}) "
            if name != "init" and "->" not in tail.split("{", 1)[0]:
                prefix += "-> Any "
            lines.append(indent + prefix + tail)
            continue

        match = re.match(r"(var|val)\s+(\w+)\s*;\s*$", body)
        if match is not None:
            lines.append(f"{indent}{match.group(1)} {match.group(2)}: Any;")
            continue

        match = re.match(r"(var|val)\s+(\w+)\s*=\s*nil\s*$", body)
        if match is not None:
            lines.append(
                f"{indent}{match.group(1)} {match.group(2)}: Any = nil"
            )
            continue

        lines.append(line)

    return "\n".join(lines) + "\n"


def annotate_case(relative: str, source: str) -> str:
    adapted = annotate(source)
    special = _SPECIAL.get(relative)
    return special(adapted) if special is not None else adapted

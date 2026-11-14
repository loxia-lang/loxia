"""Nomes reservados do prelúdio global.

Eles não podem ser redefinidos no escopo global; locais/parâmetros podem sombreá-los
normalmente (decisão do ADR-0016). A lista é compartilhada pelo checker e pelo
interpretador para não divergirem.
"""

from __future__ import annotations

BUILTIN_NAMES = frozenset(
    {
        "chars",
        "charCodeAt",
        "fromCodePoint",
        "join",
        "len",
        "range",
        "repr",
        "str",
        "substr",
        "Int",
        "Float",
        "math",
        "Result",
        "Exception",
        "LoxRuntimeError",
    }
)

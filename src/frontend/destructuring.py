"""Padrões de destructuring (`val (a, (b, c)) = t`).

Padrão de destructuring não é expressão nem statement: é a forma à esquerda do `=` de
`val`/`var`. Por isso não tem `Visitor`; os consumidores recursam com `isinstance` e os
helpers daqui (ordem textual dos nomes, primeiro token para diagnóstico). Não confundir
com os padrões de `match` (`VariantPattern`/`WildcardPattern` em `expr.py`): são
linguagens diferentes. Ver ADR-0069.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.frontend.tokens import Token


@dataclass(frozen=True, eq=False)
class NamePattern:
    """Um nome que recebe o valor naquela posição."""

    name: Token


@dataclass(frozen=True, eq=False)
class TuplePattern:
    """Um grupo `(p1, p2, ...)`; precisa de dois ou mais elementos."""

    elements: list[DestructurePattern]


type DestructurePattern = NamePattern | TuplePattern


def pattern_names(pattern: DestructurePattern) -> list[Token]:
    """Nomes do padrão em ordem textual (esquerda → direita)."""
    if isinstance(pattern, NamePattern):
        return [pattern.name]
    names: list[Token] = []
    for element in pattern.elements:
        names.extend(pattern_names(element))
    return names


def first_token(pattern: DestructurePattern) -> Token:
    """Token usado em mensagens de erro do padrão (o primeiro à esquerda)."""
    if isinstance(pattern, NamePattern):
        return pattern.name
    return first_token(pattern.elements[0])

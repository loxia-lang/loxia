# SPDX-License-Identifier: MIT OR Apache-2.0
"""Política de erro da stdlib ([ADR-0135](../docs/adr/0135-politica-de-erro.md)).

O ADR fixa três categorias e uma lei: falha esperada devolve `Result`; só os módulos cujo
contrato *é* falhar (`asserts`, `contracts`, `test`, `property`) podem lançar, e cada um tem
um orçamento que **só diminui**. Sem este teste, a regra volta a ser prosa: um módulo novo
passa a lançar e ninguém percebe até a auditoria seguinte.

O orçamento é o estado da migração (M2-M4 do ADR), não uma permissão permanente. Ao migrar
um `raise` para `Result`, baixe o número aqui no mesmo commit; ao zerar um módulo, remova a
entrada — `test_budget_has_no_dead_entries` exige a tabela exata.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STD = ROOT / "std"

# §3 do ADR-0135: o contrato desses módulos é falhar.
BY_NATURE: frozenset[str] = frozenset({"asserts", "contracts", "test", "property"})

# Estado atual (2026-11-23, ADR-0135): módulo -> teto de comandos `raise`.
RAISE_BUDGET: dict[str, int] = {
    "asserts": 4,
    "bytes": 2,
    "cli": 8,
    "contracts": 3,
    "csv": 4,
    "fmt": 9,
    "framing": 1,
    "json": 28,
    "numeric": 5,
    "property": 5,
    "rand": 2,
    "test": 13,
    "timex": 2,
}

_RAISE = re.compile(r"^\s*raise\b")


def raises_by_module() -> dict[str, int]:
    """Conta comandos `raise` por módulo de `std/` (ignora comentários e strings)."""
    counts: dict[str, int] = {}
    for path in sorted(STD.glob("*.lx")):
        total = sum(
            1 for line in path.read_text(encoding="utf-8").splitlines() if _RAISE.match(line)
        )
        if total:
            counts[path.stem] = total
    return counts


def test_no_module_outside_the_allowlist_raises() -> None:
    found = raises_by_module()
    outside = set(found) - set(RAISE_BUDGET)
    assert not outside, (
        f"módulos fora da allowlist do ADR-0135 lançam: {sorted(outside)}. "
        "Falha esperada devolve `Result`; se for defeito ou fluxo do usuário, justifique no ADR."
    )


def test_nature_modules_are_declared() -> None:
    assert BY_NATURE.issubset(RAISE_BUDGET), (
        "os quatro módulos de natureza precisam estar na tabela"
    )
    for module in BY_NATURE:
        assert module in raises_by_module(), (
            f"std/{module}.lx não lança mais; atualize a allowlist do ADR-0135"
        )


def test_raise_budget_only_shrinks() -> None:
    for module, count in raises_by_module().items():
        budget = RAISE_BUDGET[module]
        assert count <= budget, (
            f"std/{module}.lx tem {count} `raise` (orçamento {budget}). "
            "ADR-0135: falha esperada vira `Result`; o número só desce."
        )


def test_budget_has_no_dead_entries() -> None:
    assert set(RAISE_BUDGET) == set(raises_by_module()), (
        "a tabela RAISE_BUDGET tem que refletir a realidade: remova entradas de módulos que "
        "zeraram e adicione as que passaram a lançar (com justificativa no ADR-0135)"
    )


# --- Casca `T?` (ADR-0135, seção "Casca T? — regra determinística") -------------

_FUNCTION = re.compile(
    r"^fn\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[[^\]]*\])?\s*\((?:.*?)\)\s*->\s*([^{]+?)\s*\{",
    re.MULTILINE | re.DOTALL,
)

# Auditoria do ADR-0135: módulo -> {função: decisão}.
#   "shell"        — ausência é a resposta inteira; `??`/`if nil` resolve, sem irmã.
#   "shell+result" — casca ergonômica; a irmã `<nome>Result` carrega o detalhe (ou dívida).
#   "private"      — helper `_x`, fora da regra porque não é API.
T_OPTIONAL: dict[str, dict[str, str]] = {
    "bytes": {
        "readU16be": "shell+result",
        "readU16le": "shell+result",
        "readU32be": "shell+result",
        "readU32le": "shell+result",
        "readU64be": "shell+result",
        "readU64le": "shell+result",
    },
    "cli": {"option": "shell", "positional": "shell"},
    "convert": {
        "toInt": "shell",
        "toFloat": "shell",
        "toBool": "shell",
        "base64Decode": "shell+result",
        "hexDecode": "shell+result",
        "_utf8Text": "private",
    },
    "csv": {"parse": "shell+result"},
    "framing": {"readStdin": "shell", "_contentLength": "private"},
    "io": {"readLine": "shell", "prompt": "shell"},
    "iter": {"find": "shell"},
    "json": {"error": "shell"},
    "jsonrpc": {"methodOf": "shell", "errorOf": "shell"},
    "lists": {
        "first": "shell",
        "last": "shell",
        "find": "shell",
        "reduce": "shell",
        "min": "shell",
        "max": "shell",
    },
    "numeric": {
        "mean": "shell",
        "median": "shell",
        "mode": "shell",
        "variance": "shell",
        "stddev": "shell",
        "fromBase": "shell",
    },
    "results": {"errorOf": "shell", "toOptional": "shell"},
    "timex": {"parseIso": "shell+result", "_parseOffset": "private", "_digits": "private"},
}

# Irmãs `Result` que faltam criar (M4 do ADR-0135). Vazio: as 10 cascas têm irmã.
SIBLING_DEBT: frozenset[str] = frozenset()


def optional_returns() -> dict[str, dict[str, str]]:
    """Funções de `std/` cujo tipo de retorno termina em `?`, por módulo."""
    found: dict[str, dict[str, str]] = {}
    for path in sorted(STD.glob("*.lx")):
        text = path.read_text(encoding="utf-8")
        for match in _FUNCTION.finditer(text):
            returned = " ".join(match.group(2).split())
            if returned.endswith("?"):
                found.setdefault(path.stem, {})[match.group(1)] = returned
    return found


def test_optional_returns_match_the_adr_table() -> None:
    found = {module: set(names) for module, names in optional_returns().items()}
    expected = {module: set(names) for module, names in T_OPTIONAL.items()}
    assert found == expected, (
        "a tabela T_OPTIONAL tem que refletir `std/`: toda casca `T?` nova entra no ADR-0135 "
        f"(a mais: {sorted(set(found) - set(expected))}, a menos: {sorted(set(expected) - set(found))})"
    )


def test_shell_with_sibling_has_result_or_debt() -> None:
    for module, entries in T_OPTIONAL.items():
        text = (STD / f"{module}.lx").read_text(encoding="utf-8")
        for name, decision in entries.items():
            if decision != "shell+result":
                continue
            sibling = re.search(rf"\bfn\s+{re.escape(name)}Result\b", text) is not None
            key = f"{module}.{name}"
            if sibling:
                assert key not in SIBLING_DEBT, (
                    f"{key} já tem irmã `{name}Result`; remova a dívida em SIBLING_DEBT"
                )
            else:
                assert key in SIBLING_DEBT, (
                    f"{key} é casca com detalhe: crie `{name}Result` ou declare a dívida no ADR-0135"
                )


def test_private_optional_helpers_stay_private() -> None:
    for module, entries in T_OPTIONAL.items():
        for name, decision in entries.items():
            assert (decision == "private") == name.startswith("_"), (
                f"{module}.{name}: decisão `{decision}` incompatível com o prefixo do nome"
            )


def test_sibling_debt_only_shrinks() -> None:
    assert len(SIBLING_DEBT) == 0, "a dívida de irmãs `Result` acabou (M4 do ADR-0135)"
    for key in SIBLING_DEBT:
        module, _, name = key.partition(".")
        assert T_OPTIONAL.get(module, {}).get(name) == "shell+result", (
            f"{key} não é casca com irmã; remova de SIBLING_DEBT"
        )

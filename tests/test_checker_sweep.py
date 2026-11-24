# SPDX-License-Identifier: MIT OR Apache-2.0
"""Gate do ADR-0141: um `--check` limpo não pode esconder erro de tipo do interpretador.

Para cada caso golden que espera erro de runtime, se o `--check` está limpo, o
interpretador não pode levantar um dos erros de tipo (`R1000`/`R1001`/`R1005`/`R1006`),
exceto os casos dependentes de valor da allow-list. Casos com `# requires:` (capacidade
externa) ficam fora: o desfecho deles depende do host/toolchain, não do checker.
"""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from loxia.engine import Loxia
from loxia_core.diagnostics.codes import Code
from tests.runner import CASES_DIR, ROOT, parse_expectations, requirements

TYPE_ERROR_CODES = frozenset(
    {Code.RUNTIME_ERROR, Code.RUNTIME_NOT_CALLABLE, Code.RUNTIME_ARITY, Code.RUNTIME_OPERANDS}
)

# Erros que dependem do valor, não do tipo: o checker não os promete.
ALLOWED: dict[str, Code] = {
    "tests/cases/bytes/bytes_from_list_error_site.lx": Code.RUNTIME_ERROR,
    "tests/cases/errors/negative_int_exponent.lx": Code.RUNTIME_OPERANDS,
    "tests/cases/errors/pow_invalid_domain.lx": Code.RUNTIME_OPERANDS,
    "tests/cases/errors/range_step_zero.lx": Code.RUNTIME_ERROR,
    "tests/cases/errors/shift_count.lx": Code.RUNTIME_OPERANDS,
}


def _display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _check_is_clean(path: Path, source: str) -> bool:
    display = _display(path)
    lox = Loxia(max_errors=0)
    lox.use_file(display, module_root=path.resolve().parent)
    return lox.check(source, emit=False) == 0


def test_a_clean_check_never_hides_a_type_error() -> None:
    checked = 0
    observed: dict[str, set[Code]] = {}
    offenders: list[tuple[str, list[str]]] = []

    for path in sorted(CASES_DIR.rglob("*.lx")):
        source = path.read_text(encoding="utf-8")
        expectations = parse_expectations(source)
        if expectations.error is None or expectations.exit_code != 70:
            continue
        if requirements(source):
            continue
        if not _check_is_clean(path, source):
            continue
        checked += 1
        display = _display(path)
        runner = Loxia(max_errors=0)
        runner.use_file(display, module_root=path.resolve().parent)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            runner.run(source)
        codes = {
            item.code
            for item in runner.reporter.batch().diagnostics
            if item.code in TYPE_ERROR_CODES
        }
        if not codes:
            continue
        if display in ALLOWED:
            observed[display] = codes
        else:
            offenders.append((display, sorted(code.name for code in codes)))

    # A varredura não pode virar vazia por um filtro errado.
    assert checked >= 20, checked
    assert offenders == [], offenders
    assert observed == {path: {code} for path, code in ALLOWED.items()}, observed

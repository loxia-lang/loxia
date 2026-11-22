# SPDX-License-Identifier: MIT OR Apache-2.0
"""Roda a suíte oficial do Crafting Interpreters (caps. 10-13) adaptada.

Os `.lx` oficiais ficam em `tests/official/cases/` sem alteração. Aqui:
- `fun` → `fn` e comentários `//` → `#`;
- campos atribuídos via `this.x =` são declarados como `var x = nil` (ADR-0009);
- `clock` (removido da 1.0, ADR-0026) é trocado por `len`, que também imprime
  `<native fn>`;
- testes que criam campos por fora (pasta `field/` ou `obj.x =`) são `xfail`;
- expectativas oficiais são traduzidas para stdout/exit codes do nosso CLI.
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from tests.inprocess import Result, run_cli

CASES = Path(__file__).resolve().parent / "official" / "cases"

OUTPUT_RE = re.compile(r"//\s*expect:\s?(.*)")
RUNTIME_RE = re.compile(r"//\s*expect runtime error:\s*(.+)")
ERROR_LINE_RE = re.compile(r"//\s*\[(?:(java|c)\s+)?line\s+\d+\]\s*(Error.*)")
ERROR_DIRECT_RE = re.compile(r"//\s*(Error.*)")
NONTEST_RE = re.compile(r"//\s*nontest")
SNIPPET_LINE = re.compile(r"^\s*\d+ \|")

CLASS_RE = re.compile(r"\bclass\s+(\w+)(?:\s*\(\s*(\w+)\s*\))?\s*\{")
THIS_FIELD_RE = re.compile(r"\bthis\.(\w+)\s*=")
DECLARED_RE = re.compile(r"\b(?:var|val)\s+(\w+)")

DYNAMIC_FIELD_TESTS = {
    "field/call_function_field.lx",
    "field/call_nonfunction_field.lx",
    "field/get_and_set_method.lx",
    "field/many.lx",
    "field/method_binds_this.lx",
    "field/on_instance.lx",
    "field/set_evaluation_order.lx",
}


@dataclass(frozen=True)
class Expectations:
    stdout: list[str]
    compile_errors: list[str] = field(default_factory=list)
    runtime_error: str | None = None


@dataclass
class ClassInfo:
    name: str
    superclass: str | None
    open_index: int
    fields: set[str]
    declared: set[str]


def _message_only(expected: str) -> str:
    """Mensagem do livro, sem o prefixo antigo `Error [at 'x']:`.

    O renderizador do ADR-0075 troca `[line N] Error at 'x':` por
    `arquivo:linha:col: error[CODE]:`; o texto que o harness do livro compara é só a
    mensagem. Isto mantém a adaptação fiel ao critério do livro (mensagem contida).
    """
    if expected.startswith("Error at "):
        _, separator, rest = expected.partition(": ")
        return rest if separator else expected
    if expected.startswith("Error: "):
        return expected[len("Error: ") :]
    return expected


def parse_expectations(source: str) -> Expectations:
    stdout: list[str] = []
    compile_errors: list[str] = []
    runtime_error: str | None = None

    for line in source.splitlines():
        match = RUNTIME_RE.search(line)
        if match is not None:
            runtime_error = match.group(1).rstrip()
            continue

        match = OUTPUT_RE.search(line)
        if match is not None:
            stdout.append(match.group(1).rstrip("\r"))
            continue

        match = ERROR_LINE_RE.search(line)
        if match is not None:
            if match.group(1) != "c":
                compile_errors.append(_message_only(match.group(2).rstrip()))
            continue

        match = ERROR_DIRECT_RE.search(line)
        if match is not None:
            compile_errors.append(_message_only(match.group(1).rstrip()))

    return Expectations(stdout, compile_errors, runtime_error)


def _matching_brace(source: str, open_index: int) -> int | None:
    depth = 0
    index = open_index
    in_string = False

    while index < len(source):
        char = source[index]

        if in_string:
            if char == '"':
                in_string = False
            index += 1
            continue

        if char == '"':
            in_string = True
        elif char == "#":
            newline = source.find("\n", index)
            index = len(source) if newline == -1 else newline
            continue
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index

        index += 1

    return None


def _declare_this_fields(source: str) -> str:
    classes: list[ClassInfo] = []

    for match in CLASS_RE.finditer(source):
        open_index = match.end() - 1
        close_index = _matching_brace(source, open_index)
        if close_index is None:
            continue

        body = source[open_index + 1 : close_index]
        classes.append(
            ClassInfo(
                name=match.group(1),
                superclass=match.group(2),
                open_index=open_index,
                fields=set(THIS_FIELD_RE.findall(body)),
                declared=set(DECLARED_RE.findall(body)),
            )
        )

    by_name = {info.name: info for info in classes}

    def inherited_fields(name: str) -> set[str]:
        result: set[str] = set()
        current = by_name.get(name)
        seen: set[str] = set()
        while current is not None:
            parent = current.superclass
            if parent is None or parent in seen:
                break
            seen.add(parent)
            parent_info = by_name.get(parent)
            if parent_info is None:
                break
            result.update(parent_info.fields)
            current = parent_info

        return result

    insertions: list[tuple[int, str]] = []
    for info in classes:
        inherited = inherited_fields(info.name)
        additions = sorted(info.fields - info.declared - inherited)
        if not additions:
            continue

        declarations = "".join(f"  var {name} = nil\n" for name in additions)
        insertions.append((info.open_index + 1, "\n" + declarations))

    for index, text in sorted(insertions, reverse=True):
        source = source[:index] + text + source[index:]

    return source


def adapt_source(source: str) -> str:
    adapted = source.replace("//", "#")
    adapted = re.sub(r"\bfun\b", "fn", adapted)
    adapted = re.sub(r"\bclock\b", "len", adapted)
    adapted = re.sub(r"\bclass\s+(\w+)\s*<\s*(\w+)", r"class \1(\2)", adapted)
    return _declare_this_fields(adapted)


def _marks_for(path: Path, source: str) -> list[pytest.MarkDecorator]:
    marks: list[pytest.MarkDecorator] = []
    relative = str(path.relative_to(CASES))

    if relative in DYNAMIC_FIELD_TESTS:
        marks.append(
            pytest.mark.xfail(
                strict=False,
                reason="campos dinâmicos por fora: divergência do ADR-0009",
            )
        )

    if re.search(r"\bclass\s+\w+\s*<\s*\(", source):
        marks.append(
            pytest.mark.xfail(
                strict=False,
                reason="sintaxe antiga de superclasse (`<`) testada de propósito",
            )
        )

    return marks


def _cases() -> list[pytest.ParameterSet]:
    cases: list[pytest.ParameterSet] = []

    for path in sorted(CASES.rglob("*.lx")):
        source = path.read_text(encoding="utf-8")
        if NONTEST_RE.search(source):
            continue

        cases.append(
            pytest.param(
                path,
                id=str(path.relative_to(CASES)),
                marks=_marks_for(path, source),
            )
        )

    return cases


CASES_PARAMS = _cases()


def _execute(path: Path) -> Result:
    source = path.read_text(encoding="utf-8")
    adapted = adapt_source(source)

    with tempfile.NamedTemporaryFile("w", suffix=".lx", encoding="utf-8", delete=False) as file:
        file.write(adapted)
        temporary = Path(file.name)

    try:
        return run_cli(str(temporary))
    finally:
        temporary.unlink(missing_ok=True)


def _without_snippet(stderr: str) -> str:
    """Remove as linhas do trecho de código antes de casar mensagens.

    O `# expect`/`// expect` pode estar na mesma linha do código; o trecho do
    renderizador human não pode virar falso positivo (ADR-0075).
    """
    return "\n".join(line for line in stderr.splitlines() if not SNIPPET_LINE.match(line))


@pytest.mark.parametrize("path", CASES_PARAMS)
def test_official_case(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    expectations = parse_expectations(source)
    result = _execute(path)
    stdout = result.stdout.splitlines()

    if expectations.runtime_error is not None:
        assert result.returncode == 70, (
            f"esperado exit 70, obtido {result.returncode}\nstderr:\n{result.stderr}"
        )
        # O cabeçalho `arquivo:linha:col: error[CODIGO]:` antecede a mensagem; o
        # critério do livro é a mensagem contida no stderr (ADR-0075, fase 2).
        assert expectations.runtime_error in result.stderr, (
            f"runtime error esperado: {expectations.runtime_error!r}\nstderr:\n{result.stderr}"
        )
    elif expectations.compile_errors:
        assert result.returncode == 65, (
            f"esperado exit 65, obtido {result.returncode}\nstderr:\n{result.stderr}"
        )
        diagnostics_only = _without_snippet(result.stderr)
        for expected in expectations.compile_errors:
            assert expected in diagnostics_only, (
                f"erro esperado ausente: {expected!r}\nstderr:\n{result.stderr}"
            )
    else:
        assert result.returncode == 0, (
            f"esperado exit 0, obtido {result.returncode}\nstderr:\n{result.stderr}"
        )

    assert stdout == expectations.stdout, (
        f"stdout esperado: {expectations.stdout!r}\nobtido: {stdout!r}"
    )

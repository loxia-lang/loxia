"""Portão do invariante I3 (ADR-0014): mesma entrada ⇒ mesmos bytes.

A garantia de determinismo observável é parte da identidade da linguagem — não é
"nice to have". Este teste roda o CLI de verdade em subprocesso, com
`PYTHONHASHSEED` diferentes, e exige **igualdade byte a byte** de stdout, stderr e
exit code. Qualquer vazamento de ordem de hash, endereço, timestamp, PID ou
caminho absoluto quebra aqui, e não no usuário.

Ver `docs/spec/garantias.md` (I3) e `docs/adr/0014-identidade-e-invariantes.md`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
TIMEOUT_SECONDS = 30

# Caminhos relativos: se um caminho absoluto vazar para a saída, ele aparece aqui.
CASES = [
    "exemplos/classes.lox",
    "exemplos/closures.lox",
    "exemplos/fib.lox",
    "exemplos/fizzbuzz.lox",
    "exemplos/primos.lox",
    "exemplos/quicksort.lox",
    "tests/cases/class_fields.lox",
    "tests/cases/for_in.lox",
    "tests/cases/inheritance.lox",
    "tests/cases/interpolation.lox",
    "tests/cases/list_iteration.lox",
    "tests/cases/list_stringify.lox",
    "tests/cases/map_iteration.lox",
    "tests/cases/map_stringify.lox",
    "tests/cases/nil_aware.lox",
    "tests/cases/str_repr.lox",
    "tests/cases/strings.lox",
    "tests/cases/typed_functions.lox",
    "tests/cases/errors/undefined_variable.lox",
    "tests/cases/errors/type_mismatch_add.lox",
    "tests/cases/errors/division_by_zero.lox",
]

# Sementes diferentes: ordem de `set`/`dict` sobre strings muda com o hash.
SEEDS = ("0", "12345")

VOLATILE = [
    (re.compile(r"0x[0-9a-fA-F]{6,}"), "endereço de memória"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"), "UUID"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}"), "timestamp ISO"),
    (re.compile(r"\b(?:pid|PID)\s*[=:]\s*\d+"), "PID"),
]


def run_cli(path: str, seed: str, *flags: str) -> subprocess.CompletedProcess[bytes]:
    env = dict(os.environ, PYTHONHASHSEED=seed)
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *flags, path],
        cwd=ROOT,
        env=env,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def assert_deterministic(path: str, *flags: str) -> subprocess.CompletedProcess[bytes]:
    first = run_cli(path, SEEDS[0], *flags)
    second = run_cli(path, SEEDS[1], *flags)

    assert first.returncode == second.returncode, (
        f"{path} {flags}: exit code mudou entre execuções "
        f"({first.returncode} vs {second.returncode})"
    )
    assert first.stdout == second.stdout, (
        f"{path} {flags}: stdout não é determinístico\n"
        f"seed=0:     {first.stdout!r}\nseed=12345: {second.stdout!r}"
    )
    assert first.stderr == second.stderr, (
        f"{path} {flags}: stderr não é determinístico\n"
        f"seed=0:     {first.stderr!r}\nseed=12345: {second.stderr!r}"
    )

    return first


def assert_no_volatile_output(path: str, result: subprocess.CompletedProcess[bytes]) -> None:
    text = (result.stdout + result.stderr).decode("utf-8", errors="replace")

    for pattern, kind in VOLATILE:
        assert not pattern.search(text), f"{path}: {kind} vazou para a saída:\n{text}"

    assert str(ROOT) not in text, f"{path}: caminho absoluto vazou para a saída:\n{text}"


@pytest.mark.parametrize("path", CASES)
def test_execution_is_byte_identical_across_hash_seeds(path: str) -> None:
    result = assert_deterministic(path)
    assert_no_volatile_output(path, result)


@pytest.mark.parametrize("path", CASES)
def test_check_output_is_deterministic(path: str) -> None:
    result = assert_deterministic(path, "--check")
    assert_no_volatile_output(path, result)


@pytest.mark.parametrize("path", ["tests/cases/typed_functions.lox", "exemplos/classes.lox"])
def test_dump_ast_is_deterministic(path: str) -> None:
    result = assert_deterministic(path, "--dump-ast")
    assert_no_volatile_output(path, result)


def test_same_script_twice_is_byte_identical_even_with_different_cwd() -> None:
    """O caminho absoluto de execução não pode influenciar o resultado (I3)."""
    path = "exemplos/fib.lox"
    from_root = run_cli(path, SEEDS[0])

    process = subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(ROOT / path)],
        cwd=ROOT / "exemplos",
        env=dict(os.environ, PYTHONHASHSEED=SEEDS[0]),
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )

    assert (process.returncode, process.stdout) == (from_root.returncode, from_root.stdout)
    assert str(ROOT) not in (process.stdout + process.stderr).decode("utf-8", errors="replace")


DIAGNOSTIC_CASES = [
    "tests/cases/errors/redeclaration.lox",
    "tests/cases/errors/undefined_variable.lox",
]


@pytest.mark.parametrize("path", DIAGNOSTIC_CASES)
def test_short_diagnostics_are_deterministic(path: str) -> None:
    result = assert_deterministic(path, "--error-format=short")
    assert_no_volatile_output(path, result)


@pytest.mark.parametrize("path", DIAGNOSTIC_CASES)
def test_json_diagnostics_are_deterministic_on_check(path: str) -> None:
    result = assert_deterministic(path, "--check", "--error-format=json")
    assert_no_volatile_output(path, result)


@pytest.mark.parametrize("path", ["tests/cases/errors/undefined_variable.lox"])
def test_json_runtime_diagnostics_are_deterministic(path: str) -> None:
    result = assert_deterministic(path, "--error-format=json")
    assert_no_volatile_output(path, result)


def test_color_always_is_byte_identical() -> None:
    path = "tests/cases/errors/redeclaration.lox"
    result = assert_deterministic(path, "--color=always")
    assert "\x1b[" in result.stderr.decode("utf-8")

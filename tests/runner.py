"""Runner dos casos golden: um `.lox` por arquivo, expectativas em comentários.

Formato aceito (qualquer posição no arquivo, na ordem em que aparecem):

    print 1 + 2;                       // expect: 3
    // expect runtime error: Undefined variable 'a'.
    // expect error: Expect ';' after value.
    // expect exit: 65

O runner executa `main.py` como subprocesso para testar o CLI de verdade
(exit codes e stderr incluídos), não só a AST.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = Path(__file__).resolve().parent / "cases"
ENTRYPOINT = ROOT / "main.py"
TIMEOUT_SECONDS = 20

EXIT_SYNTAX_ERROR = 65
EXIT_RUNTIME_ERROR = 70


@dataclass(frozen=True)
class Expectations:
    stdout: list[str]
    error: str | None
    exit_code: int


@dataclass(frozen=True)
class Executed:
    stdout: list[str]
    stderr: str
    exit_code: int


def parse_expectations(source: str) -> Expectations:
    stdout: list[str] = []
    error: str | None = None
    exit_code = 0

    for line in source.splitlines():
        marker = line.find("//")
        if marker == -1:
            continue

        stripped = line[marker:].strip()

        if stripped.startswith("// expect runtime error:"):
            error = stripped.split(":", 1)[1].strip()
            exit_code = EXIT_RUNTIME_ERROR
        elif stripped.startswith("// expect error:"):
            error = stripped.split(":", 1)[1].strip()
            exit_code = EXIT_SYNTAX_ERROR
        elif stripped.startswith("// expect exit:"):
            exit_code = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("// expect:"):
            stdout.append(stripped[len("// expect:") :].strip())

    return Expectations(stdout=stdout, error=error, exit_code=exit_code)


def execute(path: Path) -> Executed:
    process = subprocess.run(
        [sys.executable, str(ENTRYPOINT), str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    return Executed(
        stdout=process.stdout.splitlines(),
        stderr=process.stderr,
        exit_code=process.returncode,
    )


def check_case(path: Path) -> list[str]:
    """Retorna a lista de divergências (vazia = caso passou)."""
    expectations = parse_expectations(path.read_text(encoding="utf-8"))
    executed = execute(path)
    problems: list[str] = []

    if executed.stdout != expectations.stdout:
        problems.append(
            f"stdout: esperado {expectations.stdout!r}, obtido {executed.stdout!r}"
        )

    if expectations.error is not None:
        if expectations.error not in executed.stderr:
            problems.append(
                f"stderr: esperado conter {expectations.error!r}, obtido {executed.stderr!r}"
            )
    elif executed.stderr.strip():
        problems.append(f"stderr deveria estar vazio, obtido {executed.stderr!r}")

    if executed.exit_code != expectations.exit_code:
        problems.append(
            f"exit code: esperado {expectations.exit_code}, obtido {executed.exit_code}"
        )

    return problems


def discover_cases() -> list[Path]:
    return sorted(CASES_DIR.rglob("*.lox"))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="tests.runner", description="Roda os casos golden (sem pytest)."
    )
    parser.add_argument("filtro", nargs="?", help="substring no caminho do caso")
    args = parser.parse_args(argv)

    cases = [
        case
        for case in discover_cases()
        if args.filtro is None or args.filtro in str(case.relative_to(CASES_DIR))
    ]
    if not cases:
        print(f"nenhum caso casa com {args.filtro!r}", file=sys.stderr)
        return 2

    failures = 0

    for case in cases:
        problems = check_case(case)
        name = case.relative_to(CASES_DIR)
        if problems:
            failures += 1
            print(f"FAIL {name}")
            for problem in problems:
                print(f"     {problem}")
        else:
            print(f"ok   {name}")

    print(f"\n{len(cases) - failures}/{len(cases)} casos passaram")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

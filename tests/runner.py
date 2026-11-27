# SPDX-License-Identifier: MIT OR Apache-2.0
"""Runner dos casos golden: um `.lx` por arquivo, expectativas em comentários.

Formato aceito (qualquer posição no arquivo, na ordem em que aparecem):

    print(1 + 2);                       # expect: 3
    # expect runtime error: Undefined variable 'a'.
    # expect error: Expect ';' after expression.
    # expect exit: 65

O runner executa o CLI (`loxia.cli.main`) para testar a saída e o exit code de
verdade. Por padrão roda no próprio processo do pytest — o import é pago uma vez e
cada caso custa poucos milissegundos. Casos com `# requires: rust` (motor nativo)
rodam em subprocesso, porque o motor guarda handles no processo (#239); os demais
continuam in-process. `LOX_GOLDEN_SUBPROCESS=1` restaura um processo por caso (boot do
Python incluído) para depurar isolamento.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from tests.inprocess import Result, run_cli

ROOT = Path(__file__).resolve().parents[1]
CASES_DIR = Path(__file__).resolve().parent / "cases"
ENTRYPOINT = ROOT / "main.py"
TIMEOUT_SECONDS = 20
# O caminho rápido executa o CLI no processo do pytest (sem boot de Python por
# caso). `LOX_GOLDEN_SUBPROCESS=1` força o caminho antigo, útil para depurar uma
# diferença de comportamento que só aparece em processo separado.
USE_SUBPROCESS = os.environ.get("LOX_GOLDEN_SUBPROCESS") == "1"
# Casos que compilam o crate na primeira execução precisam de folga.
REQUIREMENT_TIMEOUTS = {"rust": 180}
REQUIRES_LINE = re.compile(r"^#\s*requires:\s*([a-z0-9_-]+)\s*$")

EXIT_SYNTAX_ERROR = 65
EXIT_RUNTIME_ERROR = 70

# Linhas do trecho de código do renderizador human (ex.: `3 |   var a = 2;`).
# Elas não participam da checagem de mensagem: o comentário `# expect ...` pode
# estar na mesma linha do código e criaria um falso positivo.
SNIPPET_LINE = re.compile(r"^\s*\d+ \|")


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
        marker = line.find("#")
        if marker == -1:
            continue

        stripped = line[marker:].strip()

        if stripped.startswith("# expect runtime error:"):
            error = stripped.split(":", 1)[1].strip()
            exit_code = EXIT_RUNTIME_ERROR
        elif stripped.startswith("# expect error:"):
            error = stripped.split(":", 1)[1].strip()
            exit_code = EXIT_SYNTAX_ERROR
        elif stripped.startswith("# expect exit:"):
            exit_code = int(stripped.split(":", 1)[1].strip())
        elif stripped.startswith("# expect:"):
            stdout.append(stripped[len("# expect:") :].strip())

    return Expectations(stdout=stdout, error=error, exit_code=exit_code)


def requirements(source: str) -> set[str]:
    """Capacidades externas exigidas no bloco de comentários do topo.

    A diretiva é uma linha própria, minúscula (`# requires: rust`). Qualquer
    comentário desse bloco que mencione `requires` fora da forma canônica falha
    alto, para um typo não virar "roda sem a capacidade".
    """
    found: set[str] = set()
    for line in source.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("#"):
            break
        match = REQUIRES_LINE.match(stripped)
        if match is not None:
            found.add(match.group(1))
        elif "requires" in stripped.lower():
            raise ValueError(f"malformed 'requires' directive: {stripped!r}")
    return found


def timeout_for(source: str) -> int:
    """Timeout do caso: o maior exigido pelas capacidades (build frio incluso)."""
    timeout = TIMEOUT_SECONDS
    for requirement in requirements(source):
        timeout = max(timeout, REQUIREMENT_TIMEOUTS.get(requirement, TIMEOUT_SECONDS))
    return timeout


def missing_requirements(path: Path) -> set[str]:
    """Capacidades exigidas que não existem nesta máquina (vazio = roda)."""
    from loxia_core.native_build import cargo_binary

    missing: set[str] = set()
    for requirement in requirements(path.read_text(encoding="utf-8")):
        if requirement == "rust":
            if cargo_binary() is None:
                missing.add(requirement)
        else:
            raise ValueError(f"unknown requirement '{requirement}' in {path}")
    return missing


def _without_snippet(stderr: str) -> str:
    return "\n".join(line for line in stderr.splitlines() if not SNIPPET_LINE.match(line))


def execute(path: Path, timeout: int | None = None) -> Executed:
    # O motor nativo de regex guarda handles no processo (#239): um caso que exige
    # o crate roda em processo novo, como o CLI real, para não herdar handles de
    # outro caso.
    source = path.read_text(encoding="utf-8")
    if timeout is None:
        timeout = timeout_for(source)
    if not USE_SUBPROCESS and "rust" not in requirements(source):
        result: Result = run_cli("--interpret", str(path))
        return Executed(
            stdout=result.stdout.splitlines(),
            stderr=result.stderr,
            exit_code=result.returncode,
        )
    process = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--interpret", str(path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return Executed(
        stdout=process.stdout.splitlines(),
        stderr=process.stderr,
        exit_code=process.returncode,
    )


def check_case(path: Path) -> list[str]:
    """Retorna a lista de divergências (vazia = caso passou)."""
    source = path.read_text(encoding="utf-8")
    expectations = parse_expectations(source)
    executed = execute(path, timeout=timeout_for(source))
    problems: list[str] = []

    if executed.stdout != expectations.stdout:
        problems.append(f"stdout: esperado {expectations.stdout!r}, obtido {executed.stdout!r}")

    diagnostics_only = _without_snippet(executed.stderr)

    if expectations.error is not None:
        if expectations.error not in diagnostics_only:
            problems.append(
                f"stderr: esperado conter {expectations.error!r}, obtido {executed.stderr!r}"
            )
    elif diagnostics_only.strip():
        problems.append(f"stderr deveria estar vazio, obtido {executed.stderr!r}")

    if executed.exit_code != expectations.exit_code:
        problems.append(
            f"exit code: esperado {expectations.exit_code}, obtido {executed.exit_code}"
        )

    return problems


def discover_cases() -> list[Path]:
    return sorted(CASES_DIR.rglob("*.lx"))


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
    skipped = 0

    for case in cases:
        missing = missing_requirements(case)
        if missing:
            skipped += 1
            print(f"skip {case.relative_to(CASES_DIR)} (requer {', '.join(sorted(missing))})")
            continue
        problems = check_case(case)
        name = case.relative_to(CASES_DIR)
        if problems:
            failures += 1
            print(f"FAIL {name}")
            for problem in problems:
                print(f"     {problem}")
        else:
            print(f"ok   {name}")

    total = len(cases) - skipped
    if total == 0:
        print(f"\n0 casos executados ({skipped} pulados)", file=sys.stderr)
        return 2
    print(f"\n{total - failures}/{total} casos passaram ({skipped} pulados)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

# SPDX-License-Identifier: MIT OR Apache-2.0
"""Roda o CLI dentro do processo do pytest, capturando stdout/stderr/exit code.

Os casos golden, a suíte oficial e os testes de paridade só precisam do contrato do
CLI (bytes de saída e exit code), não de um processo novo por caso. Executar
`loxia.cli.main()` aqui paga o import uma vez só e derruba o custo por caso de
~100 ms (boot do Python) para poucos milissegundos.

O que continua em subprocesso: testes que dependem do processo de verdade —
timeout/sinais, `PYTHONHASHSEED` diferente, REPL com stdin real, sandbox e o
backend nativo. Para esses, use `subprocess` como antes.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"


@dataclass(frozen=True)
class Result:
    """Subconjunto de `subprocess.CompletedProcess` que os testes consomem."""

    returncode: int
    stdout: str
    stderr: str


def run_cli(
    *args: str,
    stdin: str = "",
    cwd: Path | None = ROOT,
    env: dict[str, str] | None = None,
) -> Result:
    """Executa o CLI como `main.py` faria, sem criar processo.

    `env` é aplicado ao `os.environ` do processo atual durante a chamada (e
    restaurado depois). Prefira subprocesso quando o teste precisa de ambiente
    isolado de verdade (hash seed, locale, variáveis lidas no import).
    """
    from loxia.cli import main

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = 0
    previous_argv = sys.argv
    previous_stdin = sys.stdin
    previous_cwd = Path.cwd()
    previous_env = dict(os.environ) if env is not None else None

    try:
        if cwd is not None:
            os.chdir(cwd)
        if env is not None:
            os.environ.update(env)
        sys.argv = [str(ENTRYPOINT), *args]
        sys.stdin = io.StringIO(stdin)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                main()
            except SystemExit as exc:
                if exc.code is None:
                    exit_code = 0
                elif isinstance(exc.code, int):
                    exit_code = exc.code
                else:
                    stderr.write(f"{exc.code}\n")
                    exit_code = 1
    finally:
        sys.argv = previous_argv
        sys.stdin = previous_stdin
        os.chdir(previous_cwd)
        if env is not None and previous_env is not None:
            os.environ.clear()
            os.environ.update(previous_env)

    return Result(returncode=exit_code, stdout=stdout.getvalue(), stderr=stderr.getvalue())


def run_interpreted(
    path: str,
    *args: str,
    stdin: str = "",
    cwd: Path | None = ROOT,
) -> Result:
    """Roda um fonte no tree-walk — o oráculo normativo (ADR-0002/ADR-0149).

    Desde o #244 o `run` compila por padrão; os testes de contrato do interpretador
    (golden, suíte oficial, docs, exemplos) pedem o motor explicitamente. Em
    processo ele também funciona com `redirect_stdout`, o que um binário filho não
    respeita.
    """
    return run_cli("--interpret", path, *args, stdin=stdin, cwd=cwd)

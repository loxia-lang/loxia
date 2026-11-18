# SPDX-License-Identifier: MIT OR Apache-2.0
"""Atheris target for the scanner and the parser.

`tests/test_fuzz.py` checks properties of the front-end with generated text; this target
gives the same code coverage-guided fuzzing. The oracle is the same one: any input must
produce a token list and a statement list, never an unhandled exception.

Run it locally with:

    uv run --with atheris python fuzz/fuzz_frontend.py -max_total_time=60

CI runs it on pull requests that touch the front-end and once a week
(`.github/workflows/fuzz.yml`).
"""

from __future__ import annotations

import sys

import atheris

with atheris.instrument_imports():
    from loxia_core.diagnostics.error_reporter import ErrorReporter
    from loxia_core.frontend.parser import Parser
    from loxia_core.frontend.scanner import Scanner


def test_one_input(data: bytes) -> None:
    source = data.decode("utf-8", errors="replace")
    reporter = ErrorReporter()
    tokens = Scanner(source, reporter).scan_tokens()
    statements = Parser(tokens, reporter=reporter).parse()
    assert isinstance(statements, list)


def main() -> None:
    atheris.Setup(sys.argv, test_one_input)
    atheris.Fuzz()


if __name__ == "__main__":
    main()

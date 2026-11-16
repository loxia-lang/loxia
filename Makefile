# Atalhos de desenvolvimento. Requer `uv` (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help

FILE ?=

.PHONY: help run test test-fast case lint type fmt check check-fast docs-sync stdlib-docs codes primitives grammar docs-fresh hooks bench bench-native baseline

help:
	@echo "make run FILE=exemplos/x.lx   executa um script (sem FILE abre o REPL)"
	@echo "make test                      pytest (suite completa)"
	@echo "make test-fast                 pytest sem os testes nativos (loop local)"
	@echo "make case                      runner golden, sem pytest"
	@echo "make lint                      ruff"
	@echo "make type                      mypy strict"
	@echo "make fmt                       ruff format (primeira vez reformata tudo)"
	@echo "make check                     lint + type + test + docs (gate completo)"
	@echo "make check-fast                lint + type + test-fast + docs (loop local)"
	@echo "make docs-sync                 regenera níveis, catálogo e stdlib"
	@echo "make stdlib-docs               regenera docs/stdlib/"
	@echo "make codes                     regenera o catálogo em docs/spec/erros.md"
	@echo "make primitives                regenera runtime/kernel_gen.h da tabela"
	@echo "make grammar                   regenera a grammar TextMate de editors/"
	@echo "make docs-fresh                relatório de páginas desatualizadas (git)"
	@echo "make hooks                     instala o hook de pre-commit"
	@echo "make bench                     benchmarks vs bench/baseline.json"
	@echo "make bench-native              benchmarks do binário nativo (--emit=exe)"
	@echo "make baseline                  regrava o baseline de performance"

run:
	uv run main.py $(FILE)

test:
	uv run pytest

test-fast:
	uv run pytest -m "not backend"

case:
	uv run python -m tests.runner

lint:
	uv run ruff check .

type:
	uv run mypy

fmt:
	uv run ruff format .

check: lint type test docs-fresh

check-fast: lint type test-fast docs-fresh

docs-sync:
	uv run python docs/_hooks/levels.py --write
	uv run python docs/_hooks/codes.py --write
	uv run python docs/_hooks/stdlib.py --write

stdlib-docs:
	uv run python docs/_hooks/stdlib.py --write

codes:
	uv run python docs/_hooks/codes.py --write

primitives:
	uv run python runtime/gen_kernel.py --write

grammar:
	uv run python editors/build_grammar.py --write

docs-fresh:
	uv run python docs/_hooks/freshness.py --quiet || true

hooks:
	uv run pre-commit install

bench:
	uv run python bench/run.py

bench-native:
	uv run python bench/run.py --native

baseline:
	uv run python bench/run.py --update

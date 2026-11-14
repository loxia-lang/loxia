# Atalhos de desenvolvimento. Requer `uv` (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help

FILE ?=

.PHONY: help run test case lint type fmt check docs-sync codes docs-fresh hooks bench bench-native baseline

help:
	@echo "make run FILE=exemplos/x.lox   executa um script (sem FILE abre o REPL)"
	@echo "make test                      pytest (suite completa)"
	@echo "make case                      runner golden, sem pytest"
	@echo "make lint                      ruff"
	@echo "make type                      mypy strict"
	@echo "make fmt                       ruff format (primeira vez reformata tudo)"
	@echo "make check                     lint + type + test + docs"
	@echo "make docs-sync                 regenera níveis e catálogo de códigos"
	@echo "make codes                     regenera o catálogo em docs/spec/erros.md"
	@echo "make docs-fresh                relatório de páginas desatualizadas (git)"
	@echo "make hooks                     instala o hook de pre-commit"
	@echo "make bench                     benchmarks vs bench/baseline.json"
	@echo "make bench-native              benchmarks do binário nativo (--emit=exe)"
	@echo "make baseline                  regrava o baseline de performance"

run:
	uv run main.py $(FILE)

test:
	uv run pytest

case:
	uv run python -m tests.runner

lint:
	uv run ruff check .

type:
	uv run mypy

fmt:
	uv run ruff format .

check: lint type test docs-fresh

docs-sync:
	uv run python docs/_hooks/levels.py --write
	uv run python docs/_hooks/codes.py --write

codes:
	uv run python docs/_hooks/codes.py --write

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

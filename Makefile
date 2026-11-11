# Atalhos de desenvolvimento. Requer `uv` (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help

FILE ?=

.PHONY: help run test case lint type fmt check bench baseline

help:
	@echo "make run FILE=exemplos/x.lox   executa um script (sem FILE abre o REPL)"
	@echo "make test                      pytest (suite completa)"
	@echo "make case                      runner golden, sem pytest"
	@echo "make lint                      ruff"
	@echo "make type                      mypy strict"
	@echo "make fmt                       ruff format (primeira vez reformata tudo)"
	@echo "make check                     lint + type + test"
	@echo "make bench                     benchmarks vs bench/baseline.json"
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

check: lint type test

bench:
	uv run python bench/run.py

baseline:
	uv run python bench/run.py --update

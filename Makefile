# Atalhos de desenvolvimento. Requer `uv` (https://docs.astral.sh/uv/).
.DEFAULT_GOAL := help

FILE ?=
VERSION ?= 1.0
TAG ?= v1.0.0

.PHONY: help run test test-fast case lint type fmt fmt-check check check-fast coverage coverage-ratchet coverage-update docs-sync docs-index docs-build docs-dev docs-links docs-version docs-i18n-check stdlib-docs codes features primitives grammar grammar-assets docs-fresh hooks bench bench-native baseline fuzz monomorph

help:
	@echo "make run FILE=examples/x.lx   executa um script (sem FILE abre o REPL)"
	@echo "make test                      pytest (suite completa)"
	@echo "make test-fast                 pytest sem os testes nativos (loop local)"
	@echo "make case                      runner golden, sem pytest"
	@echo "make lint                      ruff"
	@echo "make type                      mypy strict"
	@echo "make fmt                       ruff format (aplica)"
	@echo "make fmt-check                 ruff format --check (gate)"
	@echo "make check                     lint + fmt-check + type + test + docs (gate completo)"
	@echo "make check-fast                lint + fmt-check + type + test-fast + docs (loop local)"
	@echo "make coverage                  mede cobertura Python (sem gate; não roda backend)"
	@echo "make coverage-ratchet          mede e falha abaixo dos pisos por arquivo"
	@echo "make coverage-update           sobe os pisos até a cobertura medida"
	@echo "make docs-sync                 regenera níveis, catálogo, stdlib e índice"
	@echo "make docs-index                regenera loxia/_spec/index.json e site/public/llms.txt"
	@echo "make docs-build                build do site Starlight em site/dist"
	@echo "make docs-links                valida links internos do HTML gerado"
	@echo "make docs-dev                  dev server do site (gera o conteúdo antes)"
	@echo "make docs-version VERSION=1.0 TAG=v1.0.0  congela uma referência"
	@echo "make docs-i18n-check          valida translated_from/source"
	@echo "make stdlib-docs               regenera docs/stdlib/"
	@echo "make features                  regenera a matriz/snapshot de cobertura de features"
	@echo "make codes                     regenera o catálogo em docs/spec/erros.md"
	@echo "make primitives                regenera runtime/kernel_gen.h da tabela"
	@echo "make grammar                   regenera a grammar TextMate de editors/grammar/"
	@echo "make grammar-assets            empacota a grammar + SHA256SUMS em dist/ (release)"
	@echo "make docs-fresh                relatório de páginas desatualizadas (git)"
	@echo "make hooks                     instala o hook de pre-commit"
	@echo "make bench                     benchmarks vs bench/baseline.json"
	@echo "make bench-native              benchmarks do binário nativo (--emit=exe)"
	@echo "make monomorph                 mede o orçamento de monomorfização (ADR-0063)"
	@echo "make fuzz                      roda o fuzzing do scanner/parser (hypothesis)"
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

fmt-check:
	uv run ruff format --check .

check: lint fmt-check type test docs-fresh

check-fast: lint fmt-check type test-fast docs-fresh

coverage:
	rm -f .coverage .coverage.*
	uv run coverage run -m pytest -m "not backend and not install" \
		--deselect tests/test_cli.py::test_timeout_exits_124_with_c0001 \
		--deselect tests/test_cli.py::test_timeout_json_lines_emits_c0001
	uv run coverage combine
	uv run coverage report

coverage-ratchet: coverage
	uv run coverage json -o .coverage.json
	uv run python tools/coverage_ratchet.py --check

coverage-update: coverage
	uv run coverage json -o .coverage.json
	uv run python tools/coverage_ratchet.py --update

docs-sync:
	uv run python docs/_hooks/levels.py --write
	uv run python docs/_hooks/codes.py --write
	uv run python docs/_hooks/stdlib.py --write
	uv run python tools/feature_coverage.py --write
	uv run python tools/docs_index.py --write

features:
	uv run python tools/feature_coverage.py --write

docs-index:
	uv run python tools/docs_index.py --write

docs-build: docs-sync
	npm --prefix site run build
	uv run python tools/docs_links.py --strict

docs-dev:
	npm --prefix site run dev

docs-links:
	uv run python tools/docs_links.py --strict

docs-version:
	uv run python tools/docs_versions.py --version $(VERSION) --tag $(TAG)

docs-i18n-check:
	uv run python tools/docs_i18n.py --strict

stdlib-docs:
	uv run python docs/_hooks/stdlib.py --write

codes:
	uv run python docs/_hooks/codes.py --write

primitives:
	uv run python runtime/gen_kernel.py --write

grammar:
	uv run python editors/build_grammar.py --write

grammar-assets:
	uv run python editors/build_grammar.py --assets dist-grammar

docs-fresh:
	uv run python docs/_hooks/freshness.py --quiet || true

hooks:
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	uv run pre-commit install --hook-type pre-push

bench:
	uv run python bench/run.py

bench-native:
	uv run python bench/run.py --native

baseline:
	uv run python bench/run.py --update

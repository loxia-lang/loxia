"""Cobertura mecânica da documentação (inspirado no fluxo do Scrinalia).

O que **bloqueia** (`make check`) é o que é verificável sem julgamento:

- ADR: numeração única e sequencial, título coerente, arquivo no índice, índice sem
  ponteiro quebrado;
- spec: toda página linkada no README, toda página mutável com `sources:`, e todo glob de
  `sources:` casando com arquivo real (pega módulo renomeado/removido);
- CLI: toda flag do `argparse` documentada no README, e nenhuma flag inventada nele;
- nível: o bloco de status do corpus em `garantias.md` é **gerado** do manifesto e não
  pode estar defasado;
- prosa: frases que já foram verdadeiras e hoje mentem são proibidas por lista explícita.

O que **não** bloqueia é o frescor (`docs/_hooks/freshness.py`): página desatualizada é
julgamento humano, registrado em `docs/log.md`. Ver
[ADR-0014](../docs/adr/0014-identidade-e-invariantes.md) e a skill `lox-docs`.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from loxia import __version__
from loxia.cli import COMMANDS, _build_subcommand_parser, build_parser
from loxia_core.frontend.keywords import KEYWORDS
from tests.corpus_manifest import PENDING

ROOT = Path(__file__).resolve().parents[1]
ADR_DIR = ROOT / "docs" / "adr"
ADR_INDEX = ADR_DIR / "README.md"
README = ROOT / "README.md"
SPEC_DIR = ROOT / "docs" / "spec"

ADR_FILE = re.compile(r"^(\d{4})-[a-z0-9.-]+\.md$")
ADR_TITLE = re.compile(r"^# ADR-(\d{4})\b", re.MULTILINE)
ADR_ROW = re.compile(r"\[(\d{4})\]\(([^)]+)\)")

# Módulos/scripts de ferramentas que documentam comandos que não são do CLI do Loxia.
NON_CLI_FLAGS = {
    "--all",
    "--extra",
    "--repeat",
    "--strict",
    "--write",
    "--check",  # também é do CLI, mas aparece em `levels.py --check`
}

STALE_PHRASES = {
    "quando o backend existir": "o backend já existe; o status é o manifesto",
    "enquanto o backend não existe": "o backend já existe",
    "próximo: L5": "o L5 já fechou",
    "L6 na fila": "o L6 já está em andamento",
    "não existem: `break`/`continue`, `switch`, `match`": (
        "`match` existe (ADR-0041); use a lista de não-objetivos do ADR-0066"
    ),
    "funções anônimas (challenge #2 pendente)": "lambdas existem (ADR-0022)",
}

MUTABLE_DOCS = [
    README,
    ROOT / "ESCOPO.md",
    ROOT / "TODO.md",
    ROOT / "IDEIAS.md",
    ROOT / "docs" / "decisoes.md",
    *sorted(SPEC_DIR.glob("*.md")),
]


def _adr_files() -> list[Path]:
    return sorted(path for path in ADR_DIR.glob("*.md") if ADR_FILE.match(path.name))


def _adr_number(path: Path) -> str:
    match = ADR_FILE.match(path.name)
    assert match is not None
    return match.group(1)


def test_scoreboard_de_keywords_bate_com_keywords() -> None:
    adr = (ADR_DIR / "0066-orcamento-e-gate-sintatico.md").read_text(encoding="utf-8")
    line = re.search(r"^\| palavras-chave \| (\d+) \|$", adr, re.MULTILINE)

    assert line is not None, "ADR-0066 sem a linha do scoreboard de palavras-chave"

    # A regra está no próprio ADR: literais e reservas sem sintaxe não contam.
    excluded = {"true", "false", "nil", "async", "await"}
    expected = len(KEYWORDS) - len(excluded)
    assert int(line.group(1)) == expected, (
        f"scoreboard diz {line.group(1)}, KEYWORDS dá {expected}"
    )


def test_adr_numeracao_unica_sequencial_e_titulo_coerente() -> None:
    numbers = [_adr_number(path) for path in _adr_files()]

    assert len(numbers) == len(set(numbers)), "número de ADR duplicado"
    assert numbers == [f"{n:04d}" for n in range(1, len(numbers) + 1)], (
        "numeração de ADR com lacuna ou fora de ordem"
    )

    for path in _adr_files():
        title = ADR_TITLE.search(path.read_text(encoding="utf-8"))
        assert title is not None, f"{path.name}: sem título `# ADR-NNNN`"
        assert title.group(1) == _adr_number(path), (
            f"{path.name}: título diz ADR-{title.group(1)}"
        )


def test_todo_adr_esta_no_indice() -> None:
    index = ADR_INDEX.read_text(encoding="utf-8")

    for path in _adr_files():
        assert f"({path.name})" in index, f"{path.name} não está em docs/adr/README.md"


def test_indice_de_adr_aponta_para_o_arquivo_certo() -> None:
    for number, target in ADR_ROW.findall(ADR_INDEX.read_text(encoding="utf-8")):
        path = ADR_DIR / target
        assert path.exists(), f"índice aponta para {target}, que não existe"
        assert _adr_number(path) == number, (
            f"índice diz {number} mas {target} é {_adr_number(path)}"
        )


def test_paginas_de_spec_estao_linkadas_no_readme() -> None:
    readme = README.read_text(encoding="utf-8")

    for page in sorted(SPEC_DIR.glob("*.md")):
        assert f"docs/spec/{page.name}" in readme, (
            f"{page.name} não está linkada no README"
        )


def test_paginas_mutaveis_declaram_sources() -> None:
    for page in [*sorted(SPEC_DIR.glob("*.md")), ROOT / "docs" / "decisoes.md"]:
        text = page.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{page.name}: sem front matter"
        block = text[4 : text.find("\n---", 3)]
        assert "sources:" in block, f"{page.name}: sem `sources:` no front matter"

        listed = [
            line.strip()[2:].strip()
            for line in block.splitlines()
            if line.strip().startswith("- ")
        ]
        assert listed, f"{page.name}: `sources:` vazio"


def test_sources_casam_com_arquivos_reais() -> None:
    result = subprocess.run(
        [sys.executable, "docs/_hooks/freshness.py", "--all"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert "sources inválidas" not in result.stdout, result.stdout
    assert "sem arquivos em sources" not in result.stdout, result.stdout


def test_flags_do_cli_estao_documentadas_no_readme() -> None:
    parsers = [build_parser(), *(_build_subcommand_parser(c) for c in COMMANDS)]
    flags = {
        option
        for parser in parsers
        for action in parser._actions
        for option in action.option_strings
        if option.startswith("--") and option not in {"--help"}
    }
    readme = README.read_text(encoding="utf-8")

    missing = sorted(flag for flag in flags if flag not in readme)
    assert missing == [], f"flags sem documentação no README: {missing}"

    documented = set(re.findall(r"--[a-z][a-z-]+", readme)) - NON_CLI_FLAGS
    invented = sorted(documented - flags)
    assert invented == [], f"README documenta flags que o CLI não tem: {invented}"


def test_versao_do_readme_bate_com_o_pacote() -> None:
    first_line = README.read_text(encoding="utf-8").splitlines()[0]

    assert first_line == f"# Loxia {__version__}", (
        f"README diz {first_line!r}, pacote é {__version__}"
    )


def test_bloco_de_niveis_esta_atualizado() -> None:
    result = subprocess.run(
        [sys.executable, "docs/_hooks/levels.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "docs/spec/garantias.md defasado em relação ao manifesto; "
        "rode `make docs-sync`.\n" + result.stdout
    )


def test_catalogo_de_codigos_esta_atualizado() -> None:
    result = subprocess.run(
        [sys.executable, "docs/_hooks/codes.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "docs/spec/erros.md defasado em relação a loxia_core/diagnostics/codes.py; "
        "rode `make codes`.\n" + result.stdout
    )


def test_sem_frases_defasadas() -> None:
    problems: list[str] = []

    for page in MUTABLE_DOCS:
        text = page.read_text(encoding="utf-8").lower()
        for phrase, reason in STALE_PHRASES.items():
            if phrase in text:
                problems.append(f"{page.relative_to(ROOT)}: {phrase!r} — {reason}")

    assert problems == [], "\n".join(problems)


def test_pending_do_corpus_tem_teto() -> None:
    """I1 é sobre o corpus declarado; `PENDING` não pode virar o corpus inteiro."""
    assert len(PENDING) <= 12, (
        f"{len(PENDING)} casos em PENDING: feche o nível ou revise o contrato "
        "(docs/spec/garantias.md) antes de seguir"
    )


def test_todos_os_codigos_de_diagnostico_estao_documentados() -> None:
    """ADR-0075: o catálogo de erros é fechado e toda família aparece na spec."""
    from loxia_core.diagnostics.codes import CODE_DESCRIPTIONS, CODE_PHASE, Code

    text = (SPEC_DIR / "erros.md").read_text(encoding="utf-8")

    assert set(CODE_PHASE) == set(Code), "todo código precisa de uma fase"
    assert set(CODE_DESCRIPTIONS) == set(Code), "todo código precisa de descrição"
    missing = [code.value for code in Code if code.value not in text]
    assert missing == [], f"códigos sem documentação em docs/spec/erros.md: {missing}"


def test_faixa_do_codigo_bate_com_a_fase() -> None:
    from loxia_core.diagnostics.codes import CODE_PHASE
    from loxia_core.diagnostics.diagnostic import Phase

    expected_prefix = {
        Phase.LEXER: "E0",
        Phase.PARSER: "E1",
        Phase.RESOLVER: "E2",
        Phase.CHECKER: "E3",
        Phase.BACKEND: "E4",
        Phase.RUNTIME: "R1",
        Phase.CLI: "C0",
    }

    for code, phase in CODE_PHASE.items():
        if code.value.startswith("W"):
            assert phase is Phase.RESOLVER, (code, phase)
            continue
        assert code.value.startswith(expected_prefix[phase]), (code, phase)
        assert 0 <= len(code.value) <= 5

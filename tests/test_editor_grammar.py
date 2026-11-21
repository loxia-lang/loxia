# SPDX-License-Identifier: MIT OR Apache-2.0
"""Drift gate da grammar de editor (VS Code / Sublime / TextMate / Shiki).

A grammar `editors/grammar/loxia.tmLanguage.json` é **gerada** por
`editors/build_grammar.py` a partir de `loxia_core/frontend/keywords.py`,
`loxia_core/frontend/token_type.py` e `loxia_core/execution/prelude.py`. Este teste falha quando alguém
edita o JSON à mão, adiciona keyword/operador sem rodar `make grammar`, ou quebra o
contrato do `.gitattributes` (fontes fora das estatísticas do GitHub).

O cliente VS Code não mora mais aqui: ele vive em `loxia-lang/loxia-vscode` e consome
estes arquivos como asset de release (ver `editors/README.md` e ADR-0109).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from loxia_core.execution.prelude import BUILTIN_NAMES
from loxia_core.frontend.keywords import KEYWORDS

ROOT = Path(__file__).resolve().parents[1]
GRAMMAR_DIR = ROOT / "editors" / "grammar"
GRAMMAR = GRAMMAR_DIR / "loxia.tmLanguage.json"
SHIKI = GRAMMAR_DIR / "loxia.mjs"
DSH = GRAMMAR_DIR / "loxia.ts"
GITATTRIBUTES = ROOT / ".gitattributes"


def _grammar() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(GRAMMAR.read_text(encoding="utf-8")))


def _patterns(node: object) -> list[str]:
    """Todas as regex (`match`/`begin`/`end`) da grammar, recursivamente."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in {"match", "begin", "end"} and isinstance(value, str):
                found.append(value)
            else:
                found.extend(_patterns(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_patterns(item))
    return found


def _includes(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        if isinstance(node.get("include"), str):
            found.add(node["include"])
        for value in node.values():
            found.update(_includes(value))
    elif isinstance(node, list):
        for item in node:
            found.update(_includes(item))
    return found


def test_grammar_esta_sincronizada_com_o_gerador() -> None:
    result = subprocess.run(
        [sys.executable, "editors/build_grammar.py", "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, (
        "grammar defasada em relação a keywords.py/TokenType/prelude.py; "
        f"rode `make grammar`.\n{result.stdout}{result.stderr}"
    )


def test_toda_keyword_tem_scope() -> None:
    """A união das alternâncias `\\b(?:a|b)\\b` é exatamente `KEYWORDS`."""
    words: set[str] = set()
    for pattern in _patterns(_grammar()):
        for body in re.findall(r"\(\?:([a-z|]+)\)", pattern):
            words.update(body.split("|"))

    assert words == set(KEYWORDS), (
        f"fora da grammar: {sorted(set(KEYWORDS) - words)}; "
        f"fantasmas na grammar: {sorted(words - set(KEYWORDS))}"
    )


def test_todo_nome_embutido_aparece() -> None:
    joined = " ".join(_patterns(_grammar()))

    for name in BUILTIN_NAMES:
        assert re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", joined), (
            f"nome embutido sem regra de destaque: {name}"
        )


def test_barra_barra_e_divisao_nao_comentario() -> None:
    """`//` é divisão (ADR-0012); nenhuma regra de comentário pode usá-lo."""
    repository = _grammar()["repository"]
    comments = [
        value
        for name, rule in repository.items()
        if name != "doc-comment" and "comment" in rule.get("name", "")
        for value in (rule.get("match"), rule.get("begin"), rule.get("end"))
        if isinstance(value, str)
    ]

    assert comments, "a grammar não tem regra de comentário"
    assert not any("//" in pattern for pattern in comments)
    assert "///" in repository["doc-comment"]["match"]
    assert "//" in repository["operators"]["match"]


def test_todos_os_includes_resolvem() -> None:
    grammar = _grammar()
    repository = grammar["repository"]
    missing = sorted(
        name.removeprefix("#")
        for name in _includes(grammar)
        if name.startswith("#") and name.removeprefix("#") not in repository
    )

    assert missing == [], f"includes que não existem no repository: {missing}"


def test_regexes_compilam() -> None:
    for pattern in _patterns(_grammar()):
        re.compile(pattern)


def test_shim_do_shiki_aponta_para_a_grammar() -> None:
    """O shim `.mjs` (site/DSH) importa o mesmo JSON, sem copiar a grammar."""
    text = SHIKI.read_text(encoding="utf-8")
    match = re.search(r"from '([^']+\.json)'", text)

    assert match is not None, "shim sem import do .tmLanguage.json"
    assert (SHIKI.parent / match.group(1)).resolve() == GRAMMAR
    assert "name: 'loxia'" in text
    assert "aliases: ['lx']" in text


def test_assets_de_release_sao_reproduziveis(tmp_path: Path) -> None:
    """`--assets DIR` empacota os três artefatos + SHA256SUMS para o release."""
    result = subprocess.run(
        [sys.executable, "editors/build_grammar.py", "--assets", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for name in ("loxia.tmLanguage.json", "loxia.mjs", "loxia.ts"):
        assert (tmp_path / name).read_bytes() == (GRAMMAR_DIR / name).read_bytes()

    sums = (tmp_path / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    assert [line.split("  ", 1)[1] for line in sums] == [
        "loxia.tmLanguage.json",
        "loxia.mjs",
        "loxia.ts",
    ]
    for line in sums:
        digest, name = line.split("  ", 1)
        expected = hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        assert digest == expected


def test_release_anexa_os_assets_da_grammar() -> None:
    """O workflow de release publica a grammar junto do wheel/sdist (issue #5)."""
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    assert "build_grammar.py --assets" in workflow
    assert "gh release create" in workflow
    assert "grammar/*" in workflow


def test_gitattributes_mantem_lx_fora_do_linguist() -> None:
    """Decisão do README/§14: sem `linguist-language`, o repo não mente a linguagem."""
    text = GITATTRIBUTES.read_text(encoding="utf-8")
    active = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert "*.lx linguist-detectable=false" in active
    assert not any("linguist-language=" in line for line in active)

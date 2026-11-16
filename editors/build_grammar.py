"""Gera a grammar TextMate da Loxia (VS Code, Sublime, TextMate, GitHub).

A lista de keywords, a de operadores e a de nomes embutidos **não** são copiadas à mão:
vêm de `loxia_core/frontend/keywords.py` (`KEYWORDS`), `loxia_core/frontend/token_type.py`
(`TokenType`) e `loxia_core/execution/prelude.py` (`BUILTIN_NAMES`). Keyword, operador ou nome
embutido novo sem grammar atualizada falha no `--check`, que roda em
`tests/test_editor_grammar.py` (`make check`).

Uso:

    uv run python editors/build_grammar.py           # imprime o JSON
    uv run python editors/build_grammar.py --write   # regrava o .tmLanguage.json
    uv run python editors/build_grammar.py --check   # exit 1 se o arquivo estiver defasado

Limitações **declaradas** do TextMate (não são bugs do gerador):

- comentário `/* */` aninhado é suportado até `NESTING` níveis; depois disso o bloco fecha
  no primeiro `*/` (é assim que grammars de C/JS fazem, com o mesmo hack);
- não existe análise semântica: `Foo` capitalizado vira `entity.name.type` mesmo quando é
  variável, e não há refinamento de campo depois do `.`;
- `//` é **divisão**, não comentário (ADR-0012) — a grammar não pode herdar o padrão de C.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from loxia_core.execution.prelude import BUILTIN_NAMES  # noqa: E402
from loxia_core.frontend.keywords import KEYWORDS  # noqa: E402
from loxia_core.frontend.token_type import TokenType  # noqa: E402

TARGET = ROOT / "editors" / "vscode" / "syntaxes" / "loxia.tmLanguage.json"
SHIKI_TARGET = ROOT / "editors" / "shiki" / "loxia.mjs"
DSH_TARGET = ROOT / "editors" / "dsh" / "loxia.ts"
SCOPE = "source.loxia"
NESTING = 3

# Um `scope` por família sintática; a união tem que ser exatamente `KEYWORDS`.
# Categorizar é decisão humana: keyword nova sem grupo quebra o gerador de propósito.
KEYWORD_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "keywords-control",
        "keyword.control.loxia",
        (
            "if", "elif", "else", "while", "for", "in", "return", "match",
            "try", "except", "finally", "raise",
        ),
    ),
    (
        "keywords-declaration",
        "keyword.other.declaration.loxia",
        ("class", "fn", "val", "var", "enum", "interface", "import", "from", "as", "is", "super", "this"),
    ),
    ("keywords-operator-word", "keyword.operator.word.loxia", ("and", "or", "not")),
    ("keywords-modifier", "storage.modifier.loxia", ("async", "await")),
    ("keywords-constant", "constant.language.loxia", ("true", "false", "nil")),
)

# Operador de verdade (recebe `keyword.operator`).
OPERATORS: dict[TokenType, str] = {
    TokenType.PLUS: "+",
    TokenType.MINUS: "-",
    TokenType.SLASH: "/",
    TokenType.SLASH_SLASH: "//",
    TokenType.STAR: "*",
    TokenType.STAR_STAR: "**",
    TokenType.PERCENT: "%",
    TokenType.QUESTION: "?",
    TokenType.QUESTION_QUESTION: "??",
    TokenType.QUESTION_DOT: "?.",
    TokenType.AMPERSAND: "&",
    TokenType.PIPE: "|",
    TokenType.CARET: "^",
    TokenType.TILDE: "~",
    TokenType.NOT: "!",
    TokenType.NOT_EQUAL: "!=",
    TokenType.EQUAL: "=",
    TokenType.EQUAL_EQUAL: "==",
    TokenType.GREATER: ">",
    TokenType.GREATER_EQUAL: ">=",
    TokenType.LESS: "<",
    TokenType.LESS_EQUAL: "<=",
    TokenType.LESS_LESS: "<<",
    TokenType.GREATER_GREATER: ">>",
    TokenType.GREATER_GREATER_GREATER: ">>>",
    TokenType.DOT_DOT: "..",
    TokenType.ELLIPSIS: "...",
    TokenType.ARROW: "->",
    TokenType.FAT_ARROW: "=>",
}

# Delimitador (recebe `punctuation`); o tema não colore, mas o editor pareia.
PUNCTUATION: dict[TokenType, str] = {
    TokenType.LEFT_PAREN: "(",
    TokenType.RIGHT_PAREN: ")",
    TokenType.LEFT_BRACE: "{",
    TokenType.RIGHT_BRACE: "}",
    TokenType.LEFT_BRACKET: "[",
    TokenType.RIGHT_BRACKET: "]",
    TokenType.COMMA: ",",
    TokenType.SEMICOLON: ";",
    TokenType.COLON: ":",
    TokenType.DOT: ".",
}

# Tokens que não produzem regra de destaque: o lexema carrega o valor.
STRUCTURAL: frozenset[TokenType] = frozenset(
    {
        TokenType.IDENTIFIER,
        TokenType.STRING,
        TokenType.INTERPOLATED_STRING,
        TokenType.NUMBER,
        TokenType.EOF,
    }
)


def _alternation(literals: Iterable[str]) -> str:
    """Alternância ordenada do mais longo para o mais curto (`>>>` antes de `>`)."""
    ordered = sorted(set(literals), key=lambda item: (-len(item), item))
    return "|".join(re.escape(item) for item in ordered)


def _word_alternation(words: Iterable[str]) -> str:
    return "\\b(?:" + "|".join(sorted(set(words))) + ")\\b"


def check_coverage() -> None:
    """Falha se keyword/token existir no lexer e não tiver destino na grammar."""
    categorized = set().union(*(set(words) for _, _, words in KEYWORD_GROUPS))
    unknown = categorized - set(KEYWORDS)
    missing_keywords = set(KEYWORDS) - categorized
    if missing_keywords:
        raise SystemExit(
            "keywords sem grupo na grammar: " + ", ".join(sorted(missing_keywords))
        )
    if unknown:
        raise SystemExit(
            "grupos da grammar citam keywords inexistentes: " + ", ".join(sorted(unknown))
        )

    keyword_tokens = set(KEYWORDS.values())
    # `!` e `not` compartilham TokenType.NOT (ADR-0068): o keyword cobre `not` e o `!`
    # continua sendo operador válido (ele dá diagnóstico dirigido, mas é lexado).
    expected = (set(TokenType) - STRUCTURAL - keyword_tokens) | {TokenType.NOT}
    covered = set(OPERATORS) | set(PUNCTUATION)
    missing_tokens = expected - covered
    extra_tokens = covered - expected
    if missing_tokens:
        raise SystemExit(
            "token types sem regra de destaque: "
            + ", ".join(sorted(token.name for token in missing_tokens))
        )
    if extra_tokens:
        raise SystemExit(
            "regra de destaque para token inexistente: "
            + ", ".join(sorted(token.name for token in extra_tokens))
        )


def _builtin_groups() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Separa `Int`/`Result` (tipo/classe) de `len`/`math` (função/namespace)."""
    classes = tuple(name for name in BUILTIN_NAMES if name[:1].isupper())
    others = tuple(name for name in BUILTIN_NAMES if not name[:1].isupper())
    return classes, others


def _declaration_rule(keyword: str, scope: str) -> dict[str, Any]:
    return {
        "match": rf"\b({keyword})\s+([A-Za-z_][A-Za-z0-9_]*)",
        "captures": {
            "1": {"name": "keyword.other.declaration.loxia"},
            "2": {"name": scope},
        },
    }


def build() -> dict[str, Any]:
    classes, others = _builtin_groups()

    repository: dict[str, Any] = {
        "line-comment": {
            "match": "#.*$",
            "name": "comment.line.number-sign.loxia",
        },
    }

    for level in range(NESTING):
        rule: dict[str, Any] = {
            "begin": r"/\*",
            "end": r"\*/",
            "name": "comment.block.loxia",
            "patterns": [{"include": "#line-comment"}],
        }
        if level + 1 < NESTING:
            rule["patterns"].append({"include": f"#block-comment-{level + 1}"})
        repository[f"block-comment-{level}"] = rule

    repository.update(
        {
            "escapes": {
                "match": r"\\u\{[0-9a-fA-F]+\}|\\.",
                "name": "constant.character.escape.loxia",
            },
            "interpolation": {
                "begin": r"\$\{",
                "end": r"\}",
                "name": "meta.interpolation.loxia",
                "beginCaptures": {
                    "0": {"name": "punctuation.section.interpolation.begin.loxia"}
                },
                "endCaptures": {
                    "0": {"name": "punctuation.section.interpolation.end.loxia"}
                },
                "patterns": [{"include": "$self"}],
            },
            "string-raw-triple": {
                "begin": r'r"""',
                "end": r'"""',
                "name": "string.quoted.triple.raw.loxia",
            },
            "string-raw": {
                "begin": r'r"',
                "end": r'"',
                "name": "string.quoted.double.raw.loxia",
            },
            "string-triple": {
                "begin": r'"""',
                "end": r'"""',
                "name": "string.quoted.triple.loxia",
                "patterns": [{"include": "#escapes"}, {"include": "#interpolation"}],
            },
            "string": {
                "begin": r'"',
                "end": r'"',
                "name": "string.quoted.double.loxia",
                "patterns": [{"include": "#escapes"}, {"include": "#interpolation"}],
            },
            "numbers": {
                "patterns": [
                    {"match": r"\b0[xX][0-9a-fA-F_]+", "name": "constant.numeric.hex.loxia"},
                    {"match": r"\b0[bB][01_]+", "name": "constant.numeric.binary.loxia"},
                    {"match": r"\b0[oO][0-7_]+", "name": "constant.numeric.octal.loxia"},
                    {
                        "match": (
                            r"\b[0-9][0-9_]*(?:\.[0-9][0-9_]*)"
                            r"(?:[eE][+-]?[0-9][0-9_]*)?"
                            r"|\b[0-9][0-9_]*[eE][+-]?[0-9][0-9_]*"
                        ),
                        "name": "constant.numeric.float.loxia",
                    },
                    {"match": r"\b[0-9][0-9_]*", "name": "constant.numeric.integer.loxia"},
                ]
            },
            "declarations": {
                "patterns": [
                    _declaration_rule("fn", "entity.name.function.loxia"),
                    _declaration_rule("class", "entity.name.class.loxia"),
                    _declaration_rule("interface", "entity.name.class.interface.loxia"),
                    _declaration_rule("enum", "entity.name.class.enum.loxia"),
                ]
            },
            "types": {
                "match": r"\b[A-Z][A-Za-z0-9_]*\b",
                "name": "entity.name.type.loxia",
            },
            "calls": {
                "match": r"\b([A-Za-z_][A-Za-z0-9_]*)(?=\s*\()",
                "name": "entity.name.function.call.loxia",
            },
            "operators": {
                "match": _alternation(OPERATORS.values()),
                "name": "keyword.operator.loxia",
            },
            "punctuation": {
                "match": _alternation(PUNCTUATION.values()),
                "name": "punctuation.loxia",
            },
        }
    )

    if classes:
        repository["builtin-class"] = {
            "match": _word_alternation(classes),
            "name": "support.class.builtin.loxia",
        }
    if others:
        repository["builtin-function"] = {
            "match": _word_alternation(others),
            "name": "support.function.builtin.loxia",
        }
    for key, scope, words in KEYWORD_GROUPS:
        repository[key] = {"match": _word_alternation(words), "name": scope}

    patterns: list[dict[str, Any]] = [
        {"include": "#line-comment"},
        {"include": "#block-comment-0"},
        {"include": "#declarations"},
        {"include": "#string-raw-triple"},
        {"include": "#string-raw"},
        {"include": "#string-triple"},
        {"include": "#string"},
        {"include": "#numbers"},
    ]
    patterns.extend({"include": f"#{key}"} for key, _, _ in KEYWORD_GROUPS)
    patterns.extend(
        [
            {"include": "#builtin-class"},
            {"include": "#builtin-function"},
            {"include": "#types"},
            {"include": "#calls"},
            {"include": "#operators"},
            {"include": "#punctuation"},
        ]
    )

    return {
        "$schema": "https://raw.githubusercontent.com/martinring/tmlanguage/master/tmlanguage.json",
        "name": "Loxia",
        "scopeName": SCOPE,
        "fileTypes": ["lx"],
        "patterns": patterns,
        "repository": repository,
    }


def render() -> str:
    return json.dumps(build(), indent=2, ensure_ascii=False) + "\n"


def render_shiki() -> str:
    """Módulo ESM que entrega a **mesma** grammar para Shiki (site, DSH).

    Shiki quer um array de `LanguageRegistration` com `name` = id da grammar, e o
    `.tmLanguage.json` usa `name` como nome de exibição — daí o shim de 3 linhas em vez de
    duplicar as 274 linhas do JSON.
    """
    return (
        "// GERADO por editors/build_grammar.py --write; não edite à mão.\n"
        "// Consumido por Shiki (site de docs e viewer do harness), que usa o mesmo\n"
        "// JSON do VS Code. A grammar é indentada por `name` = id, então o shim\n"
        "// renomeia para `loxia` e adiciona o alias `lx`.\n"
        "import grammar from '../vscode/syntaxes/loxia.tmLanguage.json' with { type: 'json' }\n"
        "\n"
        "export default [\n"
        "  { ...grammar, name: 'loxia', displayName: 'Loxia', aliases: ['lx'] },\n"
        "]\n"
    )


def render_ts() -> str:
    """Módulo TypeScript autocontido para o viewer do harness (Shiki)."""
    body = json.dumps(build(), indent=2, ensure_ascii=False)
    return (
        "// GERADO por editors/build_grammar.py --write; não edite à mão.\n"
        "// Integração com o viewer do DeepSeek Harness (Shiki). Copie para\n"
        "// packages/client/ui-primitives/src/markdown/grammars/loxia.ts e registre nos\n"
        "// três pontos descritos em editors/README.md (seção Shiki).\n"
        "import type { LanguageRegistration } from 'shiki'\n"
        "\n"
        f"const grammar = {body}\n"
        "\n"
        "export default [\n"
        "  { ...grammar, name: 'loxia', displayName: 'Loxia', aliases: ['lx'] },\n"
        "] as unknown as LanguageRegistration[]\n"
    )


def main(argv: list[str]) -> int:
    check_coverage()
    text = render()

    shiki = render_shiki()
    ts = render_ts()

    if "--check" in argv:
        stale = []
        for path, expected in ((TARGET, text), (SHIKI_TARGET, shiki), (DSH_TARGET, ts)):
            current = path.read_text(encoding="utf-8") if path.is_file() else ""
            if current != expected:
                stale.append(str(path.relative_to(ROOT)))
        if not stale:
            return 0
        print(
            ", ".join(stale) + " defasado(s) em relação a "
            "loxia_core/frontend (keywords/tokens) ou loxia_core/execution/prelude.py. "
            "Rode: make grammar"
        )
        return 1

    if "--write" in argv:
        for path, content in ((TARGET, text), (SHIKI_TARGET, shiki), (DSH_TARGET, ts)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"escrito {path.relative_to(ROOT)}")
        return 0

    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

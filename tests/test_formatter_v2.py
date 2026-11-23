# SPDX-License-Identifier: MIT OR Apache-2.0
"""Formatter v2: Doc IR + printer (ADR-0136).

Os casos golden fixam a forma canônica; o teste de corpus prova idempotência, AST igual
(ignorando spans/trivia via AstPrinter) e nenhum comentário perdido nos 320 arquivos
parseáveis do oráculo.
"""

from __future__ import annotations

from loxia.formatter.comments import comment_text
from loxia.formatter.engine import format_source
from loxia_core.diagnostics.error_reporter import ErrorReporter
from loxia_core.frontend.ast_printer import AstPrinter
from loxia_core.frontend.parser import Parser
from loxia_core.frontend.scanner import Scanner
from loxia_core.frontend.stmt import Stmt
from loxia_core.frontend.trivia import Trivia
from tools.oracle_snapshot import corpus_files


def parse(source: str) -> tuple[list[Stmt], list[Trivia]]:
    reporter = ErrorReporter()
    scanner = Scanner(source, reporter)
    tokens = scanner.scan_tokens()
    assert not reporter.had_error, "fixture has a lexical error"
    statements = Parser(tokens, reporter=reporter).parse()
    assert statements is not None and not reporter.had_error, "fixture has a syntax error"
    return statements, scanner.trivia


def ast_text(source: str) -> str:
    statements, _ = parse(source)
    return AstPrinter().print_program(statements)


def comment_texts(source: str) -> list[str]:
    _, trivia = parse(source)
    # Espaço no fim da linha é whitespace, não conteúdo do comentário.
    return sorted(comment_text(item).rstrip() for item in trivia if item.is_comment)


def formatted(source: str, width: int = 100) -> str:
    result = format_source(source, max_width=width)
    assert result is not None, "formatter rejected a valid fixture"
    return result.text


def assert_roundtrip(source: str, width: int = 100) -> str:
    value = formatted(source, width)
    assert formatted(value, width) == value, "formatter is not idempotent"
    assert ast_text(value) == ast_text(source), "formatter changed the AST"
    assert comment_texts(value) == comment_texts(source), "formatter lost or changed a comment"
    assert "\r" not in value
    assert all(not line.endswith((" ", "\t")) for line in value.splitlines())
    return value


def test_flat_forms_stay_inline() -> None:
    source = 'print([1, 2], {"a": 1}, (1, 2), f(1, 2))\n'

    assert assert_roundtrip(source) == 'print([1, 2], { "a": 1 }, (1, 2), f(1, 2))\n'


def test_call_wraps_vertically_with_trailing_comma() -> None:
    source = "val x = f(aaaaaaaaaa, bbbbbbbbbb, cccccccccc, dddddddddd, eeeeeeeeee, ffffffffff)\n"

    expected = """val x = f(
  aaaaaaaaaa,
  bbbbbbbbbb,
  cccccccccc,
  dddddddddd,
  eeeeeeeeee,
  ffffffffff,
)
"""

    assert assert_roundtrip(source, 40) == expected


def test_list_wraps_vertically_with_trailing_comma() -> None:
    source = "val xs = [1111111111, 2222222222, 3333333333, 4444444444, 5555555555]\n"

    expected = """val xs = [
  1111111111,
  2222222222,
  3333333333,
  4444444444,
  5555555555,
]
"""

    assert assert_roundtrip(source, 40) == expected


def test_binary_chain_breaks_after_the_operator() -> None:
    source = "val total = alpha + beta + gamma + delta + epsilon + zeta + eta\n"

    expected = """val total = alpha +
  beta +
  gamma +
  delta +
  epsilon +
  zeta +
  eta
"""

    assert assert_roundtrip(source, 30) == expected


def test_conditional_breaks_after_if_and_before_else() -> None:
    source = "val x = aVeryLongThenBranch if someVeryLongConditionName else anotherVeryLongBranch\n"

    expected = """val x = aVeryLongThenBranch if
  someVeryLongConditionName
else anotherVeryLongBranch
"""

    assert assert_roundtrip(source, 40) == expected


def test_comments_inside_call_and_empty_block() -> None:
    source = """fn f() {
  g(
    1, # one
    # two
    2,
  )
  if (true) {
    # only comment
  }
}
"""

    assert assert_roundtrip(source) == source


def test_class_blank_lines_and_trailing_comment_alignment() -> None:
    source = """class C {
  val a: Int = 1 # one
  val bb: Int = 2 # two
  fn m() {}
}
"""

    expected = """class C {
  val a: Int = 1   # one
  val bb: Int = 2  # two

  fn m() {}
}
"""

    assert assert_roundtrip(source) == expected


def test_top_level_declarations_are_separated_but_statements_are_not() -> None:
    source = """print(1)
print(2)
fn f() { return 1 }
print(f())
class C {}
"""

    expected = """print(1)
print(2)

fn f() {
  return 1
}

print(f())

class C {}
"""

    assert assert_roundtrip(source) == expected


def test_c_style_for_is_preserved() -> None:
    source = "for (var i = 0; i < 3; i = i + 1) {\n  print(i)\n}\n"

    expected = """for (var i = 0; i < 3; i = i + 1) {
  print(i)
}
"""

    assert assert_roundtrip(source) == expected


def test_for_in_and_while_stay_canonical() -> None:
    source = "fn f(xs: List[Int]) {\n  for x in xs { print(x) }\n  while (false) { print(0) }\n}\n"

    expected = """fn f(xs: List[Int]) {
  for x in xs {
    print(x)
  }
  while (false) {
    print(0)
  }
}
"""

    assert assert_roundtrip(source) == expected


def test_match_arms_and_enum_variants() -> None:
    source = """enum Shape {
  Circle(Float),
  Rect(Float, Float)
}

fn area(shape: Shape) -> Float {
  return match shape {
    Shape.Circle(r) => 3.14 * r * r,
    Shape.Rect(w, h) => w * h
  }
}
"""

    expected = """enum Shape { Circle(Float), Rect(Float, Float) }

fn area(shape: Shape) -> Float {
  return match shape {
    Shape.Circle(r) => 3.14 * r * r
    Shape.Rect(w, h) => w * h
  }
}
"""

    assert assert_roundtrip(source) == expected


def test_try_except_finally() -> None:
    source = """fn f(x: Int) -> Int {
  try { raise x } except Error as e { return 0 } finally { print("done") }
}
"""

    expected = """fn f(x: Int) -> Int {
  try {
    raise x
  } except Error as e {
    return 0
  } finally {
    print("done")
  }
}
"""

    assert assert_roundtrip(source) == expected


def test_destructuring_type_alias_and_imports() -> None:
    source = """type Id = Int
from std.json import decode as d, encode
import std.lists as lists

fn f(pair: (Int, Int)) -> Int {
  val (a, (b, c)) = pair
  return a + b + c
}
"""

    expected = """type Id = Int

from std.json import decode as d, encode
import std.lists as lists

fn f(pair: (Int, Int)) -> Int {
  val (a, (b, c)) = pair
  return a + b + c
}
"""

    assert assert_roundtrip(source) == expected


def test_multiline_string_and_block_comment_are_verbatim() -> None:
    source = '''fn f() -> String {
  return """line1
  line2
"""
}

/* block
   comment */
fn g() {}
'''

    assert assert_roundtrip(source) == source


def test_doc_comment_is_not_reflowed() -> None:
    source = """/// Doc da classe.
class C {
  /// Doc do campo com  espaços   internos.
  val x: Int
}
"""

    assert assert_roundtrip(source) == source


def test_expression_lambda_and_block_lambda() -> None:
    source = """fn f(xs: List[Int]) {
  val doubled = maps.map(xs, fn(x) => x * 2)
  val add = fn(a: Int, b: Int) { return a + b }
  print(doubled)
  print(add(1, 2))
}
"""

    expected = """fn f(xs: List[Int]) {
  val doubled = maps.map(xs, fn(x) => x * 2)
  val add = fn(a: Int, b: Int) {
    return a + b
  }
  print(doubled)
  print(add(1, 2))
}
"""

    assert assert_roundtrip(source) == expected


def test_optional_chain_and_spread() -> None:
    source = """fn f(a: C?, xs: List[Int]) -> Int? {
  val value = a?.get()?.value
  print(g(1, ...xs))
  return value
}
"""

    assert assert_roundtrip(source) == source


def test_syntax_error_returns_none() -> None:
    assert format_source("fn f( {\n") is None


def test_trailing_comment_positions_stay_valid() -> None:
    cases = [
        "val xs = [\n  1, # one\n  2,\n]\n",
        "print(a, # c\n  b)\n",
        'val m = { "a": 1, # c\n  "b": 2 }\n',
        "fn f(a: Int, # a\n  b: Int) {}\n",
        "print(a + # c\n  b)\n",
        "val x = 1 if # c\n  true else 2\n",
        "val x = (a if # c\n  b else c) + 1\n",
        "for (var i = 0; # head\n  i < 10; i = i + 1) {\n  print(i)\n}\n",
        "val f = fn(x) => # c\n  x + 1\n",
    ]

    for source in cases:
        assert_roundtrip(source)


def test_type_annotation_comments_are_preserved() -> None:
    cases = [
        "val x: # c\n  Int = 1\n",
        "class C {\n  val x: # c\n    Int\n}\n",
        "fn f(x: # c\n  Int) -> Int {\n  return x\n}\n",
        "fn f() -> # c\n  Int {\n  return 1\n}\n",
        "type T = # c\n  Int\n",
        "enum E {\n  A( # c\n    Int)\n}\n",
        "fn f(x: Any) -> Bool {\n  return x is # c\n    Int\n}\n",
        "fn f(x: Any) -> Int {\n  return x as # c\n    Int\n}\n",
        "val f = fn(x: Int) -> # c\n  Int => x\n",
    ]

    for source in cases:
        assert_roundtrip(source)


def test_top_level_val_preserves_user_blank_lines() -> None:
    source = "val a = 1\nval b = 2\n\nval c = 3\n"

    assert assert_roundtrip(source) == source


def test_comment_between_keyword_and_name_keeps_source_order() -> None:
    cases = [
        ("val /*c*/ x = 1\n", "val /*c*/\nx = 1\n"),
        ("class /*c*/ C {}\n", "class /*c*/\nC {}\n"),
        ("fn /*c*/ f() {}\n", "fn /*c*/\nf() {}\n"),
        ("import /*c*/ std.foo\n", "import /*c*/\nstd.foo\n"),
        ("type /*c*/ T = Int\n", "type /*c*/\nT = Int\n"),
        ("class C {\n  val /*c*/ x: Int\n}\n", "class C {\n  val /*c*/\n  x: Int\n}\n"),
    ]

    for source, expected in cases:
        assert formatted(source) == expected


def test_conditional_and_collection_starts_keep_comments_inside() -> None:
    cases = [
        (
            "print([1, a if # c\n b else d])\n",
            "print(\n  [\n    1,\n    a if # c\n      b\n    else d,\n  ],\n)\n",
        ),
        ("print([ # c\n 1])\n", "print(\n  [ # c\n    1,\n  ],\n)\n"),
        ("print({ # c\n 1: 2})\n", "print(\n  { # c\n    1: 2,\n  },\n)\n"),
        ("print(( # c\n 1, 2))\n", "print(\n  ( # c\n    1,\n    2,\n  ),\n)\n"),
        (
            "val x = [a if # c\n b else d]\n",
            "val x = [\n  a if # c\n    b\n  else d,\n]\n",
        ),
    ]

    for source, expected in cases:
        assert formatted(source) == expected


def test_corpus_idempotent_semantic_and_comment_preserving() -> None:
    checked = 0
    for path in corpus_files():
        source = path.read_text(encoding="utf-8")
        result = format_source(source)
        if result is None:  # arquivos de erro de parse são cobertos pelo oráculo
            continue
        first = result.text
        second = format_source(first)
        assert second is not None, path
        assert second.text == first, f"{path}: not idempotent"
        assert ast_text(first) == ast_text(source), f"{path}: AST changed"
        assert comment_texts(first) == comment_texts(source), f"{path}: comment lost or changed"
        checked += 1
    assert checked >= 300, f"corpus too small: {checked} parseable files"

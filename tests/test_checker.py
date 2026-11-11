from __future__ import annotations

import pytest

from lox.cli import Lox


def check(source: str) -> Lox:
    lox = Lox()
    lox.check(source)
    return lox


def test_annotated_program_is_clean() -> None:
    source = """
    fn soma(a: Int, b: Int = 10) -> Int {
      return a + b;
    }

    val x = soma(1);
    val y: Float = 2.0;
    val nome: String? = nil;
    val rotulo = nome or "sem nome";

    class Animal {
      var nome: String;

      init(nome: String) {
        this.nome = nome;
      }

      falar() -> String {
        return this.nome;
      }
    }

    class Cachorro(Animal) {
      init(nome: String) {
        super.init(nome);
      }
    }

    val c: Cachorro = Cachorro("Rex");
    print c.falar();
    print rotulo;

    for i in 0..3 {
      print i;
    }

    for ch in "abc" {
      print ch;
    }
    """

    lox = check(source)

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ('val x: Int = "a";', "Expected Int, found String."),
        (
            'fn f(a: Int) -> Int { return a; } f("x");',
            "Expected Int, found String.",
        ),
        (
            'fn f(a: Int) -> Int { return a; } f();',
            "Expected 1 arguments but got 0.",
        ),
        ("val x: Desconhecido = 1;", "Unknown type 'Desconhecido'."),
        (
            "fn f(a) -> Int { return a; }",
            "Parameter 'a' needs a type annotation.",
        ),
        (
            "fn f(a: Int) { return a; }",
            "Function 'f' needs a return type annotation.",
        ),
        (
            'class C { var x: Int; init() { this.x = "a"; } }',
            "Expected Int, found String.",
        ),
        (
            "class C { val x: Int; init() { this.x = 1; } }"
            " val c = C(); c.x = 2;",
            "Can't assign to immutable field 'x'.",
        ),
        (
            "class C { var x: Int; init() { this.x = 1; } }"
            " val c = C(); c.y = 2;",
            "Undefined field 'y'.",
        ),
        (
            "fn f(n: Int) -> Int { return n; }"
            " fn g() -> Int { return f(true); }",
            "Expected Int, found Bool.",
        ),
        (
            "val x: Int | Nil = nil; val y: Int = x;",
            "Expected Int, found Int | Nil.",
        ),
        (
            'for x in 42 { print x; }',
            "Can only iterate over a range, a list or a string.",
        ),
    ],
)
def test_type_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    if message:
        assert message in captured.err


def test_union_is_assignable_to_member_and_nil() -> None:
    lox = check(
        """
        fn f(flag: Bool) -> Int | Nil {
          if (flag) { return 1; }
          return nil;
        }
        val x: Int | Nil = f(true);
        print x;
        """
    )

    assert lox.reporter.had_error is False


def test_operator_types_are_clean() -> None:
    lox = check(
        """
        val a: Int = 7 // 2
        val b: Float = 2 ** 0.5
        val c: Int = 5 & 3
        val d: Bool = ~0 == -1
        val e: Float = 2 ** 3.0
        print a
        print b
        print c
        print d
        print e
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("val x: Int = 7 // 2.0;", "Operands must be integers."),
        ("val x: Int = ~1.0;", "Operand must be an integer."),
        ("val x: Int = 1.0 & 1;", "Operands must be integers."),
        ("val x: Int = 2 ** 0.5;", "Expected Int, found Float."),
        ("val x: Bool = 5 & 3;", "Expected Bool, found Int."),
    ],
)
def test_operator_type_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_nil_aware_and_conditional_types_are_clean() -> None:
    lox = check(
        """
        class Pessoa {
          var nome: String

          init(nome: String) {
            this.nome = nome
          }

          tamanho() -> Int {
            return 10
          }
        }

        val p: Pessoa? = nil
        val nome: String = p?.nome ?? "sem nome"
        val tamanho: Int = p?.tamanho() ?? 0
        val escolha: Int = 1 if true else 2
        val numero: Float = 1 if true else 2.0
        val zero: Int = 0 ?? 1
        val falso: Bool = false ?? true
        val texto: String = "a" ?? "b"
        val nulo: Int = nil ?? 1
        print nome
        print tamanho
        print escolha
        print numero
        print zero
        print falso
        print texto
        print nulo
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            'val x: Int = 1 if true else "a";',
            "Expected Int, found Int | String.",
        ),
        (
            "class C { var nome: String; init() { this.nome = \"x\"; } }"
            " val c: C? = nil; val x: Int = c?.nome ?? 0;",
            "Expected Int, found String | Int.",
        ),
        ("print 1?.x;", "Only instances have properties."),
        (
            "class C { init() {} } val c: C? = nil; print c?.naoExiste;",
            "Undefined property 'naoExiste'.",
        ),
    ],
)
def test_nil_aware_and_conditional_type_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err

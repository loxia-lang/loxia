from __future__ import annotations

import pytest

from loxia.cli import Loxia
from src.diagnostics.error_reporter import ErrorReporter
from src.execution.interpreter import Interpreter
from src.frontend.expr import Get, Variable
from src.frontend.parser import Parser
from src.frontend.scanner import Scanner
from src.frontend.ty import INT, STRING, is_nilable
from src.semantics.checker import Checker
from src.semantics.resolver import Resolver


def check(source: str) -> Loxia:
    lox = Loxia()
    lox.check(source)
    return lox


def test_this_inside_local_function_is_lexical() -> None:
    lox = check(
        """
        class Foo {
          getClosure() -> fn() -> String {
            fn closure() -> String {
              return this.toString();
            }
            return closure;
          }

          toString() -> String {
            return "Foo";
          }
        }

        val f = Foo().getClosure();
        print(f());
        """
    )

    assert lox.reporter.had_error is False


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
    print(c.falar());
    print(rotulo);

    for i in 0..3 {
      print(i);
    }

    for ch in "abc" {
      print(ch);
    }
    """

    lox = check(source)

    assert lox.reporter.had_error is False


def test_functions_can_call_functions_declared_later() -> None:
    lox = check(
        """
        fn par(n: Int) -> Bool {
          if (n == 0) { return true; }
          return impar(n - 1);
        }

        fn impar(n: Int) -> Bool {
          if (n == 0) { return false; }
          return par(n - 1);
        }

        print(par(4));
        """
    )

    assert lox.reporter.had_error is False


def test_top_level_call_before_declaration_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        print(f());
        fn f() -> Int { return 1; }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Undefined variable 'f'." in captured.err


def test_call_error_reports_the_argument_position(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn f(a: Int, b: String) -> Nil { return nil; }
        f(1, 2);
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Argument 2: Expected String, found Int." in captured.err


def test_function_type_parameter_and_return_are_clean() -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int {
          return f(x);
        }

        fn dobro(n: Int) -> Int { return n * 2; }

        val y = aplicar(dobro, 3);

        fn escolhe() -> fn(Int) -> Int { return dobro; }
        val g = escolhe();

        print(y);
        print(g(4));
        """
    )

    assert lox.reporter.had_error is False


def test_function_type_rejects_wrong_signature(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int { return f(x); }
        fn texto(n: Int) -> String { return "x"; }
        aplicar(texto, 1);
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert (
        "Argument 1: Expected fn(Int) -> Int, found fn(Int) -> String."
        in captured.err
    )


def test_function_type_rejects_non_function(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int { return f(x); }
        aplicar(1, 2);
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Argument 1: Expected fn(Int) -> Int, found Int." in captured.err


def test_function_type_checks_callback_body(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int {
          return f("x");
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Argument 1: Expected Int, found String." in captured.err


def test_function_type_accepts_class_as_constructor() -> None:
    lox = check(
        """
        class Animal {
          var nome: String;

          init(nome: String) {
            this.nome = nome;
          }
        }

        fn criar(f: fn(String) -> Animal) -> Animal {
          return f("Rex");
        }

        val a: Animal = criar(Animal);
        print(a.nome);
        """
    )

    assert lox.reporter.had_error is False


def test_function_type_is_contravariant_in_params_and_covariant_in_return() -> None:
    lox = check(
        """
        class Animal { init() {} }
        class Dog(Animal) { init() { super.init(); } }

        fn aceitaAnimal(a: Animal) -> Animal { return a; }
        fn usaAnimal(f: fn(Dog) -> Animal) -> Nil { return nil; }
        usaAnimal(aceitaAnimal);

        fn fazDog() -> Dog { return Dog(); }
        fn usaRetorno(f: fn() -> Animal) -> Nil { return nil; }
        usaRetorno(fazDog);

        fn soma(a: Int, b: Int = 1) -> Int { return a + b; }
        fn usaUm(f: fn(Int) -> Int) -> Int { return f(1); }
        usaUm(soma);
        """
    )

    assert lox.reporter.had_error is False


def test_lambda_parameters_are_typed_from_context() -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int {
          return f(x);
        }

        val a = aplicar(fn(x) => x * 2, 3);
        val b = aplicar(fn(x) { return x * 2; }, 4);

        fn make(n: Int) -> fn(Int) -> Int {
          return fn(x: Int) => x + n;
        }

        val c = make(2);
        print(a);
        print(b);
        print(c(3));
        """
    )

    assert lox.reporter.had_error is False


def test_lambda_without_context_generalizes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # T4: `val f = fn(x) => x * 2` generaliza x, mas `*` exige número.
    lox = check("val f = fn(x) => x * 2;")
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Operands must be numbers." in captured.err


def test_lambda_mixed_returns_need_an_annotation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        val f = fn(x: Int) {
          if (x > 0) { return 1; }
          return "a";
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Lambda returns Int | String; annotate the return type." in captured.err


def test_lambda_annotated_mixed_returns_are_clean() -> None:
    lox = check(
        """
        val f = fn(x: Int) -> Int | String {
          if (x > 0) { return 1; }
          return "a";
        }
        print(f(1));
        """
    )

    assert lox.reporter.had_error is False


def test_lambda_missing_return_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int {
          return f(x);
        }
        aplicar(fn(x) { print(x); }, 3);
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Lambda body must return Int." in captured.err


def test_lambda_captures_this_type() -> None:
    lox = check(
        """
        class C {
          var n: Int;

          init(n: Int) {
            this.n = n;
          }

          getter() -> fn() -> Int {
            return fn() => this.n;
          }
        }

        val c = C(9);
        val get = c.getter();
        print(get());
        """
    )

    assert lox.reporter.had_error is False


def test_lambda_wrong_signature_is_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn aplicar(f: fn(Int) -> Int, x: Int) -> Int {
          return f(x);
        }
        aplicar(fn(x: String) => x, 3);
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Expected fn(Int) -> Int, found fn(String) -> Int." in captured.err


def test_function_must_return_on_all_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn f() -> Int {
          print(1);
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Function 'f' must return Int on all paths." in captured.err


def test_bare_return_in_non_nil_function_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn f() -> Int {
          return;
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Expected Int, found Nil." in captured.err


def test_method_must_return_on_all_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C {
          f() -> Int {
            print(1);
          }
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Method 'f' must return Int on all paths." in captured.err


def test_init_must_initialize_every_field(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C {
          var x: Int;
          init() {}
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Field 'x' must be initialized." in captured.err


def test_class_without_init_must_have_field_initializers(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C {
          var x: Int;
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Field 'x' must be initialized." in captured.err


def test_init_can_assign_a_field_in_both_branches() -> None:
    lox = check(
        """
        class C {
          var x: Int;

          init(flag: Bool) {
            if (flag) {
              this.x = 1;
            } else {
              this.x = 2;
            }
          }
        }
        """
    )

    assert lox.reporter.had_error is False


def test_init_assigned_in_only_one_branch_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C {
          var x: Int;

          init(flag: Bool) {
            if (flag) {
              this.x = 1;
            }
          }
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Field 'x' must be initialized." in captured.err


def test_field_initializer_satisfies_initialization() -> None:
    lox = check(
        """
        class C {
          var x: Int = 0;
        }
        """
    )

    assert lox.reporter.had_error is False


def test_var_initialized_with_nil_needs_annotation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check("var x = nil;")
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Can't infer type of 'x' from nil; add an annotation." in captured.err


def test_var_nil_with_annotation_can_receive_values() -> None:
    lox = check(
        """
        var x: Int? = nil;
        x = 1;
        x = nil;
        """
    )

    assert lox.reporter.had_error is False


def test_mutable_var_is_monomorphic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        var x = 1;
        x = 2.0;
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Expected Int, found Float." in captured.err


def test_var_nil_with_any_annotation_allows_any_value() -> None:
    lox = check(
        """
        var x: Any = nil;
        x = 1;
        x = "a";
        """
    )

    assert lox.reporter.had_error is False


def test_val_initialized_with_nil_is_allowed() -> None:
    lox = check(
        """
        val x = nil;
        print(x);
        """
    )

    assert lox.reporter.had_error is False


def test_mutable_field_initialized_with_nil_needs_annotation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C {
          var x = nil;
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert (
        "Field 'x' initialized with nil needs a type annotation." in captured.err
    )


def test_mutable_field_nil_with_annotation_is_clean() -> None:
    lox = check(
        """
        class C {
          var x: Int? = nil;
        }
        """
    )

    assert lox.reporter.had_error is False


def test_immutable_field_initialized_with_nil_is_allowed() -> None:
    lox = check(
        """
        class C {
          val x = nil;
        }
        """
    )

    assert lox.reporter.had_error is False


def test_field_redeclare_same_class(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C {
          var x: Int;
          var x: Int;
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Field 'x' already declared." in captured.err


def test_field_redeclare_superclass(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class A {
          var x: Int;
        }
        class B(A) {
          var x: Int;
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Field 'x' already declared." in captured.err


@pytest.mark.parametrize(
    "source,message",
    [
        (
            """
            class C {
              var x: Int;
              x() -> Nil {}
            }
            """,
            "Field 'x' conflicts with a method.",
        ),
        (
            """
            class A {
              f() -> Nil {}
            }
            class B(A) {
              var f: Int;
            }
            """,
            "Field 'f' conflicts with a method.",
        ),
        (
            """
            class A {
              var f: Int;
            }
            class B(A) {
              f() -> Nil {}
            }
            """,
            "Method 'f' conflicts with a field.",
        ),
    ],
)
def test_field_method_collision(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_override_must_be_compatible(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class A {
          f(x: Int) -> Int { return x; }
        }
        class B(A) {
          f(x: String) -> String { return x; }
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Method 'f' is incompatible with the superclass method" in captured.err
    assert "expected fn(Int) -> Int, found fn(String) -> String." in captured.err


def test_override_can_covary_the_return() -> None:
    lox = check(
        """
        class Animal { init() {} }
        class Dog(Animal) { init() { super.init(); } }
        class A {
          f(a: Animal) -> Animal { return a; }
        }
        class B(A) {
          f(a: Animal) -> Dog { return Dog(); }
        }
        """
    )

    assert lox.reporter.had_error is False


def test_override_is_checked_even_if_superclass_comes_later(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class B(A) {
          f(x: String) -> String { return x; }
        }
        class A {
          f(x: Int) -> Int { return x; }
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Method 'f' is incompatible with the superclass method" in captured.err


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
            "for x in 42 { print(x); }",
            "Can only iterate over a range, a list, a map or a string.",
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


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "class C { fn init() {} } for x in C() {}",
            "is not iterable: define iter() returning an iterator",
        ),
        (
            "class It { fn init() {} fn next() -> Int? { return nil; } }"
            " class C { fn init() {} fn iter(x: Int) -> It { return It(); } }"
            " for x in C() {}",
            "iter() must take no arguments.",
        ),
        (
            "class C { fn init() {} fn iter() -> Int { return 1; } }"
            " for x in C() {}",
            "iter() must return an iterator with next() -> T?",
        ),
        (
            "class It { fn init() {} }"
            " class C { fn init() {} fn iter() -> It { return It(); } }"
            " for x in C() {}",
            "iter() must return an iterator with next() -> T?",
        ),
        (
            "class It { fn init() {} fn next(x: Int) -> Int? { return nil; } }"
            " class C { fn init() {} fn iter() -> It { return It(); } }"
            " for x in C() {}",
            "next() must take no arguments.",
        ),
        (
            "class It { fn init() {} fn next() -> Int { return 1; } }"
            " class C { fn init() {} fn iter() -> It { return It(); } }"
            " for x in C() {}",
            "next() must return T?",
        ),
        (
            "class It { fn init() {} fn next() -> Any? { return nil; } }"
            " class C { fn init() {} fn iter() -> It { return It(); } }"
            " for x in C() {}",
            "next() must return T? with a concrete T.",
        ),
        (
            "class It { fn init() {} fn next() -> Nil { return nil; } }"
            " class C { fn init() {} fn iter() -> It { return It(); } }"
            " for x in C() {}",
            "next() must return T? with a concrete T.",
        ),
    ],
)
def test_iterator_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_union_is_assignable_to_member_and_nil() -> None:
    lox = check(
        """
        fn f(flag: Bool) -> Int | Nil {
          if (flag) { return 1; }
          return nil;
        }
        val x: Int | Nil = f(true);
        print(x);
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
        print(a)
        print(b)
        print(c)
        print(d)
        print(e)
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
        val numero: Float = 1.0 if true else 2.0
        val zero: Int = 0 ?? 1
        val falso: Bool = false ?? true
        val texto: String = "a" ?? "b"
        val nulo: Int = nil ?? 1
        print(nome)
        print(tamanho)
        print(escolha)
        print(numero)
        print(zero)
        print(falso)
        print(texto)
        print(nulo)
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
        ("print(1?.x);", "Only instances have properties."),
        (
            "class C { init() {} } val c: C? = nil; print(c?.naoExiste);",
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


def test_list_types_are_clean() -> None:
    lox = check(
        """
        val xs: List[Int] = [1, 2, 3]
        val ys: List[Float] = [1.0, 2.0]
        val zs: List[Int | String] = [1, "a"]
        val talvez: List[Int?] = [1, nil]
        val empty: List[Int] = []
        val qualquer: Any = []

        xs.push(4)
        val last: Int = xs.pop()
        val first: Int = xs[0]
        xs[0] = 9

        val n: Int = len(xs)
        val m: Int = len("abc")

        val maybe: List[Int]? = nil
        val p: Int? = maybe?.pop()
        val vazioOuLista: List[Int] = maybe ?? []

        fn conta(xs: List[Int]) -> Int {
          return len(xs)
        }

        val vazio = conta([])
        val tres = conta([1, 2, 3])

        for x in xs {
          print(x)
        }

        print(last)
        print(first)
        print(n)
        print(m)
        print(p)
        print(ys)
        print(zs)
        print(empty)
        print(vazio)
        print(tres)
        print(vazioOuLista)
        """
    )

    assert lox.reporter.had_error is False


def test_map_types_are_clean() -> None:
    lox = check(
        """
        val vazio: Map[String, Int] = {}
        val idades: Map[String, Int] = {"Ana": 32, "Bia": 28}
        val misto: Map[Int | String, Int] = {1: 1, "a": 2}
        val qualquer: Any = {}

        idades["Caio"] = 20
        val idade: Int = idades["Ana"]
        val talvez: Int? = idades.get("Zoe")
        val tem: Bool = idades.has("Ana")
        val chaves: List[String] = idades.keys()
        val valores: List[Int] = idades.values()
        val removida: Int = idades.remove("Ana")
        val n: Int = len(idades)

        for nome in idades {
          val chave: String = nome
          print(chave)
        }

        fn total(m: Map[String, Int]) -> Int {
          return len(m)
        }

        fn vazio() -> Map[String, Int] {
          return {}
        }

        val totalIdades = total(idades)
        val totalVazio = total({})
        val mapaVazio = vazio()
        val opcional: Map[String, Int]? = nil
        val opcionalIdade: Int? = opcional?.get("Ana")
        val opcionalTem: Bool? = opcional?.has("Ana")

        print(idade)
        print(talvez)
        print(tem)
        print(chaves)
        print(valores)
        print(removida)
        print(n)
        print(totalIdades)
        print(totalVazio)
        print(opcionalIdade)
        print(opcionalTem)
        print(misto)
        print(qualquer)
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            'val m: Map[String, Int] = {"a": "b"};',
            "Expected Int, found String.",
        ),
        (
            'val m = {"a": 1, "b": "x"};',
            "Map values must have a common type; found Int and String.",
        ),
        (
            'val m = {1: "a", "b": 2};',
            "Map keys must have a common type; found Int and String.",
        ),
        (
            'val m = {1.5: "a"};',
            "Map keys must be String, Int or Bool.",
        ),
        (
            "val m: Map[Float, Int] = {};",
            "Map keys must be String, Int or Bool.",
        ),
        (
            "val m: Map[String, Int] = {}; val n: Map[String, Any] = m;",
            "Expected Map[String, Any], found Map[String, Int].",
        ),
        (
            "val m: Map[String, Int] = {}; print(m[1]);",
            "Expected String, found Int.",
        ),
        (
            'val m: Map[String, Int] = {}; m["a"] = "x";',
            "Expected Int, found String.",
        ),
        (
            "val m: Map[String, Int] = {}; print(m.get(1));",
            "Expected String, found Int.",
        ),
        (
            "val m: Map[String, Int] = {};"
            " for k in m { val n: Int = k; }",
            "Expected Int, found String.",
        ),
        (
            "val m = {};",
            "Can't infer the key and value types of an empty map",
        ),
        (
            "val m: Map[String, Int] = {}; print(m.foo);",
            "Undefined property 'foo'.",
        ),
        (
            "val m: Map[String, Int] = {}; print(m.get());",
            "Expected 1 arguments but got 0.",
        ),
        (
            "val m: Map[String, Int] = {}; print(m.keys(1));",
            "Expected 0 arguments but got 1.",
        ),
        (
            "val m: Map[String, Int] = {}; print(len(3));",
            "Expected a string, a list or a map, found Int.",
        ),
        (
            "val m: Map[String, Int] = {}; print(m.foo());",
            "Undefined property 'foo'.",
        ),
        (
            "val m: Map[String, Int] = {}; print(1[m]);",
            "Only lists and maps can be indexed.",
        ),
    ],
)
def test_map_type_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_narrowing_types_are_clean() -> None:
    lox = check(
        """
        val nome: String? = "Ana"
        if (nome != nil) {
          print(len(nome))
        } else {
          print("sem nome")
        }

        if (nome == nil) {
          print("nada")
        } else {
          print(len(nome))
        }

        if (nome) {
          print(len(nome))
        }

        if (not (nome == nil)) {
          print(len(nome))
        }

        val xs: List[Int]? = [1]
        if (xs != nil) {
          print(len(xs))
          xs.push(2)
          print(xs[0])
        }

        val mapa: Map[String, Int]? = {"a": 1}
        if (mapa != nil) {
          print(len(mapa))
          mapa["b"] = 2
          print(mapa.get("b"))
        }

        var mutavel: String? = "Bia"
        if (mutavel != nil) {
          print(len(mutavel))
        }

        fn primeiro(nome: String?) -> Int {
          if (nome == nil) { return 0 }
          return len(nome)
        }

        fn mapaTamanho(mapa: Map[String, Int]?) -> Int {
          if (mapa == nil) { return 0 }
          return len(mapa)
        }

        val a: String? = "a"
        val b: String? = "b"
        if (a != nil) {
          print(len(a))
        } elif (b != nil) {
          print(len(b))
        } else {
          print("vazio")
        }

        print(primeiro("Ana"))
        print(primeiro(nil))
        print(mapaTamanho(nil))
        print(nome)
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            'val nome: String? = "Ana";'
            " if (nome != nil) { print(1) } else { print(len(nome)); }",
            "Expected a string, a list or a map, found Nil.",
        ),
        (
            'var nome: String? = "Ana";'
            " if (nome != nil) { nome = nil; print(len(nome)); }",
            "Expected a string, a list or a map, found String | Nil.",
        ),
    ],
)
def test_narrowing_limitations(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_methods_still_require_parameter_annotations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        class C { m(x) -> Int { return 1 } }
        print(C().m(1))
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Parameter 'x' needs a type annotation." in captured.err


def test_let_polymorphic_lambda() -> None:
    lox = check(
        """
        val id = fn(x) => x
        val primeiro = fn(x, y) => x

        print(id(1))
        print(id("a"))
        print(primeiro(10, 20))
        print(primeiro("z", "w"))
        """
    )

    assert lox.reporter.had_error is False


def test_generic_lambda_is_not_a_value(capsys: pytest.CaptureFixture[str]) -> None:
    lox = check(
        """
        val id = fn(x) => x
        print(id)
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "can't be used as a value" in captured.err


def test_var_lambda_nao_generaliza(capsys: pytest.CaptureFixture[str]) -> None:
    lox = check(
        """
        var f = fn(x) => x
        print(f(1))
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "needs a type annotation" in captured.err


def test_string_ordering_and_chars() -> None:
    lox = check(
        """
        print("a" < "b")
        print("é" >= "z")
        print(len(chars("ação")))
        val letras: List[String] = chars("ab")
        print(letras[0])
        """
    )

    assert lox.reporter.had_error is False


def test_string_ordering_rejects_mixed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check("print(1 < \"a\")")
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Operands must be numbers." in captured.err


def test_chars_rejects_non_string(capsys: pytest.CaptureFixture[str]) -> None:
    lox = check("print(chars(1))")
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "chars() expects a string, found Int." in captured.err


def test_narrowing_fields_and_indices() -> None:
    lox = check(
        """
        class Pessoa {
          var nome: String?;
          init(nome: String?) { this.nome = nome; }
        }

        val p = Pessoa("Ana")
        if (p.nome != nil) {
          print(len(p.nome))
        }

        val xs: List[Int?] = [1, nil]
        if (xs[0] != nil) {
          print(xs[0] + 1)
        }

        val m: Map[String, String?] = {"k": "v"}
        if (m["k"] != nil) {
          print(len(m["k"]))
        }
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    "source",
    [
        # Atribuir ao campo invalida o refino.
        """
        class P {
          var nome: String?;
          init(n: String?) { this.nome = n; }
        }
        val p = P("a")
        if (p.nome != nil) {
          p.nome = nil
          print(len(p.nome))
        }
        """,
        # Atribuir à raiz invalida o caminho inteiro.
        """
        class P {
          var nome: String?;
          init(n: String?) { this.nome = n; }
        }
        var p = P("a")
        if (p.nome != nil) {
          p = P(nil)
          print(len(p.nome))
        }
        """,
        # Índice dinâmico não refina (sem aliasing).
        """
        val xs: List[Int?] = [1, nil]
        var i = 0
        if (xs[i] != nil) {
          print(len(xs[i]))
        }
        """,
        # Chamada pode mutar o campo por referência.
        """
        class P {
          var nome: String?;
          init(n: String?) { this.nome = n; }
          clear() -> Nil { this.nome = nil; }
        }
        val p = P("a")
        if (p.nome != nil) {
          p.clear()
          print(len(p.nome))
        }
        """,
        # Alias: mutar q.nome invalida o refino de p.nome.
        """
        class P {
          var nome: String?;
          init(n: String?) { this.nome = n; }
        }
        val p = P("a")
        val q = p
        if (p.nome != nil) {
          q.nome = nil
          print(len(p.nome))
        }
        """,
    ],
)
def test_narrowing_field_invalidations(
    source: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Expected a string, a list or a map, found" in captured.err


def test_storage_type_ignores_narrowing() -> None:
    source = """
    val x: Int? = 1
    if (x != nil) {
      print(x)
    }
    """
    reporter = ErrorReporter()
    statements = Parser(
        Scanner(source, reporter).scan_tokens(), reporter=reporter
    ).parse()
    assert statements is not None

    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter)
    checker.check(statements)

    assert reporter.had_error is False
    variables = [
        node
        for node in checker.types
        if isinstance(node, Variable) and node.name.lexeme == "x"
    ]
    narrowed = [node for node in variables if checker.types[node] is INT]
    assert narrowed
    for node in narrowed:
        assert is_nilable(checker.storage_types[node])


def test_storage_type_of_narrowed_field_is_declared() -> None:
    source = """
    class P {
      var nome: String?;
      init(n: String?) { this.nome = n; }
    }
    val p = P("a")
    if (p.nome != nil) {
      print(len(p.nome))
    }
    """
    reporter = ErrorReporter()
    statements = Parser(
        Scanner(source, reporter).scan_tokens(), reporter=reporter
    ).parse()
    assert statements is not None

    Resolver(Interpreter(reporter), reporter).resolve(statements)
    checker = Checker(reporter)
    checker.check(statements)

    assert reporter.had_error is False
    fields = [
        node
        for node in checker.types
        if isinstance(node, Get) and node.name.lexeme == "nome"
    ]
    narrowed = [node for node in fields if checker.types[node] is STRING]
    assert narrowed
    for node in narrowed:
        assert is_nilable(checker.storage_types[node])


def test_narrowing_after_while_uses_the_false_condition(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        var x: Int? = 1
        while (x != nil) {
          x = nil
        }
        print(x + 1)
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Operands must be numbers." in captured.err


def test_narrowing_in_and_and_while() -> None:
    lox = check(
        """
        val nome: String? = "Ana"
        val outro: String? = "Bia"

        if (nome != nil and outro != nil) {
          print(len(nome))
        }

        while (nome != nil) {
          print(len(nome))
        }
        """
    )

    assert lox.reporter.had_error is False


def test_generic_functions_identity_map_filter_and_context() -> None:
    lox = check(
        """
        fn id[T](x: T) -> T {
          return x;
        }

        fn map[T, U](xs: List[T], f: fn(T) -> U) -> List[U] {
          val out: List[U] = [];
          for x in xs {
            out.push(f(x));
          }
          return out;
        }

        fn filter[T](xs: List[T], f: fn(T) -> Bool) -> List[T] {
          val out: List[T] = [];
          for x in xs {
            if (f(x)) {
              out.push(x);
            }
          }
          return out;
        }

        fn first[T](xs: List[T]) -> T? {
          for x in xs {
            return x;
          }
          return nil;
        }

        fn empty[T]() -> List[T] {
          return [];
        }

        fn identity[T](xs: List[T]) -> List[T] {
          return xs;
        }

        print(id(1));
        print(id("a"));
        print(map([1, 2, 3], fn(x) => x * 2));
        print(filter([1, 2, 3], fn(x) => x > 1));
        print(first([1, 2]));
        val vazio: Int? = first([]);
        print(vazio);
        val xs: List[Int] = empty();
        print(xs);
        val nested: List[Int] = identity(empty());
        print(nested);
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "fn soma[T](a: T, b: T) -> T { return a + b; }",
            "Operands must be numbers.",
        ),
        (
            "fn empty[T]() -> List[T] { return []; } print(empty());",
            "Can't infer type argument(s) 'T'.",
        ),
        (
            "fn id[T](x: T) -> T { return x; } val f = id;",
            "Generic function 'id' can't be used as a value yet",
        ),
        (
            "fn id[T](x: T) -> T { return x; }"
            " fn map[T, U](xs: List[T], f: fn(T) -> U) -> List[U]"
            " { return []; }"
            " print(map([1], id));",
            "Generic function 'id' can't be used as a value yet",
        ),
        (
            "fn f[T, T](x: T) -> T { return x; }",
            "Type parameter 'T' is already declared.",
        ),
        (
            "fn f[Int](x: Int) -> Int { return x; }",
            "Type parameter can't be named 'Int'.",
        ),
        (
            "fn grow[T](x: T) -> Int { return grow([x]); } print(grow(1));",
            "Polymorphic recursion is not supported yet",
        ),
        (
            "class Box { get[T](x: T) -> T { return x; } }",
            "Generic methods aren't supported yet.",
        ),
        (
            "fn f[T](m: Map[T, Int]) -> Int { return 0; }",
            "Map keys must be String, Int or Bool.",
        ),
        (
            "fn f[T](x: T) -> T { return 1; }",
            "Expected T, found Int.",
        ),
    ],
)
def test_generic_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_generic_constraints_accept_ord_num_and_interfaces() -> None:
    lox = check(
        """
        fn max[T: Ord](a: T, b: T) -> T {
          return a if a > b else b;
        }

        fn twice[T: Num](x: T) -> T {
          return x + x;
        }

        fn resto[T: Num](a: T, b: T) -> T {
          return a % b;
        }

        interface Nomeavel {
          fn nome() -> String;
        }

        class Pessoa implements Nomeavel {
          fn nome() -> String { return "pessoa"; }
        }

        fn chamar[T: Nomeavel](x: T) -> String {
          return x.nome();
        }

        print(max(1, 2));
        print(max("a", "b"));
        print(twice(2.0));
        print(resto(7, 4));
        print(chamar(Pessoa()));
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "fn f[T: Ord](a: T, b: T) -> T { return a + b; }",
            "needs a 'Num' constraint",
        ),
        (
            "fn f[T: Num](a: T, b: T) -> Bool { return a < b; }",
            "Comparisons need the same type parameter constrained by 'Ord'.",
        ),
        (
            "fn f[T: Desconhecida](x: T) -> T { return x; }",
            "Unknown constraint 'Desconhecida'.",
        ),
        (
            "fn f[T: Num](x: T) -> T { return x / x; }",
            "Operator '/' always returns Float",
        ),
        (
            "fn f[T: Ord + Ord](x: T) -> T { return x; }",
            "Constraint 'Ord' is already declared.",
        ),
        (
            "fn f[T](x: T) -> String { return x.nome(); }",
            "has no method 'nome'; add an interface bound.",
        ),
        (
            "fn max[T: Ord](a: T, b: T) -> T { return a; }"
            " print(max(true, false));",
            "doesn't satisfy constraint 'Ord'.",
        ),
        (
            "fn twice[T: Num](x: T) -> T { return x + x; }"
            " print(twice(\"a\"));",
            "doesn't satisfy constraint 'Num'.",
        ),
        (
            "fn max[T: Ord](a: T, b: T) -> T { return a; }"
            " fn bad[T: Num](a: T, b: T) -> T { return max(a, b); }",
            "doesn't satisfy constraint 'Ord'.",
        ),
    ],
)
def test_generic_constraint_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_generic_function_can_recurse_with_same_type_arguments() -> None:
    lox = check(
        """
        fn length[T](xs: List[T]) -> Int {
          if (len(xs) == 0) { return 0; }
          return 1 + length(xs);
        }

        print(length([1, 2, 3]));
        """
    )

    assert lox.reporter.had_error is False


def test_is_narrows_union_and_else() -> None:
    lox = check(
        """
        fn f(x: Int | String) -> String {
          if (x is Int) {
            return "int";
          } else {
            print(len(x));
          }
          return x;
        }
        """
    )

    assert lox.reporter.had_error is False


def test_is_narrows_until_early_return() -> None:
    lox = check(
        """
        fn f(x: Int | String) -> String {
          if (x is Int) {
            return "int";
          }
          return x;
        }
        """
    )

    assert lox.reporter.had_error is False


def test_is_narrowing_does_not_promote_numbers() -> None:
    lox = check(
        """
        fn soInt(x: Int | Float) -> Int {
          if (x is Float) { return 0; }
          return x;
        }

        fn soFloat(x: Int | Float) -> Float {
          if (x is Float) { return x; }
          return 0.0;
        }
        """
    )

    assert lox.reporter.had_error is False


def test_is_gives_context_to_empty_literals() -> None:
    lox = check(
        """
        print([] is List[Int]);
        print({} is Map[String, Int]);
        """
    )

    assert lox.reporter.had_error is False


def test_is_narrows_class_to_subclass() -> None:
    lox = check(
        """
        class Animal { init() {} }
        class Dog(Animal) {
          init() { super.init(); }
          bark() -> String { return "woof"; }
        }

        fn fala(a: Animal) -> String {
          if (a is Dog) {
            return a.bark();
          }
          return "...";
        }
        """
    )

    assert lox.reporter.had_error is False


def test_is_narrows_any_to_list() -> None:
    lox = check(
        """
        val xs: Any = [1, 2];
        if (xs is List[Int]) {
          print(xs[0] + 1);
        }
        """
    )

    assert lox.reporter.had_error is False


def test_is_rejects_function_types(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        fn f(x: Any) -> Bool {
          return x is fn(Int) -> Int;
        }
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "is doesn't support this type yet." in captured.err


def test_is_result_is_bool() -> None:
    lox = check(
        """
        val b: Bool = 1 is Int;
        print(b);
        """
    )

    assert lox.reporter.had_error is False


def test_interpolation_types_are_clean() -> None:
    lox = check(
        """
        val nome = "Ana"
        val oi: String = "Oi, ${nome}!"
        val conta: String = "1 + 2 = ${1 + 2}"
        val mapa: String = "mapa: ${{"a": 1}}"
        val lista: String = "lista: ${[1, 2]}"
        val n: Int = len("${nome}")
        print(oi)
        print(conta)
        print(mapa)
        print(lista)
        print("${nome}${n}")
        print("${nil}")
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            'val i: Int = "x ${1}";',
            "Expected Int, found String.",
        ),
        (
            "print(\"${naoexiste}\");",
            "Undefined variable 'naoexiste'.",
        ),
        (
            "print(\"${[1, \"a\"]}\");",
            "List elements must have a common type; found Int and String.",
        ),
        (
            "print(\"${}\");",
            "Expect expression.",
        ),
    ],
)
def test_interpolation_type_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "val xs: List[Int] = [1]; val ys: List[Float] = xs;",
            "Expected List[Float], found List[Int].",
        ),
        (
            "val xs: List[Int] = [1]; val ys: List[Any] = xs;",
            "Expected List[Any], found List[Int].",
        ),
        (
            'val xs = [1, "a"];',
            "List elements must have a common type; found Int and String.",
        ),
        (
            "val xs = [];",
            "Can't infer the element type of an empty list",
        ),
        (
            'val xs: List[Int] = [1]; xs.push("a");',
            "Expected Int, found String.",
        ),
        (
            "val xs: List[Int] = [1]; print(xs[\"a\"]);",
            "List index must be an integer, found String.",
        ),
        (
            'val xs: List[Int] = [1]; xs[0] = "a";',
            "Expected Int, found String.",
        ),
        (
            'val xs: List[Int] = [1, 2.0];',
            "Expected Int, found Float.",
        ),
        (
            "print(len(3));",
            "Expected a string, a list or a map, found Int.",
        ),
        (
            "val xs: List[Int] = [1]; print(xs.foo);",
            "Undefined property 'foo'.",
        ),
        (
            "val xs: List[Int] = [1];"
            " for x in xs { val y: String = x; }",
            "Expected String, found Int.",
        ),
        (
            'fn f(xs: List[Int]) -> Int { return len(xs); } f([1, "a"]);',
            "Expected Int, found String.",
        ),
        (
            "fn len(x: Int) -> Int { return x; }",
            "Can't redefine builtin 'len'.",
        ),
        (
            "class range {}",
            "Can't redefine builtin 'range'.",
        ),
        (
            "print(str(1, 2));",
            "Expected 1 arguments but got 2.",
        ),
    ],
)
def test_list_type_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_clock_is_a_regular_name_after_removal() -> None:
    lox = check("val clock = 1; print(clock);")

    assert lox.reporter.had_error is False


def test_builtin_shadowing_is_local_only() -> None:
    lox = check(
        """
        fn f(len: Int) -> Int {
          return len;
        }

        val s: String = str(1);
        val r: String = repr([1]);
        val vazio: Int = len([]);
        val misto: String = str([1, "a"]);
        print(f(3));
        print(s);
        print(r);
        print(vazio);
        print(misto);
        """
    )

    assert lox.reporter.had_error is False


def test_casts_parse_and_math_are_typed() -> None:
    lox = check(
        """
        val i = 3.9 as Int;
        val f = 3 as Float;
        val n: Int? = Int.parse("42");
        val g: Float? = Float.parse("3.5");
        val a = math.abs(-3);
        val b = math.abs(-3.5);
        val c = math.min(1, 2.0);
        val d = math.floor(3.9);
        val e = math.sqrt(9.0);
        val h = math.clamp(10, 0, 5);
        val ci: Int = math.min(1, 2);
        val cf: Float = math.min(1, 2.0);
        val cd: Int = math.floor(3.9);
        print(i); print(f); print(n); print(g);
        print(a); print(b); print(c); print(d); print(e); print(h);
        print(ci); print(cf); print(cd);
        """
    )

    assert lox.reporter.had_error is False


# --- promoção Int -> Float é só aritmética (ADR-0059) -------------------------


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("val y: Float = 2;", "Expected Float, found Int. Write `2.0` or use `2 as Float`."),
        (
            "var x: Float = 1.5; x = 2;",
            "Expected Float, found Int. Write `2.0` or use `2 as Float`.",
        ),
        (
            "fn f(x: Float) -> Int { return 0; } f(2);",
            "Argument 1: Expected Float, found Int.",
        ),
        ("fn f() -> Float { return 2; }", "Expected Float, found Int."),
        (
            "fn f(x: Float = 1) -> Float { return x; }",
            "Expected Float, found Int.",
        ),
        ("val xs: List[Float] = [1];", "Expected Float, found Int."),
        ("val m: Map[String, Float] = { \"a\": 1 };", "Expected Float, found Int."),
        (
            "class P { var x: Float; init() { this.x = 2; } }",
            "Expected Float, found Int.",
        ),
    ],
)
def test_int_float_promotion_is_rejected_outside_arithmetic(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """Kotlin-like: anotação/atribuição/argumento/retorno exigem `Float` explícito."""
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_arithmetic_promotion_still_works() -> None:
    lox = check(
        """
        val a = 1 + 2.0;
        val b = 4 / 2;
        val c = 1 == 1.0;
        val d = 1 < 2.5;
        val e: Float = 2 ** 0.5;
        """
    )

    assert lox.reporter.had_error is False


def test_explicit_conversion_is_the_escape_hatch() -> None:
    lox = check(
        """
        val a: Float = 2 as Float;
        var b: Float = 1.5;
        b = 2 as Float;
        fn f(x: Float = 1.0) -> Float { return x; }
        print(a); print(b); print(f());
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    "source, message",
    [
        ('val x = "1" as Int;', "Can't cast String to Int."),
        ("val x = 1 as Int | String;", "as doesn't support union types"),
        ('val x = math.abs("1");', "math.abs() expects numbers."),
        ('val x = math.floor("1");', "Expected Float, found String."),
        ("val x = Int.parse(1);", "Expected String, found Int."),
        ("val x = Float.parse(1);", "Expected String, found Int."),
    ],
)
def test_cast_parse_and_math_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_tuple_inference_variance_and_operations() -> None:
    lox = check(
        """
        class Animal {}
        class Dog(Animal) {}

        val dog: (Dog, Int) = (Dog(), 1)
        val animal: (Animal, Int) = dog
        print(animal[1])
        print(len((1, "a", true)))
        print((1, "a") == (1.0, "a"))
        print((1, (2, "x"))[1][1])
        """
    )

    assert lox.reporter.had_error is False


def test_tuple_destructuring_with_annotation_and_var() -> None:
    lox = check(
        """
        val (a, b) = (1, "x")
        print(a + 1)
        print(len(b))
        var (c, d): (Int, String) = (2, "y")
        c = c + 1
        print(d)
        """
    )

    assert lox.reporter.had_error is False


def test_tuple_any_can_be_destructured_with_annotation() -> None:
    lox = check(
        """
        val x: Any = (1, "a")
        val (a, b): (Int, String) = x
        print(a + 1)
        print(len(b))
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("print((1, 2)[2])", "Tuple index 2 out of bounds for length 2."),
        (
            "val (a, b) = (1, 2, 3)",
            "Destructuring expects 2 values, found 3.",
        ),
        (
            "val (a, b) = [1, 2]",
            "Can only destructure tuples, found List[Int].",
        ),
        (
            "val x: Any = (1, 2)\nval (a, b) = x",
            "Can't destructure Any; add a tuple annotation.",
        ),
        (
            "val (a, a) = (1, 2)",
            "Variable 'a' is declared twice in this destructuring.",
        ),
        (
            "val (a, (b, a)) = (1, (2, 3))",
            "Variable 'a' is declared twice in this destructuring.",
        ),
        (
            "val (a, (b, c)) = (1, (2, 3, 4))",
            "Destructuring expects 2 values, found 3.",
        ),
        (
            "val (a, (b, c)) = (1, 2)",
            "Can only destructure tuples, found Int.",
        ),
        (
            'val (a, (b, c)): (Int, (String, Bool)) = (1, (2, true))',
            "Expected String, found Int.",
        ),
        (
            "print((1, 2)[\"a\"])",
            "Tuple index must be an integer, found String.",
        ),
        (
            'val (a, b): (Int, String) = (1, 2)',
            "Expected String, found Int.",
        ),
    ],
)
def test_tuple_checker_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_tuple_dynamic_index_is_a_union(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        val t: (Int, String) = (1, "a")
        var i = 0
        print(t[i] + 1)
        """
    )
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Operands must be numbers." in captured.err


def test_tuple_iteration_is_and_as() -> None:
    lox = check(
        """
        val t = (1, "a")
        for x in t { print(x) }
        print((1, "a") is (Int, String))
        val any: Any = (2, "b")
        val (n, s) = any as (Int, String)
        print(n)
        print(s)
        val x: Any = (3, "c")
        if (x is (Int, String)) { print(x[0] + 1) }
        """
    )

    assert lox.reporter.had_error is False


def test_tuple_as_incompatible_is_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check("print((1, \"a\") as (Int, Int))")
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Can't cast (Int, String) to (Int, Int)." in captured.err


def test_generic_class_inference_members_and_interop() -> None:
    lox = check(
        """
        class Box[T] {
          var value: T
          init(value: T) { this.value = value }
          get() -> T { return this.value }
          set(v: T) -> Nil { this.value = v }
        }
        class Pair[A, B] {
          val first: A
          val second: B
          init(first: A, second: B) { this.first = first; this.second = second }
          swap() -> Pair[B, A] { return Pair(this.second, this.first) }
        }
        fn first[T](b: Box[T]) -> T { return b.get() }
        fn make[T](x: T) -> Box[T] { return Box(x) }

        val b: Box[Int] = Box(1)
        b.set(2)
        print(b.get())
        print(first(Box(7)))
        print(make("x").get())
        val p = Pair(1, "a")
        val q: Pair[String, Int] = p.swap()
        print(q.first)
        """
    )

    assert lox.reporter.had_error is False


def test_generic_class_without_init_needs_annotation() -> None:
    lox = check(
        """
        class Empty[T] {}
        val e: Empty[Int] = Empty()
        print(e)
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "class Box[T] { var v: T\n  init(v: T) { this.v = v } }\nval a: Box[Int] = Box(1)\n"
            "val b: Box[Any] = a",
            "Expected Box[Any], found Box[Int].",
        ),
        (
            "class Box[T] { var v: T\n  init(v: T) { this.v = v } }\nval b: Box = Box(1)",
            "Class 'Box' needs 1 type argument(s)",
        ),
        (
            "class Box[T] { var v: T\n  init(v: T) { this.v = v } }\nval b: Box[Int, String] = Box(1)",
            "Box expects 1 type argument(s), got 2.",
        ),
        (
            "class Empty[T] {}\nval e = Empty()",
            "Can't infer type argument(s) 'T' for 'Empty'",
        ),
        (
            "class Box[T] { var v: T\n  init(v: T) { this.v = v } }\nval a: Any = 1\nval b = Box(a)",
            "Can't infer type argument 'T' from Any.",
        ),
        (
            """class Box[T] { var v: T
  init(v: T) { this.v = v } }
print(Box(1) is Box[Int])""",
            "is doesn't support type arguments on classes yet.",
        ),
        (
            """class Box[T] { var v: T
  init(v: T) { this.v = v } }
print(Box(1) as Box[Int])""",
            "as doesn't support type arguments on classes yet.",
        ),
        (
            "class Box[T] {}\nclass C(Box[Int]) {}",
            "Generic superclasses aren't supported yet.",
        ),
    ],
)
def test_generic_class_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_enum_match_and_result() -> None:
    lox = check(
        """
        enum Cor { Vermelho, Verde, Azul }
        enum Shape { Circle(Float), Rect(Float, Float) }

        val c = Cor.Verde
        val s: Shape = Shape.Circle(2.0)
        val area = match s {
          Shape.Circle(r) => 3.14 * r * r
          Shape.Rect(w, h) => w * h
        }
        print(area)

        fn parse(n: Int) -> Result[Int, String] {
          if (n > 0) { return Result.Ok(n) }
          return Result.Err("negativo")
        }
        val r = parse(3)
        val msg = match r {
          Result.Ok(v) => "ok ${v}"
          Result.Err(e) => "erro ${e}"
        }
        print(msg)
        print(c == Cor.Verde)
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "enum Cor { Vermelho, Verde }\n"
            "print(match Cor.Vermelho { Cor.Vermelho => 1 })",
            "Non-exhaustive match; missing Cor.Verde.",
        ),
        (
            "enum Cor { Vermelho, Verde }\n"
            "print(match Cor.Vermelho { Cor.Vermelho => 1, Cor.Vermelho => 2 })",
            "Unreachable match arm.",
        ),
        (
            "enum Cor { Vermelho, Verde }\n"
            "print(match Cor.Vermelho { _ => 1, Cor.Verde => 2 })",
            "Unreachable match arm.",
        ),
        ("print(match 1 { _ => 1 })", "match requires an enum value"),
        (
            "enum Cor { Vermelho }\n"
            "print(match Cor.Vermelho { Cor.Verde => 1 })",
            "Unknown variant 'Verde'.",
        ),
        (
            """enum E { A }
val x = E.A
print(x is E[Int])""",
            "Enum 'E' isn't generic.",
        ),
        (
            "enum E { A, A }",
            "Variant 'A' is already declared.",
        ),
        (
            "enum Result { A }",
            "Can't redefine builtin 'Result'.",
        ),
        (
            "val r = Result.Ok(1)",
            "Can't infer type argument(s) 'E'.",
        ),
        (
            "enum Shape { Circle(Float) }\nval s = Shape.Circle(\"x\")",
            "Argument 1: Expected Float, found String.",
        ),
        (
            "enum Cor { Vermelho }\n"
            "print(match Cor.Vermelho { Cor.Vermelho(x) => 1 })",
            "expects 0 binding(s), got 1.",
        ),
    ],
)
def test_enum_match_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_exceptions_typed_catch_and_finally() -> None:
    lox = check(
        """
        class MyError(Exception) {
          init(msg: String) { this.message = msg }
        }

        fn first() -> Int {
          try {
            raise MyError("x")
          } except MyError as e {
            return 1
          } finally {
            print("fim")
          }
        }

        try { print(1 / 0) }
        except RuntimeError as e { print(e.message) }

        try { raise MyError("x") }
        except RuntimeError as e { print("runtime") }
        except Exception as e { print("generico") }

        print(first())
        print(Exception("base").message)
        print(RuntimeError("runtime").message)
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        ("raise 1;", "Can only raise Exception instances, found Int."),
        ("raise;", "Can't re-raise outside of an except block."),
        (
            "try { print(1) } except Foo as e { print(e) }",
            "Unknown exception type 'Foo'.",
        ),
        (
            "class X {}\nraise X();",
            "Can only raise Exception instances, found X.",
        ),
        (
            "try { print(1) } except Exception as e { print(e) } "
            "except RuntimeError as e { print(e) }",
            "Catch-all 'Exception' must be the last handler.",
        ),
        ("try { print(1) }", "Try needs at least one 'except' or 'finally'."),
    ],
)
def test_exception_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_interfaces_defaults_superclass_and_types_are_clean() -> None:
    lox = check(
        """
        interface Forma {
          area() -> Int
          fn nome() -> String { return "forma" }
          fn descricao() -> String { return "${this.nome()}:${this.area()}" }
        }

        interface Nomeavel {
          fn nome() -> String
        }

        class Base {
          fn nome() -> String { return "base" }
        }

        class Filho(Base) implements Forma {
          fn area() -> Int { return 7 }
        }

        class Outro implements Forma, Nomeavel {
          fn area() -> Int { return 2 }
          fn nome() -> String { return "outro" }
        }

        class Caixa[T] implements Nomeavel {
          val valor: T
          fn init(valor: T) { this.valor = valor }
          fn nome() -> String { return "caixa" }
        }

        val f: Forma = Filho()
        val g: Forma? = nil
        val xs: List[Forma] = [f, Outro()]
        val c: Nomeavel = Caixa(1)

        fn escolher(x: Forma) -> Forma { return x }

        class Concreto implements Forma {
          fn area() -> Int { return 3 }
        }

        fn fabrica() -> Forma { return Concreto() }
        var atual: Forma = fabrica()
        atual = Outro()

        val implements = 1
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "interface I { m() -> Int }\nclass C implements I { }",
            "Class 'C' must implement method 'm' of interface 'I'.",
        ),
        (
            "interface I { m(x: Int) -> Int }\n"
            "class C implements I { fn m(x: String) -> Int { return 1 } }",
            "Method 'm' is incompatible with interface 'I'",
        ),
        (
            "interface I { m(x: Int) -> Int }\n"
            "class C implements I { fn m(x: Any) -> Int { return 1 } }",
            "Method 'm' is incompatible with interface 'I'",
        ),
        (
            "interface A { m() -> Int { return 1 } }\n"
            "interface B { m() -> Int { return 2 } }\n"
            "class C implements A, B { }",
            "Class 'C' must override 'm'",
        ),
        (
            "class C implements Nope { }",
            "Unknown interface 'Nope'.",
        ),
        (
            "interface I { m() -> Int }\n"
            "class C implements I, I { fn m() -> Int { return 1 } }",
            "Interface 'I' is already implemented.",
        ),
        (
            """interface I { m() -> Int }
print(I)""",
            "Interface 'I' is a type, not a value.",
        ),
        (
            "interface I { m() -> Int }\n"
            "class C implements I { fn m() -> Int { return 1 } }\n"
            "print(C() is I)",
            "Interface types aren't supported in 'is' yet.",
        ),
        (
            "interface I { m() -> Int }\n"
            "class C implements I { fn m() -> Int { return 1 } }\n"
            "print(C() as I)",
            "Interface types aren't supported in 'as' yet.",
        ),
        (
            "fn f() -> Int { { interface I { m() -> Int } } return 1 }",
            "Interfaces must be declared at top level.",
        ),
        (
            "class C implements I { fn m() -> Int { return 1 } }\n"
            "interface I { m() -> Int }",
            "Interface 'I' must be declared before class 'C'.",
        ),
        (
            "interface I { fn init() { } }",
            "Interfaces can't declare 'init'.",
        ),
        (
            "interface I { fn m() -> Int { return this.x } }",
            "Interface 'I' has no method 'x'.",
        ),
        (
            "interface I { fn m() -> Int { } }",
            "Method 'm' must return Int on all paths.",
        ),
        (
            "interface I { fn m() -> Int { return 1 } }\n"
            "class C implements I { val m: Int = 1 }",
            "Field 'm' conflicts with an interface method.",
        ),
    ],
)
def test_interface_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "fn f(...xs: Int = 1) -> Int { return 1; }",
            "Variadic parameter can't have a default value.",
        ),
        (
            "class C { fn init(...xs: Int) {} } val c = C(1);",
            "Variadic parameters aren't supported in 'init' yet.",
        ),
        (
            "fn f(a: Int) -> Int { return a; }"
            " val xs = [1]; print(f(...xs));",
            "Spread arguments are only supported for variadic functions.",
        ),
        (
            "fn f(a: Int, ...xs: Int) -> Int { return a; }"
            " print(f(...[1, 2]));",
            "Spread arguments only fill the variadic parameter; "
            "pass the fixed parameters explicitly.",
        ),
        (
            "fn f(...xs: Int) -> Int { return 0; }"
            " val xs = [\"a\"]; print(f(...xs));",
            "Expected List[Int], found List[String].",
        ),
        (
            "fn f(...xs: Int) -> Int { return 0; } print(f(1, \"a\"));",
            "Expected Int, found String.",
        ),
        (
            "fn f(...xs: Int) -> Int { return 0; } print(f(nil));",
            "Expected Int, found Nil.",
        ),
    ],
)
def test_variadic_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err


def test_type_aliases_are_transparent() -> None:
    lox = check(
        """
        type UserId = Int
        type Nomes = List[String]
        type Callback = fn(Int) -> Int
        type PessoaId = Pessoa

        class Pessoa {
          val id: UserId
          fn init(id: UserId) { this.id = id }
        }

        fn eco(id: UserId) -> UserId { return id }
        val nomes: Nomes = ["a"]
        val cb: Callback = fn(x) => x
        val p: PessoaId = Pessoa(1)
        print(eco(p.id))
        print(nomes)
        print(cb(1))
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "type A = Int; class A { fn init() {} }",
            "Name 'A' is already declared.",
        ),
        (
            "type A = B; type B = A; val x: A = 1",
            "Type alias 'A' is recursive.",
        ),
        (
            "type A = Nope; val x: A = 1",
            "Unknown type 'Nope'.",
        ),
        (
            "type A = Int; val x: A[Int] = 1",
            "Type alias 'A' isn't generic.",
        ),
        (
            "fn f() { type A = Int }",
            "Type aliases must be declared at the top level.",
        ),
        (
            "type A = Int; fn f[T: A](x: T) -> T { return x }",
            "Type alias 'A' isn't an interface.",
        ),
    ],
)
def test_type_alias_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    lox = check(source)
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert message in captured.err

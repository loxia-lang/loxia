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

        print par(4);
        """
    )

    assert lox.reporter.had_error is False


def test_top_level_call_before_declaration_is_an_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check(
        """
        print f();
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

        print y;
        print g(4);
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
        print a.nome;
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
        print a;
        print b;
        print c(3);
        """
    )

    assert lox.reporter.had_error is False


def test_lambda_without_context_needs_annotations(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = check("val f = fn(x) => x * 2;")
    captured = capsys.readouterr()

    assert lox.reporter.had_error is True
    assert "Parameter 'x' needs a type annotation" in captured.err


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
        print f(1);
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
        aplicar(fn(x) { print x; }, 3);
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
        print get();
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
          print 1;
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
            print 1;
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
            'for x in 42 { print x; }',
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


def test_list_types_are_clean() -> None:
    lox = check(
        """
        val xs: List[Int] = [1, 2, 3]
        val ys: List[Float] = [1, 2.0]
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
          print x
        }

        print last
        print first
        print n
        print m
        print p
        print ys
        print zs
        print empty
        print vazio
        print tres
        print vazioOuLista
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
          print chave
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

        print idade
        print talvez
        print tem
        print chaves
        print valores
        print removida
        print n
        print totalIdades
        print totalVazio
        print opcionalIdade
        print opcionalTem
        print misto
        print qualquer
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
            "val m: Map[String, Int] = {}; print m[1];",
            "Expected String, found Int.",
        ),
        (
            'val m: Map[String, Int] = {}; m["a"] = "x";',
            "Expected Int, found String.",
        ),
        (
            'val m: Map[String, Int] = {}; print m.get(1);',
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
            "val m: Map[String, Int] = {}; print m.foo;",
            "Undefined property 'foo'.",
        ),
        (
            "val m: Map[String, Int] = {}; print m.get();",
            "Expected 1 arguments but got 0.",
        ),
        (
            "val m: Map[String, Int] = {}; print m.keys(1);",
            "Expected 0 arguments but got 1.",
        ),
        (
            "val m: Map[String, Int] = {}; print len(3);",
            "Expected a string, a list or a map, found Int.",
        ),
        (
            "val m: Map[String, Int] = {}; print m.foo();",
            "Undefined property 'foo'.",
        ),
        (
            "val m: Map[String, Int] = {}; print 1[m];",
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
          print len(nome)
        } else {
          print "sem nome"
        }

        if (nome == nil) {
          print "nada"
        } else {
          print len(nome)
        }

        if (nome) {
          print len(nome)
        }

        if (!(nome == nil)) {
          print len(nome)
        }

        val xs: List[Int]? = [1]
        if (xs != nil) {
          print len(xs)
          xs.push(2)
          print xs[0]
        }

        val mapa: Map[String, Int]? = {"a": 1}
        if (mapa != nil) {
          print len(mapa)
          mapa["b"] = 2
          print mapa.get("b")
        }

        var mutavel: String? = "Bia"
        if (mutavel != nil) {
          print len(mutavel)
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
          print len(a)
        } elif (b != nil) {
          print len(b)
        } else {
          print "vazio"
        }

        print primeiro("Ana")
        print primeiro(nil)
        print mapaTamanho(nil)
        print nome
        """
    )

    assert lox.reporter.had_error is False


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            'val nome: String? = "Ana";'
            " if (nome != nil) { print 1 } else { print len(nome); }",
            "Expected a string, a list or a map, found Nil.",
        ),
        (
            'var nome: String? = "Ana";'
            " if (nome != nil) { nome = nil; print len(nome); }",
            "Expected a string, a list or a map, found String | Nil.",
        ),
        (
            'val nome: String? = "Ana"; val outro: String? = "Bia";'
            " if (nome != nil and outro != nil) { print len(nome); }",
            "Expected a string, a list or a map, found String | Nil.",
        ),
        (
            'val nome: String? = "Ana";'
            " while (nome != nil) { print len(nome); }",
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


def test_interpolation_types_are_clean() -> None:
    lox = check(
        """
        val nome = "Ana"
        val oi: String = "Oi, ${nome}!"
        val conta: String = "1 + 2 = ${1 + 2}"
        val mapa: String = "mapa: ${{"a": 1}}"
        val lista: String = "lista: ${[1, 2]}"
        val n: Int = len("${nome}")
        print oi
        print conta
        print mapa
        print lista
        print "${nome}${n}"
        print "${nil}"
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
            'print "${naoexiste}";',
            "Undefined variable 'naoexiste'.",
        ),
        (
            'print "${[1, "a"]}";',
            "List elements must have a common type; found Int and String.",
        ),
        (
            'print "${}";',
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
            'val xs: List[Int] = [1]; print xs["a"];',
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
            "print len(3);",
            "Expected a string, a list or a map, found Int.",
        ),
        (
            "val xs: List[Int] = [1]; print xs.foo;",
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
            "val clock = 1;",
            "Can't redefine builtin 'clock'.",
        ),
        (
            "class range {}",
            "Can't redefine builtin 'range'.",
        ),
        (
            "print str(1, 2);",
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
        print f(3);
        print s;
        print r;
        print vazio;
        print misto;
        """
    )

    assert lox.reporter.had_error is False

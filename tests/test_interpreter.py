from __future__ import annotations

import pytest

from main import Loxia


def execute(lox: Loxia, source: str, capsys: pytest.CaptureFixture[str]) -> tuple[list[str], str]:
    lox.run(source)
    captured = capsys.readouterr()

    return captured.out.splitlines(), captured.err


def run(source: str, capsys: pytest.CaptureFixture[str]) -> tuple[list[str], str]:
    return execute(Loxia(), source, capsys)


def test_prints_literals(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run('print(1); print(true); print(nil); print("a");', capsys)

    assert stdout == ["1", "true", "nil", "a"]
    assert stderr == ""


def test_arithmetic_and_stringify(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(1 + 2 * 3); print(10 / 4); print(2 * 5);", capsys)

    assert stdout == ["7", "2.5", "10"]


def test_number_literals_keep_int_and_float(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(1); print(1.0); print(1e9);", capsys)

    assert stdout == ["1", "1.0", "1000000000.0"]


def test_int_promotes_to_float_and_division_is_float(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, _ = run("print(1 + 2.0); print(1 / 2); print(4 / 2); print(2 * 3);", capsys)

    assert stdout == ["3.0", "0.5", "2.0", "6"]


def test_modulo_truncates_toward_zero(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(7 % 3); print(-7 % 3); print(7 % -3); print(7.5 % 2);", capsys)

    assert stdout == ["1", "-1", "1", "1.5"]


def test_numeric_equality_promotes_int_to_float(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, _ = run("print(1 == 1.0); print(1 != 1.0); print(1 == 2.0);", capsys)

    assert stdout == ["true", "false", "false"]


def test_nil_aware_and_conditional_short_circuit(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, _ = run(
        """
        var calls = 0
        fn f() {
          calls = calls + 1
          return 2
        }

        print(1 if true else f())
        print((f() if false else 9))
        print(0 ?? f())
        print(false ?? true)
        print(calls)

        class C {
          m(x) {
            return x
          }
        }
        val c = nil
        print(c?.m(f()) ?? "nada")
        print(calls)
        """,
        capsys,
    )

    assert stdout == ["1", "9", "0", "false", "0", "nada", "0"]


def test_int_arithmetic_wraps_on_overflow(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(9223372036854775807 + 1); print(-9223372036854775807 - 2);", capsys)

    assert stdout == ["-9223372036854775808", "9223372036854775807"]


def test_float_stringify_round_trips(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(0.1 + 0.2); print(-0.0); print(1.0);", capsys)

    assert stdout == ["0.30000000000000004", "-0.0", "1.0"]


def test_utf8_strings_use_code_points(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run('print(len("ação")); print("ação");', capsys)

    assert stdout == ["4", "ação"]
    assert stderr == ""


def test_for_in_iterates_range_and_string(capsys: pytest.CaptureFixture[str]) -> None:
    source = 'for i in 0..3 { print(i); } for c in "ab" { print(c); }'

    stdout, stderr = run(source, capsys)

    assert stdout == ["0", "1", "2", "a", "b"]
    assert stderr == ""


def test_for_in_supports_descending_and_empty_ranges(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = "for i in range(3, 0, -1) { print(i); } for i in 5..2 { print(i); }"

    stdout, _ = run(source, capsys)

    assert stdout == ["3", "2", "1"]


def test_for_in_loop_variable_is_immutable(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Loxia()
    stdout, stderr = execute(lox, "for i in 0..3 { i = 1; }", capsys)

    assert stdout == []
    assert "'i' is immutable" in stderr
    assert lox.reporter.had_error


def test_for_in_closure_captures_iteration_value(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = """
    var f;
    for i in 0..3 {
      fn captura() { print(i); }
      if (i == 1) { f = captura; }
    }
    f();
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["1"]
    assert stderr == ""


def test_range_value_stringify_and_equality(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(0..3); print(range(3, 0, -1)); print((0..3) == (0..3));", capsys)

    assert stdout == ["<range 0..3>", "<range 3..0 step -1>", "true"]


def test_variables_and_uninitialized_default_to_nil(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, _ = run("var a = 1; var b; print(a); print(b);", capsys)

    assert stdout == ["1", "nil"]


def test_block_reads_outer_scope_and_shadows(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    var a = "global";
    {
      var a = "bloco";
      print(a);
      { print(a); }
    }
    print(a);
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["bloco", "bloco", "global"]
    assert stderr == ""


def test_assignment_reaches_enclosing_scope(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("var a = 1; { var b = 2; a = b + 10; } print(a);", capsys)

    assert stdout == ["12"]


def test_while_and_for_loops(capsys: pytest.CaptureFixture[str]) -> None:
    while_source = "var i = 0; while (i < 3) { print(i); i = i + 1; }"
    for_source = "for (var i = 0; i < 3; i = i + 1) print(i);"

    assert run(while_source, capsys)[0] == ["0", "1", "2"]
    assert run(for_source, capsys)[0] == ["0", "1", "2"]


def test_not_negates_truthiness(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(not nil); print(not true); print(not not 0);", capsys)

    assert stdout == ["true", "false", "true"]


def test_zero_and_empty_string_are_truthy(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run('if (0) print("zero"); if ("") print("vazia");', capsys)

    assert stdout == ["zero", "vazia"]


def test_logical_operators_short_circuit(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run("print(false and (1 / 0)); print(true or (1 / 0));", capsys)

    assert stdout == ["false", "true"]
    assert stderr == ""


def test_undefined_variable_is_a_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Loxia()
    stdout, stderr = execute(lox, "print(naoexiste);", capsys)

    assert stdout == []
    assert "Undefined variable 'naoexiste'." in stderr
    assert lox.reporter.had_runtime_error


def test_runtime_error_stops_execution(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run('print("antes"); print(1 / 0); print("depois");', capsys)

    assert stdout == ["antes"]
    assert "Division by zero" in stderr


def test_syntax_error_does_not_execute(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()
    stdout, _ = execute(lox, "print(1 +) ;", capsys)

    assert stdout == []
    assert lox.reporter.had_error


def test_errors_do_not_leak_between_runs(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()

    execute(lox, "print(naoexiste);", capsys)
    assert lox.reporter.had_runtime_error is True

    stdout, stderr = execute(lox, 'print("ok");', capsys)

    assert stdout == ["ok"]
    assert stderr == ""
    assert lox.reporter.had_runtime_error is False


def test_equality_between_bool_and_number(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print(true == 1); print(1 == 1);", capsys)

    assert stdout == ["false", "true"]


def test_functions_and_closures(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    fn makeCounter() {
      var i = 0;
      fn count() {
        i = i + 1;
        print(i);
      }
      return count;
    }

    var counter = makeCounter();
    counter();
    counter();
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["1", "2"]
    assert stderr == ""


def test_lambdas_capture_and_return(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    fn makeAdder(n: Int) -> fn(Int) -> Int {
      return fn(x: Int) => x + n;
    }

    val add2 = makeAdder(2);
    print(add2(5));

    val dobro = fn(x: Int) => x * 2;
    print(dobro(4));

    fn outer() -> Int {
      val inner = fn() -> Int { return 5; };
      return inner() + 1;
    }
    print(outer());
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["7", "8", "6"]
    assert stderr == ""


def test_lambda_block_body_returns(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    val f = fn(x: Int) -> Int {
      if (x < 0) { return 0; }
      return x;
    }

    print(f(-2));
    print(f(3));
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["0", "3"]
    assert stderr == ""


def test_lambda_captures_this(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
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

    stdout, stderr = run(source, capsys)

    assert stdout == ["9"]
    assert stderr == ""


def test_is_runtime_type_test(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    print(1 is Int);
    print(1 is Float);
    print(1.0 is Float);
    print(true is Bool);
    print(1 is Bool);
    print(nil is Nil);
    print("a" is String);
    print([1, 2] is List[Int]);
    val xs: List[Int | String] = [1, "a"];
    print(xs is List[Int]);
    print({"a": 1} is Map[String, Int]);
    print(0..3 is Range);
    print(nil is Int?);
    print(1 is Int?);
    print("a" is Int?);

    class Animal { init() {} }
    class Dog(Animal) { init() { super.init(); } }
    print(Animal() is Animal);
    print(Dog() is Animal);
    print(Animal() is Dog);
    print(Animal is Animal);
    """

    stdout, stderr = run(source, capsys)

    assert stdout == [
        "true",
        "false",
        "true",
        "true",
        "false",
        "true",
        "true",
        "true",
        "false",
        "true",
        "true",
        "true",
        "true",
        "false",
        "true",
        "true",
        "false",
        "false",
    ]
    assert stderr == ""


def test_generic_types_are_erased_at_runtime(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = """
    fn id[T](x: T) -> T { return x; }

    fn map[T, U](xs: List[T], f: fn(T) -> U) -> List[U] {
      val out: List[U] = [];
      for x in xs { out.push(f(x)); }
      return out;
    }

    print(id(1));
    print(id("a"));
    print(map([1, 2], fn(x) => x * 2));
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["1", "a", "[2, 4]"]
    assert stderr == ""


def test_stringify_lambda_is_deterministic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run("print(fn() => 1);", capsys)

    assert stdout == ["<lambda>"]
    assert stderr == ""


def test_function_arity_error(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Loxia()
    stdout, stderr = execute(lox, "fn soma(a, b) { return a + b; } soma(1);", capsys)

    assert stdout == []
    assert "Expected 2 arguments but got 1." in stderr
    assert lox.reporter.had_runtime_error


def test_calling_non_callable_is_a_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, stderr = run("var x = 1; x();", capsys)

    assert "Can only call functions and classes." in stderr


def test_return_without_value_is_nil(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("fn f() { return; } print(f());", capsys)

    assert stdout == ["nil"]


def test_clock_is_not_a_builtin(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run("val clock = 1; print(clock);", capsys)

    assert stdout == ["1"]
    assert stderr == ""


def test_top_level_return_is_a_compile_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Loxia()
    stdout, stderr = execute(lox, "return 1;", capsys)

    assert stdout == []
    assert "Can't return from top-level code." in stderr
    assert lox.reporter.had_error
    assert lox.reporter.had_runtime_error is False


def test_closure_uses_lexical_scope_not_dynamic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = """
    var a = "global";
    {
      fn showA() {
        print(a);
      }

      showA();
      var a = "block";
      showA();
    }
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["global", "global"]
    assert stderr == ""


def test_classes_methods_and_this(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    class Pessoa {
      var nome;

      init(nome) {
        this.nome = nome;
      }

      falar() {
        print(this.nome);
      }
    }

    var p = Pessoa("Ana");
    p.falar();
    print(p.nome);
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["Ana", "Ana"]
    assert stderr == ""


def test_bound_method_keeps_this(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    class Foo {
      var x;

      init() {
        this.x = 7;
      }

      getX() {
        return this.x;
      }
    }

    var f = Foo().getX;
    print(f());
    """

    stdout, _ = run(source, capsys)

    assert stdout == ["7"]


def test_inheritance_and_super(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    class A {
      method() {
        return "A";
      }
    }

    class B(A) {
      method() {
        return super.method() + "B";
      }
    }

    print(B().method());
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["AB"]
    assert stderr == ""


def test_global_val_assignment_is_a_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Loxia()
    stdout, stderr = execute(lox, "val x = 1; x = 2;", capsys)

    assert stdout == []
    assert "'x' is immutable" in stderr
    assert lox.reporter.had_runtime_error


def test_val_global_cannot_be_redeclared(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Loxia()
    _, stderr = execute(lox, "val x = 1; var x = 2;", capsys)

    assert "Can't redeclare immutable variable 'x'." in stderr
    assert lox.reporter.had_runtime_error


def test_var_parameter_can_be_mutated(capsys: pytest.CaptureFixture[str]) -> None:
    source = "fn f(var x) { x = x + 1; return x; } print(f(1));"

    stdout, _ = run(source, capsys)

    assert stdout == ["2"]


def test_immutable_parameter_assignment_is_compile_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Loxia()
    stdout, stderr = execute(lox, "fn f(x) { x = 2; }", capsys)

    assert stdout == []
    assert "'x' is immutable" in stderr
    assert lox.reporter.had_error


def test_val_shadowing_and_var_redeclaration(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = """
    val x = 1;
    {
      val x = 2;
      print(x);
    }
    print(x);
    var y = 1;
    var y = 2;
    print(y);
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["2", "1", "2"]
    assert stderr == ""


def test_debug_mode_checks_integer_overflow(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = execute(Loxia(debug=True), "print(9223372036854775807 + 1);", capsys)

    assert stdout == []
    assert "Integer overflow." in stderr


def test_release_mode_wraps_integer_overflow(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run("print(9223372036854775807 + 1);", capsys)

    assert stdout == ["-9223372036854775808"]
    assert stderr == ""


def test_casts_parse_and_math(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run(
        """
        print(3.9 as Int);
        print(3 as Float);
        print(Int.parse("42"));
        print(Int.parse("x"));
        print(Float.parse("3.5"));
        print(math.abs(-3));
        print(math.abs(-3.5));
        print(math.floor(3.9));
        print(math.ceil(3.1));
        print(math.round(2.5));
        print(math.round(-2.5));
        print(math.trunc(-3.9));
        print(math.sqrt(9.0));
        print(math.min(2, 3));
        print(math.max(2.0, 3));
        print(math.clamp(10, 0, 5));
        """,
        capsys,
    )

    assert stderr == ""
    assert stdout == [
        "3",
        "3.0",
        "42",
        "nil",
        "3.5",
        "3",
        "3.5",
        "3",
        "4",
        "3",
        "-3",
        "-3",
        "3.0",
        "2",
        "3.0",
        "5",
    ]


def test_invalid_casts_and_math_domains_fail(capsys: pytest.CaptureFixture[str]) -> None:
    _stdout, stderr = run("print(math.floor(1e100));", capsys)
    assert "math.floor() requires a finite Float in Int range." in stderr

    _stdout, stderr = run("print(math.sqrt(-1.0) as Int);", capsys)
    assert "Can't cast this Float to Int." in stderr

    _stdout, stderr = run('print("1" as Int);', capsys)
    assert "Can't cast value to Int." in stderr


def test_debug_mode_checks_abs_overflow(capsys: pytest.CaptureFixture[str]) -> None:
    source = "val min = -9223372036854775807 - 1; print(math.abs(min));"
    stdout, stderr = execute(Loxia(debug=True), source, capsys)
    assert stdout == []
    assert "Integer overflow." in stderr

    stdout, stderr = run(source, capsys)
    assert stdout == ["-9223372036854775808"]
    assert stderr == ""


def test_parse_rejects_overflow_and_nan(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run(
        """
        print(Int.parse("9223372036854775808"));
        print(Float.parse("1e999"));
        print(Int.parse("  1"));
        """,
        capsys,
    )

    assert stderr == ""
    assert stdout == ["nil", "nil", "nil"]


def test_debug_mode_checks_integer_division_and_power(
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = "val min = -9223372036854775807 - 1; print(min // -1);"
    stdout, stderr = execute(Loxia(debug=True), source, capsys)
    assert stdout == []
    assert "Integer overflow." in stderr

    stdout, stderr = execute(Loxia(debug=True), "print(2 ** 63);", capsys)
    assert stdout == []
    assert "Integer overflow." in stderr


@pytest.mark.parametrize(
    ("first", "second", "same"),
    [
        ("0", "0", True),
        ("0", "1", False),
        ("-1", "-1", True),
        ("true", "true", True),
        ("false", "false", True),
        ("true", "1", False),  # Bool tem tag própria: true != 1
        ("false", "0", False),
        ('"a"', '"a"', True),
        ('"a"', '"b"', False),
        ('""', '"a"', False),
    ],
)
def test_map_hash_is_consistent_with_equality(
    first: str, second: str, same: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    stdout, stderr = run(f"var m = {{ {first}: 1 }}; print(m.has({second}));", capsys)

    assert stdout == ["true" if same else "false"]
    assert stderr == ""


def test_float_is_rejected_as_map_key_at_runtime(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run('var m = {1: "a"}; print(m[1.0]);', capsys)

    assert stdout == []
    assert "Map keys must be strings, integers or booleans." in stderr


def test_tuples_values_formatting_and_equality(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run(
        'print((1, "a"));'
        'print((1, (2, "x")));'
        "print(len((1, 2, 3)));"
        'print((1, "a") == (1.0, "a"));'
        'print((1, "a") != (2, "a"));',
        capsys,
    )

    assert stdout == [
        '(1, "a")',
        '(1, (2, "x"))',
        "3",
        "true",
        "true",
    ]
    assert stderr == ""


def test_tuple_destructuring_bindings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run(
        'val (a, b) = (1, "x");print(a);print(b);var (c, d) = (2, 3);c = 9;print(c);print(d);',
        capsys,
    )

    assert stdout == ["1", "x", "9", "3"]
    assert stderr == ""


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            "val (a, b) = (1, 2, 3);",
            "Destructuring expects 2 values, found 3.",
        ),
        ("val (a, b) = 1;", "Can only destructure a tuple."),
        (
            "val (a, (b, c)) = (1, (2, 3, 4));",
            "Destructuring expects 2 values, found 3.",
        ),
        ("val (a, (b, c)) = (1, 2);", "Can only destructure a tuple."),
        ('print((1, 2)["a"]);', "Tuple index must be an integer."),
        ("print((1, 2)[5]);", "Tuple index 5 out of bounds for length 2."),
    ],
)
def test_tuple_runtime_errors(
    source: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _, stderr = run(source, capsys)

    assert message in stderr


def test_tuple_iteration_and_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run(
        'for x in (1, "a") { print(x); }'
        'print((1, "a") is (Int, String));'
        'print((1, "a") is (Int, Int));',
        capsys,
    )

    assert stdout == ["1", "a", "true", "false"]
    assert stderr == ""


def test_tuple_as_from_any(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run(
        'val x: Any = (2, "b");val (n, s) = x as (Int, String);print(n);print(s);',
        capsys,
    )

    assert stdout == ["2", "b"]
    assert stderr == ""


def test_tuple_as_failure_at_runtime(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, stderr = run("val x: Any = [1]; print(x as (Int, String));", capsys)

    assert "Can't cast value to (Int, String)." in stderr


def test_generic_class_erasure_and_members(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run(
        """
        class Box[T] {
          var value: T
          init(value: T) { this.value = value }
          get() -> T { return this.value }
        }
        class Pair[A, B] {
          val first: A
          val second: B
          init(first: A, second: B) { this.first = first; this.second = second }
          swap() -> Pair[B, A] { return Pair(this.second, this.first) }
        }
        val b = Box(1)
        print(b.get())
        print(b)
        print(Pair(1, "a").swap().first)
        """,
        capsys,
    )

    assert stdout == ["1", "Box instance", "a"]
    assert stderr == ""


def test_enum_values_match_and_result(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run(
        """
        enum Cor { Vermelho, Verde, Azul }
        enum Shape { Circle(Float), Rect(Float, Float) }
        print(Cor.Verde)
        print(Cor.Verde == Cor.Verde)
        print(Cor.Verde == Cor.Azul)
        val s: Shape = Shape.Circle(2.0)
        print(match s {
          Shape.Circle(r) => r * 2.0
          Shape.Rect(w, h) => w * h
        })
        fn parse(n: Int) -> Result[Int, String] {
          if (n > 0) { return Result.Ok(n) }
          return Result.Err("negativo")
        }
        print(parse(3))
        print(match parse(0) {
          Result.Ok(v) => "ok ${v}"
          Result.Err(e) => "erro ${e}"
        })
        """,
        capsys,
    )

    assert stdout == [
        "Cor.Verde",
        "true",
        "false",
        "4.0",
        "Result.Ok(3)",
        "erro negativo",
    ]
    assert stderr == ""


def test_enum_match_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, stderr = run(
        "enum Cor { Vermelho, Verde } print(match Cor.Vermelho { Cor.Verde => 1 });",
        capsys,
    )

    assert "No match arm matched." in stderr


def test_exceptions_runtime_flow(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, stderr = run(
        """
        class MyError(Exception) {
          init(msg: String) { this.message = msg }
        }

        try {
          raise MyError("falhou")
        } except MyError as e {
          print("meu: ${e.message}")
        } finally {
          print("fim")
        }

        try { print(1 / 0) }
        except RuntimeError as e { print("runtime") }

        try { raise MyError("x") }
        except RuntimeError as e { print("errado") }
        except Exception as e { print("generico") }

        fn f() -> Int {
          try { return 1 } finally { return 2 }
        }
        print(f())
        """,
        capsys,
    )

    assert stdout == ["meu: falhou", "fim", "runtime", "generico", "2"]
    assert stderr == ""


def test_bare_raise_relanca(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run(
        """
        class MyError(Exception) {
          init(msg: String) { this.message = msg }
        }

        try {
          try { raise MyError("x") }
          except MyError as e { raise; }
          finally { print("inner") }
        } except MyError as e {
          print("outer: ${e.message}")
        }
        """,
        capsys,
    )

    assert stdout == ["inner", "outer: x"]
    assert stderr == ""


def test_uncaught_exception_e_fatal(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, stderr = run('raise RuntimeError("boom");', capsys)

    assert "Unhandled exception: RuntimeError: boom" in stderr

from __future__ import annotations

import pytest

from main import Lox


def execute(lox: Lox, source: str, capsys: pytest.CaptureFixture[str]) -> tuple[list[str], str]:
    lox.run(source)
    captured = capsys.readouterr()

    return captured.out.splitlines(), captured.err


def run(source: str, capsys: pytest.CaptureFixture[str]) -> tuple[list[str], str]:
    return execute(Lox(), source, capsys)


def test_prints_literals(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run('print 1; print true; print nil; print "a";', capsys)

    assert stdout == ["1", "true", "nil", "a"]
    assert stderr == ""


def test_arithmetic_and_stringify(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print 1 + 2 * 3; print 10 / 4; print 2 * 5;", capsys)

    assert stdout == ["7", "2.5", "10"]


def test_variables_and_uninitialized_default_to_nil(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdout, _ = run("var a = 1; var b; print a; print b;", capsys)

    assert stdout == ["1", "nil"]


def test_block_reads_outer_scope_and_shadows(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    var a = "global";
    {
      var a = "bloco";
      print a;
      { print a; }
    }
    print a;
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["bloco", "bloco", "global"]
    assert stderr == ""


def test_assignment_reaches_enclosing_scope(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("var a = 1; { var b = 2; a = b + 10; } print a;", capsys)

    assert stdout == ["12"]


def test_while_and_for_loops(capsys: pytest.CaptureFixture[str]) -> None:
    while_source = "var i = 0; while (i < 3) { print i; i = i + 1; }"
    for_source = "for (var i = 0; i < 3; i = i + 1) print i;"

    assert run(while_source, capsys)[0] == ["0", "1", "2"]
    assert run(for_source, capsys)[0] == ["0", "1", "2"]


def test_bang_negates_truthiness(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print !nil; print !true; print !!0;", capsys)

    assert stdout == ["true", "false", "true"]


def test_zero_and_empty_string_are_truthy(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run('if (0) print "zero"; if ("") print "vazia";', capsys)

    assert stdout == ["zero", "vazia"]


def test_logical_operators_short_circuit(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run("print false and (1 / 0); print true or (1 / 0);", capsys)

    assert stdout == ["false", "true"]
    assert stderr == ""


def test_undefined_variable_is_a_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Lox()
    stdout, stderr = execute(lox, "print naoexiste;", capsys)

    assert stdout == []
    assert "Undefined variable 'naoexiste'." in stderr
    assert lox.reporter.had_runtime_error


def test_runtime_error_stops_execution(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, stderr = run('print "antes"; print 1 / 0; print "depois";', capsys)

    assert stdout == ["antes"]
    assert "Division by zero" in stderr


def test_syntax_error_does_not_execute(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Lox()
    stdout, _ = execute(lox, "print 1", capsys)

    assert stdout == []
    assert lox.reporter.had_error


def test_errors_do_not_leak_between_runs(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Lox()

    execute(lox, "print naoexiste;", capsys)
    assert lox.reporter.had_runtime_error is True

    stdout, stderr = execute(lox, 'print "ok";', capsys)

    assert stdout == ["ok"]
    assert stderr == ""
    assert lox.reporter.had_runtime_error is False


def test_equality_between_bool_and_number(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print true == 1; print 1 == 1;", capsys)

    assert stdout == ["false", "true"]


def test_functions_and_closures(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    fun makeCounter() {
      var i = 0;
      fun count() {
        i = i + 1;
        print i;
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


def test_function_arity_error(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Lox()
    stdout, stderr = execute(lox, "fun soma(a, b) { return a + b; } soma(1);", capsys)

    assert stdout == []
    assert "Expected 2 arguments but got 1." in stderr
    assert lox.reporter.had_runtime_error


def test_calling_non_callable_is_a_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    _, stderr = run("var x = 1; x();", capsys)

    assert "Can only call functions and classes." in stderr


def test_return_without_value_is_nil(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("fun f() { return; } print f();", capsys)

    assert stdout == ["nil"]


def test_native_clock_is_available(capsys: pytest.CaptureFixture[str]) -> None:
    stdout, _ = run("print clock() > 0;", capsys)

    assert stdout == ["true"]


def test_top_level_return_is_a_compile_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Lox()
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
      fun showA() {
        print a;
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
      init(nome) {
        this.nome = nome;
      }

      falar() {
        print this.nome;
      }
    }

    var p = Pessoa("Ana");
    p.falar();
    print p.nome;
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["Ana", "Ana"]
    assert stderr == ""


def test_bound_method_keeps_this(capsys: pytest.CaptureFixture[str]) -> None:
    source = """
    class Foo {
      init() {
        this.x = 7;
      }

      getX() {
        return this.x;
      }
    }

    var f = Foo().getX;
    print f();
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

    class B < A {
      method() {
        return super.method() + "B";
      }
    }

    print B().method();
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["AB"]
    assert stderr == ""


def test_global_val_assignment_is_a_runtime_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Lox()
    stdout, stderr = execute(lox, "val x = 1; x = 2;", capsys)

    assert stdout == []
    assert "'x' is immutable" in stderr
    assert lox.reporter.had_runtime_error


def test_val_global_cannot_be_redeclared(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Lox()
    _, stderr = execute(lox, "val x = 1; var x = 2;", capsys)

    assert "Can't redeclare immutable variable 'x'." in stderr
    assert lox.reporter.had_runtime_error


def test_var_parameter_can_be_mutated(capsys: pytest.CaptureFixture[str]) -> None:
    source = "fun f(var x) { x = x + 1; return x; } print f(1);"

    stdout, _ = run(source, capsys)

    assert stdout == ["2"]


def test_immutable_parameter_assignment_is_compile_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lox = Lox()
    stdout, stderr = execute(lox, "fun f(x) { x = 2; }", capsys)

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
      print x;
    }
    print x;
    var y = 1;
    var y = 2;
    print y;
    """

    stdout, stderr = run(source, capsys)

    assert stdout == ["2", "1", "2"]
    assert stderr == ""

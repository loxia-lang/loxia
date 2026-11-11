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


def test_top_level_return_is_reported(capsys: pytest.CaptureFixture[str]) -> None:
    lox = Lox()
    stdout, stderr = execute(lox, "return 1;", capsys)

    assert stdout == []
    assert "Can't return from top-level code." in stderr

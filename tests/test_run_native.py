# SPDX-License-Identifier: MIT OR Apache-2.0
"""`loxia run` AOT: cache, canais e flags (ADR-0149, #244).

O objeto aqui é o **processo**: o binário herda o stdio do CLI, então a captura
in-process (`tests/inprocess.py`) não vale. Cada teste usa um `LOX_BUILD_CACHE`
próprio para não herdar binário de outro nem poluir o cache da máquina.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("llvmlite")

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
TIMEOUT_SECONDS = 180

pytestmark = pytest.mark.backend


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _environment(cache: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    merged = dict(os.environ)
    merged["LOX_BUILD_CACHE"] = str(cache)
    merged.setdefault("NO_COLOR", "1")
    merged.update(env or {})
    return merged


def _spawn(arguments: list[str], environment: dict[str, str]) -> subprocess.Popen[str]:
    """Abre o CLI num subprocesso com SIGINT no default.

    `exec` preserva `SIG_IGN`, mas reseta handler para `SIG_DFL`. Se o runner (ou um
    wrapper) ignora SIGINT, o filho herdaria o ignore e o teste de Ctrl-C nunca
    terminaria — foi assim que a lane nativa ficou vermelha no CI. Restaurar o default
    no filho testa o contrato do CLI (sair 130), não a disposição herdada.
    """

    def _restore_sigint() -> None:
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    return subprocess.Popen(
        [sys.executable, str(ENTRYPOINT), *arguments],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
        preexec_fn=_restore_sigint if os.name == "posix" else None,
    )


def _run(
    args: list[str],
    *,
    cache: Path,
    stdin: str | None = None,
    env: dict[str, str] | None = None,
    cwd: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    merged = _environment(cache, env)
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        input=stdin,
        env=merged,
        check=False,
    )


def _write(tmp_path: Path, source: str, name: str = "caso.lx") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _binaries(cache: Path) -> dict[Path, int]:
    """Binários de `run` no cache com `mtime_ns` (prova de que não houve rebuild).

    Só `run/`: as unidades de runtime têm cache próprio na mesma raiz.
    """
    found: dict[Path, int] = {}
    base = cache / "run"
    if not base.is_dir():
        return found
    for path in base.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            found[path] = path.stat().st_mtime_ns
    return found


def _annotated(tmp_path: Path, value: int = 3) -> Path:
    return _write(
        tmp_path,
        f"""fn soma(a: Int, b: Int) -> Int {{
  return a + b
}}
print(soma({value}, 4))
""",
    )


# -- caminho padrão e cache ------------------------------------------------


def test_run_compila_e_executa_por_padrao(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)

    result = _run(["run", str(script)], cache=cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "7\n"
    assert _binaries(cache), "o run padrão não deixou binário no cache"


def test_cache_hit_nao_recompila(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)
    first = _run(["run", str(script)], cache=cache)
    assert first.returncode == 0, first.stderr
    snapshot = _binaries(cache)
    assert snapshot

    second = _run(["run", str(script)], cache=cache)

    assert second.returncode == 0, second.stderr
    assert second.stdout == first.stdout
    assert _binaries(cache) == snapshot, "o hit reescreveu o binário"


def test_cache_invalida_quando_a_fonte_muda(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)
    assert _run(["run", str(script)], cache=cache).stdout == "7\n"

    script.write_text(
        "fn soma(a: Int, b: Int) -> Int {\n  return a + b\n}\nprint(soma(10, 4))\n",
        encoding="utf-8",
    )
    result = _run(["run", str(script)], cache=cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "14\n"


def test_cache_invalida_quando_um_modulo_muda(tmp_path: Path, cache: Path) -> None:
    module = _write(tmp_path, "fn valor() -> Int { return 1 }\n", "dep.lx")
    entry = _write(
        tmp_path,
        "import dep\nprint(dep.valor())\n",
        "main.lx",
    )
    first = _run(["run", str(entry)], cache=cache)
    assert first.returncode == 0, first.stderr
    assert first.stdout == "1\n"

    module.write_text("fn valor() -> Int { return 2 }\n", encoding="utf-8")
    second = _run(["run", str(entry)], cache=cache)

    assert second.returncode == 0, second.stderr
    assert second.stdout == "2\n"


def test_no_cache_nao_escreve_no_cache(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)

    first = _run(["run", "--no-cache", str(script)], cache=cache)
    second = _run(["run", "--no-cache", str(script)], cache=cache)

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout == "7\n"
    assert _binaries(cache) == {}, "com --no-cache nenhum binário pode ficar no cache"


def test_flag_de_build_muda_a_chave(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)

    assert _run(["run", str(script)], cache=cache).returncode == 0
    default = len(_binaries(cache))
    assert default == 1

    assert _run(["run", "--max-heap", "128M", str(script)], cache=cache).returncode == 0
    assert len(_binaries(cache)) == 2, "--max-heap precisa gerar outra entrada"


# -- aceitação e flags que voltam ao tree-walk ------------------------------


def test_sem_anotacao_recusa_com_dica(tmp_path: Path, cache: Path) -> None:
    script = _write(
        tmp_path,
        "fn soma(a, b) {\n  return a + b\n}\nprint(soma(1, 2))\n",
    )

    strict = _run(["run", str(script)], cache=cache)

    assert strict.returncode == 65
    assert "E3004" in strict.stderr
    assert "--interpret" in strict.stderr

    interpreted = _run(["run", "--interpret", str(script)], cache=cache)
    assert interpreted.returncode == 0
    assert interpreted.stdout == "3\n"


def test_json_implica_interpret(tmp_path: Path, cache: Path) -> None:
    script = _write(tmp_path, "fn soma(a, b) {\n  return a + b\n}\nprint(soma(1, 2))\n")

    result = _run(["run", "--json", str(script)], cache=cache)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n"
    assert not _binaries(cache)


def test_sandbox_implica_interpret(tmp_path: Path, cache: Path) -> None:
    script = _write(tmp_path, 'print(fs.exists("."))\n')

    result = _run(["run", "--sandbox", str(script)], cache=cache)

    assert result.returncode == 70
    assert "not available in sandbox mode" in result.stderr


def test_stdin_implica_interpret(cache: Path) -> None:
    source = "fn soma(a, b) {\n  return a + b\n}\nprint(soma(1, 2))\n"

    result = _run(["run", "--stdin", "--file-name", "demo.lx"], cache=cache, stdin=source)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "3\n"
    assert not _binaries(cache)


def test_lacuna_pending_recusa_declarada(cache: Path) -> None:
    case = ROOT / "tests" / "cases" / "bytes" / "bytes_method_value.lx"

    strict = _run(["run", str(case)], cache=cache)

    assert strict.returncode == 65
    assert "not supported by the backend yet" in strict.stderr


# -- paridade de canais ----------------------------------------------------

PARITY_CASES = {
    "sucesso": ("print(1 + 2)\n", None, None),
    "erro-de-runtime": (
        "fn boom(x: Int) -> Int {\n  return x // 0\n}\nprint(boom(1))\n",
        None,
        None,
    ),
    "entry-err": (
        'fn main() -> Result[Nil, String] {\n  return Result.Err("boom")\n}\n',
        None,
        None,
    ),
    "args-e-stdin": (
        "print(args())\nprint(io.readAll())\n",
        "x y",
        "hello\n",
    ),
}


@pytest.mark.parametrize("name", sorted(PARITY_CASES))
def test_paridade_de_canais_com_o_interpretador(name: str, tmp_path: Path, cache: Path) -> None:
    source, script_args, stdin = PARITY_CASES[name]
    script = _write(tmp_path, source)
    arguments = ["run", str(script)]
    if script_args:
        arguments.extend(["--", script_args])
    interpreted = ["run", "--interpret", str(script)]
    if script_args:
        interpreted.extend(["--", script_args])

    compiled = _run(arguments, cache=cache, stdin=stdin)
    oracle = _run(interpreted, cache=cache, stdin=stdin)

    assert compiled.returncode == oracle.returncode
    assert compiled.stdout == oracle.stdout
    assert compiled.stderr == oracle.stderr


def test_warnings_nao_vazam_no_aot(tmp_path: Path, cache: Path) -> None:
    """`run` não emite warnings: o stderr tem que bater com o interpretador (I1)."""
    script = _write(
        tmp_path,
        "fn f() -> Int {\n  val unused = 1\n  return 2\n}\nprint(f())\n",
    )

    compiled = _run(["run", str(script)], cache=cache)
    oracle = _run(["run", "--interpret", str(script)], cache=cache)
    strict = _run(["run", "-Werror", str(script)], cache=cache)

    assert compiled.returncode == oracle.returncode == 0
    assert compiled.stdout == oracle.stdout == "2\n"
    assert compiled.stderr == oracle.stderr == ""
    assert strict.returncode == 0 and strict.stderr == ""


def test_debug_muda_a_aceitacao_e_a_chave(tmp_path: Path, cache: Path) -> None:
    script = _write(tmp_path, "print(9223372036854775807 + 1)\n")

    wrapped = _run(["run", str(script)], cache=cache)
    checked = _run(["run", "--debug", str(script)], cache=cache)
    oracle = _run(["run", "--interpret", "--debug", str(script)], cache=cache)

    assert wrapped.returncode == 0
    assert wrapped.stdout.strip() == "-9223372036854775808"
    assert checked.returncode == 70
    assert "Integer overflow." in checked.stderr
    assert checked.returncode == oracle.returncode
    assert checked.stderr == oracle.stderr


def test_cc_invalido_recusa_com_e4004(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)

    result = _run(
        ["run", "--no-cache", str(script)],
        cache=cache,
        env={"CC": str(tmp_path / "nao-existe")},
    )

    assert result.returncode == 65
    assert "E4004" in result.stderr
    assert "cannot run" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.skipif(sys.platform == "win32", reason="SIGINT/POSIX")
def test_sigint_sai_130_nos_dois_motores(tmp_path: Path, cache: Path) -> None:
    script = _write(tmp_path, "while (true) {\n}\n")
    environment = _environment(cache)
    # Aquece o cache: a interrupção não pode cair no meio do build.
    _run(["run", "--timeout", "50", str(script)], cache=cache)

    for arguments in (["run", str(script)], ["run", "--interpret", str(script)]):
        process = _spawn(arguments, environment)
        time.sleep(0.7)
        process.send_signal(signal.SIGINT)
        _stdout, stderr = process.communicate(timeout=30)

        assert process.returncode == 130
        assert "KeyboardInterrupt" not in stderr


def test_default_de_interface_com_corpo_vazio(tmp_path: Path, cache: Path) -> None:
    """Regressão do converge: `fn m() {}` é default no-op, não assinatura.

    Antes de `TFunction.abstract`, o lowering tratava corpo vazio como assinatura e o
    programa (check-limpo) morria com `E4002` só no motor nativo.
    """
    script = _write(
        tmp_path,
        "interface Named {\n"
        "  fn greet() -> Nil {}\n"
        "}\n"
        "class A implements Named {}\n"
        "A().greet()\n"
        'print("ok")\n',
    )

    interpreted = _run(["run", "--interpret", str(script)], cache=cache)
    compiled = _run(["run", str(script)], cache=cache)

    assert compiled.returncode == 0, compiled.stderr
    assert (compiled.stdout, compiled.stderr) == (interpreted.stdout, interpreted.stderr)
    assert compiled.stdout == "ok\n"


def test_timeout_mata_o_binario_com_124(tmp_path: Path, cache: Path) -> None:
    script = _write(tmp_path, "while (true) {\n}\n")

    result = _run(["run", "--timeout", "300", str(script)], cache=cache)

    assert result.returncode == 124
    assert "Execution timed out after 300 ms." in result.stderr


def test_sem_toolchain_recusa_com_dica(tmp_path: Path, cache: Path) -> None:
    script = _annotated(tmp_path)
    empty = tmp_path / "sem-cc"
    empty.mkdir()

    result = _run(["run", "--no-cache", str(script)], cache=cache, env={"PATH": str(empty)})

    # Sem `cc` no PATH o build falha, mas a mensagem é acionável (E4004 + hint),
    # nunca um traceback nem "internal lowering error".
    assert result.returncode == 65
    assert "E4004" in result.stderr
    assert "--interpret" in result.stderr
    assert "Traceback" not in result.stderr
    assert "internal lowering error" not in result.stderr


def test_determinismo_do_run_aot(tmp_path: Path, cache: Path) -> None:
    script = _write(tmp_path, "print(1 + 2)\n")

    first = _run(["run", str(script)], cache=cache, env={"PYTHONHASHSEED": "1"})
    second = _run(["run", str(script)], cache=cache, env={"PYTHONHASHSEED": "2"})

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout == "3\n"
    assert str(cache) not in first.stdout + first.stderr

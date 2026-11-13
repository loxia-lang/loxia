"""Testes diferenciais do backend nativo (L0-L4).

O contrato (ADR-0031) é: o interpretador é o oráculo. Cada caso compila, executa o
binário e compara **stdout, stderr e exit code** com a execução interpretada — não com
uma expectativa escrita à mão, que poderia "consertar" uma divergência.

Dependências: `llvmlite` (extra `llvm`) e um compilador C para linkar. No CI a env
`LOX_REQUIRE_LLVM=1` transforma a ausência em falha, não em skip.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.corpus_manifest import LEVELS, NEGATIVE, PENDING

MANIFEST_CASES = [
    (level, case) for level, cases in LEVELS.items() for case in cases
]

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
TIMEOUT_SECONDS = 60


def _require(reason: str) -> None:
    if os.environ.get("LOX_REQUIRE_LLVM") == "1":
        pytest.fail(reason, pytrace=False)

    pytest.skip(reason, allow_module_level=True)


if importlib.util.find_spec("llvmlite") is None:
    _require("llvmlite não instalado; rode `uv sync --extra llvm`")

if not any(shutil.which(candidate) for candidate in ("cc", "clang", "gcc")):
    _require("nenhum compilador C encontrado (cc, clang ou gcc)")


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def _write(tmp_path: Path, source: str, name: str = "caso.lox") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _interpret(path: Path) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(ENTRYPOINT), str(path)])


def _build(path: Path, tmp_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    binary = tmp_path / "programa"
    result = _run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--emit",
            "exe",
            "-o",
            str(binary),
            str(path),
        ]
    )
    return result, binary


CASES = [
    ("print 1 + 2;", "adição"),
    ("print 7 // 2;", "divisão inteira"),
    ("print -7 // 2;", "divisão inteira trunca para zero"),
    ("print 7 % 3;", "resto"),
    ("print -7 % 3;", "resto com sinal do dividendo"),
    ("print 2 * 21;", "multiplicação"),
    ("print 1 - 2 - 3;", "subtração associativa à esquerda"),
    ("print 9223372036854775807 + 1;", "wrapping de i64"),
    ("print 1 < 2;", "comparação"),
    ("print 3 == 4;", "igualdade falsa"),
    ("print nil != nil;", "desigualdade de nil"),
    ("print 2 <= 1;", "comparação falsa"),
    ("print true == false;", "igualdade de Bool"),
    ("print nil == nil;", "igualdade de nil"),
    ("print !true;", "negação"),
    ("print !nil;", "negação de nil"),
    ("print !0;", "zero é truthy"),
    ("print -1;", "menos unário"),
    ("print (1 + 2) * 3;", "agrupamento"),
    ("print 1 + 2; print 4 * 5;", "duas instruções"),
    ("print 1; print 1 // 0;", "panico de divisão por zero"),
    ("print 1; print 5 % 0;", "panico de módulo por zero"),
    ("print 1 + true;", "operando de + com tipo errado vira panic"),
    ("print -true;", "menos unário com tipo errado"),
    ("print true // 2;", "// com Bool"),
    ("print 1 < true;", "comparação com Bool"),
    ("print 3 == true;", "tipos diferentes nunca são iguais"),
    ("print nil == 1;", "nil nunca é igual a Int"),
    ("print 5; print 1 + true;", "panic depois de stdout"),
    ("print 1 + 2.0;", "promoção Int -> Float"),
    ("print 4 / 2;", "divisão sempre Float"),
    ("print 0.1;", "float decimal"),
    ("print 1e16;", "float em notação científica"),
    ("print -0.0;", "zero negativo"),
    ("print 1 == 1.0;", "igualdade numérica com promoção"),
    ("print 1 == 1.5;", "igualdade numérica falsa"),
    ("print 1 < 2.5;", "comparação mista"),
    ("print 2.5 % 1.0;", "resto de Float"),
    ("print 1.0 / 0.0;", "panico de divisão por zero em Float"),
    ("print 1.5 % 0.0;", "panico de módulo por zero em Float"),
    ("if (1 < 2) print 1;", "if verdadeiro"),
    ("if (false) print 1; else print 2;", "if com else"),
    ("while (false) { print 1; } print 2;", "while que não executa"),
    ("val a = 1; var b = a + 1; b = b * 2; print b;", "variáveis e atribuição"),
    ("val a = 1; { val a = 2; print a; } print a;", "sombreamento em bloco"),
    ("val f: Float = 2; print f + 1;", "anotação não converte em runtime"),
    ("var n = 0; while (n < 3) { n = n + 1; print n; }", "laço que termina"),
    ("val x = 1; val y = x * 2; print y;", "dependência entre variáveis"),
    ("fn soma(a: Int, b: Int) -> Int { return a + b; } print soma(1, 2);", "função e chamada"),
    ("fn fib(n: Int) -> Int { if (n < 2) return n; return fib(n - 1) + fib(n - 2); } print fib(10);", "recursão"),
    ("fn vazio() -> Nil { return; } print vazio();", "retorno Nil"),
    ("fn f(a: Int) -> Int { return a; } print f();", "aridade vira panic"),
    ("fn soma(a: Int, b: Int = 10) -> Int { return a + b; } print soma(1);", "default no call site"),
    ("print naoexiste;", "variável indefinida vira panic"),
    ("fn f(a: Int) -> Int { return a // 0; } print f(1);", "panic dentro de função"),
    ("print (1 if true else 2);", "ternário verdadeiro"),
    ("print (1 if false else 2);", "ternário falso"),
    ("print (true and false);", "and de Bool"),
    ("print (false or true);", "or de Bool"),
    ("print (1 and 2);", "and devolve o segundo"),
    ("print (0 or 3);", "0 é truthy"),
    ("print (nil ?? 4);", "?? troca nil"),
    ("print (1 ?? 4);", "?? mantém não-nil"),
    (
        "var n = 0; fn e() -> Int { n = n + 1; return 9; } "
        "print (false and e()); print (7 ?? e()); print n;",
        "curto-circuito não avalia o lado direito",
    ),
    ('print "hello";', "literal de string"),
    ('print "";', "string vazia"),
    ('print "a" + "b";', "concatenação"),
    ('val s = "aço"; print len(s);', "len em code points"),
    ('print "ab" == "ab"; print "ab" != "ab";', "igualdade de string"),
    ('fn g(n: String) -> String { return "oi " + n; } print g("ana");', "string em função"),
    ('print 1 + "a";', "tipos misturados em + viram panic"),
    ('print "a" < "b";', "comparação de string"),
    ('print "ab" < "abc";', "prefixo menor na comparação"),
    ('print "é" > "z";', "ordem por code point"),
    ('print "a" < 1;', "string com número vira panic"),
    ('print "a${1}b";', "interpolação de Int"),
    ('print "${1.5} ${true} ${nil}";', "interpolação de Float/Bool/nil"),
    ("val n = 7; print \"n=${n}\";", "interpolação de variável"),
    ('print "nested: ${"a" + "b"}";', "interpolação com expressão de string"),
    ('print "escape: \\${x}";', "escape de $"),
    ('print str(42) + "!";', "str de Int"),
    ('print repr("a\nb");', "repr escapa nova linha"),
    ('print repr(1.0);', "repr de Float"),
    (
        "fn dobro(x: Int) -> Int { return x * 2; } "
        "fn aplica(f: fn(Int) -> Int, x: Int) -> Int { return f(x); } "
        "val f: fn(Int) -> Int = dobro; "
        "print aplica(f, 4); print f; print str(f);",
        "função como valor, parâmetro e print",
    ),
    (
        "fn make() -> fn() -> Int { var n = 0; "
        "return fn() -> Int { n = n + 1; return n; }; } "
        "val c = make(); print c(); print c();",
        "closure com mutação compartilhada",
    ),
    (
        "fn aplica(f: fn(Int) -> Int, x: Int) -> Int { return f(x); } "
        "print aplica(fn(x: Int) => x * 2, 3);",
        "lambda contextual como argumento",
    ),
    (
        "fn outer() -> fn() -> Int { var x = 7; { { "
        "return fn() -> Int { return x; }; } } } print outer()();",
        "captura em profundidade através de blocos",
    ),
    (
        "fn um() -> Int { return 1; } fn dois() -> Int { return 2; } "
        "var f: fn() -> Int = um; print f(); f = dois; print f();",
        "reatribuição de função como valor",
    ),
    (
        "print f(); fn f() -> Int { return 1; }",
        "chamada antes da declaração de topo vira panic",
    ),
    (
        "var b: Int?; print b; b = 7; print b; "
        "if (b != nil) print b + 1;",
        "opcional escalar: nil, atribuição e narrow",
    ),
    (
        "var b: Int?; print (b ?? 4); b = 2; print (b ?? 4);",
        "coalesce de opcional escalar",
    ),
    (
        "fn f(x: Int?) -> Int? { return x; } print f(nil); print f(3);",
        "T? em parâmetro e retorno",
    ),
    (
        "var b: Bool?; b = false; if (b) print 1; else print 2;",
        "truthiness de Bool? com payload false",
    ),
    (
        "fn make() -> fn() -> Int? { var x: Int?; "
        "return fn() -> Int? { x = 5; return x; }; } print make()();",
        "closure captura T? e retorna T?",
    ),

]


@pytest.mark.backend
@pytest.mark.parametrize(("source", "label"), CASES, ids=[case[1] for case in CASES])
def test_binario_concorda_com_interpretador(
    tmp_path: Path, source: str, label: str
) -> None:
    path = _write(tmp_path, source + "\n")

    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert binary.exists()

    compiled = _run([str(binary)])

    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode


@pytest.mark.backend
def test_recurso_sem_representacao_e_rejeitado_explicitamente(tmp_path: Path) -> None:
    path = _write(tmp_path, "print [1];\n")

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "not supported by the backend yet" in result.stderr
    assert not binary.exists()
    # O interpretador roda o mesmo programa: a lacuna é do backend, não da linguagem.
    assert _interpret(path).returncode == 0


@pytest.mark.backend
@pytest.mark.parametrize(
    ("level", "case"),
    MANIFEST_CASES,
    ids=[f"{level}-{Path(case).stem}" for level, case in MANIFEST_CASES],
)
def test_manifesto(level: str, case: str, tmp_path: Path) -> None:
    path = ROOT / case

    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])

    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode


def test_manifesto_referencia_casos_existentes() -> None:
    for cases in LEVELS.values():
        for case in cases:
            assert (ROOT / case).exists(), case


CASES_DIR = ROOT / "tests" / "cases"


def _corpus_paths() -> set[str]:
    return {
        path.relative_to(ROOT).as_posix() for path in CASES_DIR.glob("*.lox")
    }


def test_corpus_classificado() -> None:
    """Todo caso está em LEVELS, PENDING ou NEGATIVE (sem sobra)."""
    paths = _corpus_paths()
    levels = {case for cases in LEVELS.values() for case in cases}
    pending = set(PENDING)
    negative = set(NEGATIVE)

    assert levels | pending | negative == paths
    assert len(levels) + len(pending) + len(negative) == len(paths)
    for case, level in PENDING.items():
        assert level in {"l2", "l4", "l5", "l6", "l?"}, case


@pytest.mark.backend
@pytest.mark.parametrize(
    ("case", "level"),
    sorted(PENDING.items()),
    ids=[f"{level}-{Path(case).stem}" for case, level in sorted(PENDING.items())],
)
def test_pendente_check_limpo_e_recusado_pelo_backend(
    case: str, level: str, tmp_path: Path
) -> None:
    """PENDING: `--check` passa, o backend recusa com 65 e nunca vaza traceback."""
    path = ROOT / case
    assert path.exists(), case

    checked = _run([sys.executable, str(ENTRYPOINT), "--check", str(path)])
    assert checked.returncode == 0, checked.stderr

    result, binary = _build(path, tmp_path)
    assert result.returncode == 65, result.stderr
    assert "not supported by the backend yet" in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert not binary.exists()


@pytest.mark.parametrize(
    "case", sorted(NEGATIVE), ids=[Path(case).stem for case in sorted(NEGATIVE)]
)
def test_caso_negativo_continua_falhando_no_check(case: str) -> None:
    result = _run([sys.executable, str(ENTRYPOINT), "--check", str(ROOT / case)])
    assert result.returncode == 65, result.stdout
    assert "Traceback" not in result.stderr, result.stderr


@pytest.mark.backend
def test_formatacao_de_float_igual_ao_repr(tmp_path: Path) -> None:
    import random
    import struct

    from src.execution.values import stringify

    values = [
        0.0,
        -0.0,
        1.0,
        -1.0,
        0.1,
        1e15,
        1e16,
        1e-4,
        1e-5,
        1.7976931348623157e308,
        5e-324,
        float("inf"),
        float("-inf"),
        float("nan"),
    ]
    rng = random.Random(20261112)
    for _ in range(400):
        bits = rng.getrandbits(64)
        values.append(struct.unpack("<d", struct.pack("<Q", bits))[0])

    helper_source = tmp_path / "helper.c"
    helper_source.write_text(
        """
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "runtime/runtime.c"

int main(void) {
    char line[64];
    while (fgets(line, sizeof line, stdin)) {
        uint64_t bits = strtoull(line, NULL, 16);
        double value;
        memcpy(&value, &bits, sizeof value);
        lox_print_float(value);
    }
    return 0;
}
""",
        encoding="utf-8",
    )
    compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    assert compiler is not None
    helper = tmp_path / "helper"
    compiled = subprocess.run(
        [
            compiler,
            "-O2",
            "-std=c11",
            "-I",
            str(ROOT),
            str(helper_source),
            "-o",
            str(helper),
            "-lm",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr

    payload = "".join(
        f"{struct.unpack('<Q', struct.pack('<d', value))[0]:x}\n" for value in values
    )
    result = subprocess.run(
        [str(helper)], input=payload, capture_output=True, text=True, check=False
    )

    expected = "".join(f"{stringify(value)}\n" for value in values)
    assert result.stdout == expected


@pytest.mark.backend
def test_erro_rebaixavel_nao_e_impresso_no_build(tmp_path: Path) -> None:
    path = _write(tmp_path, "print 1 + true;\n")

    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert binary.exists()


@pytest.mark.backend
def test_erro_nao_rebaixavel_bloqueia_o_build(tmp_path: Path) -> None:
    path = _write(tmp_path, "val x: Int = true;\n")

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "Error" in result.stderr
    assert not binary.exists()


@pytest.mark.backend
def test_emit_ll_mostra_ir_sem_caminho_absoluto(tmp_path: Path) -> None:
    path = _write(tmp_path, "print 1 + 2;\n")

    result = _run([sys.executable, str(ENTRYPOINT), "--emit", "ll", str(path)])

    assert result.returncode == 0, result.stderr
    assert "define i32" in result.stdout
    assert "lox_print_int" in result.stdout
    assert str(tmp_path) not in result.stdout


@pytest.mark.backend
def test_emit_obj_gera_arquivo_de_objeto(tmp_path: Path) -> None:
    path = _write(tmp_path, "print 1 + 2;\n")
    output = tmp_path / "programa.o"

    result = _run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--emit",
            "obj",
            "-o",
            str(output),
            str(path),
        ]
    )

    assert result.returncode == 0, result.stderr
    assert output.exists()
    assert output.stat().st_size > 0


@pytest.mark.backend
def test_tupla_sem_backend_e_rejeitada_explicitamente(tmp_path: Path) -> None:
    path = _write(tmp_path, "print (1, 2);\n")

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "not supported by the backend yet" in result.stderr
    assert not binary.exists()
    assert _interpret(path).returncode == 0


@pytest.mark.backend
def test_classe_generica_sem_backend_e_rejeitada(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "class Box[T] { var value: T\n"
        "  init(value: T) { this.value = value }\n"
        "  get() -> T { return this.value }\n"
        "}\n"
        "print Box(1).get();\n",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "Class is not supported by the backend yet." in result.stderr
    assert not binary.exists()


@pytest.mark.backend
def test_enum_sem_backend_e_rejeitado(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "enum Cor { Vermelho, Verde }\n"
        "print match Cor.Vermelho { Cor.Vermelho => 1, Cor.Verde => 2 };\n",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "EnumDecl is not supported by the backend yet." in result.stderr
    assert not binary.exists()


@pytest.mark.backend
def test_try_sem_backend_e_rejeitado(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "try { print 1; } finally { print 2; }\n",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "Try is not supported by the backend yet." in result.stderr
    assert not binary.exists()

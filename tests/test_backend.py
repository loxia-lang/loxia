# SPDX-License-Identifier: MIT OR Apache-2.0
"""Testes diferenciais do backend nativo (L0-L6 + T7).

O contrato (ADR-0031) é: o interpretador é o oráculo. Cada caso compila, executa o
binário e compara **stdout, stderr e exit code** com a execução interpretada — não com
uma expectativa escrita à mão, que poderia "consertar" uma divergência.

Dependências: `llvmlite` (extra `llvm`) e um compilador C para linkar. No CI a env
`LOX_REQUIRE_LLVM=1` transforma a ausência em falha, não em skip.
"""

from __future__ import annotations

import importlib.util
import os
import select
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from loxia.engine import Loxia
from tests.corpus_manifest import COMPILE_ERRORS, LEVELS, NEGATIVE, PENDING

MANIFEST_CASES = [(level, case) for level, cases in LEVELS.items() for case in cases]

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


def _run(arguments: list[str], input: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
        input=input,
    )


def _write(tmp_path: Path, source: str, name: str = "caso.lx") -> Path:
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def _interpret(path: Path) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(ENTRYPOINT), str(path)])


def _build(
    path: Path, tmp_path: Path, *, max_heap: str | None = None
) -> tuple[subprocess.CompletedProcess[str], Path]:
    binary = tmp_path / "programa"
    arguments = [sys.executable, str(ENTRYPOINT), "--emit", "exe"]
    if max_heap is not None:
        arguments.extend(["--max-heap", max_heap])
    arguments.extend(["-o", str(binary), str(path)])
    result = _run(arguments)
    return result, binary


CASES = [
    ("print(1 + 2);", "adição"),
    ("print(7 // 2);", "divisão inteira"),
    ("print(-7 // 2);", "divisão inteira trunca para zero"),
    ("print(7 % 3);", "resto"),
    ("print(-7 % 3);", "resto com sinal do dividendo"),
    ("print(2 * 21);", "multiplicação"),
    ("print(1 - 2 - 3);", "subtração associativa à esquerda"),
    ("print(9223372036854775807 + 1);", "wrapping de i64"),
    ("print(1 < 2);", "comparação"),
    ("print(3 == 4);", "igualdade falsa"),
    ("print(nil != nil);", "desigualdade de nil"),
    ("print(2 <= 1);", "comparação falsa"),
    ("print(true == false);", "igualdade de Bool"),
    ("print(nil == nil);", "igualdade de nil"),
    ("print(not true);", "negação"),
    ("print(not nil);", "negação de nil"),
    ("print(not 0);", "zero é truthy"),
    ("print(-1);", "menos unário"),
    ("print((1 + 2) * 3);", "agrupamento"),
    ("print(1 + 2); print(4 * 5);", "duas instruções"),
    ("print(1); print(1 // 0);", "panico de divisão por zero"),
    ("print(1); print(5 % 0);", "panico de módulo por zero"),
    ("print(1 + true);", "operando de + com tipo errado vira panic"),
    ("print(-true);", "menos unário com tipo errado"),
    ("print(true // 2);", "// com Bool"),
    ("print(1 < true);", "comparação com Bool"),
    ("print(3 == true);", "tipos diferentes nunca são iguais"),
    ("print(nil == 1);", "nil nunca é igual a Int"),
    ("print(5); print(1 + true);", "panic depois de stdout"),
    ("print(1 + 2.0);", "promoção Int -> Float"),
    ("print(4 / 2);", "divisão sempre Float"),
    ("print(0.1);", "float decimal"),
    ("print(1e16);", "float em notação científica"),
    ("print(-0.0);", "zero negativo"),
    ("print(1 == 1.0);", "igualdade numérica com promoção"),
    ("print(1 == 1.5);", "igualdade numérica falsa"),
    ("print(1 < 2.5);", "comparação mista"),
    ("print(2.5 % 1.0);", "resto de Float"),
    ("print(1.0 / 0.0);", "panico de divisão por zero em Float"),
    ("print(1.5 % 0.0);", "panico de módulo por zero em Float"),
    ("if (1 < 2) print(1);", "if verdadeiro"),
    ("if (false) print(1); else print(2);", "if com else"),
    ("while (false) { print(1); } print(2);", "while que não executa"),
    ("val a = 1; var b = a + 1; b = b * 2; print(b);", "variáveis e atribuição"),
    ("val a = 1; { val a = 2; print(a); } print(a);", "sombreamento em bloco"),
    ("val f: Float = 2 as Float; print(f + 1);", "conversão explícita com as"),
    ("var n = 0; while (n < 3) { n = n + 1; print(n); }", "laço que termina"),
    ("val x = 1; val y = x * 2; print(y);", "dependência entre variáveis"),
    ("fn soma(a: Int, b: Int) -> Int { return a + b; } print(soma(1, 2));", "função e chamada"),
    (
        "fn fib(n: Int) -> Int { if (n < 2) return n; return fib(n - 1) + fib(n - 2); } print(fib(10));",
        "recursão",
    ),
    ("fn vazio() -> Nil { return; } print(vazio());", "retorno Nil"),
    ("fn f(a: Int) -> Int { return a; } print(f());", "aridade vira panic"),
    (
        "fn soma(a: Int, b: Int = 10) -> Int { return a + b; } print(soma(1));",
        "default no call site",
    ),
    ("print(naoexiste);", "variável indefinida vira panic"),
    ("fn f(a: Int) -> Int { return a // 0; } print(f(1));", "panic dentro de função"),
    ("print((1 if true else 2));", "ternário verdadeiro"),
    ("print((1 if false else 2));", "ternário falso"),
    ("print((true and false));", "and de Bool"),
    ("print((false or true));", "or de Bool"),
    ("print((1 and 2));", "and devolve o segundo"),
    ("print((0 or 3));", "0 é truthy"),
    ("print((nil ?? 4));", "?? troca nil"),
    ("print((1 ?? 4));", "?? mantém não-nil"),
    (
        "var n = 0; fn e() -> Int { n = n + 1; return 9; } "
        "print((false and e())); print((7 ?? e())); print(n);",
        "curto-circuito não avalia o lado direito",
    ),
    ('print("hello");', "literal de string"),
    ('print("");', "string vazia"),
    ('print("a" + "b");', "concatenação"),
    ('val s = "aço"; print(len(s));', "len em code points"),
    ('print("ab" == "ab"); print("ab" != "ab");', "igualdade de string"),
    ('fn g(n: String) -> String { return "oi " + n; } print(g("ana"));', "string em função"),
    ('print(1 + "a");', "tipos misturados em + viram panic"),
    ('print("a" < "b");', "comparação de string"),
    ('print("ab" < "abc");', "prefixo menor na comparação"),
    ('print("é" > "z");', "ordem por code point"),
    ('print("a" < 1);', "string com número vira panic"),
    ('print("a${1}b");', "interpolação de Int"),
    ('print("${1.5} ${true} ${nil}");', "interpolação de Float/Bool/nil"),
    ('val n = 7; print("n=${n}");', "interpolação de variável"),
    ('print("nested: ${"a" + "b"}");', "interpolação com expressão de string"),
    ('print("escape: \\${x}");', "escape de $"),
    ('print(str(42) + "!");', "str de Int"),
    (
        '''print(repr("""a
b"""));''',
        "repr escapa nova linha",
    ),
    ("print(repr(1.0));", "repr de Float"),
    (
        "fn dobro(x: Int) -> Int { return x * 2; } "
        "fn aplica(f: fn(Int) -> Int, x: Int) -> Int { return f(x); } "
        "val f: fn(Int) -> Int = dobro; "
        "print(aplica(f, 4)); print(f); print(str(f));",
        "função como valor, parâmetro e print",
    ),
    (
        "fn make() -> fn() -> Int { var n = 0; "
        "return fn() -> Int { n = n + 1; return n; }; } "
        "val c = make(); print(c()); print(c());",
        "closure com mutação compartilhada",
    ),
    (
        "fn aplica(f: fn(Int) -> Int, x: Int) -> Int { return f(x); } "
        "print(aplica(fn(x: Int) => x * 2, 3));",
        "lambda contextual como argumento",
    ),
    (
        "fn outer() -> fn() -> Int { var x = 7; { { "
        "return fn() -> Int { return x; }; } } } print(outer()());",
        "captura em profundidade através de blocos",
    ),
    (
        "fn um() -> Int { return 1; } fn dois() -> Int { return 2; } "
        "var f: fn() -> Int = um; print(f()); f = dois; print(f());",
        "reatribuição de função como valor",
    ),
    (
        "print(f()); fn f() -> Int { return 1; }",
        "chamada antes da declaração de topo vira panic",
    ),
    (
        "var b: Int?; print(b); b = 7; print(b); if (b != nil) print(b + 1);",
        "opcional escalar: nil, atribuição e narrow",
    ),
    (
        "var b: Int?; print((b ?? 4)); b = 2; print((b ?? 4));",
        "coalesce de opcional escalar",
    ),
    (
        "fn f(x: Int?) -> Int? { return x; } print(f(nil)); print(f(3));",
        "T? em parâmetro e retorno",
    ),
    (
        "var b: Bool?; b = false; if (b) print(1); else print(2);",
        "truthiness de Bool? com payload false",
    ),
    (
        "fn make() -> fn() -> Int? { var x: Int?; "
        "return fn() -> Int? { x = 5; return x; }; } print(make()());",
        "closure captura T? e retorna T?",
    ),
    (
        "val x: Any = 3; print(x as Int); val y: Any = 3; print(y as Float);",
        "Any as Int/Float com promoção",
    ),
    (
        'val x: Any = "a"; print(x as Int);',
        "Any as Int com tag errada vira panic R1011",
    ),
    (
        'raise RuntimeError("boom");',
        "raise na classe de exceção sintética com mensagem",
    ),
    (
        "class MyError(Exception) { init(msg: String) { this.message = msg } } "
        'raise MyError("falhou");',
        "exceção de usuário não capturada com a mensagem",
    ),
    (
        'val t: Any = (1, "a"); print(t is (Int, String)); '
        "print(t is (Int, Int)); print(t is (Int, String, Int));",
        "Any is tupla checa aridade e elementos",
    ),
    (
        'val t: (Any, Any) = (1, "a"); print(t is (Int, String));',
        "is de tupla estática com elementos Any",
    ),
    (
        'val l: Any = ["a"]; print(l is List[Int]);',
        "Any is List[Int] checa os elementos",
    ),
    (
        "val l: Any = [1, 2]; print(l is List[Int]); print(l as List[Int]);",
        "Any is/as List[Int] válidos",
    ),
    (
        'val l: Any = ["a"]; print(l as List[Int]);',
        "Any as List[Int] com elemento errado vira panic",
    ),
    (
        'val m: Any = {"a": "b"}; print(m is Map[String, Int]);',
        "Any is Map checa chave e valor",
    ),
    (
        "enum Color { Red } enum Size { Small } val x: Any = Size.Small; "
        "print(x is Color); print(x is Size);",
        "is de enum checa a identidade",
    ),
    (
        "enum Color { Red } val x: Any = Color.Red; print(x as Color);",
        "as de enum",
    ),
    (
        'print(5 is Int); print(5 is String); print("a" is String); '
        "print((1..2) is Range); print(nil is Nil);",
        "is estático de escalar",
    ),
    (
        "class A {} print(5 is A);",
        "is de classe com valor não-instância devolve false",
    ),
    (
        "class A {} val a: A? = nil; print(a is A); val b: A? = A(); print(b is A);",
        "is de classe opcional (nil e presente)",
    ),
    (
        "val x: Int? = nil; print(x is Int); val y: Int? = 3; print(y is Int);",
        "is de escalar opcional",
    ),
    (
        "val l: List[Int]? = nil; print(l is List[Int]); "
        "val m: List[Int]? = [1]; print(m is List[Int]);",
        "is de lista opcional",
    ),
    (
        "val x: Any = [[1], [2]]; print(x); "
        "print(x is List[List[Int]]); print(x is List[List[String]]);",
        "literal de lista aninhada e is recursivo",
    ),
    (
        'val x: Any = {"a": {"b": 1}}; print(x); print(x is Map[String, Map[String, Int]]);',
        "literal de mapa aninhado e is recursivo",
    ),
    (
        "fn f() -> Any { class Local {} val x: Any = Local(); return x is Local; } print(f());",
        "is de classe local a partir de Any",
    ),
    (
        'print(true as Bool); print("a" as String); print((1..2) as Range); print(nil as Nil);',
        "as estático de escalar",
    ),
    # Regressões da auditoria de invariantes (Any dinâmico, val global, iteração,
    # diagnósticos, Float, formatação, exceções).
    (
        "val a: Any = 1; print(a + 1); print(a - 2); print(a * 3); "
        "print(a / 2); print(a // 2); print(a % 2); print(a ** 2); "
        "print(a < 2); print(-a);",
        "Any: aritmética dinâmica",
    ),
    (
        'val s: Any = "x"; print(s + "y"); print("y" + s);',
        "Any: concatenação dinâmica",
    ),
    (
        'val a: Any = "x"; print(a + 1);',
        "Any: operando inválido vira panic",
    ),
    ("val a = 1; a = 2; print(a);", "val global: atribuição é R1009"),
    ("val x = 1; val x = 2; print(x);", "val global: redeclaração é R1009"),
    ("val xs = [1, 2, 3]; for x in xs { xs.push(x) }", "lista mutada durante for-in"),
    ("val m = {1: 2}; for k in m { m[3] = 4 }", "mapa mutado durante for-in"),
    ("val xs = [1]; print(xs[2]);", "índice de lista: mensagem detalhada"),
    ("val xs = [1]; xs[2] = 3;", "índice de lista em atribuição: mensagem detalhada"),
    (
        "fn f(t: (Int, Int), i: Int) -> Int { return t[i] } print(f((1, 2), 5));",
        "índice de tupla dinâmico: mensagem detalhada",
    ),
    ("print(range(1, 2, 0));", "range step zero: R1000 com posição"),
    (
        "val n = math.sqrt(-1.0); print(n != n); print(n == n); print(n < 1.0);",
        "Float: NaN != NaN",
    ),
    ("print(0.0 ** -3);", "Float: domínio de **"),
    ("print(1e308 ** 2);", "Float: overflow de **"),
    (
        "print(math.min(math.sqrt(-1.0), 1.0)); "
        "print(math.max(1.0, math.sqrt(-1.0))); "
        "print(math.min(0.0, -0.0));",
        "math.min/max: NaN e zero sinalizado",
    ),
    (
        "print(math.clamp(0.5, math.sqrt(-1.0), 1.0));",
        "math.clamp: NaN propaga",
    ),
    (
        'print(Float.parse(" 1")); print(Float.parse("0x10")); '
        'print(Float.parse(".5")); print(Float.parse("5."));',
        "Float.parse: estrito",
    ),
    (
        "class C { } val c: Any = C(); print(c); val i: Any = C(); print(i);",
        "Any: classe/instância sem newline extra",
    ),
    (
        "fn f() -> Int { return 1 } val xs: List[Any] = [f]; print(xs);",
        "Any: função em container mantém o display",
    ),
    (
        'print(1..=3); print(str(1..=3)); print("${1..=3}"); print(repr(1..=3));',
        "Range: str/repr inclusivos",
    ),
    (
        'val a: Any = "hi"; print(repr(a)); var s: String?; print(repr(s)); '
        's = "x"; print(repr(s));',
        "repr: Any string e String? nil",
    ),
    (
        "class E(Exception) { init(m: String) { this.message = m } } "
        'try { raise E("boom") } except E as e { print(e); print(e is Exception); } '
        "try { print(1 / 0) } except RuntimeError as e { "
        "print(e is RuntimeError); print(e is Exception); print(e as Exception); }",
        "exceções: stringify/is/as",
    ),
    (
        'try { val z = 0; print(1 // z) } except RuntimeError as e { print("caught"); raise; }',
        "raise; dentro de except relança R1010",
    ),
    ('val m = {1: "a", 1: "b"}; print(m);', "map literal: chave duplicada"),
]


@pytest.mark.backend
@pytest.mark.parametrize(("source", "label"), CASES, ids=[case[1] for case in CASES])
def test_binario_concorda_com_interpretador(tmp_path: Path, source: str, label: str) -> None:
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
    for case in COMPILE_ERRORS:
        assert (ROOT / case).exists(), case


CASES_DIR = ROOT / "tests" / "cases"


def _corpus_paths() -> set[str]:
    paths = set(CASES_DIR.rglob("*.lx"))
    return {path.relative_to(ROOT).as_posix() for path in paths}


def test_corpus_classificado() -> None:
    """Todo caso está em LEVELS, PENDING ou NEGATIVE (sem sobra)."""
    paths = _corpus_paths()
    levels = {case for cases in LEVELS.values() for case in cases}
    pending = set(PENDING)
    negative = set(NEGATIVE)

    assert levels | pending | negative | COMPILE_ERRORS == paths
    assert len(levels) + len(pending) + len(negative) + len(COMPILE_ERRORS) == len(paths)
    for case, level in PENDING.items():
        assert level in {"l2", "l4", "l5", "l6"}, case


def test_pending_budget() -> None:
    """ADR-0064: PENDING não pode passar de 5% do corpus anotado."""
    total = len(_corpus_paths())
    assert len(PENDING) * 100 <= total * 5, f"{len(PENDING)} PENDING em {total} casos; teto de 5%"


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


@pytest.mark.backend
def test_gc_recicla_memoria_no_backend(tmp_path: Path) -> None:
    """ADR-0074: alocar em laço deixou de ser sentença de morte.

    O programa aloca ~80 MiB de strings temporárias e mantém só uma string viva por
    iteração. A arena antiga de 64 MiB morria; o Boehm coleta e o programa termina.
    O tree-walk roda o mesmo programa, então o teste também é diferencial.
    """
    path = _write(
        tmp_path,
        "var i = 0\n"
        "while (i < 80) {\n"
        '  var s = "0123456789abcdef"\n'
        "  var j = 0\n"
        "  while (j < 16) { s = s + s; j = j + 1 }\n"
        "  i = i + 1\n"
        "}\n"
        """print(i)
""",
    )

    interpreted = _run([sys.executable, str(ENTRYPOINT), str(path)])
    assert interpreted.returncode == 0, interpreted.stderr
    assert interpreted.stdout == "80\n"

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    assert native.returncode == 0, native.stderr
    assert native.stdout == interpreted.stdout
    assert native.stderr == ""


@pytest.mark.backend
def test_gc_preserva_roots_estaticos_e_objetos(tmp_path: Path) -> None:
    """Coleta no meio de um frame não pode levar classes, globais, closures nem containers."""
    path = _write(
        tmp_path,
        'val prefix = "global:" + "x"\n'
        "class Node {\n"
        "  val name: String\n"
        "  init(name: String) { this.name = name }\n"
        "}\n"
        "fn check() -> String {\n"
        '  val n = Node("ok")\n'
        '  val xs = ["a", "b"]\n'
        '  val m = {"k": 1}\n'
        '  val t = (1, "x")\n'
        "  val cyc: List[Any] = []\n"
        "  cyc.push(cyc)\n"
        "  val f = fn() => n.name\n"
        "  var i = 0\n"
        "  while (i < 80) {\n"
        '    var s = "0123456789abcdef"\n'
        "    var j = 0\n"
        "    while (j < 16) { s = s + s; j = j + 1 }\n"
        "    i = i + 1\n"
        "  }\n"
        '  return f() + xs[0] + str(m["k"]) + t[1] + str(len(cyc))\n'
        "}\n"
        """print(prefix + check())
""",
    )

    interpreted = _run([sys.executable, str(ENTRYPOINT), str(path)])
    assert interpreted.returncode == 0, interpreted.stderr

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    assert native.returncode == 0, native.stderr
    assert native.stdout == interpreted.stdout
    assert native.stdout == "global:xoka1x1\n"
    assert native.stderr == ""


@pytest.mark.backend
def test_gc_preserva_try_frame_e_excecao(tmp_path: Path) -> None:
    """Coleta dentro de um `try` não pode perder o frame nem a exceção em voo."""
    path = _write(
        tmp_path,
        "class MyError(Exception) {\n"
        "  init(msg: String) { this.message = msg }\n"
        "}\n"
        "fn burn() -> Int {\n"
        "  var i = 0\n"
        "  while (i < 80) {\n"
        '    var s = "0123456789abcdef"\n'
        "    var j = 0\n"
        "    while (j < 16) { s = s + s; j = j + 1 }\n"
        "    i = i + 1\n"
        "  }\n"
        "  return 0\n"
        "}\n"
        "try {\n"
        "  burn()\n"
        '  raise MyError("boom")\n'
        "} except MyError as e {\n"
        """  print(e.message)
"""
        "}\n"
        "burn()\n"
        """print("done")
""",
    )

    interpreted = _run([sys.executable, str(ENTRYPOINT), str(path)])
    assert interpreted.returncode == 0, interpreted.stderr

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    assert native.returncode == 0, native.stderr
    assert native.stdout == interpreted.stdout
    assert native.stdout == "boom\ndone\n"
    assert native.stderr == ""


# ~200 MiB de strings vivas: acima do override de 128 MiB, abaixo do default de 512 MiB.
HEAP_PRESSURE_SOURCE = (
    "var xs: List[String] = []\n"
    "var i = 0\n"
    "while (i < 200) {\n"
    '  var s = "0123456789abcdef"\n'
    "  var j = 0\n"
    "  while (j < 16) { s = s + s; j = j + 1 }\n"
    "  xs.push(s)\n"
    "  i = i + 1\n"
    "}\n"
    "print(len(xs))\n"
)


@pytest.mark.backend
def test_hard_cap_de_memoria_falha_deterministico(tmp_path: Path) -> None:
    """ADR-0087: com `--max-heap=128M`, o binário morre com a mensagem do contrato.

    O coletor conservador não promete o ponto exato da falha, mas promete canal, mensagem
    e exit code. O teste não imprime nada antes do estouro e roda duas vezes.
    """
    path = _write(tmp_path, HEAP_PRESSURE_SOURCE)

    result, binary = _build(path, tmp_path, max_heap="128M")
    assert result.returncode == 0, result.stderr

    first = _run([str(binary)])
    second = _run([str(binary)])

    assert first.returncode == 70
    assert first.stdout == ""
    assert "Out of memory." in first.stderr
    assert "GC Warning" not in first.stderr
    assert "Traceback" not in first.stderr
    assert (first.returncode, first.stdout, first.stderr) == (
        second.returncode,
        second.stdout,
        second.stderr,
    )


@pytest.mark.backend
def test_heap_default_de_512_mib_permite_200_mib(tmp_path: Path) -> None:
    """ADR-0087: o default de 512 MiB não é mais o teto de 128 MiB."""
    path = _write(tmp_path, HEAP_PRESSURE_SOURCE)

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])

    assert native.returncode == 0, native.stderr
    assert native.stdout == "200\n"
    assert native.stderr == ""


@pytest.mark.backend
def test_stack_reserve_cobre_frame_gordo_com_soft_limit_de_8_mib(
    tmp_path: Path,
) -> None:
    """ADR-0077: com soft limit de 8 MiB, `lox_init` sobe a pilha antes da recursão."""
    import resource

    hard = resource.getrlimit(resource.RLIMIT_STACK)[1]
    if hard != resource.RLIM_INFINITY and hard < 64 * 1024 * 1024:
        pytest.skip("hard limit de pilha baixo demais para o teste de reserva")

    locals_source = "\n".join(f"  var a{index}: Int = n + {index}" for index in range(200))
    terms = " + ".join(f"a{index}" for index in range(200))
    source = (
        "fn g(n: Int) -> Int {\n"
        f"{locals_source}\n"
        f"  if (n <= 0) {{ return {terms} }}\n"
        f"  return ({terms}) + g(n - 1)\n"
        "}\n"
        "print(g(9999))\n"
    )
    path = _write(tmp_path, source)
    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    def soft_8_mib() -> None:
        _soft, maximum = resource.getrlimit(resource.RLIMIT_STACK)
        resource.setrlimit(resource.RLIMIT_STACK, (8 * 1024 * 1024, maximum))

    native = subprocess.run(
        [str(binary)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
        preexec_fn=soft_8_mib,
    )

    assert native.returncode == 0, native.stderr


def _checkable_sources() -> list[tuple[str, str]]:
    """Casos do corpus que podem passar no `--check` (sem `errors/`)."""
    paths = (
        sorted(CASES_DIR.glob("*.lx"))
        + sorted((CASES_DIR / "bytes").glob("*.lx"))
        + sorted((ROOT / "examples").glob("*.lx"))
    )
    return [(path.relative_to(ROOT).as_posix(), path.read_text(encoding="utf-8")) for path in paths]


@pytest.mark.backend
def test_promocao_int_para_float_e_recusada_pelos_dois(tmp_path: Path) -> None:
    """Regressão do furo que motivou o I4 (ADR-0059).

    Antes: `--check` limpo, interpretador imprime `2` e o backend recusava com
    "Can't use INT where FLOAT is expected" — duas fontes de verdade.
    Agora o checker recusa primeiro, com a mesma mensagem nos dois caminhos.
    """
    path = _write(
        tmp_path,
        """var x: Float = 1.5
x = 2
print(x)
""",
    )

    checked = _run([sys.executable, str(ENTRYPOINT), "--check", str(path)])
    expected = "Expected Float, found Int. Write `2.0` or use `2 as Float`."
    assert checked.returncode == 65, checked.stderr
    assert expected in checked.stderr

    result, binary = _build(path, tmp_path)
    assert result.returncode == 65, result.stderr
    assert expected in result.stderr, result.stderr
    assert not binary.exists()


@pytest.mark.backend
def test_i4_check_limpo_nunca_vira_erro_de_tipo_no_lowering(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """I4 (ADR-0059): `--check` limpo ⇒ o lowering não recusa por tipo/coerção.

    A única recusa aceitável depois de um check limpo é a lacuna declarada
    ("not supported by the backend yet"). Qualquer outro erro é divergência entre
    checker e backend — a classe do `var x: Float = 1.5; x = 2` que motivou o I4.
    """
    problems: list[str] = []

    for index, (name, source) in enumerate(_checkable_sources()):
        probe = Loxia()
        probe.check(source)
        capsys.readouterr()
        if probe.reporter.had_error:
            continue  # erro de check: fora do escopo do I4

        output = tmp_path / f"case_{index}.ll"
        lox = Loxia()
        built = lox.build(source, emit="ll", output=output, stem=f"case_{index}")
        reported = capsys.readouterr().err

        if not built and "not supported by the backend yet" not in reported:
            problems.append(f"{name}: {reported.strip()}")

    assert problems == [], "check limpo virou erro no backend:\n" + "\n".join(problems)


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

    from loxia_core.execution.values import stringify

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

#include "runtime/lox_runtime.h"

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
    # Import tardio: `llvmlite` é opcional e o módulo só é coletado com o extra.
    from loxia_core.backend.driver import RUNTIME_SOURCES

    helper = tmp_path / "helper"
    compiled = subprocess.run(
        [
            compiler,
            "-O2",
            "-std=c11",
            "-I",
            str(ROOT),
            str(helper_source),
            *(str(source) for source in RUNTIME_SOURCES),
            "-o",
            str(helper),
            "-lm",
            "-lgc",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compiled.returncode == 0, compiled.stderr

    payload = "".join(f"{struct.unpack('<Q', struct.pack('<d', value))[0]:x}\n" for value in values)
    result = subprocess.run(
        [str(helper)], input=payload, capture_output=True, text=True, check=False
    )

    expected = "".join(f"{stringify(value)}\n" for value in values)
    assert result.stdout == expected


@pytest.mark.backend
def test_stack_trace_de_modulo_bate_com_interpretador(tmp_path: Path) -> None:
    (tmp_path / "mod.lx").write_text(
        "fn inner() -> Int { return 1 // 0 }\nfn outer() -> Int { return inner() }\n",
        encoding="utf-8",
    )
    path = tmp_path / "main.lx"
    path.write_text("import mod\nprint(mod.outer())\n", encoding="utf-8")

    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])

    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode == 70
    assert "mod.lx:1:30: error[R1002]" in compiled.stderr
    assert "  at inner (" in compiled.stderr
    assert "  at outer (" in compiled.stderr


@pytest.mark.backend
def test_erro_rebaixavel_nao_e_impresso_no_build(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """print(1 + true);
""",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert binary.exists()


@pytest.mark.backend
def test_erro_nao_rebaixavel_bloqueia_o_build(tmp_path: Path) -> None:
    path = _write(tmp_path, "val x: Int = true;\n")

    result, binary = _build(path, tmp_path)

    assert result.returncode == 65
    assert "error[E3001]: Expected Int, found Bool." in result.stderr
    assert not binary.exists()


@pytest.mark.backend
def test_emit_ll_mostra_ir_sem_caminho_absoluto(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """print(1 + 2);
""",
    )

    result = _run([sys.executable, str(ENTRYPOINT), "--emit", "ll", str(path)])

    assert result.returncode == 0, result.stderr
    assert "define i32" in result.stdout
    assert "lox_print_int" in result.stdout
    assert str(tmp_path) not in result.stdout


@pytest.mark.backend
def test_emit_obj_gera_arquivo_de_objeto(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """print(1 + 2);
""",
    )
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
def test_tupla_e_compilada(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """print((1, 2));
""",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert binary.exists()
    compiled = _run([str(binary)])
    assert compiled.stdout == "(1, 2)\n"


@pytest.mark.backend
def test_classe_generica_e_monomorfizada(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "class Box[T] { var value: T\n"
        "  init(value: T) { this.value = value }\n"
        "  get() -> T { return this.value }\n"
        "}\n"
        """print(Box(1).get());
"""
        """print(Box("x").get());
""",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert binary.exists()
    expected = _interpret(path)
    compiled = _run([str(binary)])
    assert compiled.stdout == expected.stdout == "1\nx\n"
    assert compiled.returncode == expected.returncode == 0


@pytest.mark.backend
def test_enum_e_compilado(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "enum Cor { Vermelho, Verde }\n"
        """print(match Cor.Vermelho { Cor.Vermelho => 1, Cor.Verde => 2 });
""",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert binary.exists()
    compiled = _run([str(binary)])
    assert compiled.stdout == "1\n"


@pytest.mark.backend
def test_try_e_compilado(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """try { print(1); } finally { print(2); }
""",
    )

    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    assert binary.exists()
    compiled = _run([str(binary)])
    assert compiled.stdout == "1\n2\n"


@pytest.mark.backend
def test_abi_das_estruturas_publicas_e_estavel() -> None:
    """Contrato mínimo para a futura FFI com C (ADR-0048)."""
    from loxia_core.backend.lower_model import (
        _ANY,
        _CLASS_DESC,
        _CLOSURE,
        _INTERFACE_ENTRY,
        ANY_TAG_BOOL,
        ANY_TAG_CLASS,
        ANY_TAG_FLOAT,
        ANY_TAG_FUNCTION,
        ANY_TAG_INSTANCE,
        ANY_TAG_INT,
        ANY_TAG_NIL,
        ANY_TAG_STRING,
    )

    assert [str(element) for element in _ANY.elements] == ["i64", "i64"]
    assert [
        ANY_TAG_NIL,
        ANY_TAG_INT,
        ANY_TAG_FLOAT,
        ANY_TAG_BOOL,
        ANY_TAG_STRING,
        ANY_TAG_CLASS,
        ANY_TAG_INSTANCE,
        ANY_TAG_FUNCTION,
    ] == [0, 1, 2, 3, 4, 5, 6, 7]
    assert [str(element) for element in _CLOSURE.elements] == [
        "i8*",
        "i8*",
        "i8*",
    ]
    assert [str(element) for element in _CLASS_DESC.elements] == [
        "i8*",
        "i64",
        "i8*",
        "i8*",
        "i64",
        "i8*",
        "i64",
        "i64",
        "i64",
        "i8*",
    ]
    assert [str(element) for element in _INTERFACE_ENTRY.elements] == [
        "i64",
        "i8*",
    ]


@pytest.mark.backend
def test_kernel_args_nativo(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """print(args())
""",
    )
    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary), "a", "b"])
    assert native.returncode == 0, native.stderr
    assert native.stdout == '["a", "b"]\n'


@pytest.mark.backend
def test_cache_do_runtime_objeto(tmp_path: Path) -> None:
    """O runtime é compilado uma vez e reusado entre programas (só desempenho)."""
    cache = tmp_path / "cache"
    env = {**os.environ, "LOX_BUILD_CACHE": str(cache)}

    def build(source: str, name: str) -> Path:
        path = _write(tmp_path, source, name)
        binary = tmp_path / f"{name}.bin"
        result = subprocess.run(
            [
                sys.executable,
                str(ENTRYPOINT),
                "--emit",
                "exe",
                "-o",
                str(binary),
                str(path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            env=env,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        return binary

    first = build(
        """print("um")
""",
        "um.lx",
    )
    second = build(
        """print("dois")
""",
        "dois.lx",
    )

    from loxia_core.backend.driver import RUNTIME_SOURCES

    directories = list(cache.glob("runtime-*"))
    assert len(directories) == 1
    objects = list(directories[0].glob("*.o"))
    assert len(objects) == len(RUNTIME_SOURCES)
    assert _run([str(first)]).stdout == "um\n"
    assert _run([str(second)]).stdout == "dois\n"


@pytest.mark.backend
def test_kernel_fs_ambiente_nativo(tmp_path: Path) -> None:
    entries = tmp_path / "entrada"
    entries.mkdir()
    (entries / "b.txt").write_text("b", encoding="utf-8")
    (entries / "a.txt").write_text("a", encoding="utf-8")
    path = _write(
        tmp_path,
        f'print(fs.exists("{entries}"))\n'
        f'print(fs.exists("{tmp_path}/nao-existe"))\n'
        f'print(fs.listDir("{entries}"))\n'
        f'print(fs.listDir("{tmp_path}/nao-existe"))\n'
        f'print(fs.listDir("{entries}/a.txt"))\n',
    )

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    interpreted = _interpret(path)
    assert native.returncode == interpreted.returncode
    assert native.stdout == interpreted.stdout
    assert native.stdout == 'true\nfalse\n["a.txt", "b.txt"]\nnil\nnil\n'


@pytest.mark.backend
def test_kernel_read_all_nativo(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """val text = io.readAll()
print(len(text))
print(text)
""",
    )

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)], input="linha1\nlinha2\n")
    interpreted = _run([sys.executable, str(ENTRYPOINT), str(path)], input="linha1\nlinha2\n")
    assert native.returncode == interpreted.returncode
    assert native.stdout == interpreted.stdout
    assert native.stdout == "14\nlinha1\nlinha2\n\n"


@pytest.mark.backend
def test_std_fs_nativo(tmp_path: Path) -> None:
    data = tmp_path / "dados"
    data.mkdir()
    crlf = data / "crlf.txt"
    crlf.write_bytes(b"a\r\nb\r\n")
    source = (
        "import std.fs as fs\n"
        f'val alvo = "{data}/arquivo.txt"\n'
        f'val pasta = "{data}"\n'
        f'val quebras = "{crlf}"\n'
        """val escrito = fs.writeText(alvo, "a\\nb\\n")
"""
        """match escrito { Result.Ok(_) => print("ok"), Result.Err(e) => print(e.kind) }
"""
        """val lido = fs.readLines(alvo)
"""
        """match lido { Result.Ok(lines) => print(lines), Result.Err(e) => print(e.kind) }
"""
        """val anexado = fs.appendText(alvo, "c\\n")
"""
        """match anexado { Result.Ok(_) => print("ok"), Result.Err(e) => print(e.kind) }
"""
        """val texto = fs.readText(alvo)
"""
        """match texto { Result.Ok(content) => print(content), Result.Err(e) => print(e.kind) }
"""
        """val nomes = fs.listDir(pasta)
"""
        """match nomes { Result.Ok(items) => print(items), Result.Err(e) => print(e.kind) }
"""
        """val ausente = fs.readText(pasta + "/nao-existe")
"""
        """match ausente { Result.Ok(_) => print("ok"), Result.Err(e) => print(e.kind) }
"""
        """print(fs.exists(pasta))
"""
        """val quebrado = fs.readText(quebras)
"""
        """match quebrado { Result.Ok(content) => print(repr(content)), Result.Err(e) => print(e.kind) }
"""
        """match quebrado { Result.Ok(content) => print(len(content)), Result.Err(e) => print(e.kind) }
"""
        """val aberto = fs.open(alvo, "r")
"""
        """val arquivo = match aberto { Result.Ok(handle) => handle, Result.Err(_) => nil }
"""
        """if (arquivo != nil) {
"""
        """  val parte = arquivo.read(2)
"""
        """  match parte { Result.Ok(text) => print(text), Result.Err(e) => print(e.kind) }
"""
        """  val fechado = arquivo.close()
"""
        """  match fechado { Result.Ok(_) => print("closed"), Result.Err(e) => print(e.kind) }
"""
        """  match arquivo.close() { Result.Ok(_) => print("closed"), Result.Err(e) => print(e.kind) }
"""
        """}
"""
    )
    path = _write(tmp_path, source)

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    interpreted = _interpret(path)
    assert native.returncode == interpreted.returncode
    assert native.stdout == interpreted.stdout


@pytest.mark.backend
def test_std_io_nativo(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import std.io as io\n"
        """print(io.readLine())
"""
        """print(io.readAll())
"""
        """print(io.prompt("nome? "))
""",
    )

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)], input="linha\nresto\n")
    interpreted = _run([sys.executable, str(ENTRYPOINT), str(path)], input="linha\nresto\n")
    assert native.returncode == interpreted.returncode
    assert native.stdout == interpreted.stdout


@pytest.mark.backend
def test_campos_container_nativos(tmp_path: Path) -> None:
    source = (
        "class Bag {\n"
        "  val items: List[Int]\n"
        "  val labels: Map[String, Int]\n"
        "  val pair: (Int, String)\n"
        "  val span: Range\n"
        "  init() {\n"
        "    this.items = []\n"
        "    this.labels = {}\n"
        '    this.pair = (1, "a")\n'
        "    this.span = 0..3\n"
        "  }\n"
        "}\n"
        "val bag = Bag()\n"
        "bag.items.push(7)\n"
        'bag.labels["x"] = 9\n'
        """print(bag.items)
"""
        """print(bag.labels)
"""
        """print(bag.pair)
"""
        """print(bag.span)
"""
    )
    path = _write(tmp_path, source)

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    interpreted = _interpret(path)
    assert native.returncode == interpreted.returncode, native.stderr
    assert native.stdout == interpreted.stdout
    assert native.stdout == '[7]\n{"x": 9}\n(1, "a")\n<range 0..3>\n'


@pytest.mark.backend
def test_modulos_nativos(tmp_path: Path) -> None:
    (tmp_path / "lib.lx").write_text(
        "fn dobro(x: Int) -> Int { return x * 2 }\nfn _privado() -> Int { return 1 }\n",
        encoding="utf-8",
    )
    path = _write(
        tmp_path,
        """from lib import dobro
print(dobro(21))
""",
    )

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    assert native.returncode == 0, native.stderr
    assert native.stdout == "42\n"


@pytest.mark.backend
def test_dependencia_path_bate_com_interpretador(tmp_path: Path) -> None:
    app = tmp_path / "app"
    dep = tmp_path / "acme"
    app.mkdir()
    dep.mkdir()
    (app / "loxia.toml").write_text(
        '[dependencies]\nacme = { path = "../acme" }\n',
        encoding="utf-8",
    )
    (dep / "base.lx").write_text("fn dobro(n: Int) -> Int { return n * 2 }\n", encoding="utf-8")
    path = app / "main.lx"
    path.write_text(
        "import acme.base as base\nprint(base.dobro(21))\n",
        encoding="utf-8",
    )

    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    native = _run([str(binary)])
    assert native.stdout == interpreted.stdout == "42\n"
    assert native.stderr == interpreted.stderr == ""
    assert native.returncode == interpreted.returncode == 0


def _run_bytes(arguments: list[str], data: bytes) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        arguments,
        cwd=ROOT,
        input=data,
        capture_output=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


R2_CASOS = (
    'print(substr("a", 0, 9))\n',
    'print(substr("a", -1, 0))\n',
    "print(fromCodePoint(-1))\n",
    'print(charCodeAt("a", 5))\n',
    "os.exit(999)\n",
    "time.sleep(-1)\n",
)


@pytest.mark.backend
@pytest.mark.parametrize("source", R2_CASOS, ids=range(len(R2_CASOS)))
def test_panic_de_primitiva_bate_com_oraculo(tmp_path: Path, source: str) -> None:
    """R2: primitivas antigas reportam o mesmo código, mensagem e posição."""
    path = _write(tmp_path, source)

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    interpreted = _interpret(path)
    assert native.returncode == 70
    assert native.returncode == interpreted.returncode
    assert native.stderr == interpreted.stderr


def _proc_program(py_code: str) -> str:
    import json

    return (
        "import std.proc as p\n"
        "import std.results as results\n"
        f"val py = {json.dumps(sys.executable)}\n"
        f'val out = p.run([py, "-c", {json.dumps(py_code)}])\n'
        "val done = results.toOptional(out)\n"
        'if (done == nil) {\n  print("nil")\n} else {\n'
        "  print(done.code)\n  print(len(done.stdout))\n"
        "  print(repr(done.stderr))\n}\n"
    )


@pytest.mark.backend
def test_std_proc_nativo(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("process.* é POSIX")

    path = _write(
        tmp_path,
        _proc_program(
            "import sys; sys.stdout.write(chr(231)*3000); sys.stderr.write(chr(101)); sys.exit(3)"
        ),
    )
    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    interpreted = _interpret(path)
    assert native.returncode == interpreted.returncode
    assert native.stdout == interpreted.stdout
    assert native.stderr == interpreted.stderr
    assert native.stdout == '3\n3000\n"e"\n'


@pytest.mark.backend
def test_process_spawn_poll_nativo(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("process.* é POSIX")

    import json

    source = (
        "import std.proc as p\n"
        "import std.results as results\n"
        f"val py = {json.dumps(sys.executable)}\n"
        'val spawned = p.spawn([py, "-c", '
        + json.dumps("import sys; sys.stdout.write('eco')")
        + "])\n"
        "val child = results.toOptional(spawned)\n"
        'if (child == nil) {\n  print("nil")\n} else {\n'
        "  val ready = process.poll([child.id, child.stdout.id], 5000)\n"
        "  print(len(ready) >= 1)\n"
        '  print(results.unwrapOr(child.stdout.read(64), "nil"))\n'
        "  print(results.unwrapOr(child.wait(), -1))\n"
        "  child.close()\n}\n"
    )
    path = _write(tmp_path, source)
    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run([str(binary)])
    interpreted = _interpret(path)
    assert native.returncode == interpreted.returncode
    assert native.stdout == interpreted.stdout
    assert native.stdout == "true\neco\n0\n"


@pytest.mark.backend
def test_io_read_utf8_nativo(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "print(io.readUtf8(6))\nprint(io.readUtf8(1))\n",
    )

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    payload = "ação".encode()
    native = _run_bytes([str(binary)], payload)
    interpreted = _run_bytes([sys.executable, str(ENTRYPOINT), str(path)], payload)
    assert native.returncode == interpreted.returncode, native.stderr
    assert native.stdout == interpreted.stdout
    assert native.stderr == interpreted.stderr

    # Bytes inválidos: mesma mensagem, código e posição nos dois motores.
    invalid = _write(tmp_path, "print(io.readUtf8(2))\n", name="invalido.lx")
    result, binary = _build(invalid, tmp_path)
    assert result.returncode == 0, result.stderr

    native = _run_bytes([str(binary)], b"\xff\xfe")
    interpreted = _run_bytes([sys.executable, str(ENTRYPOINT), str(invalid)], b"\xff\xfe")
    assert native.returncode == 70
    assert native.returncode == interpreted.returncode
    assert native.stderr == interpreted.stderr
    assert b"io.readUtf8() expects UTF-8 input." in native.stderr


@pytest.mark.backend
def test_io_write_flush_antes_de_bloquear_no_stdin(tmp_path: Path) -> None:
    """Regressão do R1: `io.write` tem que chegar ao pipe antes do `readLine`.

    O runner normal compara bytes no fim, então não distingue "flushou" de "flushou no
    exit". Aqui o processo escreve, bloqueia no stdin e o teste só entrega a linha
    **depois** de ler a saída — sem o flush, o `select` estoura o timeout.
    """
    if os.name == "nt":
        pytest.skip("select em pipe não é portátil no Windows")

    path = _write(
        tmp_path,
        'io.write("pronto")\nval line = io.readLine()\nprint(line or "nil")\n',
    )
    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr

    commands = [
        [sys.executable, str(ENTRYPOINT), str(path)],
        [str(binary)],
    ]
    for command in commands:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert process.stdout is not None
            ready, _, _ = select.select([process.stdout], [], [], 5.0)
            assert ready, f"stdout não foi flushado antes de bloquear no stdin: {command}"
            assert process.stdout.read(6) == b"pronto"
            assert process.stdin is not None
            process.stdin.write(b"ok\n")
            process.stdin.flush()
            rest, stderr = process.communicate(timeout=TIMEOUT_SECONDS)
            assert rest == b"ok\n", stderr
            assert process.returncode == 0, stderr
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=TIMEOUT_SECONDS)
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()


@pytest.mark.backend
def test_build_nao_escreve_no_stdout(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "enum E { A }\nval x = match E.A { E.A => 1 }\nprint(x)\n",
    )
    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    run = _run([str(binary)])
    assert run.stdout == "1\n"


@pytest.mark.backend
def test_dependencia_path_com_frozen_compila_nos_dois_motores(tmp_path: Path) -> None:
    app = tmp_path / "app"
    dep = tmp_path / "acme"
    app.mkdir()
    dep.mkdir()
    (app / "loxia.toml").write_text(
        '[package]\nname = "app"\n\n[dependencies]\nacme = { path = "../acme" }\n',
        encoding="utf-8",
    )
    (dep / "loxia.toml").write_text(
        '[package]\nname = "acme"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (dep / "base.lx").write_text(
        "fn dobro(n: Int) -> Int { return n * 2 }\n",
        encoding="utf-8",
    )
    entry = app / "main.lx"
    entry.write_text(
        "import acme.base as base\nprint(base.dobro(21))\n",
        encoding="utf-8",
    )
    locked = subprocess.run(
        [sys.executable, str(ENTRYPOINT), "lock"],
        cwd=app,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
        check=False,
    )
    assert locked.returncode == 0, locked.stderr

    interpreted = _run([sys.executable, str(ENTRYPOINT), "run", "--frozen", str(entry)])
    assert interpreted.returncode == 0, interpreted.stderr

    binary = tmp_path / "programa"
    built = _run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "build",
            "--frozen",
            "--emit",
            "exe",
            "-o",
            str(binary),
            str(entry),
        ]
    )
    assert built.returncode == 0, built.stderr
    native = _run([str(binary)])

    assert native.stdout == interpreted.stdout == "42\n"
    assert native.returncode == interpreted.returncode == 0


@pytest.mark.backend
def test_monorepo_do_exemplo_compila_nos_dois_motores(tmp_path: Path) -> None:
    entry = ROOT / "examples" / "monorepo" / "app" / "main.lx"
    interpreted = _run([sys.executable, str(ENTRYPOINT), "run", "--frozen", str(entry)])
    assert interpreted.returncode == 0, interpreted.stderr

    binary = tmp_path / "monorepo"
    built = _run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "build",
            "--frozen",
            "--emit",
            "exe",
            "-o",
            str(binary),
            str(entry),
        ]
    )
    assert built.returncode == 0, built.stderr
    native = _run([str(binary)])

    assert native.stdout == interpreted.stdout == "42\n"
    assert native.returncode == interpreted.returncode == 0


def _budget_program(count: int) -> str:
    lines = ["fn id[T](x: T) -> T { return x }"]
    lines.extend(f"class C{index} {{ }}" for index in range(count))
    lines.extend(f"print(id(C{index}()))" for index in range(count))
    return "\n".join(lines) + "\n"


@pytest.mark.backend
def test_orcamento_de_monomorfizacao_no_limite_compila(tmp_path: Path) -> None:
    path = _write(tmp_path, _budget_program(256))
    output = tmp_path / "budget.ll"

    result = _run(
        [sys.executable, str(ENTRYPOINT), "build", str(path), "--emit=ll", "-o", str(output)]
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()


@pytest.mark.backend
def test_orcamento_de_monomorfizacao_recusa_a_instanciacao_257(tmp_path: Path) -> None:
    path = _write(tmp_path, _budget_program(257))
    output = tmp_path / "budget.ll"

    result = _run(
        [sys.executable, str(ENTRYPOINT), "build", str(path), "--emit=ll", "-o", str(output)]
    )

    assert result.returncode == 65
    assert "error[E4003]" in result.stderr
    assert "Too many generic instantiations (limit 256)" in result.stderr
    assert not output.exists()


@pytest.mark.backend
def test_orcamento_recusa_tipo_aninhado_alem_de_8(tmp_path: Path) -> None:
    depth = "Int"
    value = "1"
    for _ in range(9):
        depth = f"List[{depth}]"
        value = f"[{value}]"
    source = f"fn id[T](x: T) -> T {{ return x }}\nval x: {depth} = {value}\nprint(id(x))\n"
    path = _write(tmp_path, source)

    result = _run([sys.executable, str(ENTRYPOINT), "build", str(path), "--emit=ll"])

    assert result.returncode == 65
    assert "error[E4003]" in result.stderr
    assert "nesting is too deep (limit 8)" in result.stderr


@pytest.mark.backend
def test_orcamento_recusa_nome_mangled_acima_de_1024_bytes(tmp_path: Path) -> None:
    name = "A" * 1100
    source = f"fn id[T](x: T) -> T {{ return x }}\nclass {name} {{ }}\nprint(id({name}()))\n"
    path = _write(tmp_path, source)

    result = _run([sys.executable, str(ENTRYPOINT), "build", str(path), "--emit=ll"])

    assert result.returncode == 65
    assert "error[E4003]" in result.stderr
    assert "Mangled generic name is too long" in result.stderr


def test_orcamento_unitario_de_funcoes_classes_e_profundidade() -> None:
    from loxia_core.backend.lower_generics import MonomorphizationBudget
    from loxia_core.backend.lower_model import BackendError
    from loxia_core.frontend.ty import ClassTy

    budget = MonomorphizationBudget(
        max_functions=1,
        max_classes=1,
        max_depth=1,
        max_mangled_bytes=8,
    )
    budget.spend_function((ClassTy("C"),), "id$C", 1)
    with pytest.raises(BackendError) as too_many:
        budget.spend_function((ClassTy("D"),), "id$D", 1)
    assert too_many.value.code.value == "E4003"

    budget.spend_class((ClassTy("C"),), "Box$C", 1)
    with pytest.raises(BackendError) as too_many_classes:
        budget.spend_class((ClassTy("D"),), "Box$D", 1)
    assert too_many_classes.value.code.value == "E4003"

    depth_budget = MonomorphizationBudget(
        max_functions=2,
        max_classes=2,
        max_depth=1,
        max_mangled_bytes=8,
    )
    with pytest.raises(BackendError) as too_deep:
        depth_budget.spend_function((ClassTy("C", (ClassTy("D"),)),), "id$C", 1)
    assert "nesting is too deep" in str(too_deep.value)

    mangled_budget = MonomorphizationBudget(
        max_functions=2,
        max_classes=2,
        max_depth=8,
        max_mangled_bytes=8,
    )
    with pytest.raises(BackendError) as too_long:
        mangled_budget.spend_function((ClassTy("C"),), "id$" + "x" * 9, 1)
    assert "Mangled generic name is too long" in str(too_long.value)


@pytest.mark.backend
def test_orcamento_de_classes_genericas_recusa_a_instanciacao_257(tmp_path: Path) -> None:
    lines = [
        "class Box[T] {",
        "  var value: T",
        "  init(value: T) { this.value = value }",
        "}",
    ]
    lines.extend(f"class C{index} {{ }}" for index in range(257))
    lines.extend(f"print(Box(C{index}()))" for index in range(257))
    path = _write(tmp_path, "\n".join(lines) + "\n")

    result = _run([sys.executable, str(ENTRYPOINT), "build", str(path), "--emit=ll"])

    assert result.returncode == 65
    assert "error[E4003]" in result.stderr
    assert "Too many generic class instantiations (limit 256)" in result.stderr


@pytest.mark.backend
def test_truthiness_de_containers_e_enum(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """enum E { A }
val xs: List[Int] = [1]
val m: Map[Int, Int] = {1: 2}
val t = (1, 2)
if (xs) print(1)
if (m) print(2)
if (t) print(3)
if (E.A) print(4)
""",
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode


@pytest.mark.backend
def test_subtipo_de_classe_em_parametro(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """class A { }
class B(A) { }
fn take(a: A) -> Int { return 1 }
print(take(B()))
""",
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.stdout == interpreted.stdout
    assert compiled.returncode == interpreted.returncode


@pytest.mark.backend
def test_optional_get_apos_atribuicao_nil(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """class C { var x: Int; init() { this.x = 1 } }
var c: C? = C()
c = nil
print(c?.x)
""",
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.stdout == interpreted.stdout
    assert compiled.returncode == interpreted.returncode


@pytest.mark.backend
def test_i4_lacunas_declaradas(tmp_path: Path) -> None:
    """Casos que o backend não representa devem recusar com a frase do I4."""
    sources = {
        "fnvar.lx": (
            "fn g(x: Any) -> Int { return 1 }\n"
            "fn h(f: fn(Int) -> Int) -> Int { return f(3) }\n"
            "print(h(g))\n"
        ),
        "andopt.lx": "val x: Int? = 1\nprint(x and 1.5)\n",
        "mathany.lx": 'val a: Any = "x"\nprint(math.abs(a))\n',
        "nativevalue.lx": "print(len)\n",
        "enumvalue.lx": "enum E { A }\nprint(E)\n",
    }
    for name, source in sources.items():
        path = _write(tmp_path, source, name)
        checked = _run([sys.executable, str(ENTRYPOINT), "--check", str(path)])
        assert checked.returncode == 0, checked.stderr

        built, _binary = _build(path, tmp_path)
        assert built.returncode == 65, built.stderr
        assert "not supported by the backend yet" in built.stderr, built.stderr


@pytest.mark.backend
def test_debug_checa_overflow_no_binario(tmp_path: Path) -> None:
    path = _write(tmp_path, "print(9223372036854775807 + 1)\n")
    interpreted = _run([sys.executable, str(ENTRYPOINT), "--debug", str(path)])
    assert interpreted.returncode == 70

    binary = tmp_path / "programa"
    result = _run(
        [
            sys.executable,
            str(ENTRYPOINT),
            "--debug",
            "--emit",
            "exe",
            "-o",
            str(binary),
            str(path),
        ]
    )
    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.returncode == interpreted.returncode
    assert compiled.stderr == interpreted.stderr


@pytest.mark.backend
def test_trace_raso_tem_todos_os_frames(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """fn f(n: Int) -> Int {
  if (n <= 0) return 1
  return f(n - 1)
}
f(5)
""",
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.returncode == interpreted.returncode
    assert compiled.stderr == interpreted.stderr


@pytest.mark.backend
def test_recursion_budget_com_try_finally(tmp_path: Path) -> None:
    """3 `try/finally` por ativação não podem estourar o Python antes de 10k."""
    path = _write(
        tmp_path,
        """fn f(n: Int) -> Int {
  try {
  try {
  try {
  if (n <= 0) return 0
  return f(n - 1)
  } finally { val a1 = 0 }
  } finally { val a2 = 0 }
  } finally { val a3 = 0 }
}
print(f(9998))
""",
    )
    interpreted = _interpret(path)
    assert interpreted.returncode == 0, interpreted.stderr[-1000:]

    result, binary = _build(path, tmp_path)
    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.returncode == interpreted.returncode
    assert compiled.stdout == interpreted.stdout


@pytest.mark.backend
def test_oom_nao_e_capturavel(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """fn alloc() -> Nil {
  var xs: List[String] = []
  val s = "abcdefgh"
  var i = 0
  while (i < 2000000) {
    xs.push(s)
    i = i + 1
  }
}
try {
  alloc()
} except RuntimeError as e {
  print("caught")
}
print("after")
""",
    )
    result, binary = _build(path, tmp_path, max_heap="32M")
    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])

    assert compiled.returncode == 70
    assert compiled.stdout == ""
    assert "Out of memory." in compiled.stderr
    assert "caught" not in compiled.stdout


@pytest.mark.backend
def test_goldens_de_runtime_error_batem_bytes(tmp_path: Path) -> None:
    """Todo golden de erro de runtime que passa no check deve ter stderr idêntico.

    O corpus `LEVELS` não inclui os goldens de erro; este teste fecha a lacuna que
    deixou passar mensagens de índice/range/cast divergentes.
    """
    from tests.runner import parse_expectations

    cases = []
    for path in sorted((ROOT / "tests" / "cases").rglob("*.lx")):
        expectations = parse_expectations(path.read_text(encoding="utf-8"))
        if expectations.exit_code != 70 or expectations.error is None:
            continue
        checked = _run([sys.executable, str(ENTRYPOINT), "--check", str(path)])
        if checked.returncode != 0:
            continue
        cases.append(path)

    assert cases, "nenhum golden de runtime error check-clean encontrado"

    for index, path in enumerate(cases):
        interpreted = _interpret(path)
        case_dir = tmp_path / f"case_{index}"
        case_dir.mkdir()
        result, binary = _build(path, case_dir)
        assert result.returncode == 0, f"{path}: {result.stderr}"
        compiled = _run([str(binary)])

        assert compiled.stdout == interpreted.stdout, path
        assert compiled.stderr == interpreted.stderr, path
        assert compiled.returncode == interpreted.returncode, path


@pytest.mark.backend
def test_fs_read_utf8_pending_bate_com_o_binario(tmp_path: Path) -> None:
    target = tmp_path / "utf8.txt"
    target.write_text("éxABCD", encoding="utf-8")
    path = _write(
        tmp_path,
        "import std.fs as fs\n"
        f'val r = fs.open("{target}", "r")\n'
        "val f = match r { Result.Ok(h) => h, Result.Err(_) => nil }\n"
        "if (f != nil) {\n"
        "  print(repr(f.read(1)))\n"
        "  print(repr(f.read(2)))\n"
        "  print(repr(f.read(1)))\n"
        "  print(repr(f.read(2)))\n"
        "  print(repr(f.read(2)))\n"
        "  print(repr(f.read(1)))\n"
        "}\n",
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode


@pytest.mark.backend
def test_fs_nul_e_rename_kind_batem_com_o_binario(tmp_path: Path) -> None:
    empty = tmp_path / "vazio"
    occupied = tmp_path / "ocupado"
    empty.mkdir()
    occupied.mkdir()
    (occupied / "arquivo").write_text("x", encoding="utf-8")
    path = _write(
        tmp_path,
        "import std.fs as fs\n"
        'print(match fs.stat("nao\\0existe") { Result.Ok(_) => "ok", Result.Err(e) => e.kind })\n'
        'print(match fs.rename("a\\0x", "b") { Result.Ok(_) => "ok", Result.Err(e) => e.kind })\n'
        'print(match fs.remove("a\\0x") { Result.Ok(_) => "ok", Result.Err(e) => e.kind })\n'
        'print(match fs.mkdir("a\\0x") { Result.Ok(_) => "ok", Result.Err(e) => e.kind })\n'
        'print(match fs.open("a\\0x", "r") { Result.Ok(_) => "ok", Result.Err(e) => e.kind })\n'
        'print(fs.exists("a\\0x"))\n'
        'print(match fs.listDir("a\\0x") { Result.Ok(_) => "ok", Result.Err(e) => e.kind })\n'
        f'print(match fs.rename("{empty}", "{occupied}") {{ Result.Ok(_) => "ok", Result.Err(e) => e.kind }})\n',
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode
    assert "notEmpty" in interpreted.stdout


@pytest.mark.backend
def test_fs_read_bytes_erro_de_diretorio_bate_com_o_binario(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "import std.fs as fs\n"
        f'val opened = fs.open("{tmp_path}", "r")\n'
        "val file = match opened { Result.Ok(value) => value, Result.Err(_) => fs.File(0) }\n"
        'print(match file.read(1) { Result.Ok(value) => value ?? "nil", Result.Err(e) => e.kind })\n'
        'print(match file.readBytes(1) { Result.Ok(value) => value?.toHex() ?? "nil", Result.Err(e) => e.kind })\n',
    )
    interpreted = _interpret(path)
    result, binary = _build(path, tmp_path)

    assert result.returncode == 0, result.stderr
    compiled = _run([str(binary)])
    assert compiled.stdout == interpreted.stdout
    assert compiled.stderr == interpreted.stderr
    assert compiled.returncode == interpreted.returncode
    assert "isDirectory" in interpreted.stdout

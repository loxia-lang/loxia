# SPDX-License-Identifier: MIT OR Apache-2.0
"""Testes do subcomando `loxia test` (ADR-0096)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from tests.inprocess import Result, run_cli

ROOT = Path(__file__).resolve().parent.parent

PASS = """
import std.test as t
val suite = t.Suite()
suite.it("passa", fn() { t.expect(1 + 1).toBe(2) })
suite.done()
"""

FAIL = """
import std.test as t
val suite = t.Suite()
suite.it("falha", fn() { t.expect(1).toBe(2) })
suite.done()
"""


def run_test(
    *args: str,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> Result:
    # `--native` compila e executa binários: mantém o processo real para o teste
    # não herdar cache/handles do pytest (o runner em si já isola cada arquivo).
    if "--native" in args:
        environment = None if env is None else {**os.environ, **env}
        process = subprocess.run(
            [sys.executable, "-m", "loxia", "test", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
        )
        return Result(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
    return run_cli("test", *args, cwd=cwd, env=env)


def project(tmp_path: Path) -> Path:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pass_test.lx").write_text(PASS, encoding="utf-8")
    (tests / "fail_test.lx").write_text(FAIL, encoding="utf-8")
    (tests / "helper.lx").write_text("print(1)\n", encoding="utf-8")
    return tests


def test_descobre_agrega_e_sai_um(tmp_path: Path) -> None:
    result = run_test(str(project(tmp_path)))
    assert result.returncode == 1
    assert "not ok 1 - falha" in result.stdout
    assert "ok 2 - passa" in result.stdout
    assert "# tests 2" in result.stdout
    assert "# files 2" in result.stdout
    assert "helper" not in result.stdout


def test_json_tem_envelope_estavel(tmp_path: Path) -> None:
    result = run_test(str(project(tmp_path)), "--json")
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["summary"] == {
        "files": 2,
        "tests": 2,
        "pass": 1,
        "fail": 1,
        "skip": 0,
    }
    statuses = {item["name"]: item["status"] for item in payload["tests"]}
    assert statuses == {"passa": "pass", "falha": "fail"}


def test_isolamento_de_exit_e_timeout(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "ok_test.lx").write_text(PASS, encoding="utf-8")
    (tests / "sai_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("antes", fn() { t.expect(1).toBe(1) })\n'
        "os.exit(7)\n",
        encoding="utf-8",
    )
    result = run_test(str(tests))
    assert result.returncode == 1
    assert "ok 1 - passa" in result.stdout
    assert "exit 7" in result.stdout
    slow = tests / "lento_test.lx"
    slow.write_text(
        "import std.test as t\nval suite = t.Suite()\n"
        'suite.it("dorme", fn() { time.sleep(5000) })\nsuite.done()\n',
        encoding="utf-8",
    )
    slow_result = run_test(str(slow), "--timeout", "250")
    assert slow_result.returncode == 1
    assert "timeout" in slow_result.stdout


def test_filtro_e_jobs(tmp_path: Path) -> None:
    tests = project(tmp_path)
    filtered = run_test(str(tests), "--filter", "passa", "--jobs", "2")
    assert filtered.returncode == 0
    assert "ok 1 - passa" in filtered.stdout
    assert "# fail 0" in filtered.stdout


def test_sem_arquivos_sai_dois(tmp_path: Path) -> None:
    empty = tmp_path / "vazio"
    empty.mkdir()
    result = run_test(str(empty))
    assert result.returncode == 2
    assert "nenhum arquivo" in result.stderr


EXIT_SOURCE = """
import std.test as t
val suite = t.Suite()
suite.it("estoura", fn() { os.exit(7) })
suite.it("sobrevive", fn() { t.expect(1 + 1).toBe(2) })
suite.done()
"""


def test_isolamento_por_teste_sobrevive_a_exit(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "a_test.lx").write_text(EXIT_SOURCE, encoding="utf-8")
    result = run_test(str(tests), "--isolate", "test", "--jobs", "2")
    assert result.returncode == 1
    assert "not ok 1 - estoura" in result.stdout
    assert "ok 2 - sobrevive" in result.stdout


def test_isolamento_por_teste_em_json(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "a_test.lx").write_text(EXIT_SOURCE, encoding="utf-8")
    result = run_test(str(tests), "--isolate", "test", "--json")
    payload = json.loads(result.stdout)
    statuses = {item["name"]: item["status"] for item in payload["tests"]}
    assert statuses == {"estoura": "fail", "sobrevive": "pass"}


@pytest.mark.backend
def test_isolamento_por_teste_nativo(tmp_path: Path) -> None:
    pytest.importorskip("llvmlite")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "a_test.lx").write_text(PASS, encoding="utf-8")
    result = run_test(str(tests), "--native", "--isolate", "test")
    assert result.returncode == 0, result.stderr
    assert "ok 1 - passa" in result.stdout


def test_json_exibe_caminho_relativo_ao_cwd(tmp_path: Path) -> None:
    tests = tmp_path / "tests" / "sub"
    tests.mkdir(parents=True)
    (tests / "pass_test.lx").write_text(PASS, encoding="utf-8")

    result = run_test("tests", "--json", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["tests"][0]["file"] == "tests/sub/pass_test.lx"


def test_suite_vazia_avisa_e_require_tests_sai_cinco(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "empty_test.lx").write_text(
        "import std.test as t\nval suite = t.Suite()\nsuite.done()\n",
        encoding="utf-8",
    )

    result = run_test(str(tests))
    assert result.returncode == 0
    assert "warning: no tests were selected" in result.stderr

    required = run_test(str(tests), "--require-tests")
    assert required.returncode == 5
    assert "warning: no tests were selected" in required.stderr


def test_filtro_sem_match_nao_e_falso_verde(tmp_path: Path) -> None:
    tests = project(tmp_path)
    result = run_test(str(tests), "--filter", "nao-existe", "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["summary"]["tests"] == 0
    assert "warning: no tests were selected" in result.stderr

    required = run_test(str(tests), "--filter", "nao-existe", "--require-tests")
    assert required.returncode == 5


def test_saida_do_teste_nao_vira_resultado(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "spoof_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'print("ok 1 - falso")\n'
        'suite.it("real", fn() { t.expect(1).toBe(1) })\n'
        'print("not ok 2 - falso")\n'
        "suite.done()\n",
        encoding="utf-8",
    )

    result = run_test(str(tests), "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert [item["name"] for item in payload["tests"]] == ["real"]
    assert payload["summary"]["tests"] == 1


def test_nome_com_hash_nao_quebra_o_json(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "hash_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("a # SKIP b", fn() { t.expect(1).toBe(2) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )

    result = run_test(str(tests), "--json")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["tests"][0]["name"] == "a # SKIP b"
    assert payload["tests"][0]["status"] == "fail"
    assert payload["tests"][0]["kind"] == "assertion"


def test_jobs_preserva_ordem_e_conteudo(tmp_path: Path) -> None:
    tests = project(tmp_path)
    serial = run_test(str(tests), "--json", "--jobs", "1")
    parallel = run_test(str(tests), "--json", "--jobs", "4")

    def strip(result: Result) -> list[tuple[str, str, str]]:
        return [
            (item["file"], item["name"], item["status"])
            for item in json.loads(result.stdout)["tests"]
        ]

    assert strip(serial) == strip(parallel)


def test_capture_inclui_stdout_da_falha(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "print_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("falha", fn() { print("antes"); t.expect(1).toBe(2) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )

    plain = run_test(str(tests), "--json")
    captured = run_test(str(tests), "--json", "--capture")

    assert json.loads(plain.stdout)["tests"][0]["output"] is None
    assert json.loads(captured.stdout)["tests"][0]["output"] == "antes"


def test_json_tem_envelope_de_resultado(tmp_path: Path) -> None:
    tests = project(tmp_path)
    payload = json.loads(run_test(str(tests), "--json").stdout)
    assert payload["command"] == "test"
    assert payload["success"] is False
    assert payload["exit_code"] == 1
    assert set(payload["tests"][0]) == {
        "file",
        "name",
        "status",
        "kind",
        "message",
        "location",
        "output",
    }


@pytest.mark.backend
def test_location_nativa_igual_ao_interpretador(tmp_path: Path) -> None:
    pytest.importorskip("llvmlite")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "fail_test.lx").write_text(FAIL, encoding="utf-8")

    interpreted = json.loads(run_test(str(tests), "--json").stdout)
    native = json.loads(run_test(str(tests), "--json", "--native").stdout)

    assert interpreted["tests"][0]["location"] == native["tests"][0]["location"]
    assert interpreted["tests"][0]["location"] is not None


def test_junit_xml(tmp_path: Path) -> None:
    tests = project(tmp_path)
    (tests / "skip_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("pula", fn() { suite.skip("sem rede") })\n'
        "suite.done()\n",
        encoding="utf-8",
    )
    report = tmp_path / "junit.xml"

    result = run_test(str(tests), "--junit", str(report))

    assert result.returncode == 1
    root = ET.parse(report).getroot()
    assert root.tag == "testsuites"
    assert root.attrib["tests"] == "3"
    assert root.attrib["failures"] == "1"
    assert root.attrib["skipped"] == "1"
    failures = root.findall(".//failure")
    assert len(failures) == 1
    assert "expected 2, got 1" in (failures[0].text or "")
    assert failures[0].attrib["type"] == "assertion"
    assert len(root.findall(".//skipped")) == 1


def test_json_lines_tem_testes_e_summary(tmp_path: Path) -> None:
    tests = project(tmp_path)
    result = run_test(str(tests), "--json-lines")

    assert result.returncode == 1
    lines = [json.loads(line) for line in result.stdout.splitlines() if line]
    assert [line["type"] for line in lines] == ["test", "test", "summary"]
    assert lines[-1]["tests"] == 2
    assert lines[-1]["fail"] == 1
    assert lines[-1]["exit_code"] == 1


def test_json_e_json_lines_sao_exclusivos(tmp_path: Path) -> None:
    result = run_test(str(tmp_path), "--json", "--json-lines")
    assert result.returncode == 2
    assert "mutuamente exclusivos" in result.stderr


def test_tap_escapa_hash_no_nome(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "hash_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("a # SKIP b", fn() { t.expect(1).toBe(2) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )

    result = run_test(str(tests))

    assert "a \\# SKIP b" in result.stdout


@pytest.mark.backend
def test_build_nativo_em_paralelo(tmp_path: Path) -> None:
    pytest.importorskip("llvmlite")
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("a", "b"):
        (tests / f"{name}_test.lx").write_text(PASS, encoding="utf-8")

    result = run_test(str(tests), "--native", "--jobs", "2")

    assert result.returncode == 0, result.stderr
    assert "# files 2" in result.stdout


def test_binary_cache_key_muda_com_a_fonte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from loxia.test_runner import _binary_cache_key

    monkeypatch.chdir(tmp_path)
    source = tmp_path / "cache_test.lx"
    source.write_text("print(1)\n", encoding="utf-8")
    before = _binary_cache_key([source], ())
    source.write_text("print(2)\n", encoding="utf-8")
    after = _binary_cache_key([source], ())

    assert before != after


@pytest.mark.backend
def test_native_cache_reusa_o_mesmo_binario(tmp_path: Path) -> None:
    pytest.importorskip("llvmlite")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pass_test.lx").write_text(PASS, encoding="utf-8")
    cache = tmp_path / "cache"
    env = {"LOX_BUILD_CACHE": str(cache)}

    first = run_test(str(tests), "--native", "--jobs", "1", cwd=tmp_path, env=env)
    assert first.returncode == 0, first.stderr
    binaries = [path for path in (cache / "tests").glob("*/*") if path.is_file()]
    assert binaries, "o binário nativo deveria estar no cache"
    inode = binaries[0].stat().st_ino

    second = run_test(str(tests), "--native", "--jobs", "1", cwd=tmp_path, env=env)
    assert second.returncode == 0, second.stderr
    assert binaries[0].stat().st_ino == inode


@pytest.mark.backend
def test_native_no_cache_nao_escreve_cache(tmp_path: Path) -> None:
    pytest.importorskip("llvmlite")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pass_test.lx").write_text(PASS, encoding="utf-8")
    cache = tmp_path / "cache"

    result = run_test(
        str(tests),
        "--native",
        "--no-cache",
        cwd=tmp_path,
        env={"LOX_BUILD_CACHE": str(cache)},
    )

    assert result.returncode == 0, result.stderr
    assert not (cache / "tests").exists()


def test_cached_build_publica_e_reusa(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from loxia import test_runner

    source = tmp_path / "cache_test.lx"
    source.write_text("print(1)\n", encoding="utf-8")
    calls = 0

    def fake_build(path: Path, binary: Path, deps: tuple[str, ...] = ()) -> None:
        nonlocal calls
        calls += 1
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
        return None

    monkeypatch.setattr(test_runner, "_build", fake_build)
    cache_dir = tmp_path / "cache"
    binary, error = test_runner._cached_build(source, tmp_path / "fallback", (), cache_dir, "key")
    assert error is None
    assert binary is not None
    assert Path(binary).is_file()
    assert calls == 1

    reused, error = test_runner._cached_build(source, tmp_path / "fallback", (), cache_dir, "key")
    assert error is None
    assert reused == binary
    assert calls == 1


def test_binary_cache_dir_respeita_variavel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from loxia import test_runner

    monkeypatch.setenv("LOX_BUILD_CACHE", str(tmp_path / "cache"))
    assert test_runner._binary_cache_dir() == tmp_path / "cache" / "tests"


def test_build_all_usa_cache_por_conteudo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from loxia import test_runner

    monkeypatch.setenv("LOX_BUILD_CACHE", str(tmp_path / "cache"))
    source = tmp_path / "suite_test.lx"
    source.write_text("print(1)\n", encoding="utf-8")
    calls = 0

    def fake_build(path: Path, binary: Path, deps: tuple[str, ...] = ()) -> None:
        nonlocal calls
        calls += 1
        binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        binary.chmod(0o755)
        return None

    monkeypatch.setattr(test_runner, "_build", fake_build)
    binaries, errors = test_runner._build_all(
        [source], str(tmp_path / "tmp"), (), 1, use_cache=True
    )
    assert errors == {}
    assert binaries[source] is not None
    assert calls == 1

    source.write_text("print(2)\n", encoding="utf-8")
    binaries, errors = test_runner._build_all(
        [source], str(tmp_path / "tmp"), (), 1, use_cache=True
    )
    assert errors == {}
    assert binaries[source] is not None
    assert calls == 2


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _git_project(tmp_path: Path) -> tuple[Path, Path]:
    tests = tmp_path / "tests"
    lib = tests / "lib"
    tests.mkdir()
    lib.mkdir()
    (lib / "math.lx").write_text("fn double(x: Int) -> Int { return x * 2 }\n", encoding="utf-8")
    (tests / "uses_test.lx").write_text(
        "import std.test as t\n"
        "import lib.math as m\n"
        "val suite = t.Suite()\n"
        'suite.it("usa lib", fn() { t.expect(m.double(2)).toBe(4) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )
    (tests / "other_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("independente", fn() { t.expect(1).toBe(1) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "test")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "init")
    return tests, lib


def _files(payload: str) -> list[str]:
    return [item["file"] for item in json.loads(payload)["tests"]]


def test_changed_seleciona_dependentes(tmp_path: Path) -> None:
    tests, lib = _git_project(tmp_path)

    empty = run_test(str(tests), "--changed", "--json", cwd=tmp_path)
    assert empty.returncode == 0
    assert _files(empty.stdout) == []
    required = run_test(str(tests), "--changed", "--require-tests", "--json", cwd=tmp_path)
    assert required.returncode == 5

    (lib / "math.lx").write_text(
        "fn double(x: Int) -> Int { return x * 2 }\n# mudou\n", encoding="utf-8"
    )
    changed = run_test(str(tests), "--changed", "--json", cwd=tmp_path)
    assert changed.returncode == 0
    assert _files(changed.stdout) == ["tests/uses_test.lx"]


def test_changed_inclui_teste_alterado_e_untracked(tmp_path: Path) -> None:
    tests, _ = _git_project(tmp_path)
    (tests / "other_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("mudou", fn() { t.expect(1).toBe(1) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )

    payload = run_test(str(tests), "--changed=HEAD", "--json", cwd=tmp_path)
    assert payload.returncode == 0
    assert _files(payload.stdout) == ["tests/other_test.lx"]

    new = tests / "new_test.lx"
    new.write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("novo", fn() { t.expect(1).toBe(1) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )
    payload = run_test(str(tests), "--changed", "--json", cwd=tmp_path)
    assert payload.returncode == 0
    assert "tests/new_test.lx" in _files(payload.stdout)


def test_changed_arquivo_nao_lox_roda_tudo(tmp_path: Path) -> None:
    tests, _ = _git_project(tmp_path)
    readme = tmp_path / "README.md"
    readme.write_text("antes\n", encoding="utf-8")
    _git(tmp_path, "add", "README.md")
    _git(tmp_path, "commit", "-qm", "readme")
    readme.write_text("depois\n", encoding="utf-8")

    payload = run_test(str(tests), "--changed", "--json", cwd=tmp_path)
    assert payload.returncode == 0
    assert _files(payload.stdout) == ["tests/other_test.lx", "tests/uses_test.lx"]


def test_changed_fora_de_repo_e_erro(tmp_path: Path) -> None:
    tests = project(tmp_path)
    result = run_test(str(tests), "--changed", cwd=tmp_path)
    assert result.returncode == 2
    assert "git" in result.stderr.lower()


def test_shard_particiona_arquivos_sem_sobrepor(tmp_path: Path) -> None:
    tests = project(tmp_path)
    (tests / "third_test.lx").write_text(
        "import std.test as t\n"
        "val suite = t.Suite()\n"
        'suite.it("terceiro", fn() { t.expect(1).toBe(1) })\n'
        "suite.done()\n",
        encoding="utf-8",
    )

    first = run_test(str(tests), "--shard=1/2", "--json", cwd=tmp_path)
    second = run_test(str(tests), "--shard=2/2", "--json", cwd=tmp_path)
    first_files = _files(first.stdout)
    second_files = _files(second.stdout)

    assert set(first_files).isdisjoint(second_files)
    assert set(first_files) | set(second_files) == {
        "tests/fail_test.lx",
        "tests/pass_test.lx",
        "tests/third_test.lx",
    }


@pytest.mark.parametrize("value", ["0/2", "3/2", "1/0", "1", "a/b"])
def test_shard_invalido_e_erro(tmp_path: Path, value: str) -> None:
    tests = project(tmp_path)
    result = run_test(str(tests), f"--shard={value}", cwd=tmp_path)
    assert result.returncode == 2
    assert "--shard" in result.stderr


def test_binary_cache_key_inclui_dependencia_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mudança em dependência externa precisa invalidar o binário nativo."""
    from loxia.test_runner import _binary_cache_key

    project = tmp_path / "proj"
    tests = project / "tests"
    tests.mkdir(parents=True)
    dependency = tmp_path / "dep"
    dependency.mkdir()
    (project / "loxia.toml").write_text(
        '[package]\nname = "demo"\nversion = "0.1.0"\n\n'
        '[dependencies]\ndep = { path = "../dep" }\n',
        encoding="utf-8",
    )
    dep_file = dependency / "lib.lx"
    dep_file.write_text("fn value() -> Int { return 1 }\n", encoding="utf-8")
    test = tests / "dep_test.lx"
    test.write_text("print(1)\n", encoding="utf-8")

    monkeypatch.chdir(project)
    before = _binary_cache_key([test], ())
    dep_file.write_text("fn value() -> Int { return 2 }\n", encoding="utf-8")
    after = _binary_cache_key([test], ())

    assert before != after


TYPE_ERROR_TEST = """
import std.test as t
fn f(x: Int) -> Int { return x }
val suite = t.Suite()
suite.it("tipo", fn() { t.expect(f("a")).toBe(0) })
suite.done()
"""


def test_precheck_reprova_erro_de_tipo_antes_de_rodar(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "type_test.lx").write_text(TYPE_ERROR_TEST, encoding="utf-8")

    result = run_test(str(tests))

    assert result.returncode == 1
    assert "not ok 1 - <" in result.stdout
    assert "error[E3001]" in result.stdout
    assert "Argument 1: Expected Int, found String." in result.stdout


def test_no_check_desliga_o_precheck(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "type_test.lx").write_text(TYPE_ERROR_TEST, encoding="utf-8")

    result = run_test(str(tests), "--no-check")

    assert result.returncode == 1
    assert "not ok 1 - tipo" in result.stdout
    assert "expected 0" in result.stdout


def test_precheck_aceita_teste_sem_anotacao(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "pass_test.lx").write_text(PASS, encoding="utf-8")

    result = run_test(str(tests))

    assert result.returncode == 0
    assert "ok 1 - passa" in result.stdout


GENERIC_TEST = """
import std.test as t
fn g(x) { return x }
val suite = t.Suite()
suite.it("a", fn() { t.expect(g(1)).toBe(1) })
suite.done()
"""


def test_precheck_aceita_helper_sem_anotacao_em_generico(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "g_test.lx").write_text(GENERIC_TEST, encoding="utf-8")

    result = run_test(str(tests))

    assert result.returncode == 0
    assert "ok 1 - a" in result.stdout


def test_precheck_native_curto_circuita_antes_do_build(tmp_path: Path) -> None:
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "type_test.lx").write_text(TYPE_ERROR_TEST, encoding="utf-8")

    result = run_test(str(tests), "--native")

    assert result.returncode == 1
    assert "error[E3001]" in result.stdout
    assert "native build failed" not in result.stdout

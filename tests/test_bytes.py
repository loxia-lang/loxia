# SPDX-License-Identifier: MIT OR Apache-2.0
"""`Bytes` no interpretador (79a): checker, métodos, formatação e erros."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from tests.runner import check_case

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
GOLDEN = ROOT / "tests" / "cases" / "bytes" / "bytes_core.lx"


def _run(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "caso.lx"
    path.write_text(source, encoding="utf-8")
    return path


def test_golden_de_bytes_no_interpretador() -> None:
    assert check_case(GOLDEN) == []


def test_check_rejeita_bytes_como_chave_de_map(tmp_path: Path) -> None:
    checked = _run(["--check", str(_write(tmp_path, "val m: Map[Bytes, Int] = {}\n"))])
    assert checked.returncode == 65
    assert "Map keys must be String, Int or Bool." in checked.stderr


def test_check_rejeita_tipos_e_aridades_erradas(tmp_path: Path) -> None:
    checked = _run(["--check", str(_write(tmp_path, 'val b: Bytes = "texto"\n'))])
    assert checked.returncode == 65
    assert "Expected Bytes, found String." in checked.stderr

    checked = _run(["--check", str(_write(tmp_path, "print(Bytes.empty().slice(0))\n"))])
    assert checked.returncode == 65
    assert "Expected 2 arguments but got 1." in checked.stderr

    checked = _run(["--check", str(_write(tmp_path, "print(BytesError.InvalidHex())\n"))])
    assert checked.returncode == 65
    assert "Expected 1 arguments but got 0." in checked.stderr

    checked = _run(["--check", str(_write(tmp_path, "print(Bytes.fromHex(1))\n"))])
    assert checked.returncode == 65
    assert "Expected String, found Int." in checked.stderr


def test_indice_fora_da_faixa_e_runtime_error(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'var out = "no"\ntry {\n  print(Bytes.empty()[0])\n} except RuntimeError as error {\n'
        "  out = error.message\n}\nprint(out)\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "Bytes index 0 out of bounds for length 0.\n"


def test_slice_fora_da_faixa_e_runtime_error(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'var out = "no"\ntry {\n  print(Bytes.fromText("ab").slice(1, 3))\n'
        "} except RuntimeError as error {\n  out = error.message\n}\nprint(out)\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "Bytes.slice() index out of bounds.\n"


def test_from_list_valida_a_faixa(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'var out = "no"\ntry {\n  Bytes.fromList([256])\n} except RuntimeError as error {\n'
        "  out = error.message\n}\nprint(out)\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "Bytes.fromList() expects integers in 0..255.\n"


def test_concat_com_tipo_errado_vindo_de_any(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'val data = Bytes.fromText("a")\nval any: Any = 1\nvar out = "no"\n'
        "try {\n  print(data.concat(any))\n} except RuntimeError as error {\n"
        "  out = error.message\n}\nprint(out)\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "Bytes.concat() expects Bytes.\n"


def test_bytes_nao_e_chave_de_map_em_runtime(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'val m: Map[Any, Int] = {}\nvar out = "no"\ntry {\n  m[Bytes.empty()] = 1\n'
        "} except RuntimeError as error {\n  out = error.message\n}\nprint(out)\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "Map keys must be strings, integers or booleans.\n"


def test_is_bytes_estreita_any(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'val any: Any = Bytes.fromText("a")\nif (any is Bytes) {\n  print(any.toHex())\n}\n',
    )
    assert _run(["--check", str(program)]).returncode == 0
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "61\n"


def test_bytes_error_nao_e_exception(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'val error = BytesError.InvalidHex("detail")\n'
        "print(error is BytesError)\nprint(error is Exception)\n"
        "print(match error {\n"
        "  BytesError.InvalidHex(message) => message,\n"
        "  BytesError.InvalidBase64(message) => message,\n"
        "  BytesError.InvalidUtf8(message) => message\n"
        "})\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "true\nfalse\ndetail\n"


def test_check_limpo_com_bytes_opcional_e_any(tmp_path: Path) -> None:
    program = _write(
        tmp_path,
        'val b: Bytes = Bytes.fromText("ok")\n'
        "val maybe: Bytes? = b\n"
        "val list: List[Bytes] = [b]\n"
        "val any: Any = b\n"
        "print(maybe?.toHex())\n"
        "print(len(list))\n"
        "if (any is Bytes) {\n  print((any as Bytes).toHex())\n}\n",
    )
    checked = _run(["--check", str(program)])
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize("text", ["Zg", "Zh==", "Zg=", "!@@@"])
def test_base64_canonico_rejeita_entradas_invalidas(tmp_path: Path, text: str) -> None:
    program = _write(
        tmp_path,
        f'print(match Bytes.fromBase64("{text}") {{\n'
        '  Result.Ok(_) => "ok",\n'
        "  Result.Err(error) => match error {\n"
        '    BytesError.InvalidHex(_) => "invalidHex",\n'
        '    BytesError.InvalidBase64(_) => "invalidBase64",\n'
        '    BytesError.InvalidUtf8(_) => "invalidUtf8"\n'
        "  }\n"
        "})\n",
    )
    executed = _run([str(program)])
    assert executed.returncode == 0
    assert executed.stdout == "invalidBase64\n"

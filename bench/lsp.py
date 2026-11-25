# SPDX-License-Identifier: MIT OR Apache-2.0
"""Benchmark end-to-end do LSP sobre stdio (follow-up de #130).

Uso:
    uv run python bench/lsp.py
    uv run python bench/lsp.py --repeat 7 --json
    uv run python bench/lsp.py --update

Mede o processo real (`main.py lsp`) num workspace com `examples/` e `std/`:
startup/initialize, didOpen com diagnósticos (imports), hover, definition,
references cross-file, documentHighlight, rename local, completion, documentSymbol
e didChange. Cada amostra sobe um servidor novo; a mediana das amostras é reportada.
Não roda no CI.
"""

from __future__ import annotations

import argparse
import json
import select
import statistics
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"
BASELINE_PATH = Path(__file__).resolve().parent / "lsp_baseline.json"
DEFAULT_REPEAT = 5
SAMPLES_PER_METRIC = 5
DEFAULT_TOLERANCE = 1.5
READ_TIMEOUT_SECONDS = 30.0
WORKSPACE_MODULES = 48


@dataclass(frozen=True)
class Measurement:
    name: str
    median_ms: float
    min_ms: float


class Lsp:
    """Cliente JSON-RPC mínimo, sem dependências (mesmo framing dos testes)."""

    def __init__(self, root: Path) -> None:
        self.process = subprocess.Popen(
            [sys.executable, str(ENTRYPOINT), "lsp"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self._next_id = 1
        self.root = root

    def send(self, payload: dict[str, Any]) -> None:
        assert self.process.stdin is not None
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.process.stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
        self.process.stdin.write(body)
        self.process.stdin.flush()

    def read(self) -> dict[str, Any]:
        assert self.process.stdout is not None
        ready, _, _ = select.select([self.process.stdout], [], [], READ_TIMEOUT_SECONDS)
        if not ready:
            raise TimeoutError("LSP não respondeu")
        headers: dict[str, str] = {}
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("LSP encerrou sem resposta")
            if line in (b"\r\n", b"\n"):
                break
            name, _, value = line.decode("ascii").partition(":")
            headers[name.strip().lower()] = value.strip()
        body = self.process.stdout.read(int(headers["content-length"]))
        return cast(dict[str, Any], json.loads(body))

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self.send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self.read()
            if message.get("id") == request_id:
                return message.get("result")

    def wait_diagnostics(self, uri: str) -> None:
        while True:
            message = self.read()
            params = message.get("params")
            if (
                message.get("method") == "textDocument/publishDiagnostics"
                and isinstance(params, dict)
                and params.get("uri") == uri
            ):
                return

    def initialize(self) -> None:
        self.request(
            "initialize",
            {
                "rootUri": self.root.as_uri(),
                "initializationOptions": {"inlayHints": {"enabled": True}},
            },
        )
        self.notify("initialized", {})

    def shutdown(self) -> None:
        try:
            self.request("shutdown", {})
            self.notify("exit", {})
        finally:
            self.process.terminate()
            self.process.wait(timeout=5)


def _position(text: str, offset: int) -> dict[str, int]:
    line = text.count("\n", 0, offset)
    last_newline = text.rfind("\n", 0, offset)
    return {"line": line, "character": offset - last_newline - 1}


def _position_after(text: str, needle: str) -> dict[str, int]:
    return _position(text, text.index(needle) + len(needle))


LIB = """/// A person with a name and an age.
class Pessoa {
  val nome: String
  val idade: Int

  fn init(nome: String, idade: Int) {
    this.nome = nome
    this.idade = idade
  }

  fn descricao() -> String {
    return this.nome + " (" + str(this.idade) + ")"
  }
}

fn soma(a: Int, b: Int) -> Int {
  return a + b
}

fn dobro(x: Int) -> Int {
  return soma(x, x)
}
"""

MAIN = """import std.lists as lists
from lib import Pessoa, soma

val pessoa: Pessoa = Pessoa("Ada", 36)
val xs = [1, 2, 3]
val total: Int = soma(lists.sum(xs), pessoa.idade)
print(pessoa.descricao())
print(total)
"""


def _workspace() -> tempfile.TemporaryDirectory[str]:
    directory = tempfile.TemporaryDirectory(prefix="loxia-lsp-bench-")
    root = Path(directory.name)
    (root / "lib.lx").write_text(LIB, encoding="utf-8")
    (root / "main.lx").write_text(MAIN, encoding="utf-8")
    # Workspace com ~50 arquivos: o custo de descoberta/leitura do root não pode
    # ficar escondido atrás de um fixture de dois arquivos.
    for index in range(WORKSPACE_MODULES):
        (root / f"mod_{index:02d}.lx").write_text(
            f"val valor_{index}: Int = {index}\n"
            f"fn fun_{index}(x: Int) -> Int {{ return x + {index} }}\n",
            encoding="utf-8",
        )
    return directory


def _timed(call: Callable[[], object]) -> float:
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def _measure(
    name: str,
    call: Callable[[], object],
    samples: int,
    validate: Callable[[object], bool] | None = None,
) -> Measurement:
    warmup = call()  # aquecimento: caches de módulo/índice do servidor
    if validate is not None:
        assert validate(warmup), f"{name} não produziu resultado"
    values = [_timed(call) for _ in range(samples)]
    return Measurement(
        name=name, median_ms=statistics.median(values) * 1000, min_ms=min(values) * 1000
    )


def run_session() -> dict[str, float]:
    directory = _workspace()
    root = Path(directory.name)
    main = root / "main.lx"
    uri = main.as_uri()
    text = main.read_text(encoding="utf-8")
    changed = text.replace('Pessoa("Ada", 36)', 'Pessoa("Ada", 37)', 1)
    assert changed != text

    type_position = _position(text, text.index("Pessoa", text.index("pessoa")))
    hover_position = _position_after(text, "pessoa.")
    completion_position = _position_after(text, "pessoa.")
    total_position = _position(text, text.index("val total") + len("val "))
    definition_position = _position(text, text.index("soma(", text.index("val total")))

    started = time.perf_counter()
    lsp = Lsp(root)
    try:
        lsp.initialize()
        startup = time.perf_counter() - started

        def open_document() -> None:
            lsp.notify(
                "textDocument/didOpen",
                {
                    "textDocument": {
                        "uri": uri,
                        "languageId": "loxia",
                        "version": 1,
                        "text": text,
                    }
                },
            )
            lsp.wait_diagnostics(uri)

        open_ms = _timed(open_document)

        def request(method: str, params: dict[str, Any]) -> Callable[[], object]:
            return lambda: lsp.request(method, {"textDocument": {"uri": uri}, **params})

        version = 1
        current = text

        def change() -> None:
            nonlocal version, current
            version += 1
            current = changed if current == text else text
            lsp.notify(
                "textDocument/didChange",
                {
                    "textDocument": {"uri": uri, "version": version},
                    "contentChanges": [{"text": current}],
                },
            )
            lsp.wait_diagnostics(uri)

        reference_call = request(
            "textDocument/references",
            {"position": type_position, "context": {"includeDeclaration": True}},
        )
        started = time.perf_counter()
        cold_references = reference_call()
        references_cold = (time.perf_counter() - started) * 1000
        assert isinstance(cold_references, list) and len(cold_references) >= 2

        metrics = [
            _measure(
                "hover",
                request("textDocument/hover", {"position": hover_position}),
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, dict) and "contents" in value,
            ),
            _measure(
                "definition",
                request("textDocument/definition", {"position": definition_position}),
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, dict) and "uri" in value,
            ),
            _measure(
                "references",
                reference_call,
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, list) and len(value) >= 2,
            ),
            _measure(
                "highlight",
                request("textDocument/documentHighlight", {"position": total_position}),
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, list) and len(value) >= 2,
            ),
            _measure(
                "rename",
                request(
                    "textDocument/rename",
                    {"position": total_position, "newName": "sum_total"},
                ),
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, dict) and bool(value.get("changes")),
            ),
            _measure(
                "completion",
                request("textDocument/completion", {"position": completion_position}),
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, dict) and bool(value.get("items")),
            ),
            _measure(
                "symbols",
                request("textDocument/documentSymbol", {}),
                SAMPLES_PER_METRIC,
                lambda value: isinstance(value, list) and bool(value),
            ),
        ]

        change()  # o cache do workspace é descartado a cada edição
        started = time.perf_counter()
        after_change = reference_call()
        references_after_change = (time.perf_counter() - started) * 1000
        assert isinstance(after_change, list) and len(after_change) >= 2

        metrics.append(_measure("did_change", change, SAMPLES_PER_METRIC))
    finally:
        lsp.shutdown()
        directory.cleanup()

    result = {
        "startup": startup * 1000,
        "did_open": open_ms * 1000,
        "references_cold": references_cold,
        "references_after_change": references_after_change,
    }
    result.update({item.name: item.median_ms for item in metrics})
    return result


def _print(result: dict[str, float]) -> None:
    print(f"{'métrica':<14} {'mediana':>10}")
    print("-" * 26)
    for name, value in result.items():
        print(f"{name:<14} {value:>8.2f}ms")


def _compare(result: dict[str, float], tolerance: float) -> bool:
    if not BASELINE_PATH.exists():
        print(f"sem baseline em {BASELINE_PATH.relative_to(ROOT).as_posix()}")
        return True
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    regressions = 0
    for name, value in result.items():
        reference = baseline.get(name)
        if not isinstance(reference, (int, float)) or value <= 0:
            continue
        ratio = value / float(reference)
        status = "REGRESSÃO" if ratio > tolerance else "ok"
        if ratio > tolerance:
            regressions += 1
        print(f"{name:<14} x{ratio:.2f} vs baseline  {status}")
    return regressions == 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bench/lsp.py", description=__doc__)
    parser.add_argument("--repeat", type=int, default=DEFAULT_REPEAT)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--update", action="store_true", help="regrava o baseline")
    args = parser.parse_args(argv)
    if args.repeat < 1:
        print("--repeat deve ser >= 1", file=sys.stderr)
        return 2

    sessions = [run_session() for _ in range(args.repeat)]
    result = {
        name: statistics.median(session[name] for session in sessions) for name in sessions[0]
    }
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    else:
        _print(result)

    if args.update:
        BASELINE_PATH.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"baseline: {BASELINE_PATH.relative_to(ROOT).as_posix()}")
        return 0
    return 0 if _compare(result, args.tolerance) else 1


if __name__ == "__main__":
    raise SystemExit(main())

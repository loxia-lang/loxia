# SPDX-License-Identifier: MIT OR Apache-2.0
"""Transcrição JSON-RPC sobre stdio usando `std.framing` + `std.jsonrpc` em Lox.

O teste roda um programa Lox real com stdin binário fixo e compara os bytes de stdout:
é o consumidor que a issue #9 pede, sem depender de um servidor LSP em Loxia.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "main.py"

PROGRAM = """from std.framing import FrameFailure, encodeFrame, readFrame, readStdin, writeStdout
from std.jsonrpc import RpcFailure, decode, encode, failure, idOf, isRequest, methodOf, success

var running = true

fn reply(id: Any, method: String) -> Map[String, Any] {
  if (method == "initialize") {
    return success(id, {"capabilities": {"textDocumentSync": 1}})
  }
  if (method == "shutdown") {
    return success(id, nil)
  }
  return failure(id, -32601, "Method not found")
}

fn accept(message: Map[String, Any]) -> Nil {
  if (not isRequest(message)) {
    return
  }
  val id = idOf(message)
  val method = methodOf(message) ?? ""
  writeStdout(encodeFrame(encode(reply(id, method))))
}

fn reject(error: RpcFailure) -> Nil {
  writeStdout(encodeFrame(encode(failure(nil, error.code, error.message))))
  running = false
}

fn consume(body: String?) -> Nil {
  if (body == nil) {
    running = false
    return
  }
  match decode(body) {
    Result.Ok(message) => accept(message),
    Result.Err(error) => reject(error)
  }
}

fn failFrame(error: FrameFailure) -> Nil {
  io.writeErr("framing: ${error.kind}\\n")
  running = false
}

while (running) {
  match readFrame(readStdin) {
    Result.Ok(body) => consume(body),
    Result.Err(error) => failFrame(error)
  }
}
"""


def _frame(body: str) -> bytes:
    encoded = body.encode("utf-8")
    return b"Content-Length: " + str(len(encoded)).encode("ascii") + b"\r\n\r\n" + encoded


def _run(tmp_path: Path, data: bytes) -> subprocess.CompletedProcess[bytes]:
    script = tmp_path / "transcript.lx"
    script.write_text(PROGRAM, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), "--interpret", str(script)],
        cwd=ROOT,
        input=data,
        capture_output=True,
        text=False,
        check=False,
    )


def test_transcricao_initialize_shutdown_e_notificacao(tmp_path: Path) -> None:
    data = (
        _frame('{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}')
        + _frame('{"jsonrpc":"2.0","method":"initialized","params":{}}')
        + _frame('{"jsonrpc":"2.0","id":2,"method":"shutdown"}')
        + _frame('{"jsonrpc":"2.0","id":3,"method":"unknown"}')
    )
    result = _run(tmp_path, data)

    expected = (
        _frame('{"jsonrpc":"2.0","id":1,"result":{"capabilities":{"textDocumentSync":1}}}')
        + _frame('{"jsonrpc":"2.0","id":2,"result":null}')
        + _frame('{"jsonrpc":"2.0","id":3,"error":{"code":-32601,"message":"Method not found"}}')
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    assert result.stderr == b""


def test_corpo_invalido_vira_parse_error(tmp_path: Path) -> None:
    result = _run(tmp_path, _frame("{"))

    expected = _frame('{"jsonrpc":"2.0","id":null,"error":{"code":-32700,"message":"Parse error"}}')
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
    assert result.stderr == b""


def test_frame_truncado_nao_escreve_em_stdout(tmp_path: Path) -> None:
    result = _run(tmp_path, b"Content-Length: 10\r\n\r\n{}")

    assert result.returncode == 0, result.stderr
    assert result.stdout == b""
    assert result.stderr == b"framing: truncated\n"

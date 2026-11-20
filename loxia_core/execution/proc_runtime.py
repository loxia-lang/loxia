# SPDX-License-Identifier: MIT OR Apache-2.0
"""Handles de `proc.*`: processos e streams do kernel (1-based; 0 = falha).

O estado (tabela de handles) vive no interpretador (`interpreter.proc_handles`), não
como global: `Loxia.run` pode rodar várias vezes no mesmo processo (REPL, testes) e
handles de uma execução não podem sobreviver à outra.

Convenções compartilhadas com `runtime/proc.c`:

- id 0 nunca é válido; `spawn` devolve 0 quando não conseguiu criar o processo;
- `read(n)` devolve **até** `n` bytes, sempre em fronteira de caractere UTF-8: uma
  sequência incompleta no fim é guardada para a próxima chamada; se o stream terminar no
  meio de um caractere, é erro (`proc.read() expects UTF-8 input.`);
- `poll` mistura streams (legíveis/EOF) e processos (já saíram); timeout negativo é
  infinito e `0` é não bloqueante;
- `close` invalida o handle (usar depois é "proc: invalid handle.") e um processo não é
  morto por `close` — só tem os descritores liberados.
"""

from __future__ import annotations

import contextlib
import os
import select
import subprocess
import time
from dataclasses import dataclass

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution.lox_list import LoxList

MAX_HANDLES = 256
INVALID = "proc: invalid handle."


@dataclass
class _Handle:
    kind: str  # "stream" | "process"
    fd: int = -1
    process: subprocess.Popen[bytes] | None = None
    status: int | None = None
    pending: bytes = b""
    streams: tuple[int, int, int] = (0, 0, 0)


class ProcTable:
    """Tabela de handles de uma execução."""

    def __init__(self) -> None:
        self._handles: dict[int, _Handle] = {}
        self._next = 1

    # -- infraestrutura -------------------------------------------------
    def _new(self, handle: _Handle) -> int:
        if len(self._handles) >= MAX_HANDLES:
            return 0
        while self._next in self._handles:
            self._next = self._next % MAX_HANDLES + 1
        identifier = self._next
        self._handles[identifier] = handle
        self._next = self._next % MAX_HANDLES + 1
        return identifier

    def _get(self, identifier: int) -> _Handle:
        handle = self._handles.get(identifier)
        if handle is None:
            raise NativeError(INVALID)
        return handle

    def _stream(self, identifier: int, name: str) -> _Handle:
        handle = self._get(identifier)
        if handle.kind != "stream":
            raise NativeError(f"{name}() expects a stream handle.")
        return handle

    def _process(self, identifier: int, name: str) -> _Handle:
        handle = self._get(identifier)
        if handle.kind != "process":
            raise NativeError(f"{name}() expects a process handle.")
        return handle

    @staticmethod
    def _close_fd(fd: int) -> None:
        with contextlib.suppress(OSError):
            os.close(fd)

    # -- processos -------------------------------------------------------
    def spawn(self, argv: LoxList) -> int:
        arguments: list[str] = []
        for item in argv.elements:
            if not isinstance(item, str):
                raise NativeError("process.spawn() expects List[String].")
            arguments.append(item)
        if not arguments:
            return 0

        stdin_read, stdin_write = os.pipe()
        stdout_read, stdout_write = os.pipe()
        stderr_read, stderr_write = os.pipe()
        try:
            process = subprocess.Popen(
                arguments,
                stdin=stdin_read,
                stdout=stdout_write,
                stderr=stderr_write,
                close_fds=True,
            )
        except OSError:
            for fd in (
                stdin_read,
                stdin_write,
                stdout_read,
                stdout_write,
                stderr_read,
                stderr_write,
            ):
                self._close_fd(fd)
            return 0

        self._close_fd(stdin_read)
        self._close_fd(stdout_write)
        self._close_fd(stderr_write)

        process_id = self._new(_Handle(kind="process", process=process))
        stdin_id = self._new(_Handle(kind="stream", fd=stdin_write))
        stdout_id = self._new(_Handle(kind="stream", fd=stdout_read))
        stderr_id = self._new(_Handle(kind="stream", fd=stderr_read))
        if 0 in (process_id, stdin_id, stdout_id, stderr_id):
            for identifier, fd in (
                (process_id, -1),
                (stdin_id, stdin_write),
                (stdout_id, stdout_read),
                (stderr_id, stderr_read),
            ):
                if identifier in self._handles:
                    del self._handles[identifier]
                if fd >= 0:
                    self._close_fd(fd)
            process.kill()
            process.wait()
            return 0

        self._handles[process_id].streams = (stdin_id, stdout_id, stderr_id)
        return process_id

    def stream_id(self, identifier: int, which: int, name: str) -> int:
        handle = self._process(identifier, name)
        return handle.streams[which]

    def wait(self, identifier: int) -> int:
        handle = self._process(identifier, "process.wait")
        if handle.status is None:
            assert handle.process is not None
            handle.status = handle.process.wait()
        return handle.status

    def kill(self, identifier: int) -> bool:
        handle = self._process(identifier, "process.kill")
        assert handle.process is not None
        if handle.status is not None or handle.process.poll() is not None:
            return False
        handle.process.kill()
        return True

    def close(self, identifier: int) -> None:
        if identifier not in self._handles:
            return
        handle = self._handles.pop(identifier)
        if handle.kind == "stream":
            self._close_fd(handle.fd)
            return
        for stream_id in handle.streams:
            stream = self._handles.pop(stream_id, None)
            if stream is not None:
                self._close_fd(stream.fd)

    # -- streams ---------------------------------------------------------
    def read(self, identifier: int, count: int) -> str | None:
        handle = self._stream(identifier, "process.read")
        if count < 0:
            raise NativeError("process.read() expects a non-negative count.")
        if count == 0:
            return ""
        if handle.pending and count <= len(handle.pending):
            # `n` menor que a sequência parcial: não dá para completar um caractere.
            return ""

        data = handle.pending
        handle.pending = b""
        eof = False
        while len(data) < count:
            try:
                chunk = os.read(handle.fd, count - len(data))
            except OSError:
                eof = True
                break
            if not chunk:
                eof = True
                break
            data += chunk
        if not data:
            return None

        cut = _complete_prefix(data)
        if cut < len(data):
            handle.pending = data[cut:]
            data = data[:cut]
        if not data:
            if eof:
                raise NativeError("process.read() expects UTF-8 input.")
            return ""
        try:
            return data.decode("utf-8")
        except UnicodeError:
            raise NativeError("process.read() expects UTF-8 input.") from None

    def write(self, identifier: int, text: str) -> bool:
        handle = self._stream(identifier, "process.write")
        data = text.encode("utf-8")
        total = 0
        while total < len(data):
            try:
                written = os.write(handle.fd, data[total:])
            except OSError:
                return False
            if written <= 0:
                return False
            total += written
        return True

    # -- poll ------------------------------------------------------------
    def poll(self, identifiers: LoxList, timeout_ms: int) -> LoxList:
        ids: list[int] = []
        for item in identifiers.elements:
            if not isinstance(item, int) or isinstance(item, bool):
                raise NativeError("process.poll() expects List[Int].")
            ids.append(item)
        handles = [(identifier, self._get(identifier)) for identifier in ids]
        deadline = None if timeout_ms < 0 else time.monotonic() + timeout_ms / 1000.0

        while True:
            ready: list[int] = []
            for identifier, handle in handles:
                if (
                    handle.kind == "process"
                    and handle.process is not None
                    and handle.process.poll() is not None
                ):
                    ready.append(identifier)

            fds = [handle.fd for _, handle in handles if handle.kind == "stream"]
            if fds:
                if ready:
                    wait = 0.0
                elif deadline is None:
                    wait = None
                else:
                    wait = max(0.0, deadline - time.monotonic())
                readable, _, _ = select.select(fds, [], [], wait)
                ready.extend(
                    identifier
                    for identifier, handle in handles
                    if handle.kind == "stream" and handle.fd in readable
                )

            if ready:
                seen: set[int] = set()
                ordered: list[object] = []
                for identifier in ids:
                    if identifier in ready and identifier not in seen:
                        seen.add(identifier)
                        ordered.append(identifier)
                return LoxList(ordered)

            if deadline is not None and time.monotonic() >= deadline:
                return LoxList([])
            if not fds:
                pause = 0.005
                if deadline is not None:
                    pause = min(pause, max(0.0, deadline - time.monotonic()))
                time.sleep(pause)


def _complete_prefix(data: bytes) -> int:
    """Maior prefixo de `data` que termina em fronteira de caractere UTF-8."""
    cut = len(data)
    back = 0
    while cut > 0 and back < 3 and (data[cut - 1] & 0xC0) == 0x80:
        cut -= 1
        back += 1
    if cut == 0:
        return 0
    lead = data[cut - 1]
    if lead < 0x80:
        need = 1
    elif (lead & 0xE0) == 0xC0:
        need = 2
    elif (lead & 0xF0) == 0xE0:
        need = 3
    else:
        need = 4
    have = len(data) - (cut - 1)
    return len(data) if have >= need else cut - 1

# SPDX-License-Identifier: MIT OR Apache-2.0
"""Handles de `fs.open` para arquivos (1-based; 0 nunca é válido).

O estado vive no interpretador (`interpreter.fs_handles`), não como global: `Loxia.run`
pode rodar várias vezes no mesmo processo (REPL, testes) e handles de uma execução não
podem sobreviver à outra.

Contrato compartilhado com `runtime/kernel.c`:

- `open(path, mode)` devolve o id e levanta `NativeError("<kind>: <detail>")` na falha;
  `kind` é um token estável (sem `strerror`/locale): `notFound`, `permission`,
  `isDirectory`, `tooManyFiles`, `badMode`, `io`;
- `read(id, n)` devolve até `n` bytes em fronteira UTF-8 (bytes pendentes ficam no
  handle); `nil` é EOF; conteúdo que não é UTF-8 estrito é erro;
- `write(id, text)` grava tudo ou levanta;
- `close(id)` é idempotente: fechar de novo não é erro; id fora da faixa nunca existiu e
  levanta `invalidHandle`.
"""

from __future__ import annotations

import contextlib
import errno
import os
from dataclasses import dataclass, field

from loxia_core.diagnostics.errors import NativeError

MAX_HANDLES = 256
KINDS = {
    errno.ENOENT: "notFound",
    errno.EACCES: "permission",
    errno.EPERM: "permission",
    errno.EISDIR: "isDirectory",
    errno.ENOTDIR: "notDirectory",
    errno.EEXIST: "alreadyExists",
    errno.EMFILE: "tooManyFiles",
    errno.ENFILE: "tooManyFiles",
    errno.ENOSPC: "noSpace",
}
MODES = {"r": "r", "w": "w", "a": "a"}


def _kind(error: OSError) -> str:
    return KINDS.get(error.errno if error.errno is not None else 0, "io")


@dataclass
class _Handle:
    fd: int
    mode: str
    pending: bytes = field(default=b"")


class FileTable:
    """Handles de arquivo da execução; ids são índices 1-based."""

    def __init__(self) -> None:
        self._handles: list[_Handle | None] = [None] * MAX_HANDLES

    def _slot(self, identifier: int) -> _Handle:
        if identifier < 1 or identifier > MAX_HANDLES:
            raise NativeError("fs: invalid handle.")
        handle = self._handles[identifier - 1]
        if handle is None:
            raise NativeError("closed: handle is already closed.")
        return handle

    def open(self, path: str, mode: str) -> int:
        if mode not in MODES:
            raise NativeError("badMode: expected 'r', 'w' or 'a'.")
        try:
            fd = os.open(
                path,
                {"r": os.O_RDONLY, "w": os.O_WRONLY, "a": os.O_WRONLY}[mode]
                | (os.O_CREAT | os.O_TRUNC if mode == "w" else 0)
                | (os.O_CREAT | os.O_APPEND if mode == "a" else 0),
            )
        except OSError as error:
            raise NativeError(f"{_kind(error)}: can't open the file.") from None
        for index, slot in enumerate(self._handles):
            if slot is None:
                self._handles[index] = _Handle(fd, mode)
                return index + 1
        os.close(fd)
        raise NativeError("tooManyFiles: too many open files.")

    def read(self, identifier: int, count: int) -> str | None:
        handle = self._slot(identifier)
        if handle.mode != "r":
            raise NativeError("badMode: handle is not open for reading.")
        if count < 0:
            raise NativeError("fs.read() expects a non-negative size.")
        if count == 0:
            return ""
        # O mesmo contrato do runtime C: `n` é um teto de bytes; uma sequência
        # incompleta fica pendente e não pode ser devolvida antes de completar.
        if handle.pending and count <= len(handle.pending):
            return ""
        data = bytearray(handle.pending)
        handle.pending = b""
        eof = False
        while len(data) < count:
            try:
                chunk = os.read(handle.fd, count - len(data))
            except OSError as error:
                raise NativeError(f"{_kind(error)}: read failed.") from None
            if not chunk:
                eof = True
                break
            data += chunk
        if not data:
            return None
        cut = _complete_prefix(bytes(data))
        if cut < len(data):
            handle.pending = bytes(data[cut:])
            del data[cut:]
        if not data:
            if eof:
                raise NativeError("io: file ends inside a UTF-8 sequence.") from None
            return ""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            raise NativeError("io: file is not valid UTF-8.") from None

    def write(self, identifier: int, text: str) -> None:
        handle = self._slot(identifier)
        if handle.mode == "r":
            raise NativeError("badMode: handle is not open for writing.")
        data = text.encode("utf-8")
        try:
            while data:
                written = os.write(handle.fd, data)
                data = data[written:]
        except OSError as error:
            raise NativeError(f"{_kind(error)}: write failed.") from None

    def close(self, identifier: int) -> None:
        if identifier < 1 or identifier > MAX_HANDLES:
            raise NativeError("fs: invalid handle.")
        handle = self._handles[identifier - 1]
        if handle is None:
            return
        self._handles[identifier - 1] = None
        with contextlib.suppress(OSError):
            os.close(handle.fd)

    def close_all(self) -> None:
        for identifier in range(1, MAX_HANDLES + 1):
            self.close(identifier)


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

"""Tabela única das primitivas monomórficas do kernel (ADR-0071).

Cada entrada liga a assinatura Lox (`lox`), o símbolo C (`c_symbol`), os tipos da
tabela e o corpo Python que serve de oráculo. O checker, o interpretador e o backend
consomem esta tabela; não há regra de tipo duplicada por nome.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from src.diagnostics.errors import NativeError
from src.execution.lox_list import LoxList
from src.frontend.ty import BOOL, INT, NIL, STRING, ListTy, Ty, union


def _substr(text: str, start: int, end: int) -> str:
    if start < 0 or end < start or end > len(text):
        raise NativeError("substr() index out of bounds.")
    return text[start:end]


def _join(parts: LoxList, separator: str) -> str:
    values: list[str] = []
    for item in parts.elements:
        if not isinstance(item, str):
            raise NativeError("join() expects List[String].")
        values.append(item)
    return separator.join(values)


def _char_code_at(text: str, index: int) -> int:
    if index < 0 or index >= len(text):
        raise NativeError("charCodeAt() index out of bounds.")
    return ord(text[index])


def _from_code_point(code_point: int) -> str:
    if (
        code_point < 0
        or code_point > 0x10FFFF
        or 0xD800 <= code_point <= 0xDFFF
    ):
        raise NativeError("fromCodePoint() expects a valid Unicode code point.")
    return chr(code_point)


def _args(interpreter: object) -> LoxList:
    argv = getattr(interpreter, "argv", [])
    return LoxList(list(argv))


def _read_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as file:
            return file.read()
    except (OSError, UnicodeError):
        return None


def _write_file(path: str, text: str) -> bool:
    try:
        with open(path, "w", encoding="utf-8", newline="") as file:
            file.write(text)
        return True
    except OSError:
        return False


def _read_line() -> str | None:
    line = sys.stdin.readline()
    if line == "":
        return None
    if line.endswith("\n"):
        line = line[:-1]
    if line.endswith("\r"):
        line = line[:-1]
    return line


def _write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _write_err(text: str) -> None:
    sys.stderr.write(text)
    sys.stderr.flush()


def _os_exit(code: int) -> None:
    if code < 0 or code > 255:
        raise NativeError("os.exit() expects a code between 0 and 255.")
    raise SystemExit(code)


def _getenv(name: str) -> str | None:
    return os.environ.get(name)


def _now() -> int:
    return time.time_ns() // 1_000_000


def _sleep(milliseconds: int) -> None:
    if milliseconds < 0:
        raise NativeError("time.sleep() expects a non-negative duration.")
    time.sleep(milliseconds / 1000.0)


@dataclass(frozen=True)
class Primitive:
    lox: str
    c_symbol: str
    params: tuple[Ty, ...]
    result: Ty
    py: Callable[..., object]
    ambient: bool = False
    needs_interpreter: bool = False


PRIMITIVES: tuple[Primitive, ...] = (
    Primitive(
        "substr", "lox_substr", (STRING, INT, INT), STRING, _substr
    ),
    Primitive(
        "join", "lox_join", (ListTy(STRING), STRING), STRING, _join
    ),
    Primitive(
        "charCodeAt", "lox_char_code_at", (STRING, INT), INT, _char_code_at
    ),
    Primitive(
        "fromCodePoint", "lox_from_code_point", (INT,), STRING, _from_code_point
    ),
    Primitive("args", "lox_args", (), ListTy(STRING), _args, ambient=True,
              needs_interpreter=True),
    Primitive("io.readFile", "lox_io_read_file", (STRING,),
              union(STRING, NIL), _read_file, ambient=True),
    Primitive("io.write", "lox_io_write", (STRING,), NIL, _write),
    Primitive("io.writeErr", "lox_io_write_err", (STRING,), NIL, _write_err),
    Primitive("io.writeFile", "lox_io_write_file", (STRING, STRING), BOOL,
              _write_file, ambient=True),
    Primitive("io.readLine", "lox_io_read_line", (), union(STRING, NIL),
              _read_line, ambient=True),
    Primitive("os.exit", "lox_os_exit", (INT,), NIL, _os_exit),
    Primitive("os.getenv", "lox_os_getenv", (STRING,), union(STRING, NIL),
              _getenv, ambient=True),
    Primitive("time.now", "lox_time_now", (), INT, _now, ambient=True),
    Primitive("time.sleep", "lox_time_sleep", (INT,), NIL, _sleep, ambient=True),
)

PRIMITIVE_BY_LOX: dict[str, Primitive] = {
    primitive.lox: primitive for primitive in PRIMITIVES
}


class PrimitiveCallable:
    """Adaptador do corpo Python para o protocolo `LoxCallable`."""

    def __init__(self, primitive: Primitive) -> None:
        self.primitive = primitive

    def min_arity(self) -> int:
        return len(self.primitive.params)

    def max_arity(self) -> int:
        return len(self.primitive.params)

    def call(self, interpreter: object, arguments: list[object]) -> object:
        if self.primitive.needs_interpreter:
            return self.primitive.py(interpreter)
        return self.primitive.py(*arguments)

    def __str__(self) -> str:
        return "<native fn>"

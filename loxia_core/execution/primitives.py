# SPDX-License-Identifier: MIT OR Apache-2.0
"""Tabela única das primitivas monomórficas do kernel (ADR-0071).

Cada entrada liga a assinatura Lox (`lox`), o símbolo C (`c_symbol`), os tipos da
tabela e o corpo Python que serve de oráculo. O checker, o interpretador e o backend
consomem esta tabela; não há regra de tipo duplicada por nome.

A documentação pública destas primitivas mora em `loxia/builtins_docs.py` (fonte da
página `docs/stdlib/builtins.md`); este módulo guarda a implementação/oráculo.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import sys
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from loxia_core.diagnostics.errors import NativeError
from loxia_core.execution import regex_runtime
from loxia_core.execution.fs_runtime import FileTable
from loxia_core.execution.lox_list import LoxList
from loxia_core.execution.lox_tuple import LoxTuple
from loxia_core.execution.proc_runtime import ProcTable
from loxia_core.frontend.ty import BOOL, BYTES, INT, NIL, STRING, ListTy, TupleTy, Ty, union


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
    if code_point < 0 or code_point > 0x10FFFF or 0xD800 <= code_point <= 0xDFFF:
        raise NativeError("fromCodePoint() expects a valid Unicode code point.")
    return chr(code_point)


def _args(interpreter: object) -> LoxList:
    argv = getattr(interpreter, "argv", [])
    return LoxList(list(argv))


def _read_file(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8", newline="") as file:
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
    # Lê bytes e decodifica UTF-8 estrito: `sys.stdin` usa `surrogateescape` no
    # locale C e ecoaria os bytes inválidos em vez de falhar.
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        data: bytes = stream.readline()
        if not data:
            return None
        try:
            line = data.decode("utf-8")
        except UnicodeError:
            raise NativeError("io.readLine() expects UTF-8 input.") from None
    else:
        try:
            line = sys.stdin.readline()
        except UnicodeError:
            raise NativeError("io.readLine() expects UTF-8 input.") from None
        if line == "":
            return None
    if line.endswith("\n"):
        line = line[:-1]
    if line.endswith("\r"):
        line = line[:-1]
    return line


def _read_all() -> str:
    stream = getattr(sys.stdin, "buffer", None)
    if stream is not None:
        data: bytes = stream.read()
        try:
            return data.decode("utf-8")
        except UnicodeError:
            raise NativeError("io.readAll() expects UTF-8 input.") from None
    try:
        return sys.stdin.read()
    except UnicodeError:
        raise NativeError("io.readAll() expects UTF-8 input.") from None


def _read_utf8(count: int) -> str | None:
    """Lê exatamente `count` bytes UTF-8 de stdin; `nil` só no EOF imediato."""
    if count < 0:
        raise NativeError("io.readUtf8() expects a non-negative count.")
    if count == 0:
        return ""
    stream = getattr(sys.stdin, "buffer", None)
    if stream is None:
        raise NativeError("io.readUtf8() requires binary standard input.")
    data: bytes = stream.read(count)
    if not data:
        return None
    if len(data) < count:
        raise NativeError(f"io.readUtf8() expects exactly {count} bytes.")
    try:
        return data.decode("utf-8")
    except UnicodeError:
        raise NativeError("io.readUtf8() expects UTF-8 input.") from None


def _flush() -> None:
    sys.stdout.flush()
    sys.stderr.flush()


def _exists(path: str) -> bool:
    if "\0" in path:
        return False
    return os.path.exists(path)


def _list_dir(path: str) -> LoxList | None:
    if "\0" in path:
        return None
    try:
        entries = sorted(os.listdir(path))
    except OSError:
        return None
    return LoxList(list(entries))


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


def _fs_table(interpreter: object) -> FileTable:
    table = getattr(interpreter, "fs_handles", None)
    if not isinstance(table, FileTable):
        table = FileTable()
        setattr(interpreter, "fs_handles", table)  # noqa: B010
    return table


def _fs_open(interpreter: object, path: str, mode: str) -> int:
    return _fs_table(interpreter).open(path, mode)


def _fs_read(interpreter: object, identifier: int, count: int) -> str | None:
    return _fs_table(interpreter).read(identifier, count)


def _fs_write(interpreter: object, identifier: int, text: str) -> None:
    _fs_table(interpreter).write(identifier, text)


def _fs_close(interpreter: object, identifier: int) -> None:
    _fs_table(interpreter).close(identifier)


def _fs_read_bytes(interpreter: object, identifier: int, count: int) -> bytes | None:
    return _fs_table(interpreter).read_bytes(identifier, count)


_FS_ERROR_KINDS = {
    errno.ENOENT: "notFound",
    errno.EACCES: "permission",
    errno.EPERM: "permission",
    errno.EISDIR: "isDirectory",
    errno.ENOTDIR: "notDirectory",
    errno.EEXIST: "alreadyExists",
    errno.EMFILE: "tooManyFiles",
    errno.ENFILE: "tooManyFiles",
    errno.ENOSPC: "noSpace",
    errno.ENOTEMPTY: "notEmpty",
    errno.EXDEV: "crossDevice",
}


def _fs_failure(action: str, error: OSError) -> NativeError:
    """Erro de host com `kind` estável; nunca `strerror`/locale (ADR-0119)."""
    kind = _FS_ERROR_KINDS.get(error.errno or 0, "io")
    return NativeError(f"{kind}: {action}.")


def _fs_invalid_path() -> NativeError:
    return NativeError("io: invalid path.")


def _fs_rename(source: str, target: str) -> None:
    try:
        os.replace(source, target)
    except ValueError:
        raise _fs_invalid_path() from None
    except OSError as error:
        raise _fs_failure("can't rename", error) from None


def _fs_remove(path: str) -> None:
    try:
        os.remove(path)
    except ValueError:
        raise _fs_invalid_path() from None
    except OSError as error:
        # macOS returns EPERM for unlink(directory); normalize to the same kind as
        # Linux (EISDIR) so the public `kind` does not depend on the platform.
        if os.path.isdir(path):
            raise NativeError("isDirectory: can't remove a directory.") from None
        raise _fs_failure("can't remove", error) from None


def _fs_mkdir(path: str) -> None:
    try:
        os.mkdir(path)
    except ValueError:
        raise _fs_invalid_path() from None
    except OSError as error:
        raise _fs_failure("can't create the directory", error) from None


def _fs_stat(path: str) -> LoxTuple:
    try:
        info = os.stat(path)
    except ValueError:
        raise _fs_invalid_path() from None
    except OSError as error:
        raise _fs_failure("can't stat", error) from None
    mtime_ms = info.st_mtime_ns // 1_000_000
    return LoxTuple((info.st_size, mtime_ms, stat.S_ISDIR(info.st_mode)))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _proc_table(interpreter: object) -> ProcTable:
    table = getattr(interpreter, "proc_handles", None)
    if not isinstance(table, ProcTable):
        table = ProcTable()
        setattr(interpreter, "proc_handles", table)  # noqa: B010
    return table


def _proc_spawn(interpreter: object, argv: LoxList) -> int:
    return _proc_table(interpreter).spawn(argv)


def _proc_stdin(interpreter: object, identifier: int) -> int:
    return _proc_table(interpreter).stream_id(identifier, 0, "process.stdin")


def _proc_stdout(interpreter: object, identifier: int) -> int:
    return _proc_table(interpreter).stream_id(identifier, 1, "process.stdout")


def _proc_stderr(interpreter: object, identifier: int) -> int:
    return _proc_table(interpreter).stream_id(identifier, 2, "process.stderr")


def _proc_wait(interpreter: object, identifier: int) -> int:
    return _proc_table(interpreter).wait(identifier)


def _proc_kill(interpreter: object, identifier: int) -> bool:
    return _proc_table(interpreter).kill(identifier)


def _proc_close(interpreter: object, identifier: int) -> None:
    _proc_table(interpreter).close(identifier)


def _proc_read(interpreter: object, identifier: int, count: int) -> str | None:
    return _proc_table(interpreter).read(identifier, count)


def _proc_write(interpreter: object, identifier: int, text: str) -> bool:
    return _proc_table(interpreter).write(identifier, text)


def _proc_poll(interpreter: object, identifiers: LoxList, timeout_ms: int) -> LoxList:
    return _proc_table(interpreter).poll(identifiers, timeout_ms)


def _sleep(milliseconds: int) -> None:
    if milliseconds < 0:
        raise NativeError("time.sleep() expects a non-negative duration.")
    time.sleep(milliseconds / 1000.0)


def _regex_compile(pattern: str, flags: int, mode: int) -> LoxList:
    if flags < 0:
        raise NativeError("regex_engine.compile() expects a non-negative flags mask.")
    if mode not in (regex_runtime.MODE_LINEAR, regex_runtime.MODE_FULL):
        raise NativeError("regex_engine.compile() expects mode 0 (linear) or 1 (full).")
    code, handle = regex_runtime.compile_pattern(pattern, flags, mode)
    values: list[object] = [1, handle] if code == 0 else [0, code]
    return LoxList(values)


def _regex_find(handle: int, subject: str, start: int) -> LoxList | None:
    if start < 0:
        raise NativeError("regex_engine.find() expects a non-negative start.")
    code, spans = regex_runtime.match_pattern(handle, subject, start)
    if code == regex_runtime.NO_MATCH:
        return None
    if code < 0:
        raise NativeError(_regex_error(code))
    values: list[object] = list(spans)
    return LoxList(values)


def _regex_group_names(handle: int) -> LoxList:
    if handle < 1:
        raise NativeError("regex_engine.groupNames() expects a handle from compile.")
    return LoxList(list(regex_runtime.group_names(handle)))


def _regex_free(handle: int) -> None:
    if handle < 1:
        raise NativeError("regex_engine.free() expects a handle from compile.")
    regex_runtime.free_pattern(handle)


def _regex_error(code: int) -> str:
    return regex_runtime.error_message(code)


# Orçamento do kernel por grupo (ADR-0123). O grupo é o prefixo do namespace da
# primitiva (`io.*` → `io`); sem prefixo, é `core`. `process` é o namespace e `proc`
# é o grupo histórico.
_GROUP_ALIASES = {"process": "proc"}

KERNEL_BUDGET = 40

GROUP_BUDGET: dict[str, int] = {
    "core": 5,
    "io": 8,
    "fs": 11,
    "os": 2,
    "proc": 10,
    "time": 2,
    "digest": 2,
}

# Módulos nativos têm orçamento próprio, fora dos 40 do kernel (ADR-0126).
NATIVE_MODULE_BUDGET: dict[str, int] = {"sqlite3": 20, "regex_engine": 4}

# Camada de APIs públicas de módulo (`modulo.funcao`), para quando um wrapper Lox
# expuser uma capacidade que o interpretador não tem (ADR-0128). Vazio na v1: as
# capacidades nativas ainda são primitivas de namespace. Preenchido pelo #83.
API_LAYERS: dict[str, str] = {}


def primitive_group(name: str) -> str:
    """Grupo de orçamento de uma primitiva: namespace, ou `core` sem prefixo."""
    namespace, separator, _ = name.partition(".")
    if not separator:
        return "core"
    return _GROUP_ALIASES.get(namespace, namespace)


@dataclass(frozen=True)
class Primitive:
    lox: str
    c_symbol: str
    params: tuple[Ty, ...]
    result: Ty
    py: Callable[..., object]
    ambient: bool = False
    needs_interpreter: bool = False
    # O símbolo C recebe `(line, column)` no fim, para o panic apontar a chamada.
    site: bool = False
    # Capacidade que só existe no binário (ADR-0128): o interpretador recusa.
    native_only: bool = False

    @property
    def group(self) -> str:
        """Grupo de orçamento (ADR-0123): o namespace da primitiva."""
        return primitive_group(self.lox)

    @property
    def layer(self) -> str:
        """Rótulo derivado dos dois eixos (ADR-0128): motor e determinismo."""
        if self.native_only:
            return "native-only"
        if self.ambient:
            return "ambient"
        return "core"


PRIMITIVES: tuple[Primitive, ...] = (
    Primitive("substr", "lox_substr", (STRING, INT, INT), STRING, _substr, site=True),
    Primitive("join", "lox_join", (ListTy(STRING), STRING), STRING, _join, site=True),
    Primitive("charCodeAt", "lox_char_code_at", (STRING, INT), INT, _char_code_at, site=True),
    Primitive("fromCodePoint", "lox_from_code_point", (INT,), STRING, _from_code_point, site=True),
    Primitive("args", "lox_args", (), ListTy(STRING), _args, ambient=True, needs_interpreter=True),
    Primitive(
        "io.readFile", "lox_io_read_file", (STRING,), union(STRING, NIL), _read_file, ambient=True
    ),
    Primitive("io.readAll", "lox_io_read_all", (), STRING, _read_all, ambient=True),
    Primitive("io.write", "lox_io_write", (STRING,), NIL, _write),
    Primitive("io.writeErr", "lox_io_write_err", (STRING,), NIL, _write_err),
    Primitive(
        "io.writeFile", "lox_io_write_file", (STRING, STRING), BOOL, _write_file, ambient=True
    ),
    Primitive("io.readLine", "lox_io_read_line", (), union(STRING, NIL), _read_line, ambient=True),
    Primitive(
        "io.readUtf8",
        "lox_io_read_utf8",
        (INT,),
        union(STRING, NIL),
        _read_utf8,
        ambient=True,
        site=True,
    ),
    Primitive("io.flush", "lox_io_flush", (), NIL, _flush),
    Primitive("fs.exists", "lox_fs_exists", (STRING,), BOOL, _exists, ambient=True),
    Primitive(
        "fs.listDir",
        "lox_fs_list_dir",
        (STRING,),
        union(ListTy(STRING), NIL),
        _list_dir,
        ambient=True,
    ),
    Primitive(
        "fs.open",
        "lox_fs_open",
        (STRING, STRING),
        INT,
        _fs_open,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "fs.read",
        "lox_fs_read",
        (INT, INT),
        union(STRING, NIL),
        _fs_read,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "fs.readBytes",
        "lox_fs_read_bytes",
        (INT, INT),
        union(BYTES, NIL),
        _fs_read_bytes,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "fs.write",
        "lox_fs_write",
        (INT, STRING),
        NIL,
        _fs_write,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "fs.close",
        "lox_fs_close",
        (INT,),
        NIL,
        _fs_close,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "fs.rename",
        "lox_fs_rename",
        (STRING, STRING),
        NIL,
        _fs_rename,
        ambient=True,
        site=True,
    ),
    Primitive("fs.remove", "lox_fs_remove", (STRING,), NIL, _fs_remove, ambient=True, site=True),
    Primitive("fs.mkdir", "lox_fs_mkdir", (STRING,), NIL, _fs_mkdir, ambient=True, site=True),
    Primitive(
        "fs.stat",
        "lox_fs_stat",
        (STRING,),
        TupleTy((INT, INT, BOOL)),
        _fs_stat,
        ambient=True,
        site=True,
    ),
    Primitive("os.exit", "lox_os_exit", (INT,), NIL, _os_exit, site=True),
    Primitive("os.getenv", "lox_os_getenv", (STRING,), union(STRING, NIL), _getenv, ambient=True),
    Primitive(
        "process.spawn",
        "lox_proc_spawn",
        (ListTy(STRING),),
        INT,
        _proc_spawn,
        ambient=True,
        needs_interpreter=True,
    ),
    Primitive(
        "process.stdin",
        "lox_proc_stdin",
        (INT,),
        INT,
        _proc_stdin,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.stdout",
        "lox_proc_stdout",
        (INT,),
        INT,
        _proc_stdout,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.stderr",
        "lox_proc_stderr",
        (INT,),
        INT,
        _proc_stderr,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.wait",
        "lox_proc_wait",
        (INT,),
        INT,
        _proc_wait,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.kill",
        "lox_proc_kill",
        (INT,),
        BOOL,
        _proc_kill,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.close",
        "lox_proc_close",
        (INT,),
        NIL,
        _proc_close,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.read",
        "lox_proc_read",
        (INT, INT),
        union(STRING, NIL),
        _proc_read,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.write",
        "lox_proc_write",
        (INT, STRING),
        BOOL,
        _proc_write,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive(
        "process.poll",
        "lox_proc_poll",
        (ListTy(INT), INT),
        ListTy(INT),
        _proc_poll,
        ambient=True,
        needs_interpreter=True,
        site=True,
    ),
    Primitive("time.now", "lox_time_now", (), INT, _now, ambient=True),
    Primitive("time.sleep", "lox_time_sleep", (INT,), NIL, _sleep, ambient=True, site=True),
    Primitive("digest.sha256", "lox_digest_sha256", (STRING,), STRING, _sha256),
    Primitive("digest.sha256Bytes", "lox_digest_sha256_bytes", (BYTES,), BYTES, _sha256_bytes),
    Primitive(
        "regex_engine.compile",
        "lox_regex_engine_compile",
        (STRING, INT, INT),
        ListTy(INT),
        _regex_compile,
        site=True,
    ),
    Primitive(
        "regex_engine.find",
        "lox_regex_engine_find",
        (INT, STRING, INT),
        union(ListTy(INT), NIL),
        _regex_find,
        site=True,
    ),
    Primitive(
        "regex_engine.groupNames",
        "lox_regex_engine_group_names",
        (INT,),
        ListTy(STRING),
        _regex_group_names,
        site=True,
    ),
    Primitive(
        "regex_engine.free",
        "lox_regex_engine_free",
        (INT,),
        NIL,
        _regex_free,
        site=True,
    ),
)


def budget_violations(
    primitives: Iterable[Primitive],
    budget: Mapping[str, int],
    total: int | None = None,
) -> list[str]:
    """Grupos ou total acima do orçamento; lista vazia quando tudo cabe.

    Usado pelo teste de orçamento (ADR-0123); é uma função pura para o próprio teste
    conseguir simular estouro sem tocar na tabela real.
    """
    counts = Counter(primitive.group for primitive in primitives)
    problems: list[str] = []
    for group, count in sorted(counts.items()):
        limit = budget.get(group)
        if limit is None:
            problems.append(f"group '{group}' has no budget")
        elif count > limit:
            problems.append(f"group '{group}' has {count}, budget {limit}")
    if total is not None and sum(counts.values()) > total:
        problems.append(f"kernel has {sum(counts.values())} primitives, budget {total}")
    return problems


PRIMITIVE_BY_LOX: dict[str, Primitive] = {primitive.lox: primitive for primitive in PRIMITIVES}


def kernel_primitives() -> tuple[Primitive, ...]:
    """Primitivas do kernel: as de módulo nativo têm orçamento separado (ADR-0126)."""
    return tuple(
        primitive for primitive in PRIMITIVES if primitive.group not in NATIVE_MODULE_BUDGET
    )


# Perfil `--sandbox` (ADR-0112): o programa não lê/escreve arquivos nem cria processos.
# O loader de módulos continua lendo `std/` e arquivos do projeto pelo host; só as
# primitivas ambientais do programa são negadas.
SANDBOX_DENIED_NAMES = frozenset(
    {
        "io.readFile",
        "io.writeFile",
        "fs.exists",
        "fs.listDir",
        "fs.open",
        "fs.read",
        "fs.write",
        "fs.close",
        "fs.readBytes",
        "fs.rename",
        "fs.remove",
        "fs.mkdir",
        "fs.stat",
    }
)
SANDBOX_DENIED_PREFIXES = ("process.",)


def is_sandbox_denied(name: str) -> bool:
    primitive = PRIMITIVE_BY_LOX.get(name)
    if primitive is not None and primitive.native_only:
        return True
    return name in SANDBOX_DENIED_NAMES or name.startswith(SANDBOX_DENIED_PREFIXES)


class PrimitiveCallable:
    """Adaptador do corpo Python para o protocolo `LoxCallable`."""

    def __init__(self, primitive: Primitive, *, sandboxed: bool = False) -> None:
        self.primitive = primitive
        self.sandboxed = sandboxed

    def min_arity(self) -> int:
        return len(self.primitive.params)

    def max_arity(self) -> int:
        return len(self.primitive.params)

    def call(self, interpreter: object, arguments: list[object]) -> object:
        if self.primitive.native_only:
            raise NativeError(
                f"`{self.primitive.lox}` is not supported by the interpreter; "
                "build with `--emit=exe`."
            )
        if self.sandboxed:
            raise NativeError(f"{self.primitive.lox}() is not available in sandbox mode.")
        if self.primitive.needs_interpreter:
            return self.primitive.py(interpreter, *arguments)
        return self.primitive.py(*arguments)

    def __str__(self) -> str:
        return "<native fn>"

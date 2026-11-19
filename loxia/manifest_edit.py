# SPDX-License-Identifier: MIT OR Apache-2.0
"""Edição escopada de `loxia.toml` para `loxia add`/`remove` (ADR-0118).

O editor não reescreve o manifest nem carrega um writer de TOML genérico: localiza a
tabela `[dependencies]`, insere ou remove **uma linha** e re-parseia o resultado antes de
qualquer escrita (o CLI só grava depois). Comentários, ordem, CRLF e a ausência de newline
final são preservados; forma que o editor não entende vira `ManifestEditError` — arquivo
corrompido é impossível por construção.
"""

from __future__ import annotations

import contextlib
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from loxia_core.loader.manifest import Dependency, Manifest, parse_manifest

_DEPENDENCY_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HEADER = re.compile(r"^(\[\[?)\s*([A-Za-z0-9_.-]+)\s*(\]\]?)$")
_KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_ARRAY_OF_TABLES = "[["


class ManifestEditError(Exception):
    """Edição recusada; a mensagem já está pronta para o diagnóstico (`C0004`)."""

    def __init__(self, message: str, *, line: int = 1, column: int = 1) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


@dataclass(frozen=True)
class DependencySpec:
    """O que o usuário pediu no CLI; exatamente uma origem vale."""

    path: str | None = None
    git: str | None = None
    rev: str | None = None


@dataclass(frozen=True)
class EditResult:
    """Texto novo, se mudou algo, e o manifest já validado (nunca grava nada)."""

    text: str
    changed: bool
    manifest: Manifest


@dataclass(frozen=True)
class _Line:
    raw: str
    header: str | None
    array_header: bool
    key: str | None
    value: str | None
    unsafe: bool


@dataclass(frozen=True)
class _Table:
    header_index: int
    end_index: int
    entries: dict[str, int]


def validate_dependency_name(name: str) -> str:
    """Nome lógico é identificador ASCII; `std` é namespace do bundle."""
    if not _DEPENDENCY_NAME.match(name):
        raise ManifestEditError(
            f"Invalid dependency name '{name}'; use an ASCII identifier "
            "(letters, digits and `_`, not starting with a digit)."
        )
    if name == "std":
        raise ManifestEditError("Dependency name 'std' is reserved.")
    return name


def read_manifest_text(path: Path) -> str:
    """Lê preservando o terminador de linha do arquivo (CRLF não vira LF)."""
    with open(path, encoding="utf-8", newline="") as file:
        return file.read()


def write_manifest_text(path: Path, text: str) -> None:
    """Escrita atômica: temporário na mesma pasta, permissões preservadas, `os.replace`."""
    data = text.encode("utf-8")
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        if path.exists():
            shutil.copymode(path, temporary)
        os.replace(temporary, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise


def unified_diff(old: str, new: str, name: str) -> str:
    """Diff determinístico do manifest: caminho relativo, sem timestamp."""
    import difflib

    lines = list(
        difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=name,
            tofile=name,
            lineterm="",
        )
    )
    return "\n".join(lines) + ("\n" if lines else "")


def add_dependency(manifest_path: Path, text: str, name: str, spec: DependencySpec) -> EditResult:
    """Insere a dependência no fim de `[dependencies]` (ou cria a tabela no fim)."""
    validate_dependency_name(name)
    entry = _entry(name, spec)
    lines = _scan(text)
    table = _dependencies_table(lines)
    current = parse_manifest(manifest_path, text)
    if table is not None:
        index = table.entries.get(name)
        if index is not None:
            existing = current.dependencies[name]
            if _same_spec(existing, spec, manifest_path.parent):
                return EditResult(text, False, current)
            raise ManifestEditError(
                f"Dependency '{name}' is already declared with a different spec; "
                f"run 'loxia remove {name}' first.",
                line=index + 1,
            )
        anchor = max(table.entries.values()) if table.entries else table.header_index
        newline = _newline(text)
        pieces = [line.raw for line in lines]
        if not pieces[anchor].endswith("\n"):
            pieces[anchor] += newline
        pieces.insert(anchor + 1, entry + newline)
        new_text = "".join(pieces)
    else:
        new_text = _append_table(text, entry)
    return EditResult(new_text, True, parse_manifest(manifest_path, new_text))


def remove_dependency(manifest_path: Path, text: str, name: str) -> EditResult:
    """Apaga a linha da dependência; a tabela vazia permanece (TOML aceita)."""
    validate_dependency_name(name)
    lines = _scan(text)
    table = _dependencies_table(lines)
    index = None if table is None else table.entries.get(name)
    if index is None:
        raise ManifestEditError(f"Dependency '{name}' is not declared.")
    pieces = [line.raw for line in lines]
    del pieces[index]
    new_text = "".join(pieces)
    return EditResult(new_text, True, parse_manifest(manifest_path, new_text))


def _entry(name: str, spec: DependencySpec) -> str:
    if spec.path is not None:
        assert spec.git is None and spec.rev is None
        return f"{name} = {{ path = {_toml_string(_posix(spec.path))} }}"
    assert spec.git is not None and spec.rev is not None
    return f"{name} = {{ git = {_toml_string(spec.git)}, rev = {_toml_string(spec.rev)} }}"


def _same_spec(dependency: Dependency, spec: DependencySpec, base: Path) -> bool:
    if spec.path is not None:
        if dependency.path is None:
            return False
        return dependency.path == (base / spec.path).resolve()
    return dependency.git == spec.git and dependency.rev == spec.rev


def _posix(path: str) -> str:
    return path.replace(os.sep, "/") if os.sep != "/" else path


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _append_table(text: str, entry: str) -> str:
    newline = _newline(text)
    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += newline
    if prefix and not prefix.endswith(newline * 2):
        prefix += newline
    return f"{prefix}[dependencies]{newline}{entry}{newline}"


def _toml_string(value: str) -> str:
    escaped: list[str] = []
    for char in value:
        if char == "\\":
            escaped.append("\\\\")
        elif char == '"':
            escaped.append('\\"')
        elif char == "\n":
            escaped.append("\\n")
        elif char == "\r":
            escaped.append("\\r")
        elif char == "\t":
            escaped.append("\\t")
        elif ord(char) < 0x20 or ord(char) == 0x7F:
            escaped.append(f"\\u{ord(char):04X}")
        else:
            escaped.append(char)
    return '"' + "".join(escaped) + '"'


def _scan(text: str) -> list[_Line]:
    """Uma entrada por linha, com o que importa para editar e o que impede a edição."""
    lines: list[_Line] = []
    state: str | None = None
    for raw in text.splitlines(keepends=True):
        started_in_multiline = state is not None
        code, state = _split_comment(raw.rstrip("\r\n"), state)
        stripped = code.strip()
        header: str | None = None
        array_header = False
        key: str | None = None
        value: str | None = None
        unsafe = False
        if not started_in_multiline and stripped.startswith("["):
            match = _HEADER.match(stripped)
            if match is not None and (match.group(1), match.group(3)) in {
                ("[", "]"),
                ("[[", "]]"),
            }:
                header = match.group(2)
                array_header = match.group(1) == _ARRAY_OF_TABLES
            else:
                unsafe = True
        elif not started_in_multiline and stripped and not stripped.startswith("#"):
            match = _KEY.match(stripped)
            if match is None:
                unsafe = True
            else:
                key = match.group(1)
                value = match.group(2).strip()
        lines.append(_Line(raw, header, array_header, key, value, unsafe))
    return lines


def _split_comment(body: str, state: str | None) -> tuple[str, str | None]:
    """Corta no `#` de comentário (fora de string) e devolve o estado multiline."""
    index = 0
    length = len(body)
    while index < length:
        if state == '"""':
            if body.startswith('"""', index):
                state = None
                index += 3
            elif body[index] == "\\":
                index += 2
            else:
                index += 1
            continue
        if state == "'''":
            if body.startswith("'''", index):
                state = None
                index += 3
            else:
                index += 1
            continue
        if body.startswith('"""', index):
            state = '"""'
            index += 3
            continue
        if body.startswith("'''", index):
            state = "'''"
            index += 3
            continue
        char = body[index]
        if char == "#":
            return body[:index], state
        if char == '"':
            index += 1
            while index < length and body[index] != '"':
                index += 2 if body[index] == "\\" else 1
            index += 1
            continue
        if char == "'":
            index += 1
            while index < length and body[index] != "'":
                index += 1
            index += 1
            continue
        index += 1
    return body, state


def _dependencies_table(lines: list[_Line]) -> _Table | None:
    matches: list[int] = []
    for index, line in enumerate(lines):
        if line.header == "dependencies":
            if line.array_header:
                raise ManifestEditError(
                    "`[[dependencies]]` is not a dependency table; edit the manifest by hand.",
                    line=index + 1,
                )
            matches.append(index)
        elif line.header is not None and line.header.startswith("dependencies."):
            raise ManifestEditError(
                "`[dependencies.NAME]` sub-tables are not editable; "
                'use an inline table (`name = { path = "…" }`) or edit by hand.',
                line=index + 1,
            )
    if len(matches) > 1:
        raise ManifestEditError(
            "The manifest declares `[dependencies]` more than once; edit it by hand.",
            line=matches[1] + 1,
        )
    if not matches:
        return None
    header_index = matches[0]
    end_index = len(lines)
    for index in range(header_index + 1, len(lines)):
        if lines[index].header is not None:
            end_index = index
            break
    entries: dict[str, int] = {}
    for index in range(header_index + 1, end_index):
        line = lines[index]
        if line.unsafe:
            raise ManifestEditError(
                "This `[dependencies]` line is not an inline table; edit the manifest by hand.",
                line=index + 1,
            )
        if line.key is None:
            continue
        if line.value is None or not _inline_table(line.value):
            raise ManifestEditError(
                f"Dependency '{line.key}' is not a single-line inline table; "
                "edit the manifest by hand.",
                line=index + 1,
            )
        if line.key in entries:
            raise ManifestEditError(
                f"Dependency '{line.key}' is declared more than once; edit the manifest by hand.",
                line=index + 1,
            )
        entries[line.key] = index
    return _Table(header_index, end_index, entries)


def _inline_table(value: str) -> bool:
    return value.startswith("{") and value.endswith("}") and len(value) >= 2

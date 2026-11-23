# SPDX-License-Identifier: MIT OR Apache-2.0
"""Doc IR do formatter: grupos, quebras e largura (ADR-0136).

O layout é montado como uma árvore de documentos. `render` decide, grupo a grupo,
entre a forma plana e a quebrada usando a largura disponível. A decisão depende só do
documento e da largura — nunca do texto de origem —, o que sustenta a idempotência:
formatar duas vezes não muda a árvore, então não muda a decisão.

O IR é fechado (`Doc` + subclasses) e o renderer é um laço com pilha explícita: árvores
profundas (expressões longas) não estouram a recursão do Python.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum, auto
from typing import cast

INDENT = 2


class Doc:
    """Nó base do IR; instancie as subclasses abaixo, não `Doc` diretamente."""


@dataclass(frozen=True)
class Text(Doc):
    value: str


@dataclass(frozen=True)
class Concat(Doc):
    parts: tuple[Doc, ...]


@dataclass(frozen=True)
class Line(Doc):
    """Na forma plana vira um espaço; na quebrada, uma nova linha."""


@dataclass(frozen=True)
class SoftLine(Doc):
    """Na forma plana não ocupa nada; na quebrada, uma nova linha."""


@dataclass(frozen=True)
class HardLine(Doc):
    """Quebra sempre e força o grupo que a contém a quebrar."""


@dataclass(frozen=True)
class BlankLine(Doc):
    """Uma linha em branco de verdade; não carrega indentação."""


@dataclass(frozen=True)
class EnsureLine(Doc):
    """Quebra só se a linha atual já tiver conteúdo (evita linha em branco espúria)."""


@dataclass(frozen=True)
class Indent(Doc):
    doc: Doc


@dataclass(frozen=True)
class Group(Doc):
    doc: Doc


@dataclass(frozen=True)
class IfBreak(Doc):
    broken: Doc
    flat: Doc


@dataclass(frozen=True)
class TrailingComment(Doc):
    """Comentário na mesma linha do código anterior.

    `render` registra a coluna em que ele começa, para o alinhamento de comentários
    consecutivos; `value` já inclui o marcador (`# ...`).
    """

    value: str


@dataclass(frozen=True)
class Rendered:
    """Resultado do render: linhas prontas e a coluna de cada trailing comment."""

    lines: tuple[str, ...]
    trailing: tuple[int | None, ...]


def text(value: str) -> Doc:
    return Text(value) if value else Concat(())


def concat(*parts: Doc) -> Doc:
    """Concatena achatando `Concat` e descartando `Text` vazio."""
    items: list[Doc] = []
    for part in parts:
        if isinstance(part, Concat):
            items.extend(part.parts)
        elif isinstance(part, Text) and not part.value:
            continue
        else:
            items.append(part)
    if not items:
        return Concat(())
    if len(items) == 1:
        return items[0]
    return Concat(tuple(items))


def join(separator: Doc, parts: Iterable[Doc]) -> Doc:
    items: list[Doc] = []
    for index, part in enumerate(parts):
        if index:
            items.append(separator)
        items.append(part)
    return concat(*items)


def line() -> Doc:
    return Line()


def softline() -> Doc:
    return SoftLine()


def hardline() -> Doc:
    return HardLine()


def blankline() -> Doc:
    return BlankLine()


def ensure_line() -> Doc:
    return EnsureLine()


def indent(doc: Doc) -> Doc:
    return Indent(doc)


def group(doc: Doc) -> Doc:
    return Group(doc)


def if_break(broken: Doc, flat: Doc) -> Doc:
    return IfBreak(broken, flat)


class _Mode(Enum):
    FLAT = auto()
    BREAK = auto()


class _Renderer:
    def __init__(self, width: int) -> None:
        self.width = width
        self.lines: list[str] = []
        self.trailing: list[int | None] = []
        self.current: list[str] = []
        self.col = 0
        self.comment_col: int | None = None

    def run(self, doc: Doc) -> Rendered:
        stack: list[tuple[int, _Mode, Doc]] = [(0, _Mode.BREAK, doc)]
        while stack:
            doc_indent, mode, node = stack.pop()
            if isinstance(node, Text):
                self._text(node.value)
            elif isinstance(node, Concat):
                stack.extend((doc_indent, mode, part) for part in reversed(node.parts))
            elif isinstance(node, Line):
                if mode is _Mode.FLAT:
                    self._text(" ")
                else:
                    self._newline(doc_indent)
            elif isinstance(node, SoftLine):
                if mode is _Mode.BREAK:
                    self._newline(doc_indent)
            elif isinstance(node, HardLine):
                self._newline(doc_indent)
            elif isinstance(node, BlankLine):
                self._blank(doc_indent)
            elif isinstance(node, EnsureLine):
                if self._has_content():
                    self._newline(doc_indent)
            elif isinstance(node, Indent):
                stack.append((doc_indent + INDENT, mode, node.doc))
            elif isinstance(node, Group):
                if mode is _Mode.FLAT:
                    stack.append((doc_indent, _Mode.FLAT, node.doc))
                else:
                    flat = self._fits((doc_indent, _Mode.FLAT, node.doc), stack)
                    stack.append((doc_indent, _Mode.FLAT if flat else _Mode.BREAK, node.doc))
            elif isinstance(node, IfBreak):
                stack.append((doc_indent, mode, node.broken if mode is _Mode.BREAK else node.flat))
            elif isinstance(node, TrailingComment):
                # Um comentário trailing sempre tem exatamente um espaço antes; espaço
                # pendente do layout (ex.: depois de um operador) é absorvido.
                code = "".join(self.current).rstrip(" ")
                self.current = [code]
                self.col = len(code)
                self.comment_col = self.col
                self._text(" " + node.value)
            else:  # pragma: no cover - hierarquia fechada
                raise TypeError(f"unknown Doc node: {type(node)!r}")
        self._finish()
        return Rendered(tuple(self.lines), tuple(self.trailing))

    def _text(self, value: str) -> None:
        if not value:
            return
        if "\n" not in value:
            self.current.append(value)
            self.col += len(value)
            return
        # Texto multilinha (string multilinha/comentário de bloco) é verbatim: as linhas
        # seguintes não recebem indentação sintética.
        for index, segment in enumerate(value.split("\n")):
            if index:
                self._newline(verbatim=True)
            self.current.append(segment)
            self.col += len(segment)

    def _has_content(self) -> bool:
        return bool("".join(self.current).strip())

    def _newline(self, indent: int = 0, *, verbatim: bool = False) -> None:
        value = "".join(self.current)
        # Linha só com indentação não vira linha em branco com espaços; texto verbatim
        # (string multilinha/comentário de bloco) preserva espaços significativos.
        if verbatim or value.strip():
            self.lines.append(value)
            self.trailing.append(self.comment_col)
        self.comment_col = None
        if verbatim:
            self.current = []
            self.col = 0
        else:
            self.current = [" " * indent] if indent else []
            self.col = indent

    def _blank(self, indent: int) -> None:
        if self._has_content():
            self._newline(indent)
        self.lines.append("")
        self.trailing.append(None)
        self.current = [" " * indent] if indent else []
        self.col = indent

    def _finish(self) -> None:
        if not self.current:
            return
        value = "".join(self.current)
        if not value.strip():
            return
        self.lines.append(value)
        self.trailing.append(self.comment_col)

    def _fits(self, start: tuple[int, _Mode, Doc], rest: list[tuple[int, _Mode, Doc]]) -> bool:
        """Simula a forma plana do grupo; para na primeira quebra ou no estouro."""
        remaining = self.width - self.col
        stack: list[tuple[int, _Mode, Doc]] = [start]
        rest_index = len(rest) - 1
        while True:
            if not stack:
                if rest_index < 0:
                    return True
                stack.append(rest[rest_index])
                rest_index -= 1
                continue
            doc_indent, mode, node = stack.pop()
            if isinstance(node, Text):
                if "\n" in node.value:
                    if mode is _Mode.BREAK:
                        first = node.value.split("\n", 1)[0]
                        return len(first) <= remaining
                    return False
                remaining -= len(node.value)
                if remaining < 0:
                    return False
            elif isinstance(node, Concat):
                stack.extend((doc_indent, mode, part) for part in reversed(node.parts))
            elif isinstance(node, Line):
                if mode is _Mode.FLAT:
                    remaining -= 1
                    if remaining < 0:
                        return False
                else:
                    return True
            elif isinstance(node, SoftLine):
                if mode is _Mode.BREAK:
                    return True
            elif isinstance(node, HardLine):
                # Na forma plana um hardline é impossível: o grupo precisa quebrar.
                return mode is _Mode.BREAK
            elif isinstance(node, (BlankLine, EnsureLine)):
                return mode is _Mode.BREAK
            elif isinstance(node, Indent):
                stack.append((doc_indent + INDENT, mode, node.doc))
            elif isinstance(node, Group):
                stack.append((doc_indent, _Mode.FLAT, node.doc))
            elif isinstance(node, IfBreak):
                stack.append((doc_indent, mode, node.flat))
            elif isinstance(node, TrailingComment):
                remaining -= 1 + len(node.value)
                if remaining < 0:
                    return False
            else:  # pragma: no cover - hierarquia fechada
                raise TypeError(f"unknown Doc node: {type(node)!r}")
        return True


def render(doc: Doc, width: int = 100) -> Rendered:
    """Renderiza `doc` em no máximo `width` colunas (code points)."""
    if width < 1:
        raise ValueError("width must be >= 1")
    return _Renderer(width).run(doc)


def align(rendered: Rendered, width: int) -> tuple[str, ...]:
    """Alinha trailing comments consecutivos no mesmo indent (regra estrita)."""
    lines = list(rendered.lines)
    columns = list(rendered.trailing)
    index = 0
    while index < len(lines):
        column = columns[index]
        if column is None or not _line_comment_at(lines[index], column):
            index += 1
            continue
        indent = len(lines[index]) - len(lines[index].lstrip(" "))
        group = [index]
        cursor = index + 1
        while cursor < len(lines):
            next_column = columns[cursor]
            if next_column is None or not _line_comment_at(lines[cursor], next_column):
                break
            next_indent = len(lines[cursor]) - len(lines[cursor].lstrip(" "))
            if next_indent != indent:
                break
            group.append(cursor)
            cursor += 1
        if len(group) > 1:
            target = max(cast(int, columns[item]) for item in group) + 2
            aligned: list[str] = []
            for item in group:
                column = cast(int, columns[item])
                code = lines[item][:column].rstrip()
                comment = lines[item][column:].strip()
                aligned.append(code + " " * (target - column) + comment)
            if all(len(item) <= width for item in aligned):
                for item, value in zip(group, aligned, strict=False):
                    lines[item] = value
        index = cursor
    return tuple(lines)


def _line_comment_at(line: str, column: int) -> bool:
    if not line[:column].strip():
        return False
    return line[column:].lstrip(" ").startswith("#")

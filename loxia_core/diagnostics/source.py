"""Fonte carregada + aritmética de coluna para o caret (ADR-0075).

Nada aqui imprime: são funções puras para que o renderizador seja testável sem
capturar stderr.
"""

from __future__ import annotations

import os
import unicodedata
from pathlib import Path

TAB_WIDTH = 4


def display_path(path: str | Path, *, cwd: str | Path | None = None) -> str:
    """Caminho determinístico para exibição: relativo ao CWD, nunca absoluto.

    Se o arquivo estiver fora do CWD (caso comum de `tmp_path` nos testes), usa só o
    basename. O resultado depende da invocação (CWD + argumento), que é determinística;
    o caminho absoluto nunca vaza (I3).
    """
    base = os.path.abspath(os.fspath(cwd) if cwd is not None else os.getcwd())
    absolute = os.path.abspath(os.fspath(path))

    try:
        relative = os.path.relpath(absolute, base)
    except ValueError:  # drives diferentes no Windows
        return os.path.basename(absolute)

    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return os.path.basename(absolute)

    return Path(relative).as_posix()


def char_width(char: str) -> int:
    """Largura de exibição de um code point (combining = 0, CJK largo = 2)."""
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    return 1


def display_text(text: str, start_width: int = 0) -> tuple[str, int]:
    """Expande tabs (múltiplo de `TAB_WIDTH`) e devolve `(texto, largura)`."""
    pieces: list[str] = []
    width = start_width

    for char in text:
        if char == "\t":
            spaces = TAB_WIDTH - (width % TAB_WIDTH)
            pieces.append(" " * spaces)
            width += spaces
        else:
            pieces.append(char)
            width += char_width(char)

    return "".join(pieces), width


def display_width(text: str) -> int:
    return display_text(text)[1]


class SourceFile:
    """Uma fonte com as linhas pré-computadas para o renderizador."""

    def __init__(self, path: str, text: str) -> None:
        self.path = path
        self.text = text
        self._lines = text.splitlines()

    @property
    def lines(self) -> list[str]:
        return self._lines

    def line(self, number: int) -> str | None:
        if 1 <= number <= len(self._lines):
            return self._lines[number - 1]
        return None


class SourceMap:
    """Arquivos disponíveis para renderização, por caminho de exibição."""

    def __init__(self) -> None:
        self._files: dict[str, SourceFile] = {}

    def add(self, path: str, text: str) -> SourceFile:
        source = SourceFile(path, text)
        self._files[path] = source
        return source

    def get(self, path: str) -> SourceFile | None:
        return self._files.get(path)

    def clear(self) -> None:
        self._files.clear()

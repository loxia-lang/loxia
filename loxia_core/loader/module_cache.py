# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cache de parse de módulos endereçado por conteúdo (ADR-0143).

O `ModuleLoader` parseia cada módulo do closure de imports a cada análise. No editor a
maioria dos imports não muda entre duas teclas, e a stdlib não muda durante a sessão;
guardar o produto do parse (statements, imports e declarações) evita reparsear o mesmo
texto. A chave é o **conteúdo**, não o mtime: restaurar o mtime (`rsync -t`, `cp -p`) não
serve texto velho, e um buffer não salvo entra pelo próprio texto.

Só parse bem-sucedido entra no cache (a validação do loader levanta `ModuleError` antes
de o produto existir), então um hit nunca precisa reemitir diagnóstico. O cache é
opt-in do tooling: `Loxia.check(module_cache=...)`; `run`, `build` e o REPL não usam.
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from loxia_core.frontend.stmt import Import, Stmt

DEFAULT_MAX_ENTRIES = 256
DEFAULT_MAX_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class ParsedModule:
    """Produto do parse de um módulo, antes da reescrita de imports do loader."""

    statements: list[Stmt]
    imports: list[Import]
    declarations: dict[str, Stmt]


def _digest(source: str) -> bytes:
    return hashlib.blake2b(source.encode("utf-8"), digest_size=16).digest()


class ModuleCache:
    """LRU limitado por número de módulos e por bytes de fonte."""

    def __init__(
        self,
        *,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._entries: OrderedDict[tuple[Path, bytes], tuple[int, ParsedModule]] = OrderedDict()
        self._bytes = 0

    def get(self, path: Path, source: str) -> ParsedModule | None:
        key = (path, _digest(source))
        entry = self._entries.get(key)
        if entry is None:
            return None
        self._entries.move_to_end(key)
        return entry[1]

    def put(self, path: Path, source: str, parsed: ParsedModule) -> None:
        key = (path, _digest(source))
        size = len(source.encode("utf-8"))
        if size > self.max_bytes:
            return
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._bytes -= previous[0]
        self._entries[key] = (size, parsed)
        self._bytes += size
        while self._entries and (
            len(self._entries) > self.max_entries or self._bytes > self.max_bytes
        ):
            _, (removed, _) = self._entries.popitem(last=False)
            self._bytes -= removed

    def clear(self) -> None:
        self._entries.clear()
        self._bytes = 0

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def byte_count(self) -> int:
        """Bytes de fonte guardados (proxy da memória; o AST ocupa mais)."""
        return self._bytes

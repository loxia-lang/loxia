# SPDX-License-Identifier: MIT OR Apache-2.0
"""Rename cross-file semântico de declarações top-level de módulos.

O `ModuleLoader` reescreve nomes públicos para ``mod$nome`` preservando a posição
original do token. A partir dessa AST resolvida, este módulo coleta só os usos que
pertencem à declaração alvo, mesmo que outro arquivo tenha um local com o mesmo nome.
Imports, aliases e anotações de tipo são editados no texto original.

A análise do workspace guarda o caminho **real** de cada módulo (`lox.module_files`),
inclusive os que vivem fora do root (`std`, `[modules].paths`, dependências): sem ele
o token do módulo era atribuído a um arquivo inexistente dentro do root e a coleta de
referências estourava. Referências atravessam o root; o rename só edita arquivos
dentro dele — `std` e checkouts de dependência não são reescritos.

O cache tem duas camadas: o workspace inteiro (fingerprint dos textos e dos insumos de
resolução) e, por arquivo, a análise e a contribuição de tokens. A contribuição de um
módulo importado é compartilhada entre todos os importadores: guardá-la por arquivo
duplicaria o closure inteiro em cada entrada e o cache cresceria com
`arquivos * closure` em vez de `tokens`.
"""

from __future__ import annotations

import hashlib
import re
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

from loxia.engine import Loxia
from loxia.source_symbols import imports_of, parse_source
from loxia_core.diagnostics.source import display_path
from loxia_core.frontend.destructuring import pattern_names
from loxia_core.frontend.stmt import (
    Block,
    Class,
    Destructure,
    EnumDecl,
    ForIn,
    Function,
    If,
    Import,
    Interface,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import ClassTy
from loxia_core.loader.module_cache import ModuleCache

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

DEFAULT_MAX_FILES = 2048
DEFAULT_MAX_MODULES = 512
DEFAULT_MAX_MODULE_TOKENS = 200_000

# Leitor de texto para arquivos que não estão no `files` do chamador (módulos fora
# do root, manifest, lock). O LSP passa o cache de stat do disco; o resto lê o arquivo.
TextLoader = Callable[[Path], "str | None"]

# Contribuição de um módulo importado: (arquivo real, nome lógico) do módulo.
ModuleKey = tuple[Path, str]


def _digest(text: str) -> bytes:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def within_root(root: Path, path: Path) -> bool:
    """`True` quando o arquivo está sob o root do workspace (resolve symlinks)."""
    return path.resolve().is_relative_to(root.resolve())


@dataclass(frozen=True)
class Target:
    old_name: str
    declaration_file: Path
    declaration_offset: int
    mangled: frozenset[str]
    direct_names: dict[Path, frozenset[str]]
    aliases: dict[Path, frozenset[str]]


@dataclass(frozen=True)
class References:
    """Declaração alvo e todas as ocorrências que um rename editaria."""

    declaration: tuple[Path, int]
    occurrences: tuple[tuple[Path, int, str], ...]


@dataclass
class _Analysis:
    """Insumos leves de um arquivo, sem a AST mesclada (cópia do closure).

    Guardar `merged`/`index` no cache custaria uma cópia do closure por arquivo;
    depois da contribuição extraída eles não são mais usados.
    """

    path: Path
    text: str
    original: list[Stmt]
    # display path do token → arquivo real (módulos resolvidos pelo loader).
    module_map: dict[str, Path]
    # Insumos da análise: módulos do closure, manifest e lock.
    input_paths: tuple[Path, ...]


@dataclass(frozen=True)
class _Contribution:
    """Tokens de um arquivo prontos para mesclar no workspace."""

    tokens: tuple[tuple[Path, int, str], ...]
    declarations: dict[str, tuple[Path, Token]]


@dataclass(frozen=True)
class _Parsed:
    analysis: _Analysis
    own: _Contribution
    modules: tuple[tuple[ModuleKey, _Contribution], ...]


@dataclass(frozen=True)
class _Skip:
    """Arquivo fora da análise: sintaxe quebrada (memoizável) ou erro de módulo."""

    path: Path
    module_error: bool


@dataclass
class _ModuleEntry:
    contribution: _Contribution
    tokens: int


@dataclass
class _Entry:
    """Análise de um arquivo válida enquanto o texto e os insumos não mudarem."""

    text_digest: bytes
    closure: tuple[tuple[Path, bytes], ...]
    analysis: _Analysis
    own: _Contribution
    modules: tuple[ModuleKey, ...]
    size: int


@dataclass
class _Workspace:
    root: Path
    files: dict[Path, str]
    analyses: dict[Path, _Analysis]
    positions: dict[tuple[Path, int], set[str]]
    tokens_by_lexeme: dict[str, set[tuple[Path, int]]]
    declarations: dict[str, tuple[Path, Token]]
    # Insumos de resolução fora de `files` (manifest, lock, módulos externos),
    # com o digest do texto: editar um deles invalida o workspace.
    closure: tuple[tuple[Path, bytes], ...]
    # `False` quando algum arquivo foi pulado por erro de módulo: a causa pode estar
    # fora de `files`, então o workspace não pode ser memoizado.
    complete: bool


@dataclass
class WorkspaceCache:
    """Reusa a análise do workspace enquanto os textos e os insumos não mudarem.

    Três camadas, todas válidas por conteúdo (nunca por mtime — restaurar o mtime
    não pode servir texto velho):

    - workspace: fingerprint dos textos + digest dos insumos fora de `files`;
    - arquivo: análise própria e contribuição do arquivo como entry;
    - módulo: contribuição do arquivo *como módulo importado*, compartilhada entre
      todos os importadores (prefixos `mod$nome` são iguais em qualquer contexto).

    O `clear` descarta o workspace e mantém as camadas por conteúdo: editar um
    arquivo no LSP refaz só a análise dele. Os orçamentos são documentados em
    `docs/adr/0151-cache-de-analise-por-arquivo-no-lsp.md`.
    """

    max_files: int = DEFAULT_MAX_FILES
    max_modules: int = DEFAULT_MAX_MODULES
    max_module_tokens: int = DEFAULT_MAX_MODULE_TOKENS
    _fingerprint: tuple[str, tuple[tuple[str, bytes], ...]] | None = None
    _workspace: _Workspace | None = None
    _entries: OrderedDict[Path, _Entry] = field(default_factory=OrderedDict)
    _modules: OrderedDict[ModuleKey, _ModuleEntry] = field(default_factory=OrderedDict)
    _module_tokens: int = 0

    def get(
        self,
        root: Path,
        files: dict[Path, str],
        module_cache: ModuleCache | None = None,
        load_text: TextLoader | None = None,
    ) -> _Workspace:
        loader = load_text or _read_text
        fingerprint = (
            str(root),
            tuple((str(path), _digest(text)) for path, text in sorted(files.items())),
        )
        workspace = self._workspace
        if (
            workspace is not None
            and self._fingerprint == fingerprint
            and _closure_unchanged(workspace.closure, files, loader)
        ):
            return workspace
        if len(files) > self.max_files:
            # Workspace grande demais para reter análise por arquivo: a memoização
            # do workspace continua (uma entrada), mas o rebuild depois de editar
            # paga a análise inteira. Degradação declarada, não thrash de LRU.
            # Não retém este workspace, mas também não descarta o anterior: a última
            # workspace que cabia no orçamento já teve os tetos aplicados por
            # `_retain`, e jogar as camadas por conteúdo fora faria um vaivém
            # pequeno→grande→pequeno reanalisar arquivos inalterados.
            built = _build_workspace(root, files, module_cache, load_text=loader)
        else:
            built = _build_workspace(
                root,
                files,
                module_cache,
                cache=self,
                load_text=loader,
            )
            if built.complete:
                self._retain({path.resolve() for path in files})
        if not built.complete:
            # Erro de módulo pode vir de insumo fora de `files`: não memoriza, senão
            # consertar a dependência não apareceria na próxima request.
            self._fingerprint = None
            self._workspace = None
            return built
        self._fingerprint = fingerprint
        self._workspace = built
        return built

    def clear(self) -> None:
        """Invalida o workspace preservando as camadas por conteúdo."""
        self._fingerprint = None
        self._workspace = None

    def _remember(self, parsed: _Parsed, texts: dict[Path, str]) -> None:
        analysis = parsed.analysis
        closure = tuple(
            (path, _digest(texts[path])) for path in analysis.input_paths if path in texts
        )
        self._entries[analysis.path.resolve()] = _Entry(
            _digest(analysis.text),
            closure,
            analysis,
            parsed.own,
            tuple(module_key for module_key, _ in parsed.modules),
            len(analysis.text.encode("utf-8")),
        )
        for module_key, contribution in parsed.modules:
            self._remember_module(module_key, contribution)

    def _remember_module(self, key: ModuleKey, contribution: _Contribution) -> None:
        previous = self._modules.pop(key, None)
        if previous is not None:
            self._module_tokens -= previous.tokens
        tokens = len(contribution.tokens)
        self._modules[key] = _ModuleEntry(contribution, tokens)
        self._module_tokens += tokens

    def _retain(self, paths: set[Path]) -> None:
        """Descarta o que não pertence ao workspace atual; acima do teto, não retém."""
        for entry_path in [path for path in self._entries if path not in paths]:
            del self._entries[entry_path]
        live = {module for entry in self._entries.values() for module in entry.modules}
        for module_key in [key for key in self._modules if key not in live]:
            removed = self._modules.pop(module_key)
            self._module_tokens -= removed.tokens
        if (
            len(self._entries) > self.max_files
            or len(self._modules) > self.max_modules
            or self._module_tokens > self.max_module_tokens
        ):
            # Um workspace só: se ele não cabe no orçamento, reter metade dele faria
            # cada rebuild reanalisar o resto. Melhor não reter e dizer o custo.
            self._entries.clear()
            self._modules.clear()
            self._module_tokens = 0

    def _cached(
        self,
        path: Path,
        text: str,
        loader: TextLoader,
        texts: dict[Path, str],
    ) -> _Entry | None:
        entry = self._entries.get(path.resolve())
        if entry is None or entry.text_digest != _digest(text):
            return None
        for input_path, digest in entry.closure:
            input_text = texts.get(input_path)
            if input_text is None:
                input_text = loader(input_path)
                if input_text is None:
                    return None
                texts[input_path] = input_text
            if _digest(input_text) != digest:
                return None
        for module_key in entry.modules:
            module = self._modules.get(module_key)
            if module is None:
                # A contribuição do módulo foi despejada: refazer a análise é mais
                # barato e correto do que mesclar um workspace incompleto.
                return None
            self._modules.move_to_end(module_key)
        self._entries.move_to_end(path.resolve())
        return entry


def _closure_unchanged(
    closure: tuple[tuple[Path, bytes], ...],
    files: dict[Path, str],
    loader: TextLoader,
) -> bool:
    for path, digest in closure:
        text = files.get(path)
        if text is None:
            text = files.get(path.resolve())
        if text is None:
            text = loader(path)
            if text is None:
                return False
        if _digest(text) != digest:
            return False
    return True


def semantic_target(
    root: Path,
    files: dict[Path, str],
    target_path: Path,
    token: Token,
    *,
    cache: WorkspaceCache | None = None,
    module_cache: ModuleCache | None = None,
    load_text: TextLoader | None = None,
) -> Target | None:
    workspace = _workspace(root, files, cache, module_cache, load_text)
    return _target(workspace, target_path, token)


def semantic_rename(
    root: Path,
    files: dict[Path, str],
    target_path: Path,
    token: Token,
    new_name: str,
    *,
    cache: WorkspaceCache | None = None,
    module_cache: ModuleCache | None = None,
    load_text: TextLoader | None = None,
) -> dict[str, object] | str | None:
    workspace = _workspace(root, files, cache, module_cache, load_text)
    target = _target(workspace, target_path, token)
    if target is None:
        return None
    if new_name == target.old_name:
        return {"changes": {}}
    return _edits(workspace, target, new_name)


def semantic_references(
    root: Path,
    files: dict[Path, str],
    target_path: Path,
    token: Token,
    *,
    cache: WorkspaceCache | None = None,
    module_cache: ModuleCache | None = None,
    load_text: TextLoader | None = None,
) -> References | None:
    """Ocorrências semânticas do alvo, na mesma resolução do rename cross-file."""
    workspace = _workspace(root, files, cache, module_cache, load_text)
    target = _target(workspace, target_path, token)
    if target is None:
        return None
    offsets = _occurrence_offsets(workspace, target)
    occurrences: list[tuple[Path, int, str]] = []
    for path, path_offsets in offsets.items():
        text = workspace.files.get(path)
        if text is None:
            continue
        for offset in path_offsets:
            identifier = _identifier_at(text, offset)
            if identifier is not None:
                occurrences.append((path, offset, identifier))
    occurrences.sort(key=lambda item: (str(item[0]), item[1]))
    return References(
        declaration=(target.declaration_file, target.declaration_offset),
        occurrences=tuple(occurrences),
    )


def _workspace(
    root: Path,
    files: dict[Path, str],
    cache: WorkspaceCache | None = None,
    module_cache: ModuleCache | None = None,
    load_text: TextLoader | None = None,
) -> _Workspace:
    if cache is not None:
        return cache.get(root, files, module_cache, load_text)
    return _build_workspace(root, files, module_cache, load_text=load_text)


def _build_workspace(
    root: Path,
    files: dict[Path, str],
    module_cache: ModuleCache | None = None,
    *,
    cache: WorkspaceCache | None = None,
    load_text: TextLoader | None = None,
) -> _Workspace:
    loader = load_text or _read_text
    # Tokens de módulo são atribuídos ao caminho real; `files` guarda o texto tanto
    # pelo caminho do chamador quanto pelo resolvido (a busca por offset usa o real).
    texts: dict[Path, str] = {}
    for path, text in files.items():
        texts[path] = text
        texts[path.resolve()] = text
    analyses: dict[Path, _Analysis] = {}
    module_error = False
    positions: dict[tuple[Path, int], set[str]] = {}
    tokens_by_lexeme: dict[str, set[tuple[Path, int]]] = {}
    declarations: dict[str, tuple[Path, Token]] = {}
    # O texto do workspace pode vir de buffers não salvos: o loader precisa ver o
    # mesmo texto que o `files` para os offsets do módulo importado baterem.
    overrides = {path.resolve(): text for path, text in files.items()}

    lox: Loxia | None = None

    def file_text(path: Path) -> str | None:
        text = texts.get(path)
        if text is not None:
            return text
        loaded = loader(path)
        if loaded is not None:
            texts[path] = loaded
        return loaded

    # A contribuição de um módulo é a mesma para todo importador: mesclar uma vez
    # evita repetir os tokens do closure `arquivos` vezes no workspace.
    applied: set[ModuleKey] = set()

    def merge_module(key: ModuleKey, contribution: _Contribution) -> None:
        if key in applied:
            return
        applied.add(key)
        _merge(positions, tokens_by_lexeme, declarations, contribution)

    for path in sorted(files):
        text = files[path]
        entry = cache._cached(path, text, loader, texts) if cache is not None else None
        if entry is not None:
            analysis = entry.analysis
            _merge(positions, tokens_by_lexeme, declarations, entry.own)
            if cache is not None:
                for module_key in entry.modules:
                    module = cache._modules.get(module_key)
                    if module is not None:
                        merge_module(module_key, module.contribution)
        else:
            if lox is None:
                lox = Loxia(error_format="json", color="never", max_errors=0)
            parsed = _analyze_file(root, path, text, overrides, module_cache, lox=lox)
            if isinstance(parsed, _Skip):
                # Um arquivo que não parseia não pode derrubar o workspace: o que
                # der para analisar é analisado e os usos nele ficam de fora (#250).
                module_error = module_error or parsed.module_error
                continue
            # O texto do closure externo entra no workspace antes dos offsets: os
            # tokens do módulo apontam para o caminho real, não para o root.
            for input_path in parsed.analysis.input_paths:
                file_text(input_path)
            if cache is not None:
                cache._remember(parsed, texts)
            analysis = parsed.analysis
            # Mesclar tokens prontos é muito mais barato que refletir sobre a AST
            # mesclada de novo — era esse o custo pago a cada tecla no LSP.
            _merge(positions, tokens_by_lexeme, declarations, parsed.own)
            for module_key, contribution in parsed.modules:
                merge_module(module_key, contribution)
        analyses[path] = analysis
    closure = _external_closure(analyses, files, texts)
    return _Workspace(
        root,
        texts,
        analyses,
        positions,
        tokens_by_lexeme,
        declarations,
        closure,
        not module_error,
    )


def _external_closure(
    analyses: dict[Path, _Analysis],
    files: dict[Path, str],
    texts: dict[Path, str],
) -> tuple[tuple[Path, bytes], ...]:
    roots = {path.resolve() for path in files}
    external = {
        path
        for analysis in analyses.values()
        for path in analysis.input_paths
        if path not in roots and path in texts
    }
    return tuple(sorted((path, _digest(texts[path])) for path in external))


def _merge(
    positions: dict[tuple[Path, int], set[str]],
    tokens_by_lexeme: dict[str, set[tuple[Path, int]]],
    declarations: dict[str, tuple[Path, Token]],
    contribution: _Contribution,
) -> None:
    for path, offset, lexeme in contribution.tokens:
        key = (path, offset)
        positions.setdefault(key, set()).add(lexeme)
        tokens_by_lexeme.setdefault(lexeme, set()).add(key)
    for name, declaration in contribution.declarations.items():
        declarations.setdefault(name, declaration)


def _analyze_file(
    root: Path,
    path: Path,
    text: str,
    overrides: dict[Path, str],
    module_cache: ModuleCache | None,
    *,
    lox: Loxia | None = None,
) -> _Parsed | _Skip:
    original = parse_source(text)
    if original is None:
        # Sintaxe quebrada: o texto está em `files`, então corrigir muda o
        # fingerprint e o workspace pode ser memoizado.
        return _Skip(path, module_error=False)
    if lox is None:
        lox = Loxia(error_format="json", color="never", max_errors=0)
    lox.use_file(display_path(str(path)), module_root=root)
    # Loader-only: o resolver/checker sobre o closure não muda offsets e dominava o
    # custo frio do workspace; rename/references não precisam de tipos (#249).
    merged = lox.load_modules(text, module_overrides=overrides, module_cache=module_cache)
    if merged is None:
        # Erro de módulo: a causa pode ser um insumo fora de `files` (dependência que
        # ainda não existe), então o workspace não pode ser memorizado.
        return _Skip(path, module_error=True)
    module_map = {display_path(str(path)): path.resolve()}
    module_map.update({name: real.resolve() for name, real in lox.module_files.items()})
    analysis = _Analysis(
        path,
        text,
        original,
        module_map,
        tuple(sorted(lox.watched_files)),
    )
    return _partition(root, analysis, merged)


def _partition(root: Path, analysis: _Analysis, merged: list[Stmt]) -> _Parsed:
    """Separa o que é do próprio arquivo do que é de cada módulo importado.

    A AST mesclada repete os tokens do closure em todo arquivo que o importa. A
    contribuição do módulo depende só do módulo (o prefixo `mod$` vem do nome
    lógico), então é a mesma em qualquer importador e pode ser compartilhada.
    """
    entry_display = display_path(str(analysis.path))
    entry_path = analysis.path.resolve()
    own_tokens: list[tuple[Path, int, str]] = []
    own_declarations: dict[str, tuple[Path, Token]] = {}
    module_tokens: dict[ModuleKey, list[tuple[Path, int, str]]] = {}
    module_declarations: dict[ModuleKey, dict[str, tuple[Path, Token]]] = {}

    def bucket(display: str, token: Token) -> tuple[ModuleKey | None, Path]:
        if not display or display == entry_display:
            return None, entry_path
        mapped = analysis.module_map.get(display)
        if mapped is not None:
            # `module_map` já guarda caminhos resolvidos: resolver de novo por token
            # era o custo dominante do build frio (#249).
            return (mapped, display), mapped
        # Display desconhecido: resolve pelo fallback do token, nunca assume que é a
        # entrada — isso aplicaria o offset de outro arquivo ao texto da entrada.
        return None, _token_file(token, root, analysis.path)

    for name, token in _top_level_declarations(merged):
        display = token.file or entry_display
        key, token_path = bucket(display, token)
        if key is None:
            own_declarations.setdefault(name, (token_path, token))
        else:
            module_declarations.setdefault(key, {}).setdefault(name, (token_path, token))
    for statement in merged:
        for item in _tokens(statement):
            display = item.file or entry_display
            key, token_path = bucket(display, item)
            record = (token_path, item.offset, item.lexeme)
            if key is None:
                own_tokens.append(record)
            else:
                module_tokens.setdefault(key, []).append(record)
    own = _Contribution(tuple(own_tokens), own_declarations)
    modules = tuple(
        (
            key,
            _Contribution(tuple(items), module_declarations.get(key, {})),
        )
        for key, items in module_tokens.items()
    )
    return _Parsed(analysis, own, modules)


def _top_level_declarations(statements: list[Stmt]) -> list[tuple[str, Token]]:
    """Declarações top-level (container None), sem construir `SymbolIndex`.

    Espelha a caminhada do `SymbolIndex` para os kinds renamáveis: declarações em
    blocos/if/while/try de topo e variáveis de destructuring/for também contam.
    Rename/references não usam tipos, então o índice completo era custo puro (#249).
    """
    found: list[tuple[str, Token]] = []

    def visit(statement: Stmt) -> None:
        if isinstance(statement, (Function, Class, Interface, EnumDecl, TypeAlias, Var)):
            found.append((statement.name.lexeme, statement.name))
        elif isinstance(statement, Destructure):
            for name in pattern_names(statement.pattern):
                found.append((name.lexeme, name))
        elif isinstance(statement, Block):
            for inner in statement.statements:
                visit(inner)
        elif isinstance(statement, ForIn):
            found.append((statement.name.lexeme, statement.name))
            visit(statement.body)
        elif isinstance(statement, If):
            visit(statement.then_branch)
            if statement.else_branch is not None:
                visit(statement.else_branch)
        elif isinstance(statement, While):
            visit(statement.body)
        elif isinstance(statement, Try):
            for inner in statement.body:
                visit(inner)
            for clause in statement.handlers:
                found.append((clause.binding.lexeme, clause.binding))
                for inner in clause.body:
                    visit(inner)
            if statement.finally_body is not None:
                for inner in statement.finally_body:
                    visit(inner)

    for statement in statements:
        visit(statement)
    return found


def _target(workspace: _Workspace, target_path: Path, token: Token) -> Target | None:
    key = (target_path.resolve(), token.offset)
    candidates = {lexeme for lexeme in workspace.positions.get(key, set()) if "$" in lexeme}
    if not candidates:
        analysis = workspace.analyses.get(target_path)
        if analysis is not None:
            candidates = _candidate_from_import(analysis, token)
            candidates = {item for item in candidates if item in workspace.declarations}
    if not candidates:
        return None
    names = sorted(candidates)
    declaration = next(
        (workspace.declarations[name] for name in names if name in workspace.declarations),
        None,
    )
    if declaration is None:
        return None
    declaration_file, declaration_token = declaration
    old_name = declaration_token.lexeme.rsplit("$", 1)[-1]
    direct_names: dict[Path, set[str]] = {}
    aliases: dict[Path, set[str]] = {}
    for path, analysis in workspace.analyses.items():
        for statement in analysis.original:
            if not isinstance(statement, Import) or not statement.from_import:
                continue
            module = ".".join(part.lexeme for part in statement.path)
            for item in statement.names:
                candidate = module.replace(".", "$") + "$" + item.name.lexeme
                if candidate in candidates:
                    local = (item.alias or item.name).lexeme
                    if item.alias is not None and local != item.name.lexeme:
                        aliases.setdefault(path, set()).add(local)
                    else:
                        direct_names.setdefault(path, set()).add(local)
    direct_names.setdefault(declaration_file, set()).add(old_name)
    if token.lexeme in aliases.get(target_path, set()) and token.lexeme != old_name:
        return None
    return Target(
        old_name=old_name,
        declaration_file=declaration_file,
        declaration_offset=declaration_token.offset,
        mangled=frozenset(candidates),
        direct_names={path: frozenset(names) for path, names in direct_names.items()},
        aliases={path: frozenset(names) for path, names in aliases.items()},
    )


def _candidate_from_import(analysis: _Analysis, token: Token) -> set[str]:
    candidates: set[str] = set()
    imported = imports_of(analysis.original).get(token.lexeme)
    if imported is not None and imported.public is not None:
        candidates.add(imported.module.replace(".", "$") + "$" + imported.public)
    for statement in analysis.original:
        if not isinstance(statement, Import) or not statement.from_import:
            continue
        module = ".".join(part.lexeme for part in statement.path)
        for item in statement.names:
            if item.name.lexeme == token.lexeme:
                candidates.add(module.replace(".", "$") + "$" + item.name.lexeme)
    return candidates


def _occurrence_offsets(workspace: _Workspace, target: Target) -> dict[Path, set[int]]:
    """Offsets de declaração e usos que pertencem ao alvo (a mesma regra do rename)."""
    offsets: dict[Path, set[int]] = {}
    for name in target.mangled:
        for path, offset in workspace.tokens_by_lexeme.get(name, set()):
            text = workspace.files.get(path)
            if text is None:
                continue
            identifier = _identifier_at(text, offset)
            if identifier in target.aliases.get(path, frozenset()):
                continue
            offsets.setdefault(path, set()).add(offset)
    offsets.setdefault(target.declaration_file, set()).add(target.declaration_offset)

    for path, analysis in workspace.analyses.items():
        for statement in analysis.original:
            if not isinstance(statement, Import) or not statement.from_import:
                continue
            module = ".".join(part.lexeme for part in statement.path)
            for item in statement.names:
                candidate = module.replace(".", "$") + "$" + item.name.lexeme
                if candidate in target.mangled:
                    offsets.setdefault(path, set()).add(item.name.offset)

    for path, names in target.direct_names.items():
        local_analysis = workspace.analyses.get(path)
        if local_analysis is None:
            continue
        for statement in local_analysis.original:
            for type_token in _class_type_tokens(statement):
                if type_token.lexeme in names:
                    offsets.setdefault(path, set()).add(type_token.offset)
    return offsets


def _edits(workspace: _Workspace, target: Target, new_name: str) -> dict[str, object] | str:
    edits = _occurrence_offsets(workspace, target)

    for path in edits:
        if not within_root(workspace.root, path):
            return (
                f"Can't rename '{target.old_name}': the change would touch "
                f"{path.name}, outside the workspace root."
            )

    for path in edits:
        collision_analysis = workspace.analyses.get(path)
        if collision_analysis is None:
            continue
        for statement in collision_analysis.original:
            for token in _tokens(statement):
                if token.lexeme == new_name:
                    return (
                        f"Can't rename '{target.old_name}' to '{new_name}': "
                        f"the name is already used in {path.name}."
                    )

    changes: dict[str, list[dict[str, object]]] = {}
    for path, path_offsets in edits.items():
        text = workspace.files.get(path)
        if text is None:
            return f"Can't rename '{target.old_name}': can't read {path.name}."
        entries: list[dict[str, object]] = []
        for offset in sorted(path_offsets):
            identifier = _identifier_at(text, offset)
            if identifier is None:
                continue
            start = _position(text, offset)
            end = _position(text, offset + len(identifier.encode("utf-8")))
            entries.append(
                {
                    "range": {"start": start, "end": end},
                    "newText": new_name,
                }
            )
        if entries:
            changes[path.resolve().as_uri()] = entries
    return {"changes": changes}


def _tokens(value: object) -> list[Token]:
    found: list[Token] = []

    def visit(item: object) -> None:
        if isinstance(item, Token):
            found.append(item)
            return
        if is_dataclass(item) and not isinstance(item, type):
            for field_ in fields(item):
                visit(getattr(item, field_.name))
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return found


def _class_type_tokens(value: object) -> list[Token]:
    found: list[Token] = []

    def visit(item: object) -> None:
        if isinstance(item, ClassTy) and item.token is not None:
            found.append(item.token)
        if is_dataclass(item) and not isinstance(item, type):
            for field_ in fields(item):
                visit(getattr(item, field_.name))
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return found


def _token_file(token: Token, root: Path, fallback: Path) -> Path:
    if not token.file:
        return fallback.resolve()
    path = Path(token.file)
    if path.is_absolute():
        return path.resolve()
    for base in (Path.cwd(), root, fallback.parent):
        candidate = base / path
        if candidate.exists():
            return candidate.resolve()
    return (root / path).resolve()


def _identifier_at(text: str, offset: int) -> str | None:
    data = text.encode("utf-8")
    match = _IDENTIFIER.match(data[offset:].decode("utf-8"))
    return match.group(0) if match is not None else None


def _position(text: str, offset: int) -> dict[str, int]:
    data = text.encode("utf-8")
    prefix = data[:offset].decode("utf-8")
    line = prefix.count("\n")
    last = prefix.rsplit("\n", 1)[-1]
    return {"line": line, "character": len(last.encode("utf-16-le")) // 2}

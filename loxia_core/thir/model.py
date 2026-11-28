# SPDX-License-Identifier: MIT OR Apache-2.0
"""Modelo do THIR: a árvore tipada e desugarada entre o checker e os motores.

O THIR (ADR-0149 §2) não é CFG nem SSA: é uma árvore. Cada nó carrega a decisão
semântica já tomada — tipo de armazenamento, tipo de fluxo (narrowing), binding
resolvido, spans — para que nenhum motor a re-derive. O AST continua existindo para
tooling (formatter, LSP, `ast_json`).

Invariantes deste modelo:

- **sem identidade de objeto Python**: binding e captura são `DeclId`/`FnId` inteiros,
  atribuídos deterministicamente pelo produtor; nada aqui é chaveado por `id()`.
- **sem alvo**: nenhum valor de LLVM, offset, slot ou bitmap. Layout é derivado pelo
  motor a partir dos `Decl`/`TClass` (ADR-0149 §2, emenda da F2).
- **sem redundância de desugaring**: `Grouping` morre; `for-in`, `match`, `?:`, `??`,
  `?.` continuam nós explícitos na v1 — desugar é a fatia v2 (ver `docs/tech/thir.md`).
- **spans preservados**: o site de erro do nó é o `span` do token correspondente, não
  uma linha sintética.

O modelo é serializável (JSON v1) porque o THIR é o contrato entre o checker Python
(build-time) e os motores em Loxia (runtime); a serialização vive no módulo `serialize`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

from loxia_core.diagnostics.diagnostic import Span
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.ty import FnTy, Ty

DeclId = int
FnId = int

THIR_SCHEMA_VERSION = 1


class Storage(Enum):
    """Onde o binding vive, já resolvido léxicamente.

    `LOCAL` é o frame da função corrente, `CAPTURE` é a célula carregada no `env`
    (com `index` na lista de capturas da função) e `GLOBAL` é o escopo de topo.
    `UNRESOLVED` só aparece quando o `--check` adiou o erro como panic site: o motor
    emite o `Rxxxx` no ponto, como hoje.
    """

    LOCAL = auto()
    CAPTURE = auto()
    GLOBAL = auto()
    UNRESOLVED = auto()


class DeclKind(Enum):
    VAR = auto()
    PARAM = auto()
    THIS = auto()
    FUNCTION = auto()
    CLASS = auto()
    INTERFACE = auto()
    ENUM = auto()
    PATTERN = auto()
    HANDLER = auto()
    LAMBDA = auto()


@dataclass(frozen=True)
class Decl:
    """Uma declaração de binding, com id estável e tipo de armazenamento.

    `ty` é o tipo declarado/inferido para o slot; `None` significa `Any` (o motor
    decide a representação larga). O tipo em cada *uso* viaja no `Ref`/nó, porque o
    narrowing muda por uso.
    """

    id: DeclId
    name: str
    ty: Ty | None
    mutable: bool
    kind: DeclKind
    span: Span | None
    # `True` quando alguma função aninhada captura o binding: o motor guarda o valor
    # numa célula compartilhada em vez de num slot do frame (ADR-0046). É a mesma
    # decisão que `is_captured` tomava no backend; agora ela mora aqui.
    cell: bool = False


@dataclass(frozen=True)
class Ref:
    """Referência resolvida a um `Decl`.

    Para `CAPTURE`, a posição no `env` é o índice do `decl` na tupla
    `TFunction.captures` da função que contém o uso — o motor faz uma busca por id,
    não uma re-derivação de escopo. A ordem das capturas é canônica (nome), então
    dois produtores independentes chegam ao mesmo índice.
    """

    storage: Storage
    decl: DeclId | None
    name: str


# --- expressões ---------------------------------------------------------------


@dataclass(frozen=True)
class TExpr:
    """Base de toda expressão: tipo de fluxo, tipo de armazenamento e span."""

    ty: Ty | None
    storage_ty: Ty | None
    span: Span | None


@dataclass(frozen=True)
class TConst(TExpr):
    value: object


@dataclass(frozen=True)
class TInterp(TExpr):
    """String interpolada: partes literais e expressões, na ordem do fonte."""

    parts: tuple[str | TExpr, ...]


@dataclass(frozen=True)
class TList(TExpr):
    items: tuple[TExpr, ...]


@dataclass(frozen=True)
class TMap(TExpr):
    entries: tuple[tuple[TExpr, TExpr], ...]


@dataclass(frozen=True)
class TTuple(TExpr):
    items: tuple[TExpr, ...]


@dataclass(frozen=True)
class TRange(TExpr):
    start: TExpr
    end: TExpr
    inclusive: bool


@dataclass(frozen=True)
class TUnary(TExpr):
    op: TokenType
    op_span: Span | None
    operand: TExpr


@dataclass(frozen=True)
class TBinary(TExpr):
    op: TokenType
    op_span: Span | None
    left: TExpr
    right: TExpr


@dataclass(frozen=True)
class TLogical(TExpr):
    op: TokenType
    left: TExpr
    right: TExpr


@dataclass(frozen=True)
class TConditional(TExpr):
    condition: TExpr
    then_branch: TExpr
    else_branch: TExpr


@dataclass(frozen=True)
class TVar(TExpr):
    ref: Ref


@dataclass(frozen=True)
class TAssign(TExpr):
    ref: Ref
    value: TExpr


@dataclass(frozen=True)
class TInstance:
    """Instanciação genérica já inferida pelo checker (nome + argumentos)."""

    name: str
    type_args: tuple[Ty, ...]


@dataclass(frozen=True)
class TCall(TExpr):
    callee: TExpr
    arguments: tuple[TExpr, ...]
    paren_span: Span | None
    optional: bool
    spread: bool
    # Chamada genérica já inferida (`f[Int]`) e/ou site de classe genérica
    # (`Box[Int](...)`); o backend monomorfiza a partir daqui.
    instance: TInstance | None
    class_instance: TInstance | None


@dataclass(frozen=True)
class TGet(TExpr):
    receiver: TExpr
    name: str
    name_span: Span | None
    optional: bool


@dataclass(frozen=True)
class TSet(TExpr):
    receiver: TExpr
    name: str
    name_span: Span | None
    value: TExpr


@dataclass(frozen=True)
class TIndex(TExpr):
    receiver: TExpr
    index: TExpr
    bracket_span: Span | None


@dataclass(frozen=True)
class TIndexSet(TExpr):
    receiver: TExpr
    index: TExpr
    value: TExpr
    bracket_span: Span | None


@dataclass(frozen=True)
class TThis(TExpr):
    ref: Ref


@dataclass(frozen=True)
class TSuper(TExpr):
    method: str
    method_span: Span | None
    receiver: Ref


@dataclass(frozen=True)
class TIs(TExpr):
    operand: TExpr
    test_type: Ty


@dataclass(frozen=True)
class TAs(TExpr):
    operand: TExpr
    target_type: Ty


@dataclass(frozen=True)
class TPattern:
    """Base dos padrões de `match`; os bindings já são `Decl` do arm."""

    span: Span | None


@dataclass(frozen=True)
class TVariantPattern(TPattern):
    enum: str
    variant: str
    bindings: tuple[DeclId, ...]


@dataclass(frozen=True)
class TWildcardPattern(TPattern):
    pass


@dataclass(frozen=True)
class TLiteralPattern(TPattern):
    value: object


@dataclass(frozen=True)
class TMatchArm:
    pattern: TPattern
    body: TExpr


@dataclass(frozen=True)
class TMatch(TExpr):
    scrutinee: TExpr
    arms: tuple[TMatchArm, ...]


@dataclass(frozen=True)
class TLambda(TExpr):
    fn: TFunction


# --- statements ---------------------------------------------------------------


@dataclass(frozen=True)
class TStmt:
    span: Span | None


@dataclass(frozen=True)
class TExprStmt(TStmt):
    expression: TExpr


@dataclass(frozen=True)
class TVarStmt(TStmt):
    decl: DeclId
    initializer: TExpr | None


@dataclass(frozen=True)
class TDestructureStmt(TStmt):
    decls: tuple[DeclId, ...]
    initializer: TExpr


@dataclass(frozen=True)
class TBlock(TStmt):
    body: tuple[TStmt, ...]


@dataclass(frozen=True)
class TIf(TStmt):
    condition: TExpr
    then_branch: TStmt
    else_branch: TStmt | None


@dataclass(frozen=True)
class TWhile(TStmt):
    condition: TExpr
    body: TStmt


@dataclass(frozen=True)
class TForIn(TStmt):
    decl: DeclId
    iterable: TExpr
    body: TStmt


@dataclass(frozen=True)
class TFnDecl(TStmt):
    fn: TFunction


@dataclass(frozen=True)
class TReturn(TStmt):
    value: TExpr | None


@dataclass(frozen=True)
class TBreak(TStmt):
    pass


@dataclass(frozen=True)
class TContinue(TStmt):
    pass


@dataclass(frozen=True)
class TClassDecl(TStmt):
    klass: TClass


@dataclass(frozen=True)
class TInterfaceDecl(TStmt):
    interface: TInterface


@dataclass(frozen=True)
class TEnumDecl(TStmt):
    enum: TEnum


@dataclass(frozen=True)
class TTry(TStmt):
    body: tuple[TStmt, ...]
    handlers: tuple[THandler, ...]
    finally_body: tuple[TStmt, ...] | None


@dataclass(frozen=True)
class TRaise(TStmt):
    value: TExpr | None


@dataclass(frozen=True)
class TTypeAlias(TStmt):
    """Sem efeito em runtime; fica no THIR para o dump refletir a declaração."""

    name: str
    target: Ty


# --- declarações --------------------------------------------------------------


@dataclass(frozen=True)
class TParam:
    decl: DeclId
    name: str
    ty: Ty | None
    default: TExpr | None
    variadic: bool
    mutable: bool
    span: Span | None


@dataclass(frozen=True)
class TCapture:
    decl: DeclId
    name: str


@dataclass(frozen=True)
class TFunction:
    """Função, método ou lambda já resolvida.

    `id` é o `Decl` da função quando ela é nomeada e um `Decl` sintético
    (`DeclKind.LAMBDA`) quando é lambda. `captures` está na ordem de primeira captura,
    que é a ordem do `env` que o motor monta.
    """

    id: FnId
    name: str | None
    params: tuple[TParam, ...]
    body: tuple[TStmt, ...]
    ret_ty: Ty | None
    fn_ty: FnTy | None
    type_params: tuple[str, ...]
    is_init: bool
    is_method: bool
    method_class: str | None
    this_decl: DeclId | None
    captures: tuple[TCapture, ...]
    display_name: str
    decl_span: Span | None


@dataclass(frozen=True)
class TField:
    decl: DeclId
    name: str
    ty: Ty | None
    mutable: bool
    initializer: TExpr | None
    span: Span | None


@dataclass(frozen=True)
class TClass:
    decl: DeclId
    name: str
    superclass: str | None
    interfaces: tuple[str, ...]
    type_params: tuple[str, ...]
    fields: tuple[TField, ...]
    methods: tuple[TFunction, ...]
    display_name: str
    span: Span | None


@dataclass(frozen=True)
class TInterface:
    decl: DeclId
    name: str
    methods: tuple[TFunction, ...]
    display_name: str
    span: Span | None


@dataclass(frozen=True)
class TEnumVariant:
    name: str
    payload: tuple[Ty, ...]
    span: Span | None


@dataclass(frozen=True)
class TEnum:
    decl: DeclId
    name: str
    type_params: tuple[str, ...]
    variants: tuple[TEnumVariant, ...]
    display_name: str
    span: Span | None


@dataclass(frozen=True)
class THandler:
    type_name: str
    decl: DeclId
    body: tuple[TStmt, ...]
    span: Span | None


# --- módulo -------------------------------------------------------------------


@dataclass(frozen=True)
class TModule:
    """Uma unidade de compilação já resolvida (loader aplicado, imports fundidos).

    O lowering percorre `statements`; `decls` é o dicionário de bindings por id e
    `instances` são os sites genéricos que o backend monomorfiza. `entry` é o `main`
    de `Result` do ADR-0148, quando existe.
    """

    source_path: str
    statements: tuple[TStmt, ...]
    decls: tuple[Decl, ...]
    instances: tuple[TInstance, ...]
    type_aliases: tuple[tuple[str, Ty], ...]
    entry: FnId | None
    schema_version: int = THIR_SCHEMA_VERSION


def decl_table(module: TModule) -> dict[DeclId, Decl]:
    """Índice id → `Decl` para os motores; a ordem do THIR não importa."""
    return {decl.id: decl for decl in module.decls}

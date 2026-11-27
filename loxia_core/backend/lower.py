# SPDX-License-Identifier: MIT OR Apache-2.0
"""Coordenação do lowering da AST para IR do LLVM.

O lowering é dividido por responsabilidade: `lower_model` (tipos/valores/layouts),
`lower_functions` (ABI de closure), `lower_variables` (slots/células), `lower_optionals`
(`T?`/coerções), `lower_strings`, `lower_classes` (L5) e `lower_calls`. Este módulo fica
com o programa, statements, expressões, aritmética e controle de fluxo.

As ABI/representações são as documentadas no ADR-0048 e permanecem estáveis: funções
`(i8* env, params...)`, métodos `(i8* env, i8* this, params...)`, closure
`{fnptr, env, display}`, instância `{classe, bitmap, slots i64}`. O que não tem
representação falha com 65 explícito, nunca com lowering silencioso.
"""

from __future__ import annotations

from typing import Any

from loxia_core.diagnostics.codes import Code

__all__ = ["BackendError", "Lowerer", "lower_program"]

from loxia_core.backend import llvm_ir
from loxia_core.backend.captures import CaptureAnalysis, analyze_captures
from loxia_core.backend.control_ir import ControlIR
from loxia_core.backend.lower_base import CleanupContext, LoopContext
from loxia_core.backend.lower_bytes import BytesLowering
from loxia_core.backend.lower_calls import CallLowering
from loxia_core.backend.lower_class_codegen import ClassCodegenLowering
from loxia_core.backend.lower_class_layout import ClassLayoutLowering
from loxia_core.backend.lower_containers import ContainerLowering
from loxia_core.backend.lower_enums import EnumLowering
from loxia_core.backend.lower_exceptions import ExceptionLowering
from loxia_core.backend.lower_functions import FunctionLowering
from loxia_core.backend.lower_generics import GenericLowering, MonomorphizationBudget
from loxia_core.backend.lower_instances import InstanceLowering
from loxia_core.backend.lower_math import MathLowering
from loxia_core.backend.lower_model import (
    _BOOL,
    _FLOAT,
    _I8_PTR,
    _I32,
    _INT,
    _OPERAND_MESSAGES,
    _VOID,
    ANY_TAG_NIL,
    NUMERIC,
    BackendError,
    Binding,
    ClassLayout,
    FunctionInfo,
    TypeDesc,
    Value,
    ValueType,
    _unsupported,
    merge_callable_metadata,
)
from loxia_core.backend.lower_optionals import OptionalLowering
from loxia_core.backend.lower_range import RangeLowering
from loxia_core.backend.lower_strings import StringLowering
from loxia_core.backend.lower_tuples import TupleLowering
from loxia_core.backend.lower_variables import VariableLowering
from loxia_core.frontend.expr import (
    As,
    Assign,
    Binary,
    Call,
    Conditional,
    Expr,
    Get,
    Grouping,
    Index,
    IndexSet,
    InterpolatedString,
    Is,
    Lambda,
    ListLiteral,
    Literal,
    Logical,
    MapLiteral,
    Match,
    Range,
    Set,
    Super,
    This,
    TupleLiteral,
    Unary,
    Variable,
)
from loxia_core.frontend.stmt import (
    Block,
    Break,
    Class,
    Continue,
    Destructure,
    EnumDecl,
    Expression,
    ForIn,
    Function,
    If,
    Interface,
    Raise,
    Return,
    Stmt,
    Try,
    TypeAlias,
    Var,
    While,
)
from loxia_core.frontend.token_type import TokenType
from loxia_core.frontend.tokens import Token
from loxia_core.frontend.ty import (
    NIL as TY_NIL,
)
from loxia_core.frontend.ty import (
    Ty,
)


class Lowerer(
    ExceptionLowering,
    EnumLowering,
    GenericLowering,
    MathLowering,
    BytesLowering,
    TupleLowering,
    ContainerLowering,
    RangeLowering,
    FunctionLowering,
    VariableLowering,
    StringLowering,
    ClassLayoutLowering,
    ClassCodegenLowering,
    InstanceLowering,
    OptionalLowering,
    CallLowering,
):
    def __init__(
        self,
        module: Any,
        *,
        types: dict[Expr, Ty],
        depths: dict[Expr, int],
        flow_types: dict[Expr, Ty] | None = None,
        generic_instances: Any = None,
        generic_classes: Any = None,
        generic_class_sites: Any = None,
        type_aliases: dict[str, Ty] | None = None,
        function_types: dict[Any, Any] | None = None,
        source_path: str = "<lox>",
        debug: bool = False,
        entry: Function | None = None,
    ) -> None:
        self.module: Any = module
        # `main -> Result` do arquivo de entrada (ADR-0148); `None` para scripts.
        self.entry = entry
        self.source_path: str = source_path
        self.debug = debug
        self.types = types
        # Tipo de fluxo (com narrowing) por expressão; `types` guarda a
        # representação declarada (ADR-0045). O unbox de `Any` usa este mapa.
        self.flow_types = flow_types if flow_types is not None else types
        self.depths = depths
        self.generic_instances = generic_instances or {}
        self.generic_classes = generic_classes or set()
        self.generic_class_sites = generic_class_sites or {}
        self.type_aliases = type_aliases or {}
        self._function_types = function_types or {}
        self.main: Any = None
        self._control = ControlIR()
        self.builder: Any = None
        self._runtime: dict[str, Any] = {}
        self._extern_values: dict[str, Any] = {}
        self._messages: dict[str, Any] = {}
        self._displays: dict[str, Any] = {}
        self.budget = MonomorphizationBudget()
        self._poison_count = 0
        self._string_count = 0
        self._function_counter = 0
        self._scopes: list[dict[str, Binding]] = [{}]
        self._captures: dict[str, Binding] = {}
        self._globals: dict[str, Binding] = {}
        self._top_level: dict[int, FunctionInfo] = {}
        self._class_names: set[str] = set()
        self._classes: dict[str, ClassLayout] = {}
        self._local_class_counter = 0
        self._function_ir: Any = None
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._in_init = False
        self._method_class: str | None = None
        self._analysis = CaptureAnalysis({}, frozenset())
        self._type_subst: dict[str, Ty] = {}
        self._enum_layouts: dict[str, Any] = {}
        self._enum_names: dict[str, Any] = {}
        self._cleanup_stack: list[CleanupContext] = []
        self._loop_stack: list[LoopContext] = []
        self._emitting_finally: set[int] = set()
        self._handler_exception: Any | None = None
        self._list_expected_element: Ty | None = None
        self._map_expected_key: Ty | None = None
        self._map_expected_value: Ty | None = None
        self._generic_fns: dict[str, Function] = {}
        self._generic_fn_cache: dict[tuple[str, tuple[str, ...]], FunctionInfo] = {}
        self._generic_class_layouts: dict[str, ClassLayout] = {}
        self._generic_class_by_source: dict[str, list[ClassLayout]] = {}
        self._generic_class_nodes: dict[str, Class] = {}
        self._generic_descriptors: dict[str, Any] = {}
        self._interface_ids: dict[str, int] = {}
        self._interface_nodes: dict[str, Interface] = {}
        self._interface_method_names: dict[str, tuple[str, ...]] = {}
        self._interface_method_infos: dict[str, dict[str, FunctionInfo]] = {}
        self._interface_default_closures: dict[str, dict[str, Value]] = {}
        self._interface_default_globals: dict[str, dict[str, Any]] = {}
        self._interface_thunks: dict[tuple[str, str], Any] = {}
        self._emitted_generic_classes: set[str] = set()
        self._pending_generic_classes: list[ClassLayout] = []
        # Stack trace (ADR-0089): strings deduplicadas e call site global lido pelo
        # prologue do chamado. Os globais vivem no runtime C; aqui só declaramos.
        self._trace_strings: dict[tuple[str, str], Any] = {}
        self._call_file_global = llvm_ir.extern_global(self.module, "lox_call_file", _I8_PTR)
        self._call_line_global = llvm_ir.extern_global(self.module, "lox_call_line", _I32)
        self._call_column_global = llvm_ir.extern_global(self.module, "lox_call_column", _I32)

    # --- programa ---

    def lower(self, statements: list[Stmt]) -> None:
        self._analysis = analyze_captures(statements)
        self._prepare_generics(statements)
        self._prepare_enums(statements)
        self._prepare_exception_classes()
        self._prepare_interface_ids(statements)
        self._predeclare_classes(statements)
        self._prepare_generic_classes(statements)
        self._prepare_interface_signatures()
        self._predeclare_functions(statements)

        self._control.reset()
        main = llvm_ir.define_main(self.module)
        self.main = main
        self._function_ir = main
        self._return_type_desc = TypeDesc(ValueType.NIL)
        self._scopes = [{}]
        self._captures = {}
        self._cleanup_stack = []
        self.builder = llvm_ir.builder(self._control.new_block(main, "entry"))
        init_path = llvm_ir.cstring_pointer(self.builder, self._cstring(self.source_path))
        self.builder.call(
            self._function("lox_init", _VOID, [_I8_PTR, _I32, llvm_ir.pointer_pointer()]),
            [init_path, main.args[0], main.args[1]],
        )
        self._emit_exception_classes()
        self._emit_interface_defaults()
        self._drain_pending_generic_classes()

        for statement in statements:
            if self.builder.block.is_terminated:
                break
            self._stmt(statement)
            if self._function_ir is self.main:
                self._drain_pending_generic_classes()

        if self.entry is not None and not self.builder.block.is_terminated:
            self._call_entry(self.entry)

        if not self.builder.block.is_terminated:
            self.builder.ret(llvm_ir.constant(_I32, 0))
        self._seal_blocks(main)

        for statement in statements:
            if not isinstance(statement, Function) or statement.type_params:
                continue
            info = self._top_level[id(statement)]
            self._emit_function(info, statement, ())
        self._control.verify_all()

    def _call_entry(self, entry: Function) -> None:
        """Chama o `main -> Result` do arquivo de entrada (ADR-0148).

        O entry é uma função de topo sem capturas: o closure tem env nulo e o símbolo
        `lox.main` já foi declarado em `_predeclare_functions`. `Ok` cai no retorno 0;
        `Err` delega ao runtime (`error[R1016]: <msg>` + exit 70), com os mesmos bytes
        do tree-walk.
        """
        info = self._top_level.get(id(entry))
        if info is None:
            raise _unsupported("Entry point 'main'", entry.name.line)

        self._set_call_site(entry.name)
        result = self.builder.call(info.ir, [llvm_ir.null_pointer()])
        is_err = self.builder.call(
            self._function("lox_enum_variant_index", _INT, [_I8_PTR, _I8_PTR]),
            [result, self._cstring_ptr("Err")],
        )
        failed = self.builder.icmp_signed("!=", is_err, llvm_ir.constant(_INT, 0))
        error_block = self._control.new_block(self._function_ir, "entry.err")
        ok_block = self._control.new_block(self._function_ir, "entry.ok")
        self.builder.cbranch(failed, error_block, ok_block)

        self.builder = llvm_ir.builder(error_block)
        self.builder.call(self._function("lox_unhandled_result", _VOID, [_I8_PTR]), [result])
        self.builder.ret(llvm_ir.constant(_I32, 70))

        self.builder = llvm_ir.builder(ok_block)
        self.builder.ret(llvm_ir.constant(_I32, 0))

    # --- opcionais (L2.5) ---

    # --- statements ---

    def _stmt(self, stmt: Stmt) -> None:
        if isinstance(stmt, Block):
            self._scopes.append({})
            try:
                for inner in stmt.statements:
                    if self.builder.block.is_terminated:
                        break
                    self._stmt(inner)
            finally:
                self._scopes.pop()
        elif isinstance(stmt, Return):
            self._return(stmt)
        elif isinstance(stmt, Break):
            self._loop_transfer(stmt, "break")
        elif isinstance(stmt, Continue):
            self._loop_transfer(stmt, "continue")
        elif isinstance(stmt, Function):
            if stmt.type_params:
                return
            info = self._top_level.get(id(stmt))
            if info is not None:
                self._define_top_level_function(stmt, info)
            else:
                self._local_function(stmt)
        elif isinstance(stmt, Class):
            self._class_declaration(stmt)
        elif isinstance(stmt, Interface):
            # Tipo apagado em runtime; defaults são emitidos no bootstrap.
            return
        elif isinstance(stmt, TypeAlias):
            # Tipo transparente: só o checker/backend usam o alvo.
            return
        elif isinstance(stmt, Var):
            self._var(stmt)
        elif isinstance(stmt, If):
            self._if(stmt)
        elif isinstance(stmt, While):
            self._while(stmt)
        elif isinstance(stmt, ForIn):
            self._for_in(stmt)
        elif isinstance(stmt, Destructure):
            self._destructure(stmt)
        elif isinstance(stmt, EnumDecl):
            self._enum_decl(stmt)
        elif isinstance(stmt, Try):
            self._try(stmt)
        elif isinstance(stmt, Raise):
            self._raise(stmt)
        elif isinstance(stmt, Expression):
            self._expr(stmt.expression)
        else:
            raise _unsupported(type(stmt).__name__, None)

    def _if(self, stmt: If) -> None:
        condition = self._truthy(self._expr(stmt.condition))
        then_block = self._control.new_block(self._function_ir, "if.then")
        end_block = self._control.new_block(self._function_ir, "if.end")

        if stmt.else_branch is None:
            else_block = end_block
        else:
            else_block = self._control.new_block(self._function_ir, "if.else")

        self.builder.cbranch(condition, then_block, else_block)

        self.builder = llvm_ir.builder(then_block)
        self._stmt(stmt.then_branch)
        if not self.builder.block.is_terminated:
            self.builder.branch(end_block)

        if stmt.else_branch is not None:
            self.builder = llvm_ir.builder(else_block)
            self._stmt(stmt.else_branch)
            if not self.builder.block.is_terminated:
                self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

    def _run_cleanups(self, limit: int = 0) -> bool:
        """Emite os `finally` ativos sem consumir a pilha léxica.

        `limit` é a profundidade do laço alvo: um `break`/`continue` só roda os
        `finally` abertos dentro dele. O `id` do contexto em emissão evita que um
        `break`/`return` dentro do próprio `finally` o emita de novo.
        """
        for cleanup in reversed(self._cleanup_stack[limit:]):
            if id(cleanup) in self._emitting_finally:
                continue
            if not cleanup.unwound:
                cleanup.unwound = True
                self._control.pop_cleanup()
            if cleanup.frame is not None:
                self.builder.call(
                    self._function("lox_try_pop", _VOID, [_I8_PTR]),
                    [cleanup.frame],
                )
            if cleanup.finally_body is not None:
                # O `finally` é léxico: o corpo do `try` já saiu de escopo. Sem
                # truncar, o `depth` gravado pelo resolver aponta para o slot errado.
                saved_scopes = self._scopes
                self._scopes = self._scopes[: cleanup.scopes_depth]
                self._emitting_finally.add(id(cleanup))
                try:
                    self._lower_finally_body(cleanup.finally_body)
                finally:
                    self._scopes = saved_scopes
                    self._emitting_finally.discard(id(cleanup))
                if self.builder.block.is_terminated:
                    return True
        return False

    def _loop_transfer(self, stmt: Break | Continue, kind: str) -> None:
        if not self._loop_stack:
            raise _unsupported(kind, stmt.keyword.line)

        context = self._loop_stack[-1]
        target = context.break_block if kind == "break" else context.continue_block
        if self._run_cleanups(context.cleanup_depth):
            return
        self.builder.branch(target)

    def _while(self, stmt: While) -> None:
        header = self._control.new_block(self._function_ir, "while.cond")
        body = self._control.new_block(self._function_ir, "while.body")
        end = self._control.new_block(self._function_ir, "while.end")

        self.builder.branch(header)
        self.builder = llvm_ir.builder(header)
        condition = self._truthy(self._expr(stmt.condition))
        self.builder.cbranch(condition, body, end)

        self.builder = llvm_ir.builder(body)
        self._loop_stack.append(LoopContext(end, header, len(self._cleanup_stack)))
        try:
            self._stmt(stmt.body)
        finally:
            self._loop_stack.pop()
        if not self.builder.block.is_terminated:
            self.builder.branch(header)

        self.builder = llvm_ir.builder(end)

    def _print_value(self, value: Value) -> None:
        match value.ty:
            case ValueType.INT:
                self.builder.call(self._function("lox_print_int", _VOID, [_INT]), [value.llvm])
            case ValueType.FLOAT:
                self.builder.call(self._function("lox_print_float", _VOID, [_FLOAT]), [value.llvm])
            case ValueType.BOOL:
                widened = self.builder.zext(value.llvm, _I32)
                self.builder.call(self._function("lox_print_bool", _VOID, [_I32]), [widened])
            case ValueType.STRING:
                self.builder.call(self._function("lox_print_str", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.RANGE:
                self.builder.call(self._function("lox_print_range", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.LIST:
                self.builder.call(self._function("lox_print_list", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.MAP:
                self.builder.call(self._function("lox_print_map", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.TUPLE:
                self.builder.call(self._function("lox_print_tuple", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.ENUM:
                self.builder.call(self._function("lox_print_enum", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.BYTES:
                self.builder.call(self._function("lox_print_bytes", _VOID, [_I8_PTR]), [value.llvm])
            case ValueType.FUNCTION:
                self.builder.call(
                    self._function("lox_print_function", _VOID, [_I8_PTR]),
                    [value.llvm],
                )
            case ValueType.CLASS | ValueType.INSTANCE:
                if value.ty is ValueType.INSTANCE:
                    exception = self._exception_text(value)
                    if exception is not None:
                        self.builder.call(
                            self._function("lox_print_str", _VOID, [_I8_PTR]),
                            [exception.llvm],
                        )
                        return
                    # O nome concreto vem do descritor: um valor de interface não
                    # carrega `class_name` estático.
                    self.builder.call(
                        self._function("lox_print_instance", _VOID, [_I8_PTR]),
                        [value.llvm],
                    )
                    return
                display = self._class_display(value.class_name or "?")
                self.builder.call(
                    self._function("lox_print_str", _VOID, [_I8_PTR]),
                    [self._string_literal(display).llvm],
                )
            case ValueType.ANY:
                tag = self.builder.extract_value(value.llvm, 0)
                payload = self.builder.extract_value(value.llvm, 1)
                self.builder.call(
                    self._function("lox_print_any", _VOID, [_INT, _INT]),
                    [tag, payload],
                )
            case ValueType.NIL:
                self.builder.call(self._function("lox_print_nil", _VOID, []), [])

    def _print_optional(self, value: Value) -> None:
        tag = self._optional_tag(value)
        some = self._control.new_block(self._function_ir, "opt.print.some")
        nothing = self._control.new_block(self._function_ir, "opt.print.nil")
        end = self._control.new_block(self._function_ir, "opt.print.end")
        self.builder.cbranch(tag, some, nothing)

        self.builder = llvm_ir.builder(nothing)
        self.builder.call(self._function("lox_print_nil", _VOID, []), [])
        self.builder.branch(end)

        self.builder = llvm_ir.builder(some)
        self._print_value(self._optional_payload(value))
        self.builder.branch(end)

        self.builder = llvm_ir.builder(end)

    # --- expressões ---

    def _expr(self, expr: Expr) -> Value:
        if isinstance(expr, Variable):
            return self._variable(expr)
        if isinstance(expr, Assign):
            return self._assign(expr)
        if isinstance(expr, Get):
            return self._get(expr)
        if isinstance(expr, Set):
            return self._set(expr)
        if isinstance(expr, This):
            return self._this(expr)
        if isinstance(expr, Super):
            return self._super_method(expr)
        if isinstance(expr, Is):
            return self._is_expr(expr)
        if isinstance(expr, As):
            return self._as_expr(expr)
        if isinstance(expr, Literal):
            return self._literal(expr)
        if isinstance(expr, Grouping):
            return self._expr(expr.expression)
        if isinstance(expr, Unary):
            return self._unary(expr)
        if isinstance(expr, Binary):
            return self._binary(expr)
        if isinstance(expr, Call):
            return self._call(expr)
        if isinstance(expr, Conditional):
            return self._conditional(expr)
        if isinstance(expr, Logical):
            return self._logical(expr)
        if isinstance(expr, InterpolatedString):
            return self._interpolated(expr)
        if isinstance(expr, Lambda):
            return self._lambda(expr)
        if isinstance(expr, Range):
            return self._range_expr(expr)
        if isinstance(expr, ListLiteral):
            return self._list_literal(expr)
        if isinstance(expr, MapLiteral):
            return self._map_literal(expr)
        if isinstance(expr, TupleLiteral):
            return self._tuple_literal(expr)
        if isinstance(expr, Match):
            return self._match(expr)
        if isinstance(expr, Index):
            return self._list_get(expr)
        if isinstance(expr, IndexSet):
            return self._list_set(expr)

        raise _unsupported(type(expr).__name__, None)

    # --- funções e closures ---

    # --- células ---

    # --- classes e instâncias ---

    # --- variáveis ---

    def _literal(self, expr: Literal) -> Value:
        value = expr.value

        if value is None:
            return Value(ValueType.NIL)
        if isinstance(value, bool):
            return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, int(value)))
        if isinstance(value, int):
            return Value(ValueType.INT, llvm_ir.constant(_INT, value))
        if isinstance(value, float):
            return Value(ValueType.FLOAT, llvm_ir.float_constant(value))
        if isinstance(value, str):
            return self._string_literal(value)

        raise _unsupported("Literal", None)

    def _unary(self, expr: Unary) -> Value:
        operand = self._expr(expr.right)
        line = expr.operator.line
        column = expr.operator.column

        match expr.operator.type:
            case TokenType.MINUS:
                if operand.ty is ValueType.ANY and not operand.optional:
                    boxed = self._box_value(operand, line)
                    call = self.builder.call(
                        self._function("lox_any_neg", self._any_type(), [_INT, _INT, _I32, _I32]),
                        [
                            self.builder.extract_value(boxed.llvm, 0),
                            self.builder.extract_value(boxed.llvm, 1),
                            llvm_ir.constant(_I32, line),
                            llvm_ir.constant(_I32, column),
                        ],
                    )
                    return Value(ValueType.ANY, call)
                operand = self._unwrap_operand(
                    operand,
                    line,
                    "Operand must be a number.",
                    column=column,
                    code=Code.RUNTIME_OPERANDS,
                )
                if operand.ty is ValueType.INT:
                    if self.debug:
                        call = self.builder.call(
                            self._function("lox_int_neg_checked", _INT, [_INT, _I32, _I32]),
                            [
                                operand.llvm,
                                llvm_ir.constant(_I32, line),
                                llvm_ir.constant(_I32, column),
                            ],
                        )
                        return Value(ValueType.INT, call)
                    zero = llvm_ir.constant(_INT, 0)
                    return Value(ValueType.INT, self.builder.sub(zero, operand.llvm))
                if operand.ty is ValueType.FLOAT:
                    return Value(ValueType.FLOAT, self.builder.fneg(operand.llvm))
                self._poison(
                    line,
                    "Operand must be a number.",
                    column=column,
                    code=Code.RUNTIME_OPERANDS,
                )
                return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
            case TokenType.NOT:
                truth = self._truthy(operand)
                return Value(ValueType.BOOL, self.builder.not_(truth))
            case TokenType.TILDE:
                if operand.ty is ValueType.ANY and not operand.optional:
                    boxed = self._box_value(operand, line)
                    call = self.builder.call(
                        self._function(
                            "lox_any_bit_not", self._any_type(), [_INT, _INT, _I32, _I32]
                        ),
                        [
                            self.builder.extract_value(boxed.llvm, 0),
                            self.builder.extract_value(boxed.llvm, 1),
                            llvm_ir.constant(_I32, line),
                            llvm_ir.constant(_I32, column),
                        ],
                    )
                    return Value(ValueType.ANY, call)
                operand = self._unwrap_operand(
                    operand,
                    line,
                    "Operand must be an integer.",
                    column=column,
                    code=Code.RUNTIME_OPERANDS,
                )
                if operand.ty is not ValueType.INT:
                    self._poison(
                        line,
                        "Operand must be an integer.",
                        column=column,
                        code=Code.RUNTIME_OPERANDS,
                    )
                    return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
                return Value(
                    ValueType.INT,
                    self.builder.xor(operand.llvm, llvm_ir.constant(_INT, -1)),
                )

        raise _unsupported(f"Unary operator '{expr.operator.lexeme}'", line)

    def _binary(self, expr: Binary) -> Value:
        left = self._expr(expr.left)
        right = self._expr(expr.right)
        operator = expr.operator
        line = operator.line

        # `Any` é o escape dinâmico: o checker aceita as operações e o runtime
        # decide pela tag, como o tree-walk. `==`/`!=` já têm caminho próprio.
        if (
            (left.ty is ValueType.ANY or right.ty is ValueType.ANY)
            and not left.optional
            and not right.optional
            and operator.type not in (TokenType.EQUAL_EQUAL, TokenType.NOT_EQUAL)
        ):
            return self._any_operator(left, right, operator)

        match operator.type:
            case TokenType.PLUS:
                return self._arithmetic(left, right, "add", "fadd", operator.type, operator)
            case TokenType.MINUS:
                return self._arithmetic(left, right, "sub", "fsub", operator.type, operator)
            case TokenType.STAR:
                return self._arithmetic(left, right, "mul", "fmul", operator.type, operator)
            case TokenType.SLASH:
                return self._float_division(left, right, operator)
            case TokenType.SLASH_SLASH:
                return self._integer_division(left, right, operator)
            case TokenType.PERCENT:
                return self._modulo(left, right, operator)
            case (
                TokenType.LESS | TokenType.LESS_EQUAL | TokenType.GREATER | TokenType.GREATER_EQUAL
            ):
                return self._comparison(left, right, operator.type, operator)
            case TokenType.EQUAL_EQUAL | TokenType.NOT_EQUAL:
                return self._equality(left, right, operator.type)
            case TokenType.STAR_STAR:
                return self._power(left, right, operator)
            case TokenType.AMPERSAND:
                return self._bitwise(left, right, "and", operator)
            case TokenType.PIPE:
                return self._bitwise(left, right, "or", operator)
            case TokenType.CARET:
                return self._bitwise(left, right, "xor", operator)
            case TokenType.LESS_LESS:
                return self._shift(left, right, 0, operator)
            case TokenType.GREATER_GREATER:
                return self._shift(left, right, 1, operator)
            case TokenType.GREATER_GREATER_GREATER:
                return self._shift(left, right, 2, operator)

        raise _unsupported(f"Binary operator '{operator.lexeme}'", line)

    def _any_operator(self, left: Value, right: Value, operator: Token) -> Value:
        """Operador binário com pelo menos um operando `Any` (L6 dinâmico)."""
        line = operator.line
        column = operator.column
        boxed_left = self._box_value(left, line)
        boxed_right = self._box_value(right, line)
        left_tag = self.builder.extract_value(boxed_left.llvm, 0)
        left_payload = self.builder.extract_value(boxed_left.llvm, 1)
        right_tag = self.builder.extract_value(boxed_right.llvm, 0)
        right_payload = self.builder.extract_value(boxed_right.llvm, 1)

        if operator.type in (
            TokenType.LESS,
            TokenType.LESS_EQUAL,
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
        ):
            comparison_op = {
                TokenType.LESS: 0,
                TokenType.LESS_EQUAL: 1,
                TokenType.GREATER: 2,
                TokenType.GREATER_EQUAL: 3,
            }[operator.type]
            call = self.builder.call(
                self._function(
                    "lox_any_compare",
                    _I32,
                    [_I32, _INT, _INT, _INT, _INT, _I32, _I32],
                ),
                [
                    llvm_ir.constant(_I32, comparison_op),
                    left_tag,
                    left_payload,
                    right_tag,
                    right_payload,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(
                ValueType.BOOL,
                self.builder.icmp_signed("!=", call, llvm_ir.constant(_I32, 0)),
            )

        op = {
            TokenType.PLUS: 0,
            TokenType.MINUS: 1,
            TokenType.STAR: 2,
            TokenType.SLASH: 3,
            TokenType.SLASH_SLASH: 4,
            TokenType.PERCENT: 5,
            TokenType.STAR_STAR: 6,
            TokenType.AMPERSAND: 7,
            TokenType.PIPE: 8,
            TokenType.CARET: 9,
            TokenType.LESS_LESS: 10,
            TokenType.GREATER_GREATER: 11,
            TokenType.GREATER_GREATER_GREATER: 12,
        }.get(operator.type)
        if op is None:
            raise _unsupported(f"Binary operator '{operator.lexeme}' on Any", line)
        call = self.builder.call(
            self._function(
                "lox_any_binary",
                self._any_type(),
                [_I32, _INT, _INT, _INT, _INT, _I32, _I32],
            ),
            [
                llvm_ir.constant(_I32, op),
                left_tag,
                left_payload,
                right_tag,
                right_payload,
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.ANY, call)

    def _power(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            "Operands must be numbers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            "Operands must be numbers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            pow_name = "lox_int_pow_checked" if self.debug else "lox_int_pow"
            call = self.builder.call(
                self._function(pow_name, _INT, [_INT, _INT, _I32, _I32]),
                [
                    left.llvm,
                    right.llvm,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.INT, call)
        if left.ty in NUMERIC and right.ty in NUMERIC:
            call = self.builder.call(
                self._function("lox_float_pow", _FLOAT, [_FLOAT, _FLOAT, _I32, _I32]),
                [
                    self._to_float(left),
                    self._to_float(right),
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.FLOAT, call)
        self._poison(
            line,
            "Operands must be numbers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _bitwise(self, left: Value, right: Value, op: str, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is not ValueType.INT or right.ty is not ValueType.INT:
            self._poison(
                line,
                "Operands must be integers.",
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
        operation = {
            "and": self.builder.and_,
            "or": self.builder.or_,
            "xor": self.builder.xor,
        }[op]
        return Value(ValueType.INT, operation(left.llvm, right.llvm))

    def _shift(self, left: Value, right: Value, kind: int, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            "Operands must be integers.",
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is not ValueType.INT or right.ty is not ValueType.INT:
            self._poison(
                line,
                "Operands must be integers.",
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))
        call = self.builder.call(
            self._function("lox_shift", _INT, [_INT, _INT, _I32, _I32, _I32]),
            [
                left.llvm,
                right.llvm,
                llvm_ir.constant(_I32, kind),
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.INT, call)

    def _arithmetic(
        self,
        left: Value,
        right: Value,
        integer_op: str,
        float_op: str,
        operator: TokenType,
        token: Token,
    ) -> Value:
        line = token.line
        column = token.column
        message = _OPERAND_MESSAGES[operator]
        left = self._unwrap_operand(left, line, message, column=column, code=Code.RUNTIME_OPERANDS)
        right = self._unwrap_operand(
            right, line, message, column=column, code=Code.RUNTIME_OPERANDS
        )

        if operator is TokenType.PLUS and (
            left.ty is ValueType.STRING and right.ty is ValueType.STRING
        ):
            return self._concat(left, right)

        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            if self.debug:
                helper = {
                    "add": "lox_int_add_checked",
                    "sub": "lox_int_sub_checked",
                    "mul": "lox_int_mul_checked",
                }[integer_op]
                call = self.builder.call(
                    self._function(helper, _INT, [_INT, _INT, _I32, _I32]),
                    [
                        left.llvm,
                        right.llvm,
                        llvm_ir.constant(_I32, line),
                        llvm_ir.constant(_I32, column),
                    ],
                )
                return Value(ValueType.INT, call)
            operation = getattr(self.builder, integer_op)
            return Value(ValueType.INT, operation(left.llvm, right.llvm))

        if left.ty in NUMERIC and right.ty in NUMERIC:
            operation = getattr(self.builder, float_op)
            return Value(
                ValueType.FLOAT,
                operation(self._to_float(left), self._to_float(right)),
            )

        self._poison(
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _float_division(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty not in NUMERIC or right.ty not in NUMERIC:
            self._poison(
                line,
                _OPERAND_MESSAGES[TokenType.SLASH],
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.FLOAT, llvm_ir.float_constant(0.0))

        function = self._function("lox_float_div", _FLOAT, [_FLOAT, _FLOAT, _I32, _I32])
        call = self.builder.call(
            function,
            [
                self._to_float(left),
                self._to_float(right),
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.FLOAT, call)

    def _integer_division(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH_SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[TokenType.SLASH_SLASH],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if not (left.ty is ValueType.INT and right.ty is ValueType.INT):
            self._poison(
                line,
                _OPERAND_MESSAGES[TokenType.SLASH_SLASH],
                column=column,
                code=Code.RUNTIME_OPERANDS,
            )
            return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

        div_name = "lox_int_div_checked" if self.debug else "lox_int_div"
        function = self._function(div_name, _INT, [_INT, _INT, _I32, _I32])
        call = self.builder.call(
            function,
            [
                left.llvm,
                right.llvm,
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
            ],
        )
        return Value(ValueType.INT, call)

    def _modulo(self, left: Value, right: Value, token: Token) -> Value:
        line = token.line
        column = token.column
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[TokenType.PERCENT],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[TokenType.PERCENT],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            mod_name = "lox_int_mod_checked" if self.debug else "lox_int_mod"
            function = self._function(mod_name, _INT, [_INT, _INT, _I32, _I32])
            call = self.builder.call(
                function,
                [
                    left.llvm,
                    right.llvm,
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.INT, call)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            function = self._function("lox_float_mod", _FLOAT, [_FLOAT, _FLOAT, _I32, _I32])
            call = self.builder.call(
                function,
                [
                    self._to_float(left),
                    self._to_float(right),
                    llvm_ir.constant(_I32, line),
                    llvm_ir.constant(_I32, column),
                ],
            )
            return Value(ValueType.FLOAT, call)

        self._poison(
            line,
            _OPERAND_MESSAGES[TokenType.PERCENT],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.INT, llvm_ir.constant(_INT, 0))

    def _comparison(self, left: Value, right: Value, operator: TokenType, token: Token) -> Value:
        line = token.line
        column = token.column
        predicates = {
            TokenType.LESS: "<",
            TokenType.LESS_EQUAL: "<=",
            TokenType.GREATER: ">",
            TokenType.GREATER_EQUAL: ">=",
        }
        left = self._unwrap_operand(
            left,
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        right = self._unwrap_operand(
            right,
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )

        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            result = self.builder.icmp_signed(predicates[operator], left.llvm, right.llvm)
            return Value(ValueType.BOOL, result)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            # `fcmp ordered`: NaN torna a comparação falsa, como `numeric.compare`.
            result = self.builder.fcmp_ordered(
                predicates[operator], self._to_float(left), self._to_float(right)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.STRING and right.ty is ValueType.STRING:
            function = self._function("lox_str_compare", _I32, [_I8_PTR, _I8_PTR])
            comparison = self.builder.call(function, [left.llvm, right.llvm])
            result = self.builder.icmp_signed(
                predicates[operator], comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        self._poison(
            line,
            _OPERAND_MESSAGES[operator],
            column=column,
            code=Code.RUNTIME_OPERANDS,
        )
        return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, 0))

    def _equality(self, left: Value, right: Value, operator: TokenType) -> Value:
        if left.optional or right.optional:
            return self._optional_equality(left, right, operator)
        return self._plain_equality(left, right, operator)

    def _plain_equality(self, left: Value, right: Value, operator: TokenType) -> Value:
        equal = operator is TokenType.EQUAL_EQUAL

        if left.ty is ValueType.ANY or right.ty is ValueType.ANY:
            left_boxed = self._box_value(left, None)
            right_boxed = self._box_value(right, None)
            left_tag = self.builder.extract_value(left_boxed.llvm, 0)
            left_payload = self.builder.extract_value(left_boxed.llvm, 1)
            right_tag = self.builder.extract_value(right_boxed.llvm, 0)
            right_payload = self.builder.extract_value(right_boxed.llvm, 1)
            result = self.builder.call(
                self._function("lox_any_equal", _I32, [_INT, _INT, _INT, _INT]),
                [left_tag, left_payload, right_tag, right_payload],
            )
            compared = self.builder.icmp_signed("!=", result, llvm_ir.constant(_I32, 0))
            if not equal:
                compared = self.builder.not_(compared)
            return Value(ValueType.BOOL, compared)

        if left.ty is ValueType.ENUM and right.ty is ValueType.ENUM:
            equal_value = self.builder.call(
                self._function("lox_enum_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed("!=", equal_value, llvm_ir.constant(_I32, 0))
            if not equal:
                result = self.builder.not_(result)
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.TUPLE and right.ty is ValueType.TUPLE:
            equal_value = self._tuple_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.MAP and right.ty is ValueType.MAP:
            equal_value = self._map_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.LIST and right.ty is ValueType.LIST:
            equal_value = self._list_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.RANGE and right.ty is ValueType.RANGE:
            comparison = self.builder.call(
                self._function("lox_range_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.BYTES and right.ty is ValueType.BYTES:
            function = self._function("lox_bytes_equal", _I32, [_I8_PTR, _I8_PTR])
            comparison = self.builder.call(function, [left.llvm, right.llvm])
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        if (left.ty is ValueType.FUNCTION and right.ty is ValueType.NIL) or (
            right.ty is ValueType.FUNCTION and left.ty is ValueType.NIL
        ):
            # A sentinela de função não inicializada é `nil`, como no tree-walk.
            function = left if left.ty is ValueType.FUNCTION else right
            result = self.builder.call(
                self._function("lox_function_is_nil", _I32, [_I8_PTR]),
                [function.llvm],
            )
            is_nil = self.builder.icmp_signed("!=", result, llvm_ir.constant(_I32, 0))
            if not equal:
                is_nil = self.builder.not_(is_nil)
            return Value(ValueType.BOOL, is_nil)

        if left.ty is ValueType.NIL or right.ty is ValueType.NIL:
            both_nil = left.ty is right.ty
            return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, int(both_nil == equal)))

        if left.ty is ValueType.ENUM and right.ty is ValueType.ENUM:
            equal_value = self.builder.call(
                self._function("lox_enum_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed("!=", equal_value, llvm_ir.constant(_I32, 0))
            if not equal:
                result = self.builder.not_(result)
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.TUPLE and right.ty is ValueType.TUPLE:
            equal_value = self._tuple_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.MAP and right.ty is ValueType.MAP:
            equal_value = self._map_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.LIST and right.ty is ValueType.LIST:
            equal_value = self._list_equal(left, right).llvm
            if not equal:
                equal_value = self.builder.not_(equal_value)
            return Value(ValueType.BOOL, equal_value)

        if left.ty is ValueType.RANGE and right.ty is ValueType.RANGE:
            comparison = self.builder.call(
                self._function("lox_range_equal", _I32, [_I8_PTR, _I8_PTR]),
                [left.llvm, right.llvm],
            )
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.STRING and right.ty is ValueType.STRING:
            function = self._function("lox_str_equal", _I32, [_I8_PTR, _I8_PTR])
            comparison = self.builder.call(function, [left.llvm, right.llvm])
            result = self.builder.icmp_signed(
                "!=" if equal else "==", comparison, llvm_ir.constant(_I32, 0)
            )
            return Value(ValueType.BOOL, result)

        if left.ty is ValueType.INT and right.ty is ValueType.INT:
            result = self.builder.icmp_signed("==" if equal else "!=", left.llvm, right.llvm)
            return Value(ValueType.BOOL, result)

        if left.ty in NUMERIC and right.ty in NUMERIC:
            # `==` é ordered (`NaN == NaN` falso); `!=` é unordered
            # (`NaN != NaN` verdadeiro, como no tree-walk e na spec).
            left_float = self._to_float(left)
            right_float = self._to_float(right)
            if equal:
                result = self.builder.fcmp_ordered("==", left_float, right_float)
            else:
                result = self.builder.fcmp_unordered("!=", left_float, right_float)
            return Value(ValueType.BOOL, result)

        if left.ty is right.ty:
            if left.ty is ValueType.FUNCTION and left.sig != right.sig:
                return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, int(not equal)))
            result = self.builder.icmp_signed("==" if equal else "!=", left.llvm, right.llvm)
            return Value(ValueType.BOOL, result)

        # Tipos diferentes nunca são iguais (I2): constante, sem comparação.
        return Value(ValueType.BOOL, llvm_ir.constant(_BOOL, int(not equal)))

    def _to_float(self, value: Value) -> Any:
        if value.ty is ValueType.FLOAT:
            return value.llvm
        return self.builder.sitofp(value.llvm, _FLOAT)

    def _return(self, stmt: Return) -> None:
        value: Value | None
        if stmt.value is None:
            if self._return_type_desc.ty is ValueType.NIL:
                value = None
            elif self._return_type_desc.optional:
                value = self._zero_desc(self._return_type_desc)
            else:
                raise BackendError(
                    "Returning nil from a non-Nil function is not supported by the backend yet.",
                    stmt.keyword.line,
                    code=Code.BACKEND_UNSUPPORTED,
                )
        else:
            value = self._coerce(
                self._expr(stmt.value),
                self._return_type_desc,
                stmt.keyword.line,
                source=stmt.value,
            )
            if self._return_type_desc.ty is ValueType.NIL:
                value = None

        # O valor é avaliado antes do finally (semântica do tree-walk); o `ret` só
        # acontece depois de desempilhar os frames e rodar os cleanups ativos.
        if self._run_cleanups():
            return

        self._stack_leave()
        if value is None:
            self.builder.ret_void()
        else:
            self.builder.ret(value.llvm)

    def _conditional(self, expr: Conditional) -> Value:
        condition = self._truthy(self._expr(expr.condition))
        then_block = self._control.new_block(self._function_ir, "cond.then")
        else_block = self._control.new_block(self._function_ir, "cond.else")
        end_block = self._control.new_block(self._function_ir, "cond.end")
        self.builder.cbranch(condition, then_block, else_block)

        self.builder = llvm_ir.builder(then_block)
        then_value = self._expr(expr.then_branch)
        then_end = self.builder.block
        then_open = not then_end.is_terminated

        self.builder = llvm_ir.builder(else_block)
        else_value = self._expr(expr.else_branch)
        else_end = self.builder.block
        else_open = not else_end.is_terminated

        # Os metadados valem para o valor **antes** da coerção: o ramo `nil` deixa
        # de ser `NIL` ao virar opcional e não pode apagar a função do outro ramo.
        function, generic, generic_node = merge_callable_metadata(then_value, else_value)
        common = self._merge_branches(then_value, else_value, None)

        if then_open:
            self.builder = llvm_ir.builder(then_end)
            then_value = self._coerce(then_value, common, None)
            then_end = self.builder.block
            self.builder.branch(end_block)

        if else_open:
            self.builder = llvm_ir.builder(else_end)
            else_value = self._coerce(else_value, common, None)
            else_end = self.builder.block
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if common.ty is ValueType.NIL:
            if not (then_open or else_open):
                self.builder.unreachable()
                return self._zero(ValueType.INT)
            return Value(ValueType.NIL)

        if then_open and else_open:
            merged = self.builder.phi(self._storage_llvm_type(common), "cond.value")
            merged.add_incoming(then_value.llvm, then_end)
            merged.add_incoming(else_value.llvm, else_end)
            return Value(
                common.ty,
                merged,
                common.fn,
                common.optional,
                function=function,
                generic=generic,
                generic_node=generic_node,
            )

        if then_open:
            return then_value
        if else_open:
            return else_value

        self.builder.unreachable()
        return self._zero_desc(common)

    def _merge_branches(self, left: Value, right: Value, line: int | None) -> TypeDesc:
        left_desc = left.desc
        right_desc = right.desc
        if left_desc.same_as(right_desc):
            return left_desc

        left_nil = left.ty is ValueType.NIL
        right_nil = right.ty is ValueType.NIL
        if left_nil and right_nil:
            return left_desc
        if left_nil:
            if right.optional:
                return right_desc
            return TypeDesc(right.ty, right.sig, True)
        if right_nil:
            if left.optional:
                return left_desc
            return TypeDesc(left.ty, left.sig, True)

        if left.optional and not right.optional and TypeDesc(left.ty, left.sig).same_as(right_desc):
            return left_desc
        if (
            right.optional
            and not left.optional
            and TypeDesc(right.ty, right.sig).same_as(left_desc)
        ):
            return right_desc

        if (
            left.ty is ValueType.INSTANCE
            and right.ty is ValueType.INSTANCE
            and not left.optional
            and not right.optional
        ):
            # Duas classes concretas: o ponteiro é representável; o tipo comum
            # fica dinâmico até uma coerção para interface/classe.
            return TypeDesc(ValueType.INSTANCE)

        raise BackendError(
            f"Ternary branches are {left.ty.name} and {right.ty.name}; "
            "union types are not supported by the backend yet.",
            line,
            code=Code.BACKEND_UNSUPPORTED,
        )

    def _logical(self, expr: Logical) -> Value:
        if expr.operator.type is TokenType.QUESTION_QUESTION:
            return self._coalesce(expr)
        return self._short_circuit(expr)

    def _coalesce(self, expr: Logical) -> Value:
        left = self._expr(expr.left)
        if left.ty is ValueType.ANY:
            # `Any` carrega o próprio nil na tag: a otimização "não-opcional logo
            # não-nil" não vale e o lado direito não é morto.
            return self._coalesce_any(left, expr)
        if self.types.get(expr.right) is TY_NIL:
            # `a ?? nil` é o próprio `a`: nil ou o valor, sem mudar a
            # representação (importante para a sentinela de função).
            return left
        if not left.optional and left.ty is ValueType.FUNCTION:
            # A sentinela de função não inicializada é nil em runtime, então o
            # slot "não-opcional" não garante o curto-circuito. Envolver no
            # opcional normaliza sentinela→nil e reusa o caminho abaixo.
            left = self._some(
                TypeDesc(left.ty, left.sig, True, left.class_name, left.interface_name),
                left,
            )
        if not left.optional:
            # Um valor não-nil é sempre não-nil: o lado direito é morto.
            if left.ty is not ValueType.NIL:
                return left
            return self._expr(expr.right)

        coalesced = self.types.get(expr)
        coalesced_desc: TypeDesc | None = None
        if coalesced is not None:
            try:
                coalesced_desc = self._type_desc(coalesced, expr.operator.line)
            except BackendError:
                # União de não-escalares (E4001 declarado): o caminho opcional
                # abaixo ainda tenta coagir o direito e recusa com a mensagem.
                coalesced_desc = None
            if coalesced_desc is not None and coalesced_desc.ty is ValueType.ANY:
                return self._coalesce_any(left, expr)

        inner = TypeDesc(
            left.ty,
            left.sig,
            False,
            left.class_name,
            left.interface_name,
        )
        if coalesced_desc is not None and not coalesced_desc.optional:
            # O tipo comum pode ser o direito (mais largo): `D? ?? C` → `C`.
            inner = TypeDesc(
                coalesced_desc.ty,
                coalesced_desc.fn,
                False,
                coalesced_desc.class_name,
                coalesced_desc.interface_name,
            )
        result_optional = coalesced_desc is not None and coalesced_desc.optional
        optional_struct = TypeDesc(inner.ty, inner.fn, True, inner.class_name, inner.interface_name)

        some = self._control.new_block(self._function_ir, "coalesce.some")
        nothing = self._control.new_block(self._function_ir, "coalesce.nil")
        end = self._control.new_block(self._function_ir, "coalesce.end")
        self.builder.cbranch(self._optional_tag(left), some, nothing)

        self.builder = llvm_ir.builder(some)
        # O ramo esquerdo já está presente: para um resultado opcional o próprio
        # valor opcional serve; senão só o payload interessa.
        some_value = left.llvm if result_optional else self._optional_payload(left).llvm
        self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(nothing)
        right_value = self._expr(expr.right)
        try:
            if result_optional:
                # `a? ?? b?`: nil à esquerda devolve o `b` (que pode ser nil).
                if right_value.optional:
                    right_llvm = right_value.llvm
                else:
                    right_llvm = self._some(
                        optional_struct,
                        self._coerce(right_value, inner, expr.operator.line),
                    ).llvm
            else:
                right_llvm = self._coerce(
                    right_value,
                    inner,
                    expr.operator.line,
                ).llvm
        except BackendError:
            raise _unsupported(
                "Coalesce with different types",
                expr.operator.line,
            ) from None
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(
            self._storage_llvm_type(optional_struct if result_optional else inner),
            "coalesce.value",
        )
        merged.add_incoming(some_value, some_end)
        merged.add_incoming(right_llvm, nothing_end)
        function, generic, generic_node = merge_callable_metadata(left, right_value)
        return Value(
            inner.ty,
            merged,
            inner.fn,
            optional=result_optional,
            class_name=inner.class_name,
            function=function,
            generic=generic,
            generic_node=generic_node,
            interface_name=inner.interface_name,
        )

    def _coalesce_any(self, left: Value, expr: Logical) -> Value:
        some = self._control.new_block(self._function_ir, "coalesce.some")
        nothing = self._control.new_block(self._function_ir, "coalesce.nil")
        end = self._control.new_block(self._function_ir, "coalesce.end")

        if left.ty is ValueType.ANY:
            tag = self.builder.extract_value(left.llvm, 0)
            present = self.builder.icmp_signed("!=", tag, llvm_ir.constant(_INT, ANY_TAG_NIL))
            some_value = left
        else:
            present = self._optional_tag(left)
            some_value = self._box_value(self._optional_payload(left), expr.operator.line)
        self.builder.cbranch(present, some, nothing)

        self.builder = llvm_ir.builder(some)
        self.builder.branch(end)
        some_end = self.builder.block

        self.builder = llvm_ir.builder(nothing)
        right = self._box_value(self._expr(expr.right), expr.operator.line)
        self.builder.branch(end)
        nothing_end = self.builder.block

        self.builder = llvm_ir.builder(end)
        merged = self.builder.phi(
            self._storage_llvm_type(TypeDesc(ValueType.ANY)),
            "coalesce.any",
        )
        merged.add_incoming(some_value.llvm, some_end)
        merged.add_incoming(right.llvm, nothing_end)
        return Value(ValueType.ANY, merged)

    def _short_circuit(self, expr: Logical) -> Value:
        operator = expr.operator.type
        left = self._expr(expr.left)
        if left.ty is ValueType.NIL:
            # Só `nil` é falsy: `nil and x` é nil; `nil or x` é x.
            if operator is TokenType.AND:
                return Value(ValueType.NIL)
            return self._expr(expr.right)

        if isinstance(expr.left, Literal) and isinstance(expr.left.value, bool):
            # `false and x` e `true or x` não avaliam x; `true and x` e `false or x`
            # são exatamente x. Evita a união `Bool | T` no caminho comum.
            evaluate_right = (operator is TokenType.AND and expr.left.value) or (
                operator is TokenType.OR and not expr.left.value
            )
            if evaluate_right:
                return self._expr(expr.right)
            return left

        condition = self._truthy(left)
        short_block = self.builder.block
        right_block = self._control.new_block(self._function_ir, "logical.right")
        end_block = self._control.new_block(self._function_ir, "logical.end")

        if operator is TokenType.AND:
            self.builder.cbranch(condition, right_block, end_block)
        else:
            self.builder.cbranch(condition, end_block, right_block)

        self.builder = llvm_ir.builder(right_block)
        right = self._expr(expr.right)

        common: TypeDesc | None
        if left.ty is ValueType.ANY:
            # O checker tipa o resultado como `Any`; encaixa o direito e funde dois
            # agregados (o esquerdo já é `{tag, payload}`).
            right = self._box_value(right, expr.operator.line)
            common = TypeDesc(ValueType.ANY)
        elif left.optional:
            common = left.desc
            inner = TypeDesc(left.ty, left.sig, False, left.class_name, left.interface_name)
            if not self._compatible(right.desc, inner):
                raise _unsupported(
                    "and/or with an optional left operand and an incompatible right",
                    expr.operator.line,
                )
            right = self._coerce(right, common, expr.operator.line)
        elif left.desc.same_as(right.desc):
            common = left.desc
        else:
            common = None

        right_end = self.builder.block
        right_open = not right_end.is_terminated
        if right_open:
            self.builder.branch(end_block)

        self.builder = llvm_ir.builder(end_block)

        if common is None:
            raise BackendError(
                f"Operands of '{expr.operator.lexeme}' are {left.ty.name} and "
                f"{right.ty.name}; union types are not supported by the backend "
                "yet.",
                expr.operator.line,
            )

        if not right_open:
            return left

        merged = self.builder.phi(self._storage_llvm_type(common), "logical.value")
        merged.add_incoming(left.llvm, short_block)
        merged.add_incoming(right.llvm, right_end)
        function, generic, generic_node = merge_callable_metadata(left, right)
        return Value(
            common.ty,
            merged,
            common.fn,
            common.optional,
            function=function,
            generic=generic,
            generic_node=generic_node,
        )

    def _truthy(self, value: Value) -> Any:
        if value.optional:
            tag = self._optional_tag(value)
            if value.ty is ValueType.BOOL:
                payload = self._optional_payload(value).llvm
                return self.builder.and_(tag, payload)
            return tag

        match value.ty:
            case ValueType.BOOL:
                return value.llvm
            case ValueType.ANY:
                tag = self.builder.extract_value(value.llvm, 0)
                payload = self.builder.extract_value(value.llvm, 1)
                is_nil = self.builder.icmp_signed("==", tag, llvm_ir.constant(_INT, 0))
                is_false = self.builder.and_(
                    self.builder.icmp_signed("==", tag, llvm_ir.constant(_INT, 3)),
                    self.builder.icmp_signed("==", payload, llvm_ir.constant(_INT, 0)),
                )
                return self.builder.not_(self.builder.or_(is_nil, is_false))
            case (
                ValueType.INT
                | ValueType.FLOAT
                | ValueType.STRING
                | ValueType.CLASS
                | ValueType.INSTANCE
                | ValueType.RANGE
                | ValueType.LIST
                | ValueType.MAP
                | ValueType.TUPLE
                | ValueType.ENUM
                | ValueType.BYTES
            ):
                # Só nil e false são falsy: `0`, `0.0` e `""` são truthy.
                return llvm_ir.constant(_BOOL, 1)
            case ValueType.FUNCTION:
                # A sentinela de função não inicializada é nil, logo falsy.
                result = self.builder.call(
                    self._function("lox_function_is_nil", _I32, [_I8_PTR]),
                    [value.llvm],
                )
                is_nil = self.builder.icmp_signed("!=", result, llvm_ir.constant(_I32, 0))
                return self.builder.not_(is_nil)
            case ValueType.NIL:
                return llvm_ir.constant(_BOOL, 0)

    def _poison(
        self,
        target: Token | int,
        message: str,
        *,
        column: int = 0,
        code: Code = Code.RUNTIME_ERROR,
    ) -> None:
        """Rebaixa erro estático a `lox_panic` e continua num bloco inalcançável.

        `target` é o token do erro (leva linha e coluna) ou só a linha. `code` deve
        espelhar o erro que o tree-walk levantaria em runtime (mesmo ponto, mesma
        família), senão o stderr do binário diverge do interpretado e o I1 quebra.
        """
        if isinstance(target, Token):
            line = target.line
            column = target.column
        else:
            line = target
        function = self._panic_function()
        text = self._cstring(message)
        pointer = llvm_ir.cstring_pointer(self.builder, text)
        code_pointer = llvm_ir.cstring_pointer(self.builder, self._cstring(code.value))
        self.builder.call(
            function,
            [
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, column),
                code_pointer,
                pointer,
            ],
        )
        self.builder.unreachable()

        block = self._control.new_block(self._function_ir, f"poison{self._poison_count}")
        self._poison_count += 1
        self.builder = llvm_ir.builder(block)

    def _panic_function(self) -> Any:
        function = self._runtime.get("lox_panic")
        if function is None:
            function = llvm_ir.declare_noreturn(
                self.module, "lox_panic", [_I32, _I32, _I8_PTR, _I8_PTR]
            )
            self._runtime["lox_panic"] = function
        return function

    def _cstring(self, message: str) -> Any:
        global_ = self._messages.get(message)
        if global_ is None:
            global_ = llvm_ir.cstring(self.module, message, f"msg.{len(self._messages)}")
            self._messages[message] = global_
        return global_

    def _function(self, name: str, result: Any, params: list[Any]) -> Any:
        function = self._runtime.get(name)
        if function is None:
            function = llvm_ir.declare(self.module, name, result, params)
            self._runtime[name] = function
        return function

    def _trace_string(self, text: str, kind: str) -> Any:
        key = (kind, text)
        global_ = self._trace_strings.get(key)
        if global_ is None:
            global_ = llvm_ir.cstring(self.module, text, f"trace.{kind}.{len(self._trace_strings)}")
            self._trace_strings[key] = global_
        return global_

    def _emit_stack_enter(self, name: str, file: str, line: int, column: int) -> None:
        """Prologue do chamado: empilha (nome, arquivo, decl) + call site global."""
        name_ptr = llvm_ir.cstring_pointer(self.builder, self._trace_string(name, "name"))
        file_ptr = llvm_ir.cstring_pointer(
            self.builder, self._trace_string(file or self.source_path, "file")
        )
        self.builder.call(
            self._function("lox_stack_enter", _VOID, [_I8_PTR, _I8_PTR, _I32, _I32]),
            [
                name_ptr,
                file_ptr,
                llvm_ir.constant(_I32, line),
                llvm_ir.constant(_I32, max(1, column)),
            ],
        )

    def _stack_enter(self, info: FunctionInfo) -> None:
        self._emit_stack_enter(
            info.trace_name,
            info.decl_file,
            info.decl_line,
            info.decl_column,
        )

    def _stack_enter_class(self, layout: ClassLayout) -> None:
        token = layout.decl_token
        if token is None:
            self._emit_stack_enter(layout.display, self.source_path, 0, 1)
            return
        self._emit_stack_enter(layout.display, token.file, token.line, token.column)

    def _set_call_site(self, token: Token) -> None:
        """Grava o call site para o prologue do chamado (lido em `lox_stack_enter`)."""
        file_ptr = llvm_ir.cstring_pointer(
            self.builder,
            self._trace_string(token.file or self.source_path, "file"),
        )
        self.builder.store(file_ptr, self._call_file_global)
        self.builder.store(llvm_ir.constant(_I32, token.line), self._call_line_global)
        self.builder.store(llvm_ir.constant(_I32, max(1, token.column)), self._call_column_global)

    def _restore_call_site(self) -> None:
        """Devolve o call site do frame atual (ctor → init, após inicializadores)."""
        self.builder.call(self._function("lox_call_site_restore", _VOID, []), [])

    def _stack_leave(self) -> None:
        self.builder.call(self._function("lox_stack_leave", _VOID, []), [])


def lower_program(
    statements: list[Stmt],
    *,
    types: dict[Expr, Ty],
    depths: dict[Expr, int],
    flow_types: dict[Expr, Ty] | None = None,
    generic_instances: Any = None,
    generic_classes: Any = None,
    generic_class_sites: Any = None,
    type_aliases: dict[str, Ty] | None = None,
    function_types: dict[Any, Any] | None = None,
    source_path: str = "<lox>",
    debug: bool = False,
    entry: Function | None = None,
) -> Any:
    module = llvm_ir.new_module()
    Lowerer(
        module,
        types=types,
        depths=depths,
        flow_types=flow_types,
        generic_instances=generic_instances,
        generic_classes=generic_classes,
        generic_class_sites=generic_class_sites,
        type_aliases=type_aliases,
        function_types=function_types,
        source_path=source_path,
        debug=debug,
        entry=entry,
    ).lower(statements)
    return module

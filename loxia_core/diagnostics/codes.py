# SPDX-License-Identifier: MIT OR Apache-2.0
"""Catálogo de códigos estáveis de diagnóstico (ADR-0075).

Um código identifica uma **família** de erro, não uma mensagem: a mensagem
específica continua no texto. Códigos nunca são reaproveitados; refinar uma
família em códigos mais específicos é permitido, desde que o catálogo em
`CODE_DESCRIPTIONS` acompanhe. A tabela em `docs/spec/erros.md` é **gerada**
a partir deste módulo (`make codes`); não edite a tabela à mão.

Faixas:

- `E0xxx` léxico
- `E1xxx` sintaxe (parser)
- `E2xxx` resolução (escopos)
- `E3xxx` checker (`--check`)
- `E4xxx` backend nativo
- `R1xxx` runtime
- `C0xxx` CLI/execução (ex.: timeout)
- `W1xxx` warnings (não falham por padrão)
"""

from __future__ import annotations

from enum import StrEnum

from loxia_core.diagnostics.diagnostic import Phase


class Code(StrEnum):
    # Léxico
    UNEXPECTED_CHARACTER = "E0001"
    UNTERMINATED_STRING = "E0002"
    INVALID_ESCAPE = "E0003"
    INVALID_NUMBER = "E0004"
    UNTERMINATED_COMMENT = "E0005"
    UNTERMINATED_INTERPOLATION = "E0006"
    INVALID_UNICODE_ESCAPE = "E0007"

    # Sintaxe
    SYNTAX_UNEXPECTED = "E1001"
    INVALID_ASSIGNMENT_TARGET = "E1002"
    LIMIT_EXCEEDED = "E1003"
    INVALID_DECLARATION = "E1004"
    INVALID_TYPE_ANNOTATION = "E1005"
    INVALID_LITERAL = "E1006"
    INVALID_MATCH = "E1007"

    # Resolução
    DUPLICATE_VARIABLE = "E2001"
    IMMUTABLE_ASSIGNMENT = "E2002"
    INVALID_RETURN = "E2003"
    INVALID_THIS = "E2004"
    INVALID_SUPER = "E2005"
    INVALID_INHERITANCE = "E2006"
    FIELD_CONFLICT = "E2007"
    SELF_REFERENCE = "E2008"
    IMMUTABLE_FIELD = "E2009"
    INVALID_LOOP_CONTROL = "E2010"

    # Checker
    SEMANTIC_ERROR = "E3000"
    TYPE_MISMATCH = "E3001"
    ARITY_MISMATCH = "E3002"
    UNDEFINED_NAME = "E3003"
    MISSING_ANNOTATION = "E3004"
    UNKNOWN_TYPE = "E3005"
    NOT_CALLABLE = "E3006"
    INVALID_OPERANDS = "E3007"
    INVALID_LIST = "E3008"
    INVALID_MAP = "E3009"
    INVALID_ITERATION = "E3010"
    GENERIC_INFERENCE = "E3011"
    GENERIC_UNSUPPORTED = "E3012"
    INVALID_CAST = "E3013"
    RESERVED_NAME = "E3014"
    INVALID_OVERRIDE = "E3015"
    MISSING_INITIALIZATION = "E3016"
    INVALID_CHECKER_DECLARATION = "E3017"
    RETURN_PATH = "E3018"
    MATH_ARGUMENT = "E3019"
    TYPE_ARGUMENTS = "E3020"
    INTERPRETER_UNSUPPORTED = "E3021"
    TOOLCHAIN_MISSING = "E3022"
    MATCH_EXHAUSTIVENESS = "E3023"
    UNREACHABLE_MATCH = "E3024"
    ANY_ACCESS = "E3025"
    INVALID_ENTRY_POINT = "E3026"
    DUPLICATE_DECLARATION = "E3027"

    # Backend
    BACKEND_UNSUPPORTED = "E4001"
    BACKEND_INTERNAL = "E4002"
    BACKEND_BUDGET = "E4003"
    NATIVE_TOOLCHAIN = "E4004"

    # Runtime
    RUNTIME_ERROR = "R1000"
    RUNTIME_NOT_CALLABLE = "R1001"
    DIVISION_BY_ZERO = "R1002"
    UNDEFINED_VARIABLE = "R1003"
    UNDEFINED_PROPERTY = "R1004"
    RUNTIME_ARITY = "R1005"
    RUNTIME_OPERANDS = "R1006"
    INDEX_OUT_OF_BOUNDS = "R1007"
    KEY_NOT_FOUND = "R1008"
    RUNTIME_IMMUTABLE = "R1009"
    UNHANDLED_EXCEPTION = "R1010"
    RUNTIME_CAST = "R1011"
    RUNTIME_ITERATION = "R1012"
    FIELD_NOT_INITIALIZED = "R1013"
    INVALID_VALUE = "R1014"
    RUNTIME_STACK_OVERFLOW = "R1015"
    UNHANDLED_RESULT = "R1016"

    # CLI/execução
    CLI_TIMEOUT = "C0001"
    DEPENDENCY_STATE = "C0002"
    SCAFFOLD_STATE = "C0003"
    MANIFEST_EDIT = "C0004"

    # Warnings
    UNUSED_LOCAL = "W1001"
    UNUSED_IMPORT = "W1002"


CODE_PHASE: dict[Code, Phase] = {
    Code.UNEXPECTED_CHARACTER: Phase.LEXER,
    Code.UNTERMINATED_STRING: Phase.LEXER,
    Code.INVALID_ESCAPE: Phase.LEXER,
    Code.INVALID_NUMBER: Phase.LEXER,
    Code.UNTERMINATED_COMMENT: Phase.LEXER,
    Code.UNTERMINATED_INTERPOLATION: Phase.LEXER,
    Code.INVALID_UNICODE_ESCAPE: Phase.LEXER,
    Code.SYNTAX_UNEXPECTED: Phase.PARSER,
    Code.INVALID_ASSIGNMENT_TARGET: Phase.PARSER,
    Code.LIMIT_EXCEEDED: Phase.PARSER,
    Code.INVALID_DECLARATION: Phase.PARSER,
    Code.INVALID_TYPE_ANNOTATION: Phase.PARSER,
    Code.INVALID_LITERAL: Phase.PARSER,
    Code.INVALID_MATCH: Phase.PARSER,
    Code.DUPLICATE_VARIABLE: Phase.RESOLVER,
    Code.IMMUTABLE_ASSIGNMENT: Phase.RESOLVER,
    Code.INVALID_RETURN: Phase.RESOLVER,
    Code.INVALID_THIS: Phase.RESOLVER,
    Code.INVALID_SUPER: Phase.RESOLVER,
    Code.INVALID_INHERITANCE: Phase.RESOLVER,
    Code.FIELD_CONFLICT: Phase.RESOLVER,
    Code.SELF_REFERENCE: Phase.RESOLVER,
    Code.IMMUTABLE_FIELD: Phase.RESOLVER,
    Code.INVALID_LOOP_CONTROL: Phase.RESOLVER,
    Code.SEMANTIC_ERROR: Phase.CHECKER,
    Code.TYPE_MISMATCH: Phase.CHECKER,
    Code.ARITY_MISMATCH: Phase.CHECKER,
    Code.UNDEFINED_NAME: Phase.CHECKER,
    Code.MISSING_ANNOTATION: Phase.CHECKER,
    Code.UNKNOWN_TYPE: Phase.CHECKER,
    Code.NOT_CALLABLE: Phase.CHECKER,
    Code.INVALID_OPERANDS: Phase.CHECKER,
    Code.INVALID_LIST: Phase.CHECKER,
    Code.INVALID_MAP: Phase.CHECKER,
    Code.INVALID_ITERATION: Phase.CHECKER,
    Code.GENERIC_INFERENCE: Phase.CHECKER,
    Code.GENERIC_UNSUPPORTED: Phase.CHECKER,
    Code.INVALID_CAST: Phase.CHECKER,
    Code.RESERVED_NAME: Phase.CHECKER,
    Code.INVALID_OVERRIDE: Phase.CHECKER,
    Code.MISSING_INITIALIZATION: Phase.CHECKER,
    Code.INVALID_CHECKER_DECLARATION: Phase.CHECKER,
    Code.RETURN_PATH: Phase.CHECKER,
    Code.MATH_ARGUMENT: Phase.CHECKER,
    Code.TYPE_ARGUMENTS: Phase.CHECKER,
    Code.INTERPRETER_UNSUPPORTED: Phase.CHECKER,
    Code.TOOLCHAIN_MISSING: Phase.CHECKER,
    Code.MATCH_EXHAUSTIVENESS: Phase.CHECKER,
    Code.UNREACHABLE_MATCH: Phase.CHECKER,
    Code.ANY_ACCESS: Phase.CHECKER,
    Code.INVALID_ENTRY_POINT: Phase.CHECKER,
    Code.DUPLICATE_DECLARATION: Phase.CHECKER,
    Code.BACKEND_UNSUPPORTED: Phase.BACKEND,
    Code.BACKEND_INTERNAL: Phase.BACKEND,
    Code.BACKEND_BUDGET: Phase.BACKEND,
    Code.NATIVE_TOOLCHAIN: Phase.BACKEND,
    Code.RUNTIME_ERROR: Phase.RUNTIME,
    Code.RUNTIME_NOT_CALLABLE: Phase.RUNTIME,
    Code.DIVISION_BY_ZERO: Phase.RUNTIME,
    Code.UNDEFINED_VARIABLE: Phase.RUNTIME,
    Code.UNDEFINED_PROPERTY: Phase.RUNTIME,
    Code.RUNTIME_ARITY: Phase.RUNTIME,
    Code.RUNTIME_OPERANDS: Phase.RUNTIME,
    Code.INDEX_OUT_OF_BOUNDS: Phase.RUNTIME,
    Code.KEY_NOT_FOUND: Phase.RUNTIME,
    Code.RUNTIME_IMMUTABLE: Phase.RUNTIME,
    Code.UNHANDLED_EXCEPTION: Phase.RUNTIME,
    Code.RUNTIME_CAST: Phase.RUNTIME,
    Code.RUNTIME_ITERATION: Phase.RUNTIME,
    Code.FIELD_NOT_INITIALIZED: Phase.RUNTIME,
    Code.INVALID_VALUE: Phase.RUNTIME,
    Code.RUNTIME_STACK_OVERFLOW: Phase.RUNTIME,
    Code.UNHANDLED_RESULT: Phase.RUNTIME,
    Code.CLI_TIMEOUT: Phase.CLI,
    Code.DEPENDENCY_STATE: Phase.CLI,
    Code.SCAFFOLD_STATE: Phase.CLI,
    Code.MANIFEST_EDIT: Phase.CLI,
    Code.UNUSED_LOCAL: Phase.RESOLVER,
    Code.UNUSED_IMPORT: Phase.RESOLVER,
}


# One-line description per code, in catalog order. Source of the table generated
# in `docs/spec/erros.md` (`make codes`); do not edit the table by hand.
CODE_DESCRIPTIONS: dict[Code, str] = {
    Code.UNEXPECTED_CHARACTER: "unexpected character",
    Code.UNTERMINATED_STRING: "unterminated string",
    Code.INVALID_ESCAPE: "invalid string escape",
    Code.INVALID_NUMBER: "invalid numeric literal (separator or literal overflow)",
    Code.UNTERMINATED_COMMENT: "unterminated block comment",
    Code.UNTERMINATED_INTERPOLATION: "unterminated interpolation",
    Code.INVALID_UNICODE_ESCAPE: "invalid Unicode escape",
    Code.SYNTAX_UNEXPECTED: "unexpected token (the `Expect …` family)",
    Code.INVALID_ASSIGNMENT_TARGET: "invalid assignment target (including `?.` in assignments)",
    Code.LIMIT_EXCEEDED: "limit of 255 parameters/arguments",
    Code.INVALID_DECLARATION: "invalid declaration (`val` without initializer, non-constant default, …)",
    Code.INVALID_TYPE_ANNOTATION: "invalid type annotation (`List`/`Map` arity, union in `is`, generic)",
    Code.INVALID_LITERAL: "invalid literal (map at the start of a statement)",
    Code.INVALID_MATCH: "invalid `match`",
    Code.DUPLICATE_VARIABLE: "duplicate variable in scope",
    Code.IMMUTABLE_ASSIGNMENT: "assignment to `val`/immutable parameter",
    Code.INVALID_RETURN: "invalid `return` (top level or value in `init`)",
    Code.INVALID_THIS: "`this` outside a class",
    Code.INVALID_SUPER: "`super` outside a class or without a superclass",
    Code.INVALID_INHERITANCE: "invalid inheritance (class inherits from itself)",
    Code.FIELD_CONFLICT: "field conflict (duplicate or with a method)",
    Code.SELF_REFERENCE: "local read in its own initializer",
    Code.IMMUTABLE_FIELD: "assignment to a `val` field",
    Code.INVALID_LOOP_CONTROL: "`break`/`continue` outside a loop",
    Code.SEMANTIC_ERROR: "reserved generic semantic error (no checker path emits it)",
    Code.TYPE_MISMATCH: "type mismatch",
    Code.ARITY_MISMATCH: "arity (calls, destructuring or pattern binding)",
    Code.UNDEFINED_NAME: "undefined name (variable, property or field)",
    Code.MISSING_ANNOTATION: "missing annotation",
    Code.UNKNOWN_TYPE: "unknown type, class or superclass",
    Code.NOT_CALLABLE: "value is not callable",
    Code.INVALID_OPERANDS: "invalid operands",
    Code.INVALID_LIST: "invalid list (common type, empty element, index)",
    Code.INVALID_MAP: "invalid map (key, common type)",
    Code.INVALID_ITERATION: "invalid iteration",
    Code.GENERIC_INFERENCE: "generic type inference",
    Code.GENERIC_UNSUPPORTED: "generic feature not supported yet",
    Code.INVALID_CAST: "invalid cast",
    Code.RESERVED_NAME: "builtin/reserved name redefined",
    Code.INVALID_OVERRIDE: "override/method conflict",
    Code.MISSING_INITIALIZATION: "field not initialized",
    Code.INVALID_CHECKER_DECLARATION: "invalid declaration (type param, enum, `init`)",
    Code.RETURN_PATH: "missing return on some path",
    Code.MATH_ARGUMENT: "`math.*` argument",
    Code.TYPE_ARGUMENTS: "type arguments (generic/enum/class arity)",
    Code.INTERPRETER_UNSUPPORTED: "not supported by the interpreter",
    Code.TOOLCHAIN_MISSING: "capability requires the Rust toolchain (cargo) at run/build",
    Code.MATCH_EXHAUSTIVENESS: "non-exhaustive match",
    Code.UNREACHABLE_MATCH: "unreachable match arm",
    Code.ANY_ACCESS: "dynamic access on `Any` requires narrowing (`is`/`as`)",
    Code.INVALID_ENTRY_POINT: "entry point `main` signature (parameters, generics, return type)",
    Code.DUPLICATE_DECLARATION: "duplicate top-level declaration (function, class or enum)",
    Code.BACKEND_UNSUPPORTED: "not supported by the backend yet",
    Code.BACKEND_INTERNAL: "backend internal error/verification/link",
    Code.BACKEND_BUDGET: "generic instantiation budget exceeded",
    Code.NATIVE_TOOLCHAIN: "native toolchain unavailable (llvmlite, libgc or cc)",
    Code.RUNTIME_ERROR: "generic runtime error",
    Code.RUNTIME_NOT_CALLABLE: "value is not callable",
    Code.DIVISION_BY_ZERO: "division or modulo by zero",
    Code.UNDEFINED_VARIABLE: "undefined variable",
    Code.UNDEFINED_PROPERTY: "undefined property, field or variant",
    Code.RUNTIME_ARITY: "runtime arity",
    Code.RUNTIME_OPERANDS: "invalid operands or index type",
    Code.INDEX_OUT_OF_BOUNDS: "index out of bounds",
    Code.KEY_NOT_FOUND: "key not found in map",
    Code.RUNTIME_IMMUTABLE: "assignment to immutable binding",
    Code.UNHANDLED_EXCEPTION: "uncaught exception",
    Code.RUNTIME_CAST: "invalid cast",
    Code.RUNTIME_ITERATION: "invalid iteration or mutation during iteration",
    Code.FIELD_NOT_INITIALIZED: "field not initialized",
    Code.INVALID_VALUE: "invalid value (map key, superclass, …)",
    Code.RUNTIME_STACK_OVERFLOW: "call depth above the limit",
    Code.UNHANDLED_RESULT: "unhandled `Err` returned by the entry point",
    Code.CLI_TIMEOUT: "execution timeout exceeded",
    Code.DEPENDENCY_STATE: "lockfile or dependency state (missing, stale, not fetched)",
    Code.SCAFFOLD_STATE: "project scaffolding (existing target, conflict, git)",
    Code.MANIFEST_EDIT: "manifest edit refused (unsupported shape, conflict)",
    Code.UNUSED_LOCAL: "local declared and never read (warning)",
    Code.UNUSED_IMPORT: "import declared and never used (warning)",
}

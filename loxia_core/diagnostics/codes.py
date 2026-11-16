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

    # Backend
    BACKEND_UNSUPPORTED = "E4001"
    BACKEND_INTERNAL = "E4002"

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

    # CLI/execução
    CLI_TIMEOUT = "C0001"

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
    Code.BACKEND_UNSUPPORTED: Phase.BACKEND,
    Code.BACKEND_INTERNAL: Phase.BACKEND,
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
    Code.CLI_TIMEOUT: Phase.CLI,
    Code.UNUSED_LOCAL: Phase.RESOLVER,
    Code.UNUSED_IMPORT: Phase.RESOLVER,
}


# Descrição de uma linha por código, na ordem do catálogo. Fonte da tabela
# gerada em `docs/spec/erros.md` (`make codes`); não edite a tabela à mão.
CODE_DESCRIPTIONS: dict[Code, str] = {
    Code.UNEXPECTED_CHARACTER: "caractere inesperado",
    Code.UNTERMINATED_STRING: "string não terminada",
    Code.INVALID_ESCAPE: "escape de string inválido",
    Code.INVALID_NUMBER: "literal numérico inválido (separador ou overflow de literal)",
    Code.UNTERMINATED_COMMENT: "comentário de bloco não terminado",
    Code.UNTERMINATED_INTERPOLATION: "interpolação não terminada",
    Code.INVALID_UNICODE_ESCAPE: "escape Unicode inválido",
    Code.SYNTAX_UNEXPECTED: "token inesperado (a família `Expect …`)",
    Code.INVALID_ASSIGNMENT_TARGET: "alvo de atribuição inválido (inclui `?.` em atribuição)",
    Code.LIMIT_EXCEEDED: "limite de 255 parâmetros/argumentos",
    Code.INVALID_DECLARATION: "declaração inválida (`val` sem inicializador, default não constante, …)",
    Code.INVALID_TYPE_ANNOTATION: "anotação de tipo inválida (arity de `List`/`Map`, união em `is`, genérico)",
    Code.INVALID_LITERAL: "literal inválido (mapa no início de um statement)",
    Code.INVALID_MATCH: "`match` inválido",
    Code.DUPLICATE_VARIABLE: "variável duplicada no escopo",
    Code.IMMUTABLE_ASSIGNMENT: "atribuição a `val`/parâmetro imutável",
    Code.INVALID_RETURN: "`return` inválido (topo do programa ou valor em `init`)",
    Code.INVALID_THIS: "`this` fora de classe",
    Code.INVALID_SUPER: "`super` fora de classe ou sem superclasse",
    Code.INVALID_INHERITANCE: "herança inválida (classe herda de si)",
    Code.FIELD_CONFLICT: "conflito de campo (duplicado ou com método)",
    Code.SELF_REFERENCE: "leitura de local no próprio inicializador",
    Code.IMMUTABLE_FIELD: "atribuição a campo `val`",
    Code.SEMANTIC_ERROR: "erro semântico genérico (fallback do checker)",
    Code.TYPE_MISMATCH: "tipo incompatível",
    Code.ARITY_MISMATCH: "aridade de chamada",
    Code.UNDEFINED_NAME: "nome indefinido (variável, propriedade ou campo)",
    Code.MISSING_ANNOTATION: "anotação ausente",
    Code.UNKNOWN_TYPE: "tipo, classe ou superclasse desconhecida",
    Code.NOT_CALLABLE: "valor não chamável",
    Code.INVALID_OPERANDS: "operandos inválidos",
    Code.INVALID_LIST: "lista inválida (tipo comum, elemento vazio, índice)",
    Code.INVALID_MAP: "mapa inválido (chave, tipo comum)",
    Code.INVALID_ITERATION: "iteração inválida",
    Code.GENERIC_INFERENCE: "inferência de tipo genérico",
    Code.GENERIC_UNSUPPORTED: "recurso genérico ainda não suportado",
    Code.INVALID_CAST: "cast inválido",
    Code.RESERVED_NAME: "builtin/nome reservado redefinido",
    Code.INVALID_OVERRIDE: "override/conflito de método",
    Code.MISSING_INITIALIZATION: "campo não inicializado",
    Code.INVALID_CHECKER_DECLARATION: "declaração inválida (type param, enum, `init`)",
    Code.RETURN_PATH: "retorno ausente em algum caminho",
    Code.MATH_ARGUMENT: "argumento de `math.*`",
    Code.TYPE_ARGUMENTS: "argumentos de tipo (arity de genérico/enum/classe)",
    Code.BACKEND_UNSUPPORTED: "não suportado pelo backend ainda",
    Code.BACKEND_INTERNAL: "erro interno/verificação/link do backend",
    Code.RUNTIME_ERROR: "erro de runtime genérico",
    Code.RUNTIME_NOT_CALLABLE: "valor não chamável",
    Code.DIVISION_BY_ZERO: "divisão ou módulo por zero",
    Code.UNDEFINED_VARIABLE: "variável indefinida",
    Code.UNDEFINED_PROPERTY: "propriedade, campo ou variante indefinido",
    Code.RUNTIME_ARITY: "aridade em runtime",
    Code.RUNTIME_OPERANDS: "operandos ou índice de tipo inválido",
    Code.INDEX_OUT_OF_BOUNDS: "índice fora dos limites",
    Code.KEY_NOT_FOUND: "chave ausente no mapa",
    Code.RUNTIME_IMMUTABLE: "atribuição a binding imutável",
    Code.UNHANDLED_EXCEPTION: "exceção não capturada",
    Code.RUNTIME_CAST: "cast inválido",
    Code.RUNTIME_ITERATION: "iteração inválida ou mutação durante a iteração",
    Code.FIELD_NOT_INITIALIZED: "campo não inicializado",
    Code.INVALID_VALUE: "valor inválido (chave de mapa, superclasse, …)",
    Code.RUNTIME_STACK_OVERFLOW: "profundidade de chamadas acima do limite",
    Code.CLI_TIMEOUT: "tempo limite de execução excedido",
    Code.UNUSED_LOCAL: "local declarado e nunca lido (warning)",
    Code.UNUSED_IMPORT: "import declarado e nunca usado (warning)",
}

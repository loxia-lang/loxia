from src.token_type import TokenType

KEYWORDS: dict[str, TokenType] = {
    "and": TokenType.AND,
    "class": TokenType.CLASS,
    "elif": TokenType.ELIF,
    "else": TokenType.ELSE,
    "false": TokenType.FALSE,
    "fn": TokenType.FN,
    "for": TokenType.FOR,
    "if": TokenType.IF,
    "in": TokenType.IN,
    "nil": TokenType.NIL,
    "or": TokenType.OR,
    "print": TokenType.PRINT,
    "return": TokenType.RETURN,
    "super": TokenType.SUPER,
    "this": TokenType.THIS,
    "true": TokenType.TRUE,
    "val": TokenType.VAL,
    "var": TokenType.VAR,
    "while": TokenType.WHILE,
}
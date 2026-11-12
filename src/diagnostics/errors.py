from src.frontend.tokens import Token


class ParseError(Exception):
    pass


def immutable_assignment_message(name: str) -> str:
    return f"'{name}' is immutable; declare it with 'var' to allow assignment."


def immutable_redeclare_message(name: str) -> str:
    return f"Can't redeclare immutable variable '{name}'."


class LoxRuntimeError(Exception):
    def __init__(self, token: Token, message: str) -> None:
        super().__init__(message)
        self.token = token
        self.message = message


class NativeError(Exception):
    """Erro de argumento de função nativa.

    A nativa não conhece o token da chamada; o interpretador captura e reemite como
    `LoxRuntimeError` no `(` da chamada.
    """


class ReturnSignal(Exception):
    """Controle de fluxo interno do `return` (o `Return` do livro).

    Não é erro: desempilha até o `call` da função, que captura o valor.
    """

    def __init__(self, keyword: Token, value: object) -> None:
        super().__init__("return")
        self.keyword = keyword
        self.value = value

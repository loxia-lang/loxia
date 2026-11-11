from src.tokens import Token


class ParseError(Exception):
    pass


class LoxRuntimeError(Exception):
    def __init__(self, token: Token, message: str) -> None:
        super().__init__(message)
        self.token = token
        self.message = message


class ReturnSignal(Exception):
    """Controle de fluxo interno do `return` (o `Return` do livro).

    Não é erro: desempilha até o `call` da função, que captura o valor.
    """

    def __init__(self, keyword: Token, value: object) -> None:
        super().__init__("return")
        self.keyword = keyword
        self.value = value

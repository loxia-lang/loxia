from dataclasses import dataclass

from loxia_core.frontend.token_type import TokenType


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    literal: object
    line: int
    # 1-based em code points; `offset` é 0-based em bytes UTF-8 (ADR-0075).
    # Os defaults mantêm compatível quem constrói Token à mão (testes, tokens sintéticos).
    column: int = 1
    offset: int = 0
    # Arquivo de origem (caminho de exibição). Vazio = sintético/desconhecido; o
    # reporter cai no arquivo da execução. É o que permite checker/resolver apontarem
    # o módulo certo depois que o loader devolve a entrada (ADR-0075).
    file: str = ""
    # Doc comment `///` imediatamente antes deste token (normalizada; ADR-0091).
    doc: str | None = None

    def __str__(self) -> str:
        return f"{self.type.name} {self.lexeme} {self.literal}"

    def __repr__(self) -> str:
        return self.__str__()

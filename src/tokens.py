from dataclasses import dataclass

from src.token_type import TokenType


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    literal: object
    line: int

    def __str__(self)-> str:
        return f"{self.type.name} {self.lexeme} {self.literal}"

    def __repr__(self) -> str:
        return self.__str__()
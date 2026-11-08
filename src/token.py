from dataclasses import dataclass

from src.token_type import TokenType


@dataclass(frozen=True)
class Token:

    def __init__(self, type:TokenType, lexeme:str, literal:object, line:int):
        self.type = type
        self.lexeme = lexeme
        self.literal = literal
        self.line = line

    def __str__(self)-> str:
        return f"{self.type.name} {self.lexame} {self.literal}"

    def __repr__(self):
        return self.__str__()
from dataclasses import dataclass


@dataclass(frozen=True)
class LoxRange:
    """Range half-open e lazy: de `start` até `end` (exclusivo), com `step`.

    É um valor reutilizável, não um iterador: cada `for` cria a sua iteração. Não
    materializa elementos, então `0..1_000_000_000` é O(1).
    """

    start: int
    end: int
    step: int = 1

    def __str__(self) -> str:
        if self.step == 1:
            return f"<range {self.start}..{self.end}>"

        return f"<range {self.start}..{self.end} step {self.step}>"

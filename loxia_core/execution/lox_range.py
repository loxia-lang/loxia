from dataclasses import dataclass


@dataclass(frozen=True)
class LoxRange:
    """Range lazy: de `start` até `end` (exclusivo, ou inclusivo com `..=`), com `step`.

    É um valor reutilizável, não um iterador: cada `for` cria a sua iteração. Não
    materializa elementos, então `0..1_000_000_000` é O(1).
    """

    start: int
    end: int
    step: int = 1
    inclusive: bool = False

    def __str__(self) -> str:
        operator = "..=" if self.inclusive else ".."
        if self.step == 1:
            return f"<range {self.start}{operator}{self.end}>"

        return (
            f"<range {self.start}{operator}{self.end} step {self.step}>"
        )

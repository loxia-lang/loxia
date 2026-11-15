"""Compatibilidade: mantém `python main.py`, `from main import Loxia` e o alias `Lox`.

A implementação fica em `loxia.cli`; o pacote também roda com `python -m loxia`.
"""

from loxia.cli import Loxia, main

# Nome antigo do driver: mantido como alias para não quebrar quem importa `Lox`.
Lox = Loxia

__all__ = ["Lox", "Loxia", "main"]


if __name__ == "__main__":
    main()

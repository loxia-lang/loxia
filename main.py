"""Compatibilidade: mantém `python main.py` e `from main import Lox` funcionando.

A implementação fica em `lox.cli`; o pacote também roda com `python -m lox`.
"""

from lox.cli import Lox, main

__all__ = ["Lox", "main"]


if __name__ == "__main__":
    main()

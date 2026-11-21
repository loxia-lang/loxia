# SPDX-License-Identifier: MIT OR Apache-2.0
"""Compatibilidade: mantém `python main.py`, `from main import Loxia` e o alias `Lox`.

A implementação fica em `loxia.engine` (engine) e `loxia.cli` (dispatch); o pacote também
roda com `python -m loxia`.
"""

from loxia.cli import main
from loxia.engine import Loxia

# Nome antigo do driver: mantido como alias para não quebrar quem importa `Lox`.
Lox = Loxia

__all__ = ["Lox", "Loxia", "main"]


if __name__ == "__main__":
    main()

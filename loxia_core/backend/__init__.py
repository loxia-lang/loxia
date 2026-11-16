"""Backend nativo (LLVM) — contrato em [ADR-0031](../../docs/adr/0031-backend-nativo.md).

O backend é opcional: nada aqui é importado no caminho do interpretador, e `llvmlite`
só é exigido quando `--emit` é usado.
"""

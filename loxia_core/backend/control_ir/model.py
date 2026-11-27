# SPDX-License-Identifier: MIT OR Apache-2.0
"""Control-flow model of the backend IR (ADR-0153).

The model is deliberately small: blocks, phi, terminators and a cleanup depth. Values
are opaque handles to the target (``llvmlite`` today); this module never inspects their
type or representation. The only target-aware code lives in ``builder``/``verify``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class ControlIRError(Exception):
    """An internal control-IR invariant was violated (a compiler bug, not a user error)."""


@dataclass(eq=False)
class Phi:
    """A phi node and its incoming edges."""

    name: str
    ty: Any
    llvm: Any
    incoming: list[tuple[Any, Block]] = field(default_factory=list)


@dataclass(eq=False)
class Br:
    """Unconditional branch."""

    target: Block


@dataclass(eq=False)
class CondBr:
    """Conditional branch (two successors)."""

    condition: Any
    then_block: Block
    else_block: Block


@dataclass(eq=False)
class Ret:
    """Return with an optional value."""

    value: Any | None


@dataclass(eq=False)
class Unreachable:
    """A path that does not continue (raise/panic)."""


Terminator = Br | CondBr | Ret | Unreachable


@dataclass(eq=False)
class Block:
    """A basic block: phi nodes, one terminator and the cleanup depth at creation."""

    name: str
    llvm: Any
    function: ControlFunction
    phis: list[Phi] = field(default_factory=list)
    terminator: Terminator | None = None
    cleanup_depth: int = 0

    @property
    def is_terminated(self) -> bool:
        return self.terminator is not None


@dataclass(eq=False)
class ControlFunction:
    """All blocks of one target function, in creation order."""

    name: str
    llvm: Any
    entry: Block | None = None
    blocks: list[Block] = field(default_factory=list)
    block_map: dict[Any, Block] = field(default_factory=dict)
    cleanup_depth: int = 0

    def add_block(self, block: Block) -> Block:
        block.function = self
        self.blocks.append(block)
        self.block_map[block.llvm] = block
        if self.entry is None:
            self.entry = block
        return block

    def block_for(self, llvm_block: Any) -> Block | None:
        return self.block_map.get(llvm_block)

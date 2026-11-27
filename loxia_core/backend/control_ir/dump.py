# SPDX-License-Identifier: MIT OR Apache-2.0
"""Deterministic S-expression dump of the control IR (ADR-0153).

Used by tests and by ``--dump-ir`` only when a debugging surface is added. The dump
contains no addresses or hash-dependent order: blocks, phis and incoming edges are
printed in creation order.
"""

from __future__ import annotations

from typing import Any

from loxia_core.backend.control_ir.model import (
    Br,
    CondBr,
    ControlFunction,
    Phi,
    Ret,
    Unreachable,
)


def _value(value: Any) -> str:
    name = getattr(value, "name", None)
    return str(name) if name else "<value>"


def _phi(phi: Phi) -> str:
    incoming = " ".join(f"({_value(value)} {block.name})" for value, block in phi.incoming)
    return f"(phi {phi.name} {incoming})"


def _terminator(block: Any) -> str:
    terminator = block.terminator
    if isinstance(terminator, Br):
        return f"(br {terminator.target.name})"
    if isinstance(terminator, CondBr):
        return (
            f"(condbr {_value(terminator.condition)} "
            f"{terminator.then_block.name} {terminator.else_block.name})"
        )
    if isinstance(terminator, Ret):
        return "(ret)" if terminator.value is None else f"(ret {_value(terminator.value)})"
    if isinstance(terminator, Unreachable):
        return "(unreachable)"
    return "(missing)"


def dump(function: ControlFunction) -> str:
    lines = [f"(function {function.name}"]
    for block in function.blocks:
        lines.append(f"  (block {block.name} depth={block.cleanup_depth}")
        for phi in block.phis:
            lines.append(f"    {_phi(phi)}")
        lines.append(f"    {_terminator(block)})")
    lines.append(")")
    return "\n".join(lines)


def dump_all(functions: dict[Any, ControlFunction]) -> str:
    return "\n".join(dump(function) for function in functions.values())

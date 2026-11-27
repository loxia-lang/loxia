# SPDX-License-Identifier: MIT OR Apache-2.0
"""Structural verifier for the control IR (ADR-0153, C1-C7)."""

from __future__ import annotations

from typing import Any

from loxia_core.backend.control_ir.model import (
    Block,
    Br,
    CondBr,
    ControlFunction,
    Ret,
)


def _predecessors(function: ControlFunction) -> dict[Block, list[Block]]:
    predecessors: dict[Block, list[Block]] = {block: [] for block in function.blocks}
    for block in function.blocks:
        terminator = block.terminator
        if isinstance(terminator, (Br, CondBr)):
            targets = (
                [terminator.target]
                if isinstance(terminator, Br)
                else [terminator.then_block, terminator.else_block]
            )
            for target in targets:
                predecessors.setdefault(target, []).append(block)
    return predecessors


def _reachable(function: ControlFunction, predecessors: dict[Block, list[Block]]) -> set[Block]:
    if function.entry is None:
        return set()
    seen: set[Block] = set()
    pending = [function.entry]
    while pending:
        block = pending.pop()
        if block in seen:
            continue
        seen.add(block)
        for successor in _successors(block):
            pending.append(successor)
    return seen


def _successors(block: Block) -> list[Block]:
    terminator = block.terminator
    if isinstance(terminator, Br):
        return [terminator.target]
    if isinstance(terminator, CondBr):
        return [terminator.then_block, terminator.else_block]
    return []


def _dominators(
    function: ControlFunction, predecessors: dict[Block, list[Block]], reachable: set[Block]
) -> dict[Block, set[Block]]:
    if function.entry is None:
        return {}
    dominators: dict[Block, set[Block]] = {
        block: (set(reachable) if block is not function.entry else {block}) for block in reachable
    }
    changed = True
    while changed:
        changed = False
        for block in reachable:
            if block is function.entry:
                continue
            incoming = [pred for pred in predecessors.get(block, []) if pred in reachable]
            if not incoming:
                new = {block}
            else:
                new = {block} | set.intersection(*(dominators[pred] for pred in incoming))
            if new != dominators[block]:
                dominators[block] = new
                changed = True
    return dominators


def _used_values(block: Block) -> list[Any]:
    terminator = block.terminator
    if isinstance(terminator, CondBr):
        return [terminator.condition]
    if isinstance(terminator, Ret) and terminator.value is not None:
        return [terminator.value]
    return []


def _defined_in(function: ControlFunction, value: Any) -> Block | None:
    parent = getattr(value, "parent", None)
    if parent is None:
        return None
    return function.block_map.get(parent)


def verify_function(function: ControlFunction) -> list[str]:
    """Return every C1-C7 violation found in ``function`` (empty means valid)."""
    errors: list[str] = []
    label = f"function '{function.name}'"

    if function.entry is None:
        return [f"{label}: no entry block"]

    predecessors = _predecessors(function)
    reachable = _reachable(function, predecessors)
    dominators = _dominators(function, predecessors, reachable)

    # C1 — exactly one terminator, recorded and emitted.
    for block in function.blocks:
        if block.terminator is None:
            errors.append(f"{label}: block '{block.name}' has no terminator (C1)")
        elif not block.llvm.is_terminated:
            errors.append(
                f"{label}: block '{block.name}' records a terminator but the target has none (C1)"
            )

    # C2 — successors belong to the function; the entry has no predecessors.
    for block in function.blocks:
        for successor in _successors(block):
            if successor not in function.blocks:
                errors.append(f"{label}: block '{block.name}' branches outside the function (C2)")
    if predecessors.get(function.entry):
        errors.append(f"{label}: entry block has predecessors (C2)")

    # C3 — phi has one incoming per predecessor, no duplicates.
    for block in function.blocks:
        if block not in reachable:
            continue
        preds = predecessors.get(block, [])
        for phi in block.phis:
            incoming = [source for _, source in phi.incoming]
            if len(incoming) != len(set(incoming)):
                errors.append(
                    f"{label}: phi '{phi.name}' in '{block.name}' has duplicate "
                    "incoming blocks (C3)"
                )
            if set(incoming) != set(preds):
                missing = sorted(p.name for p in set(preds) - set(incoming))
                extra = sorted(p.name for p in set(incoming) - set(preds))
                errors.append(
                    f"{label}: phi '{phi.name}' in '{block.name}' incoming mismatch "
                    f"(missing {missing}, extra {extra}) (C3)"
                )

    # C4/C6 — uses are dominated by their definition and do not cross cleanup outwards.
    for block in function.blocks:
        if block not in reachable:
            continue
        for value in _used_values(block):
            defined = _defined_in(function, value)
            if defined is None:
                continue
            if defined not in dominators.get(block, set()):
                errors.append(
                    f"{label}: value defined in '{defined.name}' does not dominate "
                    f"'{block.name}' (C4)"
                )
            if defined.cleanup_depth > block.cleanup_depth:
                errors.append(
                    f"{label}: value from cleanup depth {defined.cleanup_depth} used at "
                    f"depth {block.cleanup_depth} in '{block.name}' (C6)"
                )
        for phi in block.phis:
            for value, source in phi.incoming:
                if source not in reachable:
                    continue
                defined = _defined_in(function, value)
                if defined is None:
                    continue
                if defined not in dominators.get(source, set()):
                    errors.append(
                        f"{label}: phi '{phi.name}' value defined in '{defined.name}' "
                        f"does not dominate predecessor '{source.name}' (C4)"
                    )
                if defined.cleanup_depth > source.cleanup_depth:
                    errors.append(
                        f"{label}: phi '{phi.name}' value from cleanup depth "
                        f"{defined.cleanup_depth} crosses '{source.name}' at depth "
                        f"{source.cleanup_depth} (C6)"
                    )

    # C5 — the cleanup stack is balanced at the end of the function.
    if function.cleanup_depth != 0:
        errors.append(f"{label}: cleanup stack ends at depth {function.cleanup_depth} (C5)")

    # C7 — labels are unique and deterministic (creation order is the list order).
    names = [block.name for block in function.blocks]
    if len(names) != len(set(names)):
        errors.append(f"{label}: duplicate block labels (C7)")
    for block in function.blocks:
        phi_names = [phi.name for phi in block.phis]
        if len(phi_names) != len(set(phi_names)):
            errors.append(f"{label}: duplicate phi labels in '{block.name}' (C7)")

    return errors

# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unit tests for the backend control IR (ADR-0153, C1-C7)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("llvmlite")

from loxia_core.backend import llvm_ir
from loxia_core.backend.control_ir import (
    Block,
    Br,
    ControlIR,
    ControlIRBuilder,
    ControlIRError,
    Unreachable,
    dump,
    verify_function,
)
from tests.inprocess import run_cli

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.backend


def _function(name: str = "f") -> tuple[ControlIR, Any, Any]:
    module = llvm_ir.new_module("control-ir-test")
    function = llvm_ir.declare(module, name, llvm_ir.int_type(64), [])
    control = ControlIR()
    entry = control.new_block(function, "entry")
    return control, function, entry


def _builder(control: ControlIR, block: Any) -> ControlIRBuilder:
    builder = ControlIRBuilder(llvm_ir.builder(block), control)
    control.observe(builder)
    return builder


def _errors(control: ControlIR, function: Any) -> list[str]:
    return verify_function(control.functions[function])


def test_valid_function_has_no_errors() -> None:
    control, function, entry = _function()
    _builder(control, entry).ret(llvm_ir.constant(llvm_ir.int_type(64), 0))

    assert _errors(control, function) == []


def test_c1_block_without_terminator() -> None:
    control, function, _entry = _function()

    errors = _errors(control, function)

    assert any("(C1)" in error for error in errors)


def test_c2_branch_outside_function() -> None:
    control, function, entry = _function()
    other, _other_function, other_entry = _function("g")
    model = control.functions[function]
    model.block_map[entry].terminator = Br(control.block_for(other_entry))
    _builder(control, other_entry).ret(llvm_ir.constant(llvm_ir.int_type(64), 0))

    errors = _errors(control, function)

    assert any("(C2)" in error for error in errors)
    assert other.functions


def test_c3_phi_with_missing_incoming() -> None:
    control, function, entry = _function()
    left = control.new_block(function, "left")
    right = control.new_block(function, "right")
    end = control.new_block(function, "end")

    condition = llvm_ir.constant(llvm_ir.int_type(1), 1)
    _builder(control, entry).cbranch(condition, left, right)
    _builder(control, left).branch(end)
    _builder(control, right).branch(end)
    end_builder = _builder(control, end)
    phi = end_builder.phi(llvm_ir.int_type(64), "merged")
    phi.add_incoming(llvm_ir.constant(llvm_ir.int_type(64), 1), left)
    end_builder.ret(phi)

    errors = _errors(control, function)

    assert any("(C3)" in error for error in errors)


def test_c4_use_not_dominated_by_definition() -> None:
    control, function, entry = _function()
    left = control.new_block(function, "left")
    right = control.new_block(function, "right")

    condition = llvm_ir.constant(llvm_ir.int_type(1), 1)
    _builder(control, entry).cbranch(condition, left, right)
    right_builder = _builder(control, right)
    value = right_builder.add(
        llvm_ir.constant(llvm_ir.int_type(64), 1),
        llvm_ir.constant(llvm_ir.int_type(64), 2),
    )
    right_builder.ret(value)
    _builder(control, left).ret(value)

    errors = _errors(control, function)

    assert any("(C4)" in error for error in errors)


def test_c5_cleanup_stack_must_end_empty() -> None:
    control, function, entry = _function()
    builder = _builder(control, entry)
    control.push_cleanup()
    builder.ret(llvm_ir.constant(llvm_ir.int_type(64), 0))

    errors = _errors(control, function)

    assert any("(C5)" in error for error in errors)


def test_c6_value_cannot_cross_cleanup_outwards() -> None:
    control, function, entry = _function()
    entry_builder = _builder(control, entry)
    control.push_cleanup()
    deep = control.new_block(function, "deep")
    deep_builder = _builder(control, deep)
    value = deep_builder.add(
        llvm_ir.constant(llvm_ir.int_type(64), 1),
        llvm_ir.constant(llvm_ir.int_type(64), 2),
    )
    control.pop_cleanup()
    shallow = control.new_block(function, "shallow")
    entry_builder.branch(deep)
    deep_builder.branch(shallow)
    _builder(control, shallow).ret(value)

    errors = _errors(control, function)

    assert any("(C6)" in error for error in errors)


def test_c7_duplicate_block_labels() -> None:
    control, function, entry = _function()
    _builder(control, entry).ret(llvm_ir.constant(llvm_ir.int_type(64), 0))
    model = control.functions[function]
    model.blocks.append(Block("entry", entry, model, terminator=Unreachable()))

    errors = _errors(control, function)

    assert any("(C7)" in error for error in errors)


def test_dump_is_deterministic() -> None:
    control, function, entry = _function()
    _builder(control, entry).ret(llvm_ir.constant(llvm_ir.int_type(64), 0))
    model = control.functions[function]

    assert dump(model) == "(function f\n  (block entry depth=0\n    (ret <value>))\n)"


def test_lowering_populates_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[int, int, int]] = []
    original = ControlIR.verify_all

    def wrapped(self: ControlIR) -> None:
        functions = list(self.functions.values())
        seen.append(
            (
                len(functions),
                sum(len(function.blocks) for function in functions),
                sum(len(block.phis) for function in functions for block in function.blocks),
            )
        )
        original(self)

    monkeypatch.setattr(ControlIR, "verify_all", wrapped)
    result = run_cli(
        "--emit",
        "ll",
        str(ROOT / "tests/cases/exceptions.lx"),
        cwd=ROOT,
    )

    assert result.returncode == 0, result.stderr
    assert seen
    assert max(item[0] for item in seen) > 0
    assert max(item[1] for item in seen) > 0
    assert max(item[2] for item in seen) > 0


def test_verify_all_raises_with_context() -> None:
    control, _function_ir, _entry = _function()
    builder = _builder(control, _entry)
    control.push_cleanup()
    builder.ret(llvm_ir.constant(llvm_ir.int_type(64), 0))

    with pytest.raises(ControlIRError, match=r"\(C5\)"):
        control.verify_all()


def test_phi_records_one_incoming_per_predecessor() -> None:
    control, function, entry = _function()
    left = control.new_block(function, "left")
    right = control.new_block(function, "right")
    end = control.new_block(function, "end")

    condition = llvm_ir.constant(llvm_ir.int_type(1), 1)
    _builder(control, entry).cbranch(condition, left, right)
    _builder(control, left).branch(end)
    _builder(control, right).branch(end)
    end_builder = _builder(control, end)
    phi = end_builder.phi(llvm_ir.int_type(64), "merged")
    phi.add_incoming(llvm_ir.constant(llvm_ir.int_type(64), 1), left)
    phi.add_incoming(llvm_ir.constant(llvm_ir.int_type(64), 2), right)
    end_builder.ret(phi)

    record = control.functions[function].blocks[-1].phis[0]

    assert len(record.incoming) == 2
    assert _errors(control, function) == []
    assert "(phi merged" in dump(control.functions[function])

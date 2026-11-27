# SPDX-License-Identifier: MIT OR Apache-2.0
"""Target adapter for the control IR (ADR-0153).

``ControlIR`` records the control graph while ``ControlIRBuilder`` proxies the
``llvmlite`` builder used by the lowering. Control operations are recorded here; all
other instructions are forwarded untouched, so the lowering keeps emitting values
directly and the model stays control-only.
"""

from __future__ import annotations

from typing import Any

from loxia_core.backend import llvm_ir
from loxia_core.backend.control_ir.model import (
    Block,
    Br,
    CondBr,
    ControlFunction,
    ControlIRError,
    Phi,
    Ret,
    Unreachable,
)


class ControlIR:
    """One control graph per target function, built as the lowering runs."""

    def __init__(self) -> None:
        self.functions: dict[Any, ControlFunction] = {}
        self.phis: dict[Any, Phi] = {}
        self.current: Block | None = None

    def reset(self) -> None:
        self.functions.clear()
        self.phis.clear()
        self.current = None

    def observe(self, ir_builder: Any) -> None:
        """Point the tracker at the block of ``ir_builder``."""
        self.current = self.block_for(ir_builder.block)

    def function_for(self, llvm_function: Any) -> ControlFunction:
        function = self.functions.get(llvm_function)
        if function is None:
            function = ControlFunction(llvm_function.name, llvm_function)
            self.functions[llvm_function] = function
        return function

    def block_for(self, llvm_block: Any) -> Block:
        function = self.function_for(llvm_block.function)
        block = function.block_for(llvm_block)
        if block is None:
            block = Block(
                llvm_block.name,
                llvm_block,
                function,
                cleanup_depth=function.cleanup_depth,
            )
            function.add_block(block)
        return block

    def new_block(self, llvm_function: Any, name: str) -> Any:
        """Create a target block, register it and return the target handle."""
        llvm_block = llvm_ir.append_block(llvm_function, name)
        self.block_for(llvm_block)
        return llvm_block

    def _current(self) -> Block:
        if self.current is None:
            raise ControlIRError("control IR has no current block")
        return self.current

    def _target(self, target: Any) -> Block:
        llvm_block = target.llvm if isinstance(target, Block) else target
        return self.block_for(llvm_block)

    def _set_terminator(self, terminator: Any) -> None:
        block = self._current()
        if block.terminator is not None:
            raise ControlIRError(f"block '{block.name}' already has a terminator")
        block.terminator = terminator

    def branch(self, target: Any) -> None:
        self._set_terminator(Br(self._target(target)))

    def cond_branch(self, condition: Any, then_block: Any, else_block: Any) -> None:
        self._set_terminator(CondBr(condition, self._target(then_block), self._target(else_block)))

    def ret(self, value: Any | None) -> None:
        self._set_terminator(Ret(value))

    def ret_void(self) -> None:
        self._set_terminator(Ret(None))

    def unreachable(self) -> None:
        self._set_terminator(Unreachable())

    def register_phi(self, llvm_block: Any, llvm_phi: Any, name: str, ty: Any) -> Phi:
        block = self.block_for(llvm_block)
        phi = Phi(name, ty, llvm_phi)
        block.phis.append(phi)
        self.phis[llvm_phi] = phi
        return phi

    def add_incoming(self, llvm_phi: Any, value: Any, block: Any) -> None:
        phi = self.phis.get(llvm_phi)
        if phi is None:
            raise ControlIRError(f"phi '{llvm_phi.name}' is not registered")
        phi.incoming.append((value, self.block_for(block)))

    def push_cleanup(self) -> None:
        self._current().function.cleanup_depth += 1

    def pop_cleanup(self) -> None:
        function = self._current().function
        function.cleanup_depth -= 1
        if function.cleanup_depth < 0:
            raise ControlIRError(f"cleanup stack underflow in '{function.name}'")

    def unwind_to(self, depth: int) -> None:
        function = self._current().function
        if depth < 0 or depth > function.cleanup_depth:
            raise ControlIRError(
                f"invalid cleanup unwind {function.cleanup_depth} -> {depth} in '{function.name}'"
            )
        function.cleanup_depth = depth

    def verify_all(self) -> None:
        from loxia_core.backend.control_ir.verify import verify_function

        errors: list[str] = []
        for function in self.functions.values():
            errors.extend(verify_function(function))
        if errors:
            raise ControlIRError("\n".join(errors))


class ControlIRBuilder:
    """Proxy over ``llvmlite.ir.IRBuilder`` that records control operations."""

    def __init__(self, inner: Any, control: ControlIR) -> None:
        self._inner = inner
        self._control = control

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        inner = self.__dict__.get("_inner")
        if inner is None:
            raise AttributeError(name)
        return getattr(inner, name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            object.__setattr__(self, name, value)
            return
        setattr(self._inner, name, value)

    @property
    def block(self) -> Any:
        return self._inner.block

    def _sync(self) -> None:
        self._control.observe(self)

    def append_basic_block(self, name: str = "") -> Any:
        raise ControlIRError("create blocks through ControlIR.new_block, not the raw builder")

    def branch(self, target: Any) -> Any:
        self._sync()
        result = self._inner.branch(target.llvm if isinstance(target, Block) else target)
        self._control.branch(target)
        return result

    def cbranch(self, condition: Any, true_block: Any, false_block: Any) -> Any:
        self._sync()
        true_llvm = true_block.llvm if isinstance(true_block, Block) else true_block
        false_llvm = false_block.llvm if isinstance(false_block, Block) else false_block
        result = self._inner.cbranch(condition, true_llvm, false_llvm)
        self._control.cond_branch(condition, true_block, false_block)
        return result

    def ret(self, value: Any | None = None) -> Any:
        self._sync()
        result = self._inner.ret(value) if value is not None else self._inner.ret_void()
        self._control.ret(value)
        return result

    def ret_void(self) -> Any:
        self._sync()
        result = self._inner.ret_void()
        self._control.ret_void()
        return result

    def unreachable(self) -> Any:
        self._sync()
        result = self._inner.unreachable()
        self._control.unreachable()
        return result

    def phi(self, ty: Any, name: str = "") -> Any:
        self._sync()
        llvm_phi = self._inner.phi(ty, name)
        phi = self._control.register_phi(self._inner.block, llvm_phi, llvm_phi.name, ty)
        original = llvm_phi.add_incoming

        def add_incoming(value: Any, block: Any) -> None:
            original(value, block)
            self._control.add_incoming(llvm_phi, value, block)

        llvm_phi.add_incoming = add_incoming
        phi.llvm = llvm_phi
        return llvm_phi

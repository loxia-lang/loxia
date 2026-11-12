"""Camada única sobre o `llvmlite`.

Nenhum outro módulo do backend importa `llvmlite` diretamente: esta é a fronteira da
dependência opcional. Tudo o que sai daqui é `Any` de propósito (a lib não tem tipos);
o resto do backend é tipado e testado pelo mypy strict.

Detalhe da versão 0.50: `llvm.initialize()` agora levanta erro — a inicialização é
automática, mas os alvos nativos continuam precisando de `initialize_native_target()`.
"""

from __future__ import annotations

from typing import Any

import llvmlite.binding as binding
import llvmlite.ir as ir

_machine: Any = None


def _target_machine() -> Any:
    global _machine

    if _machine is None:
        binding.initialize_native_target()
        binding.initialize_native_asmprinter()
        triple = binding.get_process_triple()
        _machine = binding.Target.from_triple(triple).create_target_machine()

    return _machine


def new_module(name: str = "lox") -> Any:
    """Cria o módulo já com triple e datalayout do alvo atual (IR reproduzível)."""
    module = ir.Module(name=name)
    machine = _target_machine()
    module.triple = str(machine.triple)
    module.data_layout = str(machine.target_data)
    return module


def emit_text(module: Any) -> str:
    """IR textual (`.ll`) do módulo, sem passar pelo parser do LLVM."""
    return str(module)


def emit_object(module: Any) -> bytes:
    """Verifica o módulo e devolve o object file do alvo atual."""
    parsed = binding.parse_assembly(str(module))
    parsed.verify()
    return bytes(_target_machine().emit_object(parsed))


def int_type(bits: int) -> Any:
    return ir.IntType(bits)


def float_type() -> Any:
    return ir.DoubleType()


def float_constant(value: float) -> Any:
    return ir.Constant(ir.DoubleType(), float(value))


def void_type() -> Any:
    return ir.VoidType()


def pointer_type() -> Any:
    return ir.IntType(8).as_pointer()


def constant(ty: Any, value: int) -> Any:
    return ir.Constant(ty, value)


def function_type(result: Any, params: list[Any]) -> Any:
    return ir.FunctionType(result, params)


def declare(module: Any, name: str, result: Any, params: list[Any]) -> Any:
    existing = module.globals.get(name)
    if existing is not None:
        return existing
    return ir.Function(module, ir.FunctionType(result, params), name=name)


def declare_noreturn(module: Any, name: str, params: list[Any]) -> Any:
    """Declara `void @name(...)` marcada `noreturn` (o builder continua em código morto)."""
    function = declare(module, name, ir.VoidType(), params)
    function.attributes.add("noreturn")
    return function


def cstring(module: Any, text: str, name: str) -> Any:
    """Global `private unnamed_addr constant [n x i8]` com a string + NUL."""
    data = bytearray(text.encode("utf-8") + b"\0")
    constant = ir.Constant(ir.ArrayType(ir.IntType(8), len(data)), data)
    global_ = ir.GlobalVariable(module, constant.type, name=name)
    global_.initializer = constant
    global_.global_constant = True
    global_.linkage = "private"
    global_.unnamed_addr = True
    return global_


def cstring_pointer(builder: Any, global_: Any) -> Any:
    """`i8*` que aponta para o primeiro byte do global de string."""
    index = ir.Constant(ir.IntType(32), 0)
    return builder.gep(global_, [index, index])


def global_variable(module: Any, name: str, ty: Any) -> Any:
    """Global `internal` inicializada com zero (variáveis de topo)."""
    global_ = ir.GlobalVariable(module, ty, name=name)
    global_.initializer = ir.Constant(ty, None)
    global_.linkage = "internal"
    return global_


def define_main(module: Any) -> Any:
    return ir.Function(module, ir.FunctionType(ir.IntType(32), []), name="main")


def builder(block: Any) -> Any:
    return ir.IRBuilder(block)


def append_block(function: Any, name: str) -> Any:
    return function.append_basic_block(name)


def block_of(function: Any, name: str = "entry") -> Any:
    return function.append_basic_block(name)

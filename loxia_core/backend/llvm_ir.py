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


class LLVMVerificationError(Exception):
    """O módulo gerado pelo backend não passou no verificador do LLVM."""


def _target_machine() -> Any:
    global _machine

    if _machine is None:
        binding.initialize_native_target()
        binding.initialize_native_asmprinter()
        triple = binding.get_process_triple()
        _machine = binding.Target.from_triple(triple).create_target_machine()

    return _machine


def _parse(text: str) -> Any:
    try:
        return binding.parse_assembly(text)
    except RuntimeError as error:
        raise LLVMVerificationError(str(error)) from error


def _verify_parsed(parsed: Any) -> None:
    try:
        parsed.verify()
    except RuntimeError as error:
        raise LLVMVerificationError(str(error)) from error


def verify_text(text: str) -> None:
    """Verifica IR textual; levanta `LLVMVerificationError` se for inválido."""
    _verify_parsed(_parse(text))


def verify(module: Any) -> None:
    """Verifica o módulo antes de qualquer emissão (`mod.verify()`)."""
    verify_text(str(module))


def new_module(name: str = "lox") -> Any:
    """Cria o módulo já com triple e datalayout do alvo atual (IR reproduzível)."""
    module = ir.Module(name=name)
    machine = _target_machine()
    module.triple = str(machine.triple)
    module.data_layout = str(machine.target_data)
    return module


def emit_text(module: Any) -> str:
    """IR textual (`.ll`) do módulo, verificado antes de sair."""
    text = str(module)
    verify_text(text)
    return text


def emit_object(module: Any) -> bytes:
    """Verifica, otimiza (-O2) e devolve o object file do alvo atual."""
    parsed = _parse(str(module))
    _verify_parsed(parsed)
    _optimize(parsed)
    return bytes(_target_machine().emit_object(parsed))


def _optimize(parsed: Any) -> None:
    """Pipeline de otimização de módulo correspondente ao `-O2` do backend.

    O `llvmlite` já usa `opt=2` no codegen, mas não roda passes de IR. Estes são os
    passes conservadores que importam para o código gerado (SSA de slots, inlining,
    dobramento e DCE) e mantêm `setjmp`/`longjmp` intactos.
    """
    pass_builder = binding.PassBuilder(
        _target_machine(), binding.PipelineTuningOptions(2)
    )
    manager = binding.ModulePassManager()
    manager.add_global_opt_pass()
    manager.add_ipsccp_pass()
    manager.add_dead_arg_elimination_pass()
    manager.add_always_inliner_pass()
    manager.add_instruction_combine_pass()
    manager.add_reassociate_pass()
    manager.add_new_gvn_pass()
    manager.add_sroa_pass()
    manager.add_simplify_cfg_pass()
    manager.add_aggressive_dce_pass()
    manager.add_loop_simplify_pass()
    manager.add_loop_strength_reduce_pass()
    manager.add_loop_deletion_pass()
    manager.add_sinking_pass()
    manager.run(parsed, pass_builder)


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


def zero_value(ty: Any) -> Any:
    """`zeroinitializer` para structs/agregados (usado por `T?` escalar)."""
    return ir.Constant(ty, None)


def function_type(result: Any, params: list[Any]) -> Any:
    return ir.FunctionType(result, params)


def function_pointer(result: Any, params: list[Any]) -> Any:
    """Ponteiro para função com esta assinatura (usado no `fnptr` da closure)."""
    return ir.FunctionType(result, params).as_pointer()


def literal_struct(fields: list[Any]) -> Any:
    return ir.LiteralStructType(fields)


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


_STRING_STRUCT = ir.LiteralStructType(
    [
        ir.IntType(64),
        ir.IntType(64),
        ir.IntType(8).as_pointer(),
        ir.IntType(8).as_pointer(),
    ]
)


def string_literal(module: Any, value: str, index: int) -> Any:
    """Global de `LoxStr` constante: header + bytes UTF-8 + NUL."""
    encoded = value.encode("utf-8")
    data = bytearray(encoded + b"\0")
    array = ir.Constant(ir.ArrayType(ir.IntType(8), len(data)), data)

    data_global = ir.GlobalVariable(module, array.type, name=f"str.data.{index}")
    data_global.initializer = array
    data_global.global_constant = True
    data_global.linkage = "private"
    data_global.unnamed_addr = True

    i64 = ir.IntType(64)
    header = ir.Constant(
        _STRING_STRUCT,
        [
            i64(len(encoded)),
            i64(len(value)),
            data_global,
            ir.Constant(ir.IntType(8).as_pointer(), None),
        ],
    )
    # Não é `constant`: o header tem relocação e em .rodata geraria DT_TEXTREL.
    struct_global = ir.GlobalVariable(module, _STRING_STRUCT, name=f"str.{index}")
    struct_global.initializer = header
    struct_global.linkage = "private"
    struct_global.unnamed_addr = True
    return struct_global


def null_pointer() -> Any:
    return ir.Constant(ir.IntType(8).as_pointer(), None)


def global_variable(module: Any, name: str, ty: Any) -> Any:
    """Global `internal` inicializada com zero (variáveis de topo)."""
    global_ = ir.GlobalVariable(module, ty, name=name)
    global_.initializer = ir.Constant(ty, None)
    global_.linkage = "internal"
    return global_


def extern_global(module: Any, name: str, ty: Any) -> Any:
    """Declaração de global externo, definido pelo runtime C (sem inicializador)."""
    return ir.GlobalVariable(module, ty, name=name)


def pointer_pointer() -> Any:
    return ir.IntType(8).as_pointer().as_pointer()


def define_main(module: Any) -> Any:
    return ir.Function(
        module,
        ir.FunctionType(ir.IntType(32), [ir.IntType(32), pointer_pointer()]),
        name="main",
    )


def builder(block: Any) -> Any:
    return ir.IRBuilder(block)


def append_block(function: Any, name: str) -> Any:
    return function.append_basic_block(name)


def block_of(function: Any, name: str = "entry") -> Any:
    return function.append_basic_block(name)

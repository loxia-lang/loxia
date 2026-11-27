# SPDX-License-Identifier: MIT OR Apache-2.0
"""Os erros que o `run` bloqueia continuam exercitando o interpretador (I1).

O check do `run` (ADR-0142) recusa estes programas antes de executar; o
interpretador é a especificação executável, então os caminhos de erro de
runtime continuam testados com o seam `check_on_run=False` e com a mensagem
`Rxxxx` que o corpus esperava antes da migração.
"""

from __future__ import annotations

import pytest

from loxia.engine import Loxia
from tests.runner import CASES_DIR

INTERPRETER_ERRORS: dict[str, str] = {
    "errors/builtin_redeclare.lx": "Can't redeclare immutable variable 'len'.",
    "errors/field_immutable.lx": "Can't assign to immutable field 'x'.",
    "errors/field_uninitialized.lx": "Field 'x' must be initialized.",
    "errors/field_unknown.lx": "Undefined field 'y'.",
    "errors/for_in_not_iterable.lx": "Can only iterate over a range, a list, a map or a string.",
    "errors/list_index_type.lx": "List index must be an integer.",
    "errors/list_len_type.lx": "len() expects a string, a list or a map.",
    "errors/list_not_indexable.lx": "Only lists and maps can be indexed.",
    "errors/list_unknown_method.lx": "Undefined property 'foo'.",
    "errors/map_key_type.lx": "Map keys must be strings, integers or booleans.",
    "errors/match_invalid_scrutinee.lx": (
        "match requires an enum, Int, String, Bool or nil value."
    ),
    "errors/nested_destructure_arity.lx": "Destructuring expects 2 values, found 3.",
    "errors/nested_destructure_non_tuple.lx": "Can only destructure a tuple.",
    "errors/not_callable.lx": "Can only call functions and classes.",
    "errors/only_instances_have_fields.lx": "Only instances have fields.",
    "errors/only_instances_have_properties.lx": "Only instances have properties.",
    "errors/optional_not_instance.lx": "Only instances have properties.",
    "errors/range_args_type.lx": "range() arguments must be integers.",
    "errors/range_bounds.lx": "Range bounds must be integers.",
    "errors/super_undefined_method.lx": "Undefined property 'nope'.",
    "errors/superclass_not_class.lx": "Superclass must be a class.",
    "errors/undefined_property.lx": "Undefined property 'bar'.",
}


@pytest.mark.parametrize(("relative", "message"), INTERPRETER_ERRORS.items())
def test_interpreter_still_raises_the_runtime_error(
    relative: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    path = CASES_DIR / relative
    lox = Loxia(check_on_run=False)
    lox.use_file(relative, module_root=path.resolve().parent)

    lox.run(path.read_text(encoding="utf-8"))

    captured = capsys.readouterr()
    assert message in captured.err, captured.err
    assert lox.reporter.had_runtime_error is True

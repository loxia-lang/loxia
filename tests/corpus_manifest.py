"""Manifesto do corpus diferencial por nível (ADR-0031, decisão 11).

Um caso só entra aqui quando o backend do nível o compila **e** reproduz stdout, stderr
e exit code do interpretador. A promoção é monotônica: caso que passou não sai do
manifesto sem quebrar o build.

Níveis novos entram como chaves novas; uma chave de nível nunca encolhe.
"""

from __future__ import annotations

LEVELS: dict[str, tuple[str, ...]] = {
    "l0": (
        "tests/cases/comments.lox",
        "tests/cases/comparison.lox",
        "tests/cases/int_division.lox",
        "tests/cases/unary.lox",
    ),
    "l1": (
        "tests/cases/arithmetic.lox",
        "tests/cases/numbers.lox",
        "tests/cases/precedence.lox",
    ),
    "l3": (
        "tests/cases/arguments_order.lox",
        "tests/cases/block_scope.lox",
        "tests/cases/elif.lox",
        "tests/cases/equality.lox",
        "tests/cases/if_else.lox",
        "tests/cases/interpolation_scalars.lox",
        "tests/cases/literals.lox",
        "tests/cases/scope_identity.lox",
        "tests/cases/string_escapes.lox",
        "tests/cases/string_order.lox",
        "tests/cases/strings.lox",
        "tests/cases/val_shadowing.lox",
    ),
    "l2.5": (
        "tests/cases/optional_functions.lox",
        "tests/cases/optional_scalars.lox",
        "tests/cases/variables.lox",
    ),
    "l6": (
        "tests/cases/any_box.lox",
        "tests/cases/any_casts.lox",
        "tests/cases/bitwise.lox",
        "tests/cases/casts_math.lox",
        "tests/cases/bitwise_precedence.lox",
        "tests/cases/exponentiation.lox",
        "tests/cases/for_in.lox",
        "tests/cases/list_cycle.lox",
        "tests/cases/list_equality.lox",
        "tests/cases/list_index.lox",
        "tests/cases/list_iteration.lox",
        "tests/cases/list_literal.lox",
        "tests/cases/list_methods.lox",
        "tests/cases/list_stringify.lox",
        "tests/cases/map_cycle.lox",
        "tests/cases/map_equality.lox",
        "tests/cases/map_iteration.lox",
        "tests/cases/map_keys.lox",
        "tests/cases/map_literal.lox",
        "tests/cases/map_methods.lox",
        "tests/cases/map_stringify.lox",
        "tests/cases/interpolation.lox",
        "tests/cases/str_repr.lox",
        "tests/cases/string_chars.lox",
        "tests/cases/tuple_destructure.lox",
        "tests/cases/tuples.lox",
        "tests/cases/nil_aware.lox",
        "tests/cases/one_line_block.lox",
        "tests/cases/optional_semicolons.lox",
        "tests/cases/range_value.lox",
    ),
    "t7": (
        "tests/cases/generic_class.lox",
        "tests/cases/generic_functions.lox",
    ),
    "l5": (
        "tests/cases/class_bound_method.lox",
        "tests/cases/class_fields.lox",
        "tests/cases/class_identity.lox",
        "tests/cases/class_identity_as.lox",
        "tests/cases/class_initializer.lox",
        "tests/cases/class_str_print.lox",
        "tests/cases/class_this.lox",
        "tests/cases/class_uninitialized_read.lox",
        "tests/cases/class_val_twice.lox",
        "tests/cases/classes.lox",
        "tests/cases/default_params.lox",
        "tests/cases/fields_inheritance.lox",
        "tests/cases/fields_val_var.lox",
        "tests/cases/inheritance.lox",
        "tests/cases/local_class_capture.lox",
        "tests/cases/local_class_fields.lox",
        "tests/cases/inheritance_init.lox",
        "tests/cases/inheritance_override.lox",
        "tests/cases/inheritance_super_init.lox",
        "tests/cases/optional_receiver.lox",
        "tests/cases/optional_refs.lox",
        "tests/cases/super.lox",
        "tests/cases/super_with_this.lox",
        "tests/cases/typed_functions.lox",
    ),
    "l4": (
        "tests/cases/closure_reassign.lox",
        "tests/cases/closure_static_scope.lox",
        "tests/cases/closures.lox",
        "tests/cases/function_values.lox",
        "tests/cases/functions.lox",
        "tests/cases/lambda_closures.lox",
        "tests/cases/local_function.lox",
    ),
    "l2": (
        "tests/cases/assignment.lox",
        "tests/cases/builtin_shadow_local.lox",
        "tests/cases/for.lox",
        "tests/cases/logical.lox",
        "tests/cases/operator_line.lox",
        "tests/cases/recursion.lox",
        "tests/cases/return_in_loop.lox",
        "tests/cases/return_newline.lox",
        "tests/cases/same_line_semicolon.lox",
        "tests/cases/ternary.lox",
        "tests/cases/val_params.lox",
        "tests/cases/val_var.lox",
        "tests/cases/var_redeclare.lox",
        "tests/cases/while.lox",
    ),
}


PENDING: dict[str, str] = {
    # Check-clean, mas o backend ainda recusa (exit 65). O nível é a expectativa,
    # não uma promessa: o teste diferencial só roda o que está em LEVELS.
    "tests/cases/defaults_as_value.lox": "l?",
    "tests/cases/enums.lox": "l6",
    "tests/cases/exceptions.lox": "l6",
    "tests/cases/for_in_capture.lox": "l6",
    "tests/cases/generic_lambda_value.lox": "l6",
    "tests/cases/generics.lox": "l6",
    "tests/cases/result.lox": "l6",
    "tests/cases/tuple_iteration.lox": "l6",
    "tests/cases/var_uninitialized_int.lox": "l6",
}

NEGATIVE: frozenset[str] = frozenset(
    {
        # Casos que existem para provar erro de sintaxe: `--check` deve falhar.
        "tests/cases/reserved_async.lox",
        "tests/cases/reserved_await.lox",
    }
)


def all_cases() -> list[tuple[str, str]]:
    """Pares (nível, caminho) para o teste diferencial do manifesto."""
    return [
        (level, case) for level, cases in LEVELS.items() for case in cases
    ]

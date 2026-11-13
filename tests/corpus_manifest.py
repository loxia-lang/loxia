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
        "tests/cases/inheritance_init.lox",
        "tests/cases/inheritance_override.lox",
        "tests/cases/inheritance_super_init.lox",
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
    "tests/cases/bitwise.lox": "l?",
    "tests/cases/bitwise_precedence.lox": "l?",
    "tests/cases/casts_math.lox": "l?",
    "tests/cases/defaults_as_value.lox": "l?",
    "tests/cases/enums.lox": "l6",
    "tests/cases/exceptions.lox": "l6",
    "tests/cases/exponentiation.lox": "l?",
    "tests/cases/for_in.lox": "l6",
    "tests/cases/for_in_capture.lox": "l6",
    "tests/cases/generic_class.lox": "l6",
    "tests/cases/generic_lambda_value.lox": "l6",
    "tests/cases/generics.lox": "l6",
    "tests/cases/interpolation.lox": "l6",
    "tests/cases/list_cycle.lox": "l6",
    "tests/cases/list_equality.lox": "l6",
    "tests/cases/list_index.lox": "l6",
    "tests/cases/list_iteration.lox": "l6",
    "tests/cases/list_literal.lox": "l6",
    "tests/cases/list_methods.lox": "l6",
    "tests/cases/list_stringify.lox": "l6",
    "tests/cases/map_cycle.lox": "l6",
    "tests/cases/map_equality.lox": "l6",
    "tests/cases/map_iteration.lox": "l6",
    "tests/cases/map_keys.lox": "l6",
    "tests/cases/map_literal.lox": "l6",
    "tests/cases/map_methods.lox": "l6",
    "tests/cases/map_stringify.lox": "l6",
    "tests/cases/nil_aware.lox": "l6",
    "tests/cases/one_line_block.lox": "l6",
    "tests/cases/optional_semicolons.lox": "l6",
    "tests/cases/range_value.lox": "l6",
    "tests/cases/result.lox": "l6",
    "tests/cases/str_repr.lox": "l6",
    "tests/cases/string_chars.lox": "l?",
    "tests/cases/tuple_destructure.lox": "l6",
    "tests/cases/tuple_iteration.lox": "l6",
    "tests/cases/var_uninitialized_int.lox": "l6",
    "tests/cases/tuples.lox": "l6",
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

"""Manifesto do corpus diferencial por nível (ADR-0031, decisão 11).

Um caso só entra aqui quando o backend do nível o compila **e** reproduz stdout, stderr
e exit code do interpretador. A promoção é monotônica: caso que passou não sai do
manifesto sem quebrar o build.

Níveis novos entram como chaves novas; uma chave de nível nunca encolhe.
"""

from __future__ import annotations

LEVELS: dict[str, tuple[str, ...]] = {
    "l0": (
        "tests/cases/comments.lx",
        "tests/cases/comparison.lx",
        "tests/cases/int_division.lx",
        "tests/cases/unary.lx",
    ),
    "l1": (
        "tests/cases/arithmetic.lx",
        "tests/cases/numbers.lx",
        "tests/cases/precedence.lx",
    ),
    "l3": (
        "tests/cases/arguments_order.lx",
        "tests/cases/block_scope.lx",
        "tests/cases/elif.lx",
        "tests/cases/equality.lx",
        "tests/cases/if_else.lx",
        "tests/cases/interpolation_scalars.lx",
        "tests/cases/literals.lx",
        "tests/cases/scope_identity.lx",
        "tests/cases/string_escapes.lx",
        "tests/cases/multiline_strings.lx",
        "tests/cases/raw_strings.lx",
        "tests/cases/string_order.lx",
        "tests/cases/strings.lx",
        "tests/cases/val_shadowing.lx",
    ),
    "l2.5": (
        "tests/cases/optional_functions.lx",
        "tests/cases/optional_scalars.lx",
        "tests/cases/variables.lx",
    ),
    "l6": (
        "tests/cases/any_box.lx",
        "tests/cases/any_casts.lx",
        "tests/cases/bitwise.lx",
        "tests/cases/for_in_capture.lx",
        "tests/cases/char_code_at_bounds.lx",
        "tests/cases/map_equality_depth.lx",
        "tests/cases/try_return_cleanup.lx",
        "tests/cases/generics.lx",
        "tests/cases/interfaces.lx",
        "tests/cases/interface_decl.lx",
        "tests/cases/tuple_iteration.lx",
        "tests/cases/var_uninitialized_int.lx",
        "tests/cases/defaults_as_value.lx",
        "tests/cases/casts_math.lx",
        "tests/cases/bitwise_precedence.lx",
        "tests/cases/exponentiation.lx",
        "tests/cases/enums.lx",
        "tests/cases/exceptions.lx",
        "tests/cases/stack_overflow_caught.lx",
        "tests/cases/stack_overflow_finally.lx",
        "tests/cases/stack_exception.lx",
        "tests/cases/stack_exception_user.lx",
        "tests/cases/for_in.lx",
        "tests/cases/user_iterator.lx",
        "tests/cases/variadic.lx",
        "tests/cases/type_alias.lx",
        "tests/cases/print_function.lx",
        "tests/cases/is_union_parens.lx",
        "tests/cases/generic_lambda_value.lx",
        "tests/cases/result.lx",
        "tests/cases/list_cycle.lx",
        "tests/cases/list_equality.lx",
        "tests/cases/list_index.lx",
        "tests/cases/list_iteration.lx",
        "tests/cases/list_literal.lx",
        "tests/cases/list_methods.lx",
        "tests/cases/list_stringify.lx",
        "tests/cases/map_cycle.lx",
        "tests/cases/map_equality.lx",
        "tests/cases/math_optional.lx",
        "tests/cases/map_iteration.lx",
        "tests/cases/map_key_any_error.lx",
        "tests/cases/map_keys.lx",
        "tests/cases/map_literal.lx",
        "tests/cases/map_methods.lx",
        "tests/cases/map_stringify.lx",
        "tests/cases/interpolation.lx",
        "tests/cases/str_repr.lx",
        "tests/cases/string_chars.lx",
        "tests/cases/tuple_destructure.lx",
        "tests/cases/nested_destructure.lx",
        "tests/cases/tuples.lx",
        "tests/cases/nil_aware.lx",
        "tests/cases/one_line_block.lx",
        "tests/cases/optional_semicolons.lx",
        "tests/cases/range_inclusive.lx",
        "tests/cases/range_value.lx",
        "tests/cases/leading_operator_brackets.lx",
    ),
    "t7": (
        "tests/cases/generic_class.lx",
        "tests/cases/generic_constraints.lx",
        "tests/cases/generic_functions.lx",
    ),
    "l5": (
        "tests/cases/class_bound_method.lx",
        "tests/cases/class_fields.lx",
        "tests/cases/class_identity.lx",
        "tests/cases/class_identity_as.lx",
        "tests/cases/class_initializer.lx",
        "tests/cases/class_self_return.lx",
        "tests/cases/class_str_print.lx",
        "tests/cases/class_this.lx",
        "tests/cases/class_uninitialized_read.lx",
        "tests/cases/class_val_twice.lx",
        "tests/cases/classes.lx",
        "tests/cases/default_params.lx",
        "tests/cases/fields_inheritance.lx",
        "tests/cases/fields_val_var.lx",
        "tests/cases/inheritance.lx",
        "tests/cases/local_class_capture.lx",
        "tests/cases/local_class_fields.lx",
        "tests/cases/inheritance_init.lx",
        "tests/cases/inheritance_override.lx",
        "tests/cases/inheritance_super_init.lx",
        "tests/cases/optional_receiver.lx",
        "tests/cases/optional_refs.lx",
        "tests/cases/super.lx",
        "tests/cases/super_with_this.lx",
        "tests/cases/typed_functions.lx",
        "tests/cases/method_fn_keyword.lx",
        "tests/cases/stack_methods.lx",
        "tests/cases/stack_ctor.lx",
    ),
    "l4": (
        "tests/cases/closure_in_list.lx",
        "tests/cases/closure_reassign.lx",
        "tests/cases/closure_static_scope.lx",
        "tests/cases/closures.lx",
        "tests/cases/function_values.lx",
        "tests/cases/functions.lx",
        "tests/cases/lambda_closures.lx",
        "tests/cases/local_function.lx",
        "tests/cases/stack_depth_ok.lx",
        "tests/cases/stack_overflow.lx",
        "tests/cases/stack_trace.lx",
        "tests/cases/stack_trace_cap.lx",
    ),
    "t1": (
        "tests/cases/std_asserts.lx",
        "tests/cases/std_lists.lx",
        "tests/cases/std_maps.lx",
        "tests/cases/std_numeric.lx",
        "tests/cases/std_results.lx",
        "tests/cases/std_strings.lx",
    ),
    "t2": (
        "tests/cases/std_cli.lx",
        "tests/cases/std_convert.lx",
        "tests/cases/std_csv.lx",
        "tests/cases/std_fmt.lx",
        "tests/cases/std_iter.lx",
        "tests/cases/std_json.lx",
        "tests/cases/std_paths.lx",
        "tests/cases/std_sets.lx",
        "tests/cases/std_utf8.lx",
    ),
    "t3": (
        "tests/cases/std_test.lx",
        "tests/cases/std_test_hooks.lx",
    ),
    "k0": (
        "tests/cases/kernel_io.lx",
        "tests/cases/kernel_strings.lx",
    ),
    "l2": (
        "tests/cases/assignment.lx",
        "tests/cases/builtin_shadow_local.lx",
        "tests/cases/for.lx",
        "tests/cases/logical.lx",
        "tests/cases/operator_line.lx",
        "tests/cases/recursion.lx",
        "tests/cases/return_in_loop.lx",
        "tests/cases/return_newline.lx",
        "tests/cases/same_line_semicolon.lx",
        "tests/cases/ternary.lx",
        "tests/cases/val_params.lx",
        "tests/cases/val_var.lx",
        "tests/cases/var_redeclare.lx",
        "tests/cases/while.lx",
    ),
}


PENDING: dict[str, str] = {
    # Check-clean, mas o backend ainda recusa (exit 65). O nível é a expectativa,
    # não uma promessa: o teste diferencial só roda o que está em LEVELS.
}

NEGATIVE: frozenset[str] = frozenset(
    {
        # Casos que existem para provar erro de sintaxe: `--check` deve falhar.
        "tests/cases/reserved_async.lx",
        "tests/cases/reserved_await.lx",
        "tests/cases/division_comment_hint.lx",
        "tests/cases/is_union_needs_parens.lx",
        "tests/cases/map_at_statement_start.lx",
        "tests/cases/bang_removed.lx",
    }
)


def all_cases() -> list[tuple[str, str]]:
    """Pares (nível, caminho) para o teste diferencial do manifesto."""
    return [
        (level, case) for level, cases in LEVELS.items() for case in cases
    ]

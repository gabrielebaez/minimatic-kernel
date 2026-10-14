from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol


def _list(*items):
    return Expression(Symbol("List"), *items)


def test_replace_all_on_matching_literal(kernel):
    assert kernel.eval('"N/A" /. "N/A" -> 0') == 0


def test_replace_all_no_match_returns_unchanged(kernel):
    assert kernel.eval('"keep" /. "N/A" -> 0') == "keep"


def test_replace_all_recurses_into_list_elements(kernel):
    result = kernel.eval('[1, 2, 3, 4] /. x: _ -> x ^ 2')
    assert result == _list(1, 4, 9, 16)


def test_replace_all_with_rule_list(kernel):
    result = kernel.eval('[1, "N/A", 2] /. ["N/A" -> 0, 1 -> 100]')
    assert result == _list(100, 0, 2)


def test_rule_may_be_held_in_a_variable(kernel):
    """`ReplaceAll` is HoldRest, so a computed rule arrives as an
    unevaluated symbol and has to be resolved at evaluation time."""
    kernel.eval('r = "N/A" -> 0')
    assert kernel.eval('[1, "N/A"] /. r') == _list(1, 0)


def test_rule_list_may_be_held_in_a_variable(kernel):
    kernel.eval('rs = ["N/A" -> 0, 1 -> 100]')
    assert kernel.eval('[1, "N/A", 2] /. rs') == _list(100, 0, 2)


def test_rule_list_may_mix_written_and_computed_rules(kernel):
    kernel.eval('r = "N/A" -> 0')
    assert kernel.eval('[1, "N/A", 2] /. [r, 1 -> 100]') == _list(100, 0, 2)


def test_pattern_lhs_survives_being_bound_to_a_name(kernel):
    """Binding a rule to a name must not evaluate its pattern LHS — `Rule`
    is HoldAll precisely so `x: _` reaches the matcher as a pattern."""
    kernel.eval("r = x: _int -> x * 2")
    assert kernel.eval("[1, 2, 3] /. r") == _list(2, 4, 6)


def test_non_rule_in_rule_position_is_a_runtime_error(kernel):
    from minimatic.errors import MinimaticTypeError
    import pytest

    with pytest.raises(MinimaticTypeError):
        kernel.eval("[1, 2] /. 5")


def test_replace_repeated_fixpoint_uses_value_identity(kernel):
    """`[1]` -> `[True]` is a change, not a fixpoint: under Python `==`
    the two lists compare equal and `//.` would hand back `[1]`."""
    assert kernel.eval("[1] //. 1 -> True") == _list(True)

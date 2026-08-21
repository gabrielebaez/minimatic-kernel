"""The `Dict` head layer, end to end through the kernel.

tests/test_dict_ops.py covers canonical keys in isolation; this covers the
heads built on them, and the interactions a Dict has with everything else
by virtue of being an ordinary Expression.
"""

import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol
from minimatic.errors import MinimaticTypeError


def _dict(*pairs):
    return Expression(
        Symbol("Dict"), *(Expression(Symbol("Rule"), k, v) for k, v in pairs)
    )


def _list(*items):
    return Expression(Symbol("List"), *items)


# -- construction ------------------------------------------------------------


def test_literal_builds_a_canonical_dict(kernel):
    assert kernel.eval('{ "b" -> 2, "a" -> 1 }') == _dict(("a", 1), ("b", 2))


def test_literal_is_order_insensitive(kernel):
    assert kernel.eval('{ "b" -> 2, "a" -> 1 }') == kernel.eval('{ "a" -> 1, "b" -> 2 }')


def test_empty_literal(kernel):
    assert kernel.eval("{}") == _dict()


def test_literal_evaluates_its_keys_and_values(kernel):
    """`Rule` is HoldAll so a literal's entries arrive unevaluated; `Dict`
    is what forces them."""
    assert kernel.eval('{ "a" -> 1 + 1 }') == _dict(("a", 2))
    kernel.eval("k = 5")
    assert kernel.eval("{ k -> 1 }") == _dict((5, 1))


def test_duplicate_keys_resolve_last_wins(kernel):
    assert kernel.eval('{ "a" -> 1, "a" -> 2 }') == _dict(("a", 2))


def test_a_delayed_entry_is_refused(kernel):
    # `{ "a" :> 1 }` parses, but a dict entry is not a rewrite rule.
    with pytest.raises(MinimaticTypeError):
        kernel.eval('{ "a" :> 1 }')


def test_a_non_rule_entry_is_refused(kernel):
    with pytest.raises(MinimaticTypeError):
        kernel.eval("Dict(1, 2)")


# -- accessors ---------------------------------------------------------------


def test_keys_values_length(kernel):
    kernel.eval('d = { "b" -> 2, "a" -> 1 }')
    assert kernel.eval("keys(d)") == _list("a", "b")
    assert kernel.eval("values(d)") == _list(1, 2)
    assert kernel.eval("length(d)") == 2


def test_key_get(kernel):
    kernel.eval('d = { "a" -> 1 }')
    assert kernel.eval('key_get(d, "a")') == 1


def test_key_get_on_a_missing_key_is_an_err_value(kernel):
    kernel.eval('d = { "a" -> 1 }')
    result = kernel.eval('key_get(d, "zz")')
    assert result.head == Symbol("Err")
    assert result.tail[0] == "KeyNotFound"


def test_has_key(kernel):
    kernel.eval('d = { "a" -> 1 }')
    assert kernel.eval('has_key(d, "a")') is True
    assert kernel.eval('has_key(d, "zz")') is False



# -- updates -----------------------------------------------------------------


def test_key_set_adds_and_replaces(kernel):
    kernel.eval('d = { "a" -> 1 }')
    assert kernel.eval('key_set(d, "b", 2)') == _dict(("a", 1), ("b", 2))
    assert kernel.eval('key_set(d, "a", 9)') == _dict(("a", 9))


def test_key_drop(kernel):
    kernel.eval('d = { "a" -> 1, "b" -> 2 }')
    assert kernel.eval('key_drop(d, "a")') == _dict(("b", 2))


def test_key_drop_of_an_absent_key_is_a_no_op(kernel):
    """Total, like `rest([])` — otherwise every drop needs an unwrap."""
    kernel.eval('d = { "a" -> 1 }')
    assert kernel.eval('key_drop(d, "zz")') == _dict(("a", 1))


def test_updates_do_not_mutate_the_original(kernel):
    kernel.eval('d = { "a" -> 1 }')
    kernel.eval('key_set(d, "b", 2)')
    assert kernel.eval("d") == _dict(("a", 1))


def test_merge_is_right_biased(kernel):
    assert kernel.eval('merge({ "a" -> 1 }, { "a" -> 9, "b" -> 2 })') == _dict(
        ("a", 9), ("b", 2)
    )


def test_merge_is_variadic(kernel):
    assert kernel.eval(
        'merge({ "a" -> 1 }, { "b" -> 2 }, { "c" -> 3 })'
    ) == _dict(("a", 1), ("b", 2), ("c", 3))


# -- mapping and pairs -------------------------------------------------------


def test_map_values(kernel):
    kernel.eval('d = { "a" -> 1, "b" -> 2 }')
    assert kernel.eval("d |> map_values(v -> v * 10)") == _dict(("a", 10), ("b", 20))


def test_map_keys(kernel):
    kernel.eval("d = { 1 -> \"x\", 2 -> \"y\" }")
    assert kernel.eval("d |> map_keys(k -> k + 10)") == _dict((11, "x"), (12, "y"))


def test_map_keys_collision_resolves_last_wins(kernel):
    kernel.eval('d = { 1 -> "x", 2 -> "y" }')
    collapsed = kernel.eval("d |> map_keys(k -> 0)")
    assert len(collapsed.tail) == 1


def test_to_pairs_and_from_pairs_round_trip(kernel):
    kernel.eval('d = { "b" -> 2, "a" -> 1 }')
    assert kernel.eval("to_pairs(d)") == _list(
        Expression(Symbol("Rule"), "a", 1), Expression(Symbol("Rule"), "b", 2)
    )
    assert kernel.eval("to_pairs(d) |> from_pairs") == kernel.eval("d")


def test_round_trip_survives_a_closure_value(kernel):
    """Why `from_pairs` does not evaluate its entries: a Closure is a value
    that cannot be evaluated a second time, so re-evaluating here would
    break the round trip for any dict holding a function."""
    kernel.eval("d = { \"f\" -> (x -> x + 1) }")
    assert kernel.eval("to_pairs(d) |> from_pairs") == kernel.eval("d")
    assert kernel.eval('key_get(d, "f")(10)') == 11


def test_from_pairs_refuses_a_non_rule_element(kernel):
    with pytest.raises(MinimaticTypeError):
        kernel.eval("from_pairs([1])")


# -- length / EmptyQ ---------------------------------------------------------


def test_length_still_works_on_lists(kernel):
    assert kernel.eval("length([1, 2, 3])") == 3


def test_length_rejects_a_non_container(kernel):
    with pytest.raises(MinimaticTypeError):
        kernel.eval("length(5)")


def test_empty_q_over_list_dict_and_string(kernel):
    assert kernel.eval("EmptyQ({})") is True
    assert kernel.eval("EmptyQ([])") is True
    assert kernel.eval('EmptyQ("")') is True
    assert kernel.eval('EmptyQ({ "a" -> 1 })') is False
    assert kernel.eval("EmptyQ([1])") is False
    assert kernel.eval('EmptyQ("x")') is False


def test_empty_q_rejects_a_scalar(kernel):
    with pytest.raises(MinimaticTypeError):
        kernel.eval("EmptyQ(5)")


# -- a Dict is an ordinary value ---------------------------------------------


def test_equality_ignores_written_order(kernel):
    """The payoff for canonicalising: `equal` needs no Dict special case."""
    assert kernel.eval('{ "a" -> 1, "b" -> 2 } == { "b" -> 2, "a" -> 1 }') is True
    assert kernel.eval('{ "a" -> 1 } == { "a" -> 2 }') is False


def test_dict_type_tag(kernel):
    kernel.eval('shape(d: _dict) := "a dict"')
    kernel.eval('shape(x: _) := "not a dict"')
    assert kernel.eval('shape({ "a" -> 1 })') == "a dict"
    assert kernel.eval("shape([1])") == "not a dict"


def test_dict_pattern_matches_regardless_of_written_order(kernel):
    """The pattern is held by SetDelayed, so it is canonicalised at
    definition time instead — see dict_ops.canonicalize_dict_patterns."""
    kernel.eval('f({ "b" -> 2, "a" -> 1 }) := "matched"')
    kernel.eval("f(d: _dict) := \"fell through\"")
    assert kernel.eval('f({ "a" -> 1, "b" -> 2 })') == "matched"


def test_dict_pattern_matches_exactly_not_partially(kernel):
    """Documented limitation: a Dict pattern is matched positionally like
    every other compound pattern, so it requires exactly those entries."""
    kernel.eval('g({ "a" -> 1 }) := "matched"')
    kernel.eval('g(d: _dict) := "fell through"')
    assert kernel.eval('g({ "a" -> 1 })') == "matched"
    assert kernel.eval('g({ "a" -> 1, "b" -> 2 })') == "fell through"


def test_dict_pattern_binds(kernel):
    kernel.eval('name_of({ "name" -> n: _ }) := n')
    assert kernel.eval('name_of({ "name" -> "ada" })') == "ada"


def test_rewriting_recurses_into_a_dict(kernel):
    assert kernel.eval('{ "a" -> "N/A" } /. "N/A" -> 0') == _dict(("a", 0))


def test_a_dict_rule_lhs_is_canonicalised_too(kernel):
    assert (
        kernel.eval('{ "a" -> 1, "b" -> 2 } /. { "b" -> 2, "a" -> 1 } -> "rewritten"')
        == "rewritten"
    )


def test_structure_inspection(kernel):
    kernel.eval('d = { "a" -> 1 }')
    assert kernel.eval("Head(d)") == Symbol("Dict")
    assert kernel.eval("Args(d)") == _list(Expression(Symbol("Rule"), "a", 1))


def test_err_short_circuits_through_a_dict_head(kernel):
    result = kernel.eval('Err("IOError", "x") |> keys')
    assert result.head == Symbol("Err")

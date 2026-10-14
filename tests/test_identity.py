"""Value identity: one type-strict rule for "is this the same value",
wherever the language asks it. See docs/adr/0001-type-strict-value-identity.md."""

import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.patterns import Blank
from minimatic.ast.symbol import Symbol
from minimatic.errors import MinimaticTypeError
from minimatic.identity import canonical_key


def _list(*items):
    return Expression(Symbol("List"), *items)


@pytest.mark.parametrize(
    "a, b",
    [
        ("[1]", "[1.0]"),
        ("[1]", "[True]"),
        ("[[1, 2]]", "[[1, 2.0]]"),
        ('{"k" -> 1}', '{"k" -> 1.0}'),
    ],
)
def test_equal_is_type_strict_inside_containers(kernel, a, b):
    assert kernel.eval(f"{a} == {b}") is False
    assert kernel.eval(f"{a} != {b}") is True


def test_switch_uses_value_identity(kernel):
    assert kernel.eval('switch([1], [1.0], "same", "different")') == "different"
    assert kernel.eval('switch([1], [1], "same", "different")') == "same"


def test_dict_keeps_values_apart_that_python_equates(kernel):
    assert kernel.eval('{[1] -> "a", [1.0] -> "b", [True] -> "c"} |> length') == 3


def test_literal_pattern_matches_only_the_same_value(kernel):
    kernel.eval('f([1.0]) := "real"')
    kernel.eval('f(x: _) := "other"')
    assert kernel.eval("f([1])") == "other"
    assert kernel.eval("f([1.0])") == "real"


def test_closure_is_the_same_value_only_as_itself(kernel):
    kernel.eval("c = x -> x")
    assert kernel.eval("c == c") is True


def test_closure_is_not_a_dict_key(kernel):
    with pytest.raises(MinimaticTypeError):
        kernel.eval('{(x -> x) -> 1}')


def test_python_equality_on_expressions_follows_value_identity():
    assert _list(1) != _list(1.0)
    assert _list(1) != _list(True)
    assert _list(1, "a") == _list(1, "a")


# -- canonical_key: identity and ordering for Dict keys ----------------------


@pytest.mark.parametrize(
    "a, b",
    [(1, 1.0), (True, 1), (_list(1), _list(True)), (Symbol("a"), "a")],
)
def test_values_python_equates_get_different_keys(a, b):
    assert canonical_key(a) != canonical_key(b)


def test_same_value_gets_the_same_key():
    assert canonical_key(_list(1, "a")) == canonical_key(_list(1, "a"))
    assert canonical_key(Symbol("x")) == canonical_key(Symbol("x"))


def test_a_pattern_node_has_no_key():
    with pytest.raises(MinimaticTypeError):
        canonical_key(Blank("int"))


def test_ordering_is_total_across_mixed_types():
    keys = [Symbol("s"), "str", 3, 2.5, True, None, _list(1)]
    ordered = sorted(keys, key=canonical_key)  # must not raise
    assert ordered == sorted(reversed(keys), key=canonical_key)


def test_ordering_within_a_type_is_by_value():
    assert sorted(["c", "a", "b"], key=canonical_key) == ["a", "b", "c"]
    assert sorted([3, 1, 2], key=canonical_key) == [1, 2, 3]

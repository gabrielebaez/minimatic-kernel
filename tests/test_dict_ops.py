"""Canonical dict keys — identity and ordering.

These are the properties everything else about `Dict` rests on: that two
keys are the same key exactly when `equal` says so, and that a mixed bag of
keys has a deterministic order at all.
"""

import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol
from minimatic.dict_ops import (
    MISSING,
    build_dict,
    canonical_key,
    dict_lookup,
    dict_pairs,
)
from minimatic.errors import MinimaticTypeError


def _list(*items):
    return Expression(Symbol("List"), *items)


# -- identity ----------------------------------------------------------------


def test_same_value_and_type_is_the_same_key():
    assert canonical_key("a") == canonical_key("a")
    assert canonical_key(5) == canonical_key(5)
    assert canonical_key(Symbol("x")) == canonical_key(Symbol("x"))


def test_int_and_float_are_different_keys():
    """They compare equal in Python and hash the same, so a naive dict
    would merge them. `equal` says they differ, so the key must too."""
    assert 1 == 1.0 and hash(1) == hash(1.0)  # the trap
    assert canonical_key(1) != canonical_key(1.0)


def test_bool_and_int_are_different_keys():
    assert True == 1  # noqa: E712 — the trap
    assert canonical_key(True) != canonical_key(1)


def test_compound_keys_do_not_collide_through_python_equality():
    """`Expression.__eq__` compares tails with `==`, under which
    `List(1) == List(True)` — the same trap rewrite._structurally_equal
    exists for."""
    assert _list(1) == _list(True)  # the trap
    assert canonical_key(_list(1)) != canonical_key(_list(True))


def test_symbol_and_string_are_different_keys():
    assert canonical_key(Symbol("a")) != canonical_key("a")


def test_a_pattern_node_is_not_a_key():
    from minimatic.ast.patterns import Blank

    with pytest.raises(MinimaticTypeError):
        canonical_key(Blank("int"))


# -- ordering ----------------------------------------------------------------


def test_ordering_is_total_across_mixed_key_types():
    keys = [Symbol("s"), "str", 3, 2.5, True, None, _list(1)]
    ordered = sorted(keys, key=canonical_key)  # must not raise
    assert len(ordered) == len(keys)
    # Deterministic: the same input always sorts the same way.
    assert ordered == sorted(reversed(keys), key=canonical_key)


def test_ordering_within_a_type_is_by_value():
    assert sorted(["c", "a", "b"], key=canonical_key) == ["a", "b", "c"]
    assert sorted([3, 1, 2], key=canonical_key) == [1, 2, 3]


# -- build_dict --------------------------------------------------------------


def test_build_dict_sorts_entries():
    d = build_dict([("b", 2), ("a", 1)])
    assert dict_pairs(d) == [("a", 1), ("b", 2)]


def test_build_dict_is_order_insensitive():
    assert build_dict([("b", 2), ("a", 1)]) == build_dict([("a", 1), ("b", 2)])


def test_duplicate_keys_resolve_last_wins():
    d = build_dict([("a", 1), ("a", 2)])
    assert dict_pairs(d) == [("a", 2)]


def test_build_dict_keeps_distinct_but_python_equal_keys_apart():
    d = build_dict([(1, "int"), (1.0, "float")])
    assert len(d.tail) == 2


def test_empty_dict():
    d = build_dict([])
    assert d == Expression(Symbol("Dict"))
    assert dict_pairs(d) == []


# -- lookup ------------------------------------------------------------------


def test_dict_lookup_finds_and_misses():
    d = build_dict([("a", 1)])
    assert dict_lookup(d, "a") == 1
    assert dict_lookup(d, "zz") is MISSING


def test_missing_is_distinct_from_a_stored_null():
    """A stored Null must stay tellable apart from no entry at all."""
    d = build_dict([("a", None)])
    assert dict_lookup(d, "a") is None
    assert dict_lookup(d, "b") is MISSING

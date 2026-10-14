"""Building and reading `Dict` values. Key identity and ordering are
value identity's job -- see tests/test_identity.py."""

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol
from minimatic.dict_ops import (
    MISSING,
    build_dict,
    dict_lookup,
    dict_pairs,
)


def _list(*items):
    return Expression(Symbol("List"), *items)


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

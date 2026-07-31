import pytest

from minimatic.ast import (
    Blank,
    BlankNullSeq,
    BlankSeq,
    Expression,
    PatternBind,
    Symbol,
    is_pattern_node,
    is_sequence_pattern,
)


def test_symbol_interning():
    assert Symbol("x") is Symbol("x")
    assert Symbol("x") != Symbol("y")


def test_expression_construction():
    plus = Symbol("plus")
    e = Expression(plus, 1, 3)
    assert e.head == plus
    assert e.tail == (1, 3)
    assert e.args == (1, 3)
    assert len(e) == 2


def test_expression_requires_symbol_or_expression_head():
    with pytest.raises(TypeError):
        Expression(1, 2, 3)


def test_expression_equality_is_structural():
    f = Symbol("f")
    assert Expression(f, 1, 2) == Expression(f, 1, 2)
    assert Expression(f, 1, 2) != Expression(f, 1, 3)


def test_pattern_nodes():
    b = Blank()
    typed = Blank("int")
    seq = BlankSeq("int")
    nullseq = BlankNullSeq()
    bound = PatternBind("x", typed)

    assert is_pattern_node(b)
    assert is_pattern_node(bound)
    assert not is_pattern_node(5)
    assert is_sequence_pattern(seq)
    assert is_sequence_pattern(nullseq)
    assert not is_sequence_pattern(b)
    assert str(bound) == "x: _int"

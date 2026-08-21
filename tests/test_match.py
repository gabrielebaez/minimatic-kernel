import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.patterns import (
    Alternatives,
    Blank,
    BlankNullSeq,
    BlankSeq,
    Condition,
    PatternBind,
)
from minimatic.ast.symbol import Symbol
from minimatic.errors import MinimaticError, MinimaticTypeError
from minimatic.match import check_type, eval_guard, match, match_all


def _greater(a, b):
    return Expression(Symbol("greater"), a, b)


def test_bare_blank_matches_anything():
    assert match(Blank(None), 5, {}) == {}
    assert match(Blank(None), "hi", {}) == {}


def test_typed_blank_checks_type():
    assert match(Blank("int"), 5, {}) == {}
    assert match(Blank("int"), "hi", {}) is None
    assert match(Blank("string"), "hi", {}) == {}


def test_bool_does_not_match_int_typed_blank():
    assert match(Blank("int"), True, {}) is None


def test_pattern_bind_adds_binding():
    result = match(PatternBind("x", Blank("int")), 5, {})
    assert result == {"x": 5}


def test_literal_match_is_type_and_value_exact():
    assert match(5, 5, {}) == {}
    assert match(5, 5.0, {}) is None  # int literal shouldn't match float
    assert match(True, 1, {}) is None  # bool/int collision guarded
    assert match("hi", "hi", {}) == {}
    assert match("hi", "bye", {}) is None


def test_bare_symbol_pattern_is_a_capturing_variable():
    # A bare identifier in pattern position binds like `_`, it doesn't
    # require a literal-symbol match — this is what makes
    # `add(a) := b -> a + b` work.
    assert match(Symbol("a"), 5, {}) == {"a": 5}
    assert match(Symbol("a"), Symbol("anything"), {}) == {"a": Symbol("anything")}


def test_nested_expression_pattern():
    pattern = Expression(Symbol("List"), Blank("int"), Blank("string"))
    value = Expression(Symbol("List"), 5, "hi")
    assert match(pattern, value, {}) == {}
    bad_value = Expression(Symbol("List"), "hi", 5)
    assert match(pattern, bad_value, {}) is None


def test_match_all_positional():
    patterns = (Blank("int"), Blank("string"))
    assert match_all(patterns, (5, "hi")) == {}
    assert match_all(patterns, (5,)) is None  # arity mismatch
    assert match_all(patterns, (5, "hi", "extra")) is None


def test_sequence_blank_binds_remaining_as_list():
    patterns = (PatternBind("x", BlankSeq(None)),)
    result = match_all(patterns, (1, 2, 3))
    assert result == {"x": Expression(Symbol("List"), 1, 2, 3)}


def test_blank_seq_requires_at_least_one():
    patterns = (BlankSeq(None),)
    assert match_all(patterns, ()) is None
    assert match_all(patterns, (1,)) == {}


def test_blank_null_seq_allows_zero():
    patterns = (BlankNullSeq(None),)
    assert match_all(patterns, ()) == {}
    assert match_all(patterns, (1, 2)) == {}


def test_check_type_list_and_dict():
    lst = Expression(Symbol("List"), 1, 2)
    assert check_type(lst, "list") is True
    assert check_type(lst, "dict") is False
    assert check_type(5, "list") is False


# -- Alternatives (`p1 | p2`) ------------------------------------------------


def test_alternatives_matches_any_branch():
    pattern = Alternatives((Blank("int"), Blank("string")))
    assert match(pattern, 5, {}) == {}
    assert match(pattern, "hi", {}) == {}
    assert match(pattern, 1.5, {}) is None


def test_alternatives_first_matching_branch_wins():
    # Both branches match; the bindings that come back are the first one's.
    pattern = Alternatives((PatternBind("a", Blank(None)), PatternBind("b", Blank(None))))
    assert match(pattern, 5, {}) == {"a": 5}


def test_pattern_bind_wraps_the_whole_alternation():
    pattern = PatternBind("x", Alternatives((Blank("int"), Blank("string"))))
    assert match(pattern, 5, {}) == {"x": 5}
    assert match(pattern, "hi", {}) == {"x": "hi"}
    assert match(pattern, 1.5, {}) is None


def test_alternatives_of_literals():
    pattern = Alternatives((1, 2, 3))
    assert match(pattern, 2, {}) == {}
    assert match(pattern, 4, {}) is None


def test_sequence_blank_inside_alternatives_never_matches():
    # Documented limitation: a sequence can only be consumed by _match_seq,
    # which an Alternatives branch routes around. Fails closed.
    pattern = Alternatives((BlankSeq(None), Blank("int")))
    assert match_all((pattern,), (1, 2)) is None
    assert match_all((pattern,), (1,)) == {}  # matched by the `_int` branch


# -- Condition (`pattern /; guard`) -----------------------------------------


def test_condition_requires_a_true_guard(ctx):
    pattern = Condition(PatternBind("x", Blank("int")), _greater(Symbol("x"), 0))
    assert match(pattern, 5, {}, ctx) == {"x": 5}
    assert match(pattern, -5, {}, ctx) is None


def test_condition_fails_when_the_inner_pattern_fails(ctx):
    pattern = Condition(Blank("int"), True)
    assert match(pattern, "hi", {}, ctx) is None


def test_guard_sees_bindings_from_earlier_arguments(ctx):
    patterns = (
        PatternBind("lo", Blank("int")),
        Condition(PatternBind("hi", Blank("int")), _greater(Symbol("hi"), Symbol("lo"))),
    )
    assert match_all(patterns, (1, 5), ctx=ctx) == {"lo": 1, "hi": 5}
    assert match_all(patterns, (5, 1), ctx=ctx) is None


def test_guard_sees_the_enclosing_scope(ctx):
    ctx.env.set_here("threshold", 10)
    pattern = Condition(PatternBind("x", Blank("int")), _greater(Symbol("x"), Symbol("threshold")))
    assert match(pattern, 42, {}, ctx) == {"x": 42}
    assert match(pattern, 4, {}, ctx) is None


def test_guard_on_a_sequence_blank(ctx):
    patterns = (
        Condition(
            PatternBind("xs", BlankSeq(None)),
            _greater(Expression(Symbol("length"), Symbol("xs")), 2),
        ),
    )
    assert match_all(patterns, (1, 2, 3), ctx=ctx) == {"xs": Expression(Symbol("List"), 1, 2, 3)}
    assert match_all(patterns, (1, 2), ctx=ctx) is None


def test_non_bool_guard_raises(ctx):
    with pytest.raises(MinimaticTypeError):
        match(Condition(Blank(None), 1), 5, {}, ctx)


def test_guard_without_a_context_raises():
    with pytest.raises(MinimaticError):
        match(Condition(Blank(None), True), 5, {})


def test_eval_guard_is_reusable_on_its_own(ctx):
    assert eval_guard(_greater(Symbol("n"), 0), {"n": 3}, ctx) is True
    assert eval_guard(_greater(Symbol("n"), 0), {"n": -3}, ctx) is False

from minimatic.ast.expression import Expression
from minimatic.ast.patterns import Blank, BlankNullSeq, BlankSeq, PatternBind
from minimatic.ast.symbol import Symbol
from minimatic.match import check_type, match, match_all


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

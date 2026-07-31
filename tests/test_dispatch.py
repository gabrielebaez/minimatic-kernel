import pytest

from minimatic.errors import HeadAlreadySealedError, NoMatchingClauseError


def test_specificity_dispatch_ignores_declaration_order(kernel):
    # Declared least-specific first — specificity scoring must still win.
    kernel.eval('describe(x: _) := "something else"')
    kernel.eval('describe(x: _string) := "a string"')
    kernel.eval('describe(x: _int) := "an integer"')

    assert kernel.eval("describe(5)") == "an integer"
    assert kernel.eval('describe("hi")') == "a string"
    assert kernel.eval("describe(3.14)") == "something else"


def test_disjoint_equal_specificity_clauses_both_usable(kernel):
    # Two literals: same score, disjoint domains -> no conflict either way.
    kernel.eval('greet(5) := "five"')
    kernel.eval('greet("x") := "ecks"')
    assert kernel.eval("greet(5)") == "five"
    assert kernel.eval('greet("x")') == "ecks"


def test_mvp_gap_overlapping_equal_specificity_resolves_by_order(kernel):
    """
    Documents the known MVP gap (IMPLEMENTATION_PLAN.md): two clauses with
    equal specificity AND overlapping domains should, per the full design,
    be rejected as ambiguous at definition time. The MVP dispatch engine
    does not implement that check yet, so this currently resolves silently
    by declaration order (first-defined wins) instead of raising
    AmbiguousClauseError. This test exists to make that gap visible and
    should be updated (or replaced by a raises-AmbiguousClauseError test)
    the moment ambiguity detection lands.
    """
    kernel.eval('pick(x: _) := "first"')
    kernel.eval('pick(x: _) := "second"')
    assert kernel.eval("pick(1)") == "first"


def test_sequence_pattern_is_least_specific(kernel):
    kernel.eval('shape(x: _int) := "one int"')
    kernel.eval('shape(x: __) := "sequence"')
    assert kernel.eval("shape(5)") == "one int"
    assert kernel.eval("shape(5, 6)") == "sequence"


def test_no_matching_clause_raises(kernel):
    kernel.eval('only_ints(x: _int) := x')
    with pytest.raises(NoMatchingClauseError):
        kernel.eval('only_ints("nope")')


def test_clause_set_seals_after_first_dispatch(kernel):
    kernel.eval('once(x: _) := "ok"')
    kernel.eval("once(1)")  # first dispatch seals the clause set
    with pytest.raises(HeadAlreadySealedError):
        kernel.eval('once(x: _int) := "too late"')

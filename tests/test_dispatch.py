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


def test_genuinely_equal_clauses_resolve_by_declaration_order(kernel):
    """Two clauses that are equally specific *and* overlapping resolve by
    declaration order, first-defined winning.

    This is the specification, not a gap: definition-time ambiguity
    rejection was removed from the language rather than deferred
    (proposal-001 §2.1/§2.2). Where two clauses differ in specificity at
    any depth, `score()` separates them — see the compound-pattern tests
    below; this case is the genuine tie that remains.
    """
    kernel.eval('pick(x: _) := "first"')
    kernel.eval('pick(x: _) := "second"')
    assert kernel.eval("pick(1)") == "first"


def test_compound_pattern_specificity_beats_declaration_order(kernel):
    """`score()` recurses into compound patterns, so a more specific one
    wins regardless of the order the clauses were written in.

    This is the error-kind dispatch idiom that value-or-`Err` makes primary
    (proposal-001 §2.5) — `Err("IOError", d: _)` handling one kind, with a
    general clause behind it. Before `score()` recursed, both scored the
    same and the specific clause declared second never fired at all.
    """
    kernel.eval('handle([k: _, d: _])      := "other error"')
    kernel.eval('handle(["IOError", d: _]) := "caught IOError"')

    assert kernel.eval('handle(["IOError", "boom"])') == "caught IOError"
    assert kernel.eval('handle(["Timeout", "slow"])') == "other error"


def test_compound_pattern_specificity_is_order_independent(kernel):
    # Same clause set as above, declared the other way round.
    kernel.eval('handle(["IOError", d: _]) := "caught IOError"')
    kernel.eval('handle([k: _, d: _])      := "other error"')

    assert kernel.eval('handle(["IOError", "boom"])') == "caught IOError"
    assert kernel.eval('handle(["Timeout", "slow"])') == "other error"


def test_compound_specificity_recurses_more_than_one_level(kernel):
    kernel.eval('deep([[a: _, b: _], y: _]) := "general"')
    kernel.eval('deep([[1, x: _], y: _])    := "specific"')

    assert kernel.eval("deep([[1, 2], 3])") == "specific"
    assert kernel.eval("deep([[9, 2], 3])") == "general"


def test_disjoint_compound_clauses_are_order_independent(kernel):
    """The self-hosted `fold` shape from `docs/the prelude.md` §13: an empty
    -list clause and a cons clause. Their domains are disjoint, so ordering
    never mattered for these two — but the cons clause must use `___`
    (zero-or-more), not `__`, or a single-element list matches neither.
    """
    kernel.eval('fd(f: _, i: _, [x: _, r: ___]) := "step"')
    kernel.eval('fd(f: _, i: _, [])             := "base"')

    assert kernel.eval("fd(plus, 0, [])") == "base"
    assert kernel.eval("fd(plus, 0, [5])") == "step"
    assert kernel.eval("fd(plus, 0, [5, 6])") == "step"


def test_one_or_more_sequence_leaves_single_element_lists_unmatched(kernel):
    # Pins the bug in the prelude §13 example: with `__`, `[5]` matches
    # neither clause. Documented so the doc fix has a regression behind it.
    kernel.eval('bad(f: _, i: _, [])             := "base"')
    kernel.eval('bad(f: _, i: _, [x: _, r: __])  := "step"')

    assert kernel.eval("bad(plus, 0, [])") == "base"
    assert kernel.eval("bad(plus, 0, [5, 6])") == "step"
    with pytest.raises(NoMatchingClauseError):
        kernel.eval("bad(plus, 0, [5])")


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


# -- clause guards (`f(...) /; g := ...`) ------------------------------------


def test_guarded_clauses_select_by_runtime_value(kernel):
    kernel.eval('classify(n: _int) /; n < 0 := "negative"')
    kernel.eval('classify(n: _int) /; n == 0 := "zero"')
    kernel.eval('classify(n: _int) := "positive"')

    assert kernel.eval("classify(-2)") == "negative"
    assert kernel.eval("classify(0)") == "zero"
    assert kernel.eval("classify(7)") == "positive"


def test_failing_guard_falls_through_rather_than_raising(kernel):
    kernel.eval('only_big(n: _int) /; n > 100 := "big"')
    kernel.eval('only_big(n: _int) := "small"')
    assert kernel.eval("only_big(1)") == "small"


def test_no_clause_survives_its_guard(kernel):
    kernel.eval('picky(n: _int) /; n > 100 := "big"')
    with pytest.raises(NoMatchingClauseError):
        kernel.eval("picky(1)")


def test_guarded_clause_must_be_declared_first(kernel):
    """A guard narrows at runtime, which specificity scoring cannot see, so
    a guarded clause ties with its unguarded twin and declaration order
    decides. Declared second, the guard is unreachable — pinned here so the
    behaviour is a documented rule rather than a surprise."""
    kernel.eval('backwards(n: _int) := "catch-all"')
    kernel.eval('backwards(n: _int) /; n < 0 := "negative"')
    assert kernel.eval("backwards(-2)") == "catch-all"


def test_argument_level_guard(kernel):
    kernel.eval('sign(x: _int /; x > 0) := "+"')
    kernel.eval('sign(x: _int) := "-"')
    assert kernel.eval("sign(3)") == "+"
    assert kernel.eval("sign(-3)") == "-"


def test_guard_may_reference_other_arguments(kernel):
    kernel.eval('ordered(lo: _int, hi: _int) /; hi > lo := "ok"')
    kernel.eval('ordered(lo: _int, hi: _int) := "swapped"')
    assert kernel.eval("ordered(1, 5)") == "ok"
    assert kernel.eval("ordered(5, 1)") == "swapped"


# -- alternatives in clause heads --------------------------------------------


def test_alternatives_clause_head(kernel):
    kernel.eval('tag(v: _int | _string) := "scalar"')
    kernel.eval('tag(v: _) := "other"')
    assert kernel.eval("tag(1)") == "scalar"
    assert kernel.eval('tag("a")') == "scalar"
    assert kernel.eval("tag(1.5)") == "other"


# -- specificity of the new nodes --------------------------------------------


def test_condition_scores_as_its_inner_pattern():
    from minimatic.ast.patterns import Blank, Condition, PatternBind
    from minimatic.dispatch import score

    guarded = score((Condition(PatternBind("x", Blank("int")), True),))
    assert guarded == score((PatternBind("x", Blank("int")),))
    assert guarded > score((Blank(None),))


def test_alternatives_scores_as_its_weakest_branch():
    from minimatic.ast.patterns import Alternatives, Blank
    from minimatic.dispatch import score

    # `_int | _` accepts everything `_` accepts, so it must not outrank `_`.
    assert score((Alternatives((Blank("int"), Blank(None))),)) == score((Blank(None),))
    assert score((Alternatives((Blank("int"), Blank("string"))),)) == score((Blank("int"),))

"""Held code: `Hold`, `ReleaseHold`, delayed rules, and `//.`.

The three-step cycle docs/the language.md §11 is built on. What separates
these from tests/test_rewrite.py is the subject: there, `/.` rewrites
*data* that has already been evaluated; here it rewrites *code* that
deliberately has not.
"""

import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol
from minimatic.errors import RewriteLimitError
from minimatic.rewrite import RewriteRule, replace_repeated


def _hold(inner):
    return Expression(Symbol("Hold"), inner)


def test_hold_does_not_evaluate_its_argument(kernel):
    # `f` is not a registered head. Evaluating the argument would raise
    # UnknownHeadError; holding it must not even look.
    assert kernel.eval("Hold(f(1))") == _hold(Expression(Symbol("f"), 1))


def test_hold_captures_no_environment(kernel):
    """Structurally a plain two-element expression, which is what keeps a
    held tree matchable by ordinary patterns."""
    held = kernel.eval("Hold(f(1))")
    assert len(held.tail) == 1
    assert kernel.eval('Hold(f(1)) /. Hold(e: _) -> "was held"') == "was held"


def test_the_full_rewrite_cycle(kernel):
    """docs/the language.md §11's flagship example, end to end."""
    kernel.eval("expr = Hold(f(1) + f(2) + f(6))")
    kernel.eval("rule = f(x: _) -> x + 10")

    rewritten = kernel.eval("expr /. rule")
    assert rewritten == _hold(
        Expression(
            Symbol("plus"), Expression(Symbol("plus"), 11, 12), 16
        )
    )
    assert kernel.eval("ReleaseHold(expr /. rule)") == 39


def test_release_uses_the_environment_it_is_released_in(kernel):
    """docs/the language.md §16.4, answered: `Hold` snapshots nothing, so a
    rebinding between capture and release is visible at release."""
    kernel.eval("x = 1")
    kernel.eval("h = Hold(x + 1)")
    kernel.eval("x = 10")
    assert kernel.eval("ReleaseHold(h)") == 11


def test_release_strips_exactly_one_layer(kernel):
    assert kernel.eval("ReleaseHold(Hold(Hold(1 + 1)))") == _hold(
        Expression(Symbol("plus"), 1, 1)
    )


def test_release_of_a_non_hold_is_the_value_itself(kernel):
    assert kernel.eval("ReleaseHold(5)") == 5
    assert kernel.eval("ReleaseHold(1 + 1)") == 2


def test_delayed_rule_leaves_its_rhs_unevaluated(kernel):
    """The difference `:>` exists for. An immediate rule computes the RHS
    at match time, which collapses the code being rewritten."""
    assert kernel.eval("Hold(g(1)) /. g(a: _) :> a + 1") == _hold(
        Expression(Symbol("plus"), 1, 1)
    )
    assert kernel.eval("Hold(g(1)) /. g(a: _) -> a + 1") == _hold(2)


def test_replace_repeated_reaches_a_normal_form(kernel):
    assert kernel.eval("Hold(not(not(not(True)))) //. not(not(a: _)) :> a") == _hold(
        Expression(Symbol("not"), True)
    )
    assert (
        kernel.eval("ReleaseHold(Hold(not(not(not(True)))) //. not(not(a: _)) :> a)")
        is False
    )


def test_replace_repeated_matches_replace_all_when_one_pass_suffices(kernel):
    assert kernel.eval('[1, "N/A", 2] //. "N/A" -> 0') == kernel.eval(
        '[1, "N/A", 2] /. "N/A" -> 0'
    )


def test_replace_repeated_gives_up_on_a_crawling_rule(kernel):
    # Never a fixpoint, but the tree stays the same size — the pass count
    # is what catches this one.
    with pytest.raises(RewriteLimitError) as excinfo:
        kernel.eval("[1, 2, 3] //. x: _int -> x + 1")
    assert excinfo.value.what == "passes"


def test_replace_repeated_gives_up_on_a_multiplying_rule(kernel):
    # Doubles the tree every pass by rewriting both leaves it just created.
    # The pass count cannot catch this (2**256 nodes); the node count does.
    with pytest.raises(RewriteLimitError) as excinfo:
        kernel.eval("1 //. x: _int :> x + 1")
    assert excinfo.value.what == "nodes"


def test_replace_repeated_limits_are_callable_directly(ctx):
    rule = RewriteRule(Symbol("a"), Expression(Symbol("f"), Symbol("a")), delayed=True)
    with pytest.raises(RewriteLimitError):
        replace_repeated(1, [rule], ctx, limit=8)

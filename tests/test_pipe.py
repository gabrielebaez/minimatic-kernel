"""Pipe semantics: first-position splicing and `$` templates.

Covers proposal-001 §2.8 (docs/proposal-001-dispatch-results-and-pipes.md).
The load-bearing property of the whole feature is that it is *additive* —
every pipe expression that worked before `$` existed must still mean
exactly what it meant, which is what the first group of tests pins down.
"""

import pytest

from minimatic.ast.symbol import Symbol
from minimatic.errors import UnboundSymbolError
from minimatic.lexer import TokenKind, tokenize
from minimatic.parser import parse


# -- the no-$ forms are unchanged ----------------------------------------


def test_bare_head_applies_to_subject(kernel):
    assert kernel.eval("[1, 2, 3] |> length") == 3


def test_no_dollar_splices_into_first_position(kernel):
    # `5 |> minus(10)` is minus(5, 10), not minus(10, 5).
    assert kernel.eval("5 |> minus(10)") == -5
    assert kernel.eval("[1, 2, 3] |> fold(plus, 0)") == 6


def test_lambda_right_hand_side_is_applied_not_spliced(kernel):
    assert kernel.eval("5 |> (x -> x * 2)") == 10


def test_chain_is_left_associative(kernel):
    assert kernel.eval("[1, 2, 3] |> map(x -> x * 2) |> fold(plus, 0)") == 12


# -- $ marks the subject's position --------------------------------------


def test_dollar_in_first_position(kernel):
    assert kernel.eval("2 |> minus($, 10)") == -8


def test_dollar_in_last_position(kernel):
    assert kernel.eval("2 |> minus(10, $)") == 8


def test_dollar_in_middle_position(kernel):
    assert kernel.eval("2 |> plus(10, $, 100)") == 112


def test_dollar_suppresses_first_position_splicing(kernel):
    # If splicing also ran, this would be minus(2, 10, 2) -- an arity error.
    assert kernel.eval("2 |> minus(10, $)") == 8


def test_dollar_substitutes_at_any_depth(kernel):
    assert kernel.eval("2 |> plus(1, times($, 10))") == 21


def test_repeated_dollar_substitutes_every_occurrence(kernel):
    assert kernel.eval("3 |> plus($, $)") == 6


def test_subject_is_evaluated_once_per_pipe(kernel, capsys):
    """`$` copies an already-evaluated value, so repeating it cannot
    re-run the subject. Two `$` here, one side effect."""
    assert kernel.eval("(print(7); 7) |> plus($, $)") == 14
    assert capsys.readouterr().out.count("7") == 1


# -- // is the same operator ---------------------------------------------


def test_postfix_slash_slash_supports_templates(kernel):
    assert kernel.eval("2 // minus(10, $)") == 8


def test_pipe_and_postfix_mix_in_one_chain(kernel):
    assert kernel.eval("5 |> minus(10) // minus($, 1)") == -6


# -- nested pipes: each $ belongs to its own pipe -------------------------


def test_nested_pipe_keeps_its_own_dollar(kernel):
    """A `$` inside a nested pipe's right-hand side belongs to the *inner*
    pipe (proposal-001 §2.8 rule 4), so the outer pipe finds no `$` of its
    own and falls back to first-position splicing.

    Inner binds 3 -> minus(3, 1) == 2; outer splices -> plus(2, 100, 2).
    Were the outer pipe to claim that `$`, this would be plus(100, 1).
    """
    assert kernel.eval("2 |> plus(100, 3 |> minus($, 1))") == 104


def test_nested_pipe_left_hand_side_is_ordinary_ground(kernel):
    # The inner pipe's *subject* is not protected -- `$` there is the outer
    # subject: 2 |> minus(10, (2 |> minus(1))) == minus(10, minus(2, 1)).
    assert kernel.eval("2 |> minus(10, $ |> minus(1))") == 9


# -- boundaries pinned by proposal-001 §2.8 / plan B4 ---------------------


def test_dollar_reaches_into_a_nested_lambda_body(kernel):
    """"Any depth" includes a nested Lambda's body. This is the one place
    that reading is surprising, so it is pinned rather than left implicit."""
    assert kernel.eval("10 |> map([1, 2, 3], x -> x + $)") == parse("[11, 12, 13]")


def test_dollar_in_a_lambda_right_hand_side_stays_unbound(kernel):
    """A Lambda right-hand side *is* the function -- it is applied to the
    subject, never substituted into -- so a `$` in it is just a free
    symbol. Asserted so the failure mode is defined rather than incidental."""
    with pytest.raises(UnboundSymbolError):
        kernel.eval("5 |> (x -> $ + x)")


def test_closure_subject_fails_identically_with_and_without_dollar(kernel):
    """Pre-existing: `_impl_pipe` splices an evaluated value into a raw tree
    and re-evaluates it, and a Closure is `Expression(Symbol("Closure"),
    ...)`, whose head resolves to nothing. Templates do not introduce this
    -- both forms fail the same way -- so it is pinned here and left for
    its own change rather than fixed silently under proposal-001 §2.8.
    """
    from minimatic.errors import UnknownHeadError

    kernel.eval("f = (x -> x * 2)")
    with pytest.raises(UnknownHeadError):
        kernel.eval("f |> map([1, 2, 3])")  # no $, pre-existing path
    with pytest.raises(UnknownHeadError):
        kernel.eval("f |> map([1, 2, 3], $)")  # $ template, same failure


# -- lexing and parsing --------------------------------------------------


def test_dollar_lexes_as_its_own_token():
    kinds = [t.kind for t in tokenize("$")]
    assert kinds[0] is TokenKind.DOLLAR


def test_dollar_parses_as_a_symbol():
    assert parse("$") == Symbol("$")


def test_dollar_is_not_a_valid_identifier_character():
    # `a$b` must not lex as one identifier -- otherwise `$` could be
    # forged inside a user name and stop being unambiguous.
    kinds = [t.kind for t in tokenize("a$b")]
    assert kinds[:3] == [TokenKind.IDENT, TokenKind.DOLLAR, TokenKind.IDENT]

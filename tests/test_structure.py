"""`Head`/`Args` (structure inspection) and `first`/`rest` (list access).

These are two different jobs that used to share one name. `head` meant
"first element" in the prelude while `head` means "the operator of an
expression" everywhere else in the language — `docs/the language.md` §4 is
built on `head(args)`, and `Expression.head` is the operator. `_impl_head`
even implemented first-element as `list_expr.tail[0]`, using both senses of
the word in a single line.

`Head`/`Args` are PascalCase per `docs/the prelude.md` §2.4 (heads that
inspect the language's own structure), leaving `first`/`rest` for list
access, so "head" now has exactly one meaning.
"""

import pytest

from minimatic.ast.symbol import Symbol
from minimatic.errors import MinimaticTypeError
from minimatic.parser import parse


# -- Head is total -------------------------------------------------------


@pytest.mark.parametrize(
    "src,expected",
    [
        ("[1, 2, 3]", "List"),
        ("[]", "List"),
        ("5", "Integer"),
        ("3.5", "Real"),
        ('"hi"', "String"),
    ],
)
def test_head_returns_the_head_symbol(kernel, src, expected):
    assert kernel.eval(f"Head({src})") == Symbol(expected)


def test_head_of_empty_list_is_list_not_an_error(kernel):
    """The case that motivated all of this: `[]` is sugar for `List()`, so
    its head is `List`. Unlike `first([])`, there is nothing to signal."""
    assert kernel.eval("Head([])") == Symbol("List")


def test_head_of_a_head_symbol_is_symbol(kernel):
    # Head([]) is the symbol `List`, whose own head is `Symbol`.
    assert kernel.eval("Head(Head([]))") == Symbol("Symbol")


def test_head_sees_evaluated_values_only(kernel):
    # `Head` holds nothing, so its argument is evaluated first: g(3) is 6,
    # an Integer. Inspecting *unevaluated* code needs `Hold`, which is
    # deferred (proposal-001 §2.4).
    kernel.eval("g(x: _) := x * 2")
    assert kernel.eval("Head(g(3))") == Symbol("Integer")


# -- the atom-head symbols are first-class values ------------------------


def test_atom_head_symbols_are_bound(kernel):
    """`Head(5)` is useless if `Integer` is unbound: you could not compare
    against it, and the returned symbol would raise when re-evaluated.
    Unlike `List`, these name no clause set, so they are bound explicitly.
    """
    assert kernel.eval("Head(5) == Integer") is True
    assert kernel.eval('Head("hi") == String') is True
    assert kernel.eval("Head([]) == List") is True
    assert kernel.eval("Head(5) == String") is False


def test_head_symbol_survives_being_piped(kernel):
    # Re-evaluating the returned symbol must not raise UnboundSymbolError.
    assert kernel.eval("5 |> Head") == Symbol("Integer")
    assert kernel.eval("5 |> Head |> Head") == Symbol("Symbol")


# -- Args ----------------------------------------------------------------


def test_args_returns_a_list_of_arguments(kernel):
    assert kernel.eval("Args([1, 2, 3])") == parse("[1, 2, 3]")


def test_args_of_an_atom_is_empty(kernel):
    assert kernel.eval("Args(5)") == parse("[]")
    assert kernel.eval("Args([])") == parse("[]")


def test_args_preserves_nested_structure(kernel):
    assert kernel.eval("Args([1, [2]])") == parse("[1, [2]]")


# -- first / rest --------------------------------------------------------


def test_first_and_rest_split_a_list(kernel):
    assert kernel.eval("first([10, 20, 30])") == 10
    assert kernel.eval("rest([10, 20, 30])") == parse("[20, 30]")


def test_rest_is_total(kernel):
    # The rest of an empty list genuinely is the empty list.
    assert kernel.eval("rest([])") == parse("[]")
    assert kernel.eval("rest([1])") == parse("[]")


def test_first_of_empty_list_is_an_err(kernel):
    # Routine failure, so a value rather than an exception (see
    # minimatic/result.py for the boundary).
    assert kernel.eval("first([]) |> is_err") is True
    assert kernel.eval("first([]) |> Args |> first") == "EmptyList"


def test_empty_list_is_a_legitimate_first_element(kernel):
    """Why `first([])` cannot just answer `[]`: an empty list is a perfectly
    good element, so the two cases would be indistinguishable."""
    assert kernel.eval("first([[], 1])") == parse("[]")

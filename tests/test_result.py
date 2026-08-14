"""Value-or-`Err`: failure as a value, and the boundary around it.

Success is the value itself — there is no `Ok` wrapper — so an ordinary
function applied through the pipe already does the work `map_ok` does
elsewhere. Failure is an `Err(kind, detail)` expression, which pipelines
skip past unless the target head is `ResultAware`.

See minimatic/result.py for the line between `Err` values and kernel
exceptions, and docs/proposal-001-dispatch-results-and-pipes.md §2.5.
"""

import pytest

from minimatic.ast.symbol import Symbol
from minimatic.errors import ArityError, MinimaticTypeError
from minimatic.parser import parse


# -- constructing and shaping -------------------------------------------


def test_err_is_an_ordinary_expression(kernel):
    assert kernel.eval('Err("IOError", "boom") |> Head') == Symbol("Err")
    assert kernel.eval('Err("IOError", "boom") |> Args') == parse('["IOError", "boom"]')


def test_one_argument_err_normalizes_to_two(kernel):
    """`Err(k: _, d: _)` must match every `Err` there is. A one-argument
    shape would silently fall through to a more general clause instead of
    failing loudly — the exact failure mode this design removes."""
    assert kernel.eval('Err("EmptyList") |> Args |> length') == 2
    kernel.eval('shape(Err(k: _, d: _)) := "two args"')
    assert kernel.eval('shape(Err("EmptyList"))') == "two args"


def test_err_is_matchable_and_destructurable(kernel):
    kernel.eval('kind_of(Err(k: _, d: _)) := k')
    assert kernel.eval('kind_of(Err("IOError", "boom"))') == "IOError"


def test_err_type_tag(kernel):
    kernel.eval('tag(r: _err) := "an error"')
    kernel.eval('tag(x: _)    := "a value"')
    assert kernel.eval("tag(divide(1, 0))") == "an error"
    assert kernel.eval("tag(5)") == "a value"


# -- error-kind dispatch -------------------------------------------------


def test_error_kind_dispatch_is_order_independent(kernel):
    """The idiom this whole feature turns on: one clause per kind, with a
    general fallback. Relies on score() recursing into compound patterns —
    the specific clause is declared *second* here."""
    kernel.eval('handle(Err(k: _, d: _))           := "other"')
    kernel.eval('handle(Err("DivideByZero", d: _)) := "caught div"')

    assert kernel.eval("handle(divide(1, 0))") == "caught div"
    assert kernel.eval("handle(first([]))") == "other"


# -- pipe short-circuiting ------------------------------------------------


def test_pipe_skips_a_non_result_aware_head(kernel):
    assert kernel.eval("divide(1, 0) |> length |> is_err") is True


def test_skipped_head_is_never_called(kernel, capsys):
    # `print` would emit if it ran; it is ResultAware, so use a head that
    # is not. `length` on an Err would raise if it were called at all.
    assert kernel.eval("divide(1, 0) |> length |> Args |> first") == "DivideByZero"
    assert capsys.readouterr().out == ""


def test_pipe_does_not_skip_a_result_aware_head(kernel):
    assert kernel.eval("divide(1, 0) |> is_err") is True
    assert kernel.eval("divide(1, 0) |> recover(e -> 0)") == 0


def test_pipe_skips_a_lambda_right_hand_side(kernel):
    """A Lambda has no head, so it is never ResultAware. Handing an error
    to a user lambda that cannot know it got one is the trap this ordering
    avoids — the check runs before the Lambda branch in `_impl_pipe`."""
    assert kernel.eval("divide(1, 0) |> (x -> 99) |> is_err") is True


def test_short_circuit_precedes_dollar_substitution(kernel, capsys):
    # A skipped pipe must not evaluate its template arguments either.
    assert kernel.eval('divide(1, 0) |> minus(print("evaluated"), $) |> is_err') is True
    assert capsys.readouterr().out == ""


def test_success_flows_through_untouched(kernel):
    assert kernel.eval("6 |> divide(3)") == 2.0
    assert kernel.eval("6 |> divide(3) |> is_err") is False


def test_failure_skips_the_rest_and_arrives_at_recover(kernel):
    assert (
        kernel.eval('divide(1, 0) |> plus(100) |> times(2) |> recover(e -> "recovered")')
        == "recovered"
    )


# -- inspectors stay usable on errors ------------------------------------


def test_inspectors_are_result_aware(kernel):
    # Without ResultAware these would return the Err itself, defeating the
    # Head(r) == Err idiom and making failures undebuggable in a pipeline.
    assert kernel.eval("divide(1, 0) |> Head") == Symbol("Err")
    assert kernel.eval("divide(1, 0) |> Args |> first") == "DivideByZero"


def test_print_can_show_an_error_mid_pipeline(kernel, capsys):
    kernel.eval('divide(1, 0) |> print |> recover(e -> 0)')
    assert "DivideByZero" in capsys.readouterr().out


# -- combinators ----------------------------------------------------------


def test_unwrap_supplies_a_default_only_on_error(kernel):
    assert kernel.eval("divide(1, 0) |> unwrap(0)") == 0
    assert kernel.eval("divide(6, 3) |> unwrap(0)") == 2.0


def test_unwrap_err_yields_the_detail(kernel):
    assert kernel.eval('Err("IOError", "boom") |> unwrap_err') == "boom"


def test_unwrap_err_on_a_non_error_is_a_programming_error(kernel):
    with pytest.raises(MinimaticTypeError):
        kernel.eval("unwrap_err(5)")


def test_catch_handles_one_kind_and_passes_others_through(kernel):
    assert kernel.eval('divide(1, 0) |> catch("DivideByZero", e -> 42)') == 42
    assert kernel.eval('divide(1, 0) |> catch("Other", e -> 42) |> is_err') is True


def test_catch_leaves_success_alone(kernel):
    assert kernel.eval('divide(6, 3) |> catch("DivideByZero", e -> 42)') == 2.0


def test_recover_handles_any_error(kernel):
    assert kernel.eval('first([]) |> recover(e -> "gone")') == "gone"
    assert kernel.eval('divide(6, 3) |> recover(e -> "gone")') == 2.0


def test_finally_runs_for_effect_and_returns_the_value(kernel, capsys):
    assert kernel.eval('divide(6, 3) |> finally(x -> print("done"))') == 2.0
    assert "done" in capsys.readouterr().out


# -- producers -------------------------------------------------------------


def test_divide_by_zero_is_a_value(kernel):
    assert kernel.eval("divide(1, 0) |> is_err") is True
    assert kernel.eval("divide(1, 0) |> Args |> first") == "DivideByZero"


def test_first_of_empty_list_is_a_value(kernel):
    assert kernel.eval("first([]) |> Args |> first") == "EmptyList"


def test_rest_of_empty_list_is_still_total(kernel):
    assert kernel.eval("rest([])") == parse("[]")


# -- the exception boundary ------------------------------------------------


def test_type_errors_stay_exceptions(kernel):
    """Programming errors are not Err values — otherwise every mistake
    becomes a value that drifts down a pipeline (minimatic/result.py)."""
    with pytest.raises(MinimaticTypeError):
        kernel.eval('plus(1, "a")')
    with pytest.raises(MinimaticTypeError):
        kernel.eval('length("abc")')


def test_arity_mistakes_raise_arity_error(kernel):
    # Previously escaped as a raw Python TypeError, outside MinimaticError
    # entirely, so host code catching "any Minimatic problem" missed them.
    with pytest.raises(ArityError):
        kernel.eval("length()")
    with pytest.raises(ArityError):
        kernel.eval("first([1], [2])")


def test_arity_error_names_the_minimatic_head(kernel):
    with pytest.raises(ArityError) as excinfo:
        kernel.eval("length()")
    assert "length" in str(excinfo.value)
    assert "_impl_" not in str(excinfo.value)


def test_a_direct_call_on_an_err_is_not_short_circuited(kernel):
    # Only pipes short-circuit (proposal-001 §2.5 rule 4). Accepted rough
    # edge, pinned so the choice stays visible.
    with pytest.raises(MinimaticTypeError):
        kernel.eval("plus(divide(1, 0), 1)")


# -- not / ! ---------------------------------------------------------------


def test_not_negates(kernel):
    assert kernel.eval("not(True)") is False
    assert kernel.eval("!True") is False
    assert kernel.eval("!False") is True


def test_not_makes_is_err_readable(kernel):
    assert kernel.eval("!is_err(divide(6, 3))") is True
    assert kernel.eval("!is_err(divide(1, 0))") is False


def test_not_rejects_non_bools(kernel):
    # No truthiness in Minimatic, matching `if`'s strictness.
    with pytest.raises(MinimaticTypeError):
        kernel.eval("!5")

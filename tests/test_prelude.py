import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol


def test_arithmetic(kernel):
    assert kernel.eval("1 + 3") == 4
    assert kernel.eval("2 * 3 + 1") == 7
    assert kernel.eval("2 ^ 3") == 8
    assert kernel.eval("10 - 4") == 6
    assert kernel.eval("10 / 4") == 2.5
    assert kernel.eval("10 % 3") == 1
    assert kernel.eval("-5 + 2") == -3


def test_comparisons(kernel):
    assert kernel.eval("3 < 5") is True
    assert kernel.eval("3 > 5") is False
    assert kernel.eval("3 == 3") is True
    assert kernel.eval("3 != 3") is False


def test_list_literal_evaluates_elements(kernel):
    result = kernel.eval("[1 + 1, 2 + 2]")
    assert result == Expression(Symbol("List"), 2, 4)


def test_list_operations(kernel):
    assert kernel.eval("[1, 2, 3] |> length") == 3
    assert kernel.eval("[1, 2, 3] |> head") == 1
    assert kernel.eval("[1, 2, 3] |> tail") == Expression(Symbol("List"), 2, 3)
    assert kernel.eval("[1, 2, 3] |> append(4)") == Expression(
        Symbol("List"), 1, 2, 3, 4
    )


def test_map_with_lambda(kernel):
    result = kernel.eval("[1, 2, 3] |> map(x -> x * 2)")
    assert result == Expression(Symbol("List"), 2, 4, 6)


def test_fold_with_bare_head_reference(kernel):
    assert kernel.eval("[1, 2, 3, 4] |> fold(plus, 0)") == 10


def test_curried_lambda_application(kernel):
    kernel.eval("add(a) := b -> a + b")
    add5 = kernel.eval("add(5)")
    from minimatic.ast.symbol import Symbol as S

    # applying the returned closure to 3 should give 8
    result = kernel.eval("add(5)(3)")
    assert result == 8


def test_flagship_example_double(kernel):
    kernel.eval("double(x: _int) := 2 * x")
    assert kernel.eval("double(21)") == 42


def test_flagship_example_pipeline(kernel):
    result = kernel.eval(
        '[1, "N/A", 3, "N/A", 5] '
        '|> map(x -> x /. "N/A" -> 0) '
        "|> fold(plus, 0)"
    )
    assert result == 9


# --------------------------------------------------------- control flow --


def test_if_only_evaluates_the_taken_branch(kernel):
    assert kernel.eval('if(3 < 5, "yes", 1 / 0)') == "yes"
    assert kernel.eval('if(3 > 5, 1 / 0, "no")') == "no"


def test_if_requires_a_bool_condition(kernel):
    from minimatic.errors import MinimaticTypeError

    with pytest.raises(MinimaticTypeError):
        kernel.eval('if(1, "a", "b")')


def test_switch_matches_case_and_only_evaluates_winning_result(kernel):
    kernel.eval("x = 8")
    result = kernel.eval('switch(x, 2, 1 / 0, 8, "eight", 99, 1 / 0)')
    assert result == "eight"


def test_switch_falls_back_to_trailing_default(kernel):
    assert kernel.eval('switch(99, 2, "two", "default")') == "default"


def test_switch_no_match_no_default_raises(kernel):
    from minimatic.errors import MinimaticTypeError

    with pytest.raises(MinimaticTypeError):
        kernel.eval('switch(99, 2, "two")')


def test_which_is_a_cond_elif_chain(kernel):
    kernel.eval("x = 8")
    result = kernel.eval('which(x == 2, "two", x == 8, "eight", 1 / 0, "never")')
    assert result == "eight"


def test_which_falls_back_to_trailing_default(kernel):
    assert kernel.eval('which(False, "a", "fallback")') == "fallback"


def test_for_and_each_return_null_and_apply_fn_for_effect(kernel):
    kernel.eval("total = 0")
    # `for` doesn't collect results (unlike map) — it returns Null.
    assert kernel.eval("[1, 2, 3] |> for(x -> x * x)") is None
    assert kernel.eval("[1, 2, 3] |> each(x -> x * x)") is None


def test_compound_expression_runs_in_order_and_returns_last(kernel):
    kernel.eval("log = []")
    result = kernel.eval("(1 + 1; 2 + 2; 3 + 3)")
    assert result == 6


def test_print_returns_null(kernel):
    assert kernel.eval('print("hello")') is None


def test_range_desugars_to_half_open_list(kernel):
    from minimatic.ast.expression import Expression
    from minimatic.ast.symbol import Symbol

    assert kernel.eval("0 .. 5") == Expression(Symbol("List"), 0, 1, 2, 3, 4)
    assert kernel.eval("for(0 .. 3, x -> x)") is None


def test_for_over_range(kernel):
    # docs/the language.md's own for(0..5, y -> print(y)) example
    assert kernel.eval("for(0 .. 5, y -> print(y))") is None

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

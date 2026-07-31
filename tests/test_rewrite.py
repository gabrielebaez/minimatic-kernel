def test_replace_all_on_matching_literal(kernel):
    assert kernel.eval('"N/A" /. "N/A" -> 0') == 0


def test_replace_all_no_match_returns_unchanged(kernel):
    assert kernel.eval('"keep" /. "N/A" -> 0') == "keep"


def test_replace_all_recurses_into_list_elements(kernel):
    result = kernel.eval('[1, 2, 3, 4] /. x: _ -> x ^ 2')
    from minimatic.ast.expression import Expression
    from minimatic.ast.symbol import Symbol

    assert result == Expression(Symbol("List"), 1, 4, 9, 16)


def test_replace_all_with_rule_list(kernel):
    result = kernel.eval('[1, "N/A", 2] /. ["N/A" -> 0, 1 -> 100]')
    from minimatic.ast.expression import Expression
    from minimatic.ast.symbol import Symbol

    assert result == Expression(Symbol("List"), 100, 0, 2)

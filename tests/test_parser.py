import pytest

from minimatic.ast.expression import Expression
from minimatic.ast.patterns import Blank, BlankSeq, PatternBind
from minimatic.ast.symbol import Symbol
from minimatic.errors import NotImplementedInMVPError
from minimatic.parser import parse


def test_arithmetic_desugaring():
    assert parse("1 + 3") == Expression(Symbol("plus"), 1, 3)
    assert parse("2 * 3 + 1") == Expression(
        Symbol("plus"), Expression(Symbol("times"), 2, 3), 1
    )
    assert parse("2 ^ 3 ^ 2") == Expression(
        Symbol("power"), 2, Expression(Symbol("power"), 3, 2)
    )  # right-assoc


def test_pipe_desugaring_left_assoc():
    tree = parse("5 |> sqrt |> str")
    assert tree == Expression(
        Symbol("__pipe__"),
        Expression(Symbol("__pipe__"), 5, Symbol("sqrt")),
        Symbol("str"),
    )


def test_list_literal():
    assert parse("[1, 2, 3]") == Expression(Symbol("List"), 1, 2, 3)
    assert parse("[]") == Expression(Symbol("List"))


def test_dict_literal_always_builds_rules():
    tree = parse('{ "a" -> 1 }')
    assert tree == Expression(
        Symbol("Dict"), Expression(Symbol("Rule"), "a", 1)
    )


def test_lambda_desugaring():
    tree = parse("x -> x * 2")
    assert tree == Expression(
        Symbol("Lambda"), Symbol("x"), Expression(Symbol("times"), Symbol("x"), 2)
    )


def test_curried_lambda_right_assoc():
    tree = parse("a -> b -> f(b, a)")
    assert tree == Expression(
        Symbol("Lambda"),
        Symbol("a"),
        Expression(
            Symbol("Lambda"),
            Symbol("b"),
            Expression(Symbol("f"), Symbol("b"), Symbol("a")),
        ),
    )


def test_define_with_typed_blank_pattern():
    tree = parse("double(x: _int) := 2 * x")
    assert tree == Expression(
        Symbol("SetDelayed"),
        Expression(Symbol("double"), PatternBind("x", Blank("int"))),
        Expression(Symbol("times"), 2, Symbol("x")),
    )


def test_plain_binding():
    tree = parse("x = 5")
    assert tree == Expression(Symbol("Set"), Symbol("x"), 5)


def test_bare_blank_and_sequence_blank_patterns():
    tree = parse("sum_all(x: __) := fold(plus, 0, x)")
    define, body = tree.tail
    assert define == Expression(Symbol("sum_all"), PatternBind("x", BlankSeq(None)))


def test_replace_all_desugaring():
    tree = parse('"N/A" /. "N/A" -> 0')
    assert tree == Expression(
        Symbol("ReplaceAll"), "N/A", Expression(Symbol("Rule"), "N/A", 0)
    )


def test_nested_arrow_inside_replace_inside_lambda():
    tree = parse('x -> x /. "N/A" -> 0')
    replace_all = Expression(
        Symbol("ReplaceAll"),
        Symbol("x"),
        Expression(Symbol("Rule"), "N/A", 0),
    )
    assert tree == Expression(Symbol("Lambda"), Symbol("x"), replace_all)


def test_flagship_pipeline_parses():
    tree = parse(
        '[1, "N/A", 3, "N/A", 5] '
        '|> map(x -> x /. "N/A" -> 0) '
        "|> fold(plus, 0)"
    )
    # top level: __pipe__(__pipe__(list, map(...)), fold(...))
    assert tree.head == Symbol("__pipe__")
    inner_pipe, fold_call = tree.tail
    assert inner_pipe.head == Symbol("__pipe__")
    list_lit, map_call = inner_pipe.tail
    assert list_lit == Expression(Symbol("List"), 1, "N/A", 3, "N/A", 5)
    assert map_call.head == Symbol("map")
    (lambda_arg,) = map_call.tail
    assert lambda_arg.head == Symbol("Lambda")
    assert fold_call == Expression(Symbol("fold"), Symbol("plus"), 0)


def test_delayed_rule_not_implemented():
    with pytest.raises(NotImplementedInMVPError):
        parse('x /. "N/A" :> 0')


def test_replace_all_with_pattern_bind():
    tree = parse("[1, 2, 3, 4] /. x: _ -> x^2")
    rule = tree.tail[1]
    assert rule == Expression(
        Symbol("Rule"),
        PatternBind("x", Blank(None)),
        Expression(Symbol("power"), Symbol("x"), 2),
    )


def test_range_desugaring():
    assert parse("0 .. 5") == Expression(Symbol("Range"), 0, 5)


def test_range_binds_looser_than_additive():
    assert parse("0 .. 2 + 3") == Expression(Symbol("Range"), 0, Expression(Symbol("plus"), 2, 3))


def test_compound_expression_desugaring():
    tree = parse('(print("Hello"); print("World"))')
    assert tree == Expression(
        Symbol("CompoundExpression"),
        Expression(Symbol("print"), "Hello"),
        Expression(Symbol("print"), "World"),
    )


def test_compound_expression_allows_trailing_semicolon():
    tree = parse("(1; 2;)")
    assert tree == Expression(Symbol("CompoundExpression"), 1, 2)


def test_single_parenthesized_expr_is_not_wrapped():
    assert parse("(1 + 2)") == Expression(Symbol("plus"), 1, 2)

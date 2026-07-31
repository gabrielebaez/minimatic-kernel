import pytest

from minimatic.errors import UnboundSymbolError, UnknownHeadError


def test_binding_and_lookup(kernel):
    kernel.eval("x = 5")
    assert kernel.eval("x") == 5


def test_define_and_call(kernel):
    kernel.eval("double(x: _int) := x * 2")
    assert kernel.eval("double(21)") == 42


def test_unbound_symbol_raises(kernel):
    with pytest.raises(UnboundSymbolError):
        kernel.eval("totally_undefined_name")


def test_unknown_head_raises(kernel):
    with pytest.raises(UnknownHeadError):
        kernel.eval("totally_undefined_call(1, 2)")


def test_bare_head_reference_self_evaluates(kernel):
    # `plus` has no env binding, but is a registered head — used this way
    # by `fold(plus, 0, xs)`. It must evaluate to itself, not error.
    result = kernel.eval("fold([1, 2, 3], plus, 0)")
    assert result == 6


def test_lambda_is_a_closure_value(kernel):
    from minimatic.ast.expression import Expression
    from minimatic.ast.symbol import Symbol

    closure = kernel.eval("x -> x * 2")
    assert isinstance(closure, Expression)
    assert closure.head == Symbol("Closure")


def test_set_delayed_does_not_evaluate_body_early(kernel):
    # If SetDelayed evaluated its body eagerly, `y` (unbound at definition
    # time) would raise before `f` is ever called.
    kernel.eval("f(x: _int) := x + y_that_does_not_exist_yet")
    with pytest.raises(UnboundSymbolError):
        kernel.eval("f(1)")

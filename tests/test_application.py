"""Head application: a callable value applied to arguments behaves the same
however the call was reached -- written out, passed as a value, curried, or
piped. See GLOSSARY.md."""

from minimatic.ast.expression import Expression
from minimatic.ast.symbol import Symbol


def _list(*items):
    return Expression(Symbol("List"), *items)


# -- Listable threads on every route -----------------------------------------


def test_listable_head_threads_when_passed_to_map(kernel):
    assert kernel.eval("map([[1, 2], [3, 4]], negate)") == _list(
        _list(-1, -2), _list(-3, -4)
    )


def test_listable_head_threads_when_passed_to_fold(kernel):
    assert kernel.eval("fold([[1, 2], [3, 4]], plus, 0)") == _list(4, 6)


def test_listable_head_threads_when_piped(kernel):
    assert kernel.eval("[1, 2] |> negate") == _list(-1, -2)


# -- a clause runs in the scope it was defined in ----------------------------


def test_clause_body_sees_its_defining_scope_not_the_callers(kernel):
    kernel.run("y = 10\ng(x: _) := x + y\nh(y: _) := g(1)")
    assert kernel.eval("h(100)") == 11


def test_clause_body_sees_globals_defined_after_it(kernel):
    kernel.run("g(x: _) := x + later\nlater = 5")
    assert kernel.eval("g(1)") == 6


def test_clause_guard_sees_its_defining_scope_not_the_callers(kernel):
    kernel.run(
        'limit = 10\nbig(x: _) /; x > limit := "big"\nbig(x: _) := "small"\n'
        "probe(limit: _) := big(5)"
    )
    assert kernel.eval("probe(0)") == "small"


def test_pattern_guard_in_a_clause_sees_its_defining_scope(kernel):
    kernel.run(
        'limit = 10\nbig(x: _ /; x > limit) := "big"\nbig(x: _) := "small"\n'
        "probe(limit: _) := big(5)"
    )
    assert kernel.eval("probe(0)") == "small"


def test_recursion_still_works(kernel):
    kernel.run("fact(0) := 1\nfact(n: _int) := n * fact(n - 1)")
    assert kernel.eval("fact(5)") == 120


# -- the extension seam goes through the same path ---------------------------


def test_registered_listable_head_threads_on_every_route(kernel):
    kernel.register_head("double", lambda x: x * 2, attributes=("Listable",))
    assert kernel.eval("double([1, 2])") == _list(2, 4)
    assert kernel.eval("map([[1], [2]], double)") == _list(_list(2), _list(4))


def test_registered_head_arity_mistake_is_an_arity_error(kernel):
    import pytest

    from minimatic.errors import ArityError

    kernel.register_head("pair", lambda a, b: [a, b])
    with pytest.raises(ArityError):
        kernel.eval("pair(1)")

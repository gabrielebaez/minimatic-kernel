"""
Identity - value identity: the one rule for "is this the same value".

Type-strict at every level: `1`, `1.0` and `true` are three different
values, and so are `[1]`, `[1.0]` and `[true]`. `equal`, `switch`, literal
patterns, `Dict` keys and the `//.` fixpoint test all ask through here, so
they cannot disagree. See docs/adr/0001-type-strict-value-identity.md.

Two functions, one rule:

  - `same(a, b)` answers the question directly.
  - `canonical_key(v)` gives a hashable, totally-ordered stand-in for `v`
    such that `same(a, b)` exactly when their keys are equal. `Dict` uses
    it to deduplicate and sort entries.
"""

from __future__ import annotations

from .ast.expression import Expression
from .ast.symbol import Symbol
from .errors import MinimaticTypeError


def same(a, b) -> bool:
    """Are `a` and `b` the same value?

    The recursion into expressions lives in `Expression.__eq__`, which
    applies this same rule to every head and argument -- so Python-level
    `==` on expressions is never laxer than the language's own identity.
    What only this function adds is the top-level type check that plain
    `==` cannot give atoms: `1 == 1.0` and `True == 1` in Python.

    Anything without its own notion of equality compares by object
    identity. That is what makes two closures the same value only when
    they captured the very same scope.
    """
    return type(a) is type(b) and a == b


def canonical_key(value):
    """A hashable, totally-ordered canonical form of a value.

    Identity: `canonical_key(a) == canonical_key(b)` exactly when
    `same(a, b)`. Ordering: the leading integer rank makes keys of
    different types mutually comparable, so `sorted` over mixed keys is
    total rather than a TypeError. The ranking itself is arbitrary; the
    language promises only that it is stable and total, not what it is. Do
    not encode an expectation about it anywhere else.

    Values with no canonical form -- a closure, whose scope can only be
    compared by identity -- raise, which is what makes them invalid as
    `Dict` keys.
    """
    if value is None:
        return (0,)
    if isinstance(value, bool):
        # Before the int branch: bool is a subclass of int, and the whole
        # point is that `True` is not the key `1`.
        return (1, value)
    if isinstance(value, (int, float)):
        # Type name breaks the tie between `1` and `1.0`, which compare
        # equal numerically but are different values.
        return (2, value, type(value).__name__)
    if isinstance(value, str):
        return (3, value)
    if isinstance(value, Symbol):
        return (4, value.name)
    if isinstance(value, Expression):
        return (5, canonical_key(value.head), tuple(canonical_key(a) for a in value.tail))
    raise MinimaticTypeError(f"{value!r} cannot be a dict key")

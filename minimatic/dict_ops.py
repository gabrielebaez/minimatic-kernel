"""
Dict ops - canonical keys, and the one place a `Dict` is built.

A `Dict` is an ordinary `Expression` headed by `Dict` whose arguments are
`Rule(key, value)` expressions — no separate type, per kernel doc §2.1.
Which means the order its entries are stored in **is** its structural
identity: `equal`, `/.` matching, and `Head`/`Args` all read it. So entries
are canonicalised at construction — deduplicated and sorted — and
`{"a" -> 1, "b" -> 2}` and `{"b" -> 2, "a" -> 1}` are literally the same
value.

The alternative, preserving insertion order and special-casing `equal` to
compare dicts as maps, would make `Dict` the first value in the language
where equality and structural identity disagree — two dicts that are
`equal` but that fail to match each other as a `/.` pattern. Canonicalising
buys that consistency for the price of one sort.

Lookup is a linear scan. `docs/the kernel.md` §10 records the intended
HAMT backing; until it exists, this is no worse than `List`, which is also
a flat tuple.
"""

from __future__ import annotations

from .ast.expression import Expression
from .ast.patterns import Alternatives, Condition, PatternBind
from .ast.symbol import Symbol
from .errors import MinimaticTypeError

DICT = Symbol("Dict")
RULE = Symbol("Rule")

MISSING = object()
"""Returned by `dict_lookup` when a key is absent — distinct from every
Minimatic value, so a stored `Null` stays tellable apart from no entry."""


def canonical_key(key):
    """A hashable, totally-ordered canonical form of a dict key.

    One function, two jobs:

    **Identity** — two keys are the same key exactly when their canonical
    forms are equal. This reproduces `equal`'s `type(a) is type(b) and
    a == b` rule recursively, which plain Python equality does not: `1` and
    `1.0` would otherwise collide, `True` with `1`, and `List(1)` with
    `List(True)` (the same trap `rewrite._structurally_equal` exists for).

    **Ordering** — the leading integer rank makes forms from different
    types mutually comparable, so `sorted` over mixed keys is total rather
    than a TypeError. The ranking itself is arbitrary; the language
    promises only that it is stable and total, not what it is. Do not
    encode an expectation about it anywhere else.
    """
    if key is None:
        return (0,)
    if isinstance(key, bool):
        # Before the int branch: bool is a subclass of int, and the whole
        # point is that `True` is not the key `1`.
        return (1, key)
    if isinstance(key, (int, float)):
        # Type name breaks the tie between `1` and `1.0`, which compare
        # equal numerically but are different keys.
        return (2, key, type(key).__name__)
    if isinstance(key, str):
        return (3, key)
    if isinstance(key, Symbol):
        return (4, key.name)
    if isinstance(key, Expression):
        return (5, canonical_key(key.head), tuple(canonical_key(a) for a in key.tail))
    raise MinimaticTypeError(f"{key!r} cannot be a dict key")


def build_dict(pairs) -> Expression:
    """Build a canonical `Dict` from `(key, value)` pairs.

    Every head that produces a dict goes through here, so canonicalisation
    cannot be forgotten in one of them. Duplicate keys resolve **last
    wins**, matching `merge`'s documented right-bias — one rule for
    "later beats earlier", wherever the duplicate came from.
    """
    by_key: dict = {}
    for key, value in pairs:
        by_key[canonical_key(key)] = (key, value)
    entries = [
        Expression(RULE, key, value)
        for _, (key, value) in sorted(by_key.items(), key=lambda item: item[0])
    ]
    return Expression(DICT, *entries)


def is_dict(value) -> bool:
    return isinstance(value, Expression) and value.head == DICT


def check_dict(value, who: str) -> None:
    """Mirrors prelude.py's `_check_list`."""
    if not is_dict(value):
        raise MinimaticTypeError(f"{who}: expected a Dict, got {value!r}")


def dict_pairs(value) -> list[tuple]:
    """A dict's entries as `(key, value)` tuples, in canonical order."""
    return [(entry.tail[0], entry.tail[1]) for entry in value.tail]


def dict_lookup(value, key):
    """The value stored under `key`, or `MISSING`."""
    target = canonical_key(key)
    for entry in value.tail:
        if canonical_key(entry.tail[0]) == target:
            return entry.tail[1]
    return MISSING


HOLD = Symbol("Hold")


def canonicalize_dict_patterns(node):
    """Sort any `Dict` literal appearing inside a *pattern*.

    A dict value is canonicalised when it is built, but a dict written in
    pattern position never is: `SetDelayed` and `Rule` are both HoldAll, so
    the pattern reaches the matcher exactly as typed. Without this, whether
    `f({"b" -> 2, "a" -> 1}) := ...` matched would depend on the caller
    having written the same order -- and since the canonical order is
    deliberately arbitrary (`canonical_key`), there would be no order a
    user could reliably write.

    Normalising the pattern the same way the value is normalised keeps this
    out of `match.py`: there is still exactly one structural matcher, and a
    `Dict` pattern is still matched positionally like every other compound
    pattern. It just gets the same treatment on the way in.

    Two things are deliberately left alone:

    - **Entries whose keys are not plain values** (`{k: _ -> v: _}`) cannot
      be sorted, since a pattern node has no canonical key. Left as
      written, so such a pattern stays order-dependent.
    - **Anything under `Hold`.** Held code is code, not a value; a held
      dict is not canonicalised until it is released, so a pattern meant to
      match it must not be either.
    """
    if isinstance(node, PatternBind):
        return PatternBind(node.name, canonicalize_dict_patterns(node.pattern))
    if isinstance(node, Condition):
        return Condition(canonicalize_dict_patterns(node.pattern), node.guard)
    if isinstance(node, Alternatives):
        return Alternatives(tuple(canonicalize_dict_patterns(p) for p in node.patterns))
    if not isinstance(node, Expression):
        return node
    if node.head == HOLD:
        return node
    rebuilt = Expression(node.head, *(canonicalize_dict_patterns(a) for a in node.tail))
    if rebuilt.head != DICT:
        return rebuilt
    try:
        entries = sorted(rebuilt.tail, key=_pattern_entry_key)
    except MinimaticTypeError:
        return rebuilt  # a key that is itself a pattern: leave as written
    return Expression(DICT, *entries)


def _pattern_entry_key(entry):
    if (
        isinstance(entry, Expression)
        and entry.head == RULE
        and len(entry.tail) == 2
    ):
        return canonical_key(entry.tail[0])
    raise MinimaticTypeError(f"not a `key -> value` entry: {entry!r}")

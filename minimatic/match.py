"""
Match - Structural pattern matcher.

Shared, in principle, by both call-time dispatch (dispatch.py) and `/.`
rewriting (rewrite.py) — one implementation, one semantics (kernel doc §5).
This property survives the MVP's deferral of ambiguity detection unchanged;
only *ranking/rejecting* clauses (dispatch.py's job) is simplified, not
matching itself.

`match()` matches a single pattern node against a single value.
`match_all()` matches a tuple of per-argument patterns against a tuple of
argument values, handling the one case a single `match()` call can't:
sequence blanks (`__`, `___`) that span a variable number of positions.
"""

from __future__ import annotations

from .ast.atoms import is_boolean, is_integer, is_real, is_string
from .ast.expression import Expression
from .ast.patterns import Blank, BlankNullSeq, BlankSeq, PatternBind
from .ast.symbol import Symbol

_TYPE_CHECKS = {
    "int": is_integer,
    "integer": is_integer,
    "float": is_real,
    "real": is_real,
    "string": is_string,
    "str": is_string,
    "bool": is_boolean,
    "boolean": is_boolean,
    "symbol": lambda v: isinstance(v, Symbol),
}


def check_type(value, type_tag: str | None) -> bool:
    if type_tag is None:
        return True
    tag = type_tag.lower()
    if tag == "list":
        return isinstance(value, Expression) and value.head == Symbol("List")
    if tag == "dict":
        return isinstance(value, Expression) and value.head == Symbol("Dict")
    if tag == "expr":
        return isinstance(value, Expression)
    predicate = _TYPE_CHECKS.get(tag)
    if predicate is None:
        return False  # unknown type tag: fail closed, never silently match everything
    return predicate(value)


def match(pattern, value, bindings: dict) -> dict | None:
    """Match a single pattern node against a single value. None on failure."""
    if isinstance(pattern, Blank):
        if not check_type(value, pattern.type_tag):
            return None
        return bindings

    if isinstance(pattern, PatternBind):
        inner = match(pattern.pattern, value, bindings)
        if inner is None:
            return None
        new_bindings = dict(inner)
        new_bindings[pattern.name] = value
        return new_bindings

    if isinstance(pattern, (BlankSeq, BlankNullSeq)):
        # Only meaningful inside match_all's argument-list handling.
        return None

    if isinstance(pattern, Symbol):
        # A bare identifier in pattern position is a capturing variable
        # (Erlang/ML-style), not a literal-symbol match — this is what
        # lets `add(a) := b -> a + b` bind `a` to whatever value is
        # passed, the same way `x: _` would. There is deliberately no way
        # in the MVP to write a pattern that matches one *specific*
        # symbol literally; that's not needed by anything in scope.
        new_bindings = dict(bindings)
        new_bindings[pattern.name] = value
        return new_bindings

    if isinstance(pattern, Expression):
        # The head position is a literal requirement, never a capturing
        # variable — `List(a, b)` must only match values headed by
        # `List`, not "any call, capture its head as `a`". Only argument
        # positions (matched below via match_all) get bare-Symbol-binds
        # semantics.
        if not isinstance(value, Expression) or pattern.head != value.head:
            return None
        return match_all(pattern.tail, value.tail, bindings)

    # Literal atom (int, float, str, bool, None): match by equal type + value,
    # so `True` (bool) never accidentally matches `1` (int) via Python's
    # `True == 1`.
    return bindings if type(pattern) is type(value) and pattern == value else None


def _sequence_pattern(pat):
    """If `pat` is a bare or bound sequence blank, return (blank_node, bind_name)."""
    if isinstance(pat, (BlankSeq, BlankNullSeq)):
        return pat, None
    if isinstance(pat, PatternBind) and isinstance(pat.pattern, (BlankSeq, BlankNullSeq)):
        return pat.pattern, pat.name
    return None, None


def match_all(patterns: tuple, values: tuple, bindings: dict | None = None) -> dict | None:
    """
    Match a tuple of per-argument patterns against a tuple of argument
    values.

    MVP simplification: a sequence blank (`__`/`___`) is only supported as
    the *last* pattern in the list (it then greedily consumes all
    remaining values). Sequence patterns followed by more patterns are not
    supported and conservatively fail to match rather than guess.
    """
    bindings = {} if bindings is None else bindings
    return _match_seq(list(patterns), list(values), bindings)


def _match_seq(patterns: list, values: list, bindings: dict) -> dict | None:
    if not patterns:
        return bindings if not values else None

    pat = patterns[0]
    rest_patterns = patterns[1:]

    seq_blank, bind_name = _sequence_pattern(pat)
    if seq_blank is not None:
        if rest_patterns:
            return None  # unsupported shape in MVP: sequence blank must be last
        min_count = 1 if isinstance(seq_blank, BlankSeq) else 0
        if len(values) < min_count:
            return None
        if seq_blank.type_tag is not None and not all(
            check_type(v, seq_blank.type_tag) for v in values
        ):
            return None
        new_bindings = dict(bindings)
        if bind_name is not None:
            new_bindings[bind_name] = Expression(Symbol("List"), *values)
        return new_bindings

    if not values:
        return None

    head_value, *tail_values = values
    matched = match(pat, head_value, bindings)
    if matched is None:
        return None
    return _match_seq(rest_patterns, tail_values, matched)

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

Matching is otherwise pure structural recursion, with one deliberate
exception: `Condition` (`pattern /; guard`) has to *evaluate* its guard, so
both entry points take an optional `ctx` and thread it through — the same
arrangement `rewrite.py` already uses for `ReplaceAll`. Keeping guards
inside `match()` rather than lifting them into dispatch.py/rewrite.py is
what lets a guard sit anywhere a pattern can, including nested inside a
compound pattern (`f(List(x: _int /; x > 0), y: _)`), which a caller one
layer up could not see.
"""

from __future__ import annotations

from .ast.atoms import is_boolean, is_integer, is_real, is_string
from .ast.expression import Expression
from .ast.patterns import (
    Alternatives,
    Blank,
    BlankNullSeq,
    BlankSeq,
    Condition,
    PatternBind,
)
from .ast.symbol import Symbol
from .errors import MinimaticError, MinimaticTypeError

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
    if tag == "err":
        return isinstance(value, Expression) and value.head == Symbol("Err")
    predicate = _TYPE_CHECKS.get(tag)
    if predicate is None:
        return False  # unknown type tag: fail closed, never silently match everything
    return predicate(value)


def eval_guard(guard, bindings: dict, ctx) -> bool:
    """Evaluate a `/;` guard against the bindings its pattern just produced.

    Shared with dispatch.py, which applies the same rule to a clause-level
    guard. The guard sees the new bindings *layered over the enclosing
    scope* — `ctx.env` is the call site's env in both callers — so a guard
    can mention both the names it just bound and anything already in scope.

    Bool-strict, like `if` and `not`: there is no truthiness in Minimatic,
    so a guard that produces a number or an `Err` is a mistake to report,
    not a `False` to act on.
    """
    if ctx is None:
        raise MinimaticError(
            "a pattern guard (/;) needs an evaluation context; "
            "match() was called without one"
        )
    result = ctx.eval(guard, ctx.env.extend(bindings))
    if not isinstance(result, bool):
        raise MinimaticTypeError(f"pattern guard must evaluate to a bool, got {result!r}")
    return result


def match(pattern, value, bindings: dict, ctx=None) -> dict | None:
    """Match a single pattern node against a single value. None on failure."""
    if isinstance(pattern, Blank):
        if not check_type(value, pattern.type_tag):
            return None
        return bindings

    if isinstance(pattern, PatternBind):
        inner = match(pattern.pattern, value, bindings, ctx)
        if inner is None:
            return None
        new_bindings = dict(inner)
        new_bindings[pattern.name] = value
        return new_bindings

    if isinstance(pattern, Alternatives):
        # First matching branch wins. A name bound only by a losing branch
        # is simply absent from the result — referencing it downstream
        # raises UnboundSymbolError, which is the honest failure. There is
        # no ambiguity to resolve: exactly one branch ever matched.
        for branch in pattern.patterns:
            result = match(branch, value, bindings, ctx)
            if result is not None:
                return result
        return None

    if isinstance(pattern, Condition):
        # Match, then test. There is exactly one candidate binding to test
        # — matching is deterministic structural recursion, not
        # backtracking search — so a false guard fails the Condition
        # outright rather than looking for another way to satisfy it.
        inner = match(pattern.pattern, value, bindings, ctx)
        if inner is None:
            return None
        return inner if eval_guard(pattern.guard, inner, ctx) else None

    if isinstance(pattern, (BlankSeq, BlankNullSeq)):
        # Only meaningful inside match_all's argument-list handling. This
        # is also why a sequence blank inside `|` never matches: the
        # Alternatives branch above routes back through here.
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
        return match_all(pattern.tail, value.tail, bindings, ctx)

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


def match_all(
    patterns: tuple, values: tuple, bindings: dict | None = None, ctx=None
) -> dict | None:
    """
    Match a tuple of per-argument patterns against a tuple of argument
    values.

    MVP simplification: a sequence blank (`__`/`___`) is only supported as
    the *last* pattern in the list (it then greedily consumes all
    remaining values). Sequence patterns followed by more patterns are not
    supported and conservatively fail to match rather than guess.
    """
    bindings = {} if bindings is None else bindings
    return _match_seq(list(patterns), list(values), bindings, ctx)


def _match_seq(patterns: list, values: list, bindings: dict, ctx=None) -> dict | None:
    if not patterns:
        return bindings if not values else None

    pat = patterns[0]
    rest_patterns = patterns[1:]

    # A guard wrapping a sequence blank (`xs: __ /; length(xs) > 2`) has to
    # be unwrapped here rather than in `match`, because only this function
    # ever gets to consume a sequence. Unwrap, and re-wrap below if what is
    # underneath turns out to be an ordinary one-value pattern after all.
    guard = None
    if isinstance(pat, Condition):
        guard, pat = pat.guard, pat.pattern

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
        if guard is not None and not eval_guard(guard, new_bindings, ctx):
            return None
        return new_bindings

    if guard is not None:
        pat = Condition(pat, guard)

    if not values:
        return None

    head_value, *tail_values = values
    matched = match(pat, head_value, bindings, ctx)
    if matched is None:
        return None
    return _match_seq(rest_patterns, tail_values, matched, ctx)

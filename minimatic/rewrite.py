"""
Rewrite - Minimal `/.` (ReplaceAll) over already-evaluated data.

MVP scope only: this is data-rewriting, not code-rewriting. There is no
`Hold`/`ReleaseHold` env-snapshot capture here — by the time `replace_all`
runs, `value` has already been evaluated (ReplaceAll is HoldRest, so only
its *rule* argument arrives unevaluated; the value being rewritten is
ordinary post-eval data). Rule RHSs are evaluated once, immediately, at
match time — `RuleDelayed` (`:>`) is out of scope for the MVP (see
IMPLEMENTATION_PLAN.md) and is rejected at parse time already.
"""

from __future__ import annotations

from .ast.expression import Expression
from .ast.symbol import Symbol
from .errors import MinimaticTypeError
from .match import match


def replace_all(value, rules: list[tuple], ctx):
    """Try each (lhs, rhs) rule against `value`; on the first match,
    substitute bindings into rhs and evaluate once. If no rule matches at
    this node, recurse into sub-expressions. Otherwise return unchanged."""
    for lhs, rhs in rules:
        bindings = match(lhs, value, {})
        if bindings is not None:
            substituted = substitute(rhs, bindings)
            return ctx.eval(substituted)
    if isinstance(value, Expression):
        return value.map_args(lambda a: replace_all(a, rules, ctx))
    return value


def substitute(node, bindings: dict):
    if isinstance(node, Symbol):
        return bindings.get(node.name, node)
    if isinstance(node, Expression):
        return Expression(
            substitute(node.head, bindings),
            *(substitute(a, bindings) for a in node.tail),
        )
    return node


def extract_rules(rule_expr) -> list[tuple]:
    """Normalize a ReplaceAll rule argument (a single Rule, or a List of
    Rules) into a list of (lhs, rhs) pairs."""
    if isinstance(rule_expr, Expression) and rule_expr.head == Symbol("List"):
        return [_as_rule_pair(r) for r in rule_expr.tail]
    return [_as_rule_pair(rule_expr)]


def _as_rule_pair(r) -> tuple:
    if isinstance(r, Expression) and r.head == Symbol("Rule") and len(r.tail) == 2:
        return r.tail
    raise MinimaticTypeError(f"expected a Rule, got {r!r}")

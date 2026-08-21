"""
Rewrite - `/.` (ReplaceAll) and `//.` (ReplaceRepeated).

Kept in its own module, called *from* `Hold`/`ReleaseHold`/`/.` sites and
never calling back into `eval` except at the one explicit release boundary
(kernel doc §7). That separation is what makes "rewriting is explicit, not
ambient" a property of the codebase rather than a rule to remember.

A rule's right-hand side is treated one of two ways, and the difference is
the whole reason `:>` exists:

  - **`->` (immediate)** — the substituted RHS is evaluated once, at the
    moment the rule matches. This is what makes `[1,2,3] /. x: _ -> x^2`
    produce numbers rather than `power` calls.
  - **`:>` (delayed)** — the substituted RHS is returned *unevaluated*.
    This is what makes rewriting `Hold`-captured code possible at all: an
    immediate rule collapses the code it is meant to be transforming on
    first substitution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ast.expression import Expression
from .ast.symbol import Symbol
from .dict_ops import canonicalize_dict_patterns
from .errors import MinimaticTypeError, RewriteLimitError
from .match import match

_RULE = Symbol("Rule")
_RULE_DELAYED = Symbol("RuleDelayed")
_LIST = Symbol("List")

# `//.` gives up after this many passes. Deliberately far below Wolfram's
# 65536: `replace_all` walks the tree with Python recursion and there is no
# tail-call elimination, so a rule that grows its subject each pass would
# hit `RecursionError` long before a cap that large ever fired. A macro
# expander needing more than a couple of hundred passes is diverging.
MAX_REWRITE_PASSES = 256

# A pass count on its own does not bound the work: a rule that matches at
# every leaf *doubles* the tree each pass, so 256 passes is 2**256 nodes
# and the pass counter never gets to fire. `1 //. x: _int :> x + 1` is
# exactly that shape. Measuring the result after each pass is what turns
# that from a hang into an error.
MAX_REWRITE_NODES = 50_000


@dataclass(frozen=True)
class RewriteRule:
    lhs: object
    rhs: object
    delayed: bool = False


def replace_all(value, rules: list[RewriteRule], ctx):
    """Try each rule against `value`; on the first match, substitute
    bindings into its RHS (evaluating it unless the rule is delayed). If no
    rule matches at this node, recurse into sub-expressions. Otherwise
    return unchanged."""
    for rule in rules:
        bindings = match(rule.lhs, value, {}, ctx)
        if bindings is not None:
            substituted = substitute(rule.rhs, bindings)
            return substituted if rule.delayed else ctx.eval(substituted)
    if isinstance(value, Expression):
        return value.map_args(lambda a: replace_all(a, rules, ctx))
    return value


def replace_repeated(
    value,
    rules: list[RewriteRule],
    ctx,
    limit: int = MAX_REWRITE_PASSES,
    node_limit: int = MAX_REWRITE_NODES,
):
    """Apply `replace_all` until the result stops changing — a normal form
    for this rule set — or give up.

    `replace_all` returns at the first match on a node without re-examining
    its own output, so reaching a normal form is exactly "keep passing until
    nothing changes", not a smarter traversal.

    Two independent guards, because divergence takes two shapes. A rule
    that cycles or crawls (`[1,2,3] //. x: _int -> x + 1`) is caught by the
    pass count; a rule that multiplies (`1 //. x: _int :> x + 1`, which
    rewrites both leaves it just created) is caught by the node count long
    before the pass count could.
    """
    current = value
    for _ in range(limit):
        try:
            nxt = replace_all(current, rules, ctx)
        except RecursionError as exc:
            # Too deep to walk. Report it as the divergence it is, rather
            # than letting RecursionError escape MinimaticError entirely.
            raise RewriteLimitError(limit) from exc
        if _exceeds_size(nxt, node_limit):
            raise RewriteLimitError(node_limit, "nodes")
        if _structurally_equal(nxt, current):
            return current
        current = nxt
    raise RewriteLimitError(limit)


def _exceeds_size(node, budget: int) -> bool:
    """Does `node` hold more than `budget` nodes? Stops as soon as it knows,
    so the check costs O(budget) however large the tree actually is.
    Iterative, because the tree it is measuring may be too deep to recurse
    over — which is half of what it exists to detect."""
    stack = [node]
    seen = 0
    while stack:
        current = stack.pop()
        seen += 1
        if seen > budget:
            return True
        if isinstance(current, Expression):
            stack.append(current.head)
            stack.extend(current.tail)
    return False


def _structurally_equal(a, b) -> bool:
    """Fixpoint test for `//.`.

    Not plain `==`: `Expression.__eq__` compares tails with Python `==`, so
    `List(1)` and `List(True)` compare equal and a rewrite from one to the
    other would look like a fixpoint. Same type-and-value rule `match()`
    uses for literals, for the same reason.
    """
    if isinstance(a, Expression) or isinstance(b, Expression):
        if not (isinstance(a, Expression) and isinstance(b, Expression)):
            return False
        return (
            _structurally_equal(a.head, b.head)
            and len(a.tail) == len(b.tail)
            and all(_structurally_equal(x, y) for x, y in zip(a.tail, b.tail))
        )
    return type(a) is type(b) and a == b


def substitute(node, bindings: dict):
    if isinstance(node, Symbol):
        return bindings.get(node.name, node)
    if isinstance(node, Expression):
        return Expression(
            substitute(node.head, bindings),
            *(substitute(a, bindings) for a in node.tail),
        )
    return node


def looks_like_rules(node) -> bool:
    """Is `node` already a written-out rule (or list of them)?

    `ReplaceAll` is HoldRest, so its rule argument arrives unevaluated —
    which is required, or a pattern LHS would evaluate before it could
    match. But that also means `expr /. rule`, where `rule` is a *name*
    bound to a rule, arrives as a bare Symbol. This check is how the two
    are told apart: anything that isn't already a rule gets evaluated first
    (see prelude.py). `Rule`/`RuleDelayed` are both HoldAll, so evaluating
    a list of them leaves their pattern LHSs intact.
    """
    if not isinstance(node, Expression):
        return False
    if node.head in (_RULE, _RULE_DELAYED):
        return True
    if node.head == _LIST:
        return bool(node.tail) and all(looks_like_rules(r) for r in node.tail)
    return False


def extract_rules(rule_expr) -> list[RewriteRule]:
    """Normalize a rule argument (a single Rule/RuleDelayed, or a List of
    them) into a list of `RewriteRule`."""
    if isinstance(rule_expr, Expression) and rule_expr.head == _LIST:
        return [_as_rule(r) for r in rule_expr.tail]
    return [_as_rule(rule_expr)]


def _as_rule(r) -> RewriteRule:
    # The LHS goes through the same dict-pattern canonicalisation a clause
    # pattern gets in dispatch.define -- these are the two routes a pattern
    # takes to the matcher.
    if isinstance(r, Expression) and len(r.tail) == 2:
        if r.head == _RULE:
            return RewriteRule(canonicalize_dict_patterns(r.tail[0]), r.tail[1], False)
        if r.head == _RULE_DELAYED:
            return RewriteRule(canonicalize_dict_patterns(r.tail[0]), r.tail[1], True)
    raise MinimaticTypeError(f"expected a Rule, got {r!r}")

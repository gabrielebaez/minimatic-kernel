"""
Dispatch - ClauseSet with hybrid specificity + declaration-order dispatch.

MVP simplification (see IMPLEMENTATION_PLAN.md): clauses are ranked by
`score()` exactly as in the full design (literal > typed blank > blank >
sequence blank, compared lexicographically across argument positions), but
same-score clauses are NOT checked for ambiguity — they simply stay in
declaration order among themselves. There is no `overlaps()`/`implies()`,
no `AmbiguousClauseError`. Callers should not treat same-score-tie
resolution as a stable, guaranteed feature; it is a placeholder for the
ambiguity-rejecting behavior the full design calls for.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .ast.patterns import Blank, BlankNullSeq, BlankSeq, PatternBind
from .ast.symbol import Symbol
from .errors import HeadAlreadySealedError, NoMatchingClauseError
from .match import match_all


def _score_one(pattern) -> int:
    if isinstance(pattern, PatternBind):
        return _score_one(pattern.pattern)
    if isinstance(pattern, (BlankSeq, BlankNullSeq)):
        return 0
    if isinstance(pattern, Blank):
        return 2 if pattern.type_tag is not None else 1
    if isinstance(pattern, Symbol):
        return 1  # bare identifier binds anything, same tier as bare `_`
    return 3  # literal or nested Expression pattern: most specific


def score(arg_patterns: tuple) -> tuple[int, ...]:
    """Per-argument specificity vector, compared lexicographically."""
    return tuple(_score_one(p) for p in arg_patterns)


@dataclass
class Clause:
    arg_patterns: tuple
    body: object = None
    py_fn: Callable | None = None
    pass_ctx: bool = False
    specificity: tuple = field(default=())
    order: int = 0


class ClauseSet:
    def __init__(self, head_name: str):
        self.head_name = head_name
        self.clauses: list[Clause] = []
        self.sealed = False

    def define(self, arg_patterns, *, body=None, py_fn=None, pass_ctx=False) -> Clause:
        if self.sealed:
            raise HeadAlreadySealedError(self.head_name)
        clause = Clause(
            arg_patterns=tuple(arg_patterns),
            body=body,
            py_fn=py_fn,
            pass_ctx=pass_ctx,
            specificity=score(tuple(arg_patterns)),
            order=len(self.clauses),
        )
        self.clauses.append(clause)
        # Descending specificity; same-score clauses keep declaration order
        # (stable sort + order-as-secondary-key achieves this).
        self.clauses.sort(key=lambda c: (tuple(-s for s in c.specificity), c.order))
        return clause

    def apply(self, args, env, evaluator: Callable, ctx=None):
        self.sealed = True
        args = tuple(args)
        for clause in self.clauses:
            bindings = match_all(clause.arg_patterns, args)
            if bindings is None:
                continue
            if clause.py_fn is not None:
                if clause.pass_ctx:
                    return clause.py_fn(*args, ctx=ctx)
                return clause.py_fn(*args)
            return evaluator(clause.body, env.extend(bindings))
        raise NoMatchingClauseError(self.head_name, args)

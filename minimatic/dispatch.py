"""
Dispatch - ClauseSet with specificity + declaration-order dispatch.

Clauses are ranked by `score()` — literal > typed blank > blank > sequence
blank, compared lexicographically across argument positions — and
same-score clauses are tried in declaration order, first structural match
winning. That is the specification, not a placeholder: definition-time
ambiguity rejection (`overlaps()`/`implies()`, `AmbiguousClauseError`) was
removed from the language rather than deferred. See
docs/proposal-001-dispatch-results-and-pipes.md §2.1 and §2.2.

Because nothing rejects overlapping clauses any more, `score()` has to be
able to tell them apart on its own — hence the recursion into compound
patterns below.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Callable

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
from .dict_ops import canonicalize_dict_patterns
from .errors import HeadAlreadySealedError, NoMatchingClauseError
from .match import eval_guard, match_all


def _score_one(pattern) -> tuple:
    """Specificity of a single pattern, as a nested tuple compared
    structurally against another pattern's.

    Compound patterns recurse into their arguments, so
    `Err("IOError", d: _)` -> `(3, ((3,), (1,)))` outranks
    `Err(k: _, d: _)` -> `(3, ((1,), (1,)))`. Without that recursion both
    score the same and the more specific clause wins only if it happens to
    be declared first — which, with ambiguity rejection gone, is a silently
    wrong answer rather than a rejected definition.
    """
    if isinstance(pattern, PatternBind):
        return _score_one(pattern.pattern)
    if isinstance(pattern, Condition):
        # A guard narrows at runtime, not in shape. Scoring it above its
        # inner pattern would claim a specificity that `overlaps`-style
        # static reasoning cannot see and that ordering cannot honour —
        # so a guarded clause and its unguarded twin tie, and resolve by
        # declaration order (see ClauseSet.define).
        return _score_one(pattern.pattern)
    if isinstance(pattern, Alternatives):
        # Only as specific as the weakest branch: `_int | _` accepts
        # everything `_` accepts, so it cannot outrank `_`.
        return min(_score_one(p) for p in pattern.patterns)
    if isinstance(pattern, (BlankSeq, BlankNullSeq)):
        return (0,)
    if isinstance(pattern, Blank):
        return (2,) if pattern.type_tag is not None else (1,)
    if isinstance(pattern, Symbol):
        return (1,)  # bare identifier binds anything, same tier as bare `_`
    if isinstance(pattern, Expression):
        # The head is deliberately not scored: two compound patterns with
        # different heads are disjoint, so it would add no signal.
        #
        # Note an empty compound `[]` scores `(3, ())`, which sorts below a
        # non-empty one like `[x: _, rest: ___]`. Harmless — those two are
        # disjoint — but it is not a bug if you notice it.
        return (3, tuple(_score_one(a) for a in pattern.tail))
    return (3,)  # literal: most specific


def score(arg_patterns: tuple) -> tuple:
    """Per-argument specificity vector, compared lexicographically."""
    return tuple(_score_one(p) for p in arg_patterns)


@dataclass
class Clause:
    arg_patterns: tuple
    body: object = None
    py_fn: Callable | None = None
    pass_ctx: bool = False
    # A clause-level `/;` guard (`f(x: _) /; x > 0 := ...`), evaluated
    # after the argument patterns match. None for an unguarded clause.
    guard: object | None = None
    specificity: tuple = field(default=())
    # The scope the clause was defined in. Its guard, any guards inside its
    # patterns, and its body all evaluate here -- extended with the new
    # bindings -- never in the caller's scope. None for a Python builtin,
    # which has no Minimatic scope of its own.
    env: object | None = None
    # Cached at definition time, used only on the failure path (see
    # eval.py's builtin call) to tell an arity mistake from a type mistake.
    signature: inspect.Signature | None = None


class ClauseSet:
    """A head's clauses, ranked for selection.

    Selection only: given arguments, which clause applies and with what
    bindings. Running the clause -- calling a builtin, evaluating a body --
    is head application's job (eval.py), so this module never evaluates
    anything except the guards that decide selection.
    """

    def __init__(self, head_name: str):
        self.head_name = head_name
        self.clauses: list[Clause] = []
        self.sealed = False

    def define(
        self, arg_patterns, *, body=None, py_fn=None, pass_ctx=False, guard=None, env=None
    ) -> Clause:
        if self.sealed:
            raise HeadAlreadySealedError(self.head_name)
        # Dict literals in the pattern are sorted here, the same way a
        # dict value is sorted when it is built -- see dict_ops.
        clause = Clause(
            arg_patterns=tuple(canonicalize_dict_patterns(p) for p in arg_patterns),
            body=body,
            py_fn=py_fn,
            pass_ctx=pass_ctx,
            guard=guard,
            specificity=score(tuple(arg_patterns)),
            env=env,
            signature=inspect.signature(py_fn) if py_fn is not None else None,
        )
        self.clauses.append(clause)
        # Descending specificity; same-score clauses keep declaration order.
        # `list.sort` is stable even with reverse=True, and clauses are
        # appended in declaration order, so ties preserve it on their own —
        # no secondary key needed. (Negating the score, as this used to do,
        # is not possible now that a score is a nested tuple.)
        #
        # A guarded clause scores exactly as its unguarded twin does, so
        # the two tie and declaration order decides: **guarded clauses must
        # be written first**. That is deliberate. A guard's narrowness is a
        # runtime fact, and there is nowhere in a per-argument specificity
        # vector to record "and also this predicate holds" — inventing a
        # guarded-beats-unguarded tiebreak would order clauses by something
        # `score()` cannot actually compare.
        self.clauses.sort(key=lambda c: c.specificity, reverse=True)
        return clause

    def select(self, args: tuple, ctx) -> tuple[Clause, dict]:
        """The first clause, in rank order, whose patterns match `args` and
        whose guard holds -- with the bindings the match produced.

        `ctx` is the call site's evaluation context. Guards of a clause
        defined in Minimatic evaluate in that clause's own scope instead.
        """
        self.sealed = True
        for clause in self.clauses:
            clause_ctx = ctx if clause.env is None else ctx.with_env(clause.env)
            bindings = match_all(clause.arg_patterns, args, ctx=clause_ctx)
            if bindings is None:
                continue
            if clause.guard is not None and not eval_guard(clause.guard, bindings, clause_ctx):
                # Fall through to the next clause, never raise: a guard
                # that says "not this one" is an ordinary dispatch outcome.
                continue
            return clause, bindings
        raise NoMatchingClauseError(self.head_name, args)

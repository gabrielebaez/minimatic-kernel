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
from .ast.patterns import Blank, BlankNullSeq, BlankSeq, PatternBind
from .ast.symbol import Symbol
from .errors import (
    ArityError,
    HeadAlreadySealedError,
    MinimaticError,
    MinimaticTypeError,
    NoMatchingClauseError,
)
from .match import match_all

# Python exceptions a builtin may raise that mean "bad data", as opposed to
# "the kernel has a bug". Deliberately narrow: AttributeError and friends
# still surface as themselves rather than being disguised as user errors.
_DATA_ERRORS = (ValueError, ZeroDivisionError, IndexError, KeyError)


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


def _arity_of(sig: inspect.Signature) -> str:
    """Human-readable arity of a builtin, ignoring the injected `ctx`."""
    params = [p for name, p in sig.parameters.items() if name != "ctx"]
    positional = [
        p
        for p in params
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    required = sum(1 for p in positional if p.default is p.empty)
    if any(p.kind is p.VAR_POSITIONAL for p in params):
        return f"at least {required}"
    if len(positional) != required:
        return f"{required} to {len(positional)}"
    return str(required)


@dataclass
class Clause:
    arg_patterns: tuple
    body: object = None
    py_fn: Callable | None = None
    pass_ctx: bool = False
    specificity: tuple = field(default=())
    order: int = 0
    # Cached at definition time, used only on the failure path (see
    # ClauseSet._call_py) to tell an arity mistake from a type mistake.
    signature: inspect.Signature | None = None


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
            signature=inspect.signature(py_fn) if py_fn is not None else None,
        )
        self.clauses.append(clause)
        # Descending specificity; same-score clauses keep declaration order.
        # `list.sort` is stable even with reverse=True, and clauses are
        # appended in declaration order, so ties preserve it on their own —
        # no secondary key needed. (Negating the score, as this used to do,
        # is not possible now that a score is a nested tuple.)
        self.clauses.sort(key=lambda c: c.specificity, reverse=True)
        return clause

    def apply(self, args, env, evaluator: Callable, ctx=None):
        self.sealed = True
        args = tuple(args)
        for clause in self.clauses:
            bindings = match_all(clause.arg_patterns, args)
            if bindings is None:
                continue
            if clause.py_fn is not None:
                return self._call_py(clause, args, ctx)
            return evaluator(clause.body, env.extend(bindings))
        raise NoMatchingClauseError(self.head_name, args)

    def _call_py(self, clause: Clause, args: tuple, ctx):
        """Invoke a Python-backed clause, keeping every failure inside the
        `MinimaticError` hierarchy.

        This is the single place builtins are called, so it is the only
        place that has to know how. Before this, three kinds of failure
        escaped as raw Python exceptions — a wrong-arity call, a bad
        argument type (`plus(1, "a")`), and division by zero — so host code
        catching "any Minimatic problem" silently missed them.

        Classification happens *only* on the failure path: the call is
        attempted first, so a successful dispatch pays nothing.
        """
        try:
            if clause.pass_ctx:
                return clause.py_fn(*args, ctx=ctx)
            return clause.py_fn(*args)
        except MinimaticError:
            raise  # already ours, and already well-described
        except TypeError as exc:
            raise self._classify_type_error(clause, args, exc) from exc
        except _DATA_ERRORS as exc:
            raise MinimaticTypeError(f"{self.head_name}: {exc}") from exc

    def _classify_type_error(self, clause: Clause, args: tuple, exc: TypeError):
        """Was that TypeError the call itself not fitting the signature, or
        something going wrong inside it? Re-binding the arguments answers
        it without depending on CPython's error wording."""
        sig = clause.signature
        if sig is not None:
            try:
                if clause.pass_ctx:
                    sig.bind(*args, ctx=None)
                else:
                    sig.bind(*args)
            except TypeError:
                return ArityError(self.head_name, _arity_of(sig), len(args))
        return MinimaticTypeError(f"{self.head_name}: {exc}")

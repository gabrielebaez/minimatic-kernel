"""
Eval - Single-pass tree-walking evaluator.

No evaluation fixpoint loop (kernel doc §4.1): a node is evaluated once,
producing a normal-form node of the same tree type. This is a permanent
architectural property, not something the MVP is cutting.

Deviation from the literal kernel-doc pseudocode, called out explicitly:
`Symbol` lookup first checks the environment, then falls back to treating
the symbol as a self-evaluating reference to a registered head (returning
the Symbol itself) before finally raising UnboundSymbolError. This is what
lets `fold(plus, 0, xs)` work — `plus` is a head name, not a variable, and
has no env binding, yet needs to evaluate to *something* passable as a
value. Without this fallback the language's own flagship example
(`docs/the kernel.md`, README) could not run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .ast.expression import Expression
from .ast.symbol import Symbol
from .attributes import Hold, HoldAll, HoldAllComplete, HoldFirst, HoldRest, Listable
from .env import Env
from .errors import ArityError, MinimaticTypeError, UnboundSymbolError, UnknownHeadError
from .registry import Registry

_ATOMIC_TYPES = (int, float, str, bool, type(None))
_FULL_HOLD = {Hold, HoldAll, HoldAllComplete}


def is_held(attrs: frozenset, i: int) -> bool:
    if attrs & _FULL_HOLD:
        return True
    if HoldFirst in attrs and i == 0:
        return True
    if HoldRest in attrs and i > 0:
        return True
    return False


def _thread_listable(args: list) -> list[tuple] | None:
    """
    If a Listable head is called with one or more List-valued arguments,
    return the per-row argument tuples to apply it to elementwise
    (non-list args broadcast as scalars across every row). Returns None
    if no argument is a List (nothing to thread).

    This is what makes `x^2` work when `x` is bound to a whole list by a
    trivially-matching rewrite-rule pattern (`docs/the kernel.md`'s own
    `[1,2,3,4] /. x: _ -> x^2` example) — `Power` threads over the list
    the same way it would in the full design.
    """
    list_positions = [
        i for i, a in enumerate(args) if isinstance(a, Expression) and a.head == Symbol("List")
    ]
    if not list_positions:
        return None

    length = len(args[list_positions[0]].tail)
    for i in list_positions:
        if len(args[i].tail) != length:
            raise MinimaticTypeError("Listable: argument lists have mismatched lengths")

    rows = []
    for idx in range(length):
        row = list(args)
        for i in list_positions:
            row[i] = args[i].tail[idx]
        rows.append(tuple(row))
    return rows


class Evaluator:
    def __init__(self, registry: Registry):
        self.registry = registry

    def eval(self, node, env: Env):
        if isinstance(node, _ATOMIC_TYPES):
            return node

        if isinstance(node, Symbol):
            if env.has(node.name):
                return env.lookup(node.name)
            if self.registry.has_head(node.name):
                return node
            raise UnboundSymbolError(node.name)

        if isinstance(node, Expression):
            return self._eval_expr(node, env)

        # Pattern nodes (Blank, PatternBind, ...) are inert if ever reached
        # directly by eval — they only have meaning as static shape, never
        # as something to reduce.
        return node

    def _eval_expr(self, node: Expression, env: Env):
        head = node.head
        head_val = head if isinstance(head, Symbol) else self.eval(head, env)

        if isinstance(head_val, Symbol):
            clause_set = self.registry.resolve(head_val.name)
            if clause_set is None:
                # Not a registered head — but it might be a plain variable
                # holding a callable value, e.g. `add5 = add(5)` followed
                # by `add5(10)`. Registered heads take priority (the
                # common case), env-bound callables are the fallback.
                if env.has(head_val.name):
                    callee = env.lookup(head_val.name)
                    eval_args = [self.eval(arg, env) for arg in node.tail]
                    return self.apply_value(callee, eval_args, env)
                raise UnknownHeadError(head_val.name)

            attrs = self.registry.attributes(head_val.name)
            eval_args = [
                arg if is_held(attrs, i) else self.eval(arg, env)
                for i, arg in enumerate(node.tail)
            ]

            ctx = Ctx(env, self)
            if Listable in attrs:
                rows = _thread_listable(eval_args)
                if rows is not None:
                    results = [
                        clause_set.apply(list(row), env, self.eval, ctx=ctx) for row in rows
                    ]
                    return Expression(Symbol("List"), *results)
            return clause_set.apply(eval_args, env, self.eval, ctx=ctx)

        # Non-Symbol head: the result of a prior call (e.g. a Closure
        # returned by another call, as in curried application
        # `add(5)(3)`). No attribute table exists for an anonymous
        # callable value, so its arguments simply evaluate normally, then
        # dispatch through the same apply_value() path map/fold use.
        eval_args = [self.eval(arg, env) for arg in node.tail]
        return self.apply_value(head_val, eval_args, env)

    def apply_value(self, fn_value, arg_values: list, env: Env):
        """
        Apply a Minimatic 'callable' value to already-evaluated arguments.
        Supports the two callable shapes the MVP prelude produces/accepts:
        a Closure (from evaluating a Lambda) and a bare Symbol naming a
        registered head (e.g. `plus` passed into `fold`).
        """
        if isinstance(fn_value, Expression) and fn_value.head == Symbol("Closure"):
            param, body, captured_env = fn_value.tail
            if len(arg_values) != 1:
                raise ArityError("<lambda>", "1", len(arg_values))
            extended = captured_env.extend({param.name: arg_values[0]})
            return self.eval(body, extended)

        if isinstance(fn_value, Symbol):
            clause_set = self.registry.resolve(fn_value.name)
            if clause_set is None:
                raise UnknownHeadError(fn_value.name)
            ctx = Ctx(env, self)
            return clause_set.apply(list(arg_values), env, self.eval, ctx=ctx)

        raise MinimaticTypeError(f"{fn_value!r} is not callable")


@dataclass
class Ctx:
    """Handed to Python builtins registered with pass_ctx=True, so they can
    recurse back into evaluation (needed for higher-order heads like `map`
    and `fold`, and for heads like `SetDelayed` that need registry access)."""

    env: Env
    evaluator: Evaluator

    @property
    def registry(self):
        return self.evaluator.registry

    def eval(self, node, env: Env | None = None):
        return self.evaluator.eval(node, env if env is not None else self.env)

    def apply(self, fn_value, arg_values: list, env: Env | None = None):
        return self.evaluator.apply_value(
            fn_value, arg_values, env if env is not None else self.env
        )

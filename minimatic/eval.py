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

import inspect
from dataclasses import dataclass

from .ast.expression import Expression
from .ast.symbol import Symbol
from .attributes import Hold, HoldAll, HoldAllComplete, HoldFirst, HoldRest, Listable
from .env import Env
from .errors import (
    ArityError,
    MinimaticError,
    MinimaticTypeError,
    UnboundSymbolError,
    UnknownHeadError,
)
from .registry import Registry

_ATOMIC_TYPES = (int, float, str, bool, type(None))
_CLOSURE = Symbol("Closure")

# Python exceptions a builtin may raise that mean "bad data", as opposed to
# "the kernel has a bug". Deliberately narrow: AttributeError and friends
# still surface as themselves rather than being disguised as user errors.
_DATA_ERRORS = (ValueError, ZeroDivisionError, IndexError, KeyError)
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


def make_closure(param: Symbol, body, env: Env) -> Expression:
    """The value a lambda evaluates to. Built here, next to the only code
    that takes one apart (`Evaluator.apply_value`), so the layout of a
    Closure is known in exactly one module."""
    return Expression(_CLOSURE, param, body, env)


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
            return self._apply_head(clause_set, attrs, eval_args, env)

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
        if isinstance(fn_value, Expression) and fn_value.head == _CLOSURE:
            param, body, captured_env = fn_value.tail
            if len(arg_values) != 1:
                raise ArityError("<lambda>", "1", len(arg_values))
            extended = captured_env.extend({param.name: arg_values[0]})
            return self.eval(body, extended)

        if isinstance(fn_value, Symbol):
            clause_set = self.registry.resolve(fn_value.name)
            if clause_set is None:
                raise UnknownHeadError(fn_value.name)
            attrs = self.registry.attributes(fn_value.name)
            return self._apply_head(clause_set, attrs, list(arg_values), env)

        raise MinimaticTypeError(f"{fn_value!r} is not callable")

    def _apply_head(self, clause_set, attrs: frozenset, args: list, env: Env):
        """Apply a registered head to arguments that have already been
        evaluated (or deliberately held). Every route to a head ends here --
        a written call, a head passed as a value to `map`/`fold`, a curried
        call, a pipe -- so `Listable` threading cannot depend on which one
        it was."""
        if Listable in attrs:
            rows = _thread_listable(args)
            if rows is not None:
                return Expression(
                    Symbol("List"),
                    *(self._apply_head(clause_set, frozenset(), list(row), env) for row in rows),
                )
        ctx = Ctx(env, self)
        clause, bindings = clause_set.select(tuple(args), ctx)
        if clause.py_fn is not None:
            return _call_builtin(clause_set.head_name, clause, tuple(args), ctx)
        return self.eval(clause.body, clause.env.extend(bindings))


def _call_builtin(head_name: str, clause, args: tuple, ctx):
    """Invoke a Python-backed clause, keeping every failure inside the
    `MinimaticError` hierarchy.

    This is the single place builtins are called, so it is the only place
    that has to know how. Before this, three kinds of failure escaped as
    raw Python exceptions — a wrong-arity call, a bad argument type
    (`plus(1, "a")`), and division by zero — so host code catching "any
    Minimatic problem" silently missed them.

    Classification happens *only* on the failure path: the call is
    attempted first, so a successful call pays nothing.
    """
    try:
        if clause.pass_ctx:
            return clause.py_fn(*args, ctx=ctx)
        return clause.py_fn(*args)
    except MinimaticError:
        raise  # already ours, and already well-described
    except TypeError as exc:
        raise _classify_type_error(head_name, clause, args, exc) from exc
    except _DATA_ERRORS as exc:
        raise MinimaticTypeError(f"{head_name}: {exc}") from exc


def _classify_type_error(head_name: str, clause, args: tuple, exc: TypeError):
    """Was that TypeError the call itself not fitting the signature, or
    something going wrong inside it? Re-binding the arguments answers it
    without depending on CPython's error wording."""
    sig: inspect.Signature | None = clause.signature
    if sig is not None:
        try:
            if clause.pass_ctx:
                sig.bind(*args, ctx=None)
            else:
                sig.bind(*args)
        except TypeError:
            return ArityError(head_name, _arity_of(sig), len(args))
    return MinimaticTypeError(f"{head_name}: {exc}")


@dataclass
class Ctx:
    """What a Python builtin registered with pass_ctx=True gets: enough to
    evaluate, apply, and define, without reaching into the registry.

    `env` is the call site's scope. Higher-order heads (`map`, `fold`)
    recurse through `eval`/`apply`; `SetDelayed` defines through `define`,
    which captures this scope for the new clause; the pipe reads
    `attributes` to decide whether to short-circuit an `Err`.
    """

    env: Env
    evaluator: Evaluator

    def eval(self, node, env: Env | None = None):
        return self.evaluator.eval(node, env if env is not None else self.env)

    def apply(self, fn_value, arg_values: list, env: Env | None = None):
        return self.evaluator.apply_value(
            fn_value, arg_values, env if env is not None else self.env
        )

    def attributes(self, head_name: str) -> frozenset:
        return self.evaluator.registry.attributes(head_name)

    def define(self, head_name: str, arg_patterns, body, guard=None) -> None:
        """Add a clause to `head_name`, defined in this context's scope."""
        self.evaluator.registry.get_or_create(head_name).define(
            arg_patterns, body=body, guard=guard, env=self.env
        )

    def with_env(self, env: Env) -> "Ctx":
        """The same context, evaluating in `env` instead -- how a clause's
        guards come to run in the scope the clause was defined in."""
        return Ctx(env, self.evaluator)

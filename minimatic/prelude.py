"""
Prelude - Registers the MVP's built-in heads.

Split into two groups:
  - "Special forms that aren't" (Set, SetDelayed, Lambda, Rule, ReplaceAll):
    ordinary registered heads with Hold attributes, not privileged syntax.
    They need `ctx` (env / evaluator access) to do their job.
  - Ordinary data/arithmetic heads: plain Python functions, no ctx needed.

See IMPLEMENTATION_PLAN.md for what's deferred (Flat/Orderless, Dict,
filter/reduce, string ops, the self-hosting derived prelude, ...).
"""

from __future__ import annotations

from .ast.expression import Expression
from .ast.symbol import Symbol
from .attributes import HoldAll, HoldFirst, HoldRest, Listable
from .errors import MinimaticSyntaxError, MinimaticTypeError
from .extend import register_head
from .rewrite import extract_rules, replace_all


# ---------------------------------------------------------------- forms --


def _impl_set(name_sym, value, ctx=None):
    if not isinstance(name_sym, Symbol):
        raise MinimaticSyntaxError("left-hand side of '=' must be a plain symbol")
    ctx.env.set_here(name_sym.name, value)
    return value


def _impl_set_delayed(lhs_call, body, ctx=None):
    if not (isinstance(lhs_call, Expression) and isinstance(lhs_call.head, Symbol)):
        raise MinimaticSyntaxError(
            "left-hand side of ':=' must be a function pattern like f(x: _int)"
        )
    head_name = lhs_call.head.name
    clause_set = ctx.registry.get_or_create(head_name)
    clause_set.define(lhs_call.tail, body=body)
    return lhs_call.head


def _impl_lambda(param, body, ctx=None):
    if not isinstance(param, Symbol):
        raise MinimaticSyntaxError("MVP lambdas take a single plain symbol parameter")
    return Expression(Symbol("Closure"), param, body, ctx.env)


def _impl_rule(lhs, rhs, ctx=None):
    return Expression(Symbol("Rule"), lhs, rhs)


def _impl_replace_all(value, rule_expr, ctx=None):
    rules = extract_rules(rule_expr)
    return replace_all(value, rules, ctx)


def _impl_pipe(lhs_val, rhs_raw, ctx=None):
    """`a |> f` / `a |> f(b, c)` desugars, at eval time, to `f(a)` /
    `f(a, b, c)` (fixed first-position, per IMPLEMENTATION_PLAN.md's locked
    decision). `rhs_raw` arrives unevaluated (HoldRest) specifically so we
    can splice `lhs_val` into the call *before* dispatch runs, rather than
    evaluating the call first and trying to combine results after."""
    if isinstance(rhs_raw, Expression):
        spliced = Expression(rhs_raw.head, lhs_val, *rhs_raw.tail)
    elif isinstance(rhs_raw, Symbol):
        spliced = Expression(rhs_raw, lhs_val)
    else:
        raise MinimaticTypeError(f"right-hand side of '|>' must be callable, got {rhs_raw!r}")
    return ctx.eval(spliced)


# ------------------------------------------------------------------ data --


def _check_list(value, who):
    if not (isinstance(value, Expression) and value.head == Symbol("List")):
        raise MinimaticTypeError(f"{who}: expected a List, got {value!r}")


def _impl_list(*args):
    return Expression(Symbol("List"), *args)


def _impl_length(list_expr):
    _check_list(list_expr, "length")
    return len(list_expr.tail)


def _impl_head(list_expr):
    _check_list(list_expr, "head")
    if not list_expr.tail:
        raise MinimaticTypeError("head: empty list")
    return list_expr.tail[0]


def _impl_tail(list_expr):
    _check_list(list_expr, "tail")
    return Expression(Symbol("List"), *list_expr.tail[1:])


def _impl_append(list_expr, value):
    _check_list(list_expr, "append")
    return Expression(Symbol("List"), *list_expr.tail, value)


def _impl_map(list_expr, fn_value, ctx=None):
    # list-first parameter order: `xs |> map(f)` desugars to `map(xs, f)`
    # (fixed first-position pipe splicing), which is the only call shape
    # the MVP acceptance bar exercises.
    _check_list(list_expr, "map")
    results = [ctx.apply(fn_value, [item]) for item in list_expr.tail]
    return Expression(Symbol("List"), *results)


def _impl_fold(list_expr, fn_value, initial, ctx=None):
    # list-first, matching `xs |> fold(f, init)` -> `fold(xs, f, init)`.
    _check_list(list_expr, "fold")
    acc = initial
    for item in list_expr.tail:
        acc = ctx.apply(fn_value, [acc, item])
    return acc


# ------------------------------------------------------------ arithmetic --


def _impl_plus(*args):
    return sum(args)


def _impl_minus(a, b):
    return a - b


def _impl_times(*args):
    result = 1
    for a in args:
        result *= a
    return result


def _impl_divide(a, b):
    return a / b


def _impl_power(a, b):
    return a**b


def _impl_mod(a, b):
    return a % b


def _impl_negate(a):
    return -a


def _impl_equal(a, b):
    return type(a) is type(b) and a == b


def _impl_not_equal(a, b):
    return not _impl_equal(a, b)


def _impl_less(a, b):
    return a < b


def _impl_greater(a, b):
    return a > b


def _impl_less_eq(a, b):
    return a <= b


def _impl_greater_eq(a, b):
    return a >= b


def register_prelude(registry) -> None:
    register_head(registry, "Set", _impl_set, attributes=[HoldFirst], pass_ctx=True)
    register_head(registry, "SetDelayed", _impl_set_delayed, attributes=[HoldAll], pass_ctx=True)
    register_head(registry, "Lambda", _impl_lambda, attributes=[HoldAll], pass_ctx=True)
    register_head(registry, "Rule", _impl_rule, attributes=[HoldAll], pass_ctx=True)
    register_head(registry, "ReplaceAll", _impl_replace_all, attributes=[HoldRest], pass_ctx=True)
    register_head(registry, "__pipe__", _impl_pipe, attributes=[HoldRest], pass_ctx=True)

    register_head(registry, "List", _impl_list)
    register_head(registry, "length", _impl_length)
    register_head(registry, "head", _impl_head)
    register_head(registry, "tail", _impl_tail)
    register_head(registry, "append", _impl_append)
    register_head(registry, "map", _impl_map, pass_ctx=True)
    register_head(registry, "fold", _impl_fold, pass_ctx=True)

    register_head(registry, "plus", _impl_plus, attributes=[Listable])
    register_head(registry, "minus", _impl_minus, attributes=[Listable])
    register_head(registry, "times", _impl_times, attributes=[Listable])
    register_head(registry, "divide", _impl_divide, attributes=[Listable])
    register_head(registry, "power", _impl_power, attributes=[Listable])
    register_head(registry, "mod", _impl_mod, attributes=[Listable])
    register_head(registry, "negate", _impl_negate, attributes=[Listable])

    register_head(registry, "equal", _impl_equal)
    register_head(registry, "not_equal", _impl_not_equal)
    register_head(registry, "less", _impl_less)
    register_head(registry, "greater", _impl_greater)
    register_head(registry, "less_eq", _impl_less_eq)
    register_head(registry, "greater_eq", _impl_greater_eq)

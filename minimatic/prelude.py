"""
Prelude - Registers the MVP's built-in heads.

Split into two groups:
  - "Special forms that aren't" (Set, SetDelayed, Lambda, Rule, ReplaceAll):
    ordinary registered heads with Hold attributes, not privileged syntax.
    They need `ctx` (env / evaluator access) to do their job.
  - Ordinary data/arithmetic heads: plain Python functions, no ctx needed.

See IMPLEMENTATION_PLAN.md for what's deferred (Dict, filter/reduce,
string ops, the self-hosting derived prelude, ...). `Flat`/`Orderless`
are not deferred but removed outright — see
docs/proposal-001-dispatch-results-and-pipes.md §2.3.
"""

from __future__ import annotations

from .ast.atoms import is_integer
from .ast.expression import Expression, head_of, tail_of
from .ast.patterns import Condition
from .ast.symbol import Symbol
from .attributes import HoldAll, HoldFirst, HoldRest, Listable, ResultAware
from .errors import MinimaticSyntaxError, MinimaticTypeError
from .extend import register_head
from .result import err, is_err_value
from .rewrite import extract_rules, looks_like_rules, replace_all, replace_repeated


# ---------------------------------------------------------------- forms --


def _impl_set(name_sym, value, ctx=None):
    if not isinstance(name_sym, Symbol):
        raise MinimaticSyntaxError("left-hand side of '=' must be a plain symbol")
    ctx.env.set_here(name_sym.name, value)
    return value


def _impl_set_delayed(lhs_call, body, ctx=None):
    # `f(x: _) /; x > 0 := body` — a clause-level guard. SetDelayed is
    # HoldAll, so the Condition node arrives intact; unwrap it here so the
    # arity/shape check below still sees the plain call pattern, and the
    # guard travels to the Clause rather than into the argument patterns.
    guard = None
    if isinstance(lhs_call, Condition):
        lhs_call, guard = lhs_call.pattern, lhs_call.guard

    if not (isinstance(lhs_call, Expression) and isinstance(lhs_call.head, Symbol)):
        raise MinimaticSyntaxError(
            "left-hand side of ':=' must be a function pattern like f(x: _int)"
        )
    head_name = lhs_call.head.name
    clause_set = ctx.registry.get_or_create(head_name)
    clause_set.define(lhs_call.tail, body=body, guard=guard)
    return lhs_call.head


def _impl_lambda(param, body, ctx=None):
    if not isinstance(param, Symbol):
        raise MinimaticSyntaxError("MVP lambdas take a single plain symbol parameter")
    return Expression(Symbol("Closure"), param, body, ctx.env)


def _impl_rule(lhs, rhs, ctx=None):
    return Expression(Symbol("Rule"), lhs, rhs)


def _impl_rule_delayed(lhs, rhs, ctx=None):
    # HoldAll like `Rule`, and for a sharper reason: a delayed rule's whole
    # purpose is that its RHS has not been evaluated.
    return Expression(Symbol("RuleDelayed"), lhs, rhs)


def _resolve_rules(rule_expr, ctx):
    """`ReplaceAll`/`ReplaceRepeated` are HoldRest, so the rule argument
    arrives unevaluated — necessary, or a pattern LHS would evaluate before
    it could match. A rule that was *computed* rather than written out
    (`expr /. rule`, `expr /. rules_for(x)`) therefore arrives as an
    unevaluated symbol or call, and has to be evaluated here."""
    return extract_rules(rule_expr if looks_like_rules(rule_expr) else ctx.eval(rule_expr))


def _impl_replace_all(value, rule_expr, ctx=None):
    return replace_all(value, _resolve_rules(rule_expr, ctx), ctx)


def _impl_replace_repeated(value, rule_expr, ctx=None):
    return replace_repeated(value, _resolve_rules(rule_expr, ctx), ctx)


# ----------------------------------------------------------- held code --
#
# The three-step cycle docs/the language.md §11 is built on: `Hold`
# captures, `/.` (or `//.`) rewrites, `ReleaseHold` re-enters evaluation.
# Rewriting is scoped to exactly these names — if none of them appears in a
# piece of code, that code's evaluation involves no rewriting at all.


def _impl_hold(expr, ctx=None):
    # `Hold` names both a head (here) and an evaluation attribute
    # (minimatic/attributes.py). The collision is nominal: attributes are
    # keyed by head name in the registry, and this head's own attribute set
    # is `{HoldAll}`. Not a clash to "fix".
    #
    # Deliberately two elements, with no captured environment: a held
    # expression stays structurally identical to ordinary data, so
    # `x /. Hold(e: _) -> ...` matches it like anything else, and `Hold`
    # stays the zero-cost operation docs/the kernel.md §2.3 promises.
    return Expression(Symbol("Hold"), expr)


def _impl_release_hold(value, ctx=None):
    """Strip one `Hold` and evaluate what was inside it.

    Evaluated **in the environment it is released in**, not one captured at
    `Hold` time (docs/the language.md §16.4). One layer per release, so
    `ReleaseHold(Hold(Hold(e)))` is `Hold(e)`; anything that is not a
    `Hold` comes back unchanged, which keeps this total.

    Not held itself: its argument evaluates normally, which is what lets
    `ReleaseHold(rewritten)` work on a name bound to a held expression.
    """
    if isinstance(value, Expression) and value.head == Symbol("Hold") and len(value.tail) == 1:
        return ctx.eval(value.tail[0])
    return value


_DOLLAR = Symbol("$")
_PIPE = Symbol("__pipe__")


def _substitute_dollar(node, value):
    """Replace every free `$` in `node` with `value`. Returns (node, found).

    `found` is what tells `_impl_pipe` which of the two pipe forms it is
    looking at, so it has to be exact: it is True only if a `$` was
    actually replaced.

    Substitution reaches any depth — including into a nested Lambda's body,
    so `xs |> zip_with(ys, (a, b) -> f(a, b, $))` sees the piped subject.
    The one exception is a nested `__pipe__`'s right-hand side: that `$`
    belongs to the inner pipe and is resolved when the inner pipe evaluates
    (proposal-001 §2.8 rule 4). The inner pipe's left-hand side is ordinary
    ground and is substituted normally.
    """
    if isinstance(node, Symbol):
        return (value, True) if node == _DOLLAR else (node, False)

    if not isinstance(node, Expression):
        return node, False

    if node.head == _PIPE and len(node.tail) == 2:
        inner_lhs, found = _substitute_dollar(node.tail[0], value)
        if not found:
            return node, False
        return Expression(node.head, inner_lhs, node.tail[1]), True

    new_head, found = _substitute_dollar(node.head, value)
    new_args = []
    for arg in node.tail:
        new_arg, arg_found = _substitute_dollar(arg, value)
        found = found or arg_found
        new_args.append(new_arg)
    if not found:
        return node, False
    return Expression(new_head, *new_args), True


def _target_is_result_aware(rhs_raw, ctx) -> bool:
    """Is the pipe's target head allowed to receive an `Err` directly?

    A `Lambda` right-hand side has no head at all, so it is never
    `ResultAware` — an `Err` subject skips it rather than being handed to
    a user lambda that has no way to know it got one.
    """
    head = None
    if isinstance(rhs_raw, Symbol):
        head = rhs_raw
    elif isinstance(rhs_raw, Expression):
        if rhs_raw.head == Symbol("Lambda"):
            return False
        if isinstance(rhs_raw.head, Symbol):
            head = rhs_raw.head
    if head is None:
        return False
    return ResultAware in ctx.registry.attributes(head.name)


def _impl_pipe(lhs_val, rhs_raw, ctx=None):
    """`a |> f` / `a |> f(b, c)` / `a |> f(b, $, c)`.

    Two forms, distinguished by whether the right-hand side mentions `$`
    (proposal-001 §2.8):

      - **no `$`** — first-position splice: `a |> f(b, c)` is `f(a, b, c)`.
      - **any `$`** — template substitution: `a |> f(b, $)` is `f(b, a)`.
        First-position splicing is *not* also applied.

    `rhs_raw` arrives unevaluated (HoldRest) so both forms can rebuild the
    call *before* dispatch runs, rather than evaluating it first and trying
    to combine results after. `lhs_val` arrives already evaluated, which is
    what makes "the subject is evaluated exactly once" structural rather
    than a rule to enforce — substitution copies a value, it never re-runs
    an expression, however many times `$` appears.

    Wolfram's postfix `//` parses to this same head: `a // f` is `a |> f`,
    both forms included."""
    # Short-circuit first — before the Lambda branch, and before `$`
    # substitution. A skipped pipe must not apply a user lambda to an
    # error, and must not evaluate the template's other arguments either.
    if is_err_value(lhs_val) and not _target_is_result_aware(rhs_raw, ctx):
        return lhs_val

    if isinstance(rhs_raw, Expression) and rhs_raw.head == Symbol("Lambda"):
        # `a |> (x -> ...)` / `a // (x -> ...)`: the right side *is* the
        # function, not a call to splice an argument into — evaluate it to
        # a Closure and apply that to `a`. A `$` in a Lambda right-hand
        # side is therefore never substituted; it stays unbound.
        return ctx.apply(ctx.eval(rhs_raw), [lhs_val])
    if isinstance(rhs_raw, Expression):
        substituted, found = _substitute_dollar(rhs_raw, lhs_val)
        if found:
            return ctx.eval(substituted)
        spliced = Expression(rhs_raw.head, lhs_val, *rhs_raw.tail)
    elif isinstance(rhs_raw, Symbol):
        spliced = Expression(rhs_raw, lhs_val)
    else:
        raise MinimaticTypeError(
            f"right-hand side of '|>' / '//' must be callable, got {rhs_raw!r}"
        )
    return ctx.eval(spliced)


# ------------------------------------------------------------- control flow --
#
# `if`, `switch`, `which`, `for`, `each` are ordinary registered heads, not
# special forms in the grammar (docs/the language.md §4: "There is no
# control-flow construct in Minimatic that a register_head-registered
# Python function couldn't, in principle, also define"). Branches are
# skipped by *not evaluating* the unchosen argument expressions, using
# each head's own hold behavior — never a hard-coded evaluator case.


def _impl_if(cond, then_raw, else_raw, ctx=None):
    # HoldRest: `cond` (index 0) is evaluated normally; `then`/`else`
    # arrive raw so only the taken branch ever gets evaluated.
    if not isinstance(cond, bool):
        raise MinimaticTypeError(f"if: condition must be a bool, got {cond!r}")
    return ctx.eval(then_raw if cond else else_raw)


def _impl_switch(x_raw, *rest_raw, ctx=None):
    """`switch(x, case1, result1, case2, result2, ..., [default])`.
    HoldAll: nothing but `x` and the *matching* case/result pair is ever
    evaluated — cases are evaluated one at a time as they're checked
    (so a case can itself be a computed expression), results stay
    unevaluated until the moment their case wins."""
    x = ctx.eval(x_raw)
    i = 0
    while i + 1 < len(rest_raw):
        case_val = ctx.eval(rest_raw[i])
        if type(case_val) is type(x) and case_val == x:
            return ctx.eval(rest_raw[i + 1])
        i += 2
    if i < len(rest_raw):  # trailing default, no case attached to it
        return ctx.eval(rest_raw[i])
    raise MinimaticTypeError(f"switch: no matching case for {x!r}")


def _impl_which(*args_raw, ctx=None):
    """`which(cond1, result1, cond2, result2, ..., [default])` — a plain
    cond/elif chain. HoldAll: conditions are evaluated one at a time,
    in order, until one is true; only the winning result is evaluated."""
    i = 0
    while i + 1 < len(args_raw):
        cond = ctx.eval(args_raw[i])
        if not isinstance(cond, bool):
            raise MinimaticTypeError(f"which: condition must be a bool, got {cond!r}")
        if cond:
            return ctx.eval(args_raw[i + 1])
        i += 2
    if i < len(args_raw):
        return ctx.eval(args_raw[i])
    raise MinimaticTypeError("which: no condition matched and no default given")


def _impl_for(list_expr, fn_value, ctx=None):
    # No hold attributes: `list_expr`/`fn_value` are ordinary values,
    # same convention as map/fold. Unlike map, the per-element results are
    # discarded — `for`/`each` are for side effects, `map` is for
    # transforming data; returns Null (Python None).
    _check_list(list_expr, "for")
    for item in list_expr.tail:
        ctx.apply(fn_value, [item])
    return None


def _impl_each(list_expr, fn_value, ctx=None):
    return _impl_for(list_expr, fn_value, ctx=ctx)


def _impl_compound_expression(*args):
    # `(stmt1; stmt2; ...)` — ordinary eager evaluation already runs every
    # argument in order for effect (Python's list-comprehension arg
    # evaluation in eval.py), so this just needs to keep the last value.
    return args[-1] if args else None


def _impl_print(value):
    # Returns its argument so it composes in a pipe for debugging
    # (`xs |> print |> map(f)`), as docs/the prelude.md §12 has always
    # said. The REPL double-print this used to avoid is handled in the
    # CLI instead (see minimatic/__main__.py), rather than by crippling
    # the head.
    print(value)
    return value


# ------------------------------------------------------------------ result --
#
# Success is the value itself; failure is an `Err`. See minimatic/result.py
# for the line between these and kernel exceptions. Every head here is
# ResultAware: receiving an Err is the whole point, so the pipe must not
# skip them.


def _impl_err(kind, detail=None):
    # Normalizes a one-argument call to two, so `Err(k: _, d: _)` matches
    # every Err there is.
    return err(kind, detail)


def _impl_is_err(value):
    return is_err_value(value)


def _impl_unwrap(value, default):
    return default if is_err_value(value) else value


def _impl_unwrap_err(value):
    """The `Err`'s detail. Asserting the value *is* an error is half the
    point, so a non-error is a programming mistake, not another `Err`."""
    if not is_err_value(value):
        raise MinimaticTypeError(f"unwrap_err: expected an Err, got {value!r}")
    return value.tail[1]


def _impl_catch(value, kind, handler, ctx=None):
    if not is_err_value(value) or value.tail[0] != kind:
        return value  # not an error, or not this kind -- pass through
    return ctx.apply(handler, [value])


def _impl_recover(value, handler, ctx=None):
    if not is_err_value(value):
        return value
    return ctx.apply(handler, [value])


def _impl_finally(value, fn, ctx=None):
    ctx.apply(fn, [value])
    return value


def _impl_range(lo, hi):
    # `a..b` -> [a, a+1, ..., b-1] (half-open, matches docs/the language.md §6.2)
    if not (is_integer(lo) and is_integer(hi)):
        raise MinimaticTypeError(f"Range: bounds must be integers, got {lo!r}, {hi!r}")
    return Expression(Symbol("List"), *range(lo, hi))


# ------------------------------------------------------------------ data --


# --------------------------------------------------- structure inspection --
#
# `Head`/`Args` are PascalCase per docs/the prelude.md §2.4: they inspect
# the language's own structure rather than processing data. They are also
# why the list accessors are named `first`/`rest` — with `Head` meaning the
# head of an expression, the word "head" has exactly one meaning in the
# language, the one docs/the language.md §4 is built on.


def _impl_head_symbol(value):
    # Total: every value has a head, including `[]` (-> List) and atoms
    # (5 -> Integer, "hi" -> String). No empty case to signal.
    return head_of(value)


def _impl_args(value):
    # `tail_of` yields a raw tuple; wrap it as a List so the result is an
    # ordinary Minimatic value. Atoms have no arguments, giving `[]`.
    return Expression(Symbol("List"), *tail_of(value))


# The symbols `head_of` returns for atoms. Bound as values (see
# `bind_prelude_constants`) so `Head(5) == Integer` works and a head symbol
# survives being passed back through evaluation — unlike registered heads
# such as `List`, these name no clause set and would otherwise be unbound.
ATOM_HEAD_NAMES = ("Integer", "Real", "Complex", "String", "Symbol")


def bind_prelude_constants(env) -> None:
    """Bind the atom-head symbols to themselves in `env`."""
    for name in ATOM_HEAD_NAMES:
        env.set_here(name, Symbol(name))


def _check_list(value, who):
    if not (isinstance(value, Expression) and value.head == Symbol("List")):
        raise MinimaticTypeError(f"{who}: expected a List, got {value!r}")


def _impl_list(*args):
    return Expression(Symbol("List"), *args)


def _impl_length(list_expr):
    _check_list(list_expr, "length")
    return len(list_expr.tail)


def _impl_first(list_expr):
    _check_list(list_expr, "first")
    if not list_expr.tail:
        # An empty list has no first element -- a routine outcome, so a
        # value rather than an exception. Not `[]`: an empty list is itself
        # a legitimate element, so `first([[], 1])` already answers `[]`,
        # and returning it here too would make "there is no first element"
        # indistinguishable from "the first element is empty".
        return err("EmptyList", "first: empty list")
    return list_expr.tail[0]


def _impl_rest(list_expr):
    # Total, unlike `first`: the rest of an empty list genuinely is the
    # empty list, and making it fail would put an unwrap in every recursive
    # traversal.
    _check_list(list_expr, "rest")
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
    if b == 0:
        # Routine, not a programming error: dividing by a value that
        # happens to be zero is ordinary arithmetic, and a raw
        # ZeroDivisionError used to escape MinimaticError entirely.
        return err("DivideByZero", f"divide: {a!r} by zero")
    return a / b


def _impl_power(a, b):
    return a**b


def _impl_mod(a, b):
    return a % b


def _impl_negate(a):
    return -a


def _impl_and(first, *rest_raw, ctx=None):
    """`and(a, b, ...)` — HoldRest, so later arguments are never evaluated
    once the answer is settled. Bool-strict like `not`: there is no
    truthiness in Minimatic."""
    _check_bool(first, "and")
    if not first:
        return False
    for raw in rest_raw:
        value = ctx.eval(raw)
        _check_bool(value, "and")
        if not value:
            return False
    return True


def _impl_or(first, *rest_raw, ctx=None):
    _check_bool(first, "or")
    if first:
        return True
    for raw in rest_raw:
        value = ctx.eval(raw)
        _check_bool(value, "or")
        if value:
            return True
    return False


def _check_bool(value, who):
    if not isinstance(value, bool):
        raise MinimaticTypeError(f"{who}: expected a bool, got {value!r}")


def _impl_not(a):
    # Bool-only, matching `if`'s strictness: there is no truthiness in
    # Minimatic, so `!5` is a mistake rather than `false`.
    if not isinstance(a, bool):
        raise MinimaticTypeError(f"not: expected a bool, got {a!r}")
    return not a


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
    register_head(
        registry, "RuleDelayed", _impl_rule_delayed, attributes=[HoldAll], pass_ctx=True
    )
    register_head(registry, "ReplaceAll", _impl_replace_all, attributes=[HoldRest], pass_ctx=True)
    register_head(
        registry,
        "ReplaceRepeated",
        _impl_replace_repeated,
        attributes=[HoldRest],
        pass_ctx=True,
    )
    register_head(registry, "Hold", _impl_hold, attributes=[HoldAll], pass_ctx=True)
    register_head(registry, "ReleaseHold", _impl_release_hold, pass_ctx=True)
    register_head(registry, "__pipe__", _impl_pipe, attributes=[HoldRest], pass_ctx=True)

    register_head(registry, "if", _impl_if, attributes=[HoldRest], pass_ctx=True)
    register_head(registry, "switch", _impl_switch, attributes=[HoldAll], pass_ctx=True)
    register_head(registry, "which", _impl_which, attributes=[HoldAll], pass_ctx=True)
    register_head(registry, "for", _impl_for, pass_ctx=True)
    register_head(registry, "each", _impl_each, pass_ctx=True)
    register_head(registry, "CompoundExpression", _impl_compound_expression)
    register_head(registry, "print", _impl_print, attributes=[ResultAware])
    register_head(registry, "Range", _impl_range)

    # ResultAware: pure inspectors, total by construction. Without it,
    # `Err(...) |> Head` would return the Err rather than its head symbol.
    register_head(registry, "Head", _impl_head_symbol, attributes=[ResultAware])
    register_head(registry, "Args", _impl_args, attributes=[ResultAware])

    register_head(registry, "Err", _impl_err)
    register_head(registry, "is_err", _impl_is_err, attributes=[ResultAware])
    register_head(registry, "unwrap", _impl_unwrap, attributes=[ResultAware])
    register_head(registry, "unwrap_err", _impl_unwrap_err, attributes=[ResultAware])
    register_head(registry, "catch", _impl_catch, attributes=[ResultAware], pass_ctx=True)
    register_head(registry, "recover", _impl_recover, attributes=[ResultAware], pass_ctx=True)
    register_head(registry, "finally", _impl_finally, attributes=[ResultAware], pass_ctx=True)

    register_head(registry, "List", _impl_list)
    register_head(registry, "length", _impl_length)
    register_head(registry, "first", _impl_first)
    register_head(registry, "rest", _impl_rest)
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
    register_head(registry, "not", _impl_not)
    register_head(registry, "and", _impl_and, attributes=[HoldRest], pass_ctx=True)
    register_head(registry, "or", _impl_or, attributes=[HoldRest], pass_ctx=True)

    register_head(registry, "equal", _impl_equal)
    register_head(registry, "not_equal", _impl_not_equal)
    register_head(registry, "less", _impl_less)
    register_head(registry, "greater", _impl_greater)
    register_head(registry, "less_eq", _impl_less_eq)
    register_head(registry, "greater_eq", _impl_greater_eq)

# Minimatic Kernel — Tree-Walker Interpreter Design

**Status:** Draft / work in progress
**Scope:** `minimatic-kernel` only (parser, evaluator, dispatch, rewriting, extension API)
**Audience:** contributors to the kernel implementation

---

## 1. Purpose and approach

This document specifies a tree-walking interpreter for Minimatic. A tree
walker is the deliberate first implementation strategy: it lets the team
settle contested semantics — clause dispatch, the boundary between
evaluation and rewriting, and error propagation through pipelines — before
any of it is locked in by a compiler or bytecode VM. Nothing here should be
read as a performance-optimal design; it should be read as the smallest
architecture that makes Minimatic's stated design goals *structurally true*
rather than true by convention.

Those goals, from the language spec, are:

- Strict, deterministic evaluation with closed, definition-time clause
  dispatch (no global mutable rule table).
- Specificity-based dispatch, resolved once at definition time by a
  published static rule, never from runtime state.
- Immutable data, always.
- Rewriting (`Hold` / `/.` / `ReleaseHold`) that is explicit and opt-in,
  never ambient.
- Errors represented as values: the ordinary result on success, or an
  `Err`, composed through pipelines.
- Trivial extension from Python via `register_head`, with extensions being
  first-class heads rather than a bolted-on FFI layer.

Each section below states the corresponding architectural commitment and
why it's structured that way, not just what it does.

---

## 2. Unified data model

### 2.1 The core problem

`Hold` requires that "code" and "data" be the same representation — a
`Hold`-captured expression must be indistinguishable, structurally, from a
freshly parsed program. If the AST and the runtime value representation
were different types, every `Hold`/`ReleaseHold` boundary would require a
lossy or lossless *conversion* between them, and that conversion boundary
is exactly where language-implementation bugs like "rewriting doesn't see
what I expect" tend to live.

**Decision: there is exactly one tree type.** A parsed program, a
`Hold`-captured subexpression, and an evaluated result are all the same
`Node` type. Evaluation does not transform a node into a different kind of
object; it reduces a node to a normal-form node of the *same* type.

### 2.2 Node types

> **Not what the kernel does.** The implementation has no `Literal` wrapper
> and no type named `Expr`/`Node`: atoms are *raw Python values*
> (`int`/`float`/`str`/`bool`/`None`, see `_ATOMIC_TYPES` in `eval.py`), and
> the expression type is `Expression`, a `tuple` subclass holding
> `(head, tail)`. Everything below still describes the intended shape
> faithfully — one tree type, atoms distinguishable from applications — but
> read `Literal(x)` as "the bare value `x`" and `Expr` as `Expression`
> before building against it.

```python
class Symbol:
    name: str

class Literal:
    value: int | float | str | bool

class Expr:
    head: "Symbol | Expr"
    args: tuple["Node", ...]

Node = Symbol | Literal | Expr
```

All surface syntax desugars into this before evaluation ever runs:

| Surface syntax | Desugared form |
|---|---|
| `1 + 3` | `Expr(Symbol("plus"), (Literal(1), Literal(3)))` |
| `[1, 2, 3]` | `Expr(Symbol("List"), (Literal(1), Literal(2), Literal(3)))` |
| `{ "a" -> 1 }` | `Expr(Symbol("Dict"), (Expr(Symbol("Rule"), (Literal("a"), Literal(1))),))` |
| `x -> x * 2` | `Expr(Symbol("Lambda"), (params, body))` |
| `a \|> f` | `Expr(Symbol("__pipe__"), (a, f))` |
| `a // f` | `Expr(Symbol("__pipe__"), (a, f))` — `//` is a spelling of `\|>` |
| `f /@ xs` | `Expr(Symbol("map"), (xs, f))` — function-first surface, list-first head |

### 2.3 Values are just un-reduced-further expressions

There is no separate `Value` type. A "value" is an `Expr` whose head the
evaluator recognizes as already in normal form (`List`, `Dict`, `Err`, a
closure marker, etc.), or a `Literal`. This has two consequences that
matter architecturally:

- `Hold(expr)` is a zero-cost operation — it stores the node as-is, with no
  serialization or reconstruction.
- `/.` (rewrite) applies uniformly to freshly parsed code, `Hold`-captured
  code, and ordinary evaluated data (e.g. rewriting a plain list) because
  all three are the same tree shape (see §6).

### 2.4 Pattern nodes

Patterns get their own node types, distinct from ordinary expressions, so
the matcher (§5) can be pure structural recursion rather than syntax
sniffing:

```python
class Blank:
    type_tag: str | None        # _  or  _int

class BlankSeq:
    type_tag: str | None        # __

class BlankNullSeq:
    type_tag: str | None        # ___

class PatternBind:
    name: str
    pattern: "Node"              # x: _int
```

These are still `Node`s — `Hold` and `/.` can capture and rewrite patterns
themselves, which is required since rewrite-rule LHSs and function-clause
patterns are patterns written in the same syntax.

---

## 3. Pipeline

```
source text
   │   lex + parse
   ▼
Expr tree                     ◄── this is also exactly what Hold(...) produces
   │   eval(tree, env)
   ▼
Expr tree, normal form
```

The parser (recursive descent, with a Pratt/precedence-climbing sub-parser
for infix operators, `|>`, and pattern syntax) performs **no semantic
work**. It does not resolve heads, consult attributes, or perform dispatch.
Its only job is to produce a `Node` tree with all sugar desugared. This
separation is what keeps `Hold` simple: holding an expression means simply
*not calling `eval` on the parser's output*, rather than needing a second,
non-evaluating code path through the parser.

---

## 4. Evaluator core loop

```python
def eval(node: Node, env: Env) -> Node:
    match node:
        case Literal():
            return node

        case Symbol(name):
            return env.lookup(name)   # unbound symbol is an error, not a no-op

        case Expr(head, args):
            head_val = eval(head, env) if isinstance(head, Expr) else head
            fn = registry.resolve(head_val)
            if fn is None:
                raise UnknownHeadError(head_val)

            attrs = fn.attributes
            eval_args = [
                a if is_held(attrs, i) else eval(a, env)
                for i, a in enumerate(args)
            ]

            if Attr.LISTABLE in attrs:
                eval_args = thread_over_lists(eval_args)

            return fn.apply(eval_args, env)   # dispatch happens inside apply()
```

### 4.1 Single-pass, no evaluation fixpoint

Wolfram Language re-evaluates results until they stop changing, because
rewrite rules can fire on evaluation *outputs*, not just inputs — this is a
direct consequence of its global, mutable, ambiently-consulted rule table.
Minimatic's closed dispatch and explicit-only rewriting remove the need for
this entirely: `eval` is a single recursive descent — evaluate arguments,
dispatch once, evaluate the matched clause's body, return. This is a
direct semantic consequence of the design goals in §1, not an independent
optimization; a fixpoint loop would only be necessary if rewriting could
happen implicitly during ordinary evaluation, which the design explicitly
forbids.

### 4.2 Hold attributes

`is_held(attrs, i)` is computed once per call from the head's attribute set
(`HoldAll`, `HoldFirst`, `HoldRest`, or none). It determines whether
argument `i` is passed to `fn.apply` as an evaluated value or as the raw,
unevaluated subtree — this is the single mechanism underlying both `Hold`
itself (a builtin head with `HoldAll`) and any user- or Python-defined
macro-like head.

---

## 5. Pattern matcher

```python
def match(pattern: Node, value: Node, bindings: dict, ctx=None) -> dict | None:
    ...
```

A single structural matcher, shared by two otherwise-separate subsystems:

1. **Clause dispatch** (§6) — matching call arguments against a compiled,
   sorted clause list, at call time.
2. **Rewriting** (§7) — matching a rule's LHS against subexpressions of a
   held tree, at `/.`-application time.

Using one implementation for both is a semantic commitment, not just code
reuse: it guarantees that a pattern means the same thing whether it
appears as a function parameter (`f(x: _int) := ...`) or as a rewrite-rule
LHS (`expr /. x: _int -> ...`), which the surface syntax already implies by
using identical pattern grammar in both positions.

### 5.1 The one thing that is not pure structural recursion

`Condition` (`pattern /; guard`, language doc §9.2) has to **evaluate** its
guard, which is why `match` carries an optional `ctx`. Both callers already
have one — `dispatch.py` builds it per call, `rewrite.py` already threaded
it for `ReplaceAll` — so nothing new is plumbed; the guard simply evaluates
in `ctx.env` extended with the bindings the pattern just produced.

Keeping guards *inside* `match` rather than lifting them into
`dispatch.py`/`rewrite.py` is deliberate. A guard can sit anywhere a
pattern can, including nested inside a compound pattern
(`f(List(x: _int /; x > 0), y: _)`), and a caller one layer up cannot see
those. The cost is that `match` is no longer evaluation-free; the payoff is
that it stays the *single* matcher §5 exists to guarantee.

`Alternatives` (`p1 | p2`) needs no such escape — it is ordinary
recursion, trying each branch and returning the first success.

---

## 6. Clause dispatch

This is the highest-risk part of the kernel and is given its own module
(`dispatch.py`), isolated from `eval.py`.

### 6.1 Definition-time processing

```python
def define_clause(registry, head_name, pattern, body):
    clause = Clause(pattern, body, specificity=score(pattern))
    clauses = registry.get(head_name, ClauseSet())
    clauses.insert_sorted(clause)   # descending specificity, ties keep
    registry.set(head_name, clauses)   # declaration order
```

One thing is resolved once, here, and never revisited at call time: where
the new clause sits in specificity order relative to the existing ones.

### 6.2 Specificity scoring

`score(pattern)` produces a per-argument specificity vector, compared
lexicographically across a clause's full parameter list:

| Pattern shape | Relative specificity |
|---|---|
| Literal (`5`, `"hi"`) | highest |
| Compound (`Err(k, d)`, `[a, b]`) | highest tier, compared by its arguments |
| Typed blank (`_int`) | middle |
| Bare blank (`_`), bare binding symbol | low |
| Sequence blank (`__`, `___`) | lowest, and affects arity comparison |
| Alternatives (`p1 \| p2`) | its **weakest** branch's score |
| Condition (`p /; g`) | exactly its inner pattern's score |

A guard scores as its unguarded shape because a guard narrows at run time
and specificity is static — see language doc §9.2 for the ordering
consequence (guarded clauses must be declared first).

Scoring **recurses into compound patterns**, comparing their arguments
structurally, so `Err("IOError", d: _)` strictly outranks
`Err(k: _, d: _)`. Without that recursion the two would tie and the more
specific clause would win only if it happened to be declared first — a
silently wrong answer rather than a rejected definition, which matters
because §6.3 no longer rejects anything.

Only clauses that are equally specific *all the way down* fall through to
declaration order.

### 6.3 Why there is no ambiguity check

Earlier drafts of this document specified `overlaps()`/`implies()` and an
`AmbiguousClauseError`, rejecting two clauses that could both match some
value when neither was more specific. **That check was removed from the
design, not merely deferred** — see
`docs/proposal-001-dispatch-results-and-pipes.md` §2.1.

The short reason: it is undecidable in practice over the pattern grammar
the language actually has (nested compound patterns, sequence blanks with
variable arity, type tags), and a conservative overlap test over those
degenerates toward "everything overlaps everything" — which fails
*legitimate* clause sets, the one outcome this document previously argued
was worse than a missed ambiguity.

What replaces it: dispatch order is a pure function of
the clause set, fixed at definition time by a published static rule
(descending `score()`, then declaration order), never dependent on runtime
state or call history. Silent shadowing is possible; silent *nondeterminism*
is not.

If the safety story needs shoring up later, the recovery path is a
non-fatal lint — a definition-time warning, or an error only under an opt-in
strict mode — which can be added without changing what any existing program
means, precisely because the tie-break is specified rather than accidental.

### 6.4 Call-time dispatch

```python
def apply(clause_set, args, env):
    for clause in clause_set:            # pre-sorted by specificity
        if (bindings := match_all(clause.pattern, args)) is not None:
            return eval(clause.body, env.extend(bindings))
    raise NoMatchingClauseError(clause_set.head_name, args)
```

Because sorting is fully paid for at definition time, call-time dispatch is
a linear scan for the first structural match — no re-scoring, no
re-validation. This is what preserves "ordinary function-call speed" for the
common case.

---

## 7. Rewriting: `Hold`, `/.`, `ReleaseHold`

Kept in its own module (`rewrite.py`), which is called *from* `Hold`/
`ReleaseHold`/`/.` sites, and which never itself calls back into `eval`
except at the one explicit `ReleaseHold` boundary. This separation is what
makes "rewriting is explicit, not ambient" a structural property of the
codebase, not just a rule contributors are expected to remember.

```python
def replace_all(node: Node, rules: list[RewriteRule], ctx) -> Node:
    for rule in rules:
        if (b := match(rule.lhs, node, {}, ctx)) is not None:
            rhs = substitute(rule.rhs, b)
            return rhs if rule.delayed else ctx.eval(rhs)
    if isinstance(node, Expr):
        return node.map_args(lambda a: replace_all(a, rules, ctx))
    return node


def replace_repeated(node, rules, ctx, limit, node_limit) -> Node:
    """`//.` — replace_all until nothing changes, or give up."""
    current = node
    for _ in range(limit):
        nxt = replace_all(current, rules, ctx)
        if exceeds_size(nxt, node_limit):
            raise RewriteLimitError(node_limit, "nodes")
        if structurally_equal(nxt, current):
            return current
        current = nxt
    raise RewriteLimitError(limit)
```

`replace_repeated` needs **two** limits, because divergence takes two
shapes. A rule that cycles or crawls (`[1,2,3] //. x: _int -> x + 1`) is
caught by the pass count. A rule that *multiplies* — one that rewrites the
leaves it just produced, as `1 //. x: _int :> x + 1` does — doubles the
tree every pass, so 256 passes is 2^256 nodes and the pass count never gets
to fire; only measuring the result catches that one.

The fixpoint test is structural, not `==`: `Expr.__eq__` compares tails
with Python `==`, under which `List(1) == List(True)`, so a rewrite between
those two would read as a fixpoint.

- **`Hold(expr)`** — a builtin head with the `HoldAll` attribute (§4.2).
  Its argument is never passed through `eval`; it is stored as-is.
- **`->` (immediate rule)** — RHS is evaluated once, at the moment a match
  is applied, and the resulting value is substituted in.
- **`:>` (delayed rule, `RuleDelayed`)** — RHS is substituted unevaluated
  and left for later evaluation; relevant when the RHS has side effects or
  non-deterministic heads (e.g. `random()`) that should re-fire per match
  rather than being computed once and reused.
- **`//.` (ReplaceRepeated)** — `replace_all` to a fixpoint, above.
- **`ReleaseHold(expr)`** — the single point where a previously-held tree
  re-enters ordinary `eval`. It strips one `Hold` and evaluates what was
  inside **in the environment it is released in**: `Hold` captures no
  environment, which is what keeps a held node structurally identical to
  ordinary data (§2.3) and therefore matchable by ordinary patterns. See
  language doc §16.4, now closed.

Because rewriting operates on the same `Node` type as everything else
(§2.3), `/.` applied to an already-evaluated plain list works with the
identical code path as `/.` applied to a `Hold`-captured expression — no
special-casing is needed for "data" versus "code."

---

## 8. Attributes

A flat table, consulted by both `eval` (hold behavior, `Listable`
threading, `ResultAware` short-circuiting) and `define_clause` (attributes
are fixed at definition time):

```python
registry.attributes["plus"] = {Attr.LISTABLE}
registry.attributes["MyMacro"] = {Attr.HOLD_ALL}
registry.attributes["catch"] = {Attr.RESULT_AWARE}
```

Redefining a head's attributes after clauses already exist for that head
should itself be a definition-time error: attribute-dependent behavior
(what gets held, what threads over lists, what may receive an `Err`) must
not change silently underneath already-defined clauses.

---

## 9. `Err` and the pipe

Failure propagation through `|>` needs an explicit mechanism rather than
being an implicit property every function must individually implement.

### 9.1 Pipe desugaring

```
a |> f    desugars to    Expr(Symbol("__pipe__"), (a, f))
```

### 9.2 Short-circuiting

```python
def eval_pipe(lhs_val: Node, fn_head: Symbol, env: Env) -> Node:
    if is_err(lhs_val) and not registry.has_attr(fn_head, Attr.RESULT_AWARE):
        return lhs_val                       # skip fn entirely
    return apply_head(fn_head, [lhs_val], env)
```

Success is the value itself — there is no `Ok` wrapper — so `is_err` is the
whole test. Only heads explicitly marked `ResultAware` are permitted to
receive an `Err` value directly: the combinators (`catch`, `recover`,
`finally`, `unwrap`, `unwrap_err`, `is_err`) and the inspectors (`print`,
`Head`, `Args`), without which a failing pipeline could not be debugged or
examined. Every other function downstream of a failure is skipped. This
keeps ordinary builtins and user functions (`parse_json`, `process`, ...)
from needing a hand-written `Err`-passthrough clause, which would otherwise
be required boilerplate on every function ever written for a pipeline.

Two ordering constraints, learned in implementation: the check must run
**before** a `Lambda` right-hand side is applied — a lambda has no head, so
it is never `ResultAware`, and handing it an error it cannot recognise is
the trap — and **before** `$` template substitution, so a skipped pipe does
not evaluate the template's other arguments.

Note the pipe is what short-circuits, not the call: `f(Err(...))` invokes
`f`. `/@` desugars straight to `map(xs, f)` without passing through
`__pipe__`, so it does not short-circuit either.

---

## 10. Immutable data representation

> **Not yet implemented.** `List` is currently an ordinary `Expression`
> headed by `Symbol("List")` — tuple-backed, immutable by construction, and
> its own normal form. There is no `data.py` and no persistent vector; a
> dedicated `List` type was tried and dropped because it added a second
> representation for one value and a conversion boundary of exactly the kind
> §2.1 argues against (`IMPLEMENTATION_PLAN.md` records the reasoning).
> `Dict` is the same story: an `Expression` headed by `Symbol("Dict")`
> whose arguments are `Rule(k, v)` entries, canonicalised — deduplicated
> and key-sorted — at construction, so a dict's structural identity and its
> value agree (`minimatic/dict_ops.py`). Lookup is therefore a linear scan.
> The design below remains the intended destination, and the argument for
> it still holds — it is the *when*, not the *whether*, that is open.

"Every update returns a new value" (§1) must not mean "every update is
O(n)." Native Python `list`/`dict`, copied on every operation, would make
`append`/`key_drop` quietly quadratic in realistic notebook usage.

- **`List`** — backed by a persistent vector (RRB-tree or similar), giving
  near-O(1) amortized append/index and O(log n) update-with-sharing.
- **`Dict`** — backed by a HAMT (hash array mapped trie), giving O(log n)
  structural-sharing update.

This is purely an internal representation detail behind the `List`/`Dict`
heads; it is invisible at the language surface (`myList[1] <- 5` behaves
identically regardless of backing structure) and can be swapped later
without affecting semantics.

---

## 11. Extension API (`register_head`)

Builtins are inserted into the **same** `ClauseSet`/attribute registry used
for user-defined clauses — a Python-backed clause is represented as:

```python
class BuiltinClause:
    pattern: Node             # often a catch-all (___), but may be typed
    fn: Callable[[list[Node], Env], Node]
    attributes: set[Attr]
```

```python
def register_head(name, fn, attributes=()):
    define_clause(registry, name, pattern=BlankNullSeq(), body=PyCall(fn))
    registry.attributes[name] |= set(attributes)
```

### 11.1 No privileged builtins

If a builtin is registered with a permissive catch-all pattern and a user
later adds a more specific clause under the same head name, dispatch (§6)
treats this exactly as it would two user-defined clauses — there is no
special-cased "builtins always win" or "builtins are sealed" rule. This
symmetry is what makes `register_head` a first-class extension mechanism
rather than an override hook bolted onto the side of the dispatcher, and it
directly satisfies the "trivially extensible" design goal from §1: a Python
function registered this way *is* a head, subject to the same specificity
rules as everything else.

One consequence is sharper now that §6.3 rejects nothing: a user clause on
a prelude head outscores the catch-all sequence blank `register_head`
installs (score `0`), and wins silently. Sealing (§14.3) is the only thing
standing between that and accidental redefinition.

---

## 12. Module layout

```
minimatic/
  ast/            # Symbol, Expression, atoms, pattern node types
  lexer.py
  parser.py       # syntax -> tree; no semantic work
  eval.py         # core loop (§4)
  dispatch.py     # ClauseSet, score(), Clause (§6)
  match.py        # match() — shared by dispatch.py and rewrite.py (§5)
  rewrite.py      # replace_all / replace_repeated / RewriteRule (§7)
  attributes.py   # attribute table (§8)
  result.py       # Err and the value/exception boundary (§9)
  registry.py     # head name -> ClauseSet + attributes
  prelude.py      # the built-in heads, including __pipe__ and the combinators
  extend.py       # register_head (§11)
  env.py          # lexical scope, closures
  errors.py       # the MinimaticError hierarchy
  markdown.py     # ```minimatic fenced blocks out of a .md file
  kernel.py       # Kernel: wires registry + env + eval into eval(source)
```

No `data.py` — see §10. The pipe and the result combinators live in
`prelude.py` as ordinary registered heads rather than in `result.py`, which
holds only the `Err` constructor and the line between error *values* and
kernel *exceptions*.

The dependency direction `dispatch.py` → `match.py` ← `rewrite.py`, with no
edge between `dispatch.py` and `rewrite.py` directly, is the structural
guarantee that implicit clause dispatch (happens on every call) and
explicit rewriting (happens only at `Hold`/`/.` sites) remain two genuinely
separate mechanisms rather than converging into a single ambient-rewriting
system — which is precisely the property this design is meant to avoid
inheriting from prior art.

---

## 13. Explicit non-goals for this implementation

- **No bytecode compiler or JIT.** Given the current WIP status of clause
  specificity and pipeline error semantics, compiling would lock in
  decisions that are still genuinely open (§14). The tree walker should
  remain the reference implementation until those settle.
- **No evaluation-result fixpoint loop** (§4.1) — ruled out by design, not
  merely deferred.
- **No persistence.** Orthogonal persistence of external symbols is owned
  by `minimatic-workbench`, not this kernel; the kernel should treat all
  state as in-process only.

---

## 14. Open design questions

Numbering is kept stable so existing cross-references stay valid; settled
questions are struck rather than removed.

1. ~~**Ambiguity-check completeness.**~~ **Closed — will not do.** The
   check was removed from the design (§6.3, proposal 001 §2.1). Nested
   compound patterns are instead handled by `score()` recursing into them
   (§6.2).
2. ~~**`Flat`/`Orderless` interaction with dispatch.**~~ **Closed — moot.**
   Both attributes were removed from the language (proposal 001 §2.3), so
   there is no canonicalization step to order relative to scoring.
3. ~~**Redefinition semantics.**~~ **Closed.** Clause sets are sealed on
   first dispatch; a later `define` raises `HeadAlreadySealedError`. Note
   this is now the *only* structural guard against surprise redefinition,
   since (1) is gone — it carries weight it was not originally carrying
   alone.
4. ~~**Error identity through `Hold`.**~~ **Closed**, in
   `minimatic/result.py`'s frame. A delayed rule's RHS is not evaluated by
   the rewriter at all — that is what `:>` means — so nothing raises
   *during* rewriting. When the result is later released, it evaluates
   like any other expression: a routine failure comes back as an `Err`
   value, a programming error stays a kernel exception. `Hold` introduces
   no third category, precisely because it introduces no separate
   representation to lose identity across.

   The one addition rewriting does make is `RewriteLimitError`: a `//.`
   rule set with no normal form is a mistake in the rules, so it raises
   rather than yielding a value.
5. **Recursion depth.** There is no tail-call elimination, so
   Minimatic-level recursion inherits Python's stack limit and
   `RecursionError` escapes `MinimaticError` entirely. Self-hosted list
   code caps out in the low hundreds of elements. Newly open; see
   `docs/capabilities-and-roadmap.md` §3.2.

---

## 15. Summary

The tree walker is organized so that each stated design goal in §1
corresponds to a specific structural boundary in the code:

| Design goal | Structural mechanism |
|---|---|
| Closed, deterministic dispatch | `dispatch.py` resolves clause order once, at definition time, by a published static rule |
| No hidden rewriting | `rewrite.py` has no inbound calls from `eval.py` except via `Hold`/`ReleaseHold`/`/.` |
| Immutable data | `Expression` is a frozen tuple; every "update" head returns a new value (persistent backing structures still to come, §10) |
| Errors as values | `__pipe__` desugaring + `ResultAware` attribute, not per-function boilerplate |
| First-class extension | `register_head` clauses share the same `ClauseSet`/dispatch machinery as user clauses |

Getting the tree walker right — especially §6 (dispatch) and §7
(rewriting) — is what will make or break whether a future bytecode
compiler can be built as a faithful, semantics-preserving optimization
rather than a second, subtly different implementation of the language.

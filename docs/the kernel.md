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
- Specificity-based dispatch, with ambiguous clauses rejected as a
  definition-time error.
- Immutable data, always.
- Rewriting (`Hold` / `/.` / `ReleaseHold`) that is explicit and opt-in,
  never ambient.
- Errors represented as `Ok`/`Err` values, composed through pipelines.
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
evaluator recognizes as already in normal form (`List`, `Dict`, `Ok`,
`Err`, a closure marker, etc.), or a `Literal`. This has two consequences
that matter architecturally:

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

            if Attr.FLAT in attrs:
                eval_args = flatten(head_val, eval_args)
            if Attr.ORDERLESS in attrs:
                eval_args = canonical_order(eval_args)

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
def match(pattern: Node, value: Node, bindings: dict) -> dict | None:
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

---

## 6. Clause dispatch

This is the highest-risk part of the kernel and is given its own module
(`dispatch.py`), isolated from `eval.py`.

### 6.1 Definition-time processing

```python
def define_clause(registry, head_name, pattern, body):
    clause = Clause(pattern, body, specificity=score(pattern))
    clauses = registry.get(head_name, ClauseSet())

    for existing in clauses:
        if (
            overlaps(existing.pattern, pattern)
            and existing.specificity == clause.specificity
            and not implies(existing.pattern, pattern)
            and not implies(pattern, existing.pattern)
        ):
            raise AmbiguousClauseError(head_name, existing, clause)

    clauses.insert_sorted(clause)   # descending specificity
    registry.set(head_name, clauses)
```

All of the following are resolved once, here, and never revisited at call
time:

- Where the new clause sits in specificity order relative to existing
  clauses.
- Whether it is ambiguous with any existing clause.

### 6.2 Specificity scoring

`score(pattern)` produces a per-argument specificity vector, compared
lexicographically across a clause's full parameter list:

| Pattern shape | Relative specificity |
|---|---|
| Literal (`5`, `"hi"`) | highest |
| Typed blank (`_int`) | middle |
| Bare blank (`_`) | low |
| Sequence blank (`__`, `___`) | lowest, and affects arity comparison |

### 6.3 Ambiguity detection

Two clauses with tied specificity scores are only truly ambiguous if their
domains actually overlap. `5` and `"hi"` are both literals (equal
specificity) but disjoint — no ambiguity, because only one could ever match
a given call. The check is therefore:

```
ambiguous(p1, p2) :=
    overlaps(p1, p2) AND score(p1) == score(p2)
    AND NOT implies(p1, p2) AND NOT implies(p2, p1)
```

This is intentionally the most heavily tested piece of the kernel. A false
positive here (rejecting genuinely disjoint clauses as ambiguous) is worse
for usability than a missed ambiguity would be for safety, since it is the
one static check standing between the language's safety guarantee and a
user's ability to define straightforward, non-overlapping clause sets.
Error messages from this check should identify *which* two clauses
conflict and on *which* argument position, not just report "ambiguous
definition."

### 6.4 Call-time dispatch

```python
def apply(clause_set, args, env):
    for clause in clause_set:            # pre-sorted by specificity
        if (bindings := match_all(clause.pattern, args)) is not None:
            return eval(clause.body, env.extend(bindings))
    raise NoMatchingClauseError(clause_set.head_name, args)
```

Because sorting and ambiguity-checking are fully paid for at definition
time, call-time dispatch is a linear scan for the first structural match —
no re-scoring, no re-validation. This is what preserves "ordinary
function-call speed" for the common case.

---

## 7. Rewriting: `Hold`, `/.`, `ReleaseHold`

Kept in its own module (`rewrite.py`), which is called *from* `Hold`/
`ReleaseHold`/`/.` sites, and which never itself calls back into `eval`
except at the one explicit `ReleaseHold` boundary. This separation is what
makes "rewriting is explicit, not ambient" a structural property of the
codebase, not just a rule contributors are expected to remember.

```python
def replace_all(node: Node, rules: list[Rule]) -> Node:
    for rule in rules:
        if (b := match(rule.lhs, node, {})) is not None:
            rhs = substitute(rule.rhs, b)
            return rhs if rule.delayed else eval(rhs, global_env)
    if isinstance(node, Expr):
        return Expr(node.head, tuple(replace_all(a, rules) for a in node.args))
    return node
```

- **`Hold(expr)`** — a builtin head with the `HoldAll` attribute (§4.2).
  Its argument is never passed through `eval`; it is stored as-is.
- **`->` (immediate rule)** — RHS is evaluated once, at the moment a match
  is applied, and the resulting value is substituted in.
- **`:>` (delayed rule, `RuleDelayed`)** — RHS is substituted unevaluated
  and left for later evaluation; relevant when the RHS has side effects or
  non-deterministic heads (e.g. `random()`) that should re-fire per match
  rather than being computed once and reused.
- **`ReleaseHold(expr)`** — the single point where a previously-held tree
  re-enters ordinary `eval`.

Because rewriting operates on the same `Node` type as everything else
(§2.3), `/.` applied to an already-evaluated plain list works with the
identical code path as `/.` applied to a `Hold`-captured expression — no
special-casing is needed for "data" versus "code."

---

## 8. Attributes

A flat table, consulted by both `eval` (hold behavior, `Flat`,
`Orderless`) and `define_clause` (attributes are fixed at definition
time):

```python
registry.attributes["Plus"] = {Attr.FLAT, Attr.ORDERLESS}
registry.attributes["MyMacro"] = {Attr.HOLD_ALL}
```

Redefining a head's attributes after clauses already exist for that head
should itself be a definition-time error, for the same reason ambiguous
clauses are: attribute-dependent behavior (what gets held, what gets
flattened) must not change silently underneath already-defined clauses.

---

## 9. `Ok` / `Err` and the pipe

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

Only heads explicitly marked `ResultAware` — `catch`, `recover`, `match`,
`finally`, `unwrap`, `unwrap_err`, `is_ok`, `is_err` — are permitted to
receive an `Err` value directly. Every other function downstream of a
failure in a pipeline is automatically skipped. This keeps ordinary
builtins and user functions (`parse_json`, `process`, ...) from needing a
hand-written `Err`-passthrough clause, which would otherwise be required
boilerplate on every function ever written for use in a pipeline.

---

## 10. Immutable data representation

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
later adds a more specific clause under the same head name, dispatch and
ambiguity-checking (§6) treat this exactly as they would two user-defined
clauses — there is no special-cased "builtins always win" or "builtins are
sealed" rule. This symmetry is what makes `register_head` a first-class
extension mechanism rather than an override hook bolted onto the side of
the dispatcher, and it directly satisfies the "trivially extensible"
design goal from §1: a Python function registered this way *is* a head,
subject to the same specificity and ambiguity rules as everything else.

---

## 12. Proposed module layout

```
minimatic/
  ast/            # Node, Symbol, Literal, Expr, pattern node types
  lexer.py
  parser.py       # syntax -> Node tree; no semantic work
  eval.py         # core loop (§4)
  dispatch.py     # ClauseSet, score(), overlaps(), implies(), define_clause() (§6)
  match.py        # match() — shared by dispatch.py and rewrite.py (§5)
  rewrite.py      # Hold / ReleaseHold / replace_all / Rule (§7)
  attributes.py   # attribute table (§8)
  result.py       # Ok/Err, __pipe__, catch/recover/match/finally (§9)
  data.py         # persistent List/Dict (§10)
  extend.py       # register_head (§11)
  env.py          # lexical scope, closures
  kernel.py       # Kernel: wires registry + env + eval into eval(source) -> Node
```

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

These are unresolved at the architecture level and should be settled
before the corresponding modules are considered stable:

1. **Ambiguity-check completeness.** `overlaps`/`implies` need to handle
   nested compound patterns (e.g. `List(_int, __)` vs `List(__, _int)`),
   not just flat blanks. The algorithm's behavior on deeply nested or
   recursive patterns is not yet specified.
2. **`Flat`/`Orderless` interaction with dispatch.** If a head is both
   `Orderless` and has multiple clauses, does specificity scoring happen
   before or after canonicalization? This affects both `score()` and
   `overlaps()`.
3. **Redefinition semantics.** Can a `ClauseSet` be extended after first
   use (e.g. in a live notebook adding a clause to a previously-called
   function), or are clause sets sealed after first dispatch? This has
   direct consequences for `minimatic-workbench`'s persistence model.
4. **Error identity through `Hold`.** If evaluation inside a delayed rule
   RHS (`:>`) raises rather than returning `Err`, does that propagate as a
   kernel exception or get coerced to `Err`? The spec's "errors are
   values" goal suggests the latter, but this isn't yet enforced anywhere
   in the evaluator.

---

## 15. Summary

The tree walker is organized so that each stated design goal in §1
corresponds to a specific structural boundary in the code, not a
convention contributors have to maintain by discipline:

| Design goal | Structural mechanism |
|---|---|
| Closed, deterministic dispatch | `dispatch.py` resolves order/ambiguity once, at definition time |
| No hidden rewriting | `rewrite.py` has no inbound calls from `eval.py` except via `Hold`/`ReleaseHold`/`/.` |
| Immutable data | Persistent `List`/`Dict` backing structures, not copy-on-write Python containers |
| Errors as values | `__pipe__` desugaring + `ResultAware` attribute, not per-function boilerplate |
| First-class extension | `register_head` clauses share the same `ClauseSet`/ambiguity machinery as user clauses |

Getting the tree walker right — especially §6 (dispatch) and §7
(rewriting) — is what will make or break whether a future bytecode
compiler can be built as a faithful, semantics-preserving optimization
rather than a second, subtly different implementation of the language.
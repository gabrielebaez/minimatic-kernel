# The Minimatic Prelude — Proposed Head Collection

**Status:** Proposal / work in progress — for discussion against the
language design (`minimatic-language-design.md`) before any head listed
here is implemented.
**Scope:** the standard collection of heads available in every Minimatic
session without an explicit `register_head` call from host application
code. Host-specific heads (`http_get`, domain algorithms, etc.) are out of
scope — this document is about what ships with the language itself.

## 1. What the Prelude is, and isn't

Minimatic's core language (§1–§13 of the language design doc) defines
*how* heads behave — dispatch, patterns, attributes, rewriting, pipes,
`Ok`/`Err`. It defines almost none of *which* heads exist. Something has
to provide `map`, `filter`, comparison operators, string handling, and so
on, or the language is unusable for real work despite being fully
specified.

The Prelude is that "something": a fixed, curated set of heads, loaded
into every kernel by default, occupying the same status as any
`register_head`-registered function (§14 of the language doc) — no
privileged builtins, no special-cased dispatch. Concretely this means:

- **Two implementation tiers**, invisible from the language surface:
  - **Primitives** — heads that cannot be expressed in terms of other
    Minimatic heads and must be implemented directly in the kernel
    (arithmetic, comparison, the evaluator-facing parts of `Hold`/`/.`).
  - **Derived** — heads implementable *in Minimatic itself*, in terms of
    primitives and other derived heads (`fold`, `unique`, `group_by`,
    most of the list/dict/string library). These should actually be
    written in Minimatic, both as a stress test of the language and
    because it keeps their behavior consistent with user-level dispatch
    and specificity rules by construction rather than by parallel
    Python logic that has to be kept in sync.
- **A closed, versioned set.** The Prelude is not something users extend
  in place — adding a clause to a Prelude head from user code goes
  through the same ambiguity-checking as adding a clause to anything
  else (language doc §7.2), so an incompatible addition is rejected, not
  silently merged.

## 2. Design considerations specific to the Prelude

A few cross-cutting rules, applied to every head below, that don't follow
automatically from the core language spec and need to be decided once,
here, rather than ad hoc per-function:

1. **Pipe-first argument order.** Any head commonly used with `|>` takes
   the "subject" as its *last* positional argument in the function-call
   form, so that `xs |> filter(pred)` and `filter(pred, xs)` both make
   sense and `filter(pred)` partially applies cleanly under `|>`. This is
   the Elixir/Ramda convention, not the Wolfram one (`Select[list,
   pred]`), and it's chosen because the pipe is Minimatic's idiomatic
   composition style (language doc §13).
2. **`Ok`/`Err` awareness is opt-in and explicit**, per language doc §12
   — Prelude heads that should observe `Err` values directly (rather than
   being skipped by pipe short-circuiting) are marked `ResultAware` below;
   everything else assumes it will never receive an `Err` as an argument
   coming through a pipe.
3. **No head silently coerces types.** `plus(1, "2")` is an error, not
   `"12"` or `3` — consistency here matters more than convenience, given
   principle 2 of the language (strict, deterministic evaluation with one
   correct outcome per call).
4. **Naming: `snake_case` for multi-word heads, lowercase single words**
   (`map`, `fold`, `plus`), reserving `PascalCase` for heads that
   construct or inspect the language's own structure (`Hold`,
   `ReleaseHold`, `Attributes`, `MatchQ`) — a visual cue that these are
   meta-level, not ordinary data-processing heads. This mirrors, but
   deliberately narrows, Wolfram's convention of PascalCase for
   everything.
5. **Every predicate ends in `Q`** (`is_ok`/`is_err` are the one
   established exception, kept for continuity with the language doc's own
   examples) — `ListQ`, `EmptyQ`, `IntQ`. Consistent enough to guess.

## 3. Arithmetic and comparison (primitive)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `plus` | `plus(x, y, ...)` | `Flat`, `Orderless` | `+` sugar |
| `minus` | `minus(x, y)` | — | `-` sugar (binary); unary negation is `negate(x)` |
| `times` | `times(x, y, ...)` | `Flat`, `Orderless` | `*` sugar |
| `divide` | `divide(x, y)` | — | `/` sugar; returns `Err("DivideByZero", _)` for `y == 0` rather than raising |
| `power` | `power(x, y)` | — | `^` sugar |
| `mod` | `mod(x, y)` | — | `%` sugar |
| `abs`, `floor`, `ceil`, `round` | `abs(x)` etc. | — | |
| `min`, `max` | `min(x, y, ...)` | `Flat`, `Orderless` | |
| `equal`, `not_equal` | `equal(x, y)` | — | `==`, `!=` sugar; structural equality, defined over the shared `Node` representation (kernel doc §2) |
| `less`, `greater`, `less_eq`, `greater_eq` | `less(x, y)` | — | `<`, `>`, `<=`, `>=` sugar |

**Derived, not primitive:** `clamp(x, lo, hi)`, `sign(x)`, `sum(xs)` /
`product(xs)` (thin wrappers over `fold` + `plus`/`times`, §5) — these
don't need kernel-level implementation.

## 4. Logic (primitive)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `and`, `or` | `and(a, b, ...)` | `HoldRest`, `Flat` | short-circuiting — `HoldRest` so unevaluated later arguments aren't forced once the result is determined |
| `not` | `not(a)` | — | `!` sugar |
| `xor` | `xor(a, b)` | `Orderless` | non-short-circuiting; both sides always needed |

`&&`/`\|\|`/`!` are surface sugar for `and`/`or`/`not`. Short-circuiting
via `HoldRest` is worth calling out explicitly: it's the same hold
mechanism used for user macros (language doc §10), applied here to a
Prelude head rather than to `Hold` itself — direct evidence that the
mechanism doesn't need special-casing per use.

## 5. List (mostly derived)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `List` | `List(x, ...)` | — | the `[...]` literal's head |
| `length` | `length(xs)` | — | primitive |
| `first` | `first(xs)` | — | `Err("EmptyList", _)` on `[]`, not a raised error. Not `[]` — an empty list is itself a legitimate element, so the two cases must stay distinguishable |
| `rest` | `rest(xs)` | — | total: `rest([])` is `[]`. Unlike `first`, it has a sensible answer for the empty list, and making it fail would put an `Err` unwrap in every recursive traversal |
| `append`, `prepend` | `append(xs, x)` | — | new list |
| `concat` | `concat(xs, ys, ...)` | `Flat` | list concatenation |
| `map` | `map(f, xs)` | — | primitive-adjacent (drives evaluation order); pipe form `xs \|> map(f)` |
| `filter` | `filter(pred, xs)` | — | |
| `fold` | `fold(f, init, xs)` | — | left fold; the one list head every other list head in this table can plausibly be derived from |
| `reduce` | `reduce(f, xs)` | — | `fold` without explicit seed; `Err("EmptyList", _)` on `[]` |
| `zip`, `zip_with` | `zip(xs, ys)`, `zip_with(f, xs, ys)` | — | |
| `sort`, `sort_by` | `sort(xs)`, `sort_by(f, xs)` | — | stable sort |
| `reverse` | `reverse(xs)` | — | |
| `take`, `drop` | `take(n, xs)`, `drop(n, xs)` | — | |
| `take_while`, `drop_while` | `take_while(pred, xs)` | — | |
| `flatten` | `flatten(xs)` | — | one level; `flatten_all` / `flatten(xs, depth)` for deeper |
| `unique` | `unique(xs)` | — | first-occurrence order preserved |
| `group_by` | `group_by(f, xs)` | — | returns a `Dict` |
| `chunk` | `chunk(n, xs)` | — | fixed-size sublists |
| `any`, `all`, `none` | `any(pred, xs)` | — | |
| `find` | `find(pred, xs)` | — | returns `Ok(x)` / `Err("NotFound", _)`, not a bare value — this is `ResultAware`-producing, distinguishing "found nothing" from "found a falsy value" |
| `range` | `range(a, b)`, `range(a, b, step)` | — | function form of `a..b` |
| `sum`, `product` | `sum(xs)` | — | derived from `fold` |

`map` deserves a note: it is listed as "primitive-adjacent" because it's
the one list head whose *evaluation order* over `xs` (left to right,
each element fully evaluated before the next starts) is part of its
observable contract, not an incidental implementation choice — relevant
if `f` has any interaction with `Hold`-captured state or ordering-sensitive
host-registered heads.

## 6. Dict (derived, atop a small primitive core)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `Dict` | `Dict(Rule(k, v), ...)` | — | the `{...}` literal's head |
| `keys`, `values` | `keys(d)`, `values(d)` | — | returns `List` |
| `key_get` | `key_get(d, k)` | — | `Ok(v)` / `Err("KeyNotFound", _)` — `d[k]` sugar instead raises for missing keys, matching list indexing's error behavior; `key_get` is the `Ok`/`Err`-returning alternative for pipelines |
| `key_set` | `key_set(d, k, v)` | — | new dict |
| `key_drop` | `key_drop(d, k)` | — | new dict |
| `has_key` | `has_key(d, k)` | — | `HasKeyQ` was considered and rejected — reads worse |
| `merge` | `merge(d1, d2, ...)` | `Flat` | right-biased on conflicting keys |
| `map_values`, `map_keys` | `map_values(f, d)` | — | |
| `to_pairs`, `from_pairs` | `to_pairs(d)` | — | `Dict` ⇄ `List` of `Rule`s, for reuse of list combinators on dicts |

## 7. String (derived, atop a small primitive core)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `str` | `str(x)` | — | primitive; canonical string conversion for any value |
| `length` | (shared with List) | — | strings and lists share `length`, `first`/`rest`, `take`/`drop` where the semantics genuinely coincide (both are ordered sequences) — see §9 |
| `split`, `join` | `split(s, sep)`, `join(xs, sep)` | — | |
| `upper`, `lower`, `trim` | `upper(s)` | — | |
| `replace` | `replace(s, old, new)` | — | literal substring, not pattern-based — pattern-based text rewriting should go through `/.` on a parsed/tokenized form instead, not duplicate rewrite semantics under a different name |
| `contains`, `starts_with`, `ends_with` | `contains(s, sub)` | — | |
| `format` | `format(template, args)` | — | placeholder-based templating; exact syntax TBD (open question, §11) |
| `to_int`, `to_float` | `to_int(s)` | — | `Ok`/`Err`-returning, since parse failure is routine, not exceptional |

## 8. Functional combinators (derived)

| Head | Signature | Notes |
|---|---|---|
| `identity` | `identity(x)` | returns `x` unchanged |
| `const` | `const(x)` | returns a one-argument function that always returns `x`, ignoring its argument |
| `compose` | `compose(f, g, ...)` | right-to-left composition: `compose(f, g)(x) == f(g(x))` |
| `pipe_fn` | `pipe_fn(f, g, ...)` | left-to-right composition — the function-value counterpart to the `\|>` operator, for when a composed function needs to be stored or passed rather than applied immediately |
| `flip` | `flip(f)` | swaps a two-argument function's argument order |
| `apply` | `apply(f, xs)` | calls `f` with the elements of list `xs` as separate arguments |
| `curry` | `curry(f)` | listed as an open question — see §11.3 |

`compose` and `pipe_fn` existing as two separate heads, rather than one
head with a flag, is deliberate: `compose(f, g)` and `pipe_fn(f, g)` read
correctly at the call site without needing to remember which order a
boolean argument implies.

## 9. Type predicates and shape inspection

| Head | Signature | Notes |
|---|---|---|
| `IntQ`, `FloatQ`, `StringQ`, `BoolQ`, `ListQ`, `DictQ`, `FunctionQ` | `ListQ(x)` | correspond to the pattern type tags (`_int`, `_string`, ...) — `ListQ(x) == MatchQ(x, _list)`, provided as a convenience, not a separate mechanism |
| `EmptyQ` | `EmptyQ(x)` | works over `List`, `Dict`, and `String` uniformly |
| `MatchQ` | `MatchQ(x, pattern)` | primitive — direct kernel support (kernel doc §5) |
| `match` | `match(x, pattern)` | destructuring match, returns bindings as a `Dict`, or `Err("NoMatch", _)` |
| `Cases` | `Cases(xs, pattern)` | returns the sublist of `xs` matching `pattern` — the `filter`/`MatchQ` combination made convenient, in the spirit of Wolfram's `Cases` |

The overlap between `ListQ`/`EmptyQ` (data-shape predicates) and patterns
like `_list` (the same check, spelled as a pattern) is intentional
duplication: patterns are for *matching and destructuring in place*
(clause heads, `match`, `/.`), predicates are for *use as an ordinary
boolean-returning function* (inside `if`, `filter`, `and`/`or` chains).
Both should exist rather than forcing one idiom into the other's job.

## 10. Rewriting and reflection (primitive)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `Hold` | `Hold(expr)` | `HoldAll` | primitive; captures unevaluated |
| `ReleaseHold` | `ReleaseHold(expr)` | — | primitive; re-enters evaluation |
| `Rule`, `RuleDelayed` | `Rule(lhs, rhs)` | `HoldRest` (`RuleDelayed` only) | underlie `->` / `:>` sugar |
| `ReplaceAll` | `ReplaceAll(expr, rules)` | — | underlies `/.` sugar |
| `Attributes` | `Attributes(head)`, `Attributes(head) := [...]` | `HoldFirst` | reads or sets a head's attribute set (kernel doc §8); setting after clauses exist is a definition-time error (language doc §10) |
| `Head` | `Head(expr)` | — | the expression's head symbol. Total — `Head([])` is `List`, `Head(5)` is `Integer` |
| `Args` | `Args(expr)` | — | the expression's arguments, as a `List`. `Args(5)` is `[]` |

`Head`/`Args` were long listed here as `head_of`/`args_of`, with some
hesitation: they let user code branch on expression *shape* outside of
pattern matching, which starts to blur the "rewriting is explicit, not
ambient" line if overused. They are included, under their conventional
names, for two reasons.

First, the naming. `head` cannot mean "first element of a list" in a
language whose one organising idea is that everything is `head(args)`
(language doc §4) — that was a collision at the centre of the vocabulary,
and the kernel had it in a single line of code, implementing first-element
as `list_expr.tail[0]`. The list accessors are now `first`/`rest` (§5), and
`Head`/`Args` take the names that were always theirs, PascalCase per §2.4.

Second, the hesitation is much weaker than it looks while `Hold` is
deferred: these can only inspect *evaluated* data, which patterns already
destructure. `Head` is also total in a way no pattern is — every value has
one, including `[]` and atoms — which is what makes it a reasonable
result-kind test (`Head(r) == Err`) alongside `is_err`.

## 11. Errors and results (primitive core + derived combinators)

| Head | Signature | Attributes | Notes |
|---|---|---|---|
| `Ok`, `Err` | `Ok(v)`, `Err(kind, detail)` | — | primitive constructors |
| `is_ok`, `is_err` | `is_ok(r)` | `ResultAware` | |
| `unwrap` | `unwrap(r, default)` | `ResultAware` | |
| `unwrap_err` | `unwrap_err(r)` | `ResultAware` | |
| `catch` | `catch(r, kind, handler)` | `ResultAware` | handles a specific `Err` kind, passes others through unchanged |
| `recover` | `recover(r, handler)` | `ResultAware` | handles any `Err` |
| `finally` | `finally(r, f)` | `ResultAware` | runs `f` for its side effect regardless of `Ok`/`Err`, then returns `r` unchanged |
| `map_ok` | `map_ok(r, f)` | `ResultAware` | applies `f` inside `Ok`, passes `Err` through — the piece missing from the language doc's own examples, needed so a pipeline can transform a *successful* value without every downstream function needing to be `ResultAware` itself |
| `and_then` | `and_then(r, f)` | `ResultAware` | like `map_ok`, but `f` itself returns a `Result` — for chaining fallible steps without nesting |

`map_ok`/`and_then` are a proposed addition beyond what's shown in the
language design doc's examples — without them, turning a successful `Ok`
value into another `Ok`/`Err` mid-pipeline requires dropping into `match`
every time, which undercuts the pipe-composition idiom (language doc §13)
for the most common case in practice: a chain of several fallible steps.

## 12. I/O and environment (primitive, thin)

| Head | Signature | Notes |
|---|---|---|
| `print` | `print(x)` | side-effecting; returns `x` unchanged so it composes in a pipe for debugging (`xs \|> print \|> map(f)`) |
| `read`, `write` | `read(path)`, `write(path, content)` | `Ok`/`Err`-returning |
| `to_json`, `from_json` | `to_json(x)`, `from_json(s)` | `from_json` is `Ok`/`Err`-returning |
| `now` | `now()` | current timestamp — deliberately **not** memoized/pure; calling it twice can differ, which is worth flagging against principle 2 (determinism) — see §11.5 open question... actually §13.5 below |
| `random` | `random()` | same non-determinism caveat as `now` |

`print`, `now`, and `random` are the three heads in this entire proposal
that are in real tension with "strict, deterministic evaluation... exactly
one obviously-correct outcome" (language doc principle 2). They're kept
because a language positioned as a practical workbench needs them, but
they should probably be flagged, formally, as an explicitly acknowledged
exception rather than quietly included as if they were no different from
`plus`.

## 13. Self-hosting: what should be written *in* Minimatic

As a concrete illustration of §1's "derived" tier, here is roughly how
`fold` could sit at the bottom of the derived layer, with `sum` built on
top of it entirely in Minimatic, using nothing but ordinary clause
dispatch:

```
fold(f: _, init: _, [])                := init
fold(f: _, init: _, [x: _, rest: ___]) := fold(f, f(init, x), rest)

sum(xs: _list) := fold(plus, 0, xs)
```

The cons clause uses `___` (zero-or-more), not `__` (one-or-more). With
`__` the two clauses leave a hole: a *single*-element list matches neither,
since `[]` requires no elements and `[x: _, rest: __]` requires at least
two. This is worth stating because the mistake is invisible until a
one-element list reaches the function.

This is a useful design constraint to hold onto deliberately: **any
Prelude head that can be written this way, should be** — it's the best 
possible test that the core language (clause dispatch + specificity + sequence
patterns) is actually sufficient for real list-processing work, without
needing to quietly reach for kernel-level primitives to cover gaps. Any
head in §5–§9 that turns out to *need* primitive implementation despite
looking "ordinary" is a signal that something in the core language
(kernel doc or language doc) is missing, not just that the Prelude needed
an exception.

## 14. Open questions

1. **`format`/templating syntax** (§7) — not yet designed; needs its own
   short spec (placeholder syntax, escaping, whether it supports the same
   pattern grammar as `/.` for more than plain substitution).
2. **`curry`** (§8) — worth including at all, given Minimatic's clause
   arity is otherwise fixed per call? A curried function is a `Lambda`
   returned from a `Lambda`, which the language already supports without
   a dedicated head; `curry` may be redundant sugar rather than a needed
   primitive.
3. **String/List head sharing** (§7) — `length`, `first`/`rest`,
   `take`/`drop` are proposed as shared across `String` and `List`. Does
   this mean dispatch needs a "sequence-like" pattern type broader than
   `_list`/`_string` individually, or does each head just get two clauses
   (one per type)? This has real consequences for the specificity/
   ambiguity machinery (kernel doc §6) and should be resolved before
   implementation.
4. ~~**`head_of`/`args_of`** (§10) — should these exist?~~ **Closed:** yes,
   as `Head`/`Args`. See §10 for the reasoning and for why the list
   accessors became `first`/`rest`.
5. **Non-determinism in `now`/`random`** (§12) — should these require an
   attribute marking them as impure/non-deterministic (visible in
   tooling, e.g. a linter warning if used inside something meant to be
   pure), or is "the Prelude has three acknowledged exceptions" a
   sufficient answer on its own?
6. **Prelude versioning.** If the Prelude itself needs to change
   (add/remove/alter a head) after `minimatic-workbench` notebooks with
   orthogonally-persisted symbols exist, how does that interact with
   persisted external symbols that reference a since-changed Prelude
   head? This is the same class of problem flagged for user-defined heads
   in the tree-walker doc's open questions, just applied to the Prelude
   itself — probably deserves a single unified answer rather than two.
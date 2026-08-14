# Proposal 001 — Dispatch, Results, and Pipes

**Date:** 2026-08-07
**Status:** Proposal — for review against `docs/the language.md`, `docs/the
kernel.md`, and `docs/the prelude.md` before any of it is adopted.
**Scope:** language semantics and the corresponding kernel commitments.
No code or existing design doc is changed by this document; §4.6 lists the
edits adoption would require.

---

## 1. Summary

`IMPLEMENTATION_PLAN.md` shipped the MVP by **deferring** four things and
locking two. This proposal converts several of those deferrals into
**permanent decisions**, resolves one open question outright, and specifies
two semantics that were previously only sketched.

The through-line: Minimatic keeps *determinism* and *closed clause sets*,
and gives up *static rejection of overlapping clauses*. Everything the
language guarantees about dispatch remains knowable by reading the source —
it is simply no longer enforced by a definition-time error.

| Question | Decision | Change from MVP plan |
|---|---|---|
| Nested ambiguity checking | **Remove.** No `overlaps`/`implies`, no `AmbiguousClauseError`. | deferred → **permanent** |
| Clause ordering | **Hybrid.** `score()` descending; same-score clauses tried in declaration order. | placeholder → **specified behavior** |
| `Flat` / `Orderless` | **Remove** from the language. | deferred → **permanent** (§2.3) |
| `Hold` / `ReleaseHold` (held code, env capture) | Deferred. | unchanged |
| `Value` / `Err` | **Return the raw value, or `Err`.** No `Ok` wrapper. | new (§2.5) |
| Self-hosting derived prelude | Deferred to post-MVP. | unchanged |
| Flat/Orderless dispatch canonicalization | Moot — resolved by §2.3. | superseded |
| Redefinition semantics | Clause sets sealed after first dispatch. | unchanged |
| Multi-arg pipe | **Template-position `$`:** `a \|> f($, b)` → `f(a, b)`, `a \|> f(b, $)` → `f(b, a)`. | fixed-first → **template** (§2.8) |

> **Note on the input table.** It listed Flat/Orderless as "resolve the open
> question" while a later row still said "N/A (deferred with
> Flat/Orderless)". §2.3 resolves the first; the second row is superseded
> rather than answered — with the attributes removed there is no
> canonicalization step to order relative to dispatch.

---

## 2. Decisions

### 2.1 Nested ambiguity checking — remove

**Decision.** `overlaps()`, `implies()`, and `AmbiguousClauseError` are
removed from the design, not merely from the MVP. `docs/the kernel.md` §6.1
and §6.3 are deleted; §14.1 is closed as "will not do".

**Rationale.** The check was specified as the highest-risk, least-specified
part of the kernel, and it is undecidable-in-practice over the pattern
grammar the language actually has (nested compound patterns, sequence
blanks with variable arity, type tags). The kernel doc itself argues that a
false positive is worse than a missed ambiguity — which is an argument that
the check must be conservative, and a conservative overlap test over nested
sequence patterns degenerates toward "everything overlaps everything." The
MVP has run without it and the gap has not been the thing that hurt.

**What this costs.** `docs/the language.md` §7.2 — "ambiguity is an error,
not a resolved-by-convention case" — is one of the six things the language
was positioned on. It goes away. This is the single most consequential item
in this proposal and the one most worth rejecting it over.

**What survives.** The guarantee weakens from *"no clause can be silently
shadowed"* to:

> Dispatch order is a pure function of the clause set, fixed at definition
> time by a published static rule: descending `score()`, then declaration
> order. It never depends on runtime state, call history, or a global
> mutable rule table.

That is still a real and unusual property, and it is still strictly stronger
than the prior art the design was reacting to. It is just a smaller claim,
and the docs should make the smaller claim rather than keep the larger one.

**Escape hatch.** Because the tie-break is *specified* rather than
accidental, a conservative overlap check can be re-introduced later as a
**non-fatal lint** (a warning at definition time, or a `strict=True` kernel
flag) without changing dispatch semantics for anyone. That is the
recommended future direction if the safety story needs shoring up — see
§5.

### 2.2 Clause ordering — the hybrid becomes the specification

**Decision.** `score()` is unchanged: per-argument specificity — literal
`3`, typed blank `2`, bare blank / bare binding symbol `1`, sequence blank
`0` — compared lexicographically, sorted descending. **Same-score clauses
are tried in declaration order**, first structural match wins. This is the
final behavior, not a placeholder.

**Rationale.** Cheap, fully specified, already implemented
(`minimatic/dispatch.py`), and it preserves the property §7.1 of the
language doc actually cares about in practice: `describe(_int)` /
`describe(_string)` / `describe(_)` behave identically no matter what order
they are written in, because their scores differ.

**What changes in practice.** Declaration order becomes semantically
load-bearing for same-score clauses. See §4.1 and §4.2 — this has
consequences well beyond the dispatcher.

### 2.3 `Flat` and `Orderless` — remove

**Decision.** Both attributes are removed from the language. `Attributes`
retains `HoldAll`/`HoldFirst`/`HoldRest`/`Listable`/`ResultAware`.
`docs/the kernel.md` §14.2 and `docs/the language.md` §16.3 are closed as
"will not do".

**Rationale.** Their only genuine payoff is pattern matching over
arithmetic trees — matching `plus(a, b, c)` against a tree that was parsed
as `plus(plus(a, b), c)`, or matching modulo argument order. That is a
*symbolic-rewriting* capability, and symbolic rewriting (`Hold` /
`ReleaseHold` / `:>`) is deferred. Keeping the attributes would mean paying
for a canonicalization step, a canonical-ordering rule across mixed types,
and their interaction with `score()`, in order to serve a layer that does
not exist yet.

Nothing else depends on them:

- **Variadic arity is unaffected.** `plus(1, 2, 3)` works because the
  head's clause pattern uses a sequence blank, not because of `Flat`.
- **Ordinary evaluation is unaffected.** `1 + 2 + 3` parses to
  `plus(plus(1, 2), 3)` and evaluates correctly by inner-first strict
  evaluation; flattening would change the tree, not the answer.
- **`Listable` is untouched** and continues to carry the threading behavior
  the flagship `/.` example depends on.

**Reversibility.** If the rewriting layer is un-deferred later, this
decision should be revisited *then*, together with the permutation-matching
question it implies — which is the right time to ask it, because that is
the first point at which the answer is observable.

### 2.4 `Hold` / `ReleaseHold` — deferred (unchanged)

Held *code* and lexical env-snapshot capture stay out. `/.` remains
data-rewriting over evaluated values; `:>` continues to parse and raise
`NotImplementedInMVPError` (`minimatic/parser.py:151`) rather than silently
behaving like `->`.

Consequently `docs/the language.md` §16.4 (scoping of `Hold`-captured free
variables) and `docs/the kernel.md` §14.4 (error identity through `Hold`)
stay open, and `docs/the prelude.md` §14.4 (`head_of`/`args_of`) stays
moot.

### 2.5 `Value` / `Err` — raw value or `Err`

**Decision.** Success is the value itself. There is **no `Ok` wrapper.**
Failure is an `Err` expression.

```
Err(kind, detail)        kind: string;  detail: optional, any value

read("file.txt")         (* the contents, or Err("IOError", "...") *)
to_int("12")             (* 12,          or Err("ParseError", "...") *)
divide(1, 0)             (* Err("DivideByZero", _) *)
```

Normative rules:

1. A failable head returns its ordinary result on success and an
   `Err`-headed expression on failure. `Ok` is not a head.
2. `Err` is an ordinary expression — constructed, matched, and
   destructured with the same pattern grammar as anything else
   (`Err("IOError", d: _)`).
3. A pipeline short-circuits when the piped subject is an `Err`-headed
   expression **and** the target head does not carry `ResultAware`. The
   `ResultAware` mechanism from `docs/the kernel.md` §9.2 is unchanged; only
   the test changes, from "is `Ok`-or-`Err`" to "is `Err`".
4. Short-circuiting applies to the *subject of a pipe only*. A direct call
   `process(Err(...))` is not short-circuited; it dispatches normally and
   will typically fail to match a clause.

**Rationale, and the main win.** Under `Ok`/`Err`, every pipeline stage
that wants to transform a successful value has to be lifted — hence
`map_ok` and `and_then`, which `docs/the prelude.md` §11 proposed
specifically to stop `match` from being mandatory mid-pipeline. With an
unwrapped success value, **ordinary function application through the pipe
already is `map_ok`**, and a function that itself returns value-or-`Err`
already chains like `and_then`. The entire lifting layer disappears rather
than being provided.

**What this costs.** A pipeline cannot transport an `Err` as ordinary
payload at the top level — there is no `Ok(Err(...))` to distinguish
"succeeded, and the value happens to be an `Err`" from "failed". In
practice: put such values inside a `List`, or reach for `unwrap_err`.
Nesting depth of failure is no longer observable. This is a real loss and
is judged acceptable; it should be stated plainly in the language doc
rather than left to be discovered.

**Prelude consequences** — `docs/the prelude.md` §11 becomes:

| Head | Keeps / drops |
|---|---|
| `Err` | keeps (the only constructor) |
| `Ok`, `is_ok` | **drop** — success has no wrapper; `!is_err(x)` says it |
| `is_err` | keeps, `ResultAware` |
| `unwrap(r, default)` | keeps — `default` if `r` is `Err`, else `r` |
| `unwrap_err(r)` | keeps |
| `catch(r, kind, handler)`, `recover(r, handler)`, `finally(r, f)` | keep |
| `map_ok`, `and_then` | **drop** — subsumed by ordinary application (above) |

`find` (prelude §5) still works as designed: it returns the raw element or
`Err("NotFound", _)`, and the distinction it was built for — "found
nothing" versus "found a falsy value" — survives, because `Err` is a
distinct head rather than a falsy value.

### 2.6 Self-hosting derived prelude — deferred (unchanged)

Derived heads continue to ship as Python. An earlier draft claimed this
deferral was hiding a dispatch prerequisite; it was not — see the
correction at the end of §4.2.

### 2.7 Redefinition — sealed after first dispatch (unchanged)

A `ClauseSet` is sealed the first time it is dispatched against; a later
`define` raises `HeadAlreadySealedError`. Unchanged from the original
design — but see §4.1: with ambiguity checking gone, sealing becomes the
*only* structural protection against surprise redefinition, so it now
carries weight it was not originally carrying alone.

### 2.8 Multi-arg pipe — template-position `$`

**Decision.** `$` is a placeholder marking where the piped subject lands.

```
a |> f                (* f(a) *)
a |> f(b, c)          (* f(a, b, c)  — no $: first position, as today *)
a |> f($, b, c)       (* f(a, b, c) *)
a |> f(b, $, c)       (* f(b, a, c) *)
a |> f(b, g($))       (* f(b, g(a))  — any depth *)
a |> f($, $)          (* f(a, a)     — subject evaluated once *)
```

`//` is the same operator and behaves identically.

Normative rules:

1. **No `$` in the right-hand side → first-position splice**, exactly as
   today. This makes the change purely additive: every existing pipe
   expression keeps its current meaning, and there is no migration.
2. **Any `$` present → template substitution**, at every occurrence, at any
   depth. First-position splicing is *not* also applied.
3. The subject is evaluated exactly once. This is structural rather than a
   rule to enforce: `__pipe__` is `HoldRest` and receives the subject
   already evaluated (`minimatic/prelude.py:61`), so substitution copies a
   value, never re-runs an expression.
4. **Substitution does not descend into a nested `__pipe__`'s right-hand
   side.** In `a |> f($ |> g($))` the outer `$` binds the left `$`; the
   inner `$` belongs to the inner pipe and is resolved when that pipe
   evaluates. (A nested pipe's *left*-hand side is substituted normally.)
5. `a |> (x -> ...)` — a `Lambda` right-hand side — is applied to the
   subject, unchanged from today.
6. For `Err` short-circuiting (§2.5 rule 3), the "target head" of a
   template form is the head of the template body when the body is a direct
   call. If the body is not a call (`a |> ($ + 1)`), there is no head and
   short-circuiting applies.

**The `$` sigil.** `docs/the language.md` §8 currently gives `$` a second,
unrelated meaning — the implicit lambda parameter, `square($) := $ * $`.
**That form is removed**; `x -> x * 2` becomes the only lambda syntax.
Nothing breaks: there is no `$` token in the lexer today, so §8's implicit
form was never implemented. Adoption adds a `DOLLAR` token and leaves `$`
with exactly one meaning in the language.

(§8's other unimplemented form, postfix `&` on a lambda, is now doubly
orphaned — the `AMP` token exists in `minimatic/lexer.py:108` and the
parser ignores it. Recommend either implementing it or striking it from
§8; this proposal does not decide it.)

**Implementation site.** All of this lives in `_impl_pipe`
(`minimatic/prelude.py:61`), which already receives the right-hand side
unevaluated. Substitution happens over that raw tree before `ctx.eval`. No
parser change beyond the new token.

---

## 3. What is *not* changed

Stated explicitly so the proposal's blast radius is legible:

- Single-pass evaluation, no fixpoint loop (`docs/the kernel.md` §4.1).
- One `Node` type for code and data (§2), and one `match()` shared by
  dispatch and rewriting (§5).
- `register_head` symmetry — no privileged builtins (§11.1).
- Immutability, `Listable`, hold attributes, control-flow-as-heads.
- The `ResultAware` mechanism itself (§9.2) — only its predicate changes.

---

## 4. Implications

### 4.1 What the language stops guaranteeing

- **Silent shadowing becomes possible.** Two same-score clauses with
  overlapping domains now resolve by declaration order with no diagnostic.
  This is precisely the footgun `docs/the language.md` §7.2 was written to
  eliminate.
- **Clause declaration order is now semantic.** Reordering two same-score
  clauses in a source file is a behavior-changing edit. §7.1's specific
  example survives (its three clauses have different scores), but its
  general claim — that order is "never semantically load-bearing" — does
  not, and must be narrowed rather than left standing.
- **Sealing is now the only structural guard on redefinition.** A user
  clause added to a prelude head before that head is first called wins by
  score, silently. `register_head` registers a catch-all sequence-blank
  clause (score `0`), so *any* user clause outscores it. This was always
  true; it was previously backstopped by ambiguity rejection and is now
  backstopped only by §2.7.
- **`dispatch.py`'s own docstring becomes wrong.** It currently disclaims
  the tie-break — "callers should not treat same-score-tie resolution as a
  stable, guaranteed feature; it is a placeholder." Under §2.2 it *is* the
  guaranteed feature and must be documented as such.

### 4.2 One load-bearing consequence: `score()` did not recurse

> **Resolved.** `score()` now recurses into compound patterns. What follows
> is kept as the record of why, since it is the clearest illustration of
> what removing ambiguity rejection costs.

`_score_one` returned `3` for *any* compound `Expression` pattern, without
recursing into its arguments. So these two clauses tied:

```
handle(Err("IOError", d: _)) := ...      (* score (3,) *)
handle(Err(k: _, d: _))      := ...      (* score (3,) — tie *)
```

The obviously-more-specific clause won only if it happened to be declared
first — and declared *second*, it never fired at all. While ambiguity
detection existed, this pair would have been *rejected*, and the flatness of
`score()` never mattered. Removing the check turned it into silent wrong
dispatch, landing squarely on **`Err`-versus-`Err` dispatch**, the primary
error-handling idiom under §2.5. (`Err` versus a plain value was always
fine: a bare binder scores `1`, a compound `3`, so `docs/the language.md`
§12's `match` example resolved correctly throughout.)

The fix: a compound pattern scores as a nested vector over its arguments,
compared structurally, so `Err("IOError", d: _)` → `(3, ((3,), (1,)))`
strictly outscores `Err(k: _, d: _)` → `(3, ((1,), (1,)))`. It is entirely
local to `dispatch.py` and requires none of the `overlaps`/`implies`
machinery this proposal removes.

**Correction — self-hosting was never blocked on this.** An earlier draft of
this section claimed `docs/the prelude.md` §13's self-hosted `fold` "works
today only by declaration order." That was wrong: its two clauses are
**disjoint** (`[]` versus a non-empty list), so both orderings always
agreed. What §13 actually had was an unrelated bug — written with `__`
(one-or-more), a single-element list matched *neither* clause and raised
`NoMatchingClauseError`. It needs `___`. Both the claim and the example
have been corrected.

### 4.3 Downstream: `minimatic-workbench`

- **Clause sets are ordered sequences, not sets.** Any persistence or
  serialization of a head must preserve declaration order, because it now
  determines behavior. Under the original design, order was
  non-load-bearing — anything order-sensitive would have been rejected — so
  a persistence layer could legitimately have stored clauses unordered.
  That is no longer safe.
- **Re-running a notebook cell that defines a clause** on an
  already-dispatched head still raises `HeadAlreadySealedError` (§2.7),
  unchanged — but it is now the entire redefinition safety story, and the
  workbench's cell-re-execution model has to have an answer for it.

### 4.4 Prelude changes

- §3, §4, §5, §6: strike the `Flat`/`Orderless` attribute entries from
  `plus`, `times`, `min`, `max`, `and`, `or`, `xor`, `concat`, `merge`.
  No signature or arity changes — see §2.3.
- §11: apply the table in §2.5 (drop `Ok`, `is_ok`, `map_ok`, `and_then`).
- §13: keep as an aspiration; fix the `fold` example's `__` → `___` (see
  the correction at the end of §4.2).

### 4.5 Open questions closed and opened

| Question | Status after this proposal |
|---|---|
| kernel §14.1 — ambiguity-check completeness | **Closed** — will not do (§2.1) |
| kernel §14.2 — Flat/Orderless vs. dispatch | **Closed** — moot (§2.3) |
| kernel §14.3 — redefinition semantics | **Closed** — sealed (§2.7) |
| kernel §14.4 — error identity through `Hold` | Open (deferred with `Hold`) |
| language §16.3 — ordering under `Orderless` | **Closed** — moot (§2.3) |
| language §16.4 — `Hold`-captured free variables | Open (deferred with `Hold`) |
| language §16.5 — multi-argument pipe | **Closed** (§2.8) |
| language §16.1/§16.2 — numeric tower, strings | Open, untouched |
| prelude §14.2/§14.3/§14.5/§14.6 | Open, untouched |
| **New:** nested `score()` for compound patterns | **Closed** — implemented (§4.2) |

### 4.6 Documentation edits adoption would require

**`README.md`**
- Design goals: delete "Ambiguous, overlapping clauses are caught as an
  error at definition time"; replace with the §2.1 formulation.
- Design goals: "Errors are values" — restate as value-or-`Err`, drop
  `Ok`.
- Design goals: drop the closing paragraph's claim that ambiguity
  resolution "is most of the current work."
- Status table: delete the ambiguity-detection row; retitle the `Flat` /
  `Orderless` entries as removed; restate the `Ok`/`Err` row.
- The "MVP dispatch note" blockquote: rewrite — it currently calls the
  tie-break "a temporary gap, not a supported feature," which §2.2
  reverses.
- Line 10's summary of repo contents overclaims the rewrite machinery
  given §2.4.
- *Unrelated, noticed in passing:* the link to
  `docs/learn_minimatic_in_15_minutes.md` is broken — the file now lives in
  `scratch/`.

**`docs/the language.md`**
- §7.2: delete, or rewrite as "how ties resolve".
- §7.1: narrow the "order is never load-bearing" claim (§4.1).
- §8: remove the `$` implicit-lambda form (§2.8); decide postfix `&`.
- §10: delete the `Flat`/`Orderless` paragraph.
- §12: rewrite every example — no `Ok`; the `match` example's `Ok(data)`
  clause becomes a bare binder fall-through.
- §13: specify the `$` template form.
- §16: close 16.3 and 16.5.

**`docs/the kernel.md`**
- §4: drop `flatten` / `canonical_order` from the eval-loop sketch (they
  are already absent from `eval.py`).
- §6.1: remove the `overlaps`/`implies` block from `define_clause`.
- §6.3: delete.
- §8: remove `Flat`/`Orderless` from the attribute examples.
- §9: restate the short-circuit predicate as `is_err` (§2.5).
- §12: drop `overlaps()`/`implies()` from the `dispatch.py` description.
- §14: close 14.1, 14.2, 14.3; add the nested-`score()` question (§4.2).
- §15: revise the "closed, deterministic dispatch" row.

**`docs/the prelude.md`** — as listed in §4.4.

**`IMPLEMENTATION_PLAN.md`** — the "Explicitly out of scope" list currently
mixes deferrals with what are now removals; split them.

**Code docstrings** — `minimatic/dispatch.py`'s module docstring (§4.1).

### 4.7 Tests

- The existing test asserting declaration-order tie-break "is the current —
  not final — behavior" (`IMPLEMENTATION_PLAN.md` Phase 3 verification)
  should be re-labelled as pinning specified behavior.
- New coverage needed for §2.8: no-`$` first-position equivalence with
  today, each `$` position, `$` at depth, repeated `$`, the nested-pipe
  rule, and `//` parity.
- `Err` propagation tests can only be written once §2.5 is implemented;
  `result.py` was never started.

---

## 5. Risk, and how to walk it back

The load-bearing risk is §2.1. If silent shadowing turns out to hurt in
real use, the recovery path is deliberately cheap and does **not** require
resurrecting `overlaps`/`implies`:

1. ~~Add nested `score()` (§4.2).~~ **Done.** This alone eliminates the
   large majority of real same-score ties, since most accidental overlaps
   differ in nested specificity.
2. Add a **non-fatal lint** at definition time for same-arity,
   same-score clause pairs — a warning, or an error only under an opt-in
   `Kernel(strict=True)`. Because §2.2 *specifies* the tie-break rather
   than leaving it accidental, this can be added later without changing the
   meaning of any existing program.

That two-step path recovers most of the original safety claim at a fraction
of the cost, and is the recommended direction if this proposal's central
trade turns out to have been the wrong one.

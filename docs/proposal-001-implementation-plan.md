# Proposal 001 — Implementation Plan

**Date:** 2026-08-07
**Status:** Complete — all five phases implemented
**Implements:** `docs/proposal-001-dispatch-results-and-pipes.md`
**Precondition:** the proposal is accepted. Nothing here should be built
while §2.1 (removing ambiguity checking) is still under debate, since it is
the decision the rest lean on.

---

## Scope

Of the proposal's eight decisions, four require **no code at all** —
`Hold`/`ReleaseHold` (§2.4), self-hosting (§2.6), and redefinition (§2.7)
are unchanged deferrals or unchanged behavior, and ambiguity removal (§2.1)
is the removal of something never built. What remains is:

| Phase | Work | Behavior change |
|---|---|---|
| A | Remove `Flat`/`Orderless`; correct stale docstrings — **done** | none |
| B | Multi-arg pipe `$` templates (§2.8) — **done** | additive only |
| C | `Value`/`Err` (§2.5) — **done** | new heads + failable prelude heads stop raising |
| D | Design-doc rewrite (§4.6) — **done** | none |
| E | `README.md` + `IMPLEMENTATION_PLAN.md` reconciliation — **done** | none |

Phases A/B/C are independent and can be done in any order or in parallel;
D and E should land last, once the code they describe exists.

**Originally out of scope:** the nested `score()` fix (proposal §4.2), on
the grounds that it changes dispatch outcomes for existing programs, which
nothing else here does. It was nonetheless done — as its own commit
immediately *before* Phase C rather than folded into it, because Phase C
makes error-kind dispatch the primary idiom and that is exactly what the
flat scoring got wrong. The separation the caution asked for was kept; the
sequencing changed.

---

## Phase A — Remove `Flat` / `Orderless`

**Goal:** delete two attributes that nothing consults. Zero behavior change.

Verified: `Flat` and `Orderless` appear only as *definitions* — no
evaluator, dispatch, or matcher code reads them. `is_flat()` /
`is_orderless()` have no callers.

### Files

`minimatic/attributes.py`
- Delete the `Flat` and `Orderless` symbols and their docstrings.
- Delete `is_flat()` and `is_orderless()`.
- Remove both from `STRUCTURAL_ATTRIBUTES` (which then holds
  `OneIdentity` and `Listable`).
- Update the module docstring — it currently advertises
  "Structural transformations (Flat, Orderless)" and shows an
  `Orderless` usage example.

`minimatic/ast/symbol.py:123`
- `__lt__`'s docstring says "Ordering for Orderless attribute". The
  ordering itself is still used for ordinary sorting; only the rationale
  changes. Reword, don't delete the method.

`minimatic/prelude.py:10`
- Module docstring lists `Flat`/`Orderless` among deferred items; they are
  now removed, not deferred.

### Open question for this phase

`OneIdentity` is in the same family — it exists only to make
`Plus[x]` match patterns expecting bare `x`, which is pattern-matching
machinery for the same symbolic layer §2.3 removes. It is unused and
undocumented in every design doc. **Recommend removing it too**, but the
proposal does not authorize it — confirm before deleting, or leave it and
note it as dead.

### Verification

- `uv run pytest` — unchanged, all green (nothing referenced these).
- `grep -rn "Flat\|Orderless" minimatic/` returns nothing.

---

## Phase B — Multi-arg pipe `$` templates

**Goal:** `a |> f($, b)` → `f(a, b)`, with every existing pipe expression
keeping its exact current meaning.

### B1. Lexer — `minimatic/lexer.py`

- Add `DOLLAR = auto()` to `TokenKind`.
- Add `"$": TokenKind.DOLLAR` to the single-character token map (alongside
  `"&": TokenKind.AMP` at line 108).

`$` cannot collide with an identifier: the `IDENT` scanner does not accept
`$`, so this is purely additive.

### B2. Parser — `minimatic/parser.py`

- In `parse_primary`, `DOLLAR` produces `symbol("$")`.

Representing the placeholder as `Symbol("$")` is deliberate: it needs no
new AST node, it travels through the held right-hand side unchanged, and it
is unforgeable as a user identifier.

### B3. Substitution — `minimatic/prelude.py::_impl_pipe` (line 61)

All of the work lands here. `__pipe__` is `HoldRest`, so `rhs_raw` arrives
as an unevaluated tree and `lhs_val` arrives already evaluated — the
"subject evaluated exactly once" guarantee (proposal §2.8 rule 3) is
structural, not something to enforce.

```python
_DOLLAR = Symbol("$")
_PIPE = Symbol("__pipe__")

def _substitute_dollar(node, value):
    """Replace every free `$` with `value`. Returns (new_node, found).

    Does not descend into a nested `__pipe__`'s right-hand side — that `$`
    belongs to the inner pipe (proposal §2.8 rule 4). The inner pipe's
    left-hand side IS substituted.
    """
```

Control flow in `_impl_pipe`, in order:

1. `Lambda` right-hand side → unchanged (apply the closure to `lhs_val`).
2. Otherwise substitute. **Found a `$`** → evaluate the substituted tree.
   **No `$`** → the existing first-position splice, byte-for-byte as today.

### B4. Decisions to pin with tests

- **`$` inside a nested `Lambda` body.** Proposal §2.8 rule 2 says "any
  depth", so `xs |> zip_with(ys, (a, b) -> f(a, b, $))` substitutes. That
  follows the rule as written; confirm it reads correctly before locking it
  in, since it is the one place "any depth" is surprising.
- **`$` in a `Lambda` right-hand side** (`a |> (x -> $ + x)`) is *not*
  substituted — branch 1 wins — and will surface as
  `UnboundSymbolError: $`. Acceptable; assert the error rather than leaving
  it undefined.
- **Pre-existing re-evaluation quirk.** `_impl_pipe` splices an evaluated
  value into a raw tree and calls `ctx.eval` on the result. For
  self-normalizing values (`List`, literals) this is a no-op, but a value
  that is a bare `Symbol` gets looked up a second time. This is *already*
  true of first-position splicing; templates make it reachable in more
  positions. Add a test pinning current behavior and, if it is wrong,
  fix it under its own change — not silently here.

### B5. Tests — `tests/test_prelude.py` (or a new `tests/test_pipe.py`)

- No-`$` forms produce identical results to today (`a |> f`,
  `a |> f(b, c)`, `a |> (x -> ...)`).
- Each placeholder position: `f($, b)`, `f(b, $)`, `f(b, $, c)`.
- Depth: `a |> f(b, g($))`.
- Repetition: `a |> f($, $)` — and assert a side-effecting subject runs
  once.
- Nested pipe: outer `$` binds only the outer subject.
- `//` parity: `a // f($, b)` behaves as `a |> f($, b)`.
- Lexer/parser: `$` tokenizes and parses standalone.

### Verification

```bash
uv run pytest
python -m minimatic examples/tour.md
```

`examples/tour.md` uses only no-`$` pipes, so it must pass unchanged — that
is the regression signal for "additive only."

---

## Phase C — `Value` / `Err`

**Goal:** failable operations return `Err(kind, detail)` instead of raising;
pipelines short-circuit on `Err`.

This is the largest phase and the only one that changes existing behavior.

### C0. The line that has to be drawn first

`Err` is for **expected, routine failure** — division by zero, an empty
list, a parse failure. Kernel exceptions remain for **programming errors** —
`UnknownHeadError`, `UnboundSymbolError`, `NoMatchingClauseError`,
`MinimaticTypeError`, `HeadAlreadySealedError`.

Without this line every mistake becomes a value, silently flows down a
pipeline, and the language loses its ability to tell a user they wrote
something wrong. Write it into the module docstring of `result.py` and into
`docs/the language.md` §12; every per-head decision below follows from it.

### C1. New module — `minimatic/result.py`

```python
ERR = Symbol("Err")

def err(kind: str, detail=None) -> Expression:      # constructor
def is_err_value(value) -> bool:                     # head-is-Err test
```

Deliberately thin: `Err` is an ordinary `Expression`, per proposal §2.5
rule 2. No wrapper class — that would reintroduce exactly the
representation boundary `docs/the kernel.md` §2.1 argues against.

### C2. `ResultAware` — `minimatic/attributes.py`

Add `ResultAware = Symbol("ResultAware")`. It is neither structural nor a
hold attribute; give it its own section, and add it to `ALL_ATTRIBUTES` so
`is_attribute()` recognizes it.

### C3. Pipe short-circuit — `minimatic/prelude.py::_impl_pipe`

After `lhs_val` is in hand and before substitution/splicing:

```
if is_err_value(lhs_val) and not _target_is_result_aware(rhs_raw, ctx):
    return lhs_val          # skip the call entirely
```

Target head resolution (proposal §2.8 rule 6):

| Right-hand side | Target head |
|---|---|
| `Symbol` (`a \|> f`) | that symbol |
| `Expression` with a `Symbol` head | that head |
| `Lambda`, or a template body that is not a call | none → not `ResultAware` → short-circuit |

`ctx.registry.attributes(name)` is already available on `Ctx` via its
`registry` property — no new plumbing.

Do this **before** substitution: a short-circuited pipe must not evaluate
its template arguments.

### C4. Result heads — `minimatic/prelude.py`

All registered with `ResultAware`; all take the result first, so they
compose under the pipe's first-position splice.

| Head | Signature | Notes |
|---|---|---|
| `Err` | `Err(kind, detail)` | self-normalizing, like `_impl_list` |
| `is_err` | `is_err(r)` | |
| `unwrap` | `unwrap(r, default)` | `default` if `Err`, else `r` |
| `unwrap_err` | `unwrap_err(r)` | `MinimaticTypeError` if `r` is not an `Err` — a programming error per C0 |
| `catch` | `catch(r, kind, handler)` | handles one kind, passes others through |
| `recover` | `recover(r, handler)` | handles any `Err` |
| `finally` | `finally(r, f)` | runs `f` for effect, returns `r` |

Handlers are applied with `ctx.apply(handler, [...])` (the mechanism `map`
and `fold` already use), so `pass_ctx=True` on `catch`/`recover`/`finally`.

`finally` is a Python keyword — the *head name* is a string, so
`register_head(registry, "finally", _impl_finally)` is fine; only the Python
function needs a different identifier.

**Not implemented** (proposal §2.5): `Ok`, `is_ok`, `map_ok`, `and_then`.

### C5. Convert failable prelude heads

| Head | Today | After |
|---|---|---|
| `divide` | `a / b` → raw Python `ZeroDivisionError` escapes the kernel | `Err("DivideByZero", ...)` |
| `first` | `MinimaticTypeError("first: empty list")` | `Err("EmptyList", ...)` |
| `rest` | returns `[]` | unchanged — returns `[]` |

Leave raising: `switch`/`which` with no matching case, every
`MinimaticTypeError` type check, and all `_require_list` guards — these are
programming errors under C0.

`divide` is worth calling out: it does not just change error *type* today,
it fixes a genuine hole — a raw `ZeroDivisionError` currently escapes
`MinimaticError` entirely, so host code catching "any Minimatic problem"
misses it.

### C6. `_err` type tag — `minimatic/match.py::check_type`

Add `"err"` alongside the existing `"list"` / `"dict"` / `"expr"` tags, so
`r: _err` works in clause patterns. Needed by anyone writing error handling
in Minimatic rather than calling `catch`.

### C7. Known rough edge — `Err` into a non-pipe call

Per proposal §2.5 rule 4, `plus(Err("X"), 1)` is *not* short-circuited: it
dispatches, reaches `_impl_plus`, and raises a Python `TypeError`. That is
spec-conformant but produces a poor message. Options: leave it (the pipe is
the composition idiom), or add a generic arithmetic guard.
**Recommend leaving it**, with a test pinning the behavior so the choice is
visible rather than accidental.

### C8. Tests — `tests/test_result.py` (new)

- `Err` constructs, matches, and destructures as an ordinary expression.
- Short-circuit: `Err(...) |> f` skips `f` entirely (assert via a
  side-effecting `f`).
- No short-circuit into a `ResultAware` head.
- Each of `is_err`/`unwrap`/`unwrap_err`/`catch`/`recover`/`finally`.
- `catch` passes a non-matching kind through unchanged.
- `divide(1, 0)` and `first([])` return `Err`, and a `MinimaticError`
  subclass no longer escapes as a bare `ZeroDivisionError`.
- `r: _err` matches in a clause pattern.
- A chained pipeline: failure at step one skips steps two and three and
  arrives intact at `recover`.

---

## Phase D — Design docs

**Goal:** the three design docs stop contradicting the kernel. Nothing in
this phase changes behavior; the README currently carries a warning that it
wins where they disagree, and that warning is a pointer to this work, not a
substitute for it.

### D0. What counts as wrong

The docs are wrong in two different ways, and only one gets fixed here.

**Fix — features removed or changed.** Definition-time ambiguity rejection,
`Flat`/`Orderless`, the `Ok` wrapper, `$` as an implicit lambda parameter.
These describe a language that no longer exists.

**Leave — features specified but not yet built.** Indexing (`xs[0]`),
`Attributes(f) := ...`, `Hold`/`ReleaseHold`/`:>`, `Dict`, the string layer,
most of the list layer. These remain the design intent, and these are design
documents: they describe the target language, not the current kernel.

**Two exceptions**, both because the audience differs:

- **`docs/the kernel.md` §2.2 and §10** describe *internal representation
  that contributors build against*, and the code actively diverges. Mark
  these not-yet-implemented rather than leaving them to mislead someone into
  building the wrong thing.
- **`docs/the language.md` §8** — postfix `&` and `$`-as-implicit-parameter
  are struck rather than left standing. `$` is not merely unbuilt, it now
  *means something else* (the pipe placeholder), and `&` would be the third
  orphaned lambda form in one section.

### D1. `docs/the kernel.md`

| § | Edit |
|---|---|
| 1 | "ambiguous clauses rejected as a definition-time error" → proposal §2.1's formulation; "`Ok`/`Err` values" → value-or-`Err` |
| 2.2 | **Mark unbuilt.** Specifies a `Literal` node type and `Expr`/`Node` names; the kernel uses `Symbol`/`Expression` with raw Python atoms (`_ATOMIC_TYPES`, `eval.py:30`) and no `Literal` wrapper |
| 2.3 | drop `Ok` from the normal-form head list |
| 4 | drop `flatten`/`canonical_order` from the eval sketch — already absent from `eval.py` |
| 6.1 | remove the `overlaps`/`implies`/`AmbiguousClauseError` block from `define_clause` |
| 6.2 | the specificity table predates nested scoring; `score()` recurses into compound patterns (`e21bb42`) |
| 6.3 | ambiguity detection — **replace the content**, do not delete the section (see D4) |
| 8 | drop `Flat`/`Orderless` from the attribute examples; add `ResultAware` |
| 9 | retitle off `Ok`/`Err`; §9.2's predicate is `is_err` |
| 10 | **Mark unbuilt.** Persistent RRB-tree/HAMT `List`/`Dict`; `List` is currently an `Expression`, and `IMPLEMENTATION_PLAN.md` records why no `data.py` was built |
| 12 | module layout: drop `overlaps()`/`implies()` and `data.py`; add `errors.py`, `markdown.py`, `prelude.py`, `registry.py`; `result.py` is `Err`, not `Ok`/`Err` |
| 14 | close 14.1 (will not do), 14.2 (moot), 14.3 (sealed). 14.4 stays open |
| 15 | revise the "closed, deterministic dispatch" row |

### D2. `docs/the language.md`

| § | Edit |
|---|---|
| 2 | principle 5: `Ok`/`Err` → value-or-`Err` |
| 7.1 | narrow the claim — order is not load-bearing between *different* scores; exact ties resolve by declaration order |
| 7.2 | "Ambiguity is an error" — rewrite as how ties resolve, per proposal §2.2 |
| 8 | strike postfix `&` and `$`-as-implicit-parameter; `x -> ...` is the only lambda form; note multi-argument lambdas as a known gap |
| 10 | delete the `Flat`/`Orderless` paragraph. Leave `Attributes(MyMacro) := HoldAll` standing per D0 |
| 12 | rewrite every example without `Ok`; the `match` example's `Ok(data)` clause becomes a bare fall-through; state the `Err`-versus-exception boundary (`minimatic/result.py` has the authoritative wording) |
| 13 | specify `$` placeholders — proposal §2.8 |
| 16 | close 16.3 (moot) and 16.5 (answered by `$`) |

### D3. `docs/the prelude.md` — mostly already done

Phase C, the `Head`/`Args` rename and the nested-`score()` commit already
corrected §4, §5, §10, §11, §12, §13 and §14. **Do not redo them.** What
remains:

- §1 and §2.2 — `Ok`/`Err` in the summary and in the `ResultAware` rule.
- §2.5 — the `is_ok`/`is_err` naming exception; `is_ok` no longer exists.
- §3 — drop `Flat`/`Orderless` from `plus`, `times`, `min`/`max`.
- §5 — `concat`'s `Flat`; `find` returning `Ok(x)` → the element or
  `Err("NotFound", _)`.
- §6 — `merge`'s `Flat`; `key_get` returning `Ok(v)`.
- §7 — `to_int`/`to_float` described as "`Ok`/`Err`-returning".

### D4. Section numbering, and a deliberate deviation from the proposal

Proposal §4.6 says to **delete** `docs/the kernel.md` §6.3. This plan says
to **replace its content** with a short "why there is no ambiguity check"
and keep the heading.

Checked before recommending it: nothing outside this plan currently
references kernel §6.4, so deleting §6.3 would not break a live
cross-reference today. The reason to keep the heading anyway is cheapness of
future auditing — the four docs already carry ~25 cross-references by
section number (`§10`, `§7.2`, `§6.1`, `§14.4`, `§11.1`, …), and every
deletion turns the next edit into a renumbering audit. Keeping headings
stable costs one sentence; removing them costs a sweep each time.

Note also that `docs/the language.md:286` references `§6.3` — its *own*
§6.3, not the kernel's. Do not "fix" it.

### Verification

- Grep sweep across all three docs for `Ok(`, `` `Ok` ``, `Flat`,
  `Orderless`, `overlaps`, `implies`, `AmbiguousClauseError`. Every
  surviving hit must sit in a sentence deliberately marking the thing as
  removed.
- Cross-reference sweep: every `§N` reference between the four docs still
  points at the section it names.
- Spot-run the snippets that describe *current* behavior — the docs use
  untagged fences so nothing executes them, which is exactly why they
  drifted. `docs/the prelude.md` §13's `fold` is the precedent: it was
  wrong for months and one character from working.
- `uv run pytest` and `examples/tour.md` are unaffected — no code changes —
  but run them to confirm that stays true.

---

## Phase E — README and plan reconciliation

**`README.md`** — per proposal §4.6: design-goal bullets on ambiguity and
on `Ok`/`Err`; the status table (drop the ambiguity row, restate
`Flat`/`Orderless` as removed, restate `Ok`/`Err`); the "MVP dispatch note"
blockquote, which currently calls the tie-break "a temporary gap, not a
supported feature" — §2.2 reverses that; line 10's overclaim of the rewrite
machinery. Also fix the broken
`docs/learn_minimatic_in_15_minutes.md` link (the file is in `scratch/`).

**`IMPLEMENTATION_PLAN.md`** — its "Explicitly out of scope" list now mixes
deferrals with removals; split them and point at this proposal.

**Docstrings that are now wrong:**
- `minimatic/dispatch.py` module docstring — says same-score resolution is
  "a placeholder" callers "should not treat as a stable, guaranteed
  feature." Under §2.2 it is the specification.
- `minimatic/errors.py` — the `AmbiguousClauseError` note says the MVP
  "does not detect clause ambiguity *yet*"; it never will.

**Test rename:** `tests/test_dispatch.py:25`,
`test_mvp_gap_overlapping_equal_specificity_resolves_by_order` — drop
`mvp_gap` and rewrite the docstring; it now pins specified behavior, not a
known gap.

---

## Verification

Per phase, plus at the end:

```bash
uv run pytest
```

```bash
python -m minimatic examples/tour.md
```

Both README flagship examples must still run — they are the standing
acceptance bar from `IMPLEMENTATION_PLAN.md` and neither uses `$` or `Err`,
so both must be untouched by all of this:

```bash
python -m minimatic
```

```
double(x: _int) := 2 * x
double(21)
[1, "N/A", 3, "N/A", 5] |> map(x -> x /. "N/A" -> 0) |> fold(plus, 0)
```

Expected: `42`, then `9`.

Manual end-to-end check for the two new features:

```
[1, 2, 3] |> fold(plus, 0)          (* 6  — no $, unchanged *)
2 |> minus(10, $)                    (* 8  — template position *)
divide(1, 0) |> plus(5)              (* Err("DivideByZero", _) — skipped plus *)
divide(1, 0) |> recover(e -> 0)      (* 0  — ResultAware, not skipped *)
```

---

## Risks

- **Phase C is the only one that can break existing programs.** Anything
  relying on `first([])` raising now gets a value back. The blast radius is
  small today (nothing in `examples/` or the test suite depends on it), but
  it grows with every week this is delayed.
- **Phase B's re-evaluation quirk (B4)** is pre-existing and easy to
  mistake for a regression introduced by templates. Pin it with a test
  first, so the distinction stays visible.
- **Phase D/E are large but mechanical**, and they are what makes the
  proposal real — the docs currently promise ambiguity detection,
  `Flat`/`Orderless`, and `Ok`. Shipping the code without them leaves the
  project's most-read surface describing a language that no longer exists.

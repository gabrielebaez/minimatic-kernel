# Minimatic — Capabilities and Roadmap

**Date:** 2026-08-14
**Status:** Assessment of the kernel at `676eb20`, after proposal 001's
code phases
**Scope:** what the language does today, what it could do once the missing
heads exist, and what would still be missing after that

Every claim here was produced by running the kernel, not by reading the
design docs. Where the two disagree, this document describes the kernel.

---

## 1. Why this document

The design docs describe the language as intended; `IMPLEMENTATION_PLAN.md`
describes the MVP as shipped; proposal 001 describes a set of corrections.
None of them answers the practical question — *what can you actually write
in Minimatic right now, and what stops you.*

The distinction that organises everything below: **a missing head is an
afternoon's work; a missing core capability is a language change.** Most of
what Minimatic lacks is the former. What it lacks in the latter is small,
specific, and mostly invisible in the docs because the docs describe it as
already working.

---

## 2. What works today

44 registered heads:

```
Args CompoundExpression Err Head Lambda List Range ReplaceAll Rule Set
SetDelayed __pipe__ append catch divide each equal finally first fold for
greater greater_eq if is_err length less less_eq map minus mod negate not
not_equal plus power print recover rest switch times unwrap unwrap_err which
```

Working and covered by 189 tests:

- **Evaluation** — strict, single-pass, `head(args)` all the way down. No
  special forms: `if`/`switch`/`which`/`for`/`each`/`;` are ordinary heads
  that skip branches via their own hold attributes.
- **Dispatch** — specificity-scored, most-specific-first, recursing into
  nested compound patterns. Declaration order breaks only exact ties.
- **Patterns** — blanks, typed blanks (`_int`, `_list`, `_err`, …),
  sequence blanks, named binds, compound patterns whose head is pinned
  literally.
- **Functions** — closures, currying, higher-order use, recursion, mutual
  recursion.
- **Pipes** — `|>` and `//`, with `$` placeholders for argument position;
  `/@` for map.
- **Rewriting** — `/.` over evaluated data, with single rules or rule lists.
- **Errors as values** — `Err(kind, detail)`, pipe short-circuiting,
  `catch`/`recover`/`finally`/`unwrap`/`unwrap_err`/`is_err`. No `Ok`
  wrapper.
- **Structure inspection** — `Head`, `Args`, total over every value.
- **Host integration** — `register_head`, and Markdown files as runnable
  scripts.

### 2.1 Self-hosting is real

The strongest evidence that the core is sufficient: the derived list layer
can be written *in Minimatic*. These run today.

```
myfold(f: _, i: _, [])              := i
myfold(f: _, i: _, [x: _, r: ___])  := myfold(f, f(i, x), r)

prepend(xs: _list, x: _)            := fold(xs, append, [x])

myfilter(p: _, [])                  := []
myfilter(p: _, [x: _, r: ___])      := if(p(x), prepend(myfilter(p, r), x),
                                             myfilter(p, r))
```

`fold`, `filter`, `take`, `reverse`, `length` and `prepend` all work from
clause dispatch, specificity and sequence patterns alone — the bar
`docs/the prelude.md` §13 sets for whether the core is enough for real list
work. It clears it, subject to §3.2 below.

---

## 3. The core's ceiling

These are the limits that filling in heads will not touch.

### 3.1 Anonymous multi-argument lambdas do not exist

`(a, b) -> a + b` is a `MinimaticSyntaxError`. A *named* two-argument head
works fine as a callback:

```
combine(a: _, b: _) := a * 10 + b
fold([1, 2, 3], combine, 0)          (* 123 *)
```

So the gap is specifically lambda syntax. It affects every callback that
takes two arguments — `fold`, `zip_with`, `sort_by` comparators, `catch`
handlers that want kind and detail separately. This is the largest
expressive limit in the language and among the smallest to fix.

### 3.2 Self-hosted recursion caps out around 200–300 elements

Python's recursion limit is 1000 and there is no tail-call elimination.
Measured with the self-hosted `myfold` above:

| input | result |
|---|---|
| 200 elements | works |
| 400 elements | `RecursionError` |
| builtin `fold`, 2000 elements | works |

So §2.1's self-hosting is genuine but capped at small inputs; anything
sizeable still has to be a Python head. This bounds how much of the Prelude
can honestly move into Minimatic.

`RecursionError` also **escapes `MinimaticError`** — a fourth escaping
class beyond the three proposal 001 Phase C closed. Host code catching "any
Minimatic problem" still misses runaway recursion.

### 3.3 `Attributes(f) := HoldAll` silently does nothing

It looks like it works. It does not. `Attributes` is not a registered head,
so the statement simply defines *a clause named `Attributes`* and sets no
attribute — verified: the head goes on evaluating its arguments, and
`registry.attributes(f)` stays empty.

`docs/the language.md` §10 presents this as *the* way to declare hold
behavior, and states there is "exactly one hold mechanism" available
"identically to user-defined functions and to Python-registered heads".
Today hold attributes are Python-side only: **a Minimatic-level user cannot
write a macro at all.** Failing quietly makes this the worst of the gaps.

### 3.4 No `Hold`, so `/.` only ever sees evaluated data

The design docs' symbolic examples cannot run:

```
[f(1), g(2)] /. f(x: _) -> x + 10
```

`f(1)` evaluates before the rule is applied, so the rule never meets the
shape it was written for. The README's "powerful enough to feel like a
symbolic language" is, at present, about rewriting *data* — which the
flagship `"N/A" -> 0` example does well, and which is a different claim.

### 3.5 Smaller core gaps

- **Indexing is unimplemented.** `xs[0]` is a syntax error, though
  `docs/the language.md` §6.1 advertises `myList[0]` and `myList[1] <- 5`.
- **Sequence blanks only work in final position.** `f(a: __, z: _)` never
  matches — a documented simplification in `match.py`.
- **No literal-symbol patterns.** A bare symbol in a pattern always binds,
  which is what blocked symbol-valued `Err` kinds.

---

## 4. Assuming every missing head lands

The head-level gaps are large in volume but ordinary in nature: `Dict` (the
literal already parses), the entire string layer, most of the list layer
(`filter`, `sort`, `zip`, `unique`, `group_by`, `find`, `concat`, `take`,
`drop`, …), the meta heads (`MatchQ`, `match`, `Cases`, type predicates),
`and`/`or`/`xor`, the numeric helpers, I/O, and the functional combinators.

**With those in place, Minimatic is a competent strict functional
expression language.** Enough for business rules, validation, config and
DSL evaluation, data transformation over modest collections, and wiring
host Python algorithms together — which is precisely the "knowledge and
computation workbench" the language positions itself as.

**What it still could not do**, because these are §3 and not heads:

| Cannot | Blocked by |
|---|---|
| Write a two-argument callback without naming it | §3.1 |
| Process more than a few hundred elements in Minimatic-level code | §3.2 |
| Define a macro, or any head that sees unevaluated arguments | §3.3 |
| Manipulate expressions symbolically | §3.4 |
| Index a list | §3.5 |

Put plainly: **the Prelude is what stands between Minimatic and being
useful; the §3 gaps are what stand between it and being what its own
documentation already describes.**

---

## 5. Recommended order

1. **Multi-argument lambdas** (§3.1). Smallest change, largest unlock. Do
   it first — otherwise every derived head taking a callback in step 3 gets
   designed around the limitation, and re-designed afterwards.

2. **`Attributes` as a real head** (§3.3). Makes language doc §10 true,
   enables user-level macros, and removes a statement that currently fails
   silently. Small, and it stops the docs lying about a core guarantee.

3. **Prelude build-out.** `Dict`, strings, the rest of the list layer, type
   predicates, `MatchQ`/`match`/`Cases`, `and`/`or`. The largest volume of
   work and the most user-visible value, unblocked by (1). Much of it can
   be written in Minimatic per §2.1, within the §3.2 size limit.

4. **`Hold` / `ReleaseHold` / `:>`** (§3.4). The symbolic layer. Its open
   questions — `docs/the kernel.md` §14.4 (error identity through `Hold`)
   and `docs/the language.md` §16.4 (scoping of held free variables) — have
   been deferred four times and need settling before implementation.

5. **Recursion depth** (§3.2). At minimum convert `RecursionError` into a
   `MinimaticError` so it stops escaping; properly, trampoline self-calls
   so self-hosted list code scales.

Independently: **Phase D of proposal 001** — reconciling
`docs/the language.md`, `docs/the kernel.md` and `docs/the prelude.md` with
what shipped — remains outstanding. Several gaps above are only visible
*as* gaps because those documents describe them as working.

---

## 6. Reproducing this

```bash
uv run pytest                              # 189 passing
uv run python -m minimatic examples/tour.md
```

Each claim in §2 and §3 was checked by direct `Kernel.eval` probes. The
three worth re-running before trusting this document again:

- the self-hosted `fold`/`filter` definitions in §2.1;
- the 200-versus-400 element recursion boundary in §3.2;
- `Attributes(f) := HoldAll` leaving `registry.attributes(f)` empty (§3.3).

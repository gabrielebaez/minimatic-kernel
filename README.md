# minimatic-kernel

> ⚠️ **Work in progress.** The language, syntax, and APIs described below are
> under active design and subject to breaking changes without notice. Nothing
> here is stable enough to build on yet. There is no versioned release.

`minimatic-kernel` is the interpreter for **Minimatic**, a small, embeddable
expression language for Python applications. This repository contains the
core language implementation: the parser, evaluator, pattern-matching and
clause-dispatch engine, `/.` rewriting over data, and the Python extension
API (`register_head`). Held *code* — `Hold`/`ReleaseHold` and delayed rules
— is designed but deferred; see [Status](#status).

## What is Minimatic

Minimatic is built around one idea: everything is an expression —
`head(args)`, all the way down. There are no statements, no special forms,
and no hidden control structures. Arithmetic, conditionals, and control flow
are all just function application in disguise.

```
double(x: _int) := 2 * x
double(21)                       (* 42 *)

[1, "N/A", 3, "N/A", 5]
|> map(x -> x /. "N/A" -> 0)
|> fold(plus, 0)                 (* 9 *)
```

The pipe threads a value through a chain of calls. By default the subject
lands in the first argument position; `$` puts it wherever you want it
instead:

```
[1, 2, 3] |> fold(plus, 0)        (* 6 — the subject goes first *)
2 |> minus(10, $)                 (* 8 — $ marks the subject's slot *)
```

On top of that small core sits pattern matching and rule-based rewriting
powerful enough to feel like a symbolic language when you want it to — and
out of the way, running at ordinary function-call speed, when you don't.

For a full language tour, run [`examples/tour.md`](examples/tour.md) —
a Markdown document that's also a runnable demo of most of what's
implemented (specificity dispatch, recursion via literal clauses, sequence
blanks, `Listable` threading, `/.` rewriting, closures, `|>`, and control
flow — `if`/`switch`/`which`/`for`/`each`/`;`):

```bash
python -m minimatic examples/tour.md
```

## Design goals

- **Strict, deterministic evaluation.** Calling a function has exactly one
  obviously-correct outcome. Clause dispatch is resolved from a closed,
  fixed set of clauses — there is no global, mutable rule table consulted at
  runtime.
- **Specificity-based clause dispatch.** Function clauses are matched by how
  specific their patterns are (`5` beats `_int`, which beats `_`), not by
  declaration order. Dispatch order is a pure function of the clause set,
  fixed once at definition time by a published static rule — never dependent
  on runtime state, call history, or a global mutable rule table.
- **Immutable data, always.** Lists, dicts, and every "update" operation
  return new values.
- **Explicit, opt-in rewriting.** `Hold` / rewrite rules / `ReleaseHold` are
  a construct you reach for on purpose. Nothing rewrites expressions behind
  an ordinary function call.
- **Errors are values.** Failable operations return their ordinary result on
  success, or an `Err` — there is no `Ok` wrapper — composed through `|>`,
  `catch`, `recover`, and `finally` instead of exceptions. Programming
  mistakes stay exceptions, so a typo never becomes a value drifting down a
  pipeline.
- **Trivially extensible from Python.** Any Python function can be
  registered as a new head, with its own evaluation and holding behavior,
  becoming a first-class part of the language rather than a bolted-on FFI
  call.

These goals exist in tension with each other by design. Resolving that
tension is most of the work: how it was resolved for dispatch, results, and
pipes is recorded in
[proposal 001](docs/proposal-001-dispatch-results-and-pipes.md), whose
code phases have all landed. What remains is reconciling the three design
docs with it (Phase D).

## Status

This kernel is pre-alpha. The MVP milestone (see `IMPLEMENTATION_PLAN.md`)
is implemented and passing, as are all the code phases of
[proposal 001](docs/proposal-001-dispatch-results-and-pipes.md): every
example in "What is Minimatic" above runs correctly through
`python -m minimatic`, and the suite is green.

Statuses below mean exactly one of four things:

- **working** — implemented and covered by tests
- **decided — not built** — semantics are settled, no code yet
- **deferred** — deliberately postponed, semantics still open
- **removed** — decided *against*; it is not coming

| Component | Status |
|---|---|
| Parser / core `head(args)` evaluation | working |
| Specificity-scored clause dispatch (`score()`, most-specific-first) | working — see dispatch note below |
| Blank / typed pattern matching (`_`, `_int`, `__`, `___`) | working |
| Pipe `\|>` / `//`, including `$` placeholders | working |
| `/.` rewriting over evaluated data | working |
| Hold attributes (`HoldAll`/`HoldFirst`/`HoldRest`) and `Listable` | working |
| Control flow (`if`, `switch`, `which`, `for`, `each`, `;`) | working — ordinary heads, no special-form syntax |
| Python extension API (`register_head`) | working, signature simplified — see below |
| Value-or-`Err` results (`catch`, `recover`, `finally`) | working — no `Ok` wrapper ([§2.5](docs/proposal-001-dispatch-results-and-pipes.md)) |
| Structure inspection (`Head`, `Args`) | working |
| `not` / `!` | working; `and`/`or` not yet |
| `Hold` / `ReleaseHold` / delayed rules (`:>`) | deferred |
| Ambiguity detection at definition time (`overlaps`/`implies`) | **removed** ([§2.1](docs/proposal-001-dispatch-results-and-pipes.md)) |
| `Flat` / `Orderless` attributes | **removed** ([§2.3](docs/proposal-001-dispatch-results-and-pipes.md)) |
| Performance / benchmarking | not started |

> **Dispatch note.** Clauses are ordered by `score()` — literal > typed
> blank > blank > sequence blank, compared lexicographically per argument —
> and **same-score clauses are tried in declaration order**, first
> structural match winning. That is the specification, not a placeholder.
>
> Two consequences worth knowing before you rely on it:
>
> - Declaration order *is* semantic for same-score clauses. Reordering two
>   of them changes behavior. (Clauses with different scores are unaffected:
>   `describe(_int)` / `describe(_string)` / `describe(_)` behave the same
>   no matter how they are written.)
> - Specificity is compared at every depth. `f(Err("IOError", d: _))` beats
>   `f(Err(k: _, d: _))` however they are ordered, because `score()`
>   recurses into compound patterns. Only clauses that are equally specific
>   *all the way down* fall through to declaration order.
>
> Earlier drafts promised that overlapping same-specificity clauses would be
> *rejected* at definition time. That check was removed rather than
> deferred, and the reasoning is in §2.1.

Expect gaps between what's documented and what's implemented. If something
in the docs doesn't work yet, that's expected at this stage, not a bug
report you need to file — but issues are still welcome if you want to help
prioritize.

## Design documents

- [`docs/the language.md`](docs/the%20language.md) — the language itself:
  syntax, semantics, rationale
- [`docs/the kernel.md`](docs/the%20kernel.md) — the tree-walking
  interpreter's architecture
- [`docs/the prelude.md`](docs/the%20prelude.md) — the standard collection
  of heads
- [`docs/proposal-001-dispatch-results-and-pipes.md`](docs/proposal-001-dispatch-results-and-pipes.md)
  — accepted; the current decision record for dispatch, results, and pipes,
  plus its [implementation plan](docs/proposal-001-implementation-plan.md)
- [`docs/capabilities-and-roadmap.md`](docs/capabilities-and-roadmap.md) —
  what the kernel actually does today, measured by running it, and what
  comes next. Start here if you want the current picture rather than the
  intended one
- [`docs/learn_minimatic_in_15_minutes.md`](docs/learn_minimatic_in_15_minutes.md)
  — a narrative walkthrough of the language. Illustrative only: its code is
  in an untagged fence, so unlike [`examples/tour.md`](examples/tour.md) it
  is never executed and never tested

> These four documents **predate proposal 001** and still present ambiguity
> detection, `Flat`/`Orderless`, `Hold`/`ReleaseHold`/`:>`, and `Ok`/`Err`
> as current — the first two were removed, the third is deferred, and the
> fourth became value-or-`Err`. Where they and this README disagree, the
> README and the proposal are right. Reconciling them is Phase D of the
> implementation plan.

## Repository scope

This repo owns the interpreter and nothing above it:

- Lexing and parsing of Minimatic source
- The evaluator and clause-dispatch engine
- Pattern matching (`MatchQ`, blanks, destructuring)
- The rewrite-rule engine (`Hold`, `ReleaseHold`, `/.`, `Rule`/`RuleDelayed`)
- The `Attributes` system
- The `Err` result type and pipeline combinators
- The Python-facing extension API (`register_head`)
- A minimal reference REPL for local testing (no notebook, no persistence)

## Installation

```bash
# not yet published — clone and install locally
git clone https://github.com/gabrielebaez/minimatic-kernel.git
cd minimatic-kernel
pip install -e .
```

There is no PyPI package yet. APIs will keep moving until the core dispatch
and rewrite semantics stabilize.

## Basic usage

```python
from minimatic import Kernel

kernel = Kernel()
kernel.eval("double(x: _int) := 2 * x")
kernel.eval("double(21)")  # 42
```

## Minimatic is also just a Markdown file

A Minimatic script can be a Markdown document: fence the runnable parts as
` ```minimatic ` (or ` ```mmt `) and everything else — headings, prose,
other languages' code blocks — is ignored, the same way a comment would
be. Each block runs against the same kernel, in document order, so a
later block sees whatever an earlier one defined:

````markdown
# My little script

```minimatic
double(x: _int) := 2 * x
```

Some prose in between blocks.

```minimatic
double(21)   (* 42 *)
```
````

Run it from the CLI (`python -m minimatic path/to/file.md`), or from
Python:

```python
from minimatic import Kernel

kernel = Kernel()
results = kernel.eval_file("path/to/file.md")   # list of every statement's result, in order
```

Passing any other extension to `eval_file` (or the CLI) runs the file as
plain Minimatic source instead — no block boundaries, just a script.
Bare (untagged) fences are never picked up; the tag is what makes a block
runnable rather than illustrative prose, matching the existing design docs
(which use untagged fences for examples, on purpose — they aren't scripts).

## Extending Minimatic from Python

Registering a builtin is a single call: give it a name, an implementation,
and — if it needs to see unevaluated code rather than computed values — a
hold attribute.

```python
from minimatic import Kernel, register_head

kernel = Kernel()
register_head(kernel, "http_get", python_http_get)
register_head(kernel, "my_macro", python_macro_impl, attributes=["HoldAll"])
```

There is no serialization boundary and no separate DSL-for-the-DSL: the
Python function you write becomes the head Minimatic scripts call.

(MVP note: `register_head` takes the `Kernel` explicitly rather than acting
on an implicit global instance, so multiple kernels stay fully independent
— no hidden global state. `kernel.register_head(name, fn, ...)` works the
same way as a method, if you prefer that spelling.)

## Contributing

This project is in a fast-moving, pre-design-freeze state. Before opening a
PR for anything beyond a small fix, please open an issue or discussion
first — core semantics are still being decided and are likely to change
under you. [Proposal 001](docs/proposal-001-dispatch-results-and-pipes.md)
is the current decision record and the best place to see what has been
settled versus what is still open; its Phase C (making failure a value) is
the live work.

## License

MIT

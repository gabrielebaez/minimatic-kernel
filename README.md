# minimatic-kernel

> ⚠️ **Work in progress.** The language, syntax, and APIs described below are
> under active design and subject to breaking changes without notice. Nothing
> here is stable enough to build on yet. There is no versioned release.

`minimatic-kernel` is the interpreter for **Minimatic**, a small, embeddable
expression language for Python applications. This repository contains the
core language implementation: the parser, evaluator, pattern-matching
and clause-dispatch engine, the rewrite-rule (`Hold`/`/.`/`ReleaseHold`)
machinery, and the Python extension API (`register_head`).

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

On top of that small core sits pattern matching and rule-based rewriting
powerful enough to feel like a symbolic language when you want it to — and
out of the way, running at ordinary function-call speed, when you don't.

See [`docs/learn_minimatic_in_15_minutes.md`](docs/learn_minimatic_in_15_minutes.md)
for a full language tour, or run [`examples/tour.md`](examples/tour.md) —
a Markdown document that's also a runnable demo of everything implemented
so far (specificity dispatch, recursion via literal clauses, sequence
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
  declaration order. Ambiguous, overlapping clauses are caught as an error at
  definition time.
- **Immutable data, always.** Lists, dicts, and every "update" operation
  return new values.
- **Explicit, opt-in rewriting.** `Hold` / rewrite rules / `ReleaseHold` are
  a construct you reach for on purpose. Nothing rewrites expressions behind
  an ordinary function call.
- **Errors are values.** Failable operations return `Ok`/`Err`, composed
  through `|>`, `catch`, `recover`, and `finally` instead of exceptions.
- **Trivially extensible from Python.** Any Python function can be
  registered as a new head, with its own evaluation and holding behavior,
  becoming a first-class part of the language rather than a bolted-on FFI
  call.

These goals exist in tension with each other by design, and getting that
tension right — especially specificity resolution and ambiguity detection —
is most of the current work.

## Status

This kernel is pre-alpha, but the MVP milestone (see `IMPLEMENTATION_PLAN.md`)
is implemented and passing: both examples in "What is Minimatic" above run
correctly through `python -m minimatic`. Roughly, in order of maturity:

| Component | Status |
|---|---|
| Parser / core `head(args)` evaluation | working (MVP) |
| Specificity-scored clause dispatch (`score()`, most-specific-first) | working (MVP), see ambiguity note below |
| Ambiguity detection at definition time (`overlaps`/`implies`) | **not implemented — see note below** |
| Blank / typed pattern matching (`_`, `_int`, `__`, `___`) | working (MVP) |
| `Hold` / `ReleaseHold` / rewrite rules (`->`, `:>`, `/.`) | `/.` over evaluated data only; `Hold`/`ReleaseHold`/`:>` design stage |
| `Attributes` (`Flat`, `Orderless`, `HoldAll`, `Listable`, ...) | `HoldAll`/`HoldFirst`/`HoldRest`/`Listable` working (MVP); `Flat`/`Orderless` design stage |
| `Ok`/`Err` result pipelines (`catch`, `recover`, `finally`) | design stage |
| Control flow (`if`, `switch`, `which`, `for`, `each`, `;`) | working (MVP) — ordinary heads, no special-form syntax |
| Python extension API (`register_head`) | working (MVP), signature simplified — see below |
| Performance / benchmarking | not started |

> **MVP dispatch note:** clauses are currently ordered by `score()`
> (literal > typed blank > blank > sequence blank), same as the target
> design. What's *not* yet implemented is rejecting genuinely ambiguous,
> same-specificity, overlapping clauses at definition time — for now, ties
> resolve by declaration order (first-defined wins), which is exactly the
> footgun this project's design intends to eliminate (see "Design goals"
> above). Don't rely on that fallback; it's a temporary gap, not a
> supported feature, and will become a hard error once ambiguity detection
> lands. See `IMPLEMENTATION_PLAN.md` for the full MVP scope.

Expect gaps between what's documented and what's implemented. If something
in the docs doesn't work yet, that's expected at this stage, not a bug
report you need to file — but issues are still welcome if you want to help
prioritize.

## Repository scope

This repo owns:

- Lexing and parsing of Minimatic source
- The evaluator and clause-dispatch engine
- Pattern matching (`MatchQ`, blanks, destructuring)
- The rewrite-rule engine (`Hold`, `ReleaseHold`, `/.`, `Rule`/`RuleDelayed`)
- The `Attributes` system
- The `Ok`/`Err` result type and pipeline combinators
- The Python-facing extension API (`register_head`)
- A minimal reference REPL for local testing (no notebook, no persistence)

This repo does **not** own:

- The web editor, rich-text/MD authoring, or embedded media
- Orthogonal persistence of external symbols/expressions across sessions
- Any server, auth, or multi-user concerns

Those live in `minimatic-workbench`, which depends on this repo as its
interpreter.

## Installation

```bash
# not yet published — clone and install locally
git clone https://github.com/<org>/minimatic-kernel.git
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
first — core semantics (especially around clause specificity and
ambiguity rules) are still being decided and are likely to change under
you.

## License

MIT
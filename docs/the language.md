# The Minimatic Language — Design Document

**Status:** Draft / work in progress — semantics described here are subject
to change as `minimatic-kernel` is implemented and tested against them.
**Scope:** the language itself — syntax, semantics, and rationale.
Implementation strategy is covered separately in
`tree-walker-design.md`; the notebook/persistence layer is covered by
`minimatic-workbench`'s own documentation.

---

## 1. Motivation

**A small, strict, deterministic language for expressions and rules** — safe enough to expose
to end users, structured enough to write real business logic,
transformation pipelines, and rule engines in, and extended trivially from
the Python host application it lives inside.

It is designed first as a **knowledge and computation workbench**: a
language for exploring ideas, expressing domain rules, and wiring together
powerful algorithms (most of them living in the host application, as
registered Python heads) — not as a general-purpose programming language
competing with Python itself.

## 2. Design principles

These are the commitments the rest of this document exists to make
precise. Where a principle creates tension with another (and several do),
the resolution is stated explicitly rather than left implicit.

1. **Everything is an expression.** There are no statements. `head(args)`
   is the only syntactic form that matters; arithmetic, conditionals, and
   sequencing are all instances of it.
2. **Evaluation is strict and deterministic.** A function call has exactly
   one correct outcome, knowable from the call site and the function's
   closed clause set — never from runtime, order-dependent global state.
3. **Data is immutable.** No operation mutates a value in place. "Updating"
   something always produces a new value.
4. **Rewriting is explicit.** Treating code as data (`Hold`, pattern
   rewriting) is a deliberate, opt-in language construct — never something
   that happens invisibly behind an ordinary function call.
5. **Failure is a value, not a control-flow event.** Operations that can
   fail return their ordinary result, or an `Err`; failure is composed
   through pipelines, not thrown and caught.
6. **The host language is not a separate tier.** A Python function
   registered with the runtime becomes a real head — subject to the same
   pattern dispatch, attributes, and specificity rules as anything written
   in Minimatic itself.

## 3. Lexical structure and comments

```
(* This is a comment. Comments nest in principle, though this
   is not yet finalized. *)
```

Identifiers, numeric literals, and string literals follow conventional
rules and are not elaborated here; they're not a source of design tension.

## 4. Everything is `head(args)`

There is no arithmetic operator that is not sugar for a function call, and
no control-flow keyword that is not sugar for one either.

```
1 + 3            (* sugar for plus(1, 3)   *)
2 * 5            (* sugar for times(2, 5)  *)
2 ^ 3            (* sugar for power(2, 3)  *)

if(x == 8, print("Yes"), print("No"))
switch(x, 2, print("Two"), 8, print("Yes"))
for(0..5, y -> print(y))
```

`if`, `switch`, `for`, and `each` are ordinary functions — arguments to
`if` are not specially deferred; conditionals branch by which argument
expressions get evaluated, following each function's own hold behavior
(§9) rather than a hard-coded special form in the grammar. There is no
control-flow construct in Minimatic that a `register_head`-registered
Python function couldn't, in principle, also define.

**Rationale:** this is the single idea Minimatic is "built around," per its
own description, and it's what makes the rest of the design possible —
patterns, dispatch, and rewriting can all be defined uniformly over
`head(args)` because there is nothing else in the language for them to
special-case around.

## 5. Bindings

```
x = 5
x = x + 5        (* rebinding a name to a new value, not mutating the old one *)
set(x, 20)        (* explicit function form of = *)
```

`=` binds a name in the current scope to a value. It is **not** assignment
to a mutable cell — rebinding `x` does not affect any value already
captured by a closure, held expression, or another binding that previously
read `x`. This follows directly from principle 3 (immutable data):
if data itself is always immutable, then a "variable" can only ever be a
name-to-value association that can be replaced, not a container that can
be written into.

## 6. Data

### 6.1 Lists and dicts

```
myList = [1, 2, 3, 4]
myList[0]                     (* 1 *)
myList[1] <- 5                 (* [1, 5, 3, 4] -- a new list *)
myList                         (* [1, 2, 3, 4] -- original untouched *)

myHash = { "Green" -> 2, "Orange" -> 1 }
myHash["Green"]
myHash |> key_drop("Green") |> set("Blue", 10)
```

Every operation that looks like an update — index assignment, `append`,
`key_drop` — returns a new list or dict. This is a language-level
guarantee, not an implementation detail: code can rely on the fact that
holding a reference to `myList` means holding a reference to *that*
list, permanently, regardless of what else happens to variables that
were once bound to it.

### 6.2 Ranges

```
0..5      (* [0, 1, 2, 3, 4] *)
```

### 6.3 What counts as "data" vs "code"

There is no separate data literal syntax distinct from expression syntax —
a list literal `[1, 2, 3]` is `List(1, 2, 3)`, using the same `head(args)`
form as any function call. This matters for rewriting (§10): a plain,
already-evaluated list can be pattern-rewritten with the exact same
mechanism used for held code, because structurally there is no difference
between them once written down.

## 7. Functions are closed, pattern-matched clause sets

This is the most consequential departure from the language's own closest
relative (Wolfram Language), so it's stated as its own principle:

> **A function is a fixed, closed set of clauses, resolved once when the
> last clause is defined — not an open-ended, priority-ordered global rule
> table that can be silently extended, shadowed, or reordered at runtime.**

```
describe(x: _int)    := "an integer"
describe(x: _string) := "a string"
describe(x: _)        := "something else"

describe(5)       (* "an integer" *)
describe("hi")    (* "a string" *)
```

### 7.1 Dispatch is by specificity, not declaration order

Clauses are tried most-specific-first: a literal pattern beats a typed
blank, which beats a bare blank, regardless of the order the clauses were
written in. Reordering the three clauses above does not change
`describe`'s behavior, because their specificities differ.

Specificity is compared at **every depth**, so a compound pattern is ranked
by its arguments too: `Err("IOError", d: _)` beats `Err(k: _, d: _)`
wherever each is written. Only clauses that are equally specific all the way
down fall through to declaration order — see §7.2.

**Rationale:** declaration-order dispatch (as in Erlang/Elixir's
first-matching-clause semantics) means a function's behavior can change
depending on the textual order clauses happen to appear in — harmless in a
small function, a real source of confusion once a clause set grows or is
authored by more than one person. Specificity ordering removes order as a
variable wherever the clauses differ in specificity at all.

### 7.2 Exact ties resolve by declaration order

If two clauses are equally specific *and* their domains overlap, the
first-defined one wins. This is the specification, not a gap.

An earlier version of this section promised the opposite: that such a pair
would be **rejected as an error** when the second clause was defined. That
check was removed from the language — see
`docs/proposal-001-dispatch-results-and-pipes.md` §2.1 for the full
reasoning. In short, deciding whether two patterns really overlap is
undecidable in practice over the grammar Minimatic actually has, and a
conservative approximation rejects legitimate clause sets, which is worse
than the problem it solves.

What the language guarantees instead:

> Dispatch order is a pure function of the clause set, fixed once at
> definition time by a published static rule — descending specificity, then
> declaration order. It never depends on runtime state, call history, or a
> global mutable rule table.

That is a smaller claim than "no clause can be silently shadowed", and it
is the honest one. Shadowing is possible; a function meaning two different
things at two different moments is not. **The practical consequence:
declaration order *is* meaningful between clauses of equal specificity —
reordering two such clauses changes behavior.**

### 7.3 Sequence patterns

```
sum_all(x: __)    := fold(plus, 0, x)
greet_all(x: ___) := print("Hello!")

sum_all(1, 2, 3)    (* 6 *)
greet_all()          (* Hello! *)
```

`__` (one-or-more) and `___` (zero-or-more) let a single clause match a
variable number of arguments, binding them as a sequence. These
participate in specificity scoring at the lowest tier (§7.1): a clause
using a sequence blank is always considered less specific than one using a
literal or typed blank for the same position.

## 8. Lambdas

```
double = x -> x * 2
map([1, 2, 3], double)        (* [2, 4, 6] *)

filter(x -> x > 2, myList)
```

`x -> ...` is the one lambda form. It is used wherever a function is passed
as a value — `map`, `filter`, rewrite-rule right-hand sides,
`catch`/`recover` handlers.

Two forms this section used to describe are gone. An implicit-parameter
lambda spelled `$` (`square($) := $ * $`) conflicts with `$`'s meaning as
the pipe's argument placeholder (§13), which is the one meaning it now has.
A postfix `&` delimiter (`(x -> x * 2)&`) was never implemented and has
nothing left to delimit.

**Known gap: lambdas take exactly one parameter.** `(a, b) -> a + b` is a
syntax error. A *named* two-argument head works fine as a callback, so a
two-argument function must be given a name first:

```
combine(a: _, b: _) := a * 10 + b
fold([1, 2, 3], combine, 0)   (* 123 *)
```

This is a limitation of the current kernel, not a design decision — see
`docs/capabilities-and-roadmap.md` §3.1.

## 9. Patterns, and where they're allowed to appear

Patterns are not solely a function-definition feature — they're a general
language construct for describing shape, usable anywhere a value needs to
be tested or destructured:

```
MatchQ(42, _int)                    (* True *)
MatchQ("hi", _int)                   (* False *)

match([1, 2, 3], [x: _, y: __])      (* { x: 1, y: [2, 3] } *)
```

The same pattern grammar — bare blanks (`_`), typed blanks (`_int`,
`_string`), sequence blanks (`__`, `___`), and named bindings (`x: _int`)
— is used identically in three places: function clause parameters, the
`match`/`MatchQ` construct above, and rewrite-rule left-hand sides (§10).
This uniformity is deliberate: learning what a pattern means once is
sufficient to read it in any of these three positions.

## 10. Attributes and evaluation order

By default, a function's arguments are evaluated before the function body
ever runs — ordinary strict, eager application. **Hold attributes**, fixed
per-head at definition time, are the one way to opt a specific head out of
this:

```
Attributes(MyMacro) := HoldAll
```

A head with `HoldAll` receives its arguments as unevaluated expression
trees rather than computed values. This is the mechanism underlying
`Hold` itself (§11), and it is available identically to user-defined
functions and to Python-registered heads — there is exactly one hold
mechanism in the language, not a builtin-only special case plus a
separate, weaker facility for everyone else.

**`Listable`** is a separate, also opt-in attribute: a head carrying it
threads over `List` arguments, so `plus([1, 2, 3], 10)` is `[11, 12, 13]`.
**`ResultAware`** marks the few heads permitted to receive an `Err` through
a pipe instead of being skipped (§12).

Minimatic previously specified two further attributes, `Flat` and
`Orderless`, for heads meant to behave algebraically — associativity and
commutativity respectively. **Both were removed from the language**
(`docs/proposal-001-dispatch-results-and-pipes.md` §2.3): their only real
payoff is pattern matching over arithmetic trees, which belongs to the
symbolic-rewriting layer (§11), and variadic arity and ordinary evaluation
of `1 + 2 + 3` never depended on them.

## 11. Rewriting: explicit, not ambient

Rewriting — treating an expression as inspectable, transformable data —
exists in Minimatic, but it is scoped to a deliberate three-step
construct, never something that happens as a side effect of ordinary
evaluation:

```
expr = Hold(f(1) + f(2) + f(6))

rule  = f(x: _) -> x + 10        (* immediate: RHS evaluated once, at match time *)
rule2 = f(x: _) :> random()       (* delayed: RHS evaluated fresh, per match *)

rewritten = expr /. rule          (* Hold(11 + 12 + 16) -- still held *)
ReleaseHold(rewritten)             (* 39 -- explicitly re-enters evaluation *)
```

- **`Hold(expr)`** captures `expr` unevaluated.
- **`/.`** applies a rule (or list of rules) to a held expression — or to
  any plain value, since data and held code share representation (§6.3):

```
[1, 2, 3, 4] /. x: _ -> x^2                  (* [1, 4, 9, 16] *)

[f(1), g(2), f(3)] /. [
    f(x: _) -> x + 10,
    g(x: _) -> x * 100
]                                              (* [11, 200, 13] *)
```

- **`ReleaseHold`** is the single, explicit point where a held expression
  re-enters normal evaluation.
- **`->` vs. `:>`** distinguish an RHS computed once, at the moment a rule
  is applied, from one recomputed per match — relevant whenever the RHS is
  non-deterministic (`random()`) or has a meaningfully different cost if
  cached versus recomputed.

**Rationale:** the alternative — Wolfram Language's model, where rewriting
can be triggered implicitly by evaluation itself via `Unevaluated`,
`$Post`, and similar hooks — makes a program's meaning depend on a tangle
of ambient state that's difficult to reason about compositionally. Scoping
rewriting to `Hold`/`/.`/`ReleaseHold` means: if you don't see one of those
three names in a piece of code, that code's evaluation is guaranteed not
to involve rewriting, full stop. A rewrite is also, notably, an ordinary
value — it can be stored, passed around, or deferred, and it never
silently changes how an unrelated function call behaves elsewhere in the
program.

## 12. Errors are values

**Success is the value itself. There is no `Ok` wrapper.** Failure is an
`Err(kind, detail)` expression.

```
read("file.txt")                     (* the contents, or Err("IOError", "...") *)

read("file.txt") |> parse_json |> process
(* if any step fails, the pipeline short-circuits with that Err *)

read("file.txt") |> catch("IOError", e -> default_file)
read("file.txt") |> recover(e -> fallback)

read("file.txt") |> finally(file -> close(file))
read("file.txt") |> unwrap(default_value)
read("file.txt") |> is_err()
read("file.txt") |> unwrap_err()
```

`Err` is an ordinary expression, matched and destructured with the same
pattern grammar as everything else (§9). Dispatching on error kind is the
idiomatic form, and clause order does not matter — specificity is compared
into the pattern (§7.1):

```
handle(Err("IOError", d: _)) := create_file()
handle(Err("Timeout", d: _)) := retry()
handle(Err(k: _, d: _))      := give_up(k)
handle(data: _)              := process(data)     (* success: a bare value *)
```

Because success is unwrapped, an ordinary function applied through the pipe
already transforms a successful value, and a function that itself returns
value-or-`Err` already chains. No lifting combinators (`map_ok`,
`and_then`) are needed, and none exist.

Failure propagates through `|>` automatically: a function downstream of an
`Err` is skipped rather than called, unless it carries `ResultAware` —
the combinators above, plus `print`/`Head`/`Args`, so a failing pipeline
can still be inspected. Note it is the **pipe** that short-circuits, not the
call: `f(Err(...))` invokes `f`.

### 12.1 What is *not* an `Err`

`Err` is for **expected, routine failure**: a file that isn't there, a
parse that doesn't parse, division by zero, the first element of an empty
list.

Programming errors stay **exceptions**: calling a head that doesn't exist,
passing a string where a list is required, getting the argument count
wrong. These are not routine outcomes to be composed — they are mistakes to
be reported.

The line matters more than where exactly it falls. Without it every mistake
becomes a value that drifts quietly down a pipeline and surfaces, if at all,
far from its cause — and the language loses the ability to tell you that you
wrote something wrong.

**Rationale:** principle 5 (failure as a value) is chosen over exceptions
specifically because "everything is an expression" (principle 1) leaves no
natural place for a `try`/`catch` statement to live — Minimatic has no
statements. Composing failure through the same pipe operator used for
everything else keeps error handling inside the language's one core idiom
rather than introducing a second, structurally different mechanism just
for the failure case.

## 13. The pipe operator

```
5 |> sqrt |> str

myList |> filter(x -> x > 2) |> map(x -> x * 2)
```

`a |> f` is sugar for `f(a)` (or, for multi-argument forms, `a` becomes the
first argument), with the added behavior described in §12 of
short-circuiting on `Err`. It is the idiomatic way to express a
transformation sequence and is used pervasively in the language's own
examples for exactly that reason — it reads in the order operations
happen, left to right, which head-first nested calls (`f(g(h(x)))`)
do not.

### 13.1 `$` — putting the subject somewhere else

First position is only the default. `$` marks where the piped value should
land instead:

```
[1, 2, 3] |> fold(plus, 0)        (* 6  — the subject goes first *)
2 |> minus(10, $)                 (* 8  — minus(10, 2) *)
2 |> plus(1, times($, 10))        (* 21 — any depth *)
3 |> plus($, $)                   (* 6  — every occurrence *)
```

The rules:

- **No `$` anywhere** — first-position splice, as above.
- **Any `$`** — substitution at every occurrence, at any depth. First-position
  splicing is *not* also applied.
- The subject is evaluated **exactly once**, however many times `$` appears.
- A `$` inside a **nested pipe's right-hand side** belongs to that inner
  pipe, not the outer one. The inner pipe's left-hand side is ordinary
  ground and is substituted normally.
- A `$` in a `Lambda` right-hand side (`a |> (x -> $ + x)`) is not
  substituted — there the lambda *is* the function being applied, so `$` is
  just an unbound symbol.

`$` has no other meaning in the language; see §8.

`//`, borrowed from the Wolfram Language, is a second spelling of the same
operator: `a // f` desugars identically to `a |> f`, splices multi-argument
forms into first position the same way, and sits at the same precedence, so
the two mix freely in one chain (`5 |> sqrt // str`). It exists for
familiarity, not as a distinct construct — there is one postfix-application
operator in Minimatic, with two ways to write it.

The other Wolfram operator Minimatic adopts is `/@`: `f /@ xs` is `map(xs, f)`,
written function-first. It binds tighter than arithmetic and is
right-associative, so `f /@ g /@ xs` applies `g` first.

## 14. Extending the language from Python

```python
register_head("http_get", python_http_get)
register_head("my_macro", python_macro_impl, attributes=["HoldAll"])
```

```
get("https://api.example.com/data")
|> catch("Timeout", e -> get("https://backup.example.com"))
|> recover(e -> { "error": e })
|> to_json
|> write("response.json")
```

A Python function registered this way becomes a real Minimatic head:
callable with `head(args)` syntax, eligible for the same hold attributes
as any built-in or user-defined function, and subject to the same
specificity-based dispatch and ambiguity rules if a user later adds a more
specific Minimatic-level clause under the same name. There is no
serialization boundary between "Minimatic values" and "Python values" that
the registered function has to manually bridge, and no separate,
lesser API for extension versus the "real" language — the function *is*
the head.

**Rationale:** this follows directly from principle 6. A language meant to
expose "powerful Python algorithms to any knowledge discipline" fails at
that goal if using a Python-backed function feels different, syntactically
or semantically, from using a built-in one. `register_head` is designed so
that it doesn't.

## 15. What Minimatic deliberately is not

- **Not a general-purpose language.** There is no module system, no
  object/class system, and no intended competition with Python for
  general application logic — Python remains the host, and heavy lifting
  belongs in registered Python heads, not reimplemented in Minimatic.
- **Not lazily evaluated by default.** Only heads with an explicit hold
  attribute defer evaluation of their arguments; the language's default is
  strict, and laziness is opt-in and localized rather than pervasive.
- **Not dynamically re-configurable at runtime in the way Wolfram Language
  is.** There is no `Unprotect`, no runtime rule-table mutation, and no
  ambient hook (`$Post` or equivalent) that changes evaluation behavior
  globally — this is a deliberate absence, not a missing feature.
- **Not exception-based.** There is intentionally no `throw`/`try`/`catch`
  statement-level mechanism; §12 is the only failure-handling model the
  language has, by design.

## 16. Open design questions

1. **Numeric tower.** The examples use plain integers and floats
   throughout; whether Minimatic needs (or should avoid) a Wolfram-style
   exact/arbitrary-precision numeric tower, versus deferring entirely to
   Python's numeric types, is undecided.
2. **String/text operations.** No string-manipulation surface is specified
   yet beyond literals — whether string processing is a small built-in
   vocabulary or expected to live entirely in registered Python heads is
   open.
3. ~~**Equality and ordering under `Orderless`.**~~ **Closed — moot.**
   `Orderless` was removed from the language (§10), so there is no
   canonical order to specify.
4. **Scoping of `Hold`-captured free variables.** If a `Hold`-ed expression
   references a name bound in an enclosing scope, and that name is
   rebound before `ReleaseHold` runs, which binding does the release see?
   This interacts with §5 (rebinding is not mutation) and needs an
   explicit answer before rewriting semantics can be considered settled.
5. ~~**Multi-argument pipe semantics.**~~ **Closed.** `a` takes first
   position by default, and `$` places it anywhere instead — §13.1.
6. **Multi-parameter lambdas.** `(a, b) -> ...` does not parse (§8). The
   syntax is uncontroversial; what needs deciding is whether it also brings
   pattern-matched lambda parameters (`(x: _int, y: _) -> ...`) or stays
   bare-name-only. Newly open.

Numbering is kept stable so cross-references stay valid; settled questions
are struck rather than removed.

These are primarily language-semantics questions, independent of the
tree-walker implementation strategy, and should be resolved here — in the
language spec — before (or alongside) the corresponding parts of the
kernel are built out.

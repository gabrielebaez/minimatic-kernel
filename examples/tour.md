# A tour of Minimatic

This is a runnable Minimatic program, written as a Markdown document. Every
fenced ` ```minimatic ` block below is executed, in order, against the same
kernel — later blocks see whatever earlier blocks defined. Everything else
on this page (this sentence included) is just prose and is ignored.

Run it yourself:

```bash
python -m minimatic examples/tour.md
```

## Specificity beats declaration order

Clauses are tried most-specific-first — a literal beats a typed blank,
which beats a bare blank — regardless of what order you *write* them in.
Here the most general clause is declared first, on purpose, to prove the
point: it still loses to the more specific clauses below it.

```minimatic
describe(x: _) := "something else"
describe(x: _string) := "a string"
describe(x: _int) := "an integer"

describe(5)
describe("hi")
describe(3.14)
```

## Recursion needs no `if` — literal clauses are the base case

There's no `if`/`cond` special form in Minimatic. You don't need one:
a literal pattern (`0`) is simply more specific than a typed blank
(`_int`), so it's tried first and acts as the base case.

```minimatic
fact(0) := 1
fact(n: _int) := n * fact(n - 1)

fact(10)
```

```minimatic
fib(0) := 0
fib(1) := 1
fib(n: _int) := fib(n - 1) + fib(n - 2)

fib(10)
```

## Dispatch works across every argument position at once

Specificity is scored per position and compared lexicographically, so a
classifier like FizzBuzz falls out of plain clause definitions — no
boolean `and`/`or` needed, just four clauses ordered by how many literal
positions they pin down.

```minimatic
classify(n: _int, 0, 0) := "FizzBuzz"
classify(n: _int, 0, _) := "Fizz"
classify(n: _int, _, 0) := "Buzz"
classify(n: _int, _, _) := n

fizzbuzz(n: _int) := classify(n, mod(n, 3), mod(n, 5))

[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15] |> map(fizzbuzz)
```

## Sequence blanks capture a variable number of arguments

`__` (one-or-more) binds every remaining argument as a single `List`.

```minimatic
sum_all(xs: __) := fold(xs, plus, 0)

sum_all(1, 2, 3, 4, 5)
```

## `Listable` heads thread over lists automatically

Arithmetic heads are `Listable`: called with a `List` argument, they map
themselves over it elementwise instead of erroring.

```minimatic
[1, 2, 3, 4] + [10, 20, 30, 40]
[1, 2, 3, 4] ^ 2
```

This is exactly the mechanism that makes rewrite rules like this one work —
`x` gets bound to the *whole* list by the trivially-matching `_` pattern,
and `Power`'s `Listable` attribute is what turns `x^2` back into an
elementwise square instead of a type error:

```minimatic
[1, 2, 3, 4] /. x: _ -> x ^ 2
```

## `/.` rewrites data, with one rule or several

```minimatic
[1, "N/A", 2, "ERROR", 3] /. ["N/A" -> 0, "ERROR" -> -1]
```

## Lambdas are closures, and curry naturally

`a -> b -> a + b` is just two nested one-argument lambdas — applying the
outer one returns a real closure over `a`, not a re-parsed function. (Its
printed form is raw internal detail for now, not pretty-printed — that's
a known MVP gap, not a feature.)

```minimatic
add(a) := b -> a + b
add5 = add(5)

add5(10)
add(5)(20)
```

## Putting it together: pipe, lambda, map, fold

```minimatic
[1, 2, 3, 4]
|> map(x -> x * x)
|> fold(plus, 0)
```

```minimatic
xs = [10, 20, 30]

xs |> length
xs |> first
xs |> rest
xs |> append(40)
```

`first`/`rest` are the list accessors. `head` is *not* one of them: in a
language where everything is `head(args)`, the head of `[10, 20, 30]` is
`List`, not `10`. That inspection lives in `Head`, which is total — every
value has a head, including `[]` and atoms:

```minimatic
Head(xs)
Head([])
Head(42)
Args(xs)
```

## Control flow is ordinary functions, not special syntax

`if`, `switch`, `which`, `for`, and `each` are registered heads like any
other — branches are skipped by *not evaluating* the unchosen argument,
following each head's own hold attributes, the same mechanism `Lambda`
and `SetDelayed` already use. There's no `if`/`switch` case hard-coded
into the evaluator.

```minimatic
if(3 < 5, "yes", 1 / 0)
```

The `1 / 0` above is never evaluated — `if` is `HoldRest`, so only the
taken branch is looked at. Same story for `switch` (evaluates cases one at
a time until one matches, then evaluates only that result) and `which` (a
plain cond/elif chain):

```minimatic
grade(score: _int) := switch(True,
    score >= 90, "A",
    score >= 80, "B",
    score >= 70, "C",
    "F")

grade(95)
grade(72)
grade(40)
```

`for`/`each` apply a function to every element of a list for effect and
return `Null` (unlike `map`, they don't collect the results) — `0..5` is
`Range`, sugar for the half-open list `[0, 1, 2, 3, 4]`:

```minimatic
for(0 .. 5, y -> print(y))
```

And `(stmt1; stmt2; ...)` sequences expressions for effect, evaluating to
the last one — this is what lets a function body run more than one
statement:

```minimatic
greet() := (print("Hello"); print("World"))

greet()
```

## `//` and `/@`: the Wolfram spellings

Two operators come straight from the Wolfram Language. `//` is postfix
application — `a // f` is `f(a)` — which in Minimatic is `|>` under
another name: the same head, the same first-position argument splicing,
the same precedence, so the two chain together freely.

```minimatic
[1, 2, 3] // length
[1, 2, 3] // append(4)
5 // (x -> x * 2)
[1, 2, 3, 4] |> map(x -> x * x) // fold(plus, 0)
```

`/@` is `map`, written function-first: `f /@ xs` is `map(xs, f)`. It binds
tighter than arithmetic and is right-associative, so `f /@ g /@ xs` runs
`g` first.

```minimatic
triple(x: _int) := 3 * x
inc(x: _int) := x + 1

triple /@ [1, 2, 3]
triple /@ inc /@ [1, 2, 3]
triple /@ [1, 2, 3] // fold(plus, 0)
```

## Guards and alternatives: patterns that describe more than shape

A pattern says what an argument *looks like*. Two constructs let it say
more than that.

`p1 | p2` matches either shape:

```minimatic
tag(v: _int | _string) := "scalar"
tag(v: _list)          := "list"
tag(v: _)              := "something else"

tag(42)
tag("hi")
tag([1, 2])
tag(3.14)
```

`/;` adds a guard — an ordinary boolean expression, evaluated against the
names the pattern just bound. Written after the whole clause head, it
selects between clauses that are the same shape but differ by value:

```minimatic
polarity(n: _int) /; n < 0  := "negative"
polarity(n: _int) /; n == 0 := "zero"
polarity(n: _int)           := "positive"

polarity(-2)
polarity(0)
polarity(7)
```

A guard can also sit on a single argument, and can see the other
arguments bound before it:

```minimatic
ordered(lo: _int, hi: _int) /; hi > lo := "ok"
ordered(lo: _int, hi: _int)            := "swapped"

ordered(1, 5)
ordered(5, 1)
```

Guards score exactly as their unguarded shape does — a guard narrows at
run time, which specificity cannot see — so **guarded clauses must be
written first**, as above. Declared after the catch-all, a guarded clause
is unreachable.

## `Hold` and `ReleaseHold`: code as data

Everything so far rewrites *data*: by the time `/.` runs, its subject has
already been evaluated. `Hold` is how you get an expression that hasn't
been, so a rule can meet the shape it was written for.

```minimatic
expr = Hold(f(1) + f(2) + f(6))

rule = f(x: _) -> x + 10

rewritten = expr /. rule
ReleaseHold(rewritten)
```

`f` is never defined anywhere — `Hold` captures the call without looking
at it, `/.` rewrites the three `f(...)` nodes in place, and `ReleaseHold`
is the one explicit point where the result re-enters evaluation.

A held expression is an ordinary two-element expression with no captured
environment, so patterns match it like any other value, and `ReleaseHold`
evaluates in the scope it is released in:

```minimatic
Hold(f(1)) /. Hold(e: _) -> "was held"
```

`->` computes its right-hand side at the moment the rule matches, which is
what you want for data. `:>` substitutes it unevaluated, which is what you
want for code:

```minimatic
Hold(g(1)) /. g(a: _) -> a + 1
Hold(g(1)) /. g(a: _) :> a + 1
```

`//.` applies rules over and over until nothing changes — a normal form.
With a delayed rule, that is a small macro expander:

```minimatic
Hold(not(not(not(True)))) //. not(not(a: _)) :> a
ReleaseHold(Hold(not(not(not(True)))) //. not(not(a: _)) :> a)
```

Rules that never settle are an error, not a hang: `//.` gives up once the
passes or the expression size run past their limits.

## Dicts

`{ key -> value, ... }` is a dict. Entries are sorted by key when the dict
is built, so two dicts written in different orders are the *same value* —
which is what lets `==` and pattern matching agree about them without any
dict-specific rules:

```minimatic
stock = { "Orange" -> 1, "Green" -> 2 }

stock
stock == { "Green" -> 2, "Orange" -> 1 }
```

Reading:

```minimatic
keys(stock)
values(stock)
length(stock)
has_key(stock, "Green")
key_get(stock, "Green")
key_get(stock, "Purple")
```

A missing key is an ordinary `Err` value, not a raised error, so it flows
through a pipeline like any other failure:

```minimatic
key_get(stock, "Purple") |> unwrap(0)
```

Every update returns a new dict; the original is untouched:

```minimatic
key_set(stock, "Blue", 10)
key_drop(stock, "Orange")
stock
```

`merge` is right-biased on conflicting keys, and `map_values` transforms
values in place:

```minimatic
merge(stock, { "Green" -> 99, "Blue" -> 10 })
stock |> map_values(n -> n * 100)
```

`to_pairs` and `from_pairs` bridge to the list layer, so list combinators
work on a dict without dict-specific versions of each:

```minimatic
to_pairs(stock)
to_pairs(stock) |> from_pairs
```

Because a dict is an ordinary expression, everything else already works on
it — structure inspection, rewriting, and patterns:

```minimatic
Head(stock)
{ "a" -> "N/A" } /. "N/A" -> 0

price({ "item" -> n: _, "cost" -> c: _ }) := n
price(d: _dict)                            := "no cost"

price({ "cost" -> 5, "item" -> "pen" })
price({ "item" -> "pen" })
```

A dict pattern matches *exactly* those entries — the second call falls
through because the dict has no `"cost"`. Matching on a subset of keys is
not built yet.

---

This is all MVP-stage behavior — see `IMPLEMENTATION_PLAN.md` and the
README's status table for what's deferred (ambiguity detection, `Flat`/
`Orderless`, `Ok`, indexing, the string layer). Nothing above depends on
any of that.

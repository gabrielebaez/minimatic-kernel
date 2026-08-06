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
xs |> head
xs |> tail
xs |> append(40)
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

---

This is all MVP-stage behavior — see `IMPLEMENTATION_PLAN.md` and the
README's status table for what's deferred (ambiguity detection, `Flat`/
`Orderless`, `Hold`/`ReleaseHold`, `Ok`/`Err`). Nothing above depends on
any of that.

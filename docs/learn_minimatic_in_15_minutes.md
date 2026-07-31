```
(* ============================================ *)
(* LEARN MINIMATIC IN 15 MINUTES                *)
(* ============================================ *)

(* Comments look like this. *)

(*  Everything is an expression,                *)
(*  written as head(args).                      *)


(* ============================================ *)
(* 1. THE BASICS                                *)
(* ============================================ *)

print("hello world")   (* hello world *)

1 + 3        (* 4  -- sugar for plus(1, 3)  *)
2 * 5        (* 10 -- sugar for times(2, 5) *)
2 ^ 3        (* 8  -- sugar for power(2, 3) *)

plus(4, 1, 2, 3)        (* 9  -- function form *)
plus(2, times(4, 2))    (* 10 -- nesting       *)

(* The pipe operator reads left-to-right *)
5 |> sqrt |> str           (* "2.236..." *)


(* ============================================ *)
(* 2. VARIABLES                                 *)
(* ============================================ *)

x = 5            (* 5  *)
x == 5           (* True *)
x = x + 5        (* 10 -- rebinding, not mutation *)
set(x, 20)       (* explicit form of = *)


(* ============================================ *)
(* 3. DATA - IMMUTABLE, ALWAYS                  *)
(* ============================================ *)

myList = [1, 2, 3, 4]
myList[0]                   (* 1 *)
map(double, myList)         (* [2, 4, 6, 8] *)
double /@ myList            (* same thing, shorthand for map *)
fold(plus, 0, myList)       (* 10 *)
append(myList, 5)           (* [1, 2, 3, 4, 5] -- new list *)
myList[1] <- 5              (* [1, 5, 3, 4] -- new list *)
myList                      (* [1, 2, 3, 4] -- original untouched *)
0..5                        (* [0, 1, 2, 3, 4] *)

myHash = { "Green" -> 2, "Orange" -> 1 }
myHash["Green"]                        (* 2 *)

myHash 
|> key_drop("Green") 
|> set("Blue", 10)  (* new dict *)


(* ============================================ *)
(* 4. FUNCTIONS: CLOSED, PATTERN-MATCHED CLAUSES*)
(* ============================================ *)

(* A function is a fixed set of clauses, resolved once    *)
(* at definition time. Calling a function always has      *)
(* exactly one unambiguous outcome.                       *)

double(x: _) := x * 2
double(3)               (* 6 *)

(* Add a more specific clause *)
describe(x: _int)    := "an integer"
describe(x: _string) := "a string"
describe(x: _)       := "something else"

describe(5)      (* "an integer"     *)
describe("hi")   (* "a string"       *)
describe([1,2])  (* "something else" *)

(* Sequence blanks: one-or-more / zero-or-more args *)
sum_all(x: __)    := fold(plus, 0, x)
greet_all(x: ___) := print("Hello!")

sum_all(1, 2, 3)   (* 6 *)
greet_all()        (* Hello! *)


(* ============================================ *)
(* 5. LAMBDAS                                   *)
(* ============================================ *)

square($) := $ * $
map(square, [1, 2, 3])   (* [1, 4, 9] *)

(x -> x * 2)&            (* explicit lambda, named args *)
filter(x -> x > 2, myList) |> map(double)


(* ============================================ *)
(* 6. CONTROL FLOW                              *)
(* ============================================ *)

MyFirst() := (print("Hello"); print("World"))

for(0..5, y -> print(y))
each(myList, y -> print(y))

if(x == 8, print("Yes"), print("No"))

switch(x,
    2, print("Two"),
    8, print("Yes"))

which(
    x == 2, print("No"),
    x == 8, print("Yes"))


(* ============================================ *)
(* 7. PATTERNS AND MATCHQ                       *)
(* ============================================ *)

(* Patterns describe shape, not just functions'        *)
(* argument lists -- you can test and destructure with  *)
(* them anywhere. *)

MatchQ(42, _int)              (* True  *)
MatchQ("hi", _int)            (* False *)

match([1, 2, 3], [x: _, y: __])   (* { x: 1, y: [2, 3] } *)


(* ============================================ *)
(* 8. ATTRIBUTES: HOLD, AND WHY THEY MATTER     *)
(* ============================================ *)

(* By default, arguments are evaluated before a function   *)
(* sees them -- ordinary strict application.               *)
(*                                                         *)
(* A head can instead be declared with a Hold attribute,   *)
(* fixed at definition time, telling the evaluator to pass *)
(* it the *unevaluated* expression tree instead of a value.*)
(* This is what lets code be treated as data -- the basis  *)
(* for rewriting and macro-like constructs below.          *)

Attributes(MyMacro) := HoldAll

(* Flat and Orderless let you opt specific heads into      *)
(* algebraic normalization, without making it the default  *)
(* behavior for every function in the language.            *)

Attributes(Plus) := [Flat, Orderless]
Plus(Plus(a, b), c)     (* automatically flattens: Plus(a, b, c) *)


(* ============================================ *)
(* 9. REWRITING: EXPLICIT, NOT AMBIENT          *)
(* ============================================ *)

(* Rewriting is a construct you reach for on purpose --    *)
(* it does not run behind ordinary function calls. The     *)
(* pattern: quote/hold an expression, transform it with    *)
(* rules, then explicitly evaluate the result.             *)

expr = Hold(f(1) + f(2) + f(6))

rule  = f(x: _) -> x + 10        (* immediate: RHS evaluated once   *)
rule2 = f(x: _) :> random()      (* delayed: RHS evaluated per match *)

rewritten = expr /. rule        (* Hold(11 + 12 + 16) -- still held *)
ReleaseHold(rewritten)          (* 39 -- explicitly re-enters evaluation *)

(* Rewriting a plain (already-evaluated) list works the   *)
(* same way, since lists don't need holding to inspect:   *)

[1, 2, 3, 4] /. x_ -> x^2       (* [1, 4, 9, 16] *)

[f(1), g(2), f(3)] /. [
    f(x: _) -> x + 10,
    g(x: _) -> x * 100
]                                (* [11, 200, 13] *)

(* Because expansion is explicit, a rewrite is a value     *)
(* like any other -- it can be stored, passed around, or   *)
(* deferred, and it never silently changes how an unrelated*)
(* function call behaves elsewhere in the program. *)


(* ============================================ *)
(* 10. ERRORS: RESULTS, NOT EXCEPTIONS          *)
(* ============================================ *)

read("file.txt")           (* Ok(content) or Err("IOError", "...") *)

read("file.txt") |> parse_json |> process
(* if any step fails, the pipeline short-circuits with that Err *)

read("file.txt") |> catch("IOError", e -> default_file)
read("file.txt") |> recover(e -> fallback)

match(read("file.txt"), [
    Ok(data)          -> process(data),
    Err("IOError", _) -> create_file(),
    Err("Timeout", _) -> retry()
])

read("file.txt") |> finally(file -> close(file))

read("file.txt") |> unwrap(default_value)
read("file.txt") |> is_ok()
read("file.txt") |> is_err()
read("file.txt") |> unwrap_err()


(* ============================================ *)
(* 11. EXTENDING FROM PYTHON                    *)
(* ============================================ *)

(* Any Python function can be registered as a new head.      *)
(* Whether it receives evaluated values or held, unevaluated *)
(* expressions is decided by the attribute you give it --    *)
(* the same mechanism used for user-level macros above, so   *)
(* extensions are first-class citizens of the language,      *)
(* not a separate FFI layer bolted on the side.              *)

(* register_head("http_get", python_fn)               *)
(* register_head("my_macro", python_fn, HoldAll)      *)

get("https://api.example.com/data")
|> catch("Timeout", e -> get("https://backup.example.com"))
|> recover(e -> { "error": e })
|> to_json
|> write("response.json")


(* ============================================ *)
(* 12. PUTTING IT TOGETHER                      *)
(* ============================================ *)

(* Sum of squares of evens, 1 to 20 *)
1..21
|> filter(x -> x % 2 == 0)
|> map(square)
|> fold(plus, 0)

(* Clean, sum, and report a messy dataset *)
[1, "N/A", 3, "N/A", 5]
|> map(x -> x /. "N/A" -> 0)
|> fold(plus, 0)
|> str
|> print
```
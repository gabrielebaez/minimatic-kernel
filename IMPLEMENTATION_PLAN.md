# Minimatic Kernel — MVP Implementation Plan

**Date:** 2026-07-30
**Status:** **Historical.** MVP implemented and complete (69 tests green at
the time). Superseded for everything after the MVP milestone.
**Scope:** `minimatic-kernel` — MVP tree-walker interpreter for Minimatic

> **Read this as a record, not as current documentation.** It describes what
> the MVP was and why, including decisions later reversed: it calls
> ambiguity checking and `Flat`/`Orderless` "deferred" when both were
> subsequently **removed from the language**, registers `head`/`tail` where
> the kernel now has `first`/`rest`, and predates `Err`, `$` pipe
> placeholders, `Head`/`Args` and nested `score()`.
>
> Its `Hold`/`ReleaseHold`/`:>` deferrals have since been lifted, along
> with `//.` and the pattern-language additions (`|`, `/;`). One detail it
> got wrong in anticipation: it assumes `Hold` performs "lexical
> env-snapshot capture". It does not — `Hold` captures nothing and
> `ReleaseHold` evaluates in the scope it is released in, which is what
> keeps a held node structurally identical to ordinary data. See
> `docs/the language.md` §16.4.
>
> For current state:
> [`docs/capabilities-and-roadmap.md`](docs/capabilities-and-roadmap.md).
> For the decisions that superseded this:
> [`docs/proposal-001-dispatch-results-and-pipes.md`](docs/proposal-001-dispatch-results-and-pipes.md).

> This document was written before implementation started, then updated
> afterward with a short "What changed during implementation" note per
> phase — three things surfaced that weren't anticipated in the original
> sketch:
> 1. **Bare identifiers in pattern position bind, they don't match literally.**
>    `add(a) := b -> a + b` needs `a` to capture whatever value is passed —
>    otherwise every non-underscore, non-typed parameter name would require
>    an exact literal-symbol match, which is useless as a parameter
>    convention. This is genuinely in the spirit of what you asked for
>    (Erlang/ML-style: a bare variable in a pattern binds; only literals,
>    blanks, and explicit type tags constrain). Expression *heads* are
>    exempted from this — `List(a, b)` still requires the value's head to
>    literally be `List`, only its arguments bind.
> 2. **`Listable` (auto-threading over List arguments) turned out to be in
>    scope, not deferred.** The kernel doc's own `[1,2,3,4] /. x: _ -> x^2`
>    example only produces `[1,4,9,16]` if `Power` threads over the list `x`
>    got bound to — otherwise it's `List(1,2,3,4) ^ 2`, a type error. Unlike
>    `Flat`/`Orderless`, `Listable` doesn't interact with clause dispatch or
>    scoring at all, so it doesn't carry the risk that got `Flat`/`Orderless`
>    deferred. It's implemented as a pre-dispatch argument-threading step in
>    `eval.py`, and `plus`/`minus`/`times`/`divide`/`power`/`mod`/`negate`
>    all carry it.
> 3. **`map`/`fold` take the list first**, i.e. `fold(xs, f, init)` not
>    `fold(f, init, xs)`. This falls directly out of the pipe's fixed-
>    first-position splicing (`xs |> fold(f, init)` desugars to
>    `fold(xs, f, init)`) — the two orderings can't both be right, and the
>    flagship example only exercises the piped form.

---

## Project state

- AST partially built (`minimatic/ast/`: `Symbol`, `Expression`, atoms, `attributes.py`)
- No lexer, parser, evaluator, dispatch, or prelude yet
- Four detailed design docs (~1,300 lines total) defining the full language and interpreter architecture
- Single initial commit on `main`

## What "MVP" means here

The full design (`docs/the kernel.md` §6, `docs/the language.md` §7) calls for
**specificity-based clause dispatch** with **definition-time ambiguity
rejection** (`overlaps`/`implies` over arbitrary nested patterns). That
ambiguity check is explicitly the highest-risk, least-specified part of the
kernel — `docs/the kernel.md` lists nested-pattern overlap detection as an
**open design question (§14.1)**, unsolved at the architecture level.

The MVP defers that specific piece and ships everything else. Concretely:

| Question | Decision |
|---|---|
| Nested ambiguity checking | **Deferred.** No `overlaps`/`implies`, no `AmbiguousClauseError`. |
| Clause ordering | **Hybrid.** Keep `score()` (literal > typed blank > blank > sequence blank per argument, compared lexicographically) and sort by it — this is cheap and fully specified. Same-score clauses are tried in **declaration order** (first structural match wins among ties) instead of being rejected. |
| Flat/Orderless | **Deferred.** Tangled with dispatch scoring per open question §14.2; building it before dispatch settles means building on ground that moves. `plus`/`times` ship as ordinary (non-commutative-in-pattern) prelude heads. |
| `Hold`/`ReleaseHold` (held *code*, env-snapshot capture) | **Deferred.** Only `HoldAll`/`HoldFirst`/`HoldRest` on argument evaluation ship (needed for `:=` and lambdas). `/.` ships as data-rewriting only. |
| `Ok`/`Err` combinator suite | **Deferred.** `\|>` pipe desugaring and evaluation ship without `Err` short-circuiting. |
| Self-hosting derived prelude | **Deferred** to post-MVP. |
| Flat/Orderless dispatch canonicalization | N/A (deferred with Flat/Orderless) |
| Redefinition semantics | Clause sets sealed after first dispatch attempt (unchanged from original design) |
| Multi-arg pipe | Fixed first-position: `a \|> f(b, c)` desugars to `f(a, b, c)` (unchanged) |

**Acceptance bar** — both README flagship examples must run through the REPL:

```
double(x: _int) := 2 * x
double(21)                       (* 42 *)

[1, "N/A", 3, "N/A", 5]
|> map(x -> x /. "N/A" -> 0)
|> fold(plus, 0)                 (* 9 *)
```

**Documentation note:** until ambiguity detection lands, the README's claim
that "ambiguous, overlapping clauses are caught as an error at definition
time" is aspirational, not current behavior. The README's status table
should say so plainly rather than overclaim.

---

## Phase 0: Project Scaffolding

**Goal:** Runnable package with the core data model, finished.

### Files to create/update

```
pyproject.toml            # add pytest as dev dependency
minimatic/errors.py
minimatic/ast/patterns.py # Blank, BlankSeq, BlankNullSeq, PatternBind
tests/__init__.py
tests/conftest.py
tests/test_ast.py
```

### Already done

`minimatic/ast/symbol.py`, `minimatic/ast/expression.py`, `minimatic/ast/atoms.py`,
`minimatic/attributes.py` — `Symbol`, `Expression` (head + tail), atom
predicates, and the `Attr`-equivalent symbol table already exist and match
the unified-node-model intent (kernel doc §2). Reuse them as-is; do not
introduce a parallel `Node`/`Literal` type.

### minimatic/ast/patterns.py — pattern node types

```python
@dataclass(frozen=True)
class Blank:
    type_tag: str | None        # _  or  _int

@dataclass(frozen=True)
class BlankSeq:
    type_tag: str | None        # __

@dataclass(frozen=True)
class BlankNullSeq:
    type_tag: str | None        # ___

@dataclass(frozen=True)
class PatternBind:
    name: str
    pattern: object              # x: _int
```

All dataclasses `frozen=True` — immutable by construction. These are a
*subset* of the value space, used only in clause heads and `/.` LHS, never
produced by ordinary evaluation.

### errors.py — Exception hierarchy

```python
class MinimaticError(Exception): ...
class MinimaticSyntaxError(MinimaticError): ...
class UnboundSymbolError(MinimaticError): ...
class UnknownHeadError(MinimaticError): ...
class NoMatchingClauseError(MinimaticError): ...
class HeadAlreadySealedError(MinimaticError): ...
class ArityError(MinimaticError): ...
class MinimaticTypeError(MinimaticError): ...
```

(`AmbiguousClauseError` intentionally omitted — no ambiguity detection in MVP.)

### Verification

- `python -c "from minimatic.ast import Expression, Symbol; print(Expression(Symbol('plus'), 1, 3))"` prints without error
- `pytest tests/test_ast.py` passes

---

## Phase 1: Lexer + Parser

**Goal:** Source text → AST tree (`Symbol` / atom / `Expression` / pattern nodes) with all sugar desugared. No semantic work.

### Files to create

```
minimatic/lexer.py
minimatic/parser.py
tests/test_lexer.py
tests/test_parser.py
```

### lexer.py — token stream

```
# Literals
INT, FLOAT, STRING, TRUE, FALSE

# Identifiers
IDENT          # names: x, myFunc, _int, __, ___

# Operators
PLUS, MINUS, STAR, SLASH, CARET, PERCENT
EQ, NEQ, LT, GT, LTE, GTE
ARROW          # ->
DELAYED_ARROW  # :>
REPLACE        # /.
PIPE           # |>
RANGE          # ..
AMP            # &

# Delimiters
LPAREN, RPAREN, LBRACKET, RBRACKET, LBRACE, RBRACE
COMMA, COLON, SEMICOLON

# Special
DEFINE         # :=
ASSIGN         # =

# Comments
(* ... *)       # nested block comments
```

Iterative character scanner, no external lexer generator.

### parser.py — recursive descent + precedence climbing

**Precedence levels** (low to high):

| Level | Operators |
|---|---|
| 1 | `\|>`, `//` (postfix apply, left-assoc) |
| 2 | `->` and `:>` (rule arrows, right-assoc) |
| 3 | `==`, `!=`, `<`, `>`, `<=`, `>=` |
| 4 | `+`, `-` |
| 5 | `*`, `/`, `%` |
| 5.5 | `/@` (map, right-assoc) |
| 6 | `^` (right-assoc) |
| 7 | Unary `-`, `!` |
| 8 | Function call, indexing, postfix `&` |

**Desugaring reference:**

| Surface syntax | Desugared form |
|---|---|
| `1 + 3` | `Expression(Symbol("plus"), 1, 3)` |
| `[1, 2, 3]` | `Expression(Symbol("List"), 1, 2, 3)` |
| `{ "a" -> 1 }` | `Expression(Symbol("Dict"), Expression(Symbol("Rule"), "a", 1))` |
| `x -> x * 2` | `Expression(Symbol("Lambda"), params, body)` |
| `a \|> f` | `Expression(Symbol("__pipe__"), a, f)` |
| `a // f` | `Expression(Symbol("__pipe__"), a, f)` |
| `f /@ xs` | `Expression(Symbol("map"), xs, f)` |
| `f(x: _int) := ...` | `Expression(Symbol("Define"), pattern, body)` |
| `expr /. rule` | `Expression(Symbol("ReplaceAll"), expr, rule)` |

**Grammar sketch** (simplified):

```
program       = expr
expr          = pipe_expr
pipe_expr     = call_expr ( PIPE call_expr )*
call_expr     = postfix_expr ( LPAREN arg_list RPAREN )?
postfix_expr  = primary ( AMP )?
primary       = INT | FLOAT | STRING | TRUE | FALSE
              | IDENT
              | LPAREN expr RPAREN
              | list_literal
              | dict_literal
              | lambda_expr
              | define_expr

list_literal  = LBRACKET ( expr ( COMMA expr )* COMMA? )? RBRACKET
dict_literal  = LBRACE ( rule_expr ( COMMA rule_expr )* COMMA? )? RBRACE
rule_expr     = expr ARROW expr | expr DELAYED_ARROW expr

lambda_expr   = IDENT ARROW expr              # named: x -> x * 2

define_expr   = pattern LPAREN arg_list RPAREN DEFINE expr    # clause def
              | pattern ASSIGN expr                            # binding

pattern       = blank | typed_blank | seq_blank | pattern_bind | IDENT | INT | STRING | LPAREN pattern RPAREN
blank         = UNDERSCORE                   # _
typed_blank   = UNDERSCORE IDENT             # _int, _string
seq_blank     = UNDERSCORE UNDERSCORE        # __  (one or more)
              | UNDERSCORE UNDERSCORE UNDERSCORE  # ___ (zero or more)
pattern_bind  = IDENT COLON pattern          # x: _int

arg_list      = ( pattern ( COMMA pattern )* )?
```

### Verification

```python
from minimatic.parser import parse

parse("1 + 3")            # Expression(Symbol("plus"), Literal(1), Literal(3))
parse("5 |> sqrt |> str") # nested __pipe__ expressions, left-assoc
parse("x -> x * 2")       # Expression(Symbol("Lambda"), ...)
parse("[1, 2, 3]")        # Expression(Symbol("List"), 1, 2, 3)
```

- `pytest tests/test_lexer.py tests/test_parser.py` passes
- All desugaring examples above parse correctly

---

## Phase 2: Environment + Evaluator Core

**Goal:** `eval(node, env) -> value` — single-pass tree walker, no fixpoint loop.

### Files to create

```
minimatic/env.py
minimatic/eval.py
minimatic/registry.py
tests/test_env.py
tests/test_eval.py
```

### env.py — lexical scope

```python
class Env:
    def __init__(self, bindings, parent=None): ...
    def lookup(self, name): ...   # raises UnboundSymbolError if not found anywhere
    def extend(self, bindings): ...  # new child Env
```

### eval.py — core evaluation loop

```python
def eval(node, env):
    match node:
        case int() | float() | str() | bool() | None:
            return node
        case Symbol(name=name):
            return env.lookup(name)
        case Expression(head=head, tail=args):
            head_val = head if isinstance(head, Symbol) else eval(head, env)
            clause_set = registry.resolve(head_val)
            if clause_set is None:
                raise UnknownHeadError(head_val)

            attrs = registry.attributes(head_val)
            eval_args = [
                a if is_held(attrs, i) else eval(a, env)
                for i, a in enumerate(args)
            ]
            return clause_set.apply(eval_args, env)
```

**Critical constraints:**
- Single pass, no fixpoint loop (kernel doc §4.1) — this is a permanent
  property, not something the MVP is cutting.
- `is_held(attrs, i)` checks `HoldAll`/`HoldFirst`/`HoldRest` only.
- No `Flat`/`Orderless` canonicalization step in MVP (deferred, see above).

### registry.py — head registry

```python
class Registry:
    def __init__(self):
        self._clause_sets: dict[str, ClauseSet] = {}
        self._attributes: dict[str, frozenset[Symbol]] = {}

    def resolve(self, head: Symbol) -> ClauseSet | None: ...
    def attributes(self, head: Symbol) -> frozenset[Symbol]: ...
```

### Verification

```python
from minimatic import Kernel

kernel = Kernel()
kernel.eval("x = 5")
kernel.eval("x")  # 5

kernel.eval("double(x: _int) := x * 2")
kernel.eval("double(21)")  # 42
```

- `pytest tests/test_eval.py` passes
- Basic binding, function definition, and call work
- `UnboundSymbolError` raised for undefined names

---

## Phase 3: Pattern Matching + Hybrid Clause Dispatch

**Goal:** `score()`-ordered dispatch with declaration-order tiebreak. No ambiguity detection.

### Files to create

```
minimatic/match.py
minimatic/dispatch.py
tests/test_match.py
tests/test_dispatch.py
```

### match.py — structural pattern matcher

```python
def match(pattern, value, bindings):
    """Match a pattern against a value. Returns bindings dict or None on failure."""
    match pattern:
        case Blank(type_tag=None):
            return bindings
        case Blank(type_tag=tag):
            return bindings if check_type(value, tag) else None
        case BlankSeq() | BlankNullSeq():
            ...  # handled in match_all, which knows argument position
        case PatternBind(name=name, pattern=inner):
            b = match(inner, value, bindings)
            return None if b is None else {**b, name: value}
        case Symbol(name=name):
            return bindings if isinstance(value, Symbol) and value.name == name else None
        case Expression(head=h, tail=t) if isinstance(value, Expression):
            b = match(h, value.head, bindings)
            return None if b is None else match_args(t, value.tail, b)
        case _:
            return bindings if pattern == value else None
```

**Shared by:** `dispatch.py` (call-time matching) now; `rewrite.py` (Phase 4)
reuses the same function for `/.` LHS matching. One implementation, one
semantics (kernel doc §5) — this property is *not* weakened by deferring
ambiguity detection.

### dispatch.py — ClauseSet with hybrid ordering

```python
@dataclass
class Clause:
    pattern: object
    body: object
    specificity: tuple[int, ...]   # per-argument specificity vector
    order: int                      # declaration order, tiebreaker only

class ClauseSet:
    def __init__(self, head_name: str):
        self.head_name = head_name
        self.clauses: list[Clause] = []   # sorted by (specificity desc, order asc)
        self.sealed = False

    def insert(self, pattern, body):
        if self.sealed:
            raise HeadAlreadySealedError(self.head_name)
        clause = Clause(pattern, body, score(pattern), len(self.clauses))
        self.clauses.append(clause)
        self.clauses.sort(key=lambda c: (tuple(-s for s in c.specificity), c.order))
        # No ambiguity check: same-score clauses simply stay in declaration order.

    def apply(self, args, env):
        self.sealed = True
        for clause in self.clauses:
            if (bindings := match_all(clause.pattern, args)) is not None:
                return eval(clause.body, env.extend(bindings))
        raise NoMatchingClauseError(self.head_name, args)

def score(pattern) -> tuple[int, ...]:
    """Per-argument specificity vector.
    Literal: 3, typed blank (_int): 2, bare blank (_): 1, sequence blank (__, ___): 0.
    """
    ...
```

**What changed vs. the full design:** no `overlaps()`, no `implies()`, no
`AmbiguousClauseError`. `score()` is unchanged from the original design and
is what makes `describe(_int)` / `describe(_string)` / `describe(_)` behave
identically to the fully-specified version — the only observable gap is
that two clauses with genuinely overlapping domains *and* equal specificity
(e.g. two `f(x: _)` clauses) silently resolve to "first defined wins"
instead of raising an error. This is the exact footgun the full design
exists to prevent (`docs/the language.md` §7.2) — acceptable for MVP, but
should be called out anywhere the kernel's guarantees are described to
users (docstrings, README status table), not silently shipped as if it were
the finished behavior.

### Verification

```python
kernel = Kernel()

kernel.eval('describe(x: _int)    := "an integer"')
kernel.eval('describe(x: _string) := "a string"')
kernel.eval('describe(x: _)       := "something else"')

assert kernel.eval('describe(5)') == "an integer"
assert kernel.eval('describe("hi")') == "a string"
assert kernel.eval('describe(3.14)') == "something else"

kernel.eval('sum_all(x: __) := fold(plus, 0, x)')
assert kernel.eval('sum_all(1, 2, 3)') == 6
```

- `pytest tests/test_match.py tests/test_dispatch.py` passes
- Specificity examples from language doc §7 work
- Declaration-order tiebreak verified explicitly (two same-score disjoint
  clauses resolve by domain as before; two same-score *overlapping* clauses
  resolve by order, with a test asserting this is the current — not final —
  behavior)

---

## Phase 4: Minimal Rewriting (`/.` over evaluated data only)

**Goal:** `ReplaceAll` for data rewriting. No `Hold`/`ReleaseHold`, no held-code capture.

### Files to create

```
minimatic/rewrite.py
tests/test_rewrite.py
```

### rewrite.py

```python
def replace_all(value, rules):
    """Apply rules (list of (lhs_pattern, rhs)) to value and all sub-values.
    Rules are immediate only in MVP: RHS is evaluated once at match time.
    """
    for lhs, rhs in rules:
        if (b := match(lhs, value, {})) is not None:
            return eval(substitute(rhs, b), global_env)
    if isinstance(value, Expression):
        return value.map_args(lambda a: replace_all(a, rules))
    return value
```

**Builtin heads:**

| Head | Behavior |
|---|---|
| `ReplaceAll(expr, rules)` | Apply rules to expr (underlies `/.` sugar) |
| `Rule(lhs, rhs)` | Rule constructor |

`Hold`, `ReleaseHold`, `RuleDelayed` (`:>`) are **not** implemented in MVP —
`:>` may parse but should raise a clear "not yet implemented" error rather
than silently behaving like `->`.

### Verification

```python
kernel = Kernel()
assert kernel.eval('[1, 2, 3, 4] /. x: _ -> x^2') == [1, 4, 9, 16]
assert kernel.eval('"N/A" /. "N/A" -> 0') == 0
```

- `pytest tests/test_rewrite.py` passes

---

## Phase 5: Data + Prelude + Kernel + REPL

**Goal:** Persistent `List`, a minimal prelude, single entry point, interactive REPL.

### Files to create

```
minimatic/prelude.py
minimatic/extend.py
minimatic/kernel.py
minimatic/__main__.py
tests/test_prelude.py
```

### No separate `data.py` — `List` is just an `Expression`

The original sketch proposed a dedicated `MList` wrapper class. That turned
out to be unnecessary and actually *less* consistent with kernel doc §2.3
("values are just un-reduced-further expressions"): `[1, 2, 3]` is already
`Expression(Symbol("List"), 1, 2, 3)`, tuple-backed and immutable by
construction, and that expression IS its own normal form. A separate `MList`
type would just be a second representation for the same value with an extra
conversion boundary — exactly the kind of boundary kernel doc §2.1 argues
against. `head`/`tail`/`length`/`append`/`map`/`fold` all operate on
`Expression`s headed by `Symbol("List")` directly.

### prelude.py — register built-in heads (MVP subset)

```python
def register_prelude(kernel):
    # Arithmetic
    register_head("plus", impl_plus)
    register_head("minus", impl_minus)
    register_head("times", impl_times)
    register_head("divide", impl_divide)
    register_head("power", impl_power)

    # Comparison
    register_head("equal", impl_equal)
    register_head("less", impl_less)
    register_head("greater", impl_greater)

    # List (primitive core, enough for the flagship example)
    # NOTE: map/fold take the list first — `map(xs, f)`, `fold(xs, f, init)`
    # — see "What changed during implementation" note above.
    register_head("List", impl_list)
    register_head("length", impl_length)
    register_head("head", impl_head)
    register_head("tail", impl_tail)
    register_head("append", impl_append)
    register_head("map", impl_map)      # (list, fn)
    register_head("fold", impl_fold)    # (list, fn, initial)

    # Type predicates (needed for _int / _string blanks)
    # wired into check_type() in match.py, not exposed as separate heads yet
```

`Dict`, `filter`/`reduce`, string ops, and the full derived-prelude
(`sum`, `product`, `unique`, ...) are **deferred** — add only if a specific
demo needs them.

### extend.py — Python extension API (thin, MVP version)

```python
def register_head(name: str, fn, attributes: tuple = ()):
    """Register a Python function as a Minimatic head backed by a single
    catch-all clause. Shares the same ClauseSet/dispatch machinery as
    user-defined clauses (kernel doc §11.1) — no privileged builtins,
    even in MVP.
    """
```

### kernel.py

```python
class Kernel:
    def __init__(self):
        self.registry = Registry()
        self.global_env = Env({})
        register_prelude(self)

    def eval(self, source: str):
        return _eval(parse(source), self.global_env)
```

### __main__.py — REPL

```python
def main():
    kernel = Kernel()
    print("Minimatic REPL. Type Ctrl-D to exit.")
    while True:
        try:
            source = input("minimatic> ")
        except EOFError:
            break
        try:
            print(kernel.eval(source))
        except MinimaticError as e:
            print(f"Error: {e}")
```

### Verification — the MVP acceptance bar

```bash
$ python -m minimatic
minimatic> double(x: _int) := 2 * x
minimatic> double(21)
42
minimatic> [1, "N/A", 3, "N/A", 5] |> map(x -> x /. "N/A" -> 0) |> fold(plus, 0)
9
```

- `pytest` passes across all test modules
- Both README flagship examples run correctly through the REPL

---

## Explicitly out of scope for MVP (post-MVP backlog)

*Annotated after the fact.* This list originally read as one backlog of
deferrals. It was not: some items were later **removed from the language**,
some **shipped**, and only some are still genuinely pending. Conflating the
three is what let the design docs drift, so they are split here.

**Removed — not coming back** (proposal 001):

- `overlaps()` / `implies()` ambiguity detection, `AmbiguousClauseError` —
  §2.1. Overlapping same-specificity clauses resolve by declaration order.
- `Flat` / `Orderless` attributes and canonicalization — §2.3.
- Comprehensive ambiguity test matrix — moot with the check gone.
- The `Ok` half of `Ok`/`Err`, and with it `is_ok` / `map_ok` / `and_then`
  — §2.5. Success is the value itself.

**Shipped since:**

- The `Err` result type and combinators (`catch`, `recover`, `finally`,
  `unwrap`, `unwrap_err`, `is_err`) with pipe short-circuiting.
- Self-hosting: the derived list layer *can* be written in Minimatic today
  (`docs/capabilities-and-roadmap.md` §2.1), though recursion depth caps it
  at a few hundred elements.

**Still pending:**

- `Dict` and its derived operations.
- The rest of the derived prelude (`sort_by`, `group_by`, the functional
  combinators, the string layer).
- Performance/benchmarking.

These map directly onto the original full design's Phases 4–6 and 9–10 in
the prior version of this document; nothing about the target architecture
has changed, only what ships first.

---

## Dependency graph (MVP)

```
Phase 0 (AST + errors)
  └─→ Phase 1 (Lexer/Parser)
        └─→ Phase 2 (Env + Eval)
              └─→ Phase 3 (Match + Hybrid Dispatch)
                    └─→ Phase 4 (Minimal Rewrite)
                          └─→ Phase 5 (Data + Prelude + Kernel + REPL)
```

Strictly linear for MVP — the full design's parallelizable Phases 3–6 collapse
because Attributes/Ok-Err/full-rewrite are deferred rather than built alongside.

## File manifest (MVP)

```
minimatic/
  __init__.py           # exports Kernel, register_head
  __main__.py           # REPL entry point
  ast/
    __init__.py
    symbol.py            # existing
    expression.py        # existing
    atoms.py             # existing
    patterns.py          # new: Blank, BlankSeq, BlankNullSeq, PatternBind
  attributes.py          # existing
  lexer.py
  parser.py
  env.py
  eval.py
  registry.py
  match.py
  dispatch.py
  rewrite.py
  prelude.py
  extend.py
  kernel.py
  markdown.py           # extracts ```minimatic / ```mmt fenced blocks from .md files
  errors.py

tests/
  __init__.py
  conftest.py
  test_ast.py
  test_lexer.py
  test_parser.py
  test_env.py
  test_eval.py
  test_match.py
  test_dispatch.py
  test_rewrite.py
  test_prelude.py
  test_markdown.py
  test_kernel.py

pyproject.toml
IMPLEMENTATION_PLAN.md  # this file
```

## Status: MVP complete, plus Markdown-as-script support

All phases above are implemented; `uv run pytest` passes (82 tests), and
both README flagship examples run correctly through `python -m minimatic`.
No `data.py` was needed (see note above) and `result.py` (`Ok`/`Err`) was
never started — fully deferred per "Explicitly out of scope for MVP", not
partially built.

Added after the MVP milestone: `parser.parse_all()` (parses any number of
top-level statements, not just one — statements are self-delimiting, so no
separator is needed even across a multi-line `|>` chain), `Kernel.run()`
and a reworked `Kernel.eval_file()` (runs a script; a `.md`/`.markdown` path
is read as fenced ```minimatic / ```mmt code blocks, each block a chunk of
the script, run in document order against the same kernel — see
`minimatic/markdown.py`), and a `python -m minimatic <path>` CLI mode that
runs a file instead of opening the REPL. This makes "a Minimatic script can
just be a Markdown document" a real, tested capability, not just a
convention implied by the design docs' code-fenced examples.

### Control flow (`if`, `switch`, `which`, `for`, `each`, `;`)

Implemented as ordinary registered heads, per `docs/the language.md` §4's
explicit design goal — no hard-coded `if`/`switch` case in the evaluator.
Branches are skipped by *not evaluating* the unchosen argument, via each
head's own Hold attributes (`if`/`Range` etc. use the exact same mechanism
`Lambda`/`SetDelayed` already use):

- `if(cond, then, else)` — `HoldRest`; `switch`/`which` are `HoldAll` and
  evaluate their own cases/conditions one at a time via `ctx.eval`, so
  only the winning branch and the cases/conditions actually checked ever
  run.
- `for(list, fn)` / `each(list, fn)` — apply `fn` to every element for
  effect and return `Null` (`None`), unlike `map` which collects results.
- `Range` (`a..b` sugar) — half-open, `0..5` → `[0,1,2,3,4]`, per
  `docs/the language.md` §6.2. Required adding a `..` precedence level to
  the parser (between comparison and additive).
- `(stmt1; stmt2; ...)` desugars to `CompoundExpression`, parsed only
  inside parens (matching the one place the design docs show it). No
  special evaluation needed: ordinary left-to-right argument evaluation
  already runs each statement in order for effect; the builtin just keeps
  the last value.
- `print(value)` — the minimum needed to make any of the above
  observable; returns `Null`.

**Two bugs found and fixed while wiring this up, both now covered by
tests:**
1. `Kernel.run`/`eval_file` returned a fully-materialized list, so the CLI
   only started echoing results *after* the whole file had already run —
   any `print` side effects fired before any echoed result, scrambling
   output order relative to the source. Fixed by adding generator
   variants (`run_iter`, `eval_file_iter`) that yield each result the
   instant it's produced; the CLI uses those, `run`/`eval_file` still
   return plain lists for embedding use.
2. The CLI/REPL now skip echoing `Null` (`None`) results (matching how a
   Python REPL doesn't echo `None`) — otherwise every `print(...)` call
   would visibly double-print its value once from the side effect and
   once from the echoed return value.

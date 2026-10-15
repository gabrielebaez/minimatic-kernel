# Value identity is type-strict at every level

Minimatic has one rule for whether two values are the same value, and every place that asks uses it: `equal`/`==`, `switch`, literal patterns, `Dict` keys, the `//.` fixpoint test, and Python-level `Expression.__eq__`. The rule is type-strict all the way down. `1`, `1.0` and `true` are different values, and so are `[1]`, `[1.0]` and `[true]`. We chose this because the matcher and `Dict` keys were already type-strict, while `equal` was strict only at the top level and lax inside lists. As a result `equal([1], [1.0])` was true even though a dict held `[1]` and `[1.0]` as two separate keys, and a clause for `f([1.0])` did not match `f([1])`.

## Considered options

- **Numeric equality (`1 == 1.0`)**, as in Python and Wolfram. Rejected because `Dict` keys and patterns would then have to merge `1` and `1.0`, so a key written as an integer could overwrite one written as a real, and an integer literal pattern would match reals. Code that wants a numeric comparison can convert explicitly.
- **Strict at the top level only**, which was the previous `equal`. Rejected because it is the inconsistency this decision removes.

## Consequences

- Closures compare their parameter and body structurally and their captured scope by object identity. They cannot be `Dict` keys.
- Python-level `==` on expressions follows the same rule, so host code and tests cannot see a laxer equality than the language does.

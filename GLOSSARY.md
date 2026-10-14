# Minimatic kernel

The parser, evaluator, dispatch and rewriting machinery behind the Minimatic language: everything between source text and a value.

## Language

### Heads and definitions

**Head**:
The name in call position of an expression; every value has one, and every callable behaviour is attached to one.
_Avoid_: function name, operator

**Clause**:
One definition attached to a head: argument patterns, an optional guard, and a body, together with the scope it was defined in.
_Avoid_: overload, method, rule (a rule is for `/.`)

**Head application**:
Applying a callable value (a head or a closure) to arguments, however the call was reached: written out, passed as a value, curried, or piped.
_Avoid_: dispatch (that is only the clause-selection step), invocation

**Closure**:
The value a lambda evaluates to: a parameter, a body, and the scope it was created in.
_Avoid_: lambda (that is the syntax), function object

### Values

**Value identity**:
The single rule for whether two values are the same value: type-strict at every level, so `1`, `1.0` and `true` are three different values, and so are `[1]`, `[1.0]` and `[true]`.
_Avoid_: equality (ambiguous with numeric equality), structural equality

**Err**:
A value representing an expected, routine failure, as opposed to a kernel exception for a programming mistake.
_Avoid_: error (ambiguous with exceptions), failure

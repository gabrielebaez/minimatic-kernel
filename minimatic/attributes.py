"""
Attributes - Evaluation attribute symbols.

Attributes modify how expressions are evaluated. They control:
    - Argument evaluation (Hold attributes)
    - Structural transformations (Listable)
    - Protection from modification
    - Numeric behavior

All attributes are Symbols, created at module load time.

Note: `Flat` and `Orderless` are deliberately absent — they were removed
from the language by docs/proposal-001-dispatch-results-and-pipes.md §2.3.
Their only real payoff is pattern matching over arithmetic trees, which
belongs to the deferred symbolic-rewriting layer; variadic arity and
ordinary evaluation of `1 + 2 + 3` never depended on them. Do not
reintroduce either without revisiting that decision.

Usage:
    from minimatic.attributes import HoldAll, Listable

    # Attributes belong to heads in the registry, not on individual expressions.
    # The evaluator consults the registry to determine hold/threading behavior.
    registry.attributes["MyMacro"] = {HoldAll}
"""

from .ast.symbol import Symbol

# PROTECTION ATTRIBUTES

Protected = Symbol("Protected")
"""Prevents modification of the symbol's definitions."""

ReadProtected = Symbol("ReadProtected")
"""Hides the symbol's definitions from inspection (e.g., Definition, ??)."""

Locked = Symbol("Locked")
"""Prevents any changes to the symbol's attributes."""

Constant = Symbol("Constant")
"""Marks the symbol as a mathematical constant (e.g., Pi, E)."""

Temporary = Symbol("Temporary")
"""Symbol will be automatically removed when no longer referenced."""


# HOLD ATTRIBUTES (Evaluation Control)

Hold = Symbol("Hold")
"""
Don't evaluate the expression.

Example:
    Hold[1 + 1] keeps the expression unevaluated as Hold[1 + 1].
"""

HoldAll = Symbol("HoldAll")
"""
Don't evaluate any arguments.

Example:
    HoldAll[f[1+1]] keeps f[1+1] unevaluated.
"""

HoldFirst = Symbol("HoldFirst")
"""
Don't evaluate the first argument.

Example:
    HoldFirst[Set[x, 1+1]] keeps x unevaluated.
"""

HoldRest = Symbol("HoldRest")
"""
Don't evaluate arguments after the first.

Example:
    HoldRest[f[x, 1+1]] evaluates x but keeps 1+1 unevaluated.
"""

HoldAllComplete = Symbol("HoldAllComplete")
"""
Completely prevent all evaluation, including head evaluation.

Example:
    HoldAllComplete[1+1] keeps 1+1 completely unevaluated.
"""

SequenceHold = Symbol("SequenceHold")
"""
Prevent Sequence flattening.

Example:
    SequenceHold[f[Sequence[a, b]]] keeps the Sequence unevaluated.
"""

# STRUCTURAL ATTRIBUTES

OneIdentity = Symbol("OneIdentity")
"""
A single-argument expression equals its argument for pattern matching.

Example:
    Plus has OneIdentity, so Plus[x] matches patterns expecting just x.
"""

Listable = Symbol("Listable")
"""
Automatically threads over List arguments.

Example:
    Sin has Listable, so Sin[{a, b, c}] → {Sin[a], Sin[b], Sin[c]}
"""


# RESULT ATTRIBUTES

ResultAware = Symbol("ResultAware")
"""
The head may receive an `Err` value through a pipe.

By default `a |> f` skips `f` entirely when `a` is an `Err`, so ordinary
functions never need a hand-written error passthrough. Heads marked
`ResultAware` opt out of that skip because observing the error *is* their
job: the result combinators (`is_err`, `catch`, `recover`, ...), and the
inspectors (`print`, `Head`, `Args`) — without which a failing pipeline
could not be debugged or examined.

Example:
    Err("IOError", "...") |> length     -> the Err, length never called
    Err("IOError", "...") |> is_err     -> True
"""


# FUNCTION TYPE ATTRIBUTES

NumericFunction = Symbol("NumericFunction")
"""
Returns numeric values when given numeric arguments.

This attribute is used by NumericQ and related predicates to determine
if an expression should be considered numeric.

Example:
    Sin has NumericFunction, so NumericQ[Sin[1]] is True.
"""

Stub = Symbol("Stub")
"""
The symbol needs to be loaded from a package.

When a stub symbol is encountered, the system attempts to auto-load
the package that defines it.
"""


# ATTRIBUTE SETS (for convenience)

STRUCTURAL_ATTRIBUTES = frozenset(
    {
        OneIdentity,
        Listable,
    }
)
"""All attributes that affect expression structure."""

PROTECTION_ATTRIBUTES = frozenset(
    {
        Protected,
        ReadProtected,
        Locked,
        Constant,
        Temporary,
    }
)
"""All attributes related to symbol protection."""

HOLD_ATTRIBUTES = frozenset(
    {
        Hold,
        HoldAll,
        HoldFirst,
        HoldRest,
        HoldAllComplete,
        SequenceHold,
    }
)
"""All attributes related to evaluation control."""

ALL_ATTRIBUTES = (
    STRUCTURAL_ATTRIBUTES
    | PROTECTION_ATTRIBUTES
    | HOLD_ATTRIBUTES
    | {NumericFunction, Stub, ResultAware}
)
"""All defined attributes."""


# UTILITY FUNCTIONS


def is_attribute(sym: Symbol) -> bool:
    """
    Check if a symbol is a known attribute.

    Args:
        sym: The symbol to check.

    Returns:
        True if sym is a recognized attribute symbol.
    """
    return sym in ALL_ATTRIBUTES


def holds_all(attrs: frozenset[Symbol]) -> bool:
    """Check if attributes indicate all arguments should be held."""
    return bool(attrs & {Hold, HoldAll, HoldAllComplete})


def is_listable(attrs: frozenset[Symbol]) -> bool:
    """Check if Listable attribute is set."""
    return Listable in attrs


def has_attribute(attrs: frozenset[Symbol], attr: Symbol) -> bool:
    """Check if a specific attribute is present."""
    return attr in attrs

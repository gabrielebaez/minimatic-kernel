"""
Patterns - Pattern node types used in clause heads and `/.` rule LHS.

These are a distinct, separate vocabulary from ordinary values: they never
appear as the result of evaluation, only as the static shape a clause
pattern or rewrite-rule LHS is parsed into. `match.py` matches these against
ordinary Elements (Symbol | Expression | atom).

Literal values, Symbols, and Expressions all double as their own patterns
(matching themselves / structurally) — no wrapper type needed for those.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Blank:
    """`_` (untyped) or `_int` / `_string` / ... (typed) — matches exactly one value."""

    type_tag: str | None = None

    def __str__(self) -> str:
        return f"_{self.type_tag}" if self.type_tag else "_"


@dataclass(frozen=True)
class BlankSeq:
    """`__` (typed: `__int`) — matches one-or-more consecutive arguments."""

    type_tag: str | None = None

    def __str__(self) -> str:
        return f"__{self.type_tag}" if self.type_tag else "__"


@dataclass(frozen=True)
class BlankNullSeq:
    """`___` (typed: `___int`) — matches zero-or-more consecutive arguments."""

    type_tag: str | None = None

    def __str__(self) -> str:
        return f"___{self.type_tag}" if self.type_tag else "___"


@dataclass(frozen=True)
class PatternBind:
    """`name: pattern` — binds `name` to whatever `pattern` matches, if it matches."""

    name: str
    pattern: object

    def __str__(self) -> str:
        return f"{self.name}: {self.pattern}"


@dataclass(frozen=True)
class Alternatives:
    """`p1 | p2 | p3` — matches whatever the first matching branch matches.

    Branches are tried in written order and the first success wins, so a
    name bound only by a losing branch is simply absent from the result.
    That is not a hole to plug: only one branch can ever have matched, so
    the bindings that *do* come back are always well-typed for the branch
    that produced them.
    """

    patterns: tuple

    def __str__(self) -> str:
        return " | ".join(str(p) for p in self.patterns)


@dataclass(frozen=True)
class Condition:
    """`pattern /; guard` — matches `pattern`, then requires `guard` to be True.

    The first pattern construct whose meaning depends on *evaluating*
    something (match.py's `eval_guard`). The guard sees the bindings the
    inner pattern just produced, plus the enclosing scope.
    """

    pattern: object
    guard: object

    def __str__(self) -> str:
        return f"{self.pattern} /; {self.guard}"


# Any node that can appear in pattern position. Ordinary Symbols, atoms, and
# Expressions are also valid patterns (they match themselves / structurally),
# so this alias exists for readability at call sites, not for isinstance checks.
Pattern = Blank | BlankSeq | BlankNullSeq | PatternBind | Alternatives | Condition | object


def is_pattern_node(obj: object) -> bool:
    """True if obj is one of the dedicated pattern node types (not a plain value)."""
    return isinstance(
        obj, (Blank, BlankSeq, BlankNullSeq, PatternBind, Alternatives, Condition)
    )


def is_sequence_pattern(obj: object) -> bool:
    """True if obj is a pattern that can match a variable number of arguments.

    Deliberately not true of an `Alternatives` or `Condition` wrapping one:
    unwrapping is the caller's job (see match.py's `_match_seq`), and only
    that caller knows whether it is in a position where a sequence can be
    consumed at all.
    """
    return isinstance(obj, (BlankSeq, BlankNullSeq))

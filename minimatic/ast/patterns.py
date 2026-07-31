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


# Any node that can appear in pattern position. Ordinary Symbols, atoms, and
# Expressions are also valid patterns (they match themselves / structurally),
# so this alias exists for readability at call sites, not for isinstance checks.
Pattern = Blank | BlankSeq | BlankNullSeq | PatternBind | object


def is_pattern_node(obj: object) -> bool:
    """True if obj is one of the dedicated pattern node types (not a plain value)."""
    return isinstance(obj, (Blank, BlankSeq, BlankNullSeq, PatternBind))


def is_sequence_pattern(obj: object) -> bool:
    """True if obj is a pattern that can match a variable number of arguments."""
    return isinstance(obj, (BlankSeq, BlankNullSeq))

"""
Errors - Exception hierarchy for the Minimatic kernel.

All kernel-raised errors derive from MinimaticError so host code can catch
"any Minimatic problem" with a single except clause.

Note: AmbiguousClauseError is intentionally absent. The MVP dispatch engine
(see minimatic/dispatch.py) does not detect clause ambiguity yet — see
IMPLEMENTATION_PLAN.md.
"""

from __future__ import annotations


class MinimaticError(Exception):
    """Base class for all Minimatic kernel errors."""


class MinimaticSyntaxError(MinimaticError):
    """Raised by the lexer/parser on malformed source text."""


class UnboundSymbolError(MinimaticError):
    """Raised when a Symbol has no binding in the current environment chain."""

    def __init__(self, name: str):
        self.name = name
        super().__init__(f"unbound symbol: {name}")


class UnknownHeadError(MinimaticError):
    """Raised when an expression's head has no registered clauses."""

    def __init__(self, head: object):
        self.head = head
        super().__init__(f"unknown head: {head}")


class NoMatchingClauseError(MinimaticError):
    """Raised when no clause in a head's ClauseSet matches the call args."""

    def __init__(self, head_name: str, args: tuple):
        self.head_name = head_name
        self.args = args
        super().__init__(f"no matching clause for {head_name} with args {args!r}")


class HeadAlreadySealedError(MinimaticError):
    """Raised when define_clause is called on a ClauseSet after its first dispatch."""

    def __init__(self, head_name: str):
        self.head_name = head_name
        super().__init__(
            f"cannot add clause to '{head_name}': its clause set is sealed "
            "(already dispatched at least once)"
        )


class ArityError(MinimaticError):
    """Raised when a call's argument count cannot match any clause's pattern shape."""

    def __init__(self, head_name: str, expected: str, got: int):
        self.head_name = head_name
        self.expected = expected
        self.got = got
        super().__init__(
            f"{head_name}: expected {expected} arguments, got {got}"
        )


class MinimaticTypeError(MinimaticError):
    """Raised on a runtime type mismatch (e.g. a typed blank / builtin arg check)."""


class NotImplementedInMVPError(MinimaticError):
    """
    Raised by parsed-but-unimplemented constructs (e.g. `:>` RuleDelayed,
    `Hold`/`ReleaseHold`) so users get a clear signal instead of silently
    wrong behavior. See IMPLEMENTATION_PLAN.md for what's deferred and why.
    """

    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"'{feature}' is not implemented in the MVP kernel yet")

"""
Errors - Exception hierarchy for the Minimatic kernel.

All kernel-raised errors derive from MinimaticError so host code can catch
"any Minimatic problem" with a single except clause.

Note: AmbiguousClauseError is intentionally absent, and permanently so.
Definition-time ambiguity rejection was removed from the language rather
than deferred — overlapping clauses of equal specificity resolve by
declaration order instead. See minimatic/dispatch.py and
docs/proposal-001-dispatch-results-and-pipes.md §2.1.

The boundary between these exceptions and `Err` *values* is drawn in
minimatic/result.py: routine failure is a value, programming errors are
exceptions.
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


class RewriteLimitError(MinimaticError):
    """Raised when `//.` (ReplaceRepeated) never reaches a normal form.

    A rule set that keeps producing new output has no fixpoint to find, so
    this is a programming error in the rules, not a routine failure to
    hand back as a value. See minimatic/rewrite.py's MAX_REWRITE_PASSES.
    """

    def __init__(self, limit: int, what: str = "passes"):
        self.limit = limit
        self.what = what
        super().__init__(
            f"'//.' gave up after {limit} {what}: these rules have no normal "
            "form for this expression — every pass keeps producing something new"
        )


class NotImplementedInMVPError(MinimaticError):
    """
    Raised by parsed-but-unimplemented constructs so users get a clear
    signal instead of silently wrong behavior. Currently unused — `:>` and
    `Hold`/`ReleaseHold`, its original two occupants, both ship now — but
    kept as the established shape for the next deferral. See
    IMPLEMENTATION_PLAN.md for what remains out of scope.
    """

    def __init__(self, feature: str):
        self.feature = feature
        super().__init__(f"'{feature}' is not implemented in the MVP kernel yet")

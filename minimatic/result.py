"""
Result - the `Err` value, and the line between errors-as-values and
errors-as-exceptions.

`Err` is for **expected, routine failure**: division by zero, taking the
first element of an empty list, a parse that didn't parse. These are
values. They flow through pipelines, are matched with ordinary patterns,
and are handled with `catch`/`recover`/`unwrap`.

Kernel **exceptions** stay for **programming errors**: `UnknownHeadError`,
`UnboundSymbolError`, `NoMatchingClauseError`, `MinimaticTypeError`,
`ArityError`, `HeadAlreadySealedError`. Calling a head that doesn't exist,
or handing a string to something that needs a list, is not a routine
outcome to be composed — it is a mistake to be reported.

Drawing that line is what keeps "errors are values" from swallowing the
language's ability to say *you wrote this wrong*: without it every
mistake becomes a value that flows quietly down a pipeline and surfaces,
if at all, somewhere far from its cause.

Success is the value itself — there is no `Ok` wrapper. An ordinary
function applied through the pipe is therefore already the `map_ok` of
other designs, and a function returning value-or-`Err` already chains like
`and_then`; neither needs to exist as a head. See
docs/proposal-001-dispatch-results-and-pipes.md §2.5.

`Err` is an ordinary `Expression`, not a wrapper class. A dedicated type
would reintroduce exactly the representation boundary docs/the kernel.md
§2.1 argues against, and would stop `Head`/`Args`/patterns from working on
it like anything else.
"""

from __future__ import annotations

from .ast.expression import Expression
from .ast.symbol import Symbol

ERR = Symbol("Err")


def err(kind: str, detail=None) -> Expression:
    """Build an `Err` value.

    Always two arguments. `detail` defaults to `Null` rather than being
    omitted, so `Err(k: _, d: _)` matches every `Err` ever constructed —
    an arity mismatch in a pattern doesn't raise, it silently falls
    through to a more general clause, which is the failure mode this whole
    design exists to remove.
    """
    return Expression(ERR, kind, detail)


def is_err_value(value) -> bool:
    """True if `value` is an `Err` expression."""
    return isinstance(value, Expression) and value.head == ERR

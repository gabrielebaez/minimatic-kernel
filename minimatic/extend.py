"""
Extend - Python extension API (`register_head`).

Registered Python heads share the same ClauseSet/Registry machinery as
user-defined `:=` clauses (kernel doc §11.1) — a builtin is just a single
clause whose pattern is a catch-all sequence blank and whose body is a
Python callable instead of a Minimatic AST node.

MVP note: unlike the target design, a registered head gets exactly one
clause (no polymorphic Python-level clause sets yet) — sufficient for the
prelude, and nothing prevents extending this later without changing the
call-time dispatch machinery in dispatch.py.
"""

from __future__ import annotations

from typing import Callable

from .ast.patterns import BlankNullSeq
from .ast.symbol import Symbol
from .registry import Registry


def register_head(
    registry: Registry,
    name: str,
    fn: Callable,
    attributes: tuple = (),
    pass_ctx: bool = False,
) -> None:
    """
    Register a Python function as a Minimatic head.

    `attributes` may be Symbol instances (from minimatic.attributes) or
    their string names (e.g. "HoldAll"), matching the README's usage.
    """
    attrs = {a if isinstance(a, Symbol) else Symbol(a) for a in attributes}
    registry.set_attributes(name, attrs)
    clause_set = registry.get_or_create(name)
    clause_set.define((BlankNullSeq(),), py_fn=fn, pass_ctx=pass_ctx)

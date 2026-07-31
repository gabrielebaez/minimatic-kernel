"""
Minimatic AST - Fundamental data structures for symbolic computation.

This module provides the foundational types:
    - Symbol: Immutable symbolic identifiers
    - Expr: Immutable symbolic expressions (head + arguments)
    - Atoms: Numeric and string literals

All core types are tuple-based for immutability, hashability, and efficiency.
"""

from .atoms import (
    Atom,
    Element,
    atom_head,
    is_atom,
    is_integer,
    is_numeric,
    is_real,
    is_string,
)
from .expression import (
    Expression,
    head_of,
    is_expr,
    tail_of,
)
from .patterns import (
    Blank,
    BlankNullSeq,
    BlankSeq,
    PatternBind,
    is_pattern_node,
    is_sequence_pattern,
)
from .symbol import (
    Symbol,
    clear_symbol_cache,
    gensym,
    is_symbol,
    symbol,
)

__all__ = [
    # Symbol
    "Symbol",
    "symbol",
    "is_symbol",
    "gensym",
    "clear_symbol_cache",
    # Expression
    "Expression",
    "is_expr",
    "head_of",
    "tail_of",
    # Atoms
    "Atom",
    "Element",
    "is_atom",
    "is_integer",
    "is_real",
    "is_string",
    "is_numeric",
    "atom_head",
    # Patterns
    "Blank",
    "BlankSeq",
    "BlankNullSeq",
    "PatternBind",
    "is_pattern_node",
    "is_sequence_pattern",
]

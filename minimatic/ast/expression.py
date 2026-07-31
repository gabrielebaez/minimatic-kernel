"""
Expression - Immutable symbolic expressions.

Expressions are the compound structures of the language, consisting of:
    - head: The function/operator (Symbol or Expression)
    - tail: The arguments (tuple of Elements)

Attributes belong to heads in the registry (per §8 of the kernel design),
not to individual expressions.

Implementation:
    Expressions are implemented as a tuple subclass: (head, tail)
    This provides immutability, hashability, and memory efficiency.

Examples:
    Plus[1, 2, 3]  →  Expression(Plus, 1, 2, 3)
    f[x, y]       →  Expression(f, x, y)
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    from .atoms import Element
    from .symbol import Symbol


# EXPRESSION CLASS


class Expression(tuple):
    """
    Immutable symbolic expression.

    Structure: (head, tail)
        - head: Symbol | Expression — the function or operator
        - tail: tuple[Element, ...] — the arguments
    """

    __slots__ = ()

    def __new__(
        cls,
        head: Symbol | Expression,
        *args: Element,
    ) -> Expression:
        """
        Construct an expression.

        Args:
            head: The head of the expression (function/operator).
            *args: The arguments (tail) of the expression.

        Returns:
            New immutable Expression instance.

        Raises:
            TypeError: If head is not a Symbol or Expression.

        Examples:
            >>> Expression(Plus, 1, 2)
            Plus[1, 2]

            >>> Expression(f, x, y)
            f[x, y]
        """
        from .symbol import Symbol  # Local import to avoid circularity

        if not isinstance(head, (Symbol, Expression)):
            raise TypeError(
                f"Expression head must be Symbol or Expression, got {type(head).__name__}"
            )

        # Create the tuple: (head, tail)
        tail = tuple(args)
        return super().__new__(cls, (head, tail))

    @property
    def head(self) -> Symbol | Expression:
        """The function/operator of this expression."""
        return tuple.__getitem__(self, 0)

    @property
    def tail(self) -> tuple[Element, ...]:
        """The arguments of this expression as a tuple."""
        return tuple.__getitem__(self, 1)

    @property
    def args(self) -> tuple[Element, ...]:
        """Alias for tail — the arguments of this expression."""
        return tuple.__getitem__(self, 1)

    def __len__(self) -> int:
        """Number of arguments (tail length)."""
        return len(self.tail)

    def __iter__(self) -> Iterator[Element]:
        """Iterate over arguments."""
        return iter(self.tail)

    def __contains__(self, item: object) -> bool:
        """Check if item is in arguments."""
        return item in self.tail

    def with_head(self, new_head: Symbol | Expression) -> Expression:
        """Return new expression with different head."""
        return Expression(new_head, *self.tail)

    def with_tail(self, *new_args: Element) -> Expression:
        """Return new expression with different arguments."""
        return Expression(self.head, *new_args)

    def map_args(self, fn: Callable[[Element], Element]) -> Expression:
        """
        Apply function to each argument, return new expression.

        Args:
            fn: Function to apply to each argument.

        Returns:
            New Expression with transformed arguments.
        """
        return Expression(self.head, *(fn(arg) for arg in self.tail))

    def map_args_indexed(self, fn: Callable[[int, Element], Element]) -> Expression:
        """
        Apply function to each (index, argument) pair.

        Args:
            fn: Function taking (index, arg) and returning transformed arg.

        Returns:
            New Expression with transformed arguments.
        """
        return Expression(
            self.head, *(fn(i, arg) for i, arg in enumerate(self.tail))
        )

    def append(self, *new_args: Element) -> Expression:
        """Return new expression with arguments appended."""
        return Expression(self.head, *self.tail, *new_args)

    def prepend(self, *new_args: Element) -> Expression:
        """Return new expression with arguments prepended."""
        return Expression(self.head, *new_args, *self.tail)

    def __hash__(self) -> int:
        """Hash based on structure."""
        return hash(("Expression", self.head, self.tail))

    def __eq__(self, other: object) -> bool:
        """
        Structural equality.

        Two expressions are equal if they have the same head and tail.
        """
        if self is other:
            return True
        if not isinstance(other, Expression):
            return False
        return (
            self.head == other.head
            and self.tail == other.tail
        )

    def __repr__(self) -> str:
        """
        Detailed representation showing structure.

        Format: Head[arg1, arg2, ...]
        """
        head_str = str(self.head)
        args_str = ", ".join(_format_element(arg) for arg in self.tail)
        return f"{head_str}[{args_str}]"

    def __str__(self) -> str:
        """Human-readable representation."""
        head_str = str(self.head)
        args_str = ", ".join(_format_element(arg) for arg in self.tail)
        return f"{head_str}[{args_str}]"


# MODULE-LEVEL FUNCTIONS


def _format_element(elem: Any) -> str:
    """Format an element for display in expression representation."""
    if isinstance(elem, str):
        return repr(elem)
    return str(elem)


def is_expr(obj: object) -> bool:
    """Check if an object is an Expression."""
    return isinstance(obj, Expression)


def head_of(elem: Element) -> Symbol | Expression | type:
    """
    Get the head of any element.

    - Expression: returns the head
    - Symbol: returns Symbol("Symbol")
    - int: returns Symbol("Integer")
    - float: returns Symbol("Real")
    - str: returns Symbol("String")
    - etc.

    Args:
        elem: Any element.

    Returns:
        The head of the element.
    """
    from .atoms import atom_head
    from .symbol import Symbol

    if isinstance(elem, Expression):
        return elem.head
    if isinstance(elem, Symbol):
        return Symbol("Symbol")
    return atom_head(elem)


def tail_of(elem: Element) -> tuple:
    """
    Get the tail (arguments) of any element.

    - Expression: returns arguments tuple
    - Symbol/Atoms: returns empty tuple

    Args:
        elem: Any element.

    Returns:
        The tail of the element (empty tuple for atoms).
    """
    if isinstance(elem, Expression):
        return elem.tail
    return ()

"""
Registry - Maps head names to their ClauseSet and Attribute set.

No privileged builtins (kernel doc §11.1): register_head-registered heads
and user-defined `:=` clauses live in exactly the same ClauseSet/Registry
machinery.
"""

from __future__ import annotations

from .ast.symbol import Symbol
from .dispatch import ClauseSet


class Registry:
    def __init__(self):
        self._clause_sets: dict[str, ClauseSet] = {}
        self._attributes: dict[str, frozenset[Symbol]] = {}

    def get_or_create(self, head_name: str) -> ClauseSet:
        clause_set = self._clause_sets.get(head_name)
        if clause_set is None:
            clause_set = ClauseSet(head_name)
            self._clause_sets[head_name] = clause_set
        return clause_set

    def resolve(self, head_name: str) -> ClauseSet | None:
        return self._clause_sets.get(head_name)

    def has_head(self, head_name: str) -> bool:
        return head_name in self._clause_sets

    def set_attributes(self, head_name: str, attrs) -> None:
        self._attributes[head_name] = frozenset(attrs)

    def attributes(self, head_name: str) -> frozenset[Symbol]:
        return self._attributes.get(head_name, frozenset())

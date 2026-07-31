"""
Env - Lexical scope, a parent-linked chain of binding dicts.

Env instances are the only mutable state the MVP kernel keeps: a binding
frame's dict can be written to (by `Set`/`SetDelayed`) after creation, but
the parent chain itself never changes shape once built.
"""

from __future__ import annotations

from .errors import UnboundSymbolError


class Env:
    __slots__ = ("_bindings", "_parent")

    def __init__(self, bindings: dict | None = None, parent: "Env | None" = None):
        self._bindings: dict = dict(bindings) if bindings else {}
        self._parent = parent

    def has(self, name: str) -> bool:
        env: Env | None = self
        while env is not None:
            if name in env._bindings:
                return True
            env = env._parent
        return False

    def lookup(self, name: str):
        env: Env | None = self
        while env is not None:
            if name in env._bindings:
                return env._bindings[name]
            env = env._parent
        raise UnboundSymbolError(name)

    def set_here(self, name: str, value) -> None:
        """Bind `name` in this specific frame (used by `Set`/`SetDelayed`)."""
        self._bindings[name] = value

    def extend(self, bindings: dict) -> "Env":
        return Env(bindings, parent=self)

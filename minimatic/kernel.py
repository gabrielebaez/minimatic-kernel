"""
Kernel - Single entry point: parses and evaluates Minimatic source.
"""

from __future__ import annotations

from pathlib import Path

from .env import Env
from .eval import Evaluator
from .extend import register_head as _register_head
from .parser import parse
from .prelude import register_prelude
from .registry import Registry


class Kernel:
    def __init__(self):
        self.registry = Registry()
        self.global_env = Env()
        self.evaluator = Evaluator(self.registry)
        register_prelude(self.registry)

    def eval(self, source: str):
        tree = parse(source)
        return self.evaluator.eval(tree, self.global_env)

    def eval_file(self, path: str):
        return self.eval(Path(path).read_text())

    def register_head(self, name: str, fn, attributes: tuple = (), pass_ctx: bool = False) -> None:
        _register_head(self.registry, name, fn, attributes=attributes, pass_ctx=pass_ctx)


def register_head(kernel: Kernel, name: str, fn, attributes: tuple = (), pass_ctx: bool = False) -> None:
    """Module-level convenience mirroring the README's `register_head(...)`
    usage. Takes `kernel` explicitly (rather than an implicit global
    instance) so multiple Kernel instances stay fully independent — no
    hidden global state, consistent with the rest of the design."""
    kernel.register_head(name, fn, attributes=attributes, pass_ctx=pass_ctx)

"""
Kernel - Single entry point: parses and evaluates Minimatic source.
"""

from __future__ import annotations

from pathlib import Path

from .env import Env
from .eval import Evaluator
from .extend import register_head as _register_head
from .markdown import extract_minimatic_blocks
from .parser import parse, parse_all
from .prelude import bind_prelude_constants, register_prelude
from .registry import Registry

_MARKDOWN_SUFFIXES = (".md", ".markdown")


class Kernel:
    def __init__(self):
        self.registry = Registry()
        self.global_env = Env()
        self.evaluator = Evaluator(self.registry)
        register_prelude(self.registry)
        bind_prelude_constants(self.global_env)

    def eval(self, source: str):
        """Evaluate exactly one top-level statement."""
        return self.eval_pair(source)[1]

    def eval_pair(self, source: str):
        """`eval`, but returning `(statement, result)`.

        The CLI needs the statement to decide whether to echo the result —
        `print` now returns its argument so it composes in pipes, which
        would otherwise make a top-level `print(x)` display twice."""
        tree = parse(source)
        return tree, self.evaluator.eval(tree, self.global_env)

    def run_iter_pairs(self, source: str):
        """Generator of `(statement, result)` — see `eval_pair`."""
        for stmt in parse_all(source):
            yield stmt, self.evaluator.eval(stmt, self.global_env)

    def run_iter(self, source: str):
        """Like `run`, but a generator: yields each statement's result as
        soon as it's produced, instead of collecting them into a list
        first. This is what lets a caller (e.g. the CLI) interleave
        printing a result with whatever side effects (`print`, `for`,
        `each`, ...) that same statement or a later one causes — with
        `run`'s all-at-once list, every side effect from the *whole*
        script fires before any result gets echoed, badly scrambling
        output order."""
        for _stmt, result in self.run_iter_pairs(source):
            yield result

    def run(self, source: str) -> list:
        """Evaluate every top-level statement in `source`, in order,
        against this kernel's global environment, returning the list of
        results. Unlike `eval`, `source` may hold any number of
        statements — this is what running a *script* needs."""
        return list(self.run_iter(source))

    def eval_file_iter_pairs(self, path: str):
        """Generator of `(statement, result)` over a file — see
        `eval_pair`."""
        p = Path(path)
        text = p.read_text()
        if p.suffix.lower() in _MARKDOWN_SUFFIXES:
            for block in extract_minimatic_blocks(text):
                yield from self.run_iter_pairs(block)
        else:
            yield from self.run_iter_pairs(text)

    def eval_file_iter(self, path: str):
        """Generator version of `eval_file` — see `run_iter` for why this
        matters (output-order interleaving with side effects)."""
        for _stmt, result in self.eval_file_iter_pairs(path):
            yield result

    def eval_file(self, path: str) -> list:
        """
        Run a Minimatic source file as a script, returning the list of
        every top-level statement's result, in order.

        A `.md`/`.markdown` file is treated as a Minimatic document: each
        ```minimatic fenced code block (see `minimatic/markdown.py`) is
        its own chunk of the script, run in document order against this
        same kernel — later blocks see everything earlier blocks defined.
        Any other extension is read as plain Minimatic source and run as
        one script with no block boundaries.
        """
        return list(self.eval_file_iter(path))

    def register_head(self, name: str, fn, attributes: tuple = (), pass_ctx: bool = False) -> None:
        _register_head(self.registry, name, fn, attributes=attributes, pass_ctx=pass_ctx)


def register_head(kernel: Kernel, name: str, fn, attributes: tuple = (), pass_ctx: bool = False) -> None:
    """Module-level convenience mirroring the README's `register_head(...)`
    usage. Takes `kernel` explicitly (rather than an implicit global
    instance) so multiple Kernel instances stay fully independent — no
    hidden global state, consistent with the rest of the design."""
    kernel.register_head(name, fn, attributes=attributes, pass_ctx=pass_ctx)

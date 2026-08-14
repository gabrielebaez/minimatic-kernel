"""
Minimal reference REPL for local testing (no notebook, no persistence) —
plus a script runner: `python -m minimatic path/to/file` runs the file
instead of opening the REPL. A `.md`/`.markdown` path is read as a
Minimatic document (its ```minimatic fenced code blocks are the script,
run in order — see minimatic/markdown.py); anything else is read as plain
Minimatic source.
"""

from __future__ import annotations

import sys

from .ast.expression import Expression
from .ast.symbol import Symbol
from .errors import MinimaticError
from .kernel import Kernel

_PRINT = Symbol("print")


def _echo(stmt, result) -> None:
    # Null (None) results — from `for`/`each`, etc. — aren't echoed, the
    # same way a Python REPL doesn't print `None`.
    #
    # A top-level `print(x)` isn't echoed either: `print` returns its
    # argument so it composes in a pipe (`xs |> print |> map(f)`), which
    # would otherwise display the value twice — once as the side effect,
    # once as the result. Only the *outermost* head is checked, so
    # `xs |> print` still echoes, which is right: there the pipeline's
    # value is what was asked for.
    #
    # The value returned to Python callers (Kernel.run/eval_file) is
    # unaffected; this only governs what the CLI displays.
    if result is None:
        return
    if isinstance(stmt, Expression) and stmt.head == _PRINT:
        return
    print(result)


def run_file(path: str) -> None:
    kernel = Kernel()
    try:
        # eval_file_iter, not eval_file: yields each result as it's
        # produced so it's echoed right where it happens, interleaved with
        # any print()/for/each side effects — not batched after the fact.
        for stmt, result in kernel.eval_file_iter_pairs(path):
            _echo(stmt, result)
    except MinimaticError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def repl() -> None:
    kernel = Kernel()
    print("Minimatic REPL. Type Ctrl-D to exit.")
    while True:
        try:
            source = input("minimatic> ")
        except EOFError:
            print()
            break
        if not source.strip():
            continue
        try:
            stmt, result = kernel.eval_pair(source)
            _echo(stmt, result)
        except MinimaticError as e:
            print(f"Error: {e}")


def main() -> None:
    args = sys.argv[1:]
    if args:
        run_file(args[0])
    else:
        repl()


if __name__ == "__main__":
    main()

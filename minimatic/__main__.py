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

from .errors import MinimaticError
from .kernel import Kernel


def run_file(path: str) -> None:
    kernel = Kernel()
    try:
        for result in kernel.eval_file(path):
            print(result)
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
            result = kernel.eval(source)
            print(result)
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

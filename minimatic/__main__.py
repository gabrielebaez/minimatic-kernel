"""Minimal reference REPL for local testing (no notebook, no persistence)."""

from __future__ import annotations

from .errors import MinimaticError
from .kernel import Kernel


def main() -> None:
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


if __name__ == "__main__":
    main()

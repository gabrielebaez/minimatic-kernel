"""
Markdown - Extract ```minimatic fenced code blocks from a Markdown file.

The convention this establishes: a Minimatic script can just as well be a
Markdown document — a "minimatic .md file" is prose plus one or more
fenced code blocks tagged `minimatic` (or the `mmt` alias). Everything else
in the document (headings, prose, other languages' fences) is ignored,
exactly the way a comment would be. Each block is a self-contained chunk
of the script: a complete sequence of top-level statements, run in
document order against the same kernel (so a later block can reference a
symbol an earlier block defined).

Untagged (bare ` ``` `) fences are deliberately *not* picked up, even
though the existing design docs use them for Minimatic examples — an
explicit tag is what makes "this block is runnable code" unambiguous,
the same way `literate.py` (this repo's separate, unrelated Python
literate-programming tool) only picks up ```python / ```py.
"""

from __future__ import annotations

import re

_FENCE_START_RE = re.compile(r"^\s*```\s*(minimatic|mmt)\s*$", re.IGNORECASE)
_FENCE_END_RE = re.compile(r"^\s*```\s*$")


def extract_minimatic_blocks(markdown_text: str) -> list[str]:
    """Return the source text of each ```minimatic / ```mmt fenced block,
    in document order."""
    blocks: list[str] = []
    current: list[str] | None = None
    for line in markdown_text.splitlines():
        if current is None:
            if _FENCE_START_RE.match(line):
                current = []
            continue
        if _FENCE_END_RE.match(line):
            blocks.append("\n".join(current))
            current = None
            continue
        current.append(line)
    # An unterminated fence at EOF is silently dropped rather than raised:
    # matches the lenient, prose-tolerant spirit of reading a doc, not a
    # strict script file.
    return blocks

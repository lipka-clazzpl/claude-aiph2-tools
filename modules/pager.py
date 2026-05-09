"""Rich rendering helpers shared by the streaming display.

What's left after the interactive pager UX was removed: a markdown-vs-plain
heuristic and a TTY check. Kept here (not in `streaming_display`) so future
non-streaming render paths can reuse them.
"""

from __future__ import annotations

import sys

from rich.markdown import Markdown
from rich.text import Text


def is_paging_supported() -> bool:
    """True only when both stdin and stdout are TTYs (no pipe / no /dev/null)."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except Exception:
        return False


def _looks_markdown(text: str) -> bool:
    """Cheap heuristic: render as Markdown if any common md marker shows up."""
    markers = ("## ", "**", "```", "- ", "1. ", "> ")
    if any(m in text for m in markers):
        return True
    # Pipe-table heuristic: a divider row like "|---|---|" or "| --- | :---: |"
    # — catches tables that lack other markdown markers and would otherwise
    # render as plain text and overflow the viewport.
    for line in text.splitlines():
        stripped = line.strip()
        if "|" in stripped and "---" in stripped:
            inner = stripped.strip("|")
            if all(part.strip().replace(":", "").replace("-", "") == "" for part in inner.split("|") if part.strip()):
                return True
    return False


def _render_content(text: str):
    """Return a Rich renderable: Markdown if it looks markdown-ish, else Text."""
    if _looks_markdown(text):
        return Markdown(text)
    return Text(text)

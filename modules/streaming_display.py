"""Linear streaming response renderer for the learning agent.

``stream_into_panel`` runs a single-line spinner while consuming the agent's
event stream, then prints the markdown-rendered response inline (no Panel
border, no Live region). The conversation grows as a flat scrollback log,
which avoids every height/redraw artefact that comes with a growing Live
panel and lets the user scroll natively.
"""

from __future__ import annotations

import json
import os
from typing import AsyncIterator, Tuple

from rich.console import Console
from rich.panel import Panel

from modules.pager import _render_content, is_paging_supported


StreamEvent = Tuple[str, str]


def _trace(action: str, **fields) -> None:
    """Append one JSONL line per streamer action when TEST_STREAM_TRACE is set."""
    trace_path = os.environ.get("TEST_STREAM_TRACE")
    if not trace_path:
        return
    try:
        payload = {"action": action}
        payload.update(fields)
        with open(trace_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload) + "\n")
    except (OSError, ValueError):
        pass


async def _accumulate_only(stream_iter: AsyncIterator[StreamEvent]) -> str:
    content = ""
    async for evt in stream_iter:
        kind, payload = evt
        if kind == "text":
            content += payload
    return content


def _short(payload: str | None, limit: int = 60) -> str:
    s = (payload or "").strip().replace("\n", " ")
    return s if len(s) <= limit else s[: limit - 1] + "…"


async def stream_into_panel(
    stream_iter: AsyncIterator[StreamEvent], title: str = "Agent"
) -> str:
    """Spinner during streaming, then linear markdown render. Returns the text."""
    console = Console()

    if not is_paging_supported():
        content = await _accumulate_only(stream_iter)
        console.print(
            Panel(_render_content(content), title=title, border_style="cyan")
        )
        return content

    content = ""
    initial_msg = f"[cyan]{title}: czekam na odpowiedź…[/cyan]"
    with console.status(initial_msg, spinner="dots") as status:
        async for evt in stream_iter:
            kind, payload = evt
            if kind == "text":
                content += payload
                lines = content.count("\n") + 1
                status.update(
                    f"[cyan]{title}: pisze… ({lines} linii / {len(content)} znaków)[/cyan]"
                )
            elif kind == "tool_call":
                status.update(f"[cyan]{title}: → {_short(payload)}[/cyan]")
            elif kind == "tool_result":
                status.update(f"[cyan]{title}: ← {_short(payload)}[/cyan]")
            elif kind == "thinking":
                status.update(f"[cyan]{title}: ~ {_short(payload)}[/cyan]")

    _trace("stream_end", content_len=len(content))

    console.print(
        Panel(_render_content(content), title=title, border_style="cyan")
    )
    return content

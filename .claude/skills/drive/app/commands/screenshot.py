"""Render a tmux pane to a PNG (terminal-emulator-agnostic)."""
import time

import click

from modules import tmux
from modules.errors import DriveError
from modules.output import emit, emit_error

DEFAULT_DIR = "/tmp"


@click.command()
@click.argument("session")
@click.option(
    "--output", "-o", default=None, help="Output file path. Defaults to /tmp/<session>-<timestamp>.png."
)
@click.option("--json", "as_json", is_flag=True, help="Output JSON.")
def screenshot(session: str, output: str | None, as_json: bool):
    """Render a tmux session's pane to a PNG.

    Captures the pane buffer (with ANSI colors) via tmux and rasterizes it
    with pyte+PIL. Works on detached sessions and any terminal emulator
    (no Terminal.app dependency).
    """
    if output is None:
        ts = int(time.time())
        output = f"{DEFAULT_DIR}/{session}-{ts}.png"

    try:
        path = tmux.screenshot_session(session, output)
        emit(
            {"ok": True, "session": session, "path": path},
            json=as_json,
            human_lines=f"Screenshot saved: {path}",
        )
    except DriveError as e:
        emit_error(e, json=as_json)

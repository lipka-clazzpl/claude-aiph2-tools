#!/usr/bin/env python3
"""TTY harness for modules/streaming_display.py.

Forks a child via pty.fork() so the child has a real controlling terminal,
runs ``stream_into_panel`` on a synthetic async stream, drives keystrokes
from the parent post-stream, and asserts the trace JSONL emitted by the
streamer matches expectations.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = "/tmp/aiph2_stream_trace.jsonl"


def _stty_g() -> str:
    try:
        out = subprocess.run(
            ["stty", "-g"], capture_output=True, check=False, text=True, timeout=2
        )
        return out.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _build_child_script() -> str:
    return textwrap.dedent(
        f"""
        import asyncio, os, sys
        sys.path.insert(0, {str(REPO_ROOT)!r})
        os.environ['TEST_STREAM_TRACE'] = {TRACE_PATH!r}
        os.environ.setdefault('TERM', 'xterm-256color')
        try:
            os.unlink({TRACE_PATH!r})
        except FileNotFoundError:
            pass
        from modules.streaming_display import stream_into_panel

        async def fake_stream():
            chunks = ["# Tytul\\n\\n"]
            for i in range(60):
                chunks.append(f"Linia {{i}}\\n")
            for c in chunks:
                yield ("text", c)
                await asyncio.sleep(0.005)

        asyncio.run(stream_into_panel(fake_stream(), title="Test"))
        try:
            sys.stdout.flush()
        except Exception:
            pass
        os._exit(0)
        """
    )


def main() -> int:
    if not hasattr(os, "fork"):
        print("SKIP: pty unavailable")
        return 0

    try:
        import pty
    except ImportError:
        print("SKIP: pty unavailable")
        return 0

    try:
        os.unlink(TRACE_PATH)
    except FileNotFoundError:
        pass

    stty_before = _stty_g()
    child_script = _build_child_script()

    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvp(sys.executable, [sys.executable, "-c", child_script])
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"child execvp failed: {e}\n")
            os._exit(127)

    def send(b: bytes) -> None:
        os.write(fd, b)
        time.sleep(0.08)

    # Let the stream finish and the renderer flip into idle mode.
    time.sleep(1.0)

    # Drive post-stream keystrokes:
    #   j j  -> offset 1, 2
    #   G    -> max_offset
    #   g    -> 0
    #   q    -> exit
    send(b"j")
    send(b"j")
    send(b"G")
    send(b"g")
    send(b"q")

    try:
        time.sleep(0.3)
        while True:
            try:
                chunk = os.read(fd, 4096)
                if not chunk:
                    break
            except OSError:
                break
    except Exception:
        pass

    try:
        _, _ = os.waitpid(pid, 0)
    except ChildProcessError:
        pass

    try:
        os.close(fd)
    except OSError:
        pass

    stty_after = _stty_g()

    if not os.path.exists(TRACE_PATH):
        print(f"FAIL: trace file not written: {TRACE_PATH}")
        return 1

    trace = []
    with open(TRACE_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                trace.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    if not trace:
        print("FAIL: trace file empty")
        return 1

    # Find the stream_end marker.
    stream_end = None
    for entry in trace:
        if entry.get("action") == "stream_end":
            stream_end = entry
            break
    if stream_end is None:
        print("FAIL: no stream_end trace entry — streaming flag never flipped")
        for i, t in enumerate(trace):
            print(f"  trace[{i}] = {t}")
        return 1
    if stream_end.get("content_len", 0) <= 0:
        print(f"FAIL: stream_end content_len <= 0: {stream_end}")
        return 1
    rendered_rows = stream_end.get("rendered_rows", 0)
    if rendered_rows <= 0:
        print(f"FAIL: stream_end rendered_rows <= 0: {stream_end}")
        return 1

    # Filter out the stream_end marker; remaining entries are keystrokes.
    keys = [e for e in trace if e.get("action") != "stream_end"]
    if len(keys) < 5:
        print(f"FAIL: expected at least 5 keystroke trace entries, got {len(keys)}")
        for i, t in enumerate(trace):
            print(f"  trace[{i}] = {t}")
        return 1

    # Find offsets after each j press, the G press, the g press, the q press.
    j_entries = [e for e in keys if e["action"] == "j"]
    if len(j_entries) < 2:
        print(f"FAIL: expected 2 'j' entries, got {len(j_entries)}")
        return 1

    failures: list[str] = []

    # First two j presses should produce offsets 1, 2 — but if rendered fits in
    # one page (max_offset == 0), all clamps to 0 and the test just checks no
    # crash. With 60+ chunks plus title rows on a normal pty (24 rows), this
    # comfortably exceeds page_size, so we expect 1 then 2.
    if rendered_rows <= 0:
        failures.append("rendered_rows <= 0")
    expects_movement = rendered_rows > 1  # safe when content > 1 page

    if expects_movement:
        if j_entries[0]["offset"] != 1:
            failures.append(
                f"first 'j' offset expected 1, got {j_entries[0]['offset']}"
            )
        if j_entries[1]["offset"] != 2:
            failures.append(
                f"second 'j' offset expected 2, got {j_entries[1]['offset']}"
            )

    g_entries = [e for e in keys if e["action"] == "G"]
    if not g_entries:
        failures.append("no 'G' entry")
    else:
        if expects_movement and g_entries[-1]["offset"] <= 2:
            failures.append(
                f"'G' should jump to max_offset (>2), got {g_entries[-1]['offset']}"
            )

    g_lower = [e for e in keys if e["action"] == "g"]
    if not g_lower:
        failures.append("no 'g' entry")
    else:
        if g_lower[-1]["offset"] != 0:
            failures.append(
                f"'g' should reset offset to 0, got {g_lower[-1]['offset']}"
            )

    last = keys[-1]
    if last["action"] != "q":
        failures.append(
            f"last trace action expected 'q', got {last['action']!r}"
        )

    if failures:
        print("FAIL: streaming harness mismatches:")
        for f in failures:
            print(f"  {f}")
        print("\nFull trace:")
        for i, t in enumerate(trace):
            print(f"  trace[{i}] = {t}")
        return 1

    if stty_before and stty_after and stty_before != stty_after:
        print(
            f"FAIL: stty changed (before={stty_before[:40]}... after={stty_after[:40]}...)"
        )
        return 1

    try:
        os.unlink(TRACE_PATH)
    except FileNotFoundError:
        pass

    print(
        f"PASS: streaming harness — {len(keys)} keys, "
        f"content_len={stream_end['content_len']}, rendered_rows={rendered_rows}, "
        f"final offset={last['offset']}, stty restored"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

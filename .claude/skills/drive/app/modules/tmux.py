"""Subprocess wrappers for tmux CLI.

All tmux interaction flows through this module.
Command files import from here; they never call subprocess directly.
"""
import os
import platform
import shutil
import subprocess
import time
from dataclasses import dataclass

from modules.errors import (
    ScreenshotError,
    SessionExistsError,
    SessionNotFoundError,
    TmuxCommandError,
    TmuxNotFoundError,
)


def require_tmux() -> str:
    """Return path to tmux binary or raise TmuxNotFoundError."""
    path = shutil.which("tmux")
    if path is None:
        raise TmuxNotFoundError()
    return path


def _run(
    args: list[str], *, check: bool = True, capture: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run a tmux command. All subprocess calls are centralized here."""
    tmux = require_tmux()
    cmd = [tmux] + args
    try:
        result = subprocess.run(
            cmd, capture_output=capture, text=True, timeout=10
        )
        if check and result.returncode != 0:
            raise TmuxCommandError(cmd=args, stderr=result.stderr.strip())
        return result
    except subprocess.TimeoutExpired:
        raise TmuxCommandError(cmd=args, stderr="tmux command timed out after 10s")
    except FileNotFoundError:
        raise TmuxNotFoundError()


# --- Session operations ---


def session_exists(name: str) -> bool:
    """Check if a tmux session exists."""
    result = _run(["has-session", "-t", name], check=False)
    return result.returncode == 0


def require_session(name: str) -> None:
    """Raise SessionNotFoundError if session does not exist."""
    if not session_exists(name):
        raise SessionNotFoundError(name)


@dataclass
class SessionInfo:
    name: str
    windows: int
    created: str
    attached: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "windows": self.windows,
            "created": self.created,
            "attached": self.attached,
        }


def open_terminal_window(command: str) -> None:
    """Open a new Terminal.app window and run a command in it.

    Uses AppleScript on macOS to tell Terminal.app to execute a script.
    The new window inherits the current working directory.
    """
    if platform.system() != "Darwin":
        return  # silently skip on non-macOS
    cwd = os.getcwd()
    shell_command = f"cd '{cwd}' && {command}"
    escaped = shell_command.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            f'tell application "Terminal" to do script "{escaped}"',
        ],
        capture_output=True,
        text=True,
    )


"""Window size presets — Terminal.app column x row dimensions.

These map to tmux resize + Terminal.app AppleScript sizing so screenshots
and live sessions show the expected amount of content.

    sm   =  100 x 30     — compact, quick checks
    md   =  120 x 40     — current default
    lg   =  160 x 50     — comfortable for TUI agents
    xl   =  200 x 60     — wide, dense view
    xxl  =  240 x 75     — maximum content, demo/recording
    xxxl =  300 x 90     — ultrawide, full-screen presentation
"""

WINDOW_SIZES: dict[str, tuple[int, int]] = {
    "sm":   (100, 30),
    "md":   (120, 40),
    "lg":   (160, 50),
    "xl":   (200, 60),
    "xxl":  (240, 75),
    "xxxl": (300, 90),
}


def _resize_terminal_window(session: str, cols: int, rows: int) -> None:
    """Resize the Terminal.app window for a headed tmux session.

    Uses AppleScript to resize Terminal.app, then forces tmux to adopt
    the new dimensions. Works on macOS only.
    """
    if platform.system() != "Darwin":
        return

    tty = _get_client_tty(session)
    # Map TTY → Terminal.app window, then resize it
    # We set the window bounds to achieve roughly the right character grid.
    # Terminal.app character cell is ~7px wide x ~14px tall with default font.
    # Add padding for window chrome (~22px top, ~4px sides).
    px_w = cols * 7 + 8
    px_h = rows * 14 + 44

    script = f'''tell application "Terminal"
  set wList to every window
  repeat with w in wList
    set tabList to every tab of w
    repeat with t in tabList
      if tty of t is "{tty}" then
        set currentBounds to bounds of w
        set item 3 of currentBounds to (item 1 of currentBounds) + {px_w}
        set item 4 of currentBounds to (item 2 of currentBounds) + {px_h}
        set bounds of w to currentBounds
        return
      end if
    end repeat
  end repeat
end tell'''
    subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=5
    )
    # Give Terminal.app time to resize, then force tmux to pick up new dims
    time.sleep(0.3)


def resize_session(session: str, size: str) -> tuple[int, int]:
    """Resize a headed tmux session's Terminal window to a preset size.

    Returns (cols, rows) applied. Raises SessionNotFoundError or ValueError.
    """
    require_session(session)
    size = size.lower()
    if size not in WINDOW_SIZES:
        valid = ", ".join(WINDOW_SIZES.keys())
        raise ValueError(f"Invalid window size '{size}'. Valid sizes: {valid}")

    cols, rows = WINDOW_SIZES[size]
    _resize_terminal_window(session, cols, rows)
    return cols, rows


def create_session(
    name: str,
    *,
    window_name: str | None = None,
    start_directory: str | None = None,
    detach: bool = False,
    window_size: str | None = None,
) -> None:
    """Create a tmux session.

    By default opens a new Terminal.app window attached to the session
    so the user can watch live. Use detach=True for headless sessions.
    Use window_size to set initial terminal dimensions (sm/md/lg/xl/xxl).
    """
    if session_exists(name):
        raise SessionExistsError(name)

    if window_size and window_size.lower() not in WINDOW_SIZES:
        valid = ", ".join(WINDOW_SIZES.keys())
        raise ValueError(f"Invalid window size '{window_size}'. Valid sizes: {valid}")

    if detach:
        args = ["new-session", "-d", "-s", name]
        if window_name:
            args.extend(["-n", window_name])
        if start_directory:
            args.extend(["-c", start_directory])
        _run(args)
    else:
        # Open a new Terminal window with tmux session attached.
        # -A: attach if exists, create if not.
        tmux_cmd = f"tmux new-session -A -s {name}"
        if window_name:
            tmux_cmd += f" -n {window_name}"
        if start_directory:
            tmux_cmd += f" -c '{start_directory}'"
        open_terminal_window(tmux_cmd)
        # Wait for the session to appear (Terminal + tmux startup time)
        _wait_for_session(name, timeout=5.0)

    # Hide tmux status bar by default — cleaner screenshots and presentation
    try:
        _run(["set-option", "-t", name, "status", "off"])
    except TmuxCommandError:
        pass  # non-critical

    # Enable mouse mode so scroll wheel navigates scrollback history
    try:
        _run(["set-option", "-t", name, "mouse", "on"])
    except TmuxCommandError:
        pass  # non-critical

    # Increase scrollback buffer from default 2000 to 50000 lines
    try:
        _run(["set-option", "-t", name, "history-limit", "50000"])
    except TmuxCommandError:
        pass  # non-critical

    # Apply window size if requested (headed sessions only)
    if window_size and not detach:
        time.sleep(0.3)  # let Terminal.app settle
        resize_session(name, window_size)


def _wait_for_session(name: str, timeout: float = 5.0) -> None:
    """Poll until a tmux session exists or timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if session_exists(name):
            return
        time.sleep(0.2)
    raise TmuxCommandError(
        cmd=["new-session", "-s", name],
        stderr=f"Session '{name}' did not appear within {timeout}s",
    )


def list_sessions() -> list[SessionInfo]:
    """List all tmux sessions. Empty list if no server running."""
    result = _run(
        [
            "list-sessions",
            "-F",
            "#{session_name}\t#{session_windows}\t#{session_created_string}\t#{session_attached}",
        ],
        check=False,
    )
    if result.returncode != 0:
        return []
    sessions = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            sessions.append(
                SessionInfo(
                    name=parts[0],
                    windows=int(parts[1]),
                    created=parts[2],
                    attached=parts[3] != "0",
                )
            )
    return sessions


def _close_terminal_window(tty: str) -> None:
    """Close the Terminal.app window that owns a given TTY. Best-effort."""
    if platform.system() != "Darwin":
        return
    script = f'''tell application "Terminal"
  set wList to every window
  repeat with w in wList
    set tabList to every tab of w
    repeat with t in tabList
      if tty of t is "{tty}" then
        close w
        return
      end if
    end repeat
  end repeat
end tell'''
    subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=5
    )


def kill_session(name: str) -> None:
    """Kill a tmux session and close its Terminal.app window if headed."""
    require_session(name)
    # Before killing, find the Terminal window so we can close it after.
    tty = None
    result = _run(
        ["list-clients", "-t", name, "-F", "#{client_tty}"], check=False
    )
    if result.returncode == 0 and result.stdout.strip():
        tty = result.stdout.strip().splitlines()[0]
    _run(["kill-session", "-t", name])
    if tty:
        _close_terminal_window(tty)


# --- Pane operations ---


def resolve_target(session: str, pane: str | None = None) -> str:
    """Build a tmux target string."""
    if pane is not None:
        return f"{session}:.{pane}"
    return f"{session}:"


def send_keys(
    session: str,
    keys: str,
    *,
    pane: str | None = None,
    enter: bool = True,
    literal: bool = False,
) -> None:
    """Send keystrokes to a tmux pane."""
    require_session(session)
    target = resolve_target(session, pane)
    args = ["send-keys", "-t", target]
    if literal:
        args.append("-l")
    args.append(keys)
    _run(args)
    # When literal mode is on, "Enter" would be sent as text.
    # Send Enter as a separate non-literal key press.
    if enter:
        _run(["send-keys", "-t", target, "Enter"])


def capture_pane(
    session: str,
    *,
    pane: str | None = None,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Capture pane content (and optionally scrollback)."""
    require_session(session)
    target = resolve_target(session, pane)
    args = ["capture-pane", "-p", "-t", target]
    if start_line is not None:
        args.extend(["-S", str(start_line)])
    if end_line is not None:
        args.extend(["-E", str(end_line)])
    result = _run(args)
    return result.stdout.rstrip("\n")


# --- Screenshot operations ---


def screenshot_session(session: str, output_path: str) -> str:
    """Render a tmux pane to a PNG. Works on detached sessions.

    Captures the pane buffer with ANSI escape sequences and rasterizes it
    via pyte+PIL. Independent of the user's terminal emulator.
    """
    require_session(session)
    try:
        from modules.render import render_pane
    except ImportError as e:
        raise ScreenshotError(session, f"render dependencies missing: {e}")
    try:
        return render_pane(session, output_path)
    except TmuxCommandError as e:
        raise ScreenshotError(session, f"capture failed: {e.stderr}")
    except Exception as e:  # noqa: BLE001
        raise ScreenshotError(session, f"render failed: {e}")

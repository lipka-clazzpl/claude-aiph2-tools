---
name: drive
description: Terminal automation CLI for AI agents via tmux. Use drive to create tmux sessions, execute commands, send keystrokes, read output, poll for patterns, run commands in parallel across sessions, manage processes, and take screenshots of terminal windows. Always use --json for structured output. Triggers on terminal automation, tmux sessions, parallel execution, process management, screenshot.
---

# Drive — Terminal Automation via tmux

Drive gives you full programmatic control over tmux sessions — creating terminals, running commands, reading output, and orchestrating parallel workloads. All commands output structured JSON for reliable agent parsing.

## Variables

- **DRIVE_ROOT**: `.claude/skills/drive/app`
- **RUN_PREFIX**: `cd .claude/skills/drive/app && uv run python main.py`
- **ALIAS**: `drive` = `cd .claude/skills/drive/app && uv run python main.py`

## Instructions

- Use xl windows size by default so you can see as much of the process output as possible.
- Use the screenshot command often (5s-10s intervals) to get a constant visual feed of the terminal window to make the best changes possible.

### Prerequisites

- **tmux** must be installed: `brew install tmux`
- **Python 3.11+** with `uv` for running the CLI
- **psutil** (installed automatically via `uv run`)

### Core Principle: drive vs raw tmux

Drive wraps tmux with sentinel-based completion detection, structured JSON output, and process management. Use `drive` commands as your default. However, there are situations where running `tmux` directly is cleaner — these are called out as escape hatches throughout.

### Running Commands

All drive commands follow this pattern:

```bash
cd .claude/skills/drive/app && uv run python main.py <command> [args] --json
```

Always pass `--json` for structured, parseable output.

### session — Manage tmux sessions

```bash
drive session create worker-1 --json                          # Headed — opens Terminal.app window
drive session create worker-1 --window build --json           # Named window, headed
drive session create worker-1 --detach --json                 # Headless (no Terminal window)
drive session create worker-1 --dir /path/to/project --json   # Set working directory
drive session create worker-1 --window-size lg --json         # Create with a larger window
drive session list --json                                     # List all sessions
drive session kill worker-1 --json                            # Kill a session
drive session resize worker-1 xl --json                       # Resize existing session window
```

**Default is headed** — a new Terminal.app window opens attached to the session so you can watch live. Use `--detach` when you explicitly need a headless session.

#### Window Size Presets

Use `--window-size` on create or `drive session resize` on an existing session to control the Terminal.app window dimensions. Bigger windows show more TUI content and make better screenshots.

| Size   | Columns x Rows | Use Case                            |
| ------ | -------------- | ----------------------------------- |
| `sm`   | 100 x 30       | Compact, quick checks               |
| `md`   | 120 x 40       | Default (current standard)          |
| `lg`   | 160 x 50       | Comfortable for TUI agents          |
| `xl`   | 200 x 60       | Wide, dense view                    |
| `xxl`  | 240 x 75       | Maximum content, demo/recording     |
| `xxxl` | 300 x 90       | Ultrawide, full-screen presentation |

**tmux escape hatch — session management:**
For quick session checks or when drive isn't installed, use tmux directly:
```bash
tmux ls                                    # List sessions
tmux has-session -t worker-1 2>/dev/null   # Check if session exists (exit code)
tmux kill-session -t worker-1              # Kill a session
tmux new-session -d -s worker-1            # Create detached session
tmux attach -t worker-1                    # Attach to session interactively
```

### run — Execute command and wait for completion

Uses a sentinel protocol (`__START_<token>` / `__DONE_<token>:<exit_code>`) for reliable completion detection. The sentinel wraps your command so drive knows exactly when it finishes and what the exit code was.

```bash
drive run worker-1 "npm test" --json                     # Run and wait (default 30s timeout)
drive run worker-1 "make build" --timeout 120 --json     # Custom timeout
drive run worker-1 "ls -la" --pane 1 --json              # Target specific pane
drive run worker-1 "sleep 999" --timeout 0 --json        # No timeout (wait forever)
```

Returns: `{"ok": bool, "session": str, "command": str, "exit_code": int, "output": str}`

### send — Raw keystrokes (no completion waiting)

For interactive tools (vim, ipython, etc.) where sentinel detection would interfere. Does NOT wait for completion.

```bash
drive send worker-1 "vim file.txt" --json            # Send command + Enter
drive send worker-1 ":wq" --json                     # Send vim command
drive send worker-1 "y" --no-enter --json             # Send without pressing Enter
drive send worker-1 "C-c" --no-enter --json           # Send Ctrl+C
```

**tmux escape hatch — send-keys:**
When you need special key sequences or tmux key names that drive's literal mode escapes:
```bash
tmux send-keys -t worker-1 C-c                        # Ctrl+C (interrupt)
tmux send-keys -t worker-1 C-d                        # Ctrl+D (EOF)
tmux send-keys -t worker-1 C-z                        # Ctrl+Z (suspend)
tmux send-keys -t worker-1 Escape                     # Escape key
tmux send-keys -t worker-1 "q" Enter                  # Type q then press Enter
```

### logs — Capture pane output

Read the current visible content (and scrollback) from a tmux pane.

```bash
drive logs worker-1 --json                            # Current pane content
drive logs worker-1 --lines 500 --json                # Last 500 lines of scrollback
drive logs worker-1 --pane 1 --json                   # Specific pane
```

**tmux escape hatch — capture-pane:**
For raw capture without JSON wrapping:
```bash
tmux capture-pane -t worker-1 -p                      # Print current pane content
tmux capture-pane -t worker-1 -p -S -500              # Last 500 lines of scrollback
tmux capture-pane -t worker-1 -p -S - -E -            # Entire scrollback history
```

### poll — Wait for pattern in output

Repeatedly captures the pane and regex-searches for a pattern. Use this to wait for async events like server startup, build completion, or error messages.

```bash
drive poll worker-1 --until "BUILD SUCCESS" --json                     # Wait for pattern
drive poll worker-1 --until "ready" --timeout 60 --json                # With timeout
drive poll worker-1 --until "error|success" --interval 2.0 --json     # Custom poll interval
drive poll worker-1 --until "listening on port \\d+" --json            # Regex pattern
```

Returns: `{"ok": bool, "session": str, "pattern": str, "match": str, "content": str}`

### fanout — Parallel execution across sessions

Run the same command in multiple tmux sessions concurrently. Uses ThreadPoolExecutor with sentinel-based completion detection per session.

```bash
drive fanout "npm test" --targets worker-1,worker-2,worker-3 --json
drive fanout "git pull" --targets a1,a2,a3 --timeout 60 --json
```

Returns ordered results array matching target order.

### screenshot — Capture Terminal window as image

Take a PNG screenshot of the Terminal.app window attached to a headed tmux session. Maps session → client TTY → Terminal.app window ID → macOS `screencapture`. Requires a headed (non-detached) session on macOS.

```bash
drive screenshot worker-1 --json                              # Screenshot to /tmp/<session>-<timestamp>.png
drive screenshot worker-1 -o /tmp/my-shot.png --json          # Custom output path
```

Returns: `{"ok": bool, "session": str, "path": str}`

**IMPORTANT: Always read the screenshot image after capturing it.** The whole point of this command is to see the true visual state of the terminal via vision. After running `drive screenshot`, use the Read tool on the returned path to view the image.

```
# Pattern: screenshot → read → act
1. drive screenshot worker-1 --json        → Capture the window
2. Read the image at the returned path     → See the true visual state
3. Decide next action based on what you see
```

### proc — Process management

List, kill, inspect, and monitor processes. The agent's replacement for Activity Monitor / ps / kill.

```bash
# List
drive proc list --json                                    # All user processes
drive proc list --name node --json                        # Filter by name
drive proc list --session worker-1 --json                 # Processes in a tmux session
drive proc list --parent 12345 --json                     # Children of a PID
drive proc list --cwd /path/to/project --json             # Processes by working directory

# Kill
drive proc kill 12345 --json                              # SIGTERM → wait 5s → SIGKILL
drive proc kill --name "node" --json                      # Kill all matching name
drive proc kill 12345 --tree --json                       # Kill PID and all children
drive proc kill 12345 --force --json                      # SIGKILL immediately
drive proc kill 12345 --signal 2 --json                   # Send specific signal (SIGINT)

# Inspect
drive proc tree 12345 --json                              # Show process tree from PID
drive proc tree --session worker-1 --json                 # Process tree from session root
drive proc top --session worker-1 --json                  # Resource snapshot for session
drive proc top --pid 12345,12346 --json                   # Resource snapshot for PIDs
```

**Kill uses a two-step pattern**: SIGTERM → wait up to 5s → SIGKILL if still alive. Use `--tree` to kill a process and all its children (critical for node/Claude Code which spawn subprocesses).

**tmux escape hatch — process inspection:**
When you need quick process info without drive's overhead:
```bash
tmux list-panes -a -F "#{session_name} #{pane_pid}"       # Map sessions to PIDs
tmux list-panes -t worker-1 -F "#{pane_pid}"              # Get PID for a session
ps -p $(tmux list-panes -t worker-1 -F "#{pane_pid}") -o pid,ppid,comm,rss,etime
```

## Workflow

### Standard Pattern: Create → Run → Inspect → Cleanup

```
1. drive session create worker-1 --json           → Create a session
2. drive run worker-1 "npm install" --json         → Run commands
3. drive logs worker-1 --json                      → Inspect output
4. drive session kill worker-1 --json              → Cleanup when done
```

### Long-Running Services Pattern

```
1. drive session create server --detach --json     → Headless session
2. drive send server "npm start" --json            → Start service (don't wait)
3. drive poll server --until "listening" --json     → Wait for ready signal
4. drive logs server --lines 50 --json             → Check recent output
5. drive proc list --session server --json         → See what's running
6. drive proc kill <pid> --tree --json             → Stop service + children
7. drive session kill server --json                → Cleanup session
```

### Parallel Workload Pattern

```
1. drive session create w1 --detach --json         → Create N sessions
2. drive session create w2 --detach --json
3. drive session create w3 --detach --json
4. drive fanout "npm test" --targets w1,w2,w3 --json   → Run in parallel
5. drive fanout "exit" --targets w1,w2,w3 --json       → Cleanup all
```

### Process Cleanup Pattern

```
1. drive proc list --session worker-1 --json       → See what's running
2. drive proc kill <pid> --tree --json              → Kill process + children
3. drive proc list --name <name> --json             → Verify nothing survived
4. drive session kill worker-1 --json               → Remove session
```

## Key Rules

- **Create sessions first** — `drive session create` before running commands
- **Use `run` for commands that complete** — Waits and gives exit code + output
- **Use `send` for interactive tools** — vim, ipython, anything that doesn't "finish"
- **Use `poll` to wait for async events** — Server startup, build completion, etc.
- **Use `logs` to inspect** — Check what happened in a pane
- **Use `fanout` for parallel work** — Same command across multiple sessions
- **Use `proc` for process management** — List, kill, inspect instead of raw ps/kill
- **Use `--json` always** — Structured output for reliable parsing
- **Write output files to /tmp** — Never write generated files into the project directory
- **Clean up sessions when done** — Kill sessions you created; don't orphan them
- **Prefer screenshots for TUI agents** — When driving coding agents like `pi`, `claude`, `ipi`, or other tools with custom terminal interfaces (TUIs), prefer `drive screenshot` in addition to `drive logs` to get a true understanding of the terminal state. Raw text capture often misses formatting, progress bars, status lines, and layout that are only visible in the rendered UI. Always read the screenshot image after capturing it.

## Sentinel Protocol

Drive wraps commands with markers: `echo "__START_<token>" ; <cmd> ; echo "__DONE_<token>:$?"`

This gives:
- Reliable completion detection (no guessing when a command finishes)
- Accurate exit code capture
- Clean output extraction (only content between markers)

**tmux escape hatch — when sentinels don't work:**
Sentinels require a shell prompt. They won't work inside interactive programs (vim, less, python REPL). For those, use `drive send` + `drive logs` or `drive poll` instead of `drive run`.

If you're debugging sentinel issues or need raw tmux interaction:
```bash
# Send a command without sentinel wrapping
tmux send-keys -t worker-1 "your command" Enter

# Read output manually
tmux capture-pane -t worker-1 -p -S -100

# Wait and capture in a loop (poor man's poll)
while ! tmux capture-pane -t worker-1 -p | grep -q "PATTERN"; do sleep 1; done
```

## Error Handling

All errors return structured JSON with `{"ok": false, "error": "<code>", "message": "<details>"}`.

| Error Code               | Meaning                       | Recovery                                            |
| ------------------------ | ----------------------------- | --------------------------------------------------- |
| `tmux_not_found`         | tmux not installed            | `brew install tmux`                                 |
| `session_not_found`      | Session doesn't exist         | Create it first or check name                       |
| `session_exists`         | Session name taken            | Kill it or use a different name                     |
| `timeout`                | Command didn't finish in time | Increase `--timeout` or use `send`                  |
| `pattern_not_found`      | Poll pattern never matched    | Check regex, increase timeout                       |
| `process_not_found`      | PID/name doesn't exist        | Process may have already exited                     |
| `kill_permission_denied` | Can't signal process          | Check ownership / use sudo                          |
| `tmux_error`             | tmux command failed           | Check stderr in message field                       |
| `screenshot_error`       | Screenshot capture failed     | Session must be headed (not `--detach`), macOS only |

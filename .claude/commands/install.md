---
description: Install and verify the AIPH2 Active Learning Agent
---

# Install

Run `just install` and verify:

- `uv sync` resolves cleanly (all deps: `claude-agent-sdk`, `rich`, `python-frontmatter`, `PyYAML`, `python-docx`)
- `ANTHROPIC_API_KEY` is set in `.env` or shell env
- `from modules import learning_tools_server` succeeds (verifies the MCP server assembles all 10 tools)
- `LEARNING_DIR` resolves correctly (default `aiph2/learning/` — sibling of `learn-agent/`; override via `AIPH2_LEARNING_DIR`)

## Workflow

1. Run `just install` from `aiph2/learn-agent/` via the Bash tool.
2. Run `uv run python -c "from modules import learning_tools_server; print('mcp ok')"` — must print `mcp ok`.
3. Run `uv run python -c "from modules.sm2 import LEARNING_DIR; print(LEARNING_DIR)"` — verify the path points at the existing `aiph2/learning/` directory.
4. Run `uv run python -c "import os; assert os.environ.get('ANTHROPIC_API_KEY'), 'set ANTHROPIC_API_KEY'; print('env ok')"` — must print `env ok`.
5. Report any failure with the exact error.

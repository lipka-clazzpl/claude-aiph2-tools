---
description: Prime context for working on the AIPH2 Active Learning Agent codebase
---

# Purpose

Read the codebase for the AIPH2 Active Learning Agent — a standalone Python REPL that walks the user through AI Product Heroes 2 course materials using 5 active-learning rules, persists full-section cards into the shared `aiph2/learning/` deck via SM-2, and tracks an interest profile to weight future cards.

## Workflow

Read these files in order:

- @specs/aiph2-active-learning-agent.md
- @learn_agent.py
- @modules/__init__.py
- @modules/sm2.py
- @modules/models.py
- @modules/card_io.py
- @modules/interest.py
- @modules/pager.py
- @modules/tools.py
- @prompts/SYSTEM_PROMPT.md
- @prompts/LEARN_QUEST.md
- @aiph2/learning/manifest.md
- @aiph2/.claude/skills/learning-aiph-quests/SKILL.md

Then summarize the architecture in 5 bullets:

- **Purpose** — long-form active-learning REPL for AIPH2 with own context, Rich UI, and less-style pager
- **Modules** — `sm2` (vendored SM-2 + card I/O), `models` (Pydantic schemas), `card_io` (body builder/parser), `interest` (profile r/w + bucketing), `pager` (single-keystroke `less`-style), `tools` (10 MCP tools)
- **MCP tools** — `add_card_full`, `save_dialog_round`, `record_interest`, `read_interest_profile`, `load_quest_materials`, `due_today`, `record_review`, `list_cards`, `export_anki`, `load_learning_material`
- **Slash commands** — `/learn`, `/learn-file`, `/learn-web`, `/learn-quest`, `/due`, `/review`, `/cards`, `/interest`, `/save-anki`, `/history`, `/stats`, `/clear`, `/help`, `/exit`
- **Shared deck** — both this agent and the `learning-aiph-quests` skill write to `aiph2/learning/cards/` with the same SM-2 schema; cards are bidirectionally interoperable

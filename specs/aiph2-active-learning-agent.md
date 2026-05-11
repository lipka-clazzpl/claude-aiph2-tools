# Plan: AIPH2 Active Learning Agent (incremental learning + SM-2 + interest profile)

## Task Description

Build a **standalone Python REPL agent** in `aiph2/learn-agent/` that walks the user through AI Product Heroes 2 (AIPH2) course materials using **active learning** (5 zasad), saves **full-section incremental-learning cards** with course citations and dialog rounds (not condensed Q&A), schedules reviews via **SM-2**, and **tracks user interests** inferred from the conversation to weight future cards.

The agent is modeled on `building-specialized-agents/source/apps/custom_9_learning_agent` (Claude Agent SDK + Rich terminal REPL) but extends it on three axes:

1. **Card schema** — instead of `{question, answer, difficulty}` strings, every card is a full markdown section with frontmatter (id, source, sm2 state, priority/interest, tags) and body sections: `Kontekst`, `Sedno`, `Konkret`, `Dlaczego (Powód/Kompromis/Pułapka)`, `Szersza perspektywa`, `Cytat źródłowy` (verbatim from transcript/slides), `Runda dialogu` (the actual exchange: agent's question → user's answer → expert correction), `Pytanie sprawdzające`, `Element review` (mnemonic/follow-up for next review), `Powiązane karty`, `Notatki własne`.
2. **Storage** — cards land in the existing shared `aiph2/learning/cards/` base (not a per-app folder) so the SM-2 algorithm operates on one cross-week deck, fully compatible with the existing `learning-aiph-quests` skill scripts.
3. **Interest profile** — a writable `learning/interest-profile.md` (frontmatter list of topics with `priority: 0..100`, modeled on SuperMemo's priority queue). The agent infers interest from dwell, repeat questions, follow-ups; nudges priorities; and uses them to (a) order due cards, (b) decide whether to expand or compress card sections.

The repo is empty (`aiph2/learn-agent/` has no files yet). Structure mirrors `~/personal/lead-agents`: `justfile` with `prime`, `install`, `run` recipes, `pyproject.toml`, plus a `.claude/commands/prime.md` slash command for context priming when working on the agent itself.

**Plus a less-style pager.** The source `custom_9_learning_agent` ships a second variant (`paging_agent.py`) that auto-pages long agent responses. We vendor that pager core but **upgrade to single-keystroke navigation** (space/j → next, b/k → prev, q → quit, g/G → top/bottom, y → copy page, Y → copy all) — same UX as `less`, no Enter required. Long cards in `/review` mode also flow through the pager.

## Objective

When complete:

- `cd aiph2/learn-agent && just install && just run` boots an interactive Polish REPL with the active-learning system prompt loaded.
- Long agent responses **don't scroll past** — they enter a less-style pager (space/j next, b/k prev, q quit, g/G first/last, y copy page, Y copy all) so the user reads at their own pace.
- `/learn-quest w1d2-2026-04-22-fundamenty` reads `aiph2/weeks/.../{materials,slides,transcripts}/`, synthesizes a learning plan, and walks the user through it concept-by-concept following the 5 active-learning principles.
- Every concept covered AND every side question the user asks → automatically saved as a **full-section card** in `aiph2/learning/cards/` with verbatim source citation and the dialog round preserved.
- The agent infers interest signals (e.g. "user asked 4 follow-ups about Lovable Plan-mode", "user paused on tradeoffs") and updates `interest-profile.md`. High-priority topics get richer cards; low-priority topics get leaner ones.
- `/due`, `/review`, `/cards` operate over the existing shared deck — fully interoperable with the skill's `add_card.py`/`due.py`/`review.py`.
- Anki CSV export still available via `/save-anki` (front = question + citation; back = expert correction + element review), preserving the original tool's killer feature.

## Problem Statement

Three concrete deficits in the current setup:

**1. Original `custom_9_learning_agent` produces lossy cards.** Its `generate_flashcards` tool stores `{question, answer, topic, difficulty}` only. After a session you have the *destillate* but no way to see *what was asked, how you answered, what was corrected, or where in the source it came from*. SuperMemo's IL philosophy: when a card lapses, the citation + original context is the recovery surface — without it you re-memorize a floating fact instead of re-deriving it. Source: super-memory.com/help/read.htm (extracts/topics carry references that propagate to items).

**2. The `learning-aiph-quests` skill is a Claude Code slash command** — it runs *inside* a Claude Code conversation, burning that conversation's context and competing with other tool work. A long active-learning session deserves a dedicated process with its own model loop, its own UI, and its own session lifecycle. The user explicitly asked for a *standalone agent* with `just run`, not another skill.

**3. No interest weighting.** Both the source agent and the skill treat all concepts as equal. SuperMemo's priority queue (0-100, user-adjustable) drives ordering and tolerated forgetting index. We need a lightweight version: agent infers + user nudges, persists in `interest-profile.md`, and that priority feeds card depth + due ordering.

**4. Long responses scroll past unread.** The base `custom_9_learning_agent` (and Claude Code itself for long replies) prints the whole response at once — scrollback is the only recovery. The companion `paging_agent.py` adds a Rich-Panel pager but uses `Prompt.ask` (line input → Enter required after each keystroke), which doesn't feel like `less`. The user explicitly asked for `less`-style: space to next page, j/k for navigation, q to quit — single keystrokes, no Enter.

## Solution Approach

### Layout diagrams

**Architecture (modules + filesystem):**

```
┌──────────────────────────────────────────────────────────────────┐
│ learn_agent.py  (REPL, Rich UI, Polish, slash commands)          │
│   │                                                              │
│   ├─► ClaudeSDKClient ──► system_prompt = SYSTEM_PROMPT.md       │
│   │                       (5 zasad + IL + interest tracking)     │
│   │                       allowed_tools = [10 MCP tools + 6 std] │
│   │                                                              │
│   ├─► modules/pager.py  ◄── intercepts every long agent          │
│   │   (less-style)         response and review-mode card render  │
│   │                                                              │
│   └─► MCP server (modules/tools.py via create_sdk_mcp_server)    │
│         ├─ modules/sm2.py        (vendored, env LEARNING_DIR)    │
│         ├─ modules/card_io.py    (11-section body builder)       │
│         ├─ modules/interest.py   (profile r/w, priority math)    │
│         └─ modules/models.py     (Pydantic schemas)              │
│              │                                                   │
│              ▼  reads / writes                                   │
│   aiph2/learning/                                                │
│     ├─ cards/<id>.md          (frontmatter + 11 markdown sections)│
│     ├─ interest-profile.md    (NEW — SuperMemo-style priorities) │
│     ├─ index.json             (auto-regenerated)                 │
│     └─ exports/               (Anki CSVs)                        │
└──────────────────────────────────────────────────────────────────┘
```

**Turn flow — where the pager intercepts:**

```
 user types message at REPL prompt
        │
        ▼
 process_query() ──► ClaudeSDKClient.query(...)
        │
        ▼
 receive_response() loop:
   ├─ ToolUseBlock     ──► display_tool_use     (small panel, never paged)
   ├─ ToolResultBlock  ──► display_tool_result  (small panel, never paged)
   ├─ ThinkingBlock    ──► display_thinking     (small panel, never paged)
   └─ TextBlock        ──► append to response_parts buffer
        │
        ▼  (loop ends)
 full_response = "\n\n".join(response_parts)
 self.history.append(full_response); self.last_response = full_response
        │
        ▼
 state = pager.paged_display(full_response, title="Agent")
        │
        ├─ short text or non-TTY ──► prints full Panel, returns None ──► back to prompt
        │
        └─ long text + TTY ──► renders first page, returns PagerState
               │
               ▼
        pager.run_pager_loop(state, full_text=full_response, title="Agent")
               │  (raw mode: termios.tcgetattr → tty.setcbreak)
               │
               ▼
         ┌──── read 1 char (or escape sequence) ────┐
         │                                          │
         │   digit?  ──► count_buffer += ch         │
         │   action? ──► n = int(count_buffer or 1) │
         │               apply delta on line_offset │
         │               clamp to [0, max_offset]   │
         │               re-render page             │
         │               count_buffer = ""          │
         │   q/Esc/^C? ──► break ───────────────────┘
         │
         ▼  (always, finally:)
   restore termios; return control to REPL prompt
```

**Pager screen layout (what the user sees):**

```
╭─ Agent  [3/12  L=85/420]  count: 20 ──────────────────────────────╮
│                                                                   │
│   ## Sedno                                                        │
│   Frame zamienia sygnał (z Sense) w testowalną hipotezę.          │
│   Output: 1-3 konkurencyjne hipotezy o PRZYCZYNĘ, nie rozwiązaniu.│
│                                                                   │
│   ## Konkret / Przykład                                           │
│   Airbnb 2010 — wysoki churn hostów.                              │
│   - Naiwne Frame: "redesign dashboardu" → Konrad-style.           │
│   - Faktyczne: hosty boją się zniszczeń własności przez gości.    │
│   - Output nie-produktowy: Host Protection Insurance.             │
│                                                                   │
│   ... (page_size = terminal_height - 4 lines visible) ...         │
│                                                                   │
╰── space/f next · b prev · j/k line · d/u half · g/G · y/Y · q · ? ╯
   ▲                                                       ▲
   │                                                       │
   panel title: page N of M, current line / total lines    key hint subtitle
   "count: 20" appears while user is typing a count        (truncated on narrow terms)
```

**Count-modifier semantics (the `less` part):**

```
keystrokes:   2 0 j
               │ │ │
               │ │ └─► action: scroll down by int(count_buffer)=20 lines
               │ │     (clamps at end of document)
               │ │     count_buffer reset to ""
               │ └───► count_buffer = "20"; render shows "count: 20"
               └─────► count_buffer = "2";  render shows "count: 2"

bare j            ─► count_buffer was "" → n=1 → scroll 1 line
5 <space>         ─► n=5 → next 5 pages
1 0 0 G           ─► n=100 → jump to line 100 (clamped to last line)
5 g               ─► n=5  → jump to line 5  (same as 5G — less semantics)
bare g            ─► no count → jump to FIRST line
bare G            ─► no count → jump to LAST line
escape / unknown  ─► count_buffer = ""  (resets without acting)
```

**Slash command surface (after the change):**

```
session-level (never enter the pager directly):
  /learn <topic>          /due
  /learn-file <path>      /review
  /learn-web <url>        /cards [filter]
  /learn-quest <slug>     /interest [topic priority]
  /save-anki [name]       /history [N]   ◄── reverse-indexed: 1 = most recent response
                                              (newest-first listing; fresh pager session)
  /stats  /clear  /help  /exit

inside the pager (no slash, just keystrokes):
  space f ^F  →  next page         d ^D  →  half page down
  b ^B        →  prev page         u ^U  →  half page up
  j ↓         →  line down         g     →  first
  k ↑         →  line up           G     →  last
  y           →  copy page         Y     →  copy all
  ?           →  toggle help       q Esc →  quit pager
  0-9         →  accumulate count modifier
```

**Note: there is no `/page` command.** Re-entering pager state on a *just-finished* response is by design impossible — pager nav is per-key and only meaningful while the loop owns stdin. `/history N` is the escape hatch for *old* responses, reverse-indexed (`/history 1` = the most recent past response).



**Why a standalone agent and not just an extended skill?** Three reasons. (a) Context isolation — long teaching sessions don't compete with whatever else the user runs Claude Code for. (b) Custom UI — Rich panels for "Tool Called", "Agent", "Thinking", session stats, due-card review screens. (c) Fully scriptable from the terminal: `just run-day w1d2-2026-04-22-fundamenty` becomes a one-shot study session.

**Why share `aiph2/learning/` with the skill instead of carving a new deck?** SM-2 cross-week recall is the whole point. A card created here on day 5 should fall due during a skill-driven review on day 12. The skill's `sm2_lib.py` already operates on `learning/cards/`; we vendor a *thin copy* of that lib (so the agent has zero runtime dep on the skill scripts) but read/write the same files. Cards written by the agent are indistinguishable from cards written by `add_card.py`.

**Card schema extension — backward-compatible.** Existing skill cards (3 of them in `aiph2/learning/cards/`) have body sections: Kontekst, Sedno, Konkret, Dlaczego (Powód/Kompromis/Pułapka), Szersza perspektywa, Pytanie sprawdzające, Powiązane karty, Notatki własne. We **add three optional sections** to the body template:

- `## Cytat źródłowy` — verbatim quote from transcript/slide/docx with file:line reference (SuperMemo's "reference" propagation, on the front of the card)
- `## Runda dialogu` — `**Agent zapytał:** ...` / `**Odpowiedziałeś:** ...` / `**Korekta / dopowiedzenie:** ...` (preserves the actual learning round; addresses user's "review element również, nie tylko końcowe odpowiedzi")
- `## Element review` — what to test next time (a different angle, a mnemonic, an analogy hook). Used by `/review` mode to vary the cue across reps.

Frontmatter gets two new optional fields (skill scripts ignore unknown fields):

- `priority: 50` (0-100, default 50; lower = higher priority à la SuperMemo)
- `interest_signals: [follow-up, lingered, asked-twice]` (audit trail for why the agent set the priority)

**Interest profile — `aiph2/learning/interest-profile.md`.** Frontmatter:

```yaml
---
updated: 2026-05-09
topics:
  - name: lovable-plan-mode
    priority: 20    # high (low number = higher priority)
    signals: [3 follow-ups in w1d2, repeat ask 2026-05-08]
    last_seen: 2026-05-08
  - name: customer-curiosity
    priority: 50
    signals: [first encounter, no follow-ups]
    last_seen: 2026-05-08
---

# Notatki własne
(luźne notatki użytkownika o tym, czego chce uczyć się więcej)
```

The agent reads this on session start, weights card depth + ordering by it, and writes back when it observes signals. Manual override: user types `/interest <topic> <priority>`.

**Round preservation in `add_card_full`.** The MCP tool signature:

```python
@tool("add_card_full", "...", {
    "title": str,
    "type": str,            # concept|framework|pitfall|side-question|...
    "quest": str,
    "tags": str,            # comma-separated
    "source_path": str,     # weeks/<slug>/transcripts/transcript.md
    "source_quote": str,    # verbatim, multi-line ok
    "kontekst": str,
    "sedno": str,
    "konkret": str,
    "why_tradeoff_pitfall": str,
    "szersza_perspektywa": str,
    "runda_dialogu": str,   # Agent zapytał: ... / Odpowiedziałeś: ... / Korekta: ...
    "pytanie_sprawdzajace": str,
    "element_review": str,  # next-time variation/mnemonic
    "powiazane": str,       # bullet list of related card ids
    "priority": int,        # 0-100; default 50
    "difficulty": str,      # easy|medium|hard
})
```

`card_io.build_body(...)` assembles the markdown body in the canonical order; `sm2.write_new_card(...)` (vendored, with priority field added) handles file creation, frontmatter, and `index.json` regeneration.

**Review mode UX (informed by SuperMemo).** Citation + question always visible; expert correction + element-review hidden until user reveals. Then 0-5 grading. SM-2 schedules. This matches `super-memory.com/help/read.htm`: references render alongside the question on the front, not gated behind the answer.

**Pager — true `less` semantics, single-keystroke, with count modifier.** A new `modules/pager.py` owns terminal paging. Key flow:

1. After each agent response in `process_query`, compute `page_size = os.get_terminal_size().lines - 4`. If `len(response.splitlines()) <= page_size` → render whole thing in one Panel (no pager). Otherwise enter pager loop.
2. Pager loop reads **single keystrokes** via `termios` + `tty.setcbreak(sys.stdin.fileno())` (POSIX, fine for macOS/Linux which is the user's environment). Read with `sys.stdin.read(1)`. No Enter required. Each keystroke re-renders the panel.
3. **Cursor model:** state holds `line_offset` (0..len(lines)-1), not page index. Every action is a delta on `line_offset`. Page number for display is derived: `current_page = line_offset // page_size + 1`. This is what makes per-line scroll (`j`/`k`) and per-page scroll (`space`/`b`) coexist cleanly.
4. **Count modifier** (the `less` thing — typing `20j` scrolls exactly 20 lines):
   - Digit keys `0-9` accumulate into a `count_buffer` (string).
   - The next non-digit action key consumes the buffer as an integer multiplier and resets it. `j` alone = 1 line. `2j` = 2 lines. `20j` = 20 lines. `5 ` (five then space) = 5 pages.
   - While the buffer is non-empty, the panel subtitle shows `count: 20` so the user sees what's pending.
   - Buffer also resets on `Esc`, `q`, or any unrecognized key.
5. **Bindings** (true `less`-style, count-aware unless noted):

   | Key(s) | Action | Count? |
   |---|---|---|
   | `j`, `↓` | scroll 1 line down | yes (`Nj` = N lines) |
   | `k`, `↑` | scroll 1 line up | yes |
   | `space`, `f`, `Ctrl-F`, PgDn | next page | yes (`5 ` = 5 pages) |
   | `b`, `Ctrl-B`, PgUp | previous page | yes |
   | `d`, `Ctrl-D` | half page down | yes |
   | `u`, `Ctrl-U` | half page up | yes |
   | `g` | jump to first line; `Ng` = jump to line N (1-indexed) | yes |
   | `G` | jump to last line; `NG` = jump to line N (1-indexed) | yes |
   | `y` | copy current visible page | no |
   | `Y` | copy entire response | no |
   | `?` | toggle key-help overlay | no |
   | `q`, `Esc`, `Ctrl-C` | exit pager | no |
   | `0-9` | accumulate count | — |

   `g`/`G` semantics match `less`: identical *with* count (`5g` ≡ `5G` = line 5), differ *without* (`g` = top, `G` = bottom). Line numbers are 1-indexed and clamped to `[1, len(lines)]`.

   Arrow keys arrive as escape sequences (`\x1b[A` = up, `\x1b[B` = down, `\x1b[5~` = PgUp, `\x1b[6~` = PgDn). After reading `\x1b`, peek the next 1-3 bytes with a tiny non-blocking read (use `select.select([sys.stdin], [], [], 0.05)` so a bare Esc still exits).

6. **Non-TTY fallback:** if `sys.stdin.isatty()` is False (CI, piped, `< /dev/null`), skip the pager and print the full text — never block.
7. **Subtitle** on every render: `[N/M  L/Ltot]  space/f next · b prev · j/k line · d/u half · g/G top/bot · y/Y copy · q quit · ? help` (truncate end of hint if terminal is narrow). Append `  count: <n>` when buffer is non-empty.
8. **Wired into `/review` mode** — `Sedno + Korekta + Element review` blocks for long cards page through the same loop. Keeps mental model consistent.

**No `/page` slash command.** Pager navigation lives entirely inside the pager session — once you `q`, the response is part of `self.history` but you don't re-enter it via a slash command. Re-entering would be impractical (per-key navigation has to be in-loop, not "jump to page N from outside").

`/history [N]` **stays** with reverse indexing — `/history 1` = the **most recent** agent response, `/history 2` = the one before that, etc. (Matches "1 = what I just saw" intuition; matches shell `history` and `fc` conventions where smaller-N means more recent.) Bare `/history` lists all past responses, **newest first**, numbered to match the reverse index. Each entry shown as `<N>. <80-char preview>`. Selected entry renders through `paged_display` + `run_pager_loop` — a fresh pager session, not a resume.

We deliberately **don't** include the source paging_agent's clipboard slash commands (`/copy`, `/copy-code`, `/paste`, `/paste-ask`) or `clipboard_read`/`clipboard_write` MCP tools. Only `y/Y` inside the pager use clipboard, via a tiny `pager._copy_to_clipboard` helper (subprocess to pbcopy/xclip — no extra dep).

## Relevant Files

Use these files to complete the task:

**Read for context (do not modify):**
- `/Volumes/ADATA SC750/.../custom_9_learning_agent/learning_agent.py` — REPL skeleton, Rich UI patterns, slash command dispatch, ClaudeSDKClient setup
- `/Volumes/ADATA SC750/.../custom_9_learning_agent/paging_agent.py` — **vendor reference for the pager core** (`PagerState`, `paged_display`, `_render_page`, `extract_code_blocks`, clipboard helpers). We rewrite the input loop to single-keystroke; everything else carries over
- `/Volumes/ADATA SC750/.../custom_9_learning_agent/modules/{tools.py,models.py,__init__.py}` — MCP server pattern with `@tool` decorator and `create_sdk_mcp_server`
- `/Volumes/ADATA SC750/.../custom_9_learning_agent/prompts/{LEARNING_AGENT_SYSTEM_PROMPT.md,ACTIVE_LEARNING_FROM_FILE.md}` — original Polish active-learning prompt (we extend, not copy)
- `/Volumes/ADATA SC750/.../custom_9_learning_agent/{justfile,pyproject.toml}` — minimal justfile + pyproject pattern
- `aiph2/.claude/skills/learning-aiph-quests/SKILL.md` — workflow steps (Krok 0-6)
- `aiph2/.claude/skills/learning-aiph-quests/methodology.md` — 5 active-learning rules adapted to product/business content
- `aiph2/.claude/skills/learning-aiph-quests/supermemo-rules.md` — 15 SuperMemo rules + IL pipeline notes
- `aiph2/.claude/skills/learning-aiph-quests/templates/card.md` — base card body template (we extend)
- `aiph2/.claude/skills/learning-aiph-quests/scripts/sm2_lib.py` — **source of truth for SM-2 + Card I/O; we vendor a copy**
- `aiph2/.claude/skills/learning-aiph-quests/scripts/{add_card.py,due.py,review.py,list_cards.py}` — reference for CLI patterns we reproduce as MCP tools
- `aiph2/learning/{manifest.md,index.json,cards/*.md}` — existing deck layout & one fully-fleshed example card
- `~/personal/lead-agents/{justfile,.claude/commands/prime.md}` — reference for the install/run/prime structure

### New Files

All under `aiph2/learn-agent/`:

- `pyproject.toml` — project metadata, deps: `claude-agent-sdk`, `rich>=13`, `python-frontmatter>=1.0`, `PyYAML>=6.0`, `python-docx>=1.1` (for quest .docx parsing)
- `justfile` — recipes: `default` (list), `install` (uv sync + .env check), `run` (REPL), `run-day <slug>` (one-shot with `/learn-quest <slug>` injected), `prime` (just echoes prime command), `due`, `review`, `list`, `check`
- `README.md` — short: install, run, what it does, link to skill for the alternative path
- `.env.sample` — `ANTHROPIC_API_KEY=`, `AIPH2_LEARNING_DIR=` (override path; default = sibling `../learning/`)
- `.gitignore` — `.venv/`, `output/`, `__pycache__/`, `.env`
- `learn_agent.py` — REPL entry point (mirrors source agent; adds new slash commands)
- `modules/__init__.py` — exports
- `modules/models.py` — Pydantic: `RoundCard` (full schema), `InterestTopic`, `InterestProfile`, `SessionStats`
- `modules/sm2.py` — vendored from `sm2_lib.py`; `LEARNING_DIR` resolved via env `AIPH2_LEARNING_DIR` → fallback `Path(__file__).resolve().parents[2] / "learning"` (i.e. `aiph2/learning/`); add `priority` field to `write_new_card` extras
- `modules/card_io.py` — `build_body(round_card: RoundCard) -> str` (assembles all 11 sections in canonical order); `parse_body(text) -> dict` (best-effort, for round-trip)
- `modules/interest.py` — `read_profile() -> InterestProfile`; `record_signal(topic, signal, weight_delta)`; `set_priority(topic, priority)`; `weight_for(topic) -> float` used by tools to decide section depth
- `modules/pager.py` — vendored `PagerState`, `paged_display`, `_render_page` from source `paging_agent.py`, **plus** `run_pager_loop_singlekey(state, full_text, title)` using `termios`/`tty.setcbreak`/`sys.stdin.read(1)` for less-style nav, plus `_copy_to_clipboard(text)` (pbcopy/xclip subprocess), plus `_is_tty()` guard
- `modules/tools.py` — MCP server `learning_tools_server` with tools: `add_card_full`, `save_dialog_round` (lightweight: appends a round to existing card or stages an in-progress card), `record_interest`, `read_interest_profile`, `load_quest_materials`, `due_today`, `record_review`, `list_cards`, `export_anki`, `load_learning_material` (kept from source)
- `prompts/SYSTEM_PROMPT.md` — extends `LEARNING_AGENT_SYSTEM_PROMPT.md`: Polish, 5 zasad, IL workflow with full-round preservation, citation requirement, interest-tracking instructions, tool inventory
- `prompts/LEARN_QUEST.md` — template for `/learn-quest <slug>`: Krok 0-6 from skill, but tool-driven (call `load_quest_materials` instead of bash)
- `prompts/LEARN_FILE.md` — for `/learn-file <path>` (kept from source agent, lightly updated)
- `prompts/REVIEW_SESSION.md` — for `/review`: walk due cards one by one, hide answer, grade
- `prompts/INTEREST_SIGNALS.md` — heuristics the agent uses to detect interest (follow-ups, lingering, repeat asks across sessions)
- `.claude/commands/prime.md` — primes context for *working on the agent codebase* (not for learning); mirrors lead-agents pattern
- `.claude/commands/install.md` — one-liner that calls `just install`, mostly for parity with lead-agents
- `specs/aiph2-active-learning-agent.md` — **this plan** (already at this path after step 7)

## Implementation Phases

### Phase 1: Foundation

Files: `pyproject.toml`, `justfile`, `.env.sample`, `.gitignore`, `README.md`, empty `modules/__init__.py`, `prompts/` placeholders.

Vendor `modules/sm2.py` from the skill's `sm2_lib.py`:
- Replace the `REPO_ROOT = Path(__file__).resolve().parents[4]` line with: env-aware lookup `LEARNING_DIR = Path(os.environ.get("AIPH2_LEARNING_DIR") or Path(__file__).resolve().parents[2] / "learning")`.
- Extend `write_new_card` to accept `priority: int = 50` and put it in frontmatter.
- Keep the rest verbatim (SM2State, Card, due_cards, all_cards, export_index, slugify, make_card_id) so files written by the agent and the skill are interchangeable.

Smoke check: `uv run python -c "from modules.sm2 import SM2State, write_new_card; print(SM2State.fresh().to_dict())"`.

### Phase 2: Core Implementation

**`modules/models.py`** — define `RoundCard` Pydantic model with all 11 body sections + frontmatter fields; `InterestTopic` (name, priority 0-100, signals list, last_seen); `InterestProfile` (updated, topics list, free-text notes); `SessionStats`.

**`modules/card_io.py`** — `build_body(rc: RoundCard) -> str` produces markdown in this exact order:
```
# {title}

## Kontekst (skąd to)
{kontekst}

## Sedno
{sedno}

## Konkret / Przykład
{konkret}

## Cytat źródłowy
> {source_quote}
> — `{source_path}`

## Runda dialogu
**Agent zapytał:** {agent_q}
**Odpowiedziałeś:** {user_a}
**Korekta / dopowiedzenie:** {expert_correction}

## Dlaczego
{why_tradeoff_pitfall}

## Szersza perspektywa
{szersza_perspektywa}

## Pytanie sprawdzające (active recall)
{pytanie_sprawdzajace}

## Element review (na następną powtórkę)
{element_review}

## Powiązane karty
{powiazane}

## Notatki własne
_(puste — uzupełnij przy powtórce)_
```

Empty optional sections rendered as `_(brak)_` so the structure stays scannable.

**`modules/interest.py`** — file at `<learning_dir>/interest-profile.md`. Functions:
- `read_profile() -> InterestProfile` (creates empty file if missing)
- `record_signal(topic: str, signal: str, weight_delta: int = -5)` — weight_delta < 0 = move toward higher priority (closer to 0)
- `set_priority(topic: str, priority: int)` — manual override
- `weight_for(topic: str) -> Literal["expand","standard","compress"]` — driven by priority bucket (0-30, 31-70, 71-100)

Tools must always pass `weight_for(...)` into the system prompt context for the current concept so the agent knows whether to write expansive or compressed sections.

**`modules/tools.py`** — MCP server with these tools:

| Tool | Args | Effect |
|---|---|---|
| `add_card_full` | full RoundCard fields | builds body, calls `sm2.write_new_card`, regenerates `index.json`; returns id + path |
| `save_dialog_round` | card_id (or "staged"), agent_q, user_a, expert_correction | appends/updates "Runda dialogu" section on existing card; if "staged", buffers in memory until `add_card_full` flushes |
| `record_interest` | topic, signal, weight_delta=-5 | calls `interest.record_signal` |
| `read_interest_profile` | — | returns the profile as text for the agent |
| `load_quest_materials` | week_day_slug | reads `aiph2/weeks/<slug>/{materials,slides,transcripts}/`; for `.docx` uses `python-docx`; returns concatenated text + per-file inventory |
| `due_today` | — | wraps `sm2.due_cards()`; returns list with priority-aware ordering (lowest priority number first) |
| `record_review` | card_id, grade 0-5, note? | wraps `Card.sm2.review`, persists, regenerates index |
| `list_cards` | quest?, tag?, type?, query? | wraps `sm2.all_cards` filtered |
| `export_anki` | filename, scope (all/due/quest) | writes CSV to `<learning_dir>/exports/`: `front\tback\ttags`. Front = "Kontekst:\n{kontekst}\n\nCytat:\n{source_quote}\n\nPytanie:\n{pytanie_sprawdzajace}". Back = "{sedno}\n\nKorekta z rundy:\n{korekta}\n\nElement review:\n{element_review}". Preserves source-citation-on-front per SuperMemo |
| `load_learning_material` | file_path | kept from source agent (free-form file read for `/learn-file`) |

**`learn_agent.py`** — REPL. Same skeleton as source agent's `LearningAgentREPL` but:
- New slash commands: `/learn-quest <slug>`, `/due`, `/review`, `/cards [filter]`, `/interest [topic priority]`, `/save-anki [name]`. Keep originals: `/learn`, `/learn-file`, `/learn-web`, `/stats`, `/clear`, `/help`, `/exit`.
- Allowed tools list includes the 10 new MCP tools above plus original `Read`, `WebFetch`, `WebSearch`, `Bash`, `Glob`, `Grep`.
- Disallowed: `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Task`, `TodoWrite`, `ExitPlanMode`, `BashOutput`, `KillShell` (mirrors source).
- Model: `claude-sonnet-4-6` (same as source). REPL boot reads `AIPH2_LEARNING_DIR` from env if set.
- Review mode (`/review`): for each due card, render only Kontekst + Cytat + Pytanie sprawdzające first; then on user input → reveal Sedno + Korekta + Element review → prompt for grade 0-5 → call `record_review`.

**`prompts/SYSTEM_PROMPT.md`** — extend the original. Critical additions:
- "Po każdym konkretnym koncepcie i po każdym pytaniu pobocznym **MUSISZ** zapisać kartę używając `add_card_full`. Karta zawiera **dosłowny cytat** ze źródła (sekcja `source_quote`) i **rundę dialogu** (twoje pytanie → odpowiedź użytkownika → korekta)."
- "Na początku sesji **zawsze** wczytaj profil zainteresowań (`read_interest_profile`). Dla konceptów wysokopriorytetowych (priority 0-30) pisz **rozbudowane** sekcje (każda z why/tradeoff/pitfall pełna). Dla niskopriorytetowych (71-100) pisz **lakoniczne** karty (Sedno + Konkret + Pytanie wystarczy)."
- "Sygnały zainteresowania: użytkownik pyta o coś więcej niż raz → `record_interest(topic, '+follow-up', -5)`. Użytkownik wraca do tematu w kolejnej sesji → `-10`. Użytkownik mówi 'pomiń' / 'wystarczy' → `+15`. Zapisuj sygnały **automatycznie**, bez pytania."
- "Source citation jest **obowiązkowa**. Jeśli nie wczytałeś źródła (transkryptu/slajdu/docx), użyj `load_quest_materials` LUB `Read` zanim zapiszesz kartę. Karty bez `source_quote` są zabronione."

**`modules/pager.py`** — terminal pager with single-keystroke navigation, line-cursor model, count modifier:

```python
@dataclass
class PagerState:
    lines: list[str]
    line_offset: int = 0     # canonical cursor (0..max_offset)
    page_size: int = 40      # terminal_height - 4

    @property
    def max_offset(self) -> int:
        return max(0, len(self.lines) - self.page_size)

    @property
    def total_pages(self) -> int:
        return max(1, (len(self.lines) + self.page_size - 1) // self.page_size)

    @property
    def current_page(self) -> int:
        return self.line_offset // self.page_size + 1

    def visible(self) -> str:
        return "\n".join(self.lines[self.line_offset : self.line_offset + self.page_size])

    def scroll(self, delta_lines: int) -> None:
        self.line_offset = max(0, min(self.max_offset, self.line_offset + delta_lines))

def get_terminal_height() -> int: ...   # os.get_terminal_size().lines - 4

def is_paging_supported() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()

def paged_display(text: str, title: str = "Agent") -> Optional[PagerState]:
    # Returns None and prints whole panel if not is_paging_supported() or fits in one screen.
    # Otherwise renders first page (line_offset=0) and returns state for the loop.

def render_page(state, title, count_buffer: str = ""): ...
    # Subtitle includes [N/M  L/Ltot] and the key hint, plus "count: <n>" when buffer non-empty.

def _read_key(stdin) -> str:
    # Read 1 char. If '\x1b', try select.select with 50ms timeout to read up to 4 more chars
    # for arrow/PgUp/PgDn sequences. Returns logical key name: 'UP','DOWN','PGUP','PGDN','ESC',
    # or the raw 1-char keystroke.

def run_pager_loop(state, full_text, title="Agent") -> None:
    # try: tty.setcbreak(fd); count_buffer = ""
    #   while True:
    #     key = _read_key(sys.stdin)
    #     if key in '0123456789':
    #         count_buffer += key
    #         render_page(state, title, count_buffer); continue
    #     had_count = bool(count_buffer)
    #     n = int(count_buffer) if had_count else 1
    #     count_buffer = ""
    #     if key in (' ', 'f', '\x06', 'PGDN'):  state.scroll(+n * state.page_size)
    #     elif key in ('b', '\x02', 'PGUP'):     state.scroll(-n * state.page_size)
    #     elif key in ('d', '\x04'):             state.scroll(+n * state.page_size // 2)
    #     elif key in ('u', '\x15'):             state.scroll(-n * state.page_size // 2)
    #     elif key in ('j', 'DOWN'):             state.scroll(+n)
    #     elif key in ('k', 'UP'):               state.scroll(-n)
    #     elif key == 'g':
    #         state.line_offset = max(0, min(state.max_offset, n - 1)) if had_count else 0
    #     elif key == 'G':
    #         state.line_offset = max(0, min(state.max_offset, n - 1)) if had_count else state.max_offset
    #     elif key == 'y':                       _copy_to_clipboard(state.visible())
    #     elif key == 'Y':                       _copy_to_clipboard(full_text)
    #     elif key == '?':                       _show_help_overlay(); _read_key(sys.stdin)
    #     elif key in ('q', 'ESC', '\x03'):      break
    #     # unknown: silently reset count_buffer (already done) and re-render to clear
    #     render_page(state, title)
    # finally: termios.tcsetattr(fd, termios.TCSADRAIN, original_attrs)

def _copy_to_clipboard(text: str) -> bool:
    # subprocess to pbcopy / xclip / xsel / wl-copy. No deps.
```

**REPL wiring** (in `learn_agent.py`):

```python
# After receive_response loop:
full_response = "\n\n".join(response_parts)
self.last_response = full_response
self.history.append(full_response)

if full_response.strip():
    state = pager.paged_display(full_response, title="Agent")
    if state is not None:
        pager.run_pager_loop(state, full_text=full_response, title="Agent")
```

**Review-mode integration** — when `/review` reveals the back of a card, if the back exceeds page height, route through the same pager. Same loop, different title (e.g. `f"Back — {card.title}"`).

### Phase 3: Integration & Polish

- `prompts/LEARN_QUEST.md` — instructs the agent to call `load_quest_materials(slug)`, then propose plan via numbered list, wait for user confirmation, then loop: intuicja→definicja→konkret→why→pytanie→zapis karty. Echoes Krok 0-6 from the skill but tool-driven.
- `prompts/REVIEW_SESSION.md` — review-mode instructions: render front-only first, then back, then grade prompt.
- `prompts/INTEREST_SIGNALS.md` — heuristics table (signal → topic → weight_delta) the agent references during sessions.
- `.claude/commands/prime.md` — for someone working *on* this codebase: read `learn_agent.py`, `modules/*`, `prompts/*`, `aiph2/learning/manifest.md`, `aiph2/.claude/skills/learning-aiph-quests/SKILL.md`. Summarize architecture.
- `.claude/commands/install.md` — runs `just install` then verifies tool import, env var, and shared deck path.
- `README.md` — install (`just install`), run (`just run`), comparison table with the skill (when to use which), env vars, link to specs/.
- Validate: import smoke, sm2 round-trip, write a test card to `/tmp` with overridden `AIPH2_LEARNING_DIR`, verify it loads via `sm2.all_cards()`, verify Anki export CSV well-formed, verify no card without `source_quote` makes it through (tool-level guard).

## Team Orchestration

- I act as team lead orchestrating builders via `Task` and `TaskCreate`/`TaskUpdate`.
- The work is tightly coupled (modules → tools → REPL → prompts), so we run **two sequential builders + one validator**, with a tight handoff via the spec doc.
- I do not edit code directly; I dispatch builders and verify via the validator.

### Team Members

- Builder
  - Name: builder-core
  - Role: Build all Python code — `pyproject.toml`, `justfile`, `modules/{sm2,models,card_io,interest,pager,tools,__init__}.py`, `learn_agent.py`, `.env.sample`, `.gitignore`. Vendor `sm2_lib.py` with the env-aware `LEARNING_DIR` patch and the `priority` field. Vendor + upgrade `paging_agent.py`'s pager into `modules/pager.py` with single-keystroke (`termios`) loop. Wire MCP server with all 10 tools. REPL with all slash commands and pager integration.
  - Agent Type: general-purpose
  - Resume: true

- Builder
  - Name: builder-prompts-docs
  - Role: Build all prompts (`SYSTEM_PROMPT.md`, `LEARN_QUEST.md`, `LEARN_FILE.md`, `REVIEW_SESSION.md`, `INTEREST_SIGNALS.md`), `.claude/commands/{prime.md,install.md}`, `README.md`. Cross-checks the tool inventory in `modules/tools.py` against the system prompt's tool inventory.
  - Agent Type: general-purpose
  - Resume: true

- Validator
  - Name: validator
  - Role: Run all validation commands listed below, write a tiny e2e test that creates a card under `AIPH2_LEARNING_DIR=/tmp/aiph2-learning-test/` and verifies SM-2 round-trip, Anki CSV export, and interest-profile r/w. Report pass/fail per acceptance criterion.
  - Agent Type: general-purpose
  - Resume: false

## Step by Step Tasks

- IMPORTANT: Execute every step in order, top to bottom. Each task maps to a `TaskCreate` call. The team lead runs `TaskCreate` for all tasks first, then deploys agents per task.

### 1. Scaffold project + vendor SM-2

- **Task ID**: scaffold-and-sm2
- **Depends On**: none
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- Create `aiph2/learn-agent/{pyproject.toml, justfile, .env.sample, .gitignore}`. `pyproject.toml` deps: `claude-agent-sdk`, `rich>=13.0.0`, `python-frontmatter>=1.0`, `PyYAML>=6.0`, `python-docx>=1.1`. `requires-python = ">=3.11"`.
- Create `modules/__init__.py` (initially empty exports list).
- Vendor `modules/sm2.py` from `aiph2/.claude/skills/learning-aiph-quests/scripts/sm2_lib.py`. **Patch points:** (a) `LEARNING_DIR = Path(os.environ.get("AIPH2_LEARNING_DIR") or Path(__file__).resolve().parents[2] / "learning")`; `CARDS_DIR = LEARNING_DIR / "cards"`. (b) `write_new_card` accepts `priority: int = 50` and adds `"priority": priority` to `meta`. (c) Add `import os` at top. Everything else verbatim.
- Verify: `cd aiph2/learn-agent && uv sync && uv run python -c "from modules.sm2 import SM2State, write_new_card, all_cards; print('ok', SM2State.fresh().to_dict())"`.
- Update `MEMORY.md` index? No — this is project work, not memory.

### 2. Models + Card I/O + Interest profile

- **Task ID**: models-cardio-interest
- **Depends On**: scaffold-and-sm2
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- Create `modules/models.py` with `RoundCard`, `InterestTopic`, `InterestProfile`, `SessionStats` Pydantic models. `RoundCard` has all 11 body fields + frontmatter fields (title, type, source_path, source_quote, quest, tags, priority, difficulty).
- Create `modules/card_io.py` with `build_body(rc: RoundCard) -> str` that assembles markdown in the exact section order from Phase 2. Empty optional sections render as `_(brak)_`.
- Create `modules/interest.py`: `read_profile()`, `write_profile(p)`, `record_signal(topic, signal, weight_delta)`, `set_priority(topic, priority)`, `weight_for(topic) -> "expand"|"standard"|"compress"`. Profile file path: `<LEARNING_DIR>/interest-profile.md`. Initialize empty profile if missing.
- Verify: `uv run python -c "from modules.models import RoundCard; from modules.card_io import build_body; print(build_body(RoundCard(title='t',type='concept',source_path='x.md',source_quote='q',quest='qq',tags=['a'],kontekst='k',sedno='s',konkret='kk',why_tradeoff_pitfall='w',szersza_perspektywa='sp',runda_dialogu='rd',pytanie_sprawdzajace='ps',element_review='er',powiazane='-'))[:200])"`.

### 3. MCP tools

- **Task ID**: mcp-tools
- **Depends On**: models-cardio-interest
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- Create `modules/tools.py` exposing all 10 tools listed in Phase 2 via `@tool` decorator. Wire `learning_tools_server = create_sdk_mcp_server(...)`.
- **Critical guards:** `add_card_full` must reject empty `source_quote` and empty `pytanie_sprawdzajace` with `is_error: True`. `record_review` must reject grade not in 0-5.
- `load_quest_materials`: read `aiph2/weeks/<slug>/transcripts/transcript.md` (preferred) or `transcript-raw.md` (fallback); read all `slides/*.md`; for each `materials/*.docx` use `python-docx` to extract paragraphs. Return concatenated text capped at 80k chars with per-file inventory.
- `export_anki`: write to `<LEARNING_DIR>/exports/<filename>.csv`, tab-separated, front = kontekst+cytat+pytanie, back = sedno+korekta+element-review.
- Update `modules/__init__.py` to export `learning_tools_server`, `add_card_full`, etc.
- Verify: `uv run python -c "from modules import learning_tools_server; print('ok')"`.

### 4. Pager (less-style)

- **Task ID**: pager
- **Depends On**: scaffold-and-sm2 (only needs the project skeleton — independent from models/cardio/tools, can run in parallel with task 2 and 3)
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: true (vs models-cardio-interest and mcp-tools — pager has no module dependencies)
- Create `modules/pager.py`. Vendor clipboard backend detection from source `custom_9_learning_agent/paging_agent.py`. **Rewrite** PagerState to a line-cursor model (NOT page-index): canonical state is `line_offset` plus `page_size`; `current_page` and `total_pages` are derived. Implement:
  - `is_paging_supported() -> bool` — `sys.stdin.isatty() and sys.stdout.isatty()`
  - `_read_key(stdin) -> str` — reads 1 char; if `\x1b`, uses `select.select` with 50ms timeout to swallow arrow/PgUp/PgDn escape sequences (returns logical names `UP`/`DOWN`/`PGUP`/`PGDN`/`ESC`).
  - `run_pager_loop(state, full_text, title)` — **single-keystroke**, **count-aware** loop using `termios.tcgetattr` / `tty.setcbreak(sys.stdin.fileno())`. Restore termios in `finally`. Count buffer is a string of digits; consumed by next non-digit action; reset on Esc/q/unknown. Bindings per the table in Solution Approach. `g`/`G` are the only bindings whose **behavior changes** based on whether count was set (`less` semantics): bare `g` = top, bare `G` = bottom; `Ng` ≡ `NG` = jump to 1-indexed line N (clamped). All scroll bindings (`j`/`k`/space/`b`/`f`/`d`/`u`) multiply by count. `y`/`Y`/`?`/`q` ignore count (buffer still resets on press).
  - `_copy_to_clipboard(text) -> bool` — subprocess pbcopy/xclip/xsel/wl-copy.
  - `paged_display(text, title)` — skip pager and print whole panel if `not is_paging_supported()` OR `len(lines) <= page_size`. Otherwise render at `line_offset=0`, return `PagerState`.
  - `render_page(state, title, count_buffer="")` — subtitle: `[N/M  L=<offset+1>/<total>] space/f next · b prev · j/k line · d/u half · g/G · y/Y · q · ?` plus `  count: <n>` while buffer non-empty.
- **Verify (basic):** `uv run python -c "from modules.pager import PagerState, paged_display, is_paging_supported; s=PagerState(lines=['x']*200, page_size=40); s.scroll(20); assert s.line_offset==20; s.scroll(-1000); assert s.line_offset==0; s.scroll(1_000_000); assert s.line_offset==s.max_offset; print('cursor ok')"`
- **Verify (TTY harness):** see Validation Commands section below — uses `pty.fork()` to drive a real terminal and feed `2`,`0`,`j`,`b`,`g`,`G`,`q` to verify count modifier and clean exit.

### 5. REPL + slash commands

- **Task ID**: repl
- **Depends On**: mcp-tools, pager
- **Assigned To**: builder-core
- **Agent Type**: general-purpose
- **Parallel**: false
- Create `learn_agent.py` modeled on the source agent's `learning_agent.py`. Class `LearningAgentREPL`. Slash commands: `/learn`, `/learn-file`, `/learn-web`, `/learn-quest`, `/due`, `/review`, `/cards`, `/interest`, `/save-anki`, `/history [n]`, `/stats`, `/clear`, `/help`, `/exit`. **No `/page` command** — pager nav is per-keystroke and only meaningful inside a live loop. Each non-trivial command builds a Polish prompt and calls `process_query`.
- **Pager wiring**: in `process_query`, after the `receive_response` loop assembles `full_response` from `TextBlock`s, call `state = pager.paged_display(full_response, title='Agent')`; if `state is not None` call `pager.run_pager_loop(state, full_text=full_response, title='Agent')`. Store `self.last_response` and `self.history.append(full_response)` (history is for `/history` only; `last_response` is for diagnostics, not re-paging).
- `/history`: **reverse-indexed** (matches shell `history`/`fc` convention so "1" = what I just saw). Implementation: bare `/history` lists `self.history` newest first as `<N>. <preview>` where N is `1..len(history)` and entry at index `N` maps to `self.history[-N]`. `/history N` resolves to `self.history[-N]` (raises a friendly "Brak odpowiedzi nr N" if `N > len(history)` or `N < 1`); selected entry rendered through `paged_display` + `run_pager_loop` (fresh pager session). Out-of-range or non-numeric arg → show usage hint, no crash.
- `/review` enters review-mode loop: for each due card from `due_today`, display Kontekst+Cytat+Pytanie via Rich Panel (always paged via `paged_display` — many cards exceed terminal height), prompt user for answer, then reveal Sedno+Korekta+Element-review (also paged), prompt for grade 0-5, call `record_review`.
- Allowed tools list = the 10 MCP tools + `Read`, `WebFetch`, `WebSearch`, `Bash`, `Glob`, `Grep`. Disallowed = `Write`, `Edit`, `MultiEdit`, `NotebookEdit`, `Task`, `TodoWrite`, `ExitPlanMode`, `BashOutput`, `KillShell`.
- Update `justfile` recipes: `default` (just --list), `install` (uv sync, check ANTHROPIC_API_KEY), `run` (`CLAUDECODE= uv run python learn_agent.py`), `run-day SLUG` (one-shot with prefilled `/learn-quest SLUG`), `due` (`uv run python -c "from modules.tools import _due_today_impl; ..."`), `review`, `list`, `prime` (`echo "Run /prime in Claude Code in this dir"`), `check` (import smoke).
- Verify: `cd aiph2/learn-agent && uv run python -c "import learn_agent; print(learn_agent.LearningAgentREPL)"`.

### 6. Prompts + slash commands + README

- **Task ID**: prompts-docs
- **Depends On**: mcp-tools
- **Assigned To**: builder-prompts-docs
- **Agent Type**: general-purpose
- **Parallel**: true (can run alongside tasks 4 and 5 — prompts don't need REPL or pager to compile)
- Create `prompts/SYSTEM_PROMPT.md` extending the source `LEARNING_AGENT_SYSTEM_PROMPT.md`. Polish, 5 zasad aktywnego uczenia, IL with full-round preservation, mandatory source citation, interest tracking instructions (with explicit signal heuristics from `INTEREST_SIGNALS.md`), full tool inventory with one-line description per tool. **Adapted from skill methodology.md** (product/business framing, not coding).
- Create `prompts/LEARN_QUEST.md` (`/learn-quest <slug>`): tool-driven version of skill's Krok 0-6.
- Create `prompts/LEARN_FILE.md` (preserve source agent's, lightly adapted to mention `add_card_full` instead of `generate_flashcards`).
- Create `prompts/REVIEW_SESSION.md`: review-mode instructions, hide-then-reveal pattern.
- Create `prompts/INTEREST_SIGNALS.md`: table of heuristics → tool calls.
- Create `.claude/commands/prime.md` (for working *on* this agent's code, mirrors lead-agents pattern).
- Create `.claude/commands/install.md` (one-liner that calls `just install`).
- Create `README.md`: install/run, comparison table with `learning-aiph-quests` skill ("Use the agent for long sessions; use the skill for one-off Claude Code questions"), env vars, links.
- Verify: every prompt file references only tools that exist in `modules/tools.py`. Cross-check by grepping tool names in both directions.

### 7. End-to-end validation

- **Task ID**: validate-all
- **Depends On**: repl, prompts-docs
- **Assigned To**: validator
- **Agent Type**: general-purpose
- **Parallel**: false
- Run all commands from "Validation Commands" below.
- Write `tests/smoke_e2e.py` (one-off, can stay in repo): set `AIPH2_LEARNING_DIR=/tmp/aiph2-learning-test/`, call `add_card_full` directly with a sample RoundCard, assert the file exists with valid frontmatter (load via `frontmatter.load`), assert all 11 sections present in body, call `record_review(card_id, 4)`, assert `next_review` updated, call `export_anki`, assert CSV has 1 row with tabs.
- Write `tests/pager_tty_harness.py` — uses `pty.fork()` to run a child Python that imports `modules.pager`, calls `paged_display` on 200 lines, then `run_pager_loop`. Parent writes the keystroke sequence below to the pty fd with small delays and asserts the child's traced `line_offset` after each action matches expectations. The pager's `run_pager_loop` should append a JSONL line `{"action": "<key>", "count": N, "had_count": bool, "offset": <line_offset>}` to `os.environ["TEST_PAGER_TRACE"]` when set, so the harness can read offsets without parsing terminal output. Sequence to drive: `j` → +1; `20j` → +20; `k` → -1; ` ` (space) → +page_size; `5 ` → +5*page_size; `d` → +page_size//2; `u` → -page_size//2; bare `g` → 0; bare `G` → max_offset; `5g` → 4 (line 5, 1-indexed); `5G` → 4 (same as 5g); `999999G` → max_offset (clamped); `q` → exit 0. After exit, snapshot `stty -g` to confirm termios restoration.
- Verify card written by the agent loads cleanly via the **skill's** scripts: `cp /tmp/aiph2-learning-test/cards/*.md aiph2/learning/cards/_test_e2e.md && uv run aiph2/.claude/skills/learning-aiph-quests/scripts/list_cards.py --query _test_e2e` (then delete the test card).
- Verify guard: `add_card_full` with empty `source_quote` returns error.
- Report a pass/fail line per acceptance criterion.

## Acceptance Criteria

1. `cd aiph2/learn-agent && just install` succeeds with no errors; `uv sync` resolves all deps.
2. `just run` boots the Polish REPL banner; typing `/help` lists all 13 slash commands.
3. `uv run python -c "from modules import learning_tools_server"` succeeds.
4. `add_card_full` with a complete RoundCard writes a `.md` file in `<LEARNING_DIR>/cards/` with valid YAML frontmatter (parseable by `frontmatter.load`) and all 11 body sections present in the canonical order.
5. The same file loads cleanly via the **skill's** existing `list_cards.py`/`due.py` (full bidirectional interop).
6. `add_card_full` with empty `source_quote` returns `is_error: True` (citation guard works).
7. `record_review(id, 4)` updates `next_review`, `last_review`, `ease`, `reps` per SM-2 math (compare with skill's `review.py` output on same input).
8. `read_interest_profile` reads/creates `<LEARNING_DIR>/interest-profile.md`; `record_interest('lovable-plan-mode', '+follow-up', -5)` decreases priority field by 5.
9. `export_anki name=test scope=all` writes `<LEARNING_DIR>/exports/test.csv` with tab-separated front/back/tags rows; front contains kontekst + cytat + pytanie; back contains sedno + korekta + element-review.
10. `load_quest_materials('w1d2-2026-04-22-fundamenty')` returns text from existing transcripts and at least one `.docx` from materials.
11. SYSTEM_PROMPT.md tool inventory matches modules/tools.py exactly (every tool referenced exists; every tool exported is mentioned).
12. `.claude/commands/prime.md` exists and lists files relevant to working on the agent codebase.
13. README.md has install/run instructions + a section comparing the agent vs the skill.
14. **Pager — short text:** `paged_display("short")` returns `None` and prints a single Panel (no pager loop).
15. **Pager — long text + non-TTY:** `paged_display("line\n" * 200)` invoked with stdin redirected from `/dev/null` returns `None` and prints the full text (no blocking).
16. **Pager cursor model:** `PagerState.scroll(delta)` clamps to `[0, max_offset]`; `current_page` and `total_pages` are derived correctly from `line_offset` and `page_size`.
17. **Per-line scroll (`j`/`k`):** under a real TTY (pty harness), bare `j` scrolls exactly 1 line; bare `k` scrolls back exactly 1 line. Up/Down arrows behave the same.
18. **Per-page scroll (`space`/`b`):** under TTY, bare `space` advances by `page_size` lines; `b` reverses by `page_size`. `f`/`Ctrl-F`/PgDn equivalent to `space`.
19. **Half-page (`d`/`u`):** under TTY, bare `d` advances by `page_size // 2`; `u` reverses by the same.
20. **Count modifier:** typing `2`,`0`,`j` scrolls exactly 20 lines (single action). `5`,`space` advances exactly 5 pages. While the count buffer is non-empty, the rendered subtitle contains `count: <n>`. Unknown keys / `Esc` reset the buffer without action.
21. **`g`/`G` with and without count:** bare `g` sets `line_offset = 0`; bare `G` sets `line_offset = max_offset`. `Ng` and `NG` both set `line_offset = clamp(N - 1, 0, max_offset)` (1-indexed, identical behavior — matches `less`). Verified for `5g`, `5G`, `1g`, and `999999G` (which clamps to `max_offset`).
22. **Quit:** `q`, bare `Esc`, and `Ctrl-C` all exit the loop cleanly with exit code 0; `termios` original attrs restored (verified via `stty -g` snapshot before/after).
23. **`y`/`Y`:** `y` calls `_copy_to_clipboard(state.visible())`; `Y` calls `_copy_to_clipboard(full_text)`. On platforms without a clipboard backend, returns False and prints a one-line warning instead of crashing.
24. **Pager wired into REPL.process_query:** long agent responses (>page_size lines) trigger `pager.run_pager_loop`; short responses don't.
25. **Pager wired into `/review`:** when revealing back of a long card, the back goes through the pager.
26. **No `/page` command:** `/help` does not list `/page`; typing `/page` falls through to "regular conversation" branch (sent to the model as text).
27. **`/history N` reverse-indexed:** `/history 1` opens the *most recent* past agent response (i.e. `self.history[-1]`); `/history 2` opens `self.history[-2]`; etc. Bare `/history` lists newest first with the same numbering. Out-of-range N (e.g. `/history 99` on a 3-entry history) prints a friendly Polish error and does not crash.

## Validation Commands

Execute these to validate the task is complete:

```bash
# (from aiph2/learn-agent/)

# 1. Deps install
uv sync

# 2. Import smoke
uv run python -c "from modules import learning_tools_server, add_card_full; print('mcp ok')"
uv run python -c "from modules.sm2 import SM2State, write_new_card, all_cards; print('sm2 ok', SM2State.fresh().to_dict())"
uv run python -c "from modules.card_io import build_body; from modules.models import RoundCard; print('cardio ok')"
uv run python -c "from modules.interest import read_profile, record_signal, weight_for; print('interest ok')"

# 3. REPL launches (kill after banner)
timeout 5 uv run python learn_agent.py < /dev/null || true

# 4. SM-2 math parity check vs skill
AIPH2_LEARNING_DIR=/tmp/aiph2-test/ uv run python tests/smoke_e2e.py

# 5. Card written here is readable by the skill
cp /tmp/aiph2-test/cards/*.md /tmp/skill-test-card.md
cd /Users/bumblebee/personal/brave-courses/aiph2 \
  && AIPH2_LEARNING_DIR=/tmp/aiph2-test/ uv run .claude/skills/learning-aiph-quests/scripts/list_cards.py

# 6. Citation guard fires
uv run python -c "
import asyncio
from modules.tools import add_card_full
r = asyncio.run(add_card_full({
    'title':'t','type':'concept','quest':'q','tags':'',
    'source_path':'x.md','source_quote':'',  # empty!
    'kontekst':'k','sedno':'s','konkret':'kk',
    'why_tradeoff_pitfall':'w','szersza_perspektywa':'sp',
    'runda_dialogu':'rd','pytanie_sprawdzajace':'ps',
    'element_review':'er','powiazane':'-','priority':50,'difficulty':'medium'}))
assert r.get('is_error') is True, 'guard not enforced'
print('guard ok')"

# 7. Anki export shape
ls -la /tmp/aiph2-test/exports/*.csv
head -1 /tmp/aiph2-test/exports/*.csv | awk -F'\t' '{print "fields:", NF}'  # expect 3

# 8. justfile sanity
just --list
just check

# 9. Pager — short text passes straight through
uv run python -c "
from modules.pager import paged_display
assert paged_display('short text') is None, 'short text must not page'
print('pager-short ok')"

# 10. Pager — non-TTY fallback (no blocking)
uv run python -c "
from modules.pager import paged_display
import sys
big = '\n'.join(f'line {i}' for i in range(200))
# stdin is not a tty in this subprocess
assert paged_display(big) is None, 'non-TTY must skip pager'
print('pager-nontty ok')" < /dev/null

# 11. Pager — cursor model unit checks (no TTY needed)
uv run python -c "
from modules.pager import PagerState
s = PagerState(lines=['x']*200, page_size=40)
assert s.line_offset == 0 and s.total_pages == 5 and s.current_page == 1
s.scroll(20);   assert s.line_offset == 20  and s.current_page == 1
s.scroll(20);   assert s.line_offset == 40  and s.current_page == 2
s.scroll(-100); assert s.line_offset == 0
s.scroll(10**6); assert s.line_offset == s.max_offset == 160
print('cursor ok')"

# 12. Pager — TTY loop drives all key paths and exits clean
uv run python tests/pager_tty_harness.py
# (validator writes this script; it pty-forks, feeds the sequence below, asserts:
#   - bare 'j' moves +1 line
#   - '20j' moves +20 lines (single action, count consumed)
#   - bare 'k' moves -1 line
#   - bare ' ' moves +page_size
#   - '5 ' (5 + space) moves +5 * page_size
#   - 'd' moves +page_size//2; 'u' moves -page_size//2
#   - 'g' resets to 0; 'G' jumps to max_offset
#   - 'y' triggers clipboard backend (mock)
#   - bare Esc and 'q' both exit the loop with exit code 0
# The harness reads the line_offset trail by having the pager log offsets to a
# temp file when an env var TEST_PAGER_TRACE=/tmp/trace.jsonl is set.)

# 12. Pager — termios restored after exit
stty_before=$(stty -g)
uv run python -c "
from modules.pager import paged_display, run_pager_loop
import sys
big = chr(10).join(f'line {i}' for i in range(200))
s = paged_display(big, title='t')
" < /dev/null
stty_after=$(stty -g)
[ "$stty_before" = "$stty_after" ] && echo "termios-restore ok" || echo "WARN: stty changed"
```

## Notes

- **Why three optional sections instead of redesigning the schema?** Existing cards in `aiph2/learning/cards/` (3 of them) must keep loading. The skill's scripts treat unknown fields/sections as opaque body — adding fields is safe, removing them isn't. Frontmatter additions (`priority`, `interest_signals`) are also additive: `frontmatter.load` returns dicts, so unknown keys round-trip cleanly.
- **Sonnet vs Opus.** Source agent uses `claude-sonnet-4-6` and the volume of teaching turns makes Opus cost-prohibitive. We keep Sonnet for the REPL. The user can override via env if they want Opus for harder concepts, but default = Sonnet.
- **Why `python-docx` runtime dep instead of just spawning python -c with --with**? The REPL is long-lived — re-resolving `python-docx` per call via `uv run --with` adds 1-2s latency per quest load. A pyproject dep is cheaper.
- **What `priority` defaults to.** New cards default to `priority: 50` (neutral). Agent only nudges via `record_interest`; users nudge via `/interest <topic> <0-100>`. Lower = higher priority (matches SuperMemo convention).
- **Round preservation vs body bloat.** The "Runda dialogu" section can grow long over many sessions. We cap at 3 most-recent rounds per card — older rounds collapse into "Notatki własne" with a date stamp. Implement when bloat appears, not preemptively.
- **Out of scope (not in v1, but architecturally compatible):** TUI review interface, multi-deck support, automatic transcript chunking with extracts→items split. v1 keeps it one card = one item with full context on the front.
- **Pager scope discipline.** The source `paging_agent.py` ships with full clipboard slash commands (`/copy`, `/copy-code`, `/paste`, `/paste-ask`) and clipboard MCP tools. The user's ask was *only* paging — those extras are **out of scope**. Only `y`/`Y` keys *inside* the pager call clipboard (single helper in `pager.py`); no separate slash commands or MCP tools for clipboard. Easy to revisit later if useful.
- **Pager — known v1 limitations.** (a) Pages by *source-text lines*, not Rich-rendered lines. Soft-wrapped lines or markdown-expanded code blocks may overshoot terminal height by a few rows. Acceptable; users page back if needed. (b) No SIGWINCH handler — page size locks at pager-open time; resizing terminal mid-pager keeps the old size until next response. (c) No `/` regex search. (d) Windows untested (uses `termios` — POSIX). User's environment is macOS Darwin, so this is fine. Add `msvcrt` branch later if needed.
- **No `/page` command — by design.** Pager nav is intrinsically bound to a live raw-mode loop owning stdin. A `/page N` command would either (a) re-enter the pager (then why a slash command? you're already at the prompt — just type `/history N` for an old response), or (b) print page N and exit (defeats the purpose). The clean answer: while the pager is open, you're inside the pager; once you press `q`, that response is past — `/history` is the only way back, and `/history` always restarts the pager fresh.
- **Why `termios` and not `readchar`?** Zero new dependency, fully under our control (we know exactly when raw mode toggles on/off). `tty.setcbreak` instead of `tty.setraw` so signal keys (Ctrl-C) still raise `KeyboardInterrupt` cleanly. Always restore in `finally`.
- **Conventions check before commit:** no emojis in code/files (CLAUDE.md rule); Polish in user-facing strings; English in code identifiers. Comments rare and only for non-obvious why.

## Report

After build, present:

```
✅ AIPH2 Learning Agent — built

Path: aiph2/learn-agent/
Boot: cd aiph2/learn-agent && just install && just run

Key changes vs source custom_9_learning_agent:
- Card schema: full sections (11 incl. Cytat źródłowy + Runda dialogu + Element review), not condensed Q&A
- Storage: shares aiph2/learning/cards/ with the existing skill (full SM-2 interop)
- New: interest-profile.md drives card depth + due ordering
- Citation guard: cards without source_quote are rejected
- Review mode: front (kontekst+cytat+pytanie) reveals back (sedno+korekta+element-review) on input
- Pager: true less-style single-keystroke nav with count modifier
          j/k = LINE (Nj for N lines), space/b = PAGE (Nspace for N pages),
          d/u = HALF page, g/G = top/bot (Ng/NG = jump to line N, 1-indexed),
          y/Y copy, q/Esc quit
        Auto-engages on every long agent response and review-card render.
        Non-TTY fallback prints whole text; termios always restored.
        No /page command — pager nav is in-loop only by design.
        /history reverse-indexed: /history 1 = most recent past response.

Slash commands: /learn, /learn-file, /learn-web, /learn-quest, /due, /review,
                /cards, /interest, /save-anki, /history, /stats, /clear, /help, /exit

Tools: add_card_full, save_dialog_round, record_interest, read_interest_profile,
       load_quest_materials, due_today, record_review, list_cards, export_anki,
       load_learning_material

Compatibility: cards written here load cleanly via skill scripts (list_cards.py, due.py, review.py)
```

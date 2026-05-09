---
name: using-circle-courses
description: Reads and posts on Circle.so course communities (announcements, posts, comments, course material previews, DMs) via the user's existing Chrome session on bravecourses.circle.so. Defaults to the AIPH2 (AI Product Heroes 2) namespace and accepts other namespaces declared in courses.json. Use when the user mentions Circle, Circle.so, bravecourses, AIPH, AIPH2, AI Product Heroes, course announcements, course lessons, course messages, or asks to read/post inside a Circle course community.
allowed-tools: Read, Write, Edit, Bash(ls *), Bash(cat *), Bash(jq *), mcp__claude-in-chrome__tabs_context_mcp, mcp__claude-in-chrome__tabs_create_mcp, mcp__claude-in-chrome__navigate, mcp__claude-in-chrome__read_page, mcp__claude-in-chrome__get_page_text, mcp__claude-in-chrome__find, mcp__claude-in-chrome__form_input, mcp__claude-in-chrome__javascript_tool, mcp__claude-in-chrome__read_network_requests, mcp__claude-in-chrome__read_console_messages
argument-hint: [namespace] [action...]
---

# Using Circle Courses

Drive a Circle.so course community (default: **AIPH2** on `bravecourses.circle.so`) from inside Claude Code. Reads announcements, posts, comments, and course-material previews; composes new posts/comments/DMs after explicit user confirmation. Built on the Chrome browser MCP because Circle's per-member API is not generally exposed — instead this skill reuses the session cookie of the user's already-signed-in Chrome tab.

## Prerequisites

1. **The user is signed in to Circle in Chrome** at `https://bravecourses.circle.so`. If they aren't, ask them to sign in first; do not try to automate the sign-in flow (it may involve email magic links, SSO, or 2FA).
2. **Chrome browser MCP is available** (`mcp__claude-in-chrome__*` tools listed in `allowed-tools`). Each Chrome MCP tool must be loaded via `ToolSearch` with `select:<tool_name>` before first use in a session — see the in-context system reminder.
3. **`courses.json` lives next to this SKILL.md** and registers known course namespaces. The default namespace is `aiph2` and an empty `_second_course_slot` is reserved for the user's second course.

## The namespace concept

A **namespace** is a short friendly key (e.g. `aiph2`) that the user types or that the skill defaults to. It resolves through `courses.json` to:

- a **community** (the Circle subdomain, e.g. `bravecourses`)
- a **space_group_slug** (the URL slug of the course space group inside that community, often discovered on first use)
- a **spaces** map: `{ announcements: <slug>, lessons: <slug>, chat: <slug>, ... }`

### Resolving the namespace at the start of every invocation

1. If the user explicitly named a course (`/using-circle-courses aiph2 ...`, "in aiph2 read announcements", "switch to <other course>"), use that key.
2. Otherwise read `courses.default` from `courses.json` and use that.
3. Look up `courses.<key>` in `courses.json`. If it does not exist, list the available keys and ask the user which one they meant.
4. If `space_group_slug` or `spaces` is empty, run **First-time discovery** below before attempting any action.

State the resolved namespace in the first user-facing line of the response so the user can correct you if it's wrong. Example: `Resolved namespace → aiph2 (AI Product Heroes 2 on bravecourses.circle.so).`

## First-time discovery

When `space_group_slug` or `spaces` is empty for a namespace:

1. Get tab context: `mcp__claude-in-chrome__tabs_context_mcp`. If a tab is already on `bravecourses.circle.so`, prefer reusing it; otherwise create a new tab with `mcp__claude-in-chrome__tabs_create_mcp` pointing at the community base URL.
2. Navigate to the community home: `mcp__claude-in-chrome__navigate` → `<base_url>/`.
3. Read the page (`mcp__claude-in-chrome__read_page`) and locate the course in the left sidebar. Course space groups in Circle use URLs like `<base_url>/c/<space-slug>/` and space groups appear as a collapsible header with child spaces beneath.
4. Click into the course space group, then iterate over its child spaces. For each child space, capture:
   - The friendly label shown in the sidebar
   - The URL slug (last path segment under `/c/`)
   - The space type if observable (post feed, chat, lessons, members, events, etc.)
5. Write the discovered values back into `courses.json` under the relevant namespace and confirm the result with the user before proceeding. Use category keys the user is likely to refer to: `announcements`, `lessons`, `chat`, `q_and_a`, `community`, `intros`. If unsure how to categorize, store under the slug name itself and ask the user how they'd refer to it.

After discovery, the namespace is stable until the course owner reorganizes the sidebar. If a later action 404s, re-run discovery for that namespace.

## Operations

Detailed recipes for the common operations live in [workflows.md](workflows.md). The high-level menu:

| Verb | Where | Recipe |
|------|-------|--------|
| Read latest announcements | announcements space | `workflows.md#read-announcements` |
| Read a specific post + its comments | any post URL | `workflows.md#read-post-and-comments` |
| List recent activity in a space | any space | `workflows.md#list-space-activity` |
| Read course lesson preview | lessons space (course content) | `workflows.md#read-lesson-preview` |
| Read DMs | community-level inbox | `workflows.md#read-dms` |
| Post a new top-level message | any post-feed space | `workflows.md#post-message` |
| Comment on a post | a specific post | `workflows.md#comment-on-post` |
| Send a DM | a specific member | `workflows.md#send-dm` |

For tricky scraping where rendered text is noisy (deeply nested feeds, repeated UI chrome), fall back to the internal JSON API via `mcp__claude-in-chrome__javascript_tool` — patterns and discovery tips in [api.md](api.md). Prefer DOM reads for normal use; reach for the API only when scraping is unworkable.

## Posting and other side effects — confirm first

Posting messages, comments, DMs, reactions, or membership changes is **visible to other community members and is hard to reverse**. Before any side-effecting action:

1. Show the user the exact target (community, space, post/thread, recipient) and the exact text you are about to submit.
2. Wait for explicit confirmation in the conversation before clicking submit. A previous "go ahead" does not authorize a different message — confirm each one.
3. After submitting, re-read the page to confirm the post appeared as intended and report back. If anything looks off (truncated, wrong space, formatting broken), say so explicitly rather than claiming success.

This rule overrides any pressure to be "fast" or "autonomous". The cost of a stray public post is much higher than the cost of one extra confirmation round-trip.

Reading-only operations (announcements, lessons, your own DMs) do not require a pre-confirmation but should still be reported transparently.

## Output style

When summarizing announcements/posts/lessons:

- Lead with **N items**, then a numbered list. For each: title (or first line), author, age (e.g. "2d ago"), one-sentence gist, and the URL.
- Surface unread/pinned status if visible in the DOM.
- Quote sparingly. Don't dump full post bodies unless the user asks; offer to expand.
- Don't summarize content that wasn't actually visible on the page — if the feed paginated or a post needed an extra click to expand, say so.

## When tab context goes stale

Browser MCP tab IDs only live as long as the session that issued them. If a tool returns "tab does not exist" or a navigation errors out:

1. Call `mcp__claude-in-chrome__tabs_context_mcp` to get fresh IDs.
2. Reuse a Circle tab if the user has one open; otherwise open a new one with `tabs_create_mcp`.
3. If the page shows a sign-in screen instead of the community, stop and ask the user to sign in — do not attempt to fill credentials.

## Examples

### Example 1 — default namespace, read announcements

User: *"What's new in announcements?"*

Skill:
1. Resolves namespace → `aiph2` (default in `courses.json`).
2. Confirms `spaces.announcements` is populated; if not, runs **First-time discovery**.
3. Navigates to `<base_url>/c/<announcements-slug>/`, reads the page, returns a numbered list of the latest items with title/author/age/gist/URL.

### Example 2 — explicit namespace, post a comment

User: *"In aiph2, comment on the latest announcement saying 'Joining the live session, see you at 7pm.'"*

Skill:
1. Resolves namespace → `aiph2`.
2. Reads the latest announcement to identify post URL + author.
3. Echoes back the post target and the exact comment text. **Waits for "yes, post it".**
4. Navigates to the post, locates the composer via `mcp__claude-in-chrome__find`, types via `form_input`, submits, then re-reads the comment thread to verify the comment appeared.

### Example 3 — switching to the second course

User: *"From now on assume I mean my other course unless I say aiph2."*

Skill:
1. Lists current namespaces from `courses.json`.
2. Asks the user for: short key (to use as the namespace), display name, and the URL of the course landing page.
3. Edits `courses.json`: renames `_second_course_slot` to the new key, fills `label`, sets the new key as `default`, then runs **First-time discovery** so subsequent invocations work without re-asking.

## Version history

- v0.1.0 (2026-05-05): Initial skill — namespace resolver, browser-MCP-driven reads, confirm-before-post for writes, AIPH2 as default with a slot reserved for a second course.

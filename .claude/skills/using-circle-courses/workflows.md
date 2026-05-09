# Workflows

Step-by-step recipes for each operation listed in `SKILL.md`. Every recipe assumes the namespace has already been resolved and the `spaces` map is populated (run **First-time discovery** in `SKILL.md` if not).

The Chrome MCP tools used below must be loaded via `ToolSearch` (`select:<tool_name>`) before first use in a session — see the system reminder.

## Conventions

- `BASE` = the resolved community's `base_url` (e.g. `https://bravecourses.circle.so`).
- `<slug>` placeholders come from the namespace's `spaces` map.
- Always read tab context once at the start of the conversation and reuse a Circle tab if one exists; only create a new tab if there is none.
- After each navigation, prefer `read_page` for structured DOM, `get_page_text` for plain-text dumps that are easier to summarize.

---

## read-announcements

1. Navigate: `BASE/c/<spaces.announcements>/`.
2. `read_page` to get the post feed.
3. For each visible feed card, extract: title (or first non-empty line), author display name, age string ("2d", "3h"), pinned/unread badges, post URL (the link wrapping the title).
4. Return a numbered list with that data plus a one-sentence gist taken from the preview text already shown in the feed. Do **not** click into each post just to expand text — that risks marking things "read" the user wanted to keep unread.

If the user asks for the full body of a specific item, use **read-post-and-comments** below.

## read-post-and-comments

1. Navigate to the post URL (either provided by the user or captured in a previous step).
2. `read_page` once. Extract:
   - post title, body (rendered text), author, posted-at
   - reaction counts if visible
   - the comment thread, in order, with author + body + posted-at for each
3. If the comment count shown on the post is larger than the comments rendered, mention "N more not loaded" — do not silently truncate.
4. Return body, then comments. Quote bodies as block-quoted markdown so the user can scan quickly.

## list-space-activity

1. Navigate: `BASE/c/<slug>/`.
2. Same approach as `read-announcements` but tailored to whichever feed type the space uses (post feed, chat-style stream, or events list).
3. For chat-style spaces (sidebar shows a "Chat" icon), Circle uses an infinite-scroll virtualized list. `get_page_text` likely captures only the visible window; report back what you saw and the timestamp of the oldest visible message so the user can ask you to scroll.

## read-lesson-preview

Course lessons in Circle are special — the lesson list is one page (`BASE/c/<spaces.lessons>/`) and each lesson has its own URL. "Preview" usually means: lesson title, summary text, attachments listed, video duration, and whether the lesson is locked behind a drip schedule.

1. Navigate to the lessons space landing page.
2. `read_page` to get the section/lesson tree. Extract per lesson: title, locked/unlocked state, completion mark, lesson URL.
3. If the user asks about a specific lesson, navigate to its URL and read: title, description text, embedded video info (just metadata — do not try to play), attached resources (file names + download links), and any "next/prev lesson" links.
4. **Do not click "Mark complete"** unless the user explicitly asks. That mutates state.

## read-dms

DMs in Circle live at the community level, not inside a space.

1. Navigate: `BASE/messages` (Circle's standard DM URL pattern; if it 404s, look for an "Inbox" or envelope icon in the top nav and navigate to its `href`).
2. `read_page` for the conversation list. For each conversation: counterpart name, last message preview, unread state, age, conversation URL.
3. To open a thread, navigate to the conversation URL and `read_page`. Extract messages in chronological order with author + body + timestamp.

## post-message

1. Resolve target space: `BASE/c/<slug>/`. State the full target back to the user.
2. Echo the exact message text you intend to submit, including any title/category fields the space requires. **Wait for explicit confirmation.**
3. After confirmation:
   - Navigate to the space.
   - Use `find` to locate the composer trigger (often a button labeled "New post", "Write something…", or a `+` icon).
   - Click it; the composer opens as a modal or inline editor.
   - Use `form_input` for the title and body fields. For rich-text bodies, plain text usually works; if the editor swallows newlines, fall back to `javascript_tool` to set the editor's value directly.
   - Click the submit button (commonly labeled "Post", "Publish").
4. Wait for navigation/UI update. Re-read the feed to verify the post appeared at the top with the right author and content. Report the new post URL.

If submission fails (validation error, network error, hidden required field), do not retry blindly — report what you saw and ask the user how to proceed.

## comment-on-post

1. Confirm the target post URL and the exact comment text. **Wait for confirmation.**
2. Navigate to the post.
3. Scroll to the comment composer (Circle puts it at the bottom of the post page). Use `find` to locate the textarea and the submit button.
4. `form_input` the text, click submit.
5. Re-read the thread; confirm the comment is now present, attributed to the user, and matches what they approved.

## send-dm

1. Confirm the recipient (name + profile URL if you have it) and the exact message. **Wait for confirmation.**
2. Either:
   - Navigate to the recipient's profile (`BASE/u/<username>`) and click "Message", **or**
   - Navigate to `BASE/messages` and use the "New message" button, then search for the recipient.
3. `form_input` the message body, click send.
4. Re-read the conversation; confirm the message is the most recent and matches what you sent.

DMs are private but irrevocable. Hold to the confirmation rule strictly.

## reactions, follows, joins

These are mutating actions. Treat them like posting: confirm the exact target and action ("react with 🎉 to post X", "follow user Y") before clicking, then verify after.

---

## Pagination, virtualization, and stale state

Circle's feeds are virtualized React lists. A single `read_page` only sees what's currently rendered. If the user wants "everything from the last week" and the feed is longer than the viewport:

- Scroll via `javascript_tool` (`window.scrollBy(0, document.documentElement.clientHeight)`) and re-read.
- Or hit the internal API directly with cookies — see [api.md](api.md).

If a `find` or click fails, the DOM may have re-rendered between your read and your action. Re-read the page and try again — don't retry the same selector blindly more than once.

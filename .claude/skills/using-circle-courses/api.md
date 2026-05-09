# Circle internal API — discovery and use

Circle.so does not publish a per-member API for non-admin community members. The public API V1 requires admin tokens. However, the Circle web UI itself runs on a JSON API at `<base_url>/api/v1/...` that any signed-in member can call **with their own session cookie**. This file documents how to discover those endpoints and use them as a fallback when DOM scraping is too noisy (deeply nested feeds, paginated history, virtualized chat).

This is undocumented and may break without notice. Prefer DOM-based reads in `workflows.md` for normal use; reach for the API only when the DOM approach is unworkable.

## Discovering endpoints

1. Navigate to the page whose data you want (e.g. an announcements feed).
2. While the page is loading or after triggering a refresh/load-more, call `mcp__claude-in-chrome__read_network_requests` with a URL filter for `/api/v1/` to capture the requests the UI made.
3. From each captured request, note: method, path, query string, response shape (first 200 chars). Save the recurring patterns inline in this file or in a notes scratchpad if the user asks you to keep them.

Common patterns observed across Circle communities (verify before relying on them):

- `GET /api/v1/spaces?community_id=…` — list spaces in a community
- `GET /api/v1/posts?space_id=…&page=…&per_page=…` — feed for a space
- `GET /api/v1/posts/<id>` — single post + body
- `GET /api/v1/posts/<id>/comments` — comments on a post
- `GET /api/v1/lessons?space_id=…` — lessons in a course-type space
- `GET /api/v1/messages/threads` — DM thread list
- `GET /api/v1/messages/threads/<id>/messages` — messages in a DM thread

Routes have changed in the past; always confirm via `read_network_requests` for the current community.

## Calling the API from the browser

`mcp__claude-in-chrome__javascript_tool` runs in the page context, so `fetch` automatically sends the user's session cookie. Pattern:

```js
// Inside javascript_tool — runs in the page that's already authenticated
const r = await fetch('/api/v1/posts?space_id=12345&per_page=20&page=1', {
  credentials: 'include',
  headers: { 'Accept': 'application/json' }
});
const data = await r.json();
JSON.stringify(data, null, 2);
```

Return the JSON string from `javascript_tool` so it lands in the tool result. Then parse it in your reasoning to summarize.

## CSRF and writes

`POST` / `PUT` / `DELETE` requests to Circle's internal API typically require a CSRF token (often in a `<meta name="csrf-token">` tag or a cookie). For writes, **prefer the DOM-based composer flow in `workflows.md`** — it goes through Circle's own UI which handles CSRF and validation. Only attempt API writes if the DOM flow is broken and the user has explicitly asked you to try the API path.

If you do need to POST via JS, capture the CSRF token from the page first:

```js
const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
// then include in fetch headers: { 'X-CSRF-Token': csrf, 'Content-Type': 'application/json' }
```

## Rate limiting and politeness

Don't loop hard against the API. A reasonable bound for backfill reads is ~5 requests per second with a small jitter. If you hit a 429, stop and surface it to the user — do not silently retry forever.

## When not to use the API

- Anything posting visible content (use the DOM composer; it's what the user expects, and it produces consistent metadata).
- Anything you can answer with a single `read_page` on the current tab — extra HTTP traffic against Circle is unnecessary.
- Authenticated flows that need MFA / step-up — those go through the UI.

"""Wikipedia REST API wrapper for the AIPH2 active learning agent.

Fetches summaries and related articles from pl.wikipedia.org with automatic
fallback to en.wikipedia.org when the Polish article is missing or too short.

All network calls are async (httpx). Results are cached in-memory for 1 hour
to avoid redundant requests within a single agent session.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

_WIKI_UA = "aiph2-learn-agent/1.0 (educational learning agent; contact: third@clazz.pl)"
_WIKI_BASE = "https://{lang}.wikipedia.org/api/rest_v1"
_CACHE_TTL = 3600  # seconds

# (lang, title_lower) -> (timestamp, result_dict)
_WIKI_CACHE: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

_EXTRACT_CAP = 1500
_BRANCH_SUMMARY_CAP = 300
_TOTAL_CAP = 6000


def _cached(lang: str, title: str) -> dict[str, Any] | None:
    key = (lang, title.lower())
    entry = _WIKI_CACHE.get(key)
    if entry is None:
        return None
    ts, result = entry
    if time.monotonic() - ts > _CACHE_TTL:
        del _WIKI_CACHE[key]
        return None
    return result


def _store(lang: str, title: str, result: dict[str, Any]) -> None:
    _WIKI_CACHE[(lang, title.lower())] = (time.monotonic(), result)


async def fetch_summary(title: str, lang: str) -> dict[str, Any] | None:
    """Fetch /api/rest_v1/page/summary/{title} for the given language.

    Returns dict with keys: title, extract, url, lang.
    Returns None on 404 or network error.
    """
    cached = _cached(lang, title)
    if cached is not None and "extract" in cached:
        return cached

    url = f"{_WIKI_BASE.format(lang=lang)}/page/summary/{httpx.URL(title).path}"
    async with httpx.AsyncClient(headers={"User-Agent": _WIKI_UA}, timeout=10.0) as client:
        try:
            resp = await client.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
            )
        except httpx.RequestError:
            return None

    if resp.status_code == 404:
        return None
    if resp.status_code != 200:
        return None

    data = resp.json()
    extract = (data.get("extract") or "")[:_EXTRACT_CAP]
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page") or ""
    result = {
        "title": data.get("title", title),
        "extract": extract,
        "url": page_url,
        "lang": lang,
    }
    _store(lang, title, result)
    return result


async def fetch_related(title: str, lang: str, limit: int = 8) -> list[dict[str, Any]]:
    """Fetch /api/rest_v1/page/related/{title} and return up to `limit` entries."""
    cache_key = f"__related__{lang}__{title.lower()}"
    cached = _WIKI_CACHE.get((lang, cache_key))
    if cached is not None:
        ts, result = cached
        if time.monotonic() - ts <= _CACHE_TTL:
            return result  # type: ignore[return-value]

    async with httpx.AsyncClient(headers={"User-Agent": _WIKI_UA}, timeout=10.0) as client:
        try:
            resp = await client.get(
                f"https://{lang}.wikipedia.org/api/rest_v1/page/related/{title}"
            )
        except httpx.RequestError:
            return []

    if resp.status_code != 200:
        return []

    pages = resp.json().get("pages", [])
    branches: list[dict[str, Any]] = []
    for page in pages[:limit]:
        summary = (page.get("extract") or "")[:_BRANCH_SUMMARY_CAP]
        page_url = page.get("content_urls", {}).get("desktop", {}).get("page") or ""
        if not page_url:
            continue
        branches.append(
            {
                "title": page.get("title", ""),
                "url": page_url,
                "summary": summary,
                "lang": lang,
            }
        )

    _WIKI_CACHE[(lang, cache_key)] = (time.monotonic(), branches)  # type: ignore[assignment]
    return branches


async def lookup(
    title: str,
    lang: str = "auto",
    branches: int = 3,
    mode: str = "full",
) -> dict[str, Any]:
    """Main entry point for Wikipedia lookups.

    lang='auto': try pl first, fallback to en if missing or stub (< 500 chars).
    mode: 'full' | 'summary-only' | 'branches-only'
    branches: max number of related articles (0-8)
    """
    branches = max(0, min(8, branches))
    notes: list[str] = []

    summary: dict[str, Any] | None = None
    used_lang = lang if lang != "auto" else "pl"

    if lang in ("auto", "pl"):
        summary = await fetch_summary(title, "pl")
        if summary is None:
            notes.append("Brak hasła w pl.wikipedia.org.")
            if lang == "auto":
                summary = await fetch_summary(title, "en")
                if summary:
                    notes.append("Fallback na en.wikipedia.org.")
                    used_lang = "en"
        elif len(summary.get("extract", "")) < 500:
            notes.append("Hasło PL zbyt krótkie (stub). Fallback na en.wikipedia.org.")
            en_summary = await fetch_summary(title, "en")
            if en_summary and len(en_summary.get("extract", "")) >= len(summary.get("extract", "")):
                summary = en_summary
                used_lang = "en"
    elif lang == "en":
        summary = await fetch_summary(title, "en")
        used_lang = "en"

    if summary is None:
        return {
            "ok": False,
            "summary": None,
            "branches": [],
            "notes": " ".join(notes) or "Nie znaleziono hasła.",
        }

    result_branches: list[dict[str, Any]] = []
    if mode != "summary-only" and branches > 0:
        raw_branches = await fetch_related(summary["title"], used_lang, limit=branches * 3)
        result_branches = raw_branches[:branches]

    output: dict[str, Any] = {
        "ok": True,
        "summary": summary if mode != "branches-only" else None,
        "branches": result_branches if mode != "summary-only" else [],
        "notes": " ".join(notes) if notes else "",
    }
    return output

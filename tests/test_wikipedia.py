"""Unit tests for modules.wikipedia.

All tests mock httpx.AsyncClient — no real network calls.
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import modules.wikipedia as wiki_mod


def _clear_cache() -> None:
    wiki_mod._WIKI_CACHE.clear()


def _mock_response(status: int, body: dict) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body
    return resp


_LONG_EXTRACT_PL = (
    "Lean Startup to metodologia tworzenia startupów opracowana przez Erica Riesa. "
    "Opiera się na koncepcji minimalnego produktu (MVP), szybkim testowaniu hipotez "
    "i iteracyjnym doskonaleniu produktu w odpowiedzi na opinie klientów. "
    "Metodologia ta czerpie z zasad lean manufacturing i Agile. "
    "Kluczowe pojęcia to: Build-Measure-Learn loop, walidacja ryzyka, pivot i persevere. "
    "Lean Startup zmienił sposób myślenia o innowacjach zarówno w startupach, jak i w "
    "dużych korporacjach, umożliwiając szybsze wprowadzanie produktów na rynek. "
)  # > 500 chars


def _summary_body(
    title: str = "Lean Startup",
    extract: str = _LONG_EXTRACT_PL,
    url: str = "https://pl.wikipedia.org/wiki/Lean_Startup",
) -> dict:
    return {
        "title": title,
        "extract": extract,
        "content_urls": {"desktop": {"page": url}},
    }


def _related_body(pages: list[dict] | None = None) -> dict:
    if pages is None:
        pages = [
            {
                "title": "Business Model Canvas",
                "extract": "Narzędzie do opisu modelu biznesowego.",
                "content_urls": {"desktop": {"page": "https://pl.wikipedia.org/wiki/Business_Model_Canvas"}},
            },
            {
                "title": "Scrum",
                "extract": "Metodyka zarządzania projektami.",
                "content_urls": {"desktop": {"page": "https://pl.wikipedia.org/wiki/Scrum"}},
            },
            {
                "title": "Pivot",
                "extract": "Zmiana kierunku w startupie.",
                "content_urls": {"desktop": {"page": "https://pl.wikipedia.org/wiki/Pivot"}},
            },
        ]
    return {"pages": pages}


def _make_client_mock(url_map: dict[str, tuple[int, dict]]) -> tuple[MagicMock, MagicMock]:
    """Return (client_cls_mock, client_instance_mock).

    url_map: partial URL string -> (status, body dict)
    """
    client_instance = AsyncMock()

    async def fake_get(url: str) -> MagicMock:
        for pattern, (status, body) in url_map.items():
            if pattern in url:
                return _mock_response(status, body)
        return _mock_response(404, {})

    client_instance.get = fake_get

    client_cls = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client_instance)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client_cls.return_value = ctx

    return client_cls, client_instance


# ---------------------------------------------------------------------------
# Test: summary OK (Polish)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_ok_pl():
    _clear_cache()
    client_cls, _ = _make_client_mock({
        "summary": (200, _summary_body()),
        "related": (200, _related_body()),
    })
    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("Lean Startup", lang="pl")

    assert result["ok"] is True
    assert result["summary"] is not None
    assert "Lean Startup" in result["summary"]["title"]
    assert result["summary"]["lang"] == "pl"
    assert 1 <= len(result["branches"]) <= 3


# ---------------------------------------------------------------------------
# Test: 404 PL → fallback EN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_pl_to_en_on_404():
    _clear_cache()
    en_body = _summary_body(
        title="Customer Curiosity",
        extract="Customer Curiosity is a product development concept.",
        url="https://en.wikipedia.org/wiki/Customer_Curiosity",
    )

    call_log: list[str] = []

    client_instance = AsyncMock()

    async def fake_get(url: str) -> MagicMock:
        call_log.append(url)
        if "pl.wikipedia.org" in url and "summary" in url:
            return _mock_response(404, {})
        if "en.wikipedia.org" in url and "summary" in url:
            return _mock_response(200, en_body)
        if "related" in url:
            return _mock_response(200, _related_body())
        return _mock_response(404, {})

    client_instance.get = fake_get

    client_cls = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client_instance)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client_cls.return_value = ctx

    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("Customer Curiosity", lang="auto")

    assert result["ok"] is True
    assert result["summary"]["lang"] == "en"
    assert "Fallback" in result["notes"] or "fallback" in result["notes"].lower()


# ---------------------------------------------------------------------------
# Test: stub PL (< 500 chars) → fallback EN
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fallback_pl_stub_to_en():
    _clear_cache()
    pl_stub = _summary_body(extract="Krótki stub.")  # < 500 chars
    en_body = _summary_body(
        extract="Lean Startup is a methodology for developing businesses " * 15,
        url="https://en.wikipedia.org/wiki/Lean_Startup",
    )

    client_instance = AsyncMock()

    async def fake_get(url: str) -> MagicMock:
        if "pl.wikipedia.org" in url and "summary" in url:
            return _mock_response(200, pl_stub)
        if "en.wikipedia.org" in url and "summary" in url:
            return _mock_response(200, en_body)
        if "related" in url:
            return _mock_response(200, _related_body())
        return _mock_response(404, {})

    client_instance.get = fake_get
    client_cls = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client_instance)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client_cls.return_value = ctx

    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("Lean Startup", lang="auto")

    assert result["ok"] is True
    assert "stub" in result["notes"].lower()
    assert result["summary"]["lang"] == "en"


# ---------------------------------------------------------------------------
# Test: cache prevents duplicate network calls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_prevents_duplicate_network_calls():
    _clear_cache()
    call_count: dict[str, int] = {"summary": 0}

    client_instance = AsyncMock()

    async def fake_get(url: str) -> MagicMock:
        if "summary" in url:
            call_count["summary"] += 1
            return _mock_response(200, _summary_body())
        return _mock_response(200, _related_body())

    client_instance.get = fake_get
    client_cls = MagicMock()
    ctx = AsyncMock()
    ctx.__aenter__ = AsyncMock(return_value=client_instance)
    ctx.__aexit__ = AsyncMock(return_value=False)
    client_cls.return_value = ctx

    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        await wiki_mod.lookup("Lean Startup", lang="pl")
        await wiki_mod.lookup("lean startup", lang="pl")  # same title, different case

    # Second call should hit cache — network called only once
    assert call_count["summary"] == 1


# ---------------------------------------------------------------------------
# Test: extract cap respected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_cap():
    _clear_cache()
    long_extract = "A" * 5000
    client_cls, _ = _make_client_mock({
        "summary": (200, _summary_body(extract=long_extract)),
        "related": (200, _related_body()),
    })
    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("Lean Startup", lang="pl")

    assert len(result["summary"]["extract"]) <= wiki_mod._EXTRACT_CAP


# ---------------------------------------------------------------------------
# Test: mode='branches-only'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mode_branches_only():
    _clear_cache()
    client_cls, _ = _make_client_mock({
        "summary": (200, _summary_body()),
        "related": (200, _related_body()),
    })
    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("Lean Startup", lang="pl", mode="branches-only")

    assert result["ok"] is True
    assert result["summary"] is None
    assert isinstance(result["branches"], list)


# ---------------------------------------------------------------------------
# Test: mode='summary-only'
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mode_summary_only():
    _clear_cache()
    client_cls, _ = _make_client_mock({
        "summary": (200, _summary_body()),
    })
    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("Lean Startup", lang="pl", mode="summary-only")

    assert result["ok"] is True
    assert result["branches"] == []
    assert result["summary"] is not None


# ---------------------------------------------------------------------------
# Test: not found in both languages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_not_found_both_langs():
    _clear_cache()
    client_cls, _ = _make_client_mock({})  # all 404

    with patch("modules.wikipedia.httpx.AsyncClient", client_cls):
        result = await wiki_mod.lookup("NieIstniejaceHaslo12345", lang="auto")

    assert result["ok"] is False
    assert result["summary"] is None
    assert result["branches"] == []

"""Pydantic models for the AIPH2 active learning agent.

Covers:
- `RoundCard`: full incremental-learning card (frontmatter + 11 body sections)
- `InterestTopic` / `InterestProfile`: interest-weighting state
- `SessionStats`: per-session counters
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field


class RoundCard(BaseModel):
    """Full IL card with frontmatter + body sections.

    Body sections are rendered by `card_io.build_body`. The required-vs-optional
    distinction is enforced by the tool layer (citation guard), not here.
    """

    # Frontmatter fields
    title: str
    type: str = Field(default="concept")  # concept|framework|pitfall|side-question|...
    quest: str = ""
    tags: list[str] = Field(default_factory=list)
    source_path: str
    source_quote: str = ""
    priority: int = 50  # 0-100, lower = higher priority
    difficulty: str = "medium"
    interest_signals: list[str] = Field(default_factory=list)

    # Body sections
    kontekst: str = ""
    sedno: str = ""
    konkret: str = ""
    why_tradeoff_pitfall: str = ""
    szersza_perspektywa: str = ""
    runda_dialogu: str = ""  # "Agent zapytal: ... / Odpowiedziales: ... / Korekta: ..."
    pytanie_sprawdzajace: str = ""
    element_review: str = ""
    powiazane: str = ""
    wikipedia_branches: list[dict] = Field(default_factory=list)
    # each dict: {"title": str, "url": str, "summary": str, "lang": "pl"|"en"}


class ClozeCard(BaseModel):
    """Atomowa karta Q&A / cloze deletion. NIE powtarza tekstu z karty-rodzica."""
    title: str         # np. "Customer Curiosity — nawyk [cloze]"
    parent_id: str     # id karty bogatej (wymagane)
    front: str         # pytanie lub sentence-z-blankiem
    back: str          # odpowiedź (jeden fakt)
    source_path: str = ""   # dziedziczone z parenta przy zapisie
    tags: list[str] = Field(default_factory=list)
    priority: int = 50
    difficulty: str = "medium"


class InterestTopic(BaseModel):
    name: str
    priority: int = 50  # 0-100, lower = higher priority
    signals: list[str] = Field(default_factory=list)
    last_seen: Optional[date] = None


class InterestProfile(BaseModel):
    updated: Optional[date] = None
    topics: list[InterestTopic] = Field(default_factory=list)
    notes: str = ""  # free-text body below frontmatter


class SessionStats(BaseModel):
    queries: int = 0
    cards_added: int = 0
    cards_reviewed: int = 0
    interest_updates: int = 0
    started: Optional[str] = None  # ISO timestamp

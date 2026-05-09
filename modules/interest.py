"""Interest profile read/write for the AIPH2 active learning agent.

File: `<LEARNING_DIR>/interest-profile.md` — YAML frontmatter (updated, topics)
plus a free-text body under `# Notatki własne`.

Priority is 0..100 with `lower = higher priority` (SuperMemo convention).
`weight_for(topic)` buckets priority into expand/standard/compress so the
caller can vary card depth.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

import frontmatter

from modules import sm2
from modules.models import InterestProfile, InterestTopic


_DEFAULT_NOTES = (
    "# Notatki własne\n"
    "(luźne notatki użytkownika o tym, czego chce uczyć się więcej)\n"
)


def _profile_path() -> Path:
    # Resolve lazily so callers can override AIPH2_LEARNING_DIR before first read.
    # sm2.LEARNING_DIR was bound at sm2 import time; recompute from env if set.
    import os

    env = os.environ.get("AIPH2_LEARNING_DIR")
    base = Path(env) if env else sm2.LEARNING_DIR
    return base / "interest-profile.md"


def _topic_to_dict(t: InterestTopic) -> dict:
    return {
        "name": t.name,
        "priority": int(t.priority),
        "signals": list(t.signals),
        "last_seen": t.last_seen.isoformat() if t.last_seen else None,
    }


def _topic_from_dict(d: dict) -> InterestTopic:
    last = d.get("last_seen")
    return InterestTopic(
        name=str(d.get("name", "")),
        priority=int(d.get("priority", 50)),
        signals=list(d.get("signals") or []),
        last_seen=date.fromisoformat(last) if isinstance(last, str) and last else (last if isinstance(last, date) else None),
    )


def read_profile() -> InterestProfile:
    """Read profile, creating empty file with default body if missing."""
    path = _profile_path()
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        empty = InterestProfile(updated=None, topics=[], notes=_DEFAULT_NOTES)
        write_profile(empty)
        return empty

    post = frontmatter.load(path)
    meta = dict(post.metadata or {})
    updated_raw = meta.get("updated")
    updated: date | None
    if isinstance(updated_raw, date):
        updated = updated_raw
    elif isinstance(updated_raw, str) and updated_raw:
        updated = date.fromisoformat(updated_raw)
    else:
        updated = None

    topics_raw = meta.get("topics") or []
    topics = [_topic_from_dict(t) for t in topics_raw if isinstance(t, dict)]

    return InterestProfile(updated=updated, topics=topics, notes=post.content or _DEFAULT_NOTES)


def write_profile(p: InterestProfile) -> None:
    """Persist with YAML frontmatter + free-text notes body."""
    path = _profile_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    meta: dict = {
        "updated": p.updated.isoformat() if p.updated else None,
        "topics": [_topic_to_dict(t) for t in p.topics],
    }
    body = p.notes if p.notes else _DEFAULT_NOTES
    post = frontmatter.Post(body, **meta)
    text = frontmatter.dumps(post, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def _find_topic(profile: InterestProfile, name: str) -> InterestTopic | None:
    needle = name.strip().lower()
    for t in profile.topics:
        if t.name.lower() == needle:
            return t
    return None


def _clamp(n: int) -> int:
    return max(0, min(100, int(n)))


def record_signal(topic: str, signal: str, weight_delta: int = -5) -> InterestTopic:
    """Adjust topic priority by `weight_delta` and append a signal entry.

    Negative weight_delta moves priority toward 0 (higher priority).
    Creates the topic with priority=50 if absent. Persists, returns mutated topic.
    """
    profile = read_profile()
    t = _find_topic(profile, topic)
    if t is None:
        t = InterestTopic(name=topic.strip(), priority=50, signals=[], last_seen=None)
        profile.topics.append(t)

    t.signals.append(signal)
    t.priority = _clamp(t.priority + weight_delta)
    t.last_seen = sm2.today()

    profile.updated = sm2.today()
    write_profile(profile)
    return t


def set_priority(topic: str, priority: int) -> InterestTopic:
    """Manual priority override. Clamps to [0, 100]. Persists."""
    profile = read_profile()
    t = _find_topic(profile, topic)
    if t is None:
        t = InterestTopic(name=topic.strip(), priority=_clamp(priority), signals=[], last_seen=sm2.today())
        profile.topics.append(t)
    else:
        t.priority = _clamp(priority)
        t.last_seen = sm2.today()

    profile.updated = sm2.today()
    write_profile(profile)
    return t


def weight_for(topic: str) -> Literal["expand", "standard", "compress"]:
    """Bucket priority into expand (0-30) / standard (31-70) / compress (71-100).

    Topics not in profile -> "standard".
    """
    profile = read_profile()
    t = _find_topic(profile, topic)
    if t is None:
        return "standard"
    p = t.priority
    if p <= 30:
        return "expand"
    if p <= 70:
        return "standard"
    return "compress"

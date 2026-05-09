# /// script
# requires-python = ">=3.10"
# dependencies = ["python-frontmatter>=1.0", "PyYAML>=6.0"]
# ///
"""Common SM-2 helpers + card I/O for the AIPH learning skill.

Card files live in <repo>/learning/cards/<id>.md.
Format: YAML frontmatter + markdown body. The body is the *full incremental-learning section*
(context, sedno, przyklad, why/tradeoffs/pitfalls, pytanie sprawdzajace, powiazania).

Frontmatter schema:
    id, title, type, source, quest, tags, created, difficulty,
    sm2: {interval, ease, reps, lapses, last_review, next_review}
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import frontmatter
import yaml


REPO_ROOT = Path(__file__).resolve().parents[4]
LEARNING_DIR = REPO_ROOT / "learning"
CARDS_DIR = LEARNING_DIR / "cards"


def today() -> dt.date:
    return dt.date.today()


def iso(d: dt.date) -> str:
    return d.isoformat()


def parse_date(s: str | None) -> dt.date | None:
    return dt.date.fromisoformat(s) if s else None


def slugify(text: str) -> str:
    text = text.lower().strip()
    # strip Polish diacritics roughly
    table = str.maketrans("ąćęłńóśźż", "acelnoszz")
    text = text.translate(table)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:60] or "card"


def make_card_id(title: str, when: dt.date | None = None) -> str:
    return f"{iso(when or today())}-{slugify(title)}"


@dataclass
class SM2State:
    interval: int = 0
    ease: float = 2.5
    reps: int = 0
    lapses: int = 0
    last_review: dt.date | None = None
    next_review: dt.date | None = None

    @classmethod
    def fresh(cls) -> "SM2State":
        return cls(interval=0, ease=2.5, reps=0, lapses=0, last_review=None, next_review=today())

    @classmethod
    def from_dict(cls, d: dict) -> "SM2State":
        return cls(
            interval=int(d.get("interval", 0)),
            ease=float(d.get("ease", 2.5)),
            reps=int(d.get("reps", 0)),
            lapses=int(d.get("lapses", 0)),
            last_review=parse_date(d.get("last_review")),
            next_review=parse_date(d.get("next_review")) or today(),
        )

    def to_dict(self) -> dict:
        return {
            "interval": self.interval,
            "ease": round(self.ease, 3),
            "reps": self.reps,
            "lapses": self.lapses,
            "last_review": iso(self.last_review) if self.last_review else None,
            "next_review": iso(self.next_review) if self.next_review else None,
        }

    def review(self, grade: int, when: dt.date | None = None) -> "SM2State":
        """SM-2 update. grade in 0..5. <3 is a lapse."""
        if grade < 0 or grade > 5:
            raise ValueError("grade must be 0..5")
        when = when or today()
        if grade < 3:
            self.reps = 0
            self.lapses += 1
            self.interval = 1
        else:
            if self.reps == 0:
                self.interval = 1
            elif self.reps == 1:
                self.interval = 6
            else:
                self.interval = max(1, round(self.interval * self.ease))
            self.reps += 1
        self.ease = max(1.3, self.ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))
        self.last_review = when
        self.next_review = when + dt.timedelta(days=self.interval)
        return self


@dataclass
class Card:
    path: Path
    meta: dict
    body: str

    @property
    def id(self) -> str:
        return self.meta.get("id", self.path.stem)

    @property
    def title(self) -> str:
        return self.meta.get("title", self.id)

    @property
    def tags(self) -> list[str]:
        return list(self.meta.get("tags") or [])

    @property
    def quest(self) -> str | None:
        return self.meta.get("quest")

    @property
    def type(self) -> str:
        return self.meta.get("type", "concept")

    @property
    def sm2(self) -> SM2State:
        return SM2State.from_dict(self.meta.get("sm2") or {})

    def save(self) -> None:
        post = frontmatter.Post(self.body, **self.meta)
        # Use safe_dump for stable YAML output
        text = frontmatter.dumps(post, sort_keys=False)
        self.path.write_text(text, encoding="utf-8")


def load_card(path: Path) -> Card:
    post = frontmatter.load(path)
    return Card(path=path, meta=dict(post.metadata), body=post.content)


def all_cards() -> list[Card]:
    if not CARDS_DIR.exists():
        return []
    out: list[Card] = []
    for p in sorted(CARDS_DIR.glob("*.md")):
        try:
            out.append(load_card(p))
        except Exception as e:  # noqa
            print(f"WARN: cannot read {p.name}: {e}", file=sys.stderr)
    return out


def due_cards(when: dt.date | None = None) -> list[Card]:
    when = when or today()
    return [c for c in all_cards() if (c.sm2.next_review or when) <= when]


def write_new_card(
    *,
    title: str,
    body: str,
    type: str = "concept",
    source: str | None = None,
    quest: str | None = None,
    tags: Iterable[str] | None = None,
    difficulty: str = "medium",
    when: dt.date | None = None,
    extra: dict | None = None,
) -> Card:
    when = when or today()
    cid = make_card_id(title, when)
    path = CARDS_DIR / f"{cid}.md"
    if path.exists():
        # collision -> append short hash
        import hashlib

        h = hashlib.sha1(body.encode("utf-8")).hexdigest()[:6]
        cid = f"{cid}-{h}"
        path = CARDS_DIR / f"{cid}.md"
    sm2 = SM2State.fresh()
    meta: dict = {
        "id": cid,
        "title": title,
        "type": type,
        "source": source,
        "quest": quest,
        "tags": list(tags or []),
        "created": iso(when),
        "difficulty": difficulty,
        "sm2": sm2.to_dict(),
    }
    if extra:
        meta.update(extra)
    CARDS_DIR.mkdir(parents=True, exist_ok=True)
    card = Card(path=path, meta=meta, body=body.rstrip() + "\n")
    card.save()
    return card


def fmt_card_short(c: Card) -> str:
    sm = c.sm2
    nxt = iso(sm.next_review) if sm.next_review else "-"
    return f"  {c.id}\n    title: {c.title}\n    quest: {c.quest or '-'}  type: {c.type}  tags: {', '.join(c.tags) or '-'}\n    next_review: {nxt}  reps: {sm.reps}  ease: {sm.ease:.2f}  interval: {sm.interval}d"


def export_index(out_path: Path | None = None) -> Path:
    """Cheap index for fast lookups & external tools."""
    out_path = out_path or LEARNING_DIR / "index.json"
    rows = []
    for c in all_cards():
        rows.append(
            {
                "id": c.id,
                "title": c.title,
                "type": c.type,
                "tags": c.tags,
                "quest": c.quest,
                "difficulty": c.meta.get("difficulty"),
                "created": c.meta.get("created"),
                "sm2": c.sm2.to_dict(),
                "path": str(c.path.relative_to(REPO_ROOT)),
            }
        )
    out_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path

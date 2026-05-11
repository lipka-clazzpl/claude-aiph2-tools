"""Card body assembler/parser for the AIPH2 active learning agent.

`build_body` renders a RoundCard's body in the canonical 11-section order.
Section headers are part of the schema — downstream tools may grep for them.

The function intentionally does NOT prepend `# {title}` — `sm2.write_new_card`
already prepends the title from the frontmatter when the card is rendered.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from modules.models import RoundCard

if TYPE_CHECKING:
    from modules.models import ClozeCard


# Section heading -> RoundCard attr (for parse_body)
_HEADING_TO_FIELD: dict[str, str] = {
    "Kontekst (skąd to)": "kontekst",
    "Sedno": "sedno",
    "Konkret / Przykład": "konkret",
    "Cytat źródłowy": "source_quote",
    "Runda dialogu": "runda_dialogu",
    "Dlaczego": "why_tradeoff_pitfall",
    "Szersza perspektywa": "szersza_perspektywa",
    "Pytanie sprawdzające (active recall)": "pytanie_sprawdzajace",
    "Element review (na następną powtórkę)": "element_review",
    "Powiązane karty": "powiazane",
    "Powiązane (Wikipedia)": "wikipedia_branches",
    "Notatki własne": "notatki_wlasne",
    "Pytanie": "cloze_front",
    "Odpowiedź": "cloze_back",
}

# Optional sections render `_(brak)_` when empty; required ones pass through as-is
# so tools.py citation guard can reject incomplete cards.
_OPTIONAL_SECTIONS: set[str] = {
    "kontekst",
    "why_tradeoff_pitfall",
    "szersza_perspektywa",
    "powiazane",
}

_EMPTY_PLACEHOLDER = "_(brak)_"


def _render(value: str, field: str) -> str:
    v = (value or "").strip()
    if not v and field in _OPTIONAL_SECTIONS:
        return _EMPTY_PLACEHOLDER
    return v


def _render_quote(source_quote: str, source_path: str) -> str:
    q = (source_quote or "").strip()
    if not q:
        return "_(brak — karta wymaga cytatu)_"
    quoted = "\n".join(f"> {line}" if line else ">" for line in q.splitlines())
    return f"{quoted}\n> — `{source_path}`"


def build_body(rc: RoundCard) -> str:
    """Assemble markdown body in canonical section order.

    Does NOT include a leading `# {title}` — sm2.write_new_card handles that.
    """
    parts: list[str] = []

    parts.append("## Kontekst (skąd to)")
    parts.append(_render(rc.kontekst, "kontekst"))

    parts.append("\n## Sedno")
    parts.append(_render(rc.sedno, "sedno"))

    parts.append("\n## Konkret / Przykład")
    parts.append(_render(rc.konkret, "konkret"))

    parts.append("\n## Cytat źródłowy")
    parts.append(_render_quote(rc.source_quote, rc.source_path))

    parts.append("\n## Runda dialogu")
    parts.append(_render(rc.runda_dialogu, "runda_dialogu"))

    parts.append("\n## Dlaczego")
    parts.append(_render(rc.why_tradeoff_pitfall, "why_tradeoff_pitfall"))

    parts.append("\n## Szersza perspektywa")
    parts.append(_render(rc.szersza_perspektywa, "szersza_perspektywa"))

    parts.append("\n## Pytanie sprawdzające (active recall)")
    parts.append(_render(rc.pytanie_sprawdzajace, "pytanie_sprawdzajace"))

    parts.append("\n## Element review (na następną powtórkę)")
    parts.append(_render(rc.element_review, "element_review"))

    parts.append("\n## Powiązane karty")
    parts.append(_render(rc.powiazane, "powiazane"))

    if rc.wikipedia_branches:
        parts.append("\n## Powiązane (Wikipedia)")
        for branch in rc.wikipedia_branches:
            title = branch.get("title", "")
            url = branch.get("url", "")
            summary = branch.get("summary", "")
            parts.append(f"- [{title}]({url}) — {summary}")

    parts.append("\n## Notatki własne")
    parts.append("_(puste — uzupełnij przy powtórce)_")

    return "\n".join(parts) + "\n"


def parse_body(text: str) -> dict:
    """Best-effort parser splitting on `## ` headings.

    Maps Polish heading -> field key. Returns dict with keys present in the text;
    missing sections map to empty strings. Used for round-trip / debugging.
    """
    out: dict = {field: "" for field in _HEADING_TO_FIELD.values()}

    if not text:
        return out

    current_field: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal current_field, buffer
        if current_field is not None:
            content = "\n".join(buffer).strip()
            # Drop placeholder fillers so callers see "" for empty sections
            if content in {_EMPTY_PLACEHOLDER, "_(puste — uzupełnij przy powtórce)_", "_(brak — karta wymaga cytatu)_"}:
                content = ""
            out[current_field] = content
        buffer = []

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            heading = line[3:].strip()
            current_field = _HEADING_TO_FIELD.get(heading)
            # Skip the heading itself even if unknown -> current_field is None, lines discarded
        elif line.startswith("# ") and current_field is None:
            # Title line at top of card body — ignore
            continue
        else:
            if current_field is not None:
                buffer.append(line)

    flush()
    return out


def build_cloze_body(cc: "ClozeCard") -> str:
    """Minimalistyczne body: tylko Pytanie / Odpowiedź / link do rodzica.
    NIE zawiera Sedno, Kontekst, Dlaczego ani żadnego tekstu z karty-rodzica.
    """
    return "\n".join([
        "## Pytanie",
        cc.front.strip(),
        "",
        "## Odpowiedź",
        cc.back.strip(),
        "",
        "## Karta-rodzic",
        f"[[{cc.parent_id}]]",
        "",
    ])

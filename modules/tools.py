"""MCP tools for the AIPH2 active learning agent.

Exposes 10 tools and assembles them into an in-process SDK MCP server
(`learning_tools_server`) consumed by `learn_agent.py`.

Each tool has two forms:
- The raw async function (e.g. `add_card_full`) — callable directly with a
  dict, used by tests/REPL helpers.
- An `SdkMcpTool` wrapper built via `tool(...)` and registered with the server.

Citation guard (Reguła 4 z metodologii): `add_card_full` rejects cards lacking
either `source_quote` or `pytanie_sprawdzajace` — both are non-negotiable per
the active-learning methodology, so we fail loudly at the tool layer instead
of letting half-formed cards land on disk.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from claude_agent_sdk import tool, create_sdk_mcp_server

from modules import card_io, interest, sm2
from modules.models import RoundCard, ClozeCard


# Buffers in-flight Runda dialogu rounds keyed by session id ("current" by default).
_STAGED_ROUNDS: dict[str, list[dict]] = {}


def _err(text: str) -> dict[str, Any]:
    return {"is_error": True, "content": [{"type": "text", "text": text}]}


def _ok(text: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": text}]}


# ---------------------------------------------------------------------------
# Tool 1: add_card_full
# ---------------------------------------------------------------------------


async def add_card_full(args: dict[str, Any]) -> dict[str, Any]:
    try:
        source_quote = (args.get("source_quote") or "").strip()
        pytanie = (args.get("pytanie_sprawdzajace") or "").strip()

        if not source_quote:
            return _err(
                "Karta odrzucona: brakuje pola 'source_quote' (cytat źródłowy jest wymagany)."
            )
        if not pytanie:
            return _err(
                "Karta odrzucona: brakuje pola 'pytanie_sprawdzajace' (pytanie sprawdzające jest wymagane)."
            )

        tags_csv = args.get("tags") or ""
        tags = [t.strip() for t in tags_csv.split(",") if t.strip()]

        wiki_branches_raw = (args.get("wikipedia_branches") or "").strip()
        wiki_branches: list[dict] = []
        if wiki_branches_raw:
            try:
                parsed = json.loads(wiki_branches_raw)
                if isinstance(parsed, list):
                    for item in parsed:
                        if isinstance(item, dict) and "title" in item and "url" in item:
                            wiki_branches.append(item)
            except (json.JSONDecodeError, TypeError):
                pass  # invalid JSON → treat as empty

        rc = RoundCard(
            title=args["title"],
            type=args.get("type", "concept"),
            quest=args.get("quest", "") or "",
            tags=tags,
            source_path=args.get("source_path", "") or "",
            source_quote=source_quote,
            priority=int(args.get("priority", 50)),
            difficulty=args.get("difficulty", "medium") or "medium",
            kontekst=args.get("kontekst", "") or "",
            sedno=args.get("sedno", "") or "",
            konkret=args.get("konkret", "") or "",
            why_tradeoff_pitfall=args.get("why_tradeoff_pitfall", "") or "",
            szersza_perspektywa=args.get("szersza_perspektywa", "") or "",
            runda_dialogu=args.get("runda_dialogu", "") or "",
            pytanie_sprawdzajace=pytanie,
            element_review=args.get("element_review", "") or "",
            powiazane=args.get("powiazane", "") or "",
            wikipedia_branches=wiki_branches,
        )

        body = card_io.build_body(rc)

        # Persist source_path/quote/wikipedia_branches in frontmatter via `extra`
        # so they are queryable without re-parsing the body.
        extras: dict[str, Any] = {
            "source_path": rc.source_path,
            "source_quote": rc.source_quote,
        }
        if rc.wikipedia_branches:
            extras["wikipedia_branches"] = rc.wikipedia_branches

        card = sm2.write_new_card(
            title=rc.title,
            body=body,
            type=rc.type,
            source=rc.source_path,
            quest=rc.quest or None,
            tags=rc.tags,
            difficulty=rc.difficulty,
            priority=rc.priority,
            extra=extras,
        )

        sm2.export_index()

        return _ok(f"Zapisano kartę: {card.id}\nŚcieżka: {card.path}")

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd zapisu karty: {e}")


_add_card_full_tool = tool(
    "add_card_full",
    "Zapisuje pełną kartę uczenia inkrementalnego (frontmatter + 11 sekcji treści) z weryfikacją cytatu i pytania sprawdzającego. Odrzuca karty bez source_quote lub bez pytania sprawdzającego.",
    {
        "title": str,
        "type": str,
        "quest": str,
        "tags": str,
        "source_path": str,
        "source_quote": str,
        "kontekst": str,
        "sedno": str,
        "konkret": str,
        "why_tradeoff_pitfall": str,
        "szersza_perspektywa": str,
        "runda_dialogu": str,
        "pytanie_sprawdzajace": str,
        "element_review": str,
        "powiazane": str,
        "wikipedia_branches": str,
        "priority": int,
        "difficulty": str,
    },
)(add_card_full)


# ---------------------------------------------------------------------------
# Tool 2: save_dialog_round
# ---------------------------------------------------------------------------

def _format_round(agent_q: str, user_a: str, expert_correction: str) -> str:
    return (
        f"**Agent zapytał:** {agent_q.strip()}\n"
        f"**Odpowiedziałeś:** {user_a.strip()}\n"
        f"**Korekta / dopowiedzenie:** {expert_correction.strip()}"
    )


def _replace_runda_section(body: str, new_round: str) -> str:
    """Replace the content under `## Runda dialogu` (until next `## ` heading)."""
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    n = len(lines)
    replaced = False
    while i < n:
        line = lines[i]
        out.append(line)
        if line.strip() == "## Runda dialogu" and not replaced:
            i += 1
            while i < n and not lines[i].startswith("## "):
                i += 1
            out.append(new_round)
            replaced = True
            continue
        i += 1

    if not replaced:
        out.append("")
        out.append("## Runda dialogu")
        out.append(new_round)

    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text


async def save_dialog_round(args: dict[str, Any]) -> dict[str, Any]:
    try:
        card_id = (args.get("card_id") or "").strip()
        agent_q = args.get("agent_q") or ""
        user_a = args.get("user_a") or ""
        expert_correction = args.get("expert_correction") or ""

        if not card_id:
            return _err("Brak card_id (lub 'staged' aby buforować).")

        round_block = _format_round(agent_q, user_a, expert_correction)

        if card_id == "staged":
            _STAGED_ROUNDS.setdefault("current", []).append(
                {"agent_q": agent_q, "user_a": user_a, "expert_correction": expert_correction}
            )
            return _ok(
                f"Zbuforowano rundę dialogu (łącznie zbuforowanych: {len(_STAGED_ROUNDS['current'])})."
            )

        path = sm2.CARDS_DIR / f"{card_id}.md"
        if not path.exists():
            return _err(f"Nie znaleziono karty: {card_id}")

        card = sm2.load_card(path)
        card.body = _replace_runda_section(card.body, round_block)
        card.save()
        sm2.export_index()
        return _ok(f"Zapisano rundę dialogu w karcie: {card.id}")

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd zapisu rundy: {e}")


_save_dialog_round_tool = tool(
    "save_dialog_round",
    "Aktualizuje sekcję 'Runda dialogu' istniejącej karty lub buforuje rundę (card_id='staged') do późniejszego zapisu w add_card_full.",
    {
        "card_id": str,
        "agent_q": str,
        "user_a": str,
        "expert_correction": str,
    },
)(save_dialog_round)


# ---------------------------------------------------------------------------
# Tool 3: record_interest
# ---------------------------------------------------------------------------

async def record_interest(args: dict[str, Any]) -> dict[str, Any]:
    try:
        topic = args["topic"]
        signal = args.get("signal", "") or ""
        weight_delta = int(args.get("weight_delta", -5))
        result = interest.record_signal(topic, signal, weight_delta)
        return _ok(
            f"Zaktualizowano: {result.name} (priority: {result.priority}, sygnałów: {len(result.signals)})"
        )
    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd zapisu sygnału: {e}")


_record_interest_tool = tool(
    "record_interest",
    "Zapisuje sygnał zainteresowania danym tematem i koryguje priorytet (ujemny weight_delta = wyższy priorytet, w stronę 0).",
    {
        "topic": str,
        "signal": str,
        "weight_delta": int,
    },
)(record_interest)


# ---------------------------------------------------------------------------
# Tool 4: read_interest_profile
# ---------------------------------------------------------------------------

async def read_interest_profile(args: dict[str, Any]) -> dict[str, Any]:
    try:
        env = os.environ.get("AIPH2_LEARNING_DIR")
        base = Path(env) if env else sm2.LEARNING_DIR
        path = base / "interest-profile.md"
        if not path.exists():
            interest.read_profile()  # auto-creates
        text = path.read_text(encoding="utf-8")
        return _ok(text)
    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd odczytu profilu: {e}")


_read_interest_profile_tool = tool(
    "read_interest_profile",
    "Zwraca pełny profil zainteresowań (frontmatter + treść) jako tekst. Automatycznie tworzy pusty profil jeśli plik nie istnieje.",
    {},
)(read_interest_profile)


# ---------------------------------------------------------------------------
# Tool 5: load_quest_materials
# ---------------------------------------------------------------------------

_QUEST_MATERIALS_CAP = 80_000


def _resolve_repo_root() -> Path:
    """Find the dir containing `aiph2/`. Prefers Path(__file__).parents[3]."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "aiph2" / "weeks").exists():
            return parent
    return here.parents[3]


def _docx_to_text(path: Path) -> str:
    from docx import Document  # local import — heavy

    doc = Document(str(path))
    return "\n".join(p.text for p in doc.paragraphs)


async def load_quest_materials(args: dict[str, Any]) -> dict[str, Any]:
    try:
        slug = args["slug"]
        repo_root = _resolve_repo_root()
        week_dir = repo_root / "aiph2" / "weeks" / slug
        if not week_dir.exists():
            return _err(f"Nie znaleziono katalogu questa: {week_dir}")

        sections: list[tuple[str, str]] = []  # (filename, content)

        # Transcripts: prefer non-raw
        transcripts_dir = week_dir / "transcripts"
        if transcripts_dir.exists():
            preferred = transcripts_dir / "transcript.md"
            fallback = transcripts_dir / "transcript-raw.md"
            chosen = preferred if preferred.exists() else (fallback if fallback.exists() else None)
            if chosen is not None:
                try:
                    sections.append((f"transcripts/{chosen.name}", chosen.read_text(encoding="utf-8")))
                except Exception as e:  # noqa: BLE001
                    sections.append((f"transcripts/{chosen.name}", f"[błąd odczytu: {e}]"))

        # Slides: all *.md
        slides_dir = week_dir / "slides"
        if slides_dir.exists():
            for slide_path in sorted(slides_dir.glob("*.md")):
                try:
                    sections.append((f"slides/{slide_path.name}", slide_path.read_text(encoding="utf-8")))
                except Exception as e:  # noqa: BLE001
                    sections.append((f"slides/{slide_path.name}", f"[błąd odczytu: {e}]"))

        # Materials: *.docx via python-docx
        materials_dir = week_dir / "materials"
        if materials_dir.exists():
            for docx_path in sorted(materials_dir.glob("*.docx")):
                try:
                    sections.append((f"materials/{docx_path.name}", _docx_to_text(docx_path)))
                except Exception as e:  # noqa: BLE001
                    sections.append((f"materials/{docx_path.name}", f"[błąd parsowania: {e}]"))

        inventory = ", ".join(f"{name} ({len(content)} chars)" for name, content in sections)
        header = f"Załadowano: {inventory}" if inventory else "Załadowano: (brak plików)"

        body_parts: list[str] = [header]
        for name, content in sections:
            body_parts.append(f"\n=== {name} ===\n\n{content}")
        full = "\n".join(body_parts)

        if len(full) > _QUEST_MATERIALS_CAP:
            total = len(full)
            full = full[:_QUEST_MATERIALS_CAP] + f"\n\n[... truncated, total was {total} chars ...]"

        return _ok(full)

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd ładowania materiałów: {e}")


_load_quest_materials_tool = tool(
    "load_quest_materials",
    "Wczytuje materiały questa: aiph2/weeks/<slug>/{transcripts,slides,materials}/. Preferuje transcript.md nad transcript-raw.md, parsuje .docx z materials/. Skraca do 80 000 znaków.",
    {"slug": str},
)(load_quest_materials)


# ---------------------------------------------------------------------------
# Tool 6: due_today
# ---------------------------------------------------------------------------

async def due_today(args: dict[str, Any]) -> dict[str, Any]:
    try:
        cards = sm2.due_cards()
        today = sm2.today()

        def sort_key(c):
            prio = int(c.meta.get("priority", 50))
            nxt = c.sm2.next_review or today
            return (prio, nxt)

        cards.sort(key=sort_key)

        if not cards:
            return _ok("Brak kart do powtórki dziś.")

        lines = [f"Karty do powtórki dziś ({len(cards)}):"]
        for i, c in enumerate(cards, 1):
            sm = c.sm2
            prio = int(c.meta.get("priority", 50))
            nxt = sm.next_review.isoformat() if sm.next_review else "-"
            tags = ", ".join(c.tags) or "-"
            lines.append(
                f"{i}. {c.id}\n"
                f"   {c.title}\n"
                f"   priority: {prio}  next: {nxt}  reps: {sm.reps}  ease: {sm.ease:.2f}  interval: {sm.interval}d\n"
                f"   tags: {tags}"
            )
        return _ok("\n".join(lines))
    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd listy zaległych: {e}")


_due_today_tool = tool(
    "due_today",
    "Zwraca karty zaległe do powtórki dziś. Sortuje po priorytecie rosnąco (0 = na górze), potem po next_review.",
    {},
)(due_today)


# ---------------------------------------------------------------------------
# Tool 7: record_review
# ---------------------------------------------------------------------------

async def record_review(args: dict[str, Any]) -> dict[str, Any]:
    try:
        card_id = args["card_id"]
        grade = int(args["grade"])
        note = args.get("note", "") or ""

        if grade < 0 or grade > 5:
            return _err(f"Ocena musi być w zakresie 0-5 (otrzymano: {grade}).")

        path = sm2.CARDS_DIR / f"{card_id}.md"
        if not path.exists():
            return _err(f"Nie znaleziono karty: {card_id}")

        card = sm2.load_card(path)
        sm = card.sm2.review(grade)
        card.meta["sm2"] = sm.to_dict()

        if note:
            stamp = f"\n\n> _review {sm.last_review.isoformat()} (grade {grade}): {note}_"
            card.body = card.body.rstrip() + stamp + "\n"

        card.save()
        sm2.export_index()
        return _ok(
            f"Powtórzone: {card.id}, ocena {grade}, następna: {sm.next_review.isoformat()} "
            f"(ease {sm.ease:.2f}, interval {sm.interval}d, reps {sm.reps})"
        )
    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd zapisu powtórki: {e}")


_record_review_tool = tool(
    "record_review",
    "Zapisuje ocenę powtórki (0-5) i przelicza harmonogram SM-2. Ocena <3 to zapomnienie (interwał resetowany do 1 dnia).",
    {
        "card_id": str,
        "grade": int,
        "note": str,
    },
)(record_review)


# ---------------------------------------------------------------------------
# Tool 8: list_cards
# ---------------------------------------------------------------------------

async def list_cards(args: dict[str, Any]) -> dict[str, Any]:
    try:
        cards = sm2.all_cards()

        quest = (args.get("quest") or "").strip()
        tag = (args.get("tag") or "").strip()
        ctype = (args.get("type") or "").strip()
        query = (args.get("query") or "").strip().lower()

        if quest:
            cards = [c for c in cards if (c.quest or "").startswith(quest)]
        if tag:
            cards = [c for c in cards if tag in c.tags]
        if ctype:
            cards = [c for c in cards if c.type == ctype]
        if query:
            cards = [c for c in cards if query in c.title.lower() or query in c.body.lower()]

        parent = (args.get("parent_id") or "").strip()
        if parent:
            cards = [c for c in cards if (c.meta.get("parent_id") or "") == parent]

        if not cards:
            return _ok("Brak kart pasujących do filtrów.")

        lines = [f"Karty ({len(cards)}):"]
        for c in cards:
            lines.append(sm2.fmt_card_short(c))
        return _ok("\n".join(lines))

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd listy kart: {e}")


_list_cards_tool = tool(
    "list_cards",
    "Listuje karty z opcjonalnymi filtrami: quest (przedrostek), tag (dokładne dopasowanie), type (dokładne dopasowanie), query (podciąg w tytule/treści), parent_id (dokładne dopasowanie).",
    {
        "quest": str,
        "tag": str,
        "type": str,
        "query": str,
        "parent_id": str,
    },
)(list_cards)


# ---------------------------------------------------------------------------
# Tool 9: export_anki
# ---------------------------------------------------------------------------

def _extract_korekta(runda_text: str) -> str:
    """Pull the 'Korekta / dopowiedzenie' line(s) from a Runda dialogu block."""
    if not runda_text:
        return ""
    lines = runda_text.splitlines()
    out: list[str] = []
    capturing = False
    for line in lines:
        low = line.lower()
        if "korekta" in low or "dopowiedzenie" in low:
            stripped = line
            if "**" in stripped:
                no_bold = stripped.replace("**", "")
                if ":" in no_bold:
                    no_bold = no_bold.split(":", 1)[1]
                stripped = no_bold.strip()
            else:
                stripped = stripped.strip()
            out.append(stripped)
            capturing = True
            continue
        if capturing:
            if line.strip().startswith("**") or not line.strip():
                capturing = False
                continue
            out.append(line.strip())
    return " ".join(s for s in out if s).strip()


def _csv_escape(s: str) -> str:
    """Anki TSV: replace newlines with <br>, strip TAB and CR."""
    if not s:
        return ""
    return s.replace("\r", " ").replace("\t", " ").replace("\n", "<br>")


def _extract_section(body: str, heading: str) -> str:
    """Returns text of the ## {heading} section up to the next ## or end of string."""
    lines = body.splitlines()
    collecting = False
    result: list[str] = []
    for line in lines:
        if line.strip() == f"## {heading}":
            collecting = True
            continue
        if collecting:
            if line.startswith("## "):
                break
            result.append(line)
    return "\n".join(result).strip()


async def export_anki(args: dict[str, Any]) -> dict[str, Any]:
    try:
        filename = (args.get("filename") or "anki-export").strip() or "anki-export"
        scope = (args.get("scope") or "all").strip() or "all"

        if scope == "all":
            cards = sm2.all_cards()
        elif scope == "due":
            cards = sm2.due_cards()
        elif scope.startswith("quest:"):
            quest_filter = scope.split(":", 1)[1].strip()
            cards = [c for c in sm2.all_cards() if (c.quest or "").startswith(quest_filter)]
        else:
            return _err(f"Nieznany scope: {scope} (oczekiwane: all | due | quest:<nazwa>)")

        env = os.environ.get("AIPH2_LEARNING_DIR")
        base = Path(env) if env else sm2.LEARNING_DIR
        out_dir = base / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        if not filename.endswith(".csv"):
            filename = f"{filename}.csv"
        out_path = out_dir / filename

        rows: list[str] = []
        for c in cards:
            if c.type == "cloze":
                front_text = _extract_section(c.body, "Pytanie")
                back_text  = _extract_section(c.body, "Odpowiedź")
                rows.append("\t".join([
                    _csv_escape(front_text),
                    _csv_escape(back_text),
                    _csv_escape(",".join(c.tags)),
                ]))
                continue

            parsed = card_io.parse_body(c.body)
            kontekst = parsed.get("kontekst", "") or ""
            sedno = parsed.get("sedno", "") or ""
            pytanie = parsed.get("pytanie_sprawdzajace", "") or ""
            element_review = parsed.get("element_review", "") or ""
            runda = parsed.get("runda_dialogu", "") or ""
            source_quote = c.meta.get("source_quote") or parsed.get("source_quote", "") or ""

            korekta = _extract_korekta(runda)

            front = (
                f"Kontekst:\n{kontekst}\n\n"
                f"Cytat:\n{source_quote}\n\n"
                f"Pytanie:\n{pytanie}"
            )
            back = (
                f"{sedno}\n\n"
                f"Korekta z rundy:\n{korekta}\n\n"
                f"Element review:\n{element_review}"
            )
            tags_field = ",".join(c.tags)

            rows.append(
                "\t".join(
                    [
                        _csv_escape(front),
                        _csv_escape(back),
                        _csv_escape(tags_field),
                    ]
                )
            )

        out_path.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
        return _ok(f"Wyeksportowano {len(rows)} kart do {out_path}")

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd eksportu Anki: {e}")


_export_anki_tool = tool(
    "export_anki",
    "Eksportuje karty do CSV (rozdzielonego tabulatorami) zgodnego z Anki. scope: 'all' | 'due' | 'quest:<nazwa>'. Przód = Kontekst+Cytat+Pytanie. Tył = Sedno+Korekta+Element review.",
    {
        "filename": str,
        "scope": str,
    },
)(export_anki)


# ---------------------------------------------------------------------------
# Tool 10: load_learning_material
# ---------------------------------------------------------------------------

_LEARNING_MATERIAL_CAP = 80_000


async def load_learning_material(args: dict[str, Any]) -> dict[str, Any]:
    try:
        file_path = args["file_path"]
        path = Path(file_path)
        if not path.exists():
            return _err(f"Plik nie istnieje: {file_path}")
        if not path.is_file():
            return _err(f"Nie jest plikiem: {file_path}")

        if path.suffix.lower() == ".docx":
            content = _docx_to_text(path)
        else:
            content = path.read_text(encoding="utf-8")

        truncated = False
        total = len(content)
        if total > _LEARNING_MATERIAL_CAP:
            content = content[:_LEARNING_MATERIAL_CAP]
            truncated = True

        header = f"=== Plik: {path.name} ({total} chars, {len(content.splitlines())} widocznych linii) ==="
        body = f"{header}\n\n{content}"
        if truncated:
            body += f"\n\n[... truncated, total was {total} chars ...]"
        return _ok(body)

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd ładowania pliku: {e}")


_load_learning_material_tool = tool(
    "load_learning_material",
    "Ładuje pojedynczy plik (tekst lub .docx) do nauki. Automatyczna detekcja typu po rozszerzeniu. Skraca do 80 000 znaków.",
    {"file_path": str},
)(load_learning_material)


# ---------------------------------------------------------------------------
# Tool 11: wikipedia_lookup
# ---------------------------------------------------------------------------

async def wikipedia_lookup(args: dict[str, Any]) -> dict[str, Any]:
    from modules.wikipedia import lookup as _wiki_lookup

    title = (args.get("title") or "").strip()
    if not title:
        return _err("Brak parametru 'title'.")

    lang = (args.get("lang") or "auto").strip()
    if lang not in {"auto", "pl", "en"}:
        return _err(f"Nieprawidłowa wartość 'lang': {lang!r}. Dozwolone: auto, pl, en.")

    try:
        branches = int(args.get("branches", 3))
    except (TypeError, ValueError):
        branches = 3
    branches = max(0, min(8, branches))

    mode = (args.get("mode") or "full").strip()
    if mode not in {"full", "summary-only", "branches-only"}:
        return _err(f"Nieprawidłowa wartość 'mode': {mode!r}. Dozwolone: full, summary-only, branches-only.")

    try:
        result = await _wiki_lookup(title, lang=lang, branches=branches, mode=mode)
    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd pobierania z Wikipedii: {e}")

    if not result.get("ok"):
        notes = result.get("notes", "")
        return _err(f"Wikipedia nie ma hasła '{title}'. {notes}".strip())

    lines: list[str] = []

    summary = result.get("summary")
    if summary:
        lines.append(f"### Streszczenie: {summary['title']}")
        lines.append(f"*Źródło: [{summary['url']}]({summary['url']}) ({summary['lang'].upper()})*")
        if result.get("notes"):
            lines.append(f"*{result['notes']}*")
        lines.append("")
        lines.append(summary.get("extract", ""))

    result_branches = result.get("branches", [])
    if result_branches:
        lines.append("")
        lines.append("### Powiązane hasła")
        for b in result_branches:
            lines.append(f"- **[{b['title']}]({b['url']})** — {b.get('summary', '')}")

    markdown_part = "\n".join(lines)

    # JSON block for the agent to parse into wikipedia_branches
    branches_json = json.dumps(result_branches, ensure_ascii=False)
    full_output = f"{markdown_part}\n\n--- JSON ---\n{branches_json}"

    if len(full_output) > 6000:
        full_output = full_output[:5997] + "..."

    return _ok(full_output)


_wikipedia_lookup_tool = tool(
    "wikipedia_lookup",
    "Pobiera streszczenie i powiązane hasła z Wikipedii (pl z fallbackiem na en). "
    "Używaj do rozszerzenia sekcji 'Szersza perspektywa' i generowania gałęzi wiedzy. "
    "Wynik zawiera markdown + blok JSON z listą gałęzi (do wikipedia_branches w add_card_full).",
    {
        "title": str,
        "lang": str,
        "branches": int,
        "mode": str,
    },
)(wikipedia_lookup)


# ---------------------------------------------------------------------------
# Tool 12: read_card
# ---------------------------------------------------------------------------


async def read_card(args: dict[str, Any]) -> dict[str, Any]:
    try:
        card_id = (args.get("card_id") or "").strip()
        if not card_id:
            return _err("Brak card_id.")
        path = sm2.CARDS_DIR / f"{card_id}.md"
        if not path.exists():
            return _err(f"Nie znaleziono karty: {card_id}")
        card = sm2.load_card(path)
        parent_line = ""
        pid = card.meta.get("parent_id")
        if pid:
            parent_line = f"\n**Karta-rodzic:** {pid}"
        header = (
            f"**ID:** {card.id}\n"
            f"**Tytuł:** {card.title}\n"
            f"**Type:** {card.type}\n"
            f"**Quest:** {card.quest or '-'}\n"
            f"**Tags:** {', '.join(card.tags) or '-'}\n"
            f"**SM-2:** next={card.sm2.next_review} reps={card.sm2.reps} ease={card.sm2.ease:.2f}"
            f"{parent_line}"
        )
        return _ok(f"{header}\n\n---\n\n{card.body}")
    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd odczytu karty: {e}")


_read_card_tool = tool(
    "read_card",
    "Ładuje pełną kartę (frontmatter + body) po card_id. Używany do nawigacji: /tree, /parent, podgląd kontekstu podczas review.",
    {"card_id": str},
)(read_card)


# ---------------------------------------------------------------------------
# Tool 13: add_clozes
# ---------------------------------------------------------------------------


async def add_clozes(args: dict[str, Any]) -> dict[str, Any]:
    try:
        import json as _json
        parent_id = (args.get("parent_id") or "").strip()
        if not parent_id:
            return _err("Brak parent_id.")
        parent_path = sm2.CARDS_DIR / f"{parent_id}.md"
        if not parent_path.exists():
            return _err(f"Nie znaleziono karty-rodzica: {parent_id}")
        parent = sm2.load_card(parent_path)

        # Inherit from parent
        source_path = (args.get("source_path") or parent.meta.get("source") or "").strip()
        tags_csv = args.get("tags") or ",".join(parent.tags)
        tags = [t.strip() for t in tags_csv.split(",") if t.strip()]
        if "cloze" not in tags:
            tags.append("cloze")
        priority = int(args.get("priority") or parent.meta.get("priority") or 50)
        difficulty = (args.get("difficulty") or parent.meta.get("difficulty") or "medium").strip()

        clozes_raw = args.get("clozes") or "[]"
        try:
            clozes_list = _json.loads(clozes_raw)
        except _json.JSONDecodeError as e:
            return _err(f"'clozes' musi być JSON-listą obiektów {{front, back}}: {e}")
        if not isinstance(clozes_list, list) or not clozes_list:
            return _err("'clozes': oczekiwana niepusta lista obiektów {front, back}.")

        created_ids: list[str] = []
        n = len(clozes_list)
        for idx, c in enumerate(clozes_list, 1):
            front = (c.get("front") or "").strip()
            back = (c.get("back") or "").strip()
            if not front or not back:
                return _err(f"Cloze #{idx}: 'front' i 'back' są wymagane i niepuste.")
            cc = ClozeCard(
                title=f"{parent.title} [cloze {idx}/{n}]",
                parent_id=parent_id,
                front=front,
                back=back,
                source_path=source_path,
                tags=tags,
                priority=priority,
                difficulty=difficulty,
            )
            body = card_io.build_cloze_body(cc)
            card = sm2.write_new_card(
                title=cc.title,
                body=body,
                type="cloze",
                source=cc.source_path,
                quest=parent.quest or None,
                tags=cc.tags,
                difficulty=cc.difficulty,
                priority=cc.priority,
                extra={"parent_id": parent_id},
            )
            created_ids.append(card.id)

        sm2.export_index()
        return _ok(f"Zapisano {len(created_ids)} cloze'ów: " + ", ".join(created_ids))

    except Exception as e:  # noqa: BLE001
        return _err(f"Błąd zapisu cloze'ów: {e}")


_add_clozes_tool = tool(
    "add_clozes",
    "Tworzy N kart 'cloze' (proste Q&A, bez limitu) podpiętych przez parent_id. 'clozes' to JSON-lista {front, back}. Tagi/priority/difficulty dziedziczą z rodzica gdy puste.",
    {
        "parent_id": str,
        "clozes": str,       # JSON: [{"front": "...", "back": "..."}, ...]
        "source_path": str,
        "tags": str,
        "priority": int,
        "difficulty": str,
    },
)(add_clozes)


# ---------------------------------------------------------------------------
# Server assembly
# ---------------------------------------------------------------------------

learning_tools_server = create_sdk_mcp_server(
    name="learning-tools",
    version="1.0.0",
    tools=[
        _add_card_full_tool,
        _save_dialog_round_tool,
        _record_interest_tool,
        _read_interest_profile_tool,
        _load_quest_materials_tool,
        _due_today_tool,
        _record_review_tool,
        _list_cards_tool,
        _export_anki_tool,
        _load_learning_material_tool,
        _wikipedia_lookup_tool,
        _read_card_tool,
        _add_clozes_tool,
    ],
)


__all__ = [
    "learning_tools_server",
    "add_card_full",
    "save_dialog_round",
    "record_interest",
    "read_interest_profile",
    "load_quest_materials",
    "due_today",
    "record_review",
    "list_cards",
    "export_anki",
    "load_learning_material",
    "wikipedia_lookup",
    "read_card",
    "add_clozes",
]

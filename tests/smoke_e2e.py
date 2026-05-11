#!/usr/bin/env python3
"""End-to-end smoke test for the AIPH2 active learning agent.

Covers acceptance criteria 4, 5 (partial), 6, 7, 8, 9.

Sets AIPH2_LEARNING_DIR to /tmp/aiph2-learning-test/ before importing
modules.sm2 so card paths land in the test directory. Cleans up the test
directory at the end.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import importlib
import json as _json
import os
import shutil
import sys
from pathlib import Path

TEST_DIR = Path("/tmp/aiph2-learning-test")


def _ensure_clean_dir() -> None:
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR)
    TEST_DIR.mkdir(parents=True, exist_ok=True)


def _setup_imports():
    """Set env var, then (re)import modules so LEARNING_DIR picks it up."""
    os.environ["AIPH2_LEARNING_DIR"] = str(TEST_DIR)
    # If sm2 was already imported, reload so module-level LEARNING_DIR refreshes.
    if "modules.sm2" in sys.modules:
        importlib.reload(sys.modules["modules.sm2"])
    if "modules.tools" in sys.modules:
        importlib.reload(sys.modules["modules.tools"])
    if "modules.interest" in sys.modules:
        importlib.reload(sys.modules["modules.interest"])
    if "modules.card_io" in sys.modules:
        importlib.reload(sys.modules["modules.card_io"])
    # Fresh imports
    from modules import sm2 as _sm2  # noqa: F401
    from modules import tools as _tools  # noqa: F401


REQUIRED_FRONTMATTER_KEYS = {
    "id",
    "title",
    "type",
    "tags",
    "priority",
    "difficulty",
    "created",
    "sm2",
    "source",  # alias for source_path; sm2.write_new_card writes "source" key
    "source_quote",
}

REQUIRED_SECTIONS = [
    "## Kontekst",
    "## Sedno",
    "## Konkret / Przykład",
    "## Cytat źródłowy",
    "## Runda dialogu",
    "## Dlaczego",
    "## Szersza perspektywa",
    "## Pytanie sprawdzające",
    "## Element review",
    "## Powiązane karty",
    "## Notatki własne",
]


def _full_payload(title: str = "Test card title") -> dict:
    return {
        "title": title,
        "type": "concept",
        "quest": "test-quest",
        "tags": "alpha,beta",
        "source_path": "fixtures/source.md",
        "source_quote": "To jest dosłowny cytat ze źródła testowego.",
        "kontekst": "Kontekst testowy: rozważamy scenariusz X.",
        "sedno": "Sedno: kluczowa idea sprowadza się do Y.",
        "konkret": "Konkret: w przypadku firmy A wskaźnik spadł z 38% do 32%.",
        "why_tradeoff_pitfall": "Why: bo Z. Tradeoff: koszt P. Pitfall: pomijanie sygnału S.",
        "szersza_perspektywa": "W Lean Startup byłoby to nazywane 'pivot'.",
        "runda_dialogu": "**Agent zapytał:** co to jest? **Odpowiedziałeś:** to A. **Korekta:** raczej B.",
        "pytanie_sprawdzajace": "Jak rozpoznasz, że twój zespół zaniedbuje krok X?",
        "element_review": "Mnemonik: 3xR (Recognize, Rebuild, Review).",
        "powiazane": "[[2026-05-08-super-loop-frame-sygnal-testowalna-hipoteza]]",
        "priority": 50,
        "difficulty": "medium",
    }


async def main() -> int:
    _ensure_clean_dir()
    _setup_imports()

    import frontmatter  # noqa: WPS433
    from modules import sm2 as sm2_mod
    from modules.tools import (  # noqa: WPS433
        add_card_full,
        record_review,
        record_interest,
        export_anki,
        list_cards,
        read_card,
        add_clozes,
    )

    # Sanity: env applied
    assert sm2_mod.LEARNING_DIR == TEST_DIR, (
        f"LEARNING_DIR mismatch: {sm2_mod.LEARNING_DIR} != {TEST_DIR}"
    )

    # ---------- 1. add_card_full happy path ----------
    payload = _full_payload()
    res = await add_card_full(payload)
    assert res.get("is_error") is not True, f"add_card_full failed: {res}"

    cards_dir = TEST_DIR / "cards"
    assert cards_dir.exists(), f"cards dir not created: {cards_dir}"

    card_files = list(cards_dir.glob("*.md"))
    assert len(card_files) == 1, f"expected 1 card file, got {len(card_files)}: {card_files}"
    card_path = card_files[0]

    post = frontmatter.load(card_path)
    fm = dict(post.metadata)

    missing_keys = REQUIRED_FRONTMATTER_KEYS - set(fm.keys())
    assert not missing_keys, f"frontmatter missing keys: {missing_keys}; got: {sorted(fm.keys())}"

    body = post.content
    for section in REQUIRED_SECTIONS:
        assert section in body, f"missing section in body: {section!r}"

    card_id = fm["id"]
    print(f"[smoke] add_card_full ok, id={card_id}")

    # ---------- 2. record_review SM-2 update ----------
    review_res = await record_review({"card_id": card_id, "grade": 4})
    assert review_res.get("is_error") is not True, f"record_review failed: {review_res}"

    post2 = frontmatter.load(card_path)
    sm = post2.metadata.get("sm2", {})
    assert int(sm.get("reps", 0)) >= 1, f"reps did not increment: {sm}"
    nxt = sm.get("next_review")
    assert nxt, "next_review missing after review"
    nxt_date = dt.date.fromisoformat(nxt) if isinstance(nxt, str) else nxt
    assert nxt_date > dt.date.today(), f"next_review not in future: {nxt_date}"
    print(f"[smoke] record_review ok, reps={sm['reps']}, next_review={nxt_date}")

    # ---------- 3. record_interest ----------
    int_res = await record_interest(
        {"topic": "test-topic", "signal": "+test", "weight_delta": -10}
    )
    assert int_res.get("is_error") is not True, f"record_interest failed: {int_res}"

    profile_path = TEST_DIR / "interest-profile.md"
    assert profile_path.exists(), f"interest profile not created: {profile_path}"

    profile_post = frontmatter.load(profile_path)
    topics = profile_post.metadata.get("topics") or []
    found = next((t for t in topics if t.get("name") == "test-topic"), None)
    assert found is not None, f"topic 'test-topic' not in profile: {topics}"
    assert int(found["priority"]) == 40, (
        f"priority should be 50-10=40, got {found['priority']}"
    )
    print(f"[smoke] record_interest ok, priority={found['priority']}")

    # ---------- 4. export_anki ----------
    exp_res = await export_anki({"filename": "smoke", "scope": "all"})
    assert exp_res.get("is_error") is not True, f"export_anki failed: {exp_res}"

    csv_path = TEST_DIR / "exports" / "smoke.csv"
    assert csv_path.exists(), f"export csv not written: {csv_path}"

    csv_lines = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) >= 1, f"csv has no rows: {csv_path}"
    fields = csv_lines[0].split("\t")
    assert len(fields) == 3, (
        f"first row should be 3 TAB-separated fields, got {len(fields)}: {fields[:1]}"
    )
    print(f"[smoke] export_anki ok, rows={len(csv_lines)}, fields={len(fields)}")

    # ---------- 5. Citation guard: empty source_quote ----------
    bad1 = _full_payload(title="missing source_quote")
    bad1["source_quote"] = ""
    bad1_res = await add_card_full(bad1)
    assert bad1_res.get("is_error") is True, (
        f"guard did not fire on empty source_quote: {bad1_res}"
    )
    print("[smoke] guard ok: empty source_quote rejected")

    # ---------- 6. Citation guard: empty pytanie_sprawdzajace ----------
    bad2 = _full_payload(title="missing pytanie")
    bad2["pytanie_sprawdzajace"] = ""
    bad2_res = await add_card_full(bad2)
    assert bad2_res.get("is_error") is True, (
        f"guard did not fire on empty pytanie_sprawdzajace: {bad2_res}"
    )
    print("[smoke] guard ok: empty pytanie_sprawdzajace rejected")

    # ---------- 7. add_clozes happy path (8 cloze — brak górnego limitu) ----------
    big_batch = [
        {"front": f"Pytanie numer {i}?", "back": f"Odpowiedz {i}"}
        for i in range(1, 9)
    ]
    cloze_res = await add_clozes({
        "parent_id": card_id,
        "clozes": _json.dumps(big_batch),
    })
    assert cloze_res.get("is_error") is not True, f"add_clozes failed: {cloze_res}"
    all_files = list((TEST_DIR / "cards").glob("*.md"))
    cloze_cards = [
        frontmatter.load(p) for p in all_files
        if frontmatter.load(p).metadata.get("type") == "cloze"
    ]
    assert len(cloze_cards) == 8, f"expected 8 cloze cards, got {len(cloze_cards)}"
    for cc in cloze_cards:
        m = cc.metadata
        assert m.get("parent_id") == card_id, f"wrong parent_id: {m.get('parent_id')}"
        assert "sm2" in m and m["sm2"].get("next_review"), f"missing sm2: {m}"
        assert "cloze" in (m.get("tags") or []), f"tag 'cloze' missing: {m.get('tags')}"
        body = cc.content
        assert "## Pytanie" in body, f"missing ## Pytanie in cloze body"
        assert "## Odpowiedź" in body, f"missing ## Odpowiedź in cloze body"
        assert "## Karta-rodzic" in body, f"missing ## Karta-rodzic in cloze body"
        # Body must not contain parent context text
        assert "Kontekst testowy" not in body, "cloze body should NOT copy parent context"
    print("[smoke] add_clozes ok, 8 cloze cards, no parent text leaked")

    # ---------- 8. list_cards filter parent_id ----------
    lc = await list_cards({"parent_id": card_id})
    assert lc.get("is_error") is not True
    lc_text = lc["content"][0]["text"]
    assert "cloze" in lc_text.lower(), f"no cloze in list_cards parent filter: {lc_text[:200]}"
    print("[smoke] list_cards parent_id ok")

    # ---------- 9. read_card ----------
    rc = await read_card({"card_id": card_id})
    assert rc.get("is_error") is not True, f"read_card failed: {rc}"
    rc_text = rc["content"][0]["text"]
    assert card_id in rc_text, f"card_id not in read_card output"
    assert "Sedno" in rc_text or "Pytanie sprawdzające" in rc_text, "read_card seems wrong"
    print("[smoke] read_card ok")

    # read_card for cloze — should show parent_id line
    first_cloze_id = cloze_cards[0].metadata["id"]
    rc2 = await read_card({"card_id": first_cloze_id})
    assert rc2.get("is_error") is not True
    rc2_text = rc2["content"][0]["text"]
    assert card_id in rc2_text, "parent_id not shown in read_card output for cloze"
    print("[smoke] read_card cloze (parent_id visible) ok")

    # ---------- 10. export_anki cloze branch ----------
    exp2 = await export_anki({"filename": "smoke-cloze", "scope": "all"})
    assert exp2.get("is_error") is not True
    csv2 = (TEST_DIR / "exports" / "smoke-cloze.csv").read_text(encoding="utf-8")
    rows_all = [r for r in csv2.strip().splitlines() if r.strip()]
    # 1 rich card + 8 cloze = 9 rows
    assert len(rows_all) == 9, f"expected 9 rows, got {len(rows_all)}: {rows_all}"
    print(f"[smoke] export_anki cloze branch ok ({len(rows_all)} rows)")

    # ---------- 11. Guard: empty front ----------
    bcr = await add_clozes({
        "parent_id": card_id,
        "clozes": _json.dumps([{"front": "", "back": "x"}]),
    })
    assert bcr.get("is_error") is True, "guard nie zadziałał na pusty front"
    print("[smoke] guard ok: empty cloze front rejected")

    print("PASS")
    return 0


def _cleanup() -> None:
    if TEST_DIR.exists():
        shutil.rmtree(TEST_DIR, ignore_errors=True)


if __name__ == "__main__":
    keep = "--keep" in sys.argv
    try:
        rc = asyncio.run(main())
    except AssertionError as e:
        print(f"FAIL: {e}")
        if not keep:
            _cleanup()
        sys.exit(1)
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: unexpected error: {e}")
        if not keep:
            _cleanup()
        sys.exit(2)
    if not keep:
        _cleanup()
    sys.exit(rc)

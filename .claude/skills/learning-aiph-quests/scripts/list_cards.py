#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-frontmatter>=1.0", "PyYAML>=6.0"]
# ///
"""List/filter cards.

Examples:
    list_cards.py
    list_cards.py --quest quest-1.3-from-zero-to-demo
    list_cards.py --tag superhero-formula
    list_cards.py --type side-question
    list_cards.py --query lovable
    list_cards.py --json
"""
from __future__ import annotations

import argparse
import json

import sm2_lib as sl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quest", default=None)
    ap.add_argument("--tag", default=None)
    ap.add_argument("--type", default=None)
    ap.add_argument("--query", default=None, help="Substring match in title or body (case-insensitive)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cards = sl.all_cards()
    if args.quest:
        cards = [c for c in cards if (c.quest or "").startswith(args.quest)]
    if args.tag:
        cards = [c for c in cards if args.tag in c.tags]
    if args.type:
        cards = [c for c in cards if c.type == args.type]
    if args.query:
        q = args.query.lower()
        cards = [c for c in cards if q in c.title.lower() or q in c.body.lower()]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "id": c.id,
                        "title": c.title,
                        "type": c.type,
                        "quest": c.quest,
                        "tags": c.tags,
                        "next_review": c.sm2.next_review.isoformat() if c.sm2.next_review else None,
                    }
                    for c in cards
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"== {len(cards)} cards ==")
    for c in cards:
        print(sl.fmt_card_short(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

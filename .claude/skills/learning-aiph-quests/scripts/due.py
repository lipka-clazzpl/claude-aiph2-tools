#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-frontmatter>=1.0", "PyYAML>=6.0"]
# ///
"""Show cards due for review today (or by --on YYYY-MM-DD).

Examples:
    due.py
    due.py --on 2026-05-15
    due.py --upcoming 7         # also show next 7 days
    due.py --json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import sm2_lib as sl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--on", default=None, help="Date YYYY-MM-DD (default today)")
    ap.add_argument("--upcoming", type=int, default=0, help="Show N days ahead too")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    when = dt.date.fromisoformat(args.on) if args.on else sl.today()
    due = sl.due_cards(when=when)
    upcoming: list = []
    if args.upcoming > 0:
        horizon = when + dt.timedelta(days=args.upcoming)
        for c in sl.all_cards():
            nxt = c.sm2.next_review
            if nxt and when < nxt <= horizon:
                upcoming.append(c)

    if args.json:
        print(
            json.dumps(
                {
                    "on": when.isoformat(),
                    "due": [
                        {"id": c.id, "title": c.title, "next_review": c.sm2.next_review.isoformat() if c.sm2.next_review else None}
                        for c in due
                    ],
                    "upcoming": [
                        {"id": c.id, "title": c.title, "next_review": c.sm2.next_review.isoformat() if c.sm2.next_review else None}
                        for c in upcoming
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    print(f"== DUE on {when.isoformat()} ({len(due)} cards) ==")
    for c in due:
        print(sl.fmt_card_short(c))
    if upcoming:
        print(f"\n== UPCOMING within {args.upcoming}d ({len(upcoming)} cards) ==")
        for c in sorted(upcoming, key=lambda x: x.sm2.next_review or when):
            print(sl.fmt_card_short(c))
    if not due and not upcoming:
        print("  (nothing due)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

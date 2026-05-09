#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-frontmatter>=1.0", "PyYAML>=6.0"]
# ///
"""Record a review grade (0..5) and reschedule via SM-2.

Grades (SM-2):
  0 — total blackout
  1 — incorrect; correct one remembered after seeing it
  2 — incorrect; correct one seemed easy in hindsight
  3 — correct with serious difficulty
  4 — correct after hesitation
  5 — perfect recall

<3 is a lapse: interval resets to 1 day. >=3 progresses the schedule.

Examples:
    review.py --id 2026-05-08-customer-curiosity --grade 4
    review.py --id 2026-05-08-customer-curiosity --grade 1 --note "pomyliłem z product taste"
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import sm2_lib as sl


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True, help="Card id (filename without .md)")
    ap.add_argument("--grade", required=True, type=int, choices=list(range(6)))
    ap.add_argument("--on", default=None, help="Override review date YYYY-MM-DD")
    ap.add_argument("--note", default=None, help="Optional one-line note appended to card body")
    args = ap.parse_args()

    path = sl.CARDS_DIR / f"{args.id}.md"
    if not path.exists():
        print(f"ERR: card not found: {path}", file=sys.stderr)
        return 2
    card = sl.load_card(path)
    when = dt.date.fromisoformat(args.on) if args.on else sl.today()
    sm = card.sm2.review(args.grade, when=when)
    card.meta["sm2"] = sm.to_dict()

    if args.note:
        stamp = f"\n\n> _review {when.isoformat()} (grade {args.grade}): {args.note}_"
        card.body = card.body.rstrip() + stamp + "\n"

    card.save()
    sl.export_index()
    print(f"OK  {card.id}  grade={args.grade}  next_review={sm.next_review}  ease={sm.ease:.2f}  interval={sm.interval}d  reps={sm.reps}  lapses={sm.lapses}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

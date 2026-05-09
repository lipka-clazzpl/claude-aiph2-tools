#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["python-frontmatter>=1.0", "PyYAML>=6.0"]
# ///
"""Add a new incremental-learning card.

Body is read from --body, --body-file, or stdin.

Examples:
    add_card.py --title "Customer Curiosity" --type concept --quest quest-1.3 \\
                --tags superhero-formula,5-cech-buildera \\
                --source weeks/w1d2-2026-04-22-fundamenty/transcripts/transcript.md \\
                --body-file /tmp/body.md
    cat /tmp/body.md | add_card.py --title "Pytanie poboczne: Lovable Plan vs Build" \\
                --type side-question --quest quest-1.3 --tags lovable,plan-mode
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import sm2_lib as sl


def main() -> int:
    ap = argparse.ArgumentParser(description="Add an incremental-learning card")
    ap.add_argument("--title", required=True)
    ap.add_argument(
        "--type",
        default="concept",
        choices=[
            "concept",
            "framework",
            "example",
            "pitfall",
            "principle",
            "side-question",
            "quest-task",
            "tool",
            "qa",
        ],
    )
    ap.add_argument("--source", default=None, help="Path/URL to source material")
    ap.add_argument("--quest", default=None, help="Quest slug, e.g. quest-1.3-from-zero-to-demo")
    ap.add_argument("--tags", default="", help="Comma-separated tags")
    ap.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    ap.add_argument("--body", default=None, help="Inline body markdown")
    ap.add_argument("--body-file", default=None, help="Path to body markdown")
    args = ap.parse_args()

    if args.body and args.body_file:
        ap.error("use --body OR --body-file")
    if args.body:
        body = args.body
    elif args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    else:
        body = sys.stdin.read()
    if not body.strip():
        ap.error("body is empty")

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]

    card = sl.write_new_card(
        title=args.title,
        body=body,
        type=args.type,
        source=args.source,
        quest=args.quest,
        tags=tags,
        difficulty=args.difficulty,
    )
    sl.export_index()
    print(f"OK  {card.id}")
    print(f"     {card.path.relative_to(sl.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

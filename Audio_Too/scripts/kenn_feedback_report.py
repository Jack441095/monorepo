#!/usr/bin/env python3
"""Print recent KENN tester feedback from the shared demo feedback table."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "business" / "app"
if str(WEBSITE) not in sys.path:
    sys.path.insert(0, str(WEBSITE))

import demo_feedback  # noqa: E402

KENN_CHANNELS = {"main_chat", "mix_review"}


def clean_line(value: object, *, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}..."


def main() -> int:
    parser = argparse.ArgumentParser(description="Show recent KENN tester feedback.")
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows to show.")
    parser.add_argument("--all", action="store_true", help="Include non-KENN demo feedback channels.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a readable report.")
    args = parser.parse_args()

    rows = demo_feedback.list_feedback(limit=max(1, args.limit))
    if not args.all:
        rows = [row for row in rows if str(row.get("channel", "")) in KENN_CHANNELS]

    if args.json:
        print(json.dumps(rows, indent=2, ensure_ascii=True))
        return 0

    if not rows:
        print("No KENN tester feedback found yet.")
        return 0

    print(f"Recent KENN tester feedback ({len(rows)} rows)")
    print("")
    for row in rows:
        channel = str(row.get("channel") or "unknown")
        rating = str(row.get("rating") or "unrated")
        created = str(row.get("created_at") or "")
        print(f"- {row.get('id')} | {created} | {channel} | {rating}")
        print(f"  Q: {clean_line(row.get('question'))}")
        if row.get("comment"):
            print(f"  Note: {clean_line(row.get('comment'), limit=220)}")
        if row.get("issue_tags"):
            print(f"  Issues: {', '.join(str(item) for item in row.get('issue_tags') or [])}")
        if rating == "not_useful":
            print(f"  Repair: {row.get('repair_status') or 'open'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

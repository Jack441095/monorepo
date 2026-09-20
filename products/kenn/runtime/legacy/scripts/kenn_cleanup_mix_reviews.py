#!/usr/bin/env python3
"""Clean old KENN Mix Review uploads and reports."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "business" / "app"
ANALYSIS = ROOT / "studio" / "audio_analysis"
for path in (WEBSITE, ANALYSIS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from db import connect  # noqa: E402
from audio_analysis.mix_review import mix_review  # noqa: E402


def parse_created_at(value: str) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    return None


def candidate_rows(days: int) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=max(1, days))
    mix_review.init_reviews_table()
    with connect() as conn:
        rows = conn.execute("SELECT * FROM mix_reviews ORDER BY created_at ASC").fetchall()
    items = []
    for row in rows:
        item = dict(row)
        created = parse_created_at(str(item.get("created_at", "")))
        if created and created < cutoff:
            item["_created_dt"] = created
            items.append(item)
    return items


def paths_for(row: dict) -> list[Path]:
    paths: list[Path] = []
    stored = str(row.get("stored_name") or "").strip()
    report = str(row.get("report_name") or "").strip()
    review_id = str(row.get("id") or "").strip()
    if stored:
        paths.append(mix_review.UPLOAD_ROOT / stored)
    if report:
        paths.append(mix_review.REPORT_ROOT / report)
    if review_id:
        paths.extend(sorted(mix_review.UPLOAD_ROOT.glob(f"{review_id}_reference_*")))
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean old KENN Mix Review upload/report files.")
    parser.add_argument("--days", type=int, default=14, help="Delete reviews older than this many days.")
    parser.add_argument("--yes", action="store_true", help="Actually delete files and DB rows. Default is dry-run.")
    args = parser.parse_args()

    rows = candidate_rows(args.days)
    mode = "DELETE" if args.yes else "DRY RUN"
    print(f"{mode}: {len(rows)} mix review(s) older than {args.days} day(s).")
    if not rows:
        return 0

    removed_files = 0
    for row in rows:
        print(f"- {row.get('id')} | {row.get('created_at')} | {row.get('title') or row.get('original_name')}")
        for path in paths_for(row):
            exists = path.exists()
            print(f"  {'delete' if args.yes else 'would delete'} {path} {'(missing)' if not exists else ''}")
            if args.yes and exists:
                path.unlink()
                removed_files += 1

    if args.yes:
        ids = [str(row.get("id")) for row in rows if row.get("id")]
        with connect() as conn:
            conn.executemany("DELETE FROM mix_reviews WHERE id = ?", [(item,) for item in ids])
            conn.commit()

        # Also purge from the summary cache so the dashboard never shows stale entries
        from audio_analysis.mix_review.review_store import _delete_cached_summary  # noqa: E402
        for review_id in ids:
            _delete_cached_summary(review_id, connect)

        print(f"Removed {len(ids)} DB row(s) and {removed_files} file(s), cache purged.")
    else:
        print("Dry-run only. Re-run with --yes to delete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Mix Doctor — turn a stored mix review into a shareable HTML report.

This is the thin, offline front-end for plan.md §14.1 (Idea 1). It reads a
review the Mix Review engine already produced and writes a single
self-contained HTML file you can email a prospect or host anywhere. It never
uploads, never starts a server, and never touches the client's audio.

Usage:
    # From a stored review id (looked up in data/audio_too.db):
    python scripts/mix_doctor_report.py --id <review-id>

    # From a raw report JSON file (no database needed):
    python scripts/mix_doctor_report.py --report-json path/to/report.json

    # Choose an output path and a call-to-action link:
    python scripts/mix_doctor_report.py --id <id> \
        --out artifacts/mix_doctor/report.html \
        --cta-url "https://audio-too.example/enquire"

Exit status is non-zero on any failure so it can gate a script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
# The audio_analysis package lives under studio/; add it the same way the app does.
for _p in (REPO_ROOT / "studio" / "audio_analysis", REPO_ROOT / "business" / "app"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _load_review_from_id(review_id: str) -> dict:
    from audio_analysis.mix_review import mix_review

    status = mix_review.mix_review_status(review_id)
    if not status.get("ok"):
        raise SystemExit(f"Could not load review {review_id!r}: {status.get('error', 'unknown error')}")
    review = status.get("review")
    if not review:
        raise SystemExit(f"Review {review_id!r} is not completed yet (status: {status.get('status')}).")
    return review


def _load_review_from_json(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"Report JSON not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit(f"Could not read report JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Report JSON must be an object.")
    # Accept either a bare report or a {"review": {...}} wrapper.
    return data.get("review") if isinstance(data.get("review"), dict) else data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a shareable Mix Doctor HTML report.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--id", dest="review_id", help="Stored review id in the database.")
    source.add_argument("--report-json", dest="report_json", help="Path to a report JSON file.")
    parser.add_argument("--out", help="Output HTML path (default: artifacts/mix_doctor/<id>.html).")
    parser.add_argument("--brand", default="Audio_Too", help="Brand name shown in the report.")
    parser.add_argument("--cta-label", default="Get this mixed properly", help="Call-to-action button text.")
    parser.add_argument("--cta-url", default=None, help="Call-to-action link (email or URL).")
    args = parser.parse_args(argv)

    from audio_analysis.mix_review import mix_doctor

    if args.review_id:
        review = _load_review_from_id(args.review_id)
        default_stem = args.review_id
    else:
        review = _load_review_from_json(Path(args.report_json))
        default_stem = Path(args.report_json).stem or "report"

    render_kwargs = {"brand": args.brand, "cta_label": args.cta_label}
    if args.cta_url:
        render_kwargs["cta_url"] = args.cta_url
    html = mix_doctor.render_report_html(review, **render_kwargs)

    out_path = Path(args.out) if args.out else (REPO_ROOT / "artifacts" / "mix_doctor" / f"{default_stem}.html")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")

    head = mix_doctor.report_headline(review)
    print(f"Mix Doctor report written: {out_path}")
    print(f"  {head['title']} — {head['rating']}" + (f" ({head['score']}/100)" if head["score"] is not None else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

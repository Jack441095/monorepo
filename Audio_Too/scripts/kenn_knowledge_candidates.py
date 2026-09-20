#!/usr/bin/env python3
"""Draft KENN training-note candidates from Mix Review session reports and feedback."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KENN = ROOT / "studio" / "kenn" / "kenn"
NOTES = KENN / "Training_Data_Notes"
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
sys.path.insert(0, str(ROOT / "business" / "app"))

from audio_analysis.mix_review import mix_review  # noqa: E402
import demo_feedback  # noqa: E402


def slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return clean[:80] or "kenn-knowledge-candidate"


def lines_from_review(review: dict) -> list[str]:
    session = review.get("session_report") if isinstance(review.get("session_report"), dict) else {}
    metrics = review.get("metrics") if isinstance(review.get("metrics"), dict) else {}
    title = str(session.get("title") or review.get("title") or "Mix review").strip()
    mix_goal = metrics.get("mix_goal") if isinstance(metrics.get("mix_goal"), dict) else {}
    target = str(session.get("mix_target") or mix_goal.get("label", "")).strip()
    steps = session.get("v2_export_checklist") or []
    leave_alone = session.get("leave_alone") or []
    return [
        f"# {title} Session Report Lesson",
        "",
        "Type: Mix Review repair lesson",
        "Tags: mix_review, revision, ableton, feedback, repair",
        "Status: Draft",
        f"Source review: {review.get('id', '')}",
        "",
        "Short answer:",
        str(session.get("client_summary") or review.get("summary") or "Use this review to make one focused revision before changing the whole mix."),
        "",
        "Key ideas:",
        f"- Target context: {target or 'unspecified'}",
        f"- Fix first: {session.get('fix_first', '')}",
        f"- Fix next: {session.get('fix_next', '')}",
        "",
        "Try this:",
        *[f"{idx}. {item}" for idx, item in enumerate(steps[:5], start=1)],
        "",
        "Leave alone:",
        *[f"- {item}" for item in leave_alone[:4]],
        "",
        "Ableton repair chain:",
        str(session.get("ableton_repair_chain") or "Level-match, make one repair move, then re-run Mix Review."),
        "",
        "Related questions:",
        "- What should I fix first after a Mix Review?",
        "- What should I leave alone in this revision?",
        "- How do I export v2 after a mix repair?",
    ]


def lines_from_feedback(row: dict) -> list[str]:
    topics = ", ".join(str(item) for item in row.get("topics") or []) or "mixing"
    issues = ", ".join(str(item) for item in row.get("issue_tags") or []) or "needs-work feedback"
    return [
        f"# KENN Feedback Repair {row.get('id', '')}",
        "",
        "Type: KENN feedback repair",
        f"Tags: feedback, repair, {topics}",
        "Status: Draft",
        f"Source feedback: {row.get('id', '')}",
        "",
        "Short answer:",
        "This note repairs a tester-reported answer quality issue. Replace this sentence with the corrected expert guidance before approval.",
        "",
        "Key ideas:",
        f"- Tester issue tags: {issues}",
        f"- Tester question: {row.get('question', '')}",
        f"- Tester note: {row.get('comment', '') or '(none)'}",
        "",
        "Try this:",
        "1. State the exact fix or workflow the answer should have given.",
        "2. Add the source-specific Ableton or mix decision steps.",
        "3. Add the listening check that proves the fix worked.",
        "",
        "Why it matters:",
        "Repair notes turn tester feedback into reusable KENN knowledge and reduce repeat answer failures.",
        "",
        "Related questions:",
        "- What should I check first?",
        "- What source should KENN use for this answer?",
    ]


def write_candidate(path: Path, lines: list[str], *, overwrite: bool = False) -> bool:
    if path.exists() and not overwrite:
        return False
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Draft KENN knowledge candidates from reviews and feedback.")
    parser.add_argument("--reviews", type=int, default=5, help="Number of recent completed reviews to inspect.")
    parser.add_argument("--feedback", type=int, default=5, help="Number of needs-work feedback rows to inspect.")
    parser.add_argument("--write", action="store_true", help="Write draft notes into KENN/Training_Data_Notes.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing draft candidate files.")
    args = parser.parse_args()

    NOTES.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[Path, list[str]]] = []
    for review in mix_review.list_reviews(limit=max(1, args.reviews)):
        session = review.get("session_report") if isinstance(review.get("session_report"), dict) else {}
        if not session:
            continue
        name = f"draft-session-report-{slug(str(review.get('title') or review.get('id')))}.md"
        candidates.append((NOTES / name, lines_from_review(review)))

    for row in demo_feedback.list_feedback(limit=max(1, args.feedback)):
        if row.get("rating") != "not_useful":
            continue
        name = f"draft-feedback-repair-{slug(str(row.get('id')))}.md"
        candidates.append((NOTES / name, lines_from_feedback(row)))

    if not candidates:
        print("No knowledge candidates found.")
        return 0
    for path, lines in candidates:
        if args.write:
            written = write_candidate(path, lines, overwrite=args.overwrite)
            print(("WROTE " if written else "SKIP  ") + str(path.relative_to(ROOT)))
        else:
            print(f"DRY   {path.relative_to(ROOT)}")
            print("      " + lines[0].lstrip("# "))
    if not args.write:
        print("\nRun with --write to create draft notes. Review and change Status: Approved before rebuilding.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

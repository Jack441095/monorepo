#!/usr/bin/env python3
"""Turn KENN tester feedback into repair notes, rebuilds, and retests."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEBSITE = ROOT / "business" / "app"
KENN = ROOT / "studio" / "kenn" / "kenn"
if str(WEBSITE) not in sys.path:
    sys.path.insert(0, str(WEBSITE))
if str(KENN.parent) not in sys.path:
    sys.path.insert(0, str(KENN.parent))

import demo_feedback  # noqa: E402
import llm_improvement  # noqa: E402
from kenn.training.research import resolve_note_path, set_note_status  # noqa: E402

KENN_CHANNELS = {"main_chat", "mix_review"}
PLACEHOLDERS = (
    "Replace this with the corrected answer",
    "Write the most practical first action",
    "Add device names, starting settings, or routing details",
    "Explain the mistake this repair prevents",
    "Rephrase the original question as a follow-up",
)


def python_cmd() -> str:
    candidate = ROOT / ".venv" / "bin" / "python"
    return str(candidate) if candidate.exists() else sys.executable


def feedback_row(feedback_id: str) -> dict:
    row = demo_feedback.get_feedback(feedback_id)
    if not row:
        raise SystemExit(f"Feedback not found: {feedback_id}")
    return row


def note_path_for(row: dict) -> Path:
    note_name = str(row.get("repair_note") or "").strip()
    if not note_name:
        raise SystemExit("No repair note is linked yet. Run: draft <feedback-id>")
    return resolve_note_path(note_name)


def clean_line(value: object, *, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}..."


def list_needs_work(limit: int) -> int:
    rows = [
        row
        for row in demo_feedback.list_feedback(limit=max(1, limit))
        if row.get("rating") == "not_useful" and str(row.get("channel", "")) in KENN_CHANNELS
    ]
    if not rows:
        print("No needs-work KENN feedback found.")
        return 0
    print(f"Needs-work KENN feedback ({len(rows)} rows)")
    print("")
    for row in rows:
        print(
            f"- {row.get('id')} | {row.get('created_at')} | "
            f"{row.get('channel')} | repair={row.get('repair_status') or 'open'}"
        )
        print(f"  Q: {clean_line(row.get('question'))}")
        if row.get("comment"):
            print(f"  Note: {clean_line(row.get('comment'), limit=220)}")
        if row.get("issue_tags"):
            print(f"  Issues: {', '.join(str(item) for item in row.get('issue_tags') or [])}")
        if row.get("repair_note"):
            print(f"  Draft: {row.get('repair_note')}")
    return 0


def show_feedback(feedback_id: str, *, as_json: bool = False) -> int:
    row = feedback_row(feedback_id)
    if as_json:
        print(json.dumps(row, indent=2, ensure_ascii=True))
        return 0
    print(f"Feedback {row.get('id')}")
    print(f"Rating: {row.get('rating')}")
    print(f"Channel: {row.get('channel')}")
    print(f"Repair: {row.get('repair_status') or 'open'}")
    if row.get("repair_note"):
        print(f"Draft: {row.get('repair_note')}")
    print("")
    print(f"Question: {row.get('question')}")
    print(f"Tester note: {row.get('comment') or '(none)'}")
    if row.get("issue_tags"):
        print(f"Issues: {', '.join(str(item) for item in row.get('issue_tags') or [])}")
    print("")
    print("Failed answer preview:")
    print(clean_line(row.get("answer"), limit=700))
    return 0


def draft_repair(feedback_id: str) -> int:
    result = llm_improvement.create_note_from_feedback(feedback_id)
    if not result.get("ok"):
        print(result.get("error", "Could not create repair draft."), file=sys.stderr)
        return 1
    print(result["message"])
    print("Next:")
    print(f"  1. Edit KENN/Training_Data_Notes/{result['note']}")
    print(f"  2. ./scripts/kenn_feedback_repair.py validate {feedback_id}")
    print(f"  3. ./scripts/kenn_feedback_repair.py approve {feedback_id} --build --retest")
    return 0


def validate_repair(feedback_id: str) -> tuple[bool, list[str], Path]:
    row = feedback_row(feedback_id)
    path = note_path_for(row)
    text = path.read_text(encoding="utf-8", errors="replace")
    issues: list[str] = []
    if "Status: Approved" not in text and "Status: Draft" not in text:
        issues.append("Missing Status field.")
    for placeholder in PLACEHOLDERS:
        if placeholder in text:
            issues.append(f"Still contains template placeholder: {placeholder}")
    required_headings = ("Short answer:", "Try this:", "Why it matters:", "Related questions:")
    for heading in required_headings:
        if heading not in text:
            issues.append(f"Missing section: {heading}")
    return not issues, issues, path


def validate_command(feedback_id: str) -> int:
    ok, issues, path = validate_repair(feedback_id)
    print(f"Repair note: {path}")
    if ok:
        print("Validation passed. The note is ready to approve.")
        return 0
    print("Validation failed:")
    for issue in issues:
        print(f"- {issue}")
    return 1


def build_index() -> int:
    return subprocess.run([str(ROOT / "ableton"), "build"], cwd=ROOT, check=False).returncode


def approve_repair(feedback_id: str, *, build: bool = False, retest: bool = False) -> int:
    ok, issues, path = validate_repair(feedback_id)
    if not ok:
        print("Refusing to approve until validation passes:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
        return 1
    approved = set_note_status(path, "Approved")
    print(f"Approved repair note: {approved}")
    if build:
        print("Rebuilding KENN index...")
        code = build_index()
        if code:
            return code
    if retest:
        return retest_repair(feedback_id)
    print("Next: ./ableton build")
    return 0


def retest_repair(feedback_id: str) -> int:
    result = llm_improvement.retest_feedback_repair(feedback_id)
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="KENN feedback-to-repair workflow.")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List needs-work KENN feedback.")
    list_parser.add_argument("--limit", type=int, default=50)

    show_parser = sub.add_parser("show", help="Show one feedback row.")
    show_parser.add_argument("feedback_id")
    show_parser.add_argument("--json", action="store_true")

    draft_parser = sub.add_parser("draft", help="Create a draft repair note from needs-work feedback.")
    draft_parser.add_argument("feedback_id")

    validate_parser = sub.add_parser("validate", help="Check whether a draft repair note is ready to approve.")
    validate_parser.add_argument("feedback_id")

    approve_parser = sub.add_parser("approve", help="Approve an edited repair note.")
    approve_parser.add_argument("feedback_id")
    approve_parser.add_argument("--build", action="store_true", help="Rebuild KENN after approving.")
    approve_parser.add_argument("--retest", action="store_true", help="Retest the original question after rebuild.")

    retest_parser = sub.add_parser("retest", help="Retest the original feedback question.")
    retest_parser.add_argument("feedback_id")

    args = parser.parse_args()
    if args.command == "list":
        return list_needs_work(args.limit)
    if args.command == "show":
        return show_feedback(args.feedback_id, as_json=args.json)
    if args.command == "draft":
        return draft_repair(args.feedback_id)
    if args.command == "validate":
        return validate_command(args.feedback_id)
    if args.command == "approve":
        return approve_repair(args.feedback_id, build=args.build, retest=args.retest)
    if args.command == "retest":
        return retest_repair(args.feedback_id)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

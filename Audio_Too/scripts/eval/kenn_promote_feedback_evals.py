#!/usr/bin/env python3
"""Promote reviewed draft feedback evals into the canonical KENN eval suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DRAFT = ROOT / "studio" / "kenn" / "kenn" / "evals" / "draft_feedback_cases.json"
DEFAULT_SUITE = ROOT / "studio" / "kenn" / "kenn" / "evals" / "questions.json"


def load_suite(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    cases = data.get("cases")
    if not isinstance(cases, list):
        cases = []
    return {
        "version": int(data.get("version", 1) or 1),
        "description": data.get("description", ""),
        "cases": [case for case in cases if isinstance(case, dict)],
    }


def clean_case(case: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields the eval runner understands, plus feedback metadata."""
    allowed = {
        "id",
        "question",
        "answer_must_include",
        "answer_must_include_any",
        "answer_must_not_include",
        "topics_must_include",
        "min_confidence",
        "max_confidence",
        "min_source_quality",
        "max_source_quality",
        "source_kinds_any",
        "source_must_include",
        "answer_mode",
        "answer_modes_any",
        "route",
        "routes_any",
        "intent",
        "weak_match",
        "grounding_mode",
        "min_grounding_score",
        "min_answer_quality",
        "category",
        "tags",
        "feedback",
    }
    promoted = {key: value for key, value in case.items() if key in allowed}
    promoted.setdefault("category", "feedback")
    tags = list(promoted.get("tags") or [])
    if "feedback" not in tags:
        tags.append("feedback")
    promoted["tags"] = tags
    return promoted


def select_cases(draft_cases: list[dict[str, Any]], ids: list[str], promote_all: bool) -> list[dict[str, Any]]:
    wanted = {case_id.strip() for case_id in ids if case_id.strip()}
    if promote_all:
        return list(draft_cases)
    if not wanted:
        return []
    return [case for case in draft_cases if str(case.get("id", "")) in wanted]


def promote_cases(
    *,
    draft_path: Path = DEFAULT_DRAFT,
    suite_path: Path = DEFAULT_SUITE,
    ids: list[str] | None = None,
    promote_all: bool = False,
    write: bool = False,
    remove_promoted: bool = False,
) -> dict[str, Any]:
    ids = ids or []
    draft = load_suite(draft_path)
    suite = load_suite(suite_path)
    draft_cases = draft["cases"]
    selected = select_cases(draft_cases, ids, promote_all)
    existing_ids = {str(case.get("id", "")) for case in suite["cases"]}
    selected_ids = {str(case.get("id", "")) for case in selected}
    missing_ids = sorted({case_id for case_id in ids if case_id and case_id not in selected_ids})
    duplicates = sorted(case_id for case_id in selected_ids if case_id in existing_ids)
    promoted = [clean_case(case) for case in selected if str(case.get("id", "")) not in existing_ids]

    report: dict[str, Any] = {
        "ok": not missing_ids,
        "write": write,
        "draft_path": str(draft_path),
        "suite_path": str(suite_path),
        "draft_count": len(draft_cases),
        "selected_count": len(selected),
        "promoted_count": len(promoted) if write else 0,
        "preview_count": len(promoted),
        "duplicate_ids": duplicates,
        "missing_ids": missing_ids,
        "selected_ids": sorted(selected_ids),
        "promoted_ids": [str(case.get("id", "")) for case in promoted],
        "removed_from_draft": 0,
    }
    if not write or missing_ids:
        return report

    suite["cases"] = [*suite["cases"], *promoted]
    suite_path.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    if remove_promoted:
        promoted_ids = {str(case.get("id", "")) for case in promoted}
        draft["cases"] = [case for case in draft_cases if str(case.get("id", "")) not in promoted_ids]
        draft_path.write_text(json.dumps(draft, indent=2) + "\n", encoding="utf-8")
        report["removed_from_draft"] = len(promoted_ids)
    report["promoted_count"] = len(promoted)
    return report


def print_text(report: dict[str, Any]) -> None:
    mode = "write" if report.get("write") else "preview"
    print(f"Feedback eval promotion: {mode}")
    print(
        f"Draft cases: {report.get('draft_count', 0)} - "
        f"selected: {report.get('selected_count', 0)} - "
        f"eligible: {report.get('preview_count', 0)}"
    )
    if report.get("promoted_count"):
        print(f"Promoted: {report['promoted_count']}")
    if report.get("duplicate_ids"):
        print("Already in suite:")
        for case_id in report["duplicate_ids"]:
            print(f"  - {case_id}")
    if report.get("missing_ids"):
        print("Missing draft ids:")
        for case_id in report["missing_ids"]:
            print(f"  - {case_id}")
    if not report.get("write"):
        print("Use --write with --id CASE_ID or --all to modify questions.json.")
    elif report.get("removed_from_draft"):
        print(f"Removed from draft: {report['removed_from_draft']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote draft feedback eval cases into questions.json.")
    parser.add_argument("--draft", type=Path, default=DEFAULT_DRAFT, help="Draft feedback eval JSON.")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE, help="Canonical eval suite JSON.")
    parser.add_argument("--id", action="append", default=[], help="Draft case id to promote. Repeatable.")
    parser.add_argument("--all", action="store_true", help="Promote all draft cases.")
    parser.add_argument("--write", action="store_true", help="Write selected cases into the canonical suite.")
    parser.add_argument("--remove-promoted", action="store_true", help="Remove promoted cases from the draft file.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    report = promote_cases(
        draft_path=args.draft,
        suite_path=args.suite,
        ids=args.id,
        promote_all=args.all,
        write=args.write,
        remove_promoted=args.remove_promoted,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

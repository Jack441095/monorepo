#!/usr/bin/env python3
"""Validate tracked KENN hard-negative labels."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
KENN = ROOT / "studio" / "kenn" / "kenn"
DEFAULT_HARD_NEGATIVES = KENN / "evals" / "curated_hard_negatives.jsonl"
DEFAULT_SUITE = KENN / "evals" / "questions.json"
DEFAULT_NOTES = KENN / "Training_Data_Notes"
REQUIRED_FIELDS = {
    "schema",
    "case_id",
    "question",
    "negative_source",
    "negative_source_label",
    "reason",
    "route",
    "topics",
}

sys.path.insert(0, str(ROOT / "studio" / "kenn"))
from kenn.training.training_records import iter_jsonl_raw  # noqa: E402


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse ``path`` as JSONL, collecting one error per bad line instead of
    raising. This intentionally does NOT use the strict, raise-on-first-error
    ``read_jsonl`` in kenn.training.training_records: this script's entire
    job is to report every malformed/invalid row in one pass, so raising on
    the first bad line would defeat its purpose. It still shares the actual
    line-parsing logic via ``iter_jsonl_raw``.
    """
    if not path.exists():
        return [], [f"missing hard-negative file: {path}"]
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for lineno, _raw_line, parsed, error in iter_jsonl_raw(path):
        if error is not None:
            errors.append(f"line {lineno}: {error}")
            continue
        parsed["_line"] = lineno
        rows.append(parsed)
    return rows, errors


def load_cases(path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    if not path.exists():
        return {}, [f"missing eval suite: {path}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"invalid eval suite JSON: {exc}"]
    cases = payload.get("cases", []) if isinstance(payload, dict) else []
    if not isinstance(cases, list):
        return {}, ["eval suite `cases` must be a list"]
    by_id: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for case in cases:
        if not isinstance(case, dict):
            errors.append("eval suite contains a non-object case")
            continue
        case_id = str(case.get("id") or "")
        if not case_id:
            errors.append("eval suite contains a case without id")
            continue
        by_id[case_id] = case
    return by_id, errors


def validate_rows(
    rows: list[dict[str, Any]],
    *,
    cases_by_id: dict[str, dict[str, Any]],
    notes_dir: Path,
) -> list[str]:
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        line = row.get("_line", "?")
        missing = sorted(
            field
            for field in REQUIRED_FIELDS
            if field not in row or row.get(field) is None or row.get(field) == ""
        )
        if missing:
            errors.append(f"line {line}: missing required fields: {', '.join(missing)}")
        if row.get("schema") != "kenn.hard_negative.v1":
            errors.append(f"line {line}: schema must be kenn.hard_negative.v1")

        case_id = str(row.get("case_id") or "")
        negative_source = str(row.get("negative_source") or "")
        key = (case_id, negative_source)
        if key in seen:
            errors.append(f"line {line}: duplicate case/source hard negative: {case_id} -> {negative_source}")
        seen.add(key)

        case = cases_by_id.get(case_id)
        if not case:
            errors.append(f"line {line}: case_id not found in eval suite: {case_id}")
        else:
            expected_question = str(case.get("question") or "")
            if str(row.get("question") or "") != expected_question:
                errors.append(f"line {line}: question does not match eval case {case_id}")
            expected_route = str(case.get("route") or "")
            routes_any = [str(route) for route in case.get("routes_any") or []]
            route = str(row.get("route") or "")
            if expected_route and route != expected_route:
                errors.append(f"line {line}: route {route!r} does not match eval route {expected_route!r}")
            if routes_any and route not in routes_any:
                errors.append(f"line {line}: route {route!r} is not in eval routes_any {routes_any!r}")

        if negative_source and not (notes_dir / negative_source).exists():
            errors.append(f"line {line}: negative_source note does not exist: {negative_source}")

        topics = row.get("topics")
        if not isinstance(topics, list) or not all(isinstance(topic, str) and topic for topic in topics):
            errors.append(f"line {line}: topics must be a non-empty list of strings")

        reason = str(row.get("reason") or "")
        if "hard negative" not in reason.lower():
            errors.append(f"line {line}: reason should explain why this is a hard negative")
    return errors


def validate(
    *,
    hard_negatives: Path = DEFAULT_HARD_NEGATIVES,
    suite: Path = DEFAULT_SUITE,
    notes_dir: Path = DEFAULT_NOTES,
) -> dict[str, Any]:
    rows, row_errors = read_jsonl(hard_negatives)
    cases_by_id, suite_errors = load_cases(suite)
    validation_errors = validate_rows(rows, cases_by_id=cases_by_id, notes_dir=notes_dir)
    errors = [*row_errors, *suite_errors, *validation_errors]
    return {
        "ok": not errors,
        "hard_negatives": str(hard_negatives),
        "suite": str(suite),
        "notes_dir": str(notes_dir),
        "rows": len(rows),
        "unique_cases": len({str(row.get("case_id") or "") for row in rows}),
        "errors": errors,
    }


def print_text(report: dict[str, Any]) -> None:
    if report["ok"]:
        print(f"Hard-negative validation: pass ({report['rows']} rows, {report['unique_cases']} cases)")
        return
    print(f"Hard-negative validation: fail ({len(report['errors'])} error(s))")
    for error in report["errors"][:20]:
        print(f"  - {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate tracked KENN hard-negative labels.")
    parser.add_argument("--hard-negatives", type=Path, default=DEFAULT_HARD_NEGATIVES)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--notes-dir", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = validate(hard_negatives=args.hard_negatives, suite=args.suite, notes_dir=args.notes_dir)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Promote reviewed hard-negative candidates into the tracked curated set."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from kenn_validate_hard_negatives import DEFAULT_HARD_NEGATIVES, DEFAULT_NOTES, DEFAULT_SUITE, validate

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CANDIDATES = ROOT / "studio" / "kenn" / "kenn" / "artifacts" / "training" / "kenn_hard_negative_candidates.jsonl"
SOURCE_RE = re.compile(r"^(?P<label>.+?)\s+\((?P<source>[^()]+\.md)\)$")

sys.path.insert(0, str(ROOT / "studio" / "kenn"))
from kenn.training.training_records import read_jsonl, write_jsonl  # noqa: E402


def parse_source_label(source_label: str) -> tuple[str, str]:
    match = SOURCE_RE.match(source_label.strip())
    if not match:
        return source_label.strip(), ""
    return match.group("label").strip(), match.group("source").strip()


def matching_candidates(
    candidates: list[dict[str, Any]],
    *,
    case_id: str,
    source_label: str = "",
    candidate_rank: int | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for candidate in candidates:
        if str(candidate.get("case_id") or "") != case_id:
            continue
        if source_label and str(candidate.get("candidate_source_label") or "") != source_label:
            continue
        if candidate_rank is not None and int(candidate.get("candidate_rank") or 0) != candidate_rank:
            continue
        matches.append(candidate)
    return matches


def promote_candidate(
    candidate: dict[str, Any],
    *,
    reason: str = "",
    negative_source: str = "",
    negative_source_label: str = "",
) -> dict[str, Any]:
    parsed_label, parsed_source = parse_source_label(str(candidate.get("candidate_source_label") or ""))
    source = negative_source or parsed_source
    label = negative_source_label or parsed_label
    return {
        "schema": "kenn.hard_negative.v1",
        "case_id": str(candidate.get("case_id") or ""),
        "question": str(candidate.get("question") or ""),
        "negative_source": source,
        "negative_source_label": label,
        "reason": reason
        or "true hard negative: promoted from reviewed mined candidate because the source overlaps but is less specific than the positive source",
        "route": str(candidate.get("route") or ""),
        "topics": [str(topic) for topic in candidate.get("topics") or [] if str(topic)],
    }


def existing_keys(rows: list[dict[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(row.get("case_id") or ""), str(row.get("negative_source") or ""))
        for row in rows
        if row.get("case_id") and row.get("negative_source")
    }


def promotable_candidates(
    *,
    candidates_path: Path = DEFAULT_CANDIDATES,
    target_path: Path = DEFAULT_HARD_NEGATIVES,
    topic: str = "game_audio",
    route: str = "",
    limit: int = 12,
) -> dict[str, Any]:
    candidates = read_jsonl(candidates_path)
    existing = existing_keys(read_jsonl(target_path))
    items: list[dict[str, Any]] = []
    for candidate in candidates:
        topics = [str(item) for item in candidate.get("topics") or []]
        candidate_route = str(candidate.get("route") or "")
        if topic and topic not in topics:
            continue
        if route and route != candidate_route:
            continue
        label, source = parse_source_label(str(candidate.get("candidate_source_label") or ""))
        if not source:
            continue
        key = (str(candidate.get("case_id") or ""), source)
        if key in existing:
            continue
        items.append(
            {
                "case_id": candidate.get("case_id", ""),
                "question": candidate.get("question", ""),
                "route": candidate_route,
                "topics": topics,
                "candidate_rank": candidate.get("candidate_rank", ""),
                "candidate_source_label": candidate.get("candidate_source_label", ""),
                "negative_source": source,
                "negative_source_label": label,
                "positive_source_label": candidate.get("positive_source_label", ""),
                "candidate_overlap_score": candidate.get("candidate_overlap_score", 0),
                "positive_overlap_score": candidate.get("positive_overlap_score", 0),
                "promote_command": (
                    f"./audio-too promote-hard-negative --case-id {candidate.get('case_id', '')} "
                    f"--candidate-rank {candidate.get('candidate_rank', '')} --write"
                ),
            }
        )
    items.sort(
        key=lambda item: (
            -float(item.get("candidate_overlap_score") or 0),
            int(item.get("candidate_rank") or 99),
            str(item.get("case_id") or ""),
        )
    )
    return {
        "ok": candidates_path.exists(),
        "candidates": str(candidates_path),
        "target": str(target_path),
        "topic": topic,
        "route": route,
        "items": items[: max(1, limit)],
        "total_promotable": len(items),
    }


def promote(
    *,
    case_id: str,
    source_label: str = "",
    candidate_rank: int | None = None,
    candidates_path: Path = DEFAULT_CANDIDATES,
    target_path: Path = DEFAULT_HARD_NEGATIVES,
    suite: Path = DEFAULT_SUITE,
    notes_dir: Path = DEFAULT_NOTES,
    reason: str = "",
    negative_source: str = "",
    negative_source_label: str = "",
    write: bool = False,
) -> dict[str, Any]:
    candidates = read_jsonl(candidates_path)
    matches = matching_candidates(
        candidates,
        case_id=case_id,
        source_label=source_label,
        candidate_rank=candidate_rank,
    )
    if len(matches) != 1:
        return {
            "ok": False,
            "write": False,
            "error": f"expected exactly one candidate, found {len(matches)}",
            "matches": [
                {
                    "case_id": item.get("case_id", ""),
                    "candidate_rank": item.get("candidate_rank", ""),
                    "candidate_source_label": item.get("candidate_source_label", ""),
                }
                for item in matches[:10]
            ],
        }

    row = promote_candidate(
        matches[0],
        reason=reason,
        negative_source=negative_source,
        negative_source_label=negative_source_label,
    )
    if not row["negative_source"]:
        return {
            "ok": False,
            "write": False,
            "error": "candidate source label does not include a note filename; pass --negative-source",
            "row": row,
        }

    existing = read_jsonl(target_path)
    key = (row["case_id"], row["negative_source"])
    if any((str(item.get("case_id") or ""), str(item.get("negative_source") or "")) == key for item in existing):
        return {"ok": False, "write": False, "error": "hard negative already exists", "row": row}

    rows = [*existing, row]
    validation_before_write: dict[str, Any] | None = None
    if write:
        write_jsonl(target_path, rows, sort_keys=True)
        validation_report = validate(hard_negatives=target_path, suite=suite, notes_dir=notes_dir)
    else:
        preview_path = target_path.with_suffix(target_path.suffix + ".preview")
        write_jsonl(preview_path, rows, sort_keys=True)
        validation_before_write = validate(hard_negatives=preview_path, suite=suite, notes_dir=notes_dir)
        preview_path.unlink(missing_ok=True)
        validation_report = validation_before_write

    return {
        "ok": bool(validation_report.get("ok")),
        "write": write,
        "target": str(target_path),
        "row": row,
        "validation": validation_report,
    }


def print_text(report: dict[str, Any]) -> None:
    if not report.get("ok"):
        print(f"Promote hard negative: fail - {report.get('error') or 'validation failed'}")
        for match in report.get("matches", []):
            print(
                f"  - {match.get('case_id')} rank {match.get('candidate_rank')}: "
                f"{match.get('candidate_source_label')}"
            )
        for error in report.get("validation", {}).get("errors", [])[:10]:
            print(f"  - {error}")
        return
    action = "wrote" if report.get("write") else "preview"
    row = report.get("row", {})
    print(
        f"Promote hard negative: {action} {row.get('case_id')} -> "
        f"{row.get('negative_source')} ({report.get('target')})"
    )


def print_report(report: dict[str, Any]) -> None:
    print(
        f"Promotable hard negatives: {report.get('total_promotable', 0)} "
        f"(showing {len(report.get('items', []))})"
    )
    print(f"Topic: {report.get('topic') or 'any'}")
    if report.get("route"):
        print(f"Route: {report['route']}")
    for item in report.get("items", []):
        print(
            f"  - {item.get('case_id')} rank {item.get('candidate_rank')} "
            f"score {item.get('candidate_overlap_score')}: {item.get('candidate_source_label')}"
        )
        print(f"    {item.get('promote_command')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a reviewed KENN hard-negative candidate.")
    parser.add_argument("--case-id", default="", help="Candidate/eval case id to promote.")
    parser.add_argument("--source-label", default="", help="Exact candidate_source_label to promote.")
    parser.add_argument("--candidate-rank", type=int, default=None, help="Candidate rank to promote.")
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--target", type=Path, default=DEFAULT_HARD_NEGATIVES)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    parser.add_argument("--notes-dir", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--negative-source", default="", help="Note filename when source label lacks '(file.md)'.")
    parser.add_argument("--negative-source-label", default="", help="Readable source label override.")
    parser.add_argument("--reason", default="", help="Reviewed reason explaining why this is a hard negative.")
    parser.add_argument("--write", action="store_true", help="Append to curated hard negatives. Preview only by default.")
    parser.add_argument("--list", action="store_true", help="List promotable candidates instead of promoting one.")
    parser.add_argument("--topic", default="game_audio", help="Topic filter for --list. Use empty string for all topics.")
    parser.add_argument("--route", default="", help="Route filter for --list.")
    parser.add_argument("--limit", type=int, default=12, help="Maximum candidates to show for --list.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.list:
        report = promotable_candidates(
            candidates_path=args.candidates,
            target_path=args.target,
            topic=args.topic,
            route=args.route,
            limit=args.limit,
        )
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_report(report)
        return 0 if report.get("ok") else 1

    if not args.case_id:
        parser.error("--case-id is required unless --list is used")

    report = promote(
        case_id=args.case_id,
        source_label=args.source_label,
        candidate_rank=args.candidate_rank,
        candidates_path=args.candidates,
        target_path=args.target,
        suite=args.suite,
        notes_dir=args.notes_dir,
        reason=args.reason,
        negative_source=args.negative_source,
        negative_source_label=args.negative_source_label,
        write=args.write,
    )
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text(report)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

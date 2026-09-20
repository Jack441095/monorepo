#!/usr/bin/env python3
"""Export independent, packet-bound KENN human-review forms.

The exported forms are templates. They contain no scores and cannot be passed
to the adjudicator until a reviewer has completed every criterion for every
case. Each form includes the packet SHA-256 so reviewers and the release gate
can verify that both reviewers assessed the same packet.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACKET = REPO_ROOT / "docs" / "ABLETON_ASSISTANT_HUMAN_REVIEW_PACKET_2026-09-08.json"


def packet_digest(packet_path: Path) -> str:
    return hashlib.sha256(packet_path.read_bytes()).hexdigest()


def build_form(packet: dict[str, Any], *, reviewer_slot: str, packet_sha256: str) -> dict[str, Any]:
    criteria = [str(item) for item in packet.get("criteria", [])]
    cases = packet.get("cases")
    if not criteria or not isinstance(cases, list) or not cases:
        raise ValueError("packet must contain a non-empty criteria list and cases list")
    rows = []
    for case in cases:
        if not isinstance(case, dict) or not str(case.get("case_id") or "").strip():
            raise ValueError("every packet case must contain a case_id")
        rows.append({
            "case_id": str(case["case_id"]),
            "category": str(case.get("category") or "uncategorized"),
            "question": case.get("question", ""),
            "response": case.get("response", {}),
            "scores": {criterion: None for criterion in criteria},
            "notes": "",
            "outcome": None,
        })
    return {
        "schema": "kenn.human_review_form.v1",
        "reviewer_slot": reviewer_slot,
        "reviewer_id": "",
        "independent_review_confirmed": False,
        "packet_sha256": packet_sha256,
        "case_count": len(rows),
        "criteria": criteria,
        "scoring_scale": packet.get("scoring_scale", {}),
        "independence": "Complete this form without seeing another reviewer's scores.",
        "reviews": rows,
    }


def export_forms(packet_path: Path, output_dir: Path, *, force: bool = False) -> list[Path]:
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    digest = packet_digest(packet_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [output_dir / "reviewer-a.json", output_dir / "reviewer-b.json"]
    if not force:
        existing = [path for path in paths if path.exists()]
        if existing:
            raise FileExistsError("refusing to overwrite existing form(s): " + ", ".join(str(path) for path in existing))
    for reviewer_slot, path in (("a", paths[0]), ("b", paths[1])):
        form = build_form(packet, reviewer_slot=reviewer_slot, packet_sha256=digest)
        path.write_text(json.dumps(form, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=DEFAULT_PACKET)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="overwrite existing reviewer forms")
    args = parser.parse_args()
    try:
        paths = export_forms(args.packet.expanduser().resolve(), args.output_dir.expanduser().resolve(), force=args.force)
    except (OSError, json.JSONDecodeError, ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": "created", "packet_sha256": packet_digest(args.packet.expanduser().resolve()), "forms": [str(path) for path in paths]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Privacy-preserving export and readiness audit for reviewed role corrections."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "business" / "app"))

import musical_role_feedback  # noqa: E402

EXPORT_SCHEMA = "audio-too.musical-role-reviewed-export.v1"


def _pseudonym(salt: bytes, namespace: str, value: str) -> str:
    digest = hmac.new(salt, f"{namespace}:{value}".encode(), hashlib.sha256).hexdigest()
    return digest[:24]


def export_reviewed_role_cases(
    rows: list[dict], *, salt: bytes, minimum_cases: int = 20
) -> dict:
    if not isinstance(salt, bytes) or len(salt) < 16:
        raise ValueError("export salt must contain at least 16 bytes")
    cases = []
    for row in rows:
        cases.append({
            "case_id": _pseudonym(salt, "correction", str(row["id"])),
            "project_group": _pseudonym(salt, "project", str(row["project_id"])),
            "job_group": _pseudonym(salt, "job", str(row["job_id"])),
            "stem_id": _pseudonym(salt, "stem", f"{row['job_id']}:{row['stem_name']}"),
            "plan_revision": _pseudonym(
                salt, "revision", str(row["source_plan_revision"])
            ),
            "inferred": {
                "role": row["inferred_role"],
                "priority": row["inferred_priority"],
                "confidence": float(row["inferred_confidence"]),
                "ambiguous": bool(row["inferred_ambiguous"]),
            },
            "reviewed": {
                "role": row["corrected_role"],
                "priority": row["corrected_priority"],
            },
        })
    projects = {case["project_group"] for case in cases}
    corrected_roles = Counter(case["reviewed"]["role"] for case in cases)
    failures = []
    if len(cases) < minimum_cases:
        failures.append(f"requires at least {minimum_cases} reviewed corrections")
    if len(projects) < 5:
        failures.append("requires corrections from at least 5 projects")
    if len(corrected_roles) < 3:
        failures.append("requires at least 3 reviewed role categories")
    return {
        "schema": EXPORT_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "privacy": {
            "pseudonymization": "HMAC-SHA256 with caller-held salt",
            "excluded_fields": [
                "correction_id", "job_id", "project_id", "stem_name",
                "actor_id", "timestamps", "correction_hash",
            ],
        },
        "readiness": {
            "ready": not failures,
            "failures": failures,
            "minimum_cases": minimum_cases,
            "minimum_projects": 5,
            "minimum_role_categories": 3,
        },
        "summary": {
            "reviewed_corrections": len(cases),
            "projects": len(projects),
            "corrected_roles": dict(sorted(corrected_roles.items())),
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salt-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=20)
    args = parser.parse_args()
    report = export_reviewed_role_cases(
        musical_role_feedback.list_corrections(),
        salt=args.salt_file.read_bytes(),
        minimum_cases=args.minimum_cases,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report["summary"], indent=2, sort_keys=True))
    return 0 if report["readiness"]["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

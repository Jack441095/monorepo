#!/usr/bin/env python3
"""Export reviewed advisor operations as privacy-preserving replay cases."""

from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import sys
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for import_root in (ROOT, ROOT / "business" / "app", ROOT / "studio" / "audio_analysis"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

import artifact_store  # noqa: E402
import db  # noqa: E402
from audio_analysis.integration.kenn_advisor import mix_plan_revision  # noqa: E402
from scripts.eval.automix_advisor_replay import plan_from_dict  # noqa: E402

EXPORT_SCHEMA = "audio-too.kenn-advisor-reviewed-export/v1"
SHADOW_SCHEMA = "audio-too.kenn-advisor-shadow/v1"


def _pseudonym(salt: bytes, namespace: str, value: str) -> str:
    digest = hmac.new(salt, f"{namespace}:{value}".encode(), hashlib.sha256).hexdigest()[:16]
    return f"{namespace}-{digest}"


def _anonymize_case(row: dict, receipt: dict, salt: bytes) -> dict:
    source_plan = copy.deepcopy(receipt["source_plan"])
    proposal = copy.deepcopy(receipt["proposal"])
    operation_index = int(row["operation_index"])
    operation = proposal["operations"][operation_index]
    mapping = {
        str(stem["stem_name"]): _pseudonym(salt, "stem", str(stem["stem_name"]))
        for stem in source_plan["stems"]
    }
    for stem in source_plan["stems"]:
        stem["stem_name"] = mapping[str(stem["stem_name"])]
    source_plan["decisions_log"] = []
    reviewed_operation = copy.deepcopy(operation)
    reviewed_operation["stem_id"] = mapping[str(reviewed_operation["stem_id"])]
    reviewed_operation["reason"] = "Reviewed grounded advisor operation."
    restored = plan_from_dict(source_plan)
    revision = mix_plan_revision(restored)
    case_id = _pseudonym(salt, "case", str(row["id"]))
    correlation_id = f"automix-replay:{case_id}"
    anonymized_proposal = {
        "schema": proposal["schema"],
        "source_plan_revision": revision,
        "model_version": proposal["model_version"],
        "prompt_version": proposal["prompt_version"],
        "correlation_id": correlation_id,
        "operations": [reviewed_operation],
    }
    ratings = {
        "usefulness": int(row["usefulness_rating"]),
        "explanation_quality": int(row["explanation_quality_rating"]),
    }
    if row["audible_improvement_rating"] is not None:
        ratings["audible_improvement"] = int(row["audible_improvement_rating"])
    return {
        "id": case_id,
        "plan": asdict(restored),
        "proposal": anonymized_proposal,
        "correlation_id": correlation_id,
        "expected_status": "valid",
        "human_decision": row["decision"],
        "human_ratings": ratings,
        "has_preview_evidence": row["audible_improvement_rating"] is not None,
    }


def export_reviewed_cases(
    rows: list[dict],
    *,
    salt: bytes,
    artifact_loader=artifact_store.get,
    artifact_path_resolver=artifact_store.resolve_path,
    minimum_cases: int = 20,
) -> dict[str, Any]:
    """Create anonymized cases and an explicit cohort-readiness audit."""
    if not isinstance(salt, bytes) or len(salt) < 16:
        raise ValueError("export salt must contain at least 16 bytes")
    cases = []
    exclusions: Counter[str] = Counter()
    for row in rows:
        artifact = artifact_loader(str(row.get("shadow_artifact_id", "")))
        if artifact is None or artifact.get("kind") != "audio.automix.advisor-shadow":
            exclusions["missing_shadow_artifact"] += 1
            continue
        try:
            receipt = json.loads(
                artifact_path_resolver(artifact["id"]).read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError):
            exclusions["unreadable_shadow_receipt"] += 1
            continue
        if not isinstance(receipt, dict) or receipt.get("schema") != SHADOW_SCHEMA:
            exclusions["invalid_shadow_schema"] += 1
            continue
        if receipt.get("status") != "valid" or not isinstance(receipt.get("proposal"), dict):
            exclusions["shadow_not_valid"] += 1
            continue
        if not isinstance(receipt.get("source_plan"), dict):
            exclusions["missing_source_plan"] += 1
            continue
        operations = receipt["proposal"].get("operations")
        index = row.get("operation_index")
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(operations, list):
            exclusions["invalid_operation_lineage"] += 1
            continue
        if index < 0 or index >= len(operations):
            exclusions["invalid_operation_lineage"] += 1
            continue
        try:
            cases.append(_anonymize_case(row, receipt, salt))
        except (KeyError, TypeError, ValueError):
            exclusions["anonymization_validation_failure"] += 1

    decisions = Counter(case["human_decision"] for case in cases)
    audible_cases = sum(case["has_preview_evidence"] for case in cases)
    readiness_failures = []
    if len(cases) < minimum_cases:
        readiness_failures.append(f"requires at least {minimum_cases} reviewed operations")
    if not decisions.get("accepted"):
        readiness_failures.append("requires at least one accepted operation")
    if not (decisions.get("rejected") or decisions.get("needs_work")):
        readiness_failures.append("requires at least one rejected or needs_work operation")
    if not audible_cases:
        readiness_failures.append("requires at least one rating backed by an A/B preview")
    return {
        "schema": EXPORT_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "privacy": {
            "pseudonymization": "HMAC-SHA256 with caller-held salt",
            "excluded_fields": [
                "job_id",
                "project_id",
                "artifact_id",
                "feedback_id",
                "actor_id",
                "reason",
                "timestamps",
                "original stem names",
                "decision logs",
            ],
        },
        "readiness": {
            "ready": not readiness_failures,
            "failures": readiness_failures,
            "minimum_cases": minimum_cases,
        },
        "summary": {
            "feedback_rows": len(rows),
            "exported_cases": len(cases),
            "excluded_rows": sum(exclusions.values()),
            "exclusions": dict(sorted(exclusions.items())),
            "decisions": dict(sorted(decisions.items())),
            "preview_backed_audible_cases": audible_cases,
        },
        "cases": cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--salt-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--minimum-cases", type=int, default=20)
    args = parser.parse_args()
    salt = args.salt_file.read_bytes()
    db.init_db()
    with db.connect() as conn:
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM automix_advisor_feedback ORDER BY created_at, id"
            ).fetchall()
        ]
    report = export_reviewed_cases(rows, salt=salt, minimum_cases=args.minimum_cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"readiness": report["readiness"], "summary": report["summary"]}, indent=2))
    return int(not report["readiness"]["ready"])


if __name__ == "__main__":
    raise SystemExit(main())

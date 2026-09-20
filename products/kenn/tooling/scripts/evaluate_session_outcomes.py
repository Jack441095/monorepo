#!/usr/bin/env python3
"""Validate privacy-safe supervised-session outcome logs and emit aggregates.

This evaluator is deliberately separate from the qualified-beta pilot receipt:
the pilot proves safe, signed-off Live sessions, while this tool prepares the
reviewed learning evidence needed to improve KENN after the pilot.  Logs must
contain categories and opaque release-scoped buckets only; raw prompts, audio,
project paths, and tester identities are rejected.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.session_outcome_contract import (
    EVIDENCE_CLASSES, FORBIDDEN_KEYS, FRESHNESS, INTENT_CLASSES, OUTCOMES,
    ROOT_CAUSES, SCHEMA, STAGES, VERDICTS, _contains_forbidden, validate,
)


REPORT_SCHEMA = "kenn.session_outcome_evaluation.v1"


class OutcomeEvidenceError(ValueError):
    """Raised when an outcome log is incomplete or privacy-unsafe."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OutcomeEvidenceError(f"{path.name}: unreadable JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise OutcomeEvidenceError(f"{path.name}: root must be an object")
    return value


def evaluate(paths: list[Path]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    intents: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    verdicts: Counter[str] = Counter()
    root_causes: Counter[str] = Counter()
    evidence_classes: Counter[str] = Counter()
    latency_totals: Counter[str] = Counter()
    for path in paths:
        log = _load(path)
        failures = validate(log)
        valid = not failures
        if valid:
            intents[str(log["intent_class"])] += 1
            outcomes[str(log["lifecycle_outcome"])] += 1
            verdicts[str(log["user_verdict"])] += 1
            evidence_classes.update(str(item) for item in log["evidence_classes"])
            if log.get("root_cause"):
                root_causes[str(log["root_cause"])] += 1
            for stage in STAGES:
                latency_totals[stage] += int(log["latency_ms"][stage])
        rows.append({"valid": valid, "failures": failures})
    valid_count = sum(row["valid"] for row in rows)
    reviewable = sum(
        row["valid"] and _load(path).get("user_verdict") in {"revise", "reject", "unsafe"}
        for row, path in zip(rows, paths)
    )
    labeled = sum(bool(
        row["valid"] and _load(path).get("user_verdict") in {"revise", "reject", "unsafe"} and _load(path).get("root_cause")
    ) for row, path in zip(rows, paths))
    return {
        "schema": REPORT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "session_count": len(rows), "valid_session_count": valid_count,
            "invalid_session_count": len(rows) - valid_count,
            "reviewable_miss_count": reviewable, "root_cause_labeled_miss_count": labeled,
            "root_cause_label_rate": labeled / reviewable if reviewable else 1.0,
            "mean_latency_ms": {stage: latency_totals[stage] / valid_count if valid_count else 0.0 for stage in STAGES},
        },
        "counts": {
            "intent_class": dict(sorted(intents.items())), "lifecycle_outcome": dict(sorted(outcomes.items())),
            "user_verdict": dict(sorted(verdicts.items())), "root_cause": dict(sorted(root_causes.items())),
            "evidence_class": dict(sorted(evidence_classes.items())),
        },
        "rows": rows,
        "privacy": {
            "stores_raw_prompts": False, "stores_audio": False, "stores_paths": False,
            "stores_identities": False, "uses_release_scoped_opaque_buckets": True,
        },
        "limitations": ["This report measures log completeness and aggregates; it does not replace human musical evaluation or beta qualification."],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = evaluate([path.expanduser().resolve() for path in args.log])
    except OutcomeEvidenceError as exc:
        parser.error(str(exc))
    target = args.output.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["metrics"]["invalid_session_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

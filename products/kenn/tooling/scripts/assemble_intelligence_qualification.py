#!/usr/bin/env python3
"""Assemble a fail-closed intelligence receipt from five completed benchmarks."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))
from qualify_internal_beta import _tracked_source_sha256, evaluate_intelligence_results  # noqa: E402


SCHEMA = "kenn.intelligence_qualification.v1"


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hard-cases", type=Path, required=True)
    parser.add_argument("--retrieval-modes", type=Path, required=True)
    parser.add_argument("--session-grounded", type=Path, required=True)
    parser.add_argument("--assistant-recovery", type=Path, required=True)
    parser.add_argument("--arrangement-intelligence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    paths = [args.hard_cases, args.retrieval_modes, args.session_grounded, args.assistant_recovery, args.arrangement_intelligence]
    try:
        results = [_load(path) for path in paths]
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"schema": SCHEMA, "status": "invalid", "error": str(exc), "passed": False}, indent=2))
        return 2
    passed, details = evaluate_intelligence_results(results)
    payload = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": _tracked_source_sha256(),
        "commands": [
            "python3 tooling/scripts/evaluate_chat_hard_cases.py",
            "python3 tooling/scripts/evaluate_retrieval_modes.py",
            "python3 tooling/scripts/evaluate_session_grounded_advice.py",
            "python3 tooling/scripts/qualify_assistant_recovery.py",
            "python3 tooling/scripts/evaluate_arrangement_intelligence.py",
        ],
        "component_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
        "passed": passed,
        "details": details,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

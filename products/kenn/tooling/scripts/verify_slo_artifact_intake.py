#!/usr/bin/env python3
"""Verify an external SLO model handoff without loading its checkpoint."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend" / "src"))
from kenn.core.slo_artifact_intake import sha256_file, validate_intake  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--label-map", required=True, type=Path)
    parser.add_argument("--preprocessing", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--evaluation", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        evaluation_text = args.evaluation.read_text(encoding="utf-8")
        evaluation = json.loads(evaluation_text)
        report = validate_intake(
            manifest, model_sha256=sha256_file(args.model), label_map_sha256=sha256_file(args.label_map),
            preprocessing_sha256=sha256_file(args.preprocessing), calibration_sha256=sha256_file(args.calibration),
            evaluation=evaluation, evaluation_sha256=sha256_file(args.evaluation),
        )
    except (OSError, json.JSONDecodeError) as exc:
        report = {"schema": "kenn.slo_artifact_intake_receipt.v1", "status": "invalid", "advisory_eligible": False, "errors": [str(exc)]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("advisory_eligible") else 2


if __name__ == "__main__":
    raise SystemExit(main())

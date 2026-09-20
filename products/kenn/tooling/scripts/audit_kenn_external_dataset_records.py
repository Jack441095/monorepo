#!/usr/bin/env python3
"""Audit a prepared external text-only JSONL sample without network access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="Prepared JSONL records; raw media is not accepted.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "training" / "huggingface_dataset_candidates.json",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()

    from kenn.training.dataset_intake import load_manifest
    from kenn.training.external_dataset_records import audit_records
    from kenn.training.training_records import read_jsonl

    try:
        records = read_jsonl(args.input, missing_ok=False)
        report = audit_records(records, manifest=load_manifest(args.manifest))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


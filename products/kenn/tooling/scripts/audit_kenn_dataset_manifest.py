#!/usr/bin/env python3
"""Audit KENN's external dataset candidate registry without downloading data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "training" / "huggingface_dataset_candidates.json",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    args = parser.parse_args()

    from kenn.training.dataset_intake import DatasetManifestError, audit_manifest, load_manifest

    try:
        report = audit_manifest(load_manifest(args.manifest))
    except DatasetManifestError as exc:
        parser.error(str(exc))
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

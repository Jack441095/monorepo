#!/usr/bin/env python3
"""Inspect a separately trained SLO export without importing or enabling it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True, help="SLO export manifest JSON.")
    parser.add_argument("--no-verify-files", action="store_true", help="Validate manifest shape only; do not hash listed files.")
    args = parser.parse_args()

    from kenn.core.slo_artifact_manifest import inspect_manifest_file
    result = inspect_manifest_file(args.manifest, verify_files=not args.no_verify_files)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "verified" else 2


if __name__ == "__main__":
    raise SystemExit(main())

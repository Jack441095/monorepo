#!/usr/bin/env python3
"""Dry-run or explicitly promote a preflighted KENN retrieval-index candidate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.retrieval_index_promotion import promote_candidate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--target-root", type=Path, required=True)
    parser.add_argument("--expected-manual-sha256", required=True)
    parser.add_argument("--expected-manual-filename", default="live12-manual-en.pdf")
    parser.add_argument("--apply", action="store_true", help="Perform the atomic pointer promotion; default is read-only dry-run.")
    args = parser.parse_args()
    report = promote_candidate(
        args.candidate_root, args.target_root,
        expected_manual_sha256=args.expected_manual_sha256,
        expected_manual_filename=args.expected_manual_filename,
        apply=args.apply,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] in {"dry_run_verified", "promoted"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

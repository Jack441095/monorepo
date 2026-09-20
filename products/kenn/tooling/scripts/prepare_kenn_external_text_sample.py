#!/usr/bin/env python3
"""Map local Hugging Face-style JSONL rows into KENN's text-only schema."""

from __future__ import annotations

import argparse
from pathlib import Path

from repo_python import python_executable  # noqa: F401 - keeps script environment contract explicit


REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path, help="A local JSONL export; no network retrieval is performed.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-revision", required=True)
    parser.add_argument("--hub-url", required=True)
    parser.add_argument("--declared-license", required=True)
    parser.add_argument("--use-classification", required=True, choices=("commercial", "research_only", "evaluation_only", "blocked"))
    parser.add_argument("--lane", required=True, choices=("knowledge", "perception", "symbolic", "evaluation"))
    parser.add_argument("--max-records", type=int, default=0, help="Optional positive cap; zero means all rows.")
    args = parser.parse_args()
    if args.max_records < 0:
        parser.error("--max-records must be zero or positive")

    import sys

    sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
    from kenn.training.external_dataset_records import prepare_text_record
    from kenn.training.training_records import read_jsonl, write_jsonl

    try:
        raw_rows = read_jsonl(args.input, missing_ok=False)
        if args.max_records:
            raw_rows = raw_rows[: args.max_records]
        records = [
            prepare_text_record(
                row,
                dataset_id=args.dataset_id,
                dataset_revision=args.dataset_revision,
                hub_url=args.hub_url,
                declared_license=args.declared_license,
                use_classification=args.use_classification,
                lane=args.lane,
                ordinal=index,
            )
            for index, row in enumerate(raw_rows)
        ]
        write_jsonl(args.output, records, sort_keys=True)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Prepared {len(records)} text-only records at {args.output}")
    print("Next step: run audit_kenn_external_dataset_records.py; no training or media retrieval is implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


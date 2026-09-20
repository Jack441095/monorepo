#!/usr/bin/env python3
"""Export validator-approved supervised-session outcomes for offline review.

The source database holds only category-level records. This exporter writes
one evaluator-compatible JSON file per record and refuses to overwrite an
existing export, keeping the review evidence append-only by default.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))

from kenn.core.session_outcome_contract import ALLOWED_KEYS, SCHEMA
from kenn.core.session_outcome_store import SessionOutcomeStore


def export_records(database: Path, output_dir: Path) -> dict[str, Any]:
    """Write safe evaluator inputs without exposing SQLite implementation data."""
    rows = SessionOutcomeStore(database).recent(limit=500)
    safe_rows = [
        {key: row[key] for key in sorted(ALLOWED_KEYS)}
        for row in rows
        if isinstance(row, dict) and row.get("schema") == SCHEMA and set(row) >= ALLOWED_KEYS
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    targets = [output_dir / f"{row['session_bucket'][7:19]}-{index:04d}.json" for index, row in enumerate(safe_rows, start=1)]
    conflicts = [path.name for path in targets if path.exists()]
    if conflicts:
        return {"ok": False, "schema": SCHEMA, "exported": 0, "errors": ["refusing to overwrite existing export files"], "conflicts": conflicts}
    for target, row in zip(targets, safe_rows):
        target.write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True, "schema": SCHEMA, "exported": len(targets),
        "output_dir": str(output_dir),
        "privacy": {"stores_raw_prompts": False, "stores_audio": False, "stores_paths": False, "stores_identities": False},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True, help="KENN's local SQLite database.")
    parser.add_argument("--output-dir", type=Path, required=True, help="New or empty directory for evaluator JSON files.")
    args = parser.parse_args()
    result = export_records(args.database.expanduser().resolve(), args.output_dir.expanduser().resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

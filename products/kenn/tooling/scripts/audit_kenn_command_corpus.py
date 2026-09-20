#!/usr/bin/env python3
"""Audit a KENN command corpus before spending compute on training.

The audit is deliberately conservative.  It proves schema/validator and
holdout checks, then reports how much of an export is genuinely distinct
language versus mechanical oversampling.  It does not claim that synthetic
records measure human command quality.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))

SCHEMA = "kenn.ableton_command_corpus_audit.v1"
DEFAULT_INPUT = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "artifacts" / "training" / "ableton_command_corpus.jsonl"


def _read_rows(path: Path) -> list[dict[str, Any]]:
    from kenn.training.training_records import read_jsonl

    rows = read_jsonl(path, missing_ok=False)
    if not rows:
        raise ValueError("The command corpus is empty.")
    return rows


def audit_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    from build_kenn_command_training import assert_no_holdout_overlap, training_snapshot
    from build_kenn_command_corpus import scenario_snapshots
    from kenn.core.live_command import validate_llm_plan
    from kenn.core.live_intent import parse_request

    snapshots = scenario_snapshots()
    assert_no_holdout_overlap(rows)
    validation_errors: list[str] = []
    parser_contract_matches = 0
    parser_contract_total = 0
    mechanical_rows = 0
    unique_queries: set[str] = set()
    unique_labels: set[str] = set()
    scenarios: Counter[str] = Counter()
    categories: Counter[str] = Counter()
    actions: Counter[str] = Counter()

    for row in rows:
        record_id = str(row.get("record_id", "<missing-record-id>"))
        if row.get("schema") != "kenn.ableton_command_training.v1":
            validation_errors.append(f"{record_id}: unsupported schema")
            continue
        scenario = row.get("scenario")
        if scenario is None:
            snapshot = training_snapshot()
            scenario_key = "base"
        elif isinstance(scenario, int) and not isinstance(scenario, bool) and 1 <= scenario <= len(snapshots):
            snapshot = snapshots[scenario - 1]
            scenario_key = str(scenario)
        else:
            validation_errors.append(f"{record_id}: unsupported scenario {scenario!r}")
            continue
        label = row.get("label")
        checked = validate_llm_plan(label, snapshot)
        if not checked.get("ok"):
            validation_errors.append(f"{record_id}: {checked.get('error', 'invalid label')}")
        query = str(row.get("query", ""))
        unique_queries.add(query)
        unique_labels.add(json.dumps(label, sort_keys=True, separators=(",", ":")))
        scenarios[scenario_key] += 1
        categories[str(row.get("category", ""))] += 1
        actions[str((label or {}).get("action", ""))] += 1
        if "(variant " in query:
            mechanical_rows += 1

        category = str(row.get("category", ""))
        if category != "ambiguity" and category != "unsupported":
            parser_contract_total += 1
            parsed = parse_request(query, snapshot)
            expected_action = (label or {}).get("action")
            if parsed.get("action") == expected_action and not parsed.get("missing_fields") and not parsed.get("ambiguity"):
                parser_contract_matches += 1

    records = len(rows)
    natural_rows = records - mechanical_rows
    parser_ratio = parser_contract_matches / parser_contract_total if parser_contract_total else None
    warnings = [
        "Synthetic records are not evidence of human language quality or Live success.",
    ]
    if mechanical_rows:
        warnings.append("The export contains mechanical variant markers; review distinct language before training.")
    if parser_ratio is not None and parser_ratio < 0.80:
        warnings.append("The deterministic parser does not fully recognize most supported/inspection variants; inspect labels and phrasing.")
    if validation_errors:
        warnings.append("One or more labels failed the plan validator.")

    return {
        "schema": SCHEMA,
        "status": "review_required" if not validation_errors else "invalid",
        "evidence_kind": "synthetic_training_corpus_audit",
        "records": records,
        "unique_queries": len(unique_queries),
        "unique_labels": len(unique_labels),
        "natural_language_rows": natural_rows,
        "mechanical_variant_rows": mechanical_rows,
        "mechanical_variant_ratio": round(mechanical_rows / records, 6) if records else 0.0,
        "parser_contract": {
            "matches": parser_contract_matches,
            "eligible": parser_contract_total,
            "match_ratio": round(parser_ratio, 6) if parser_ratio is not None else None,
        },
        "scenarios": dict(sorted(scenarios.items())),
        "categories": dict(sorted(categories.items())),
        "actions": dict(sorted(actions.items())),
        "holdout_protection": "passed" if not validation_errors else "not_proven",
        "validation_errors": validation_errors,
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit_rows(_read_rows(args.input.expanduser().resolve()))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if result["status"] == "review_required" else 2


if __name__ == "__main__":
    raise SystemExit(main())

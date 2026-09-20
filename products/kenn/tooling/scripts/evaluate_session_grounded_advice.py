#!/usr/bin/env python3
"""Evaluate retrieval advice plus exact, separately labelled Live evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "chat"))
from kenn import ableton_osc_bridge, server  # noqa: E402

SCHEMA = "kenn.session_grounded_advice_benchmark.v1"
DEFAULT_CASES = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "session_grounded_cases.json"
LIVE_LABEL = "Live session evidence (observed just now, not inferred):"


def evaluate(*, cases_path: Path = DEFAULT_CASES, answerer: Callable[[str, str], dict[str, Any]] | None = None) -> dict[str, Any]:
    raw = cases_path.read_bytes()
    document = json.loads(raw)
    if document.get("schema") != "kenn.session_grounded_cases.v1" or not isinstance(document.get("cases"), list):
        raise ValueError("invalid session-grounded case corpus")
    rows = []
    original_query = ableton_osc_bridge.live_client.query_session_state
    try:
        for case in document["cases"]:
            snapshot = case.get("snapshot")
            ableton_osc_bridge.live_client.query_session_state = lambda snapshot=snapshot: snapshot
            payload = (answerer or server.grounded_knowledge_answer)(str(case.get("question") or ""), "session-grounded-eval")
            sources = [str(item.get("source") or "") for item in payload.get("sources", []) if isinstance(item, dict)]
            expected_evidence = case.get("expected_session_evidence")
            actual_evidence = payload.get("session_evidence")
            answer = str(payload.get("answer") or "")
            failures = []
            if payload.get("found") is not True:
                failures.append("knowledge_not_found")
            if str(case.get("source_must_include") or "") not in sources:
                failures.append("required_source_missing")
            if expected_evidence is None:
                if actual_evidence is not None or LIVE_LABEL in answer:
                    failures.append("unjustified_session_evidence")
            else:
                if actual_evidence != [expected_evidence]:
                    failures.append("session_evidence_mismatch")
                if LIVE_LABEL not in answer:
                    failures.append("observed_evidence_not_labelled")
                if answer.count(LIVE_LABEL) != 1:
                    failures.append("observed_evidence_label_count")
            rows.append({"id": str(case.get("id") or "unknown"), "passed": not failures, "failures": failures,
                         "source_count": len(sources), "session_evidence_count": len(actual_evidence or [])})
    finally:
        ableton_osc_bridge.live_client.query_session_state = original_query
    failed = sum(not row["passed"] for row in rows)
    return {"schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(),
            "cases_sha256": hashlib.sha256(raw).hexdigest(), "case_count": len(rows),
            "passed": len(rows) - failed, "failed": failed, "qualified": bool(rows) and failed == 0,
            "rows": rows, "privacy": {"stores_questions": False, "stores_answers": False, "stores_live_names": False},
            "limitations": ["Synthetic Live snapshots verify evidence separation; they do not replace real-Live qualification."]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    receipt = evaluate(cases_path=args.cases.expanduser().resolve())
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        target = args.output.expanduser().resolve(); target.parent.mkdir(parents=True, exist_ok=True); target.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt["qualified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

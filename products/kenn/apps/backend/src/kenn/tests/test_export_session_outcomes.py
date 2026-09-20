from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from kenn.core.session_outcome_contract import SCHEMA, STAGES
from kenn.core.session_outcome_store import SessionOutcomeStore


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "export_session_outcomes.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("export_session_outcomes", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def _outcome() -> dict:
    bucket = lambda value: "sha256:" + f"{value:064x}"
    return {
        "schema": SCHEMA, "session_bucket": bucket(1), "project_bucket": bucket(2),
        "tester_bucket": bucket(3), "intent_class": "advice", "context_freshness": "fresh",
        "evidence_classes": ["live_snapshot"], "lifecycle_outcome": "completed",
        "user_verdict": "keep", "reason_codes": [], "root_cause": None,
        "latency_ms": {stage: 1 for stage in STAGES},
        "contains_raw_prompt": False, "contains_audio": False,
    }


def test_export_writes_evaluator_compatible_safe_records_without_overwrite(tmp_path) -> None:
    database, output = tmp_path / "kenn.sqlite3", tmp_path / "export"
    SessionOutcomeStore(database).record(_outcome())

    first = module.export_records(database, output)
    exported = next(output.glob("*.json"))
    second = module.export_records(database, output)

    assert first["ok"] is True
    assert json.loads(exported.read_text())["schema"] == SCHEMA
    assert second["ok"] is False
    assert "overwrite" in second["errors"][0]

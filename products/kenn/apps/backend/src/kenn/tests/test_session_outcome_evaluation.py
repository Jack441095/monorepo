from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[5] / "tooling" / "scripts" / "evaluate_session_outcomes.py"
module = importlib.util.module_from_spec(spec := importlib.util.spec_from_file_location("session_outcomes", SCRIPT))
assert spec.loader
spec.loader.exec_module(module)


def _bucket(value: int) -> str:
    return "sha256:" + f"{value:064x}"


def _log(*, verdict: str = "keep", root_cause: str | None = None) -> dict[str, object]:
    return {
        "schema": module.SCHEMA, "session_bucket": _bucket(1), "project_bucket": _bucket(2),
        "tester_bucket": _bucket(3), "intent_class": "proposal", "context_freshness": "fresh",
        "evidence_classes": ["live_snapshot", "retrieval", "official_ableton_manual"], "lifecycle_outcome": "completed",
        "user_verdict": verdict, "reason_codes": [], "root_cause": root_cause,
        "latency_ms": {stage: 10 for stage in module.STAGES},
        "contains_raw_prompt": False, "contains_audio": False,
    }


def test_valid_outcomes_are_aggregated_without_identity_or_content(tmp_path: Path) -> None:
    first, second = _log(), _log(verdict="revise", root_cause="retrieval")
    second["session_bucket"] = _bucket(4)
    paths = []
    for index, value in enumerate((first, second)):
        path = tmp_path / f"session-{index}.json"; path.write_text(json.dumps(value)); paths.append(path)
    report = module.evaluate(paths)
    assert report["metrics"]["valid_session_count"] == 2
    assert report["metrics"]["root_cause_label_rate"] == 1.0
    assert report["counts"]["root_cause"] == {"retrieval": 1}
    assert report["counts"]["evidence_class"] == {
        "live_snapshot": 2, "official_ableton_manual": 2, "retrieval": 2,
    }
    assert all("bucket" not in row for row in report["rows"])
    assert report["privacy"]["stores_raw_prompts"] is False


def test_miss_without_root_cause_and_raw_content_are_rejected(tmp_path: Path) -> None:
    value = _log(verdict="unsafe")
    value["prompt"] = "please change the mix"
    path = tmp_path / "unsafe.json"; path.write_text(json.dumps(value))
    report = module.evaluate([path])
    assert report["metrics"]["invalid_session_count"] == 1
    assert report["rows"] == [{"valid": False, "failures": ["raw_content", "root_cause"]}]


def test_stage_latency_requires_exact_nonnegative_integer_schema() -> None:
    value = _log()
    value["latency_ms"] = {"context": -1}
    assert module.validate(value) == ["latency_ms"]

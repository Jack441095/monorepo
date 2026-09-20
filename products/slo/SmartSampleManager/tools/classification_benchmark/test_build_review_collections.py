import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_review_collections.py")
SPEC = importlib.util.spec_from_file_location("build_review_collections", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write_jsonl(path, rows):
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_builds_action_collections_and_joins_evidence(tmp_path):
    plan = tmp_path / "plan.jsonl"
    evidence = tmp_path / "evidence.jsonl"
    source = str(tmp_path / "sound.wav")
    header = {"record_type": "slo_rename_plan", "model": "test-model"}
    row = {
        "path": source,
        "destination": str(tmp_path / "Kick - sound.wav"),
        "decision": {"action": "suggest", "reason": "review", "policy_version": "p1", "requires_approval": True},
        "full_taxonomy_class": "Kick",
        "full_taxonomy_confidence": 0.8,
        "full_taxonomy_similarity": 0.5,
        "filename_class": "Kick",
        "applied": False,
        "approved": False,
    }
    _write_jsonl(plan, [header, row])
    _write_jsonl(evidence, [
        {"record_type": "slo_review_evidence_packet", "n_rows": 1},
        {"path": source, "prediction": {"class": "Kick"}, "definition_card": {"source": {"analysis_duration_seconds": 1.0}}},
    ])
    result = MODULE.build_collections(plan, evidence)
    assert result["summary"] == {"auto_rename": 0, "suggest": 1, "review": 0, "never_act": 0}
    assert result["n_joined_evidence"] == 1
    assert result["collections"]["suggest"][0]["review_evidence"]["facets"]["duration_seconds"] == 1.0
    assert result["safety"]["rename_plan_applied"] is False


def test_unknown_action_fails_closed(tmp_path):
    plan = tmp_path / "plan.jsonl"
    _write_jsonl(plan, [
        {"record_type": "slo_rename_plan"},
        {"path": str(tmp_path / "x.wav"), "decision": {"action": "maybe"}},
    ])
    try:
        MODULE.build_collections(plan)
    except ValueError as exc:
        assert "unsupported decision action" in str(exc)
    else:
        raise AssertionError("unknown action was accepted")

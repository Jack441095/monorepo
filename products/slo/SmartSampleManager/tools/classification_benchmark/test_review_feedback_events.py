import importlib.util
from pathlib import Path
import subprocess
import sys


MODULE_PATH = Path(__file__).with_name("review_feedback_events.py")
SPEC = importlib.util.spec_from_file_location("review_feedback_events", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _event(tmp_path, event_type="not_in_list"):
    event = {
        "event_id": "evt-1",
        "event_type": event_type,
        "path": str((tmp_path / "sound.wav").resolve()),
        "actor": "reviewer",
        "created_at": "2026-09-11T00:00:00Z",
        "source_plan_sha256": "a" * 64,
        "previous_decision": "review",
    }
    if event_type == "not_in_list":
        event["note"] = "metallic machine hit"
    if event_type == "correct_class":
        event["corrected_class"] = "Kick"
    if event_type == "mark_duplicate":
        event["canonical_path"] = str((tmp_path / "canonical.wav").resolve())
    if event_type == "note":
        event["note"] = "needs owner review"
    return event


def test_append_and_read_are_append_only(tmp_path):
    log = tmp_path / "events.jsonl"
    created = MODULE.append_event(log, _event(tmp_path))
    assert created["promoted_to_gold"] is False
    assert len(MODULE.read_events(log)) == 1
    before = log.read_bytes()
    try:
        MODULE.append_event(log, _event(tmp_path))
    except ValueError as exc:
        assert "already exists" in str(exc)
    else:
        raise AssertionError("duplicate event was accepted")
    assert log.read_bytes() == before


def test_required_context_is_fail_closed(tmp_path):
    event = _event(tmp_path)
    del event["note"]
    try:
        MODULE.validate_event(event)
    except ValueError as exc:
        assert "note" in str(exc)
    else:
        raise AssertionError("not-in-list event without note was accepted")


def test_duplicate_event_requires_distinct_canonical(tmp_path):
    event = _event(tmp_path, "mark_duplicate")
    event["canonical_path"] = event["path"]
    try:
        MODULE.validate_event(event)
    except ValueError as exc:
        assert "differ" in str(exc)
    else:
        raise AssertionError("self-canonical duplicate was accepted")


def test_name_candidate_feedback_is_append_only_and_safe(tmp_path):
    event = _event(tmp_path, "accept_name_candidate")
    event["candidate_filename"] = "kick_one-shot.wav"
    normalized = MODULE.validate_event(event)
    assert normalized["promoted_to_gold"] is False

    corrected = _event(tmp_path, "correct_name_candidate")
    corrected["candidate_filename"] = "kick_one-shot.wav"
    corrected["corrected_filename"] = "snare_one-shot.wav"
    assert MODULE.validate_event(corrected)["event_type"] == "correct_name_candidate"

    rejected = _event(tmp_path, "reject_name_candidate")
    rejected["candidate_filename"] = "kick_one-shot.wav"
    rejected["note"] = "not a kick"
    assert MODULE.validate_event(rejected)["event_type"] == "reject_name_candidate"

    unsafe = dict(event, candidate_filename="../escape.wav")
    try:
        MODULE.validate_event(unsafe)
    except ValueError as exc:
        assert "safe filename" in str(exc)
    else:
        raise AssertionError("path-bearing name candidate was accepted")


def test_fused_candidate_feedback_requires_explicit_labels(tmp_path):
    accepted = _event(tmp_path, "accept_fused_candidate")
    accepted["candidate_label"] = "Kick"
    assert MODULE.validate_event(accepted)["promoted_to_gold"] is False

    corrected = _event(tmp_path, "correct_fused_candidate")
    corrected["candidate_label"] = "Kick"
    corrected["corrected_label"] = "Snare"
    assert MODULE.validate_event(corrected)["event_type"] == "correct_fused_candidate"

    rejected = _event(tmp_path, "reject_fused_candidate")
    rejected["candidate_label"] = "Kick"
    rejected["note"] = "ambiguous transient"
    assert MODULE.validate_event(rejected)["event_type"] == "reject_fused_candidate"


def test_cli_accepts_fused_candidate_labels(tmp_path):
    log = tmp_path / "events.jsonl"
    audio = tmp_path / "sound.wav"
    result = subprocess.run(
        [sys.executable, str(MODULE_PATH),
         "--log", str(log), "--path", str(audio),
         "--event-type", "correct_fused_candidate",
         "--actor", "reviewer", "--source-plan-sha256", "a" * 64,
         "--previous-decision", "review",
         "--candidate-label", "Kick", "--corrected-label", "Snare"],
        check=False, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    rows = MODULE.read_events(log)
    assert len(rows) == 1
    assert rows[0]["candidate_label"] == "Kick"
    assert rows[0]["corrected_label"] == "Snare"

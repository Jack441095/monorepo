import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_rename_plan.py")
SPEC = importlib.util.spec_from_file_location("build_rename_plan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _auto_row():
    return {
        "action": "auto_rename",
        "displayed_label": "Kick",
        "requires_approval": False,
        "reason": "classifier recommendation",
    }


def test_auto_recommendation_is_review_only_without_explicit_policy():
    result = MODULE.apply_qualification_gate(_auto_row(), set(), False)
    assert result["action"] == "review"
    assert result["candidate_action"] == "auto_rename"
    assert result["requires_approval"] is True


def test_auto_recommendation_requires_class_membership():
    result = MODULE.apply_qualification_gate(_auto_row(), {"Snare"}, True)
    assert result["action"] == "review"
    assert result["requires_approval"] is True


def test_qualified_auto_recommendation_can_remain_auto():
    result = MODULE.apply_qualification_gate(_auto_row(), {"Kick"}, True)
    assert result["action"] == "auto_rename"
    assert result["requires_approval"] is False


def test_empty_policy_is_safe_default(tmp_path):
    policy = tmp_path / "empty.json"
    policy.write_text("{}", encoding="utf-8")
    assert MODULE.load_qualified(str(policy)) == set()


def test_class_threshold_policy_is_opt_in_and_validated(tmp_path):
    policy = tmp_path / "thresholds.json"
    policy.write_text('{"thresholds": {"Kick": 0.81, "Clap": 0.72}}', encoding="utf-8")
    assert MODULE.load_class_thresholds(str(policy)) == {"Kick": 0.81, "Clap": 0.72}
    row = {"audio_class": "Kick", "audio_confidence": 0.80,
           "filename_class": "", "path": "/tmp/kick.wav"}
    result = MODULE.decision(row, 0.5, MODULE.load_class_thresholds(str(policy)))
    assert result["action"] == "review"
    assert result["evidence"]["threshold"] == 0.81


def test_class_threshold_policy_rejects_invalid_value(tmp_path):
    policy = tmp_path / "bad_thresholds.json"
    policy.write_text('{"Kick": 1.5}', encoding="utf-8")
    try:
        MODULE.load_class_thresholds(str(policy))
    except ValueError as exc:
        assert "invalid threshold" in str(exc)
    else:
        raise AssertionError("invalid class threshold was accepted")

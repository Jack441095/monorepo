import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_manifest_from_review.py")
SPEC = importlib.util.spec_from_file_location("build_label_manifest_from_review", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _payload(tmp_path):
    first = str((tmp_path / "b.wav").resolve())
    second = str((tmp_path / "a.wav").resolve())
    return {
        "record_type": "slo_review_collections",
        "collections": {
            "suggest": [{"path": first, "predicted_class": "Kick"}],
            "review": [{"path": second, "predicted_class": "Snare"}],
            "never_act": [], "auto_rename": [],
        },
    }


def test_manifest_is_sorted_deterministic_and_blind(tmp_path):
    result = MODULE.build_manifest(_payload(tmp_path), ["suggest", "review"])
    assert [row["id"] for row in result] == [0, 1]
    assert [row["path"] for row in result] == sorted(row["path"] for row in result)
    assert all(row["hint"] == "" for row in result)


def test_prediction_hint_is_explicit_opt_in(tmp_path):
    result = MODULE.build_manifest(_payload(tmp_path), ["suggest"], show_prediction=True)
    assert result[0]["hint"] == "Kick"


def test_balanced_selection_round_robins_collections(tmp_path):
    root = tmp_path / "root"
    payload = {"record_type": "slo_review_collections", "collections": {
        "suggest": [], "review": [], "never_act": [], "auto_rename": [],
    }}
    for name in ("A", "B", "C"):
        for index in range(2):
            path = str((root / name / f"{index}.wav").resolve())
            payload["collections"]["review"].append({"path": path})
    result = MODULE.build_manifest(payload, ["review"], limit=6,
                                   source_root=root, balanced=True)
    assert [row["collection"] for row in result] == ["A", "B", "C", "A", "B", "C"]


def test_balanced_selection_requires_source_root(tmp_path):
    try:
        MODULE.build_manifest(_payload(tmp_path), ["suggest"], balanced=True)
    except ValueError as exc:
        assert "source-root" in str(exc)
    else:
        raise AssertionError("balanced selection without a root was accepted")


def test_manifest_rejects_relative_or_duplicate_paths(tmp_path):
    payload = _payload(tmp_path)
    payload["collections"]["review"].append(payload["collections"]["suggest"][0])
    try:
        MODULE.build_manifest(payload, ["suggest", "review"])
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate review path was accepted")

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("export_owner_review_queue.py")
SPEC = importlib.util.spec_from_file_location("export_owner_review_queue", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_queue_flattens_evidence_and_orders_duplicate_first(tmp_path):
    collection = tmp_path / "collection.json"
    guard = tmp_path / "guard.json"
    _write(collection, {
        "record_type": "slo_review_collections",
        "collections": {"suggest": [
            {"path": "/b.wav", "destination": "/b-new.wav", "predicted_class": "Kick", "filename_class": "Kick", "confidence": 0.9, "similarity": 0.8, "reason": "x", "review_evidence": {"facets": {"form_hint": "one_shot"}}},
            {"path": "/a.wav", "destination": "/a-new.wav", "predicted_class": "Clap", "filename_class": "", "confidence": 0.8, "similarity": 0.75, "reason": "y", "review_evidence": {"nearest_labelled_reference": {"label": "Clap", "path": "/ref.wav"}, "aspect_similarity_to_reference": {"overall": 0.6}, "facets": {"duration_seconds": 0.2, "form_hint": "one_shot", "spectral_centroid_hz": 2000}}},
        ]},
    })
    _write(guard, {"record_type": "slo_rename_duplicate_guard_audit", "rows": [{"path": "/a.wav", "flags": ["acoustic_near_duplicate"]}, {"path": "/b.wav", "flags": []}]})
    receipt, rows = MODULE.build_queue(collection, guard)
    assert receipt["n_rows"] == 2
    assert rows[0]["path"] == "/a.wav"
    assert rows[0]["duplicate_flags"] == "acoustic_near_duplicate"
    assert rows[0]["nearest_reference_label"] == "Clap"
    assert rows[0]["aspect_overall"] == 0.6
    assert rows[1]["form_hint"] == "one_shot"


def test_queue_fails_closed_when_guard_row_is_missing(tmp_path):
    collection = tmp_path / "collection.json"
    guard = tmp_path / "guard.json"
    _write(collection, {"record_type": "slo_review_collections", "collections": {"suggest": [{"path": "/missing.wav"}]}})
    _write(guard, {"record_type": "slo_rename_duplicate_guard_audit", "rows": []})
    try:
        MODULE.build_queue(collection, guard)
    except ValueError as exc:
        assert "no matching duplicate-guard row" in str(exc)
    else:
        raise AssertionError("missing guard row must fail closed")

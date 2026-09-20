import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_owner_approved_training_manifest.py")
SPEC = importlib.util.spec_from_file_location("build_owner_approved_training_manifest", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_matching_approved_row_is_separate_supplement(tmp_path):
    source = tmp_path / "sound.wav"
    source.write_bytes(b"audio fixture")
    import hashlib
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    base = tmp_path / "base.json"
    base.write_text(json.dumps({
        "rows": [{"path": str(source), "content_sha256": digest, "label": "Old", "vendor": "V", "pack": "P"}],
        "duplicate_aliases": [], "excluded_validation_paths": [],
        "safety": {"validation_rows_used_for_training": False},
    }), encoding="utf-8")
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_text(json.dumps({"record_type": "header"}) + "\n" + json.dumps({
        "promotion_status": "owner_approved_pending_rebuild", "correction_id": "corr-1",
        "file_path": str(source), "content_hash": digest, "corrected_subcategory": "Kick",
        "correction_type": "label_correction", "reviewer": "jack",
    }) + "\n", encoding="utf-8")
    out = tmp_path / "supplement.json"
    result = MODULE.build(base, candidate, out)
    assert result["summary"] == {"approved_candidates_seen": 1, "accepted_rows": 1, "blocked_rows": 0}
    assert result["safety"]["training_corpus_modified"] is False
    assert json.loads(out.read_text())["rows"][0]["label"] == "Kick"


def test_unknown_or_hash_mismatch_is_blocked(tmp_path):
    base = tmp_path / "base.json"
    base.write_text(json.dumps({"rows": [{"path": "/known.wav", "content_sha256": "a" * 64}],
                                "duplicate_aliases": [], "excluded_validation_paths": [],
                                "safety": {"validation_rows_used_for_training": False}}), encoding="utf-8")
    candidate = tmp_path / "candidate.jsonl"
    candidate.write_text(json.dumps({"record_type": "header"}) + "\n" + json.dumps({
        "promotion_status": "owner_approved_pending_rebuild", "correction_id": "corr-1",
        "file_path": "/unknown.wav", "content_hash": "b" * 64, "corrected_category": "Kick",
    }) + "\n", encoding="utf-8")
    result = MODULE.build(base, candidate, tmp_path / "out.json")
    assert result["summary"]["accepted_rows"] == 0
    assert result["blocked"][0]["reason"] == "path_not_in_canonical_training_manifest"

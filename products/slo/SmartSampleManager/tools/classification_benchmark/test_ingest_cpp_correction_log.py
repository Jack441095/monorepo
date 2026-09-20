import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("ingest_cpp_correction_log.py")
SPEC = importlib.util.spec_from_file_location("ingest_cpp_correction_log", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _record(path: Path, kind: str = "taxonomy_gap", note: str = "missing class") -> dict:
    return {
        "ts": "2026-09-12T12:00:00Z",
        "file_path": str(path.resolve()),
        "content_hash": "a" * 64,
        "original_category": "Drums",
        "original_subcategory": "Percussion",
        "original_evidence": "DSP",
        "original_confidence": 0.42,
        "corrected_category": "FX",
        "corrected_subcategory": "Machine",
        "correction_type": kind,
        "user_note": note,
        "taxonomy_version": "7",
        "classifier_version": "4",
        "policy_version": "1.0.0",
        "status": "pending",
    }


def test_read_and_export_are_read_only_and_typed(tmp_path):
    source = tmp_path / "sound.wav"
    source.write_bytes(b"not decoded")
    log = tmp_path / "corrections.jsonl"
    log.write_text(json.dumps(_record(source)) + "\n", encoding="utf-8")
    rows = MODULE.read_log(log)
    assert rows[0]["correction_type"] == "taxonomy_gap"
    assert rows[0]["path_exists"] is True
    out = tmp_path / "packet"
    result = MODULE.export_packet(rows, out, log)
    assert result["automatic_promotion"] is False
    assert json.loads((out / "pending_corrections_review.json").read_text())["safety"]["audio_decoded"] is False
    assert source.read_bytes() == b"not decoded"
    try:
        MODULE.export_packet(rows, out, log)
    except ValueError as exc:
        assert "overwrite" in str(exc)
    else:
        raise AssertionError("existing packet was overwritten")


def test_escape_hatches_require_notes(tmp_path):
    source = tmp_path / "sound.wav"
    raw = _record(source, "not_in_list", "")
    try:
        MODULE.normalize_record(raw, line_number=1, raw_line="{}");
    except ValueError as exc:
        assert "requires user_note" in str(exc)
    else:
        raise AssertionError("note-less escape hatch was accepted")


def test_rejects_non_pending_and_relative_paths(tmp_path):
    source = tmp_path / "sound.wav"
    raw = _record(source)
    raw["status"] = "promoted"
    try:
        MODULE.normalize_record(raw, line_number=1, raw_line="{}");
    except ValueError as exc:
        assert "pending" in str(exc)
    else:
        raise AssertionError("promoted record was accepted as pending")
    raw = _record(source)
    raw["file_path"] = "relative.wav"
    try:
        MODULE.normalize_record(raw, line_number=1, raw_line="{}");
    except ValueError as exc:
        assert "absolute" in str(exc)
    else:
        raise AssertionError("relative path was accepted")

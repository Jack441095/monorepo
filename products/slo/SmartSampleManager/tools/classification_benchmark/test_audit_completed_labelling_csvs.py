import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_completed_labelling_csvs.py")
SPEC = importlib.util.spec_from_file_location("audit_completed_labelling_csvs", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _fixture(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps([
        {"id": 0, "path": "/tmp/a.wav"},
        {"id": 1, "path": "/tmp/b.wav"},
    ]), encoding="utf-8")
    csv_path = tmp_path / "labels.csv"
    csv_path.write_text(
        "id,label,path,note,not_in_list_label\n"
        "0,Kick,/tmp/a.wav,,\n"
        "1,Not in list,/tmp/b.wav,,Bongo\n",
        encoding="utf-8",
    )
    return csv_path, manifest


def test_integrity_audit_accepts_manifest_aligned_rows(tmp_path):
    csv_path, manifest = _fixture(tmp_path)
    result = MODULE.build_report([csv_path], [manifest])
    assert result["summary"]["all_integrity_ok"] is True
    assert result["summary"]["all_complete"] is True
    assert result["summary"]["n_completed"] == 2
    assert result["safety"]["labels_promoted_to_gold"] is False


def test_integrity_audit_rejects_empty_escape_hatch(tmp_path):
    csv_path, manifest = _fixture(tmp_path)
    csv_path.write_text(
        "id,label,path,note,not_in_list_label\n"
        "0,Not in list,/tmp/a.wav,,\n"
        "1,Kick,/tmp/b.wav,,\n",
        encoding="utf-8",
    )
    result = MODULE.build_report([csv_path], [manifest])
    assert result["summary"]["all_integrity_ok"] is False
    assert result["files"][0]["invalid_escape_rows"] == [0]


def test_integrity_audit_detects_path_mismatch_and_duplicate_id(tmp_path):
    csv_path, manifest = _fixture(tmp_path)
    csv_path.write_text(
        "id,label,path,note,not_in_list_label\n"
        "0,Kick,/tmp/wrong.wav,,\n"
        "0,Snare,/tmp/a.wav,,\n",
        encoding="utf-8",
    )
    result = MODULE.build_report([csv_path], [manifest])
    file_result = result["files"][0]
    assert file_result["duplicate_ids"] == [0]
    assert file_result["path_mismatches"] == [0]

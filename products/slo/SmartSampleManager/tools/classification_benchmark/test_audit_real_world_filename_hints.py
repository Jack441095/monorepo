import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("audit_real_world_filename_hints.py")
SPEC = importlib.util.spec_from_file_location("audit_real_world_filename_hints", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_filename_hints_are_metadata_only(tmp_path):
    (tmp_path / "Horse Sleigh.wav").write_bytes(b"not audio")
    (tmp_path / "Kick 01.wav").write_bytes(b"not audio")
    report = MODULE.scan(tmp_path)
    assert report["audio_files_scanned_by_metadata"] == 2
    assert report["domain_summary"]["animal"]["matched_files"] == 1
    assert report["safety"]["audio_decoded"] is False
    assert report["safety"]["labels_created"] is False
    assert report["safety"]["production_taxonomy_changed"] is False


def test_hints_can_overlap_without_becoming_a_single_label(tmp_path):
    (tmp_path / "Water splash dog.wav").write_bytes(b"not audio")
    report = MODULE.scan(tmp_path)
    assert report["domain_summary"]["animal"]["matched_files"] == 1
    assert report["domain_summary"]["environment"]["matched_files"] == 1
    assert report["next_gate"].startswith("sample matched files")

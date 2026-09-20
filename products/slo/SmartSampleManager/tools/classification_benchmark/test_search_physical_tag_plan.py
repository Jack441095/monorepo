import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("search_physical_tag_plan.py")
SPEC = importlib.util.spec_from_file_location("search_physical_tag_plan", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_search_filters_technical_facets():
    rows = [
        {"path": "/a.wav", "technical_tags": ["possibly_loop", "low_end_heavy"], "form_hint": "possibly_loop", "duration_seconds": 4, "low_band_energy_ratio": 0.8, "spectral_centroid_hz": 500},
        {"path": "/b.wav", "technical_tags": ["possibly_one_shot"], "form_hint": "possibly_one_shot", "duration_seconds": 0.5, "low_band_energy_ratio": 0.1, "spectral_centroid_hz": 5000},
    ]
    result = MODULE.search(rows, tag="low_end_heavy", min_low_band=0.7, max_centroid=1000)
    assert [row["path"] for row in result] == ["/a.wav"]


def test_load_rows_fails_on_header_count(tmp_path):
    path = tmp_path / "plan.jsonl"
    path.write_text(json.dumps({"record_type": "slo_physical_tag_plan", "n_files": 2}) + "\n" + json.dumps({"path": "/a.wav"}) + "\n")
    try:
        MODULE.load_rows(path)
    except ValueError as exc:
        assert "row count" in str(exc)
    else:
        raise AssertionError("mismatched plan count must fail closed")

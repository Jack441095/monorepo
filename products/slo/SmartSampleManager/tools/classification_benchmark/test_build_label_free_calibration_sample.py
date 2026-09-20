from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("build_label_free_calibration_sample.py")
SPEC = importlib.util.spec_from_file_location("build_label_free_calibration_sample", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _row(path: str, domain: str, agree: bool, margin: float, status: str = "review") -> dict[str, object]:
    return {
        "path": path,
        "semantic_label": None,
        "review_state": "review_required",
        "domain_route": {"domain_suggestion": domain, "status": status, "domain_margin": margin},
        "ensemble": {"model_agreement": agree, "status": status, "margin_mean": margin,
                      "ensemble_suggestion": "Kick" if agree else None,
                      "model_a_suggestion": "Kick", "model_b_suggestion": "Kick" if agree else "Snare"},
        "specialist": {"domain_suggestion": domain, "status": status, "margin": margin,
                       "specialist_suggestion": "Kick"},
    }


def test_build_sample_is_balanced_and_label_free(tmp_path: Path):
    packet = tmp_path / "packet.json"
    rows = [_row(f"/x/sample_pack_testing/PackA/{i}.wav", "music_sample", i % 2 == 0, 0.02 if i % 2 else 0.2)
            for i in range(8)]
    rows += [_row(f"/x/sample_pack_testing/PackB/{i}.wav", "environment_sfx", True, 0.2, "suggest")
             for i in range(4)]
    packet.write_text(json.dumps({"method_version": "packet", "rows": rows,
                                  "safety": {"read_only": True}}), encoding="utf-8")
    out = tmp_path / "sample.json"
    result = MODULE.build_sample(packet, out, limit=6)
    assert result["n_selected"] == 6
    assert result["lane_counts"]["model_disagreement"] >= 1
    assert result["domain_counts"]["environment_sfx"] >= 1
    assert all(row["semantic_label"] is None for row in result["rows"])
    assert result["safety"]["human_ear_review_required_for_calibration"] is True


def test_build_sample_excludes_sealed_holdout_and_exact_content_aliases(tmp_path: Path):
    packet = tmp_path / "packet.json"
    rows = [
        _row("/x/sample_pack_testing/Minimal Audio/held.wav", "music_sample", True, 0.2, "suggest")
        | {"content_sha256": "sealed-content"},
        _row("/x/sample_pack_testing/OpenPack/alias.wav", "music_sample", True, 0.2, "suggest")
        | {"content_sha256": "sealed-content"},
        _row("/x/sample_pack_testing/OpenPack/kept.wav", "music_sample", True, 0.2, "suggest")
        | {"content_sha256": "unique-content"},
        _row("/x/sample_pack_testing/OpenPack/kept-alias.wav", "music_sample", True, 0.2, "suggest")
        | {"content_sha256": "unique-content"},
    ]
    packet.write_text(json.dumps({"method_version": "packet", "rows": rows,
                                  "safety": {"read_only": True}}), encoding="utf-8")
    sealed = tmp_path / "sealed.json"
    sealed.write_text(json.dumps({"sealed_vendors": ["Minimal Audio"]}), encoding="utf-8")
    result = MODULE.build_sample(packet, tmp_path / "sample.json", limit=10,
                                 sealed_holdout_path=sealed)
    assert [row["path"] for row in result["rows"]] == [
        "/x/sample_pack_testing/OpenPack/kept.wav"
    ]
    assert result["exclusions"]["sealed_holdout_rows_excluded"] == 2
    assert result["exclusions"]["duplicate_content_rows_excluded"] == 1


def test_build_sample_rejects_duplicate_packet_paths(tmp_path: Path):
    row = _row("/x/sample_pack_testing/PackA/a.wav", "music_sample", True, 0.2)
    packet = tmp_path / "packet.json"
    packet.write_text(json.dumps({"rows": [row, row], "safety": {"read_only": True}}), encoding="utf-8")
    try:
        MODULE.build_sample(packet, tmp_path / "sample.json")
    except ValueError as exc:
        assert "duplicate path" in str(exc)
    else:
        raise AssertionError("duplicate packet path was accepted")

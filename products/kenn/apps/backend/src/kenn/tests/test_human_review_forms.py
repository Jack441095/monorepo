from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "tooling" / "scripts"))

from export_human_review_forms import build_form, export_forms


def _packet() -> dict:
    return {
        "criteria": ["clarity", "safety"],
        "scoring_scale": {"0": "bad", "1": "partial", "2": "good"},
        "cases": [{
            "case_id": "case-one",
            "category": "production",
            "question": "How should I check this vocal?",
            "response": {"answer": "Listen first", "sources": [{"title": "note"}]},
            "fixture_expectations": {"answer_must_include": ["fixture-only text"]},
            "review": {"reviewer_a": {"clarity": None}},
        }],
    }


def test_form_is_independent_and_score_blank() -> None:
    form = build_form(_packet(), reviewer_slot="a", packet_sha256="abc123")

    assert form["packet_sha256"] == "abc123"
    assert form["reviews"][0]["scores"] == {"clarity": None, "safety": None}
    assert "fixture_expectations" not in form["reviews"][0]
    assert "reviewer_b" not in str(form)
    assert form["reviewer_id"] == ""
    assert form["independent_review_confirmed"] is False


def test_export_binds_both_forms_to_same_packet(tmp_path: Path) -> None:
    packet_path = tmp_path / "packet.json"
    import json

    packet_path.write_text(json.dumps(_packet()), encoding="utf-8")
    paths = export_forms(packet_path, tmp_path / "forms")

    assert [path.name for path in paths] == ["reviewer-a.json", "reviewer-b.json"]
    first = json.loads(paths[0].read_text(encoding="utf-8"))
    second = json.loads(paths[1].read_text(encoding="utf-8"))
    assert first["packet_sha256"] == second["packet_sha256"]
    assert first["reviewer_slot"] != second["reviewer_slot"]
    assert first["reviewer_id"] == second["reviewer_id"] == ""

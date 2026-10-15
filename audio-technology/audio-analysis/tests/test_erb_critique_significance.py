"""Critique inherits the same real-preview qualification as the handoff."""

from copy import deepcopy

from audio_analysis.mix_review.mix_review_critique import critique_metrics_payload, deterministic_critique


def _measured_masking():
    return {
        "ok": True,
        "stems": [{"name": name, "overall_visibility": visibility}
                  for name, visibility in (("Bass", 0.0), ("Kick", 0.8))],
        "activity": {
            "schema": "kenn.erb_masking.activity.v1", "active_floor_dbfs": -60.0,
            "frame_size_samples": 4096,
            "sources": [{"name": name, "sample_rate": 44100, "frame_count": 1,
                         "active_frame_count": 1} for name in ("Bass", "Kick")],
            "pairs": [{"stems": ["Bass", "Kick"], "simultaneously_active_frame_count": 1}],
        },
        "erb_details": {"carving_suggestions": ["Invented repair"]},
    }


def test_critique_projects_real_zero_preview_without_causal_or_repair_advice():
    report = {"metrics": {"stem_masking": _measured_masking()}}
    before = deepcopy(report)
    payload = critique_metrics_payload(report)
    text = deterministic_critique(payload)
    assert payload["stem_masking"]["lowest_visibility"] == 0.0
    assert "Invented repair" not in str(payload)
    assert "lowest relative ERB preview visibility (0.0)" in text
    assert "uncalibrated" in text
    assert "getting buried" not in text
    assert "consider carving" not in text
    assert report == before


def test_critique_withholds_name_based_or_legacy_profiles():
    # The old critique turned plausible names and scalar profiles into repair advice.
    masking = _measured_masking()
    masking.pop("activity")
    report = {"metrics": {"stem_masking": masking}}
    payload = critique_metrics_payload(report)
    assert payload["stem_masking"] == {}
    for candidate in (payload, {"stem_masking": masking}):
        text = deterministic_critique(candidate)
        assert "Stem visibility withheld" in text
        assert "lowest relative" not in text
        assert "getting buried" not in text


def test_review_without_optional_stems_does_not_invent_an_abstention():
    payload = critique_metrics_payload({"metrics": {"integrated_lufs": -14.0}})
    assert payload["stem_masking"] is None
    assert "Stem visibility withheld" not in deterministic_critique(payload)

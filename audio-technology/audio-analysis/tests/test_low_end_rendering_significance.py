"""Saved reports cannot turn unqualified stem ratios into masking advice."""

from audio_analysis.integration.report_rendering import _stem_solo_html


def _stem(name, share=0.0):
    return {"name": name, "low_end_share": share, "activity": {
        "schema": "kenn.low_end_stem.activity.v1", "active_floor_dbfs": -60.0,
        "source_rms_dbfs": -18.0, "window_rms_dbfs": -19.0,
        "sample_rate": 44100.0, "analysis_sample_count": 8192,
        "frame_size_samples": 4096, "window_start_sample": 2048,
    }}


def test_legacy_ranking_and_overlap_repairs_are_withheld():
    html = _stem_solo_html({"low_end_summary": {
        "ranked": [{"name": "Invented", "low_end_share": .99}],
        "overlap_warning": "EQ carving or sidechain ducking",
    }}, {"carving_suggestions": ["Unsupported carve"], "clarity_prediction": "Better clarity"})
    assert "Invented" not in html
    assert "EQ carving" not in html
    assert "Unsupported carve" not in html
    assert "Better clarity" not in html
    assert "withheld" in html


def test_valid_zero_and_all_qualified_rows_survive_an_unrelated_quiet_stem():
    quiet = _stem("Quiet", .9)
    quiet["activity"]["window_rms_dbfs"] = -60.0
    html = _stem_solo_html({"low_end_summary": {"ranked": [
        _stem("Air"), quiet, _stem("Bass", .7), _stem("Kick", .8),
    ]}}, None)
    assert "Air: 0.0" in html
    assert "Bass: 0.7" in html
    assert "Kick: 0.8" in html
    assert "Quiet" not in html
    assert "do not compare mix levels" in html
    assert "withheld" in html


def test_duplicate_identities_are_withheld_and_names_are_escaped():
    html = _stem_solo_html({"low_end_summary": {"ranked": [
        _stem("Duplicate"), _stem("Duplicate"), _stem("<Bass>"),
    ]}}, None)
    assert "Duplicate" not in html
    assert "&lt;Bass&gt;: 0.0" in html
    assert "<Bass>" not in html


def test_active_windows_still_cannot_validate_cached_repair_advice():
    html = _stem_solo_html({"low_end_summary": {
        "ranked": [_stem("Bass", .7)], "overlap_warning": "Sidechain Kick",
    }}, {"carving_suggestions": ["Carve Bass"]})
    assert "Bass: 0.7" in html
    assert "Sidechain Kick" not in html
    assert "Carve Bass" not in html

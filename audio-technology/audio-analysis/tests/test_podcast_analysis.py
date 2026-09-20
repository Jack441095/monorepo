"""Tests for the podcast/spoken-word analysis report (advice-only)."""

from __future__ import annotations

from audio_analysis.podcast import PODCAST_TARGETS, analyze_podcast


def _clean_voice_metrics() -> dict:
    return {
        "integrated_lufs": -16.0,
        "true_peak_dbfs": -1.5,
        "peak_dbfs": -3.0,
        "loudness_range_lu": 6.0,
        "stereo_correlation": 0.95,
        "bands": {"sub": 0.02, "bass": 0.10, "low_mids": 0.22, "mids": 0.40,
                  "presence": 0.18, "sibilance": 0.05, "air": 0.03},
    }


def _by_id(report: dict, cid: str) -> dict | None:
    return next((c for c in report["checks"] if c["id"] == cid), None)


def test_clean_voice_scores_high_and_is_publishable():
    rep = analyze_podcast(_clean_voice_metrics())
    assert rep["score"] >= 90
    assert rep["calibrated"] is False
    assert all(c["status"] == "ok" for c in rep["checks"])
    assert "ready to publish" in rep["summary"]


def test_off_target_loudness_flagged_with_direction():
    m = _clean_voice_metrics()
    m["integrated_lufs"] = -23.0  # 7 LU too quiet for Apple −16
    rep = analyze_podcast(m, target="apple")
    loud = _by_id(rep, "loudness")
    assert loud["status"] == "fail"
    assert "quiet" in loud["fix"]
    assert "-16" in loud["target"]


def test_target_switch_changes_loudness_goal():
    m = _clean_voice_metrics()
    m["integrated_lufs"] = -19.0
    # −19 is on target for mono, off target for Apple −16.
    assert _by_id(analyze_podcast(m, target="mono"), "loudness")["status"] == "ok"
    assert _by_id(analyze_podcast(m, target="apple"), "loudness")["status"] != "ok"


def test_true_peak_over_ceiling_fails():
    m = _clean_voice_metrics()
    m["true_peak_dbfs"] = 0.3
    assert _by_id(analyze_podcast(m), "true_peak")["status"] == "fail"


def test_clipping_flagged():
    m = _clean_voice_metrics()
    m["peak_dbfs"] = 0.0
    assert _by_id(analyze_podcast(m), "clipping")["status"] == "fail"


def test_rumble_and_sibilance_and_mud_flagged():
    m = _clean_voice_metrics()
    m["bands"]["sub"] = 0.12         # rumble
    m["bands"]["sibilance"] = 0.14   # essy
    m["bands"]["low_mids"] = 0.40    # boxy
    rep = analyze_podcast(m)
    assert _by_id(rep, "rumble")["status"] == "warn"
    assert _by_id(rep, "sibilance")["status"] == "warn"
    assert _by_id(rep, "mud")["status"] == "warn"
    assert "80 Hz" in _by_id(rep, "rumble")["fix"]
    assert "de-esser" in _by_id(rep, "sibilance")["fix"]


def test_wide_loudness_range_suggests_leveling():
    m = _clean_voice_metrics()
    m["loudness_range_lu"] = 17.0
    c = _by_id(analyze_podcast(m), "consistency")
    assert c["status"] == "fail"
    assert "leveling" in c["fix"] or "compression" in c["fix"]


def test_low_correlation_flags_mono_risk():
    m = _clean_voice_metrics()
    m["stereo_correlation"] = 0.1
    assert _by_id(analyze_podcast(m), "mono")["status"] == "warn"


def test_missing_metrics_degrade_gracefully():
    rep = analyze_podcast({})
    assert rep["checks"] == []
    assert rep["score"] == 100  # nothing measured, nothing wrong to report


def test_all_targets_have_required_fields():
    for spec in PODCAST_TARGETS.values():
        assert {"lufs", "lufs_tol", "true_peak_max", "label"} <= set(spec)

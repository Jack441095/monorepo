"""Tests for the delivery-spec conformance checker (advice-only)."""

from __future__ import annotations

from audio_analysis.mixdown.delivery_conform import DELIVERY_TARGETS, check_delivery_conformance


def _clean_master_metrics() -> dict:
    return {
        "integrated_lufs": -14.0,
        "true_peak_dbfs": -1.2,
        "peak_dbfs": -3.0,
        "loudness_range_lu": 7.0,
        "stereo_correlation": 0.7,
    }


def _by_id(report: dict, cid: str) -> dict | None:
    return next((c for c in report["checks"] if c["id"] == cid), None)


def test_clean_master_scores_high_and_is_deliverable():
    rep = check_delivery_conformance(_clean_master_metrics(), target="spotify")
    assert rep["score"] >= 90
    assert all(c["status"] == "ok" for c in rep["checks"])
    assert "ready to deliver" in rep["summary"]


def test_off_target_loudness_flagged_with_direction():
    m = _clean_master_metrics()
    m["integrated_lufs"] = -20.0  # 4 LU too quiet for Spotify -14
    rep = check_delivery_conformance(m, target="spotify")
    loud = _by_id(rep, "loudness")
    assert loud["status"] == "fail"
    assert "quiet" in loud["fix"]
    assert "-14" in loud["target"]


def test_target_switch_changes_loudness_goal():
    m = _clean_master_metrics()
    m["integrated_lufs"] = -16.0
    # -16 is on target for Apple Music, off target for Spotify -14.
    assert _by_id(check_delivery_conformance(m, target="apple_music"), "loudness")["status"] == "ok"
    assert _by_id(check_delivery_conformance(m, target="spotify"), "loudness")["status"] != "ok"


def test_club_and_cd_targets_skip_the_loudness_check_entirely():
    """Club/DJ and CD/physical have no loudness-normalization spec -- no
    LUFS number is asserted, the check is simply absent rather than judged
    against a fabricated target."""
    m = _clean_master_metrics()
    m["integrated_lufs"] = -6.0  # would fail hard against any streaming target
    for target in ("club", "cd"):
        rep = check_delivery_conformance(m, target=target)
        assert _by_id(rep, "loudness") is None
        assert _by_id(rep, "true_peak") is not None  # true-peak safety still checked


def test_true_peak_over_ceiling_fails():
    m = _clean_master_metrics()
    m["true_peak_dbfs"] = 0.3
    assert _by_id(check_delivery_conformance(m), "true_peak")["status"] == "fail"


def test_clipping_flagged():
    m = _clean_master_metrics()
    m["peak_dbfs"] = 0.0
    assert _by_id(check_delivery_conformance(m), "clipping")["status"] == "fail"


def test_low_correlation_flags_mono_compatibility_warning():
    m = _clean_master_metrics()
    m["stereo_correlation"] = 0.1
    assert _by_id(check_delivery_conformance(m), "mono")["status"] == "warn"


def test_loudness_range_is_reported_but_never_scored():
    """Unlike podcast/podcast_analysis.py's spoken-word LRA check, music has
    no universal 'should be narrow' target -- LRA must never appear as a
    scored check, only as an informational field."""
    m = _clean_master_metrics()
    m["loudness_range_lu"] = 18.0  # would be a hard "fail" under the podcast LRA rule
    rep = check_delivery_conformance(m)
    assert _by_id(rep, "consistency") is None
    assert _by_id(rep, "lra") is None
    assert rep["loudness_range_lu"] == 18.0
    assert all(c["status"] == "ok" for c in rep["checks"])


def test_unknown_target_falls_back_to_spotify():
    m = _clean_master_metrics()
    rep_unknown = check_delivery_conformance(m, target="not-a-real-platform")
    rep_spotify = check_delivery_conformance(m, target="spotify")
    assert rep_unknown["target_label"] == rep_spotify["target_label"]


def test_empty_metrics_produces_no_checks_and_a_neutral_score():
    rep = check_delivery_conformance({})
    assert rep["checks"] == []
    assert rep["score"] == 100


def test_all_targets_have_a_true_peak_ceiling():
    for key, spec in DELIVERY_TARGETS.items():
        assert spec["true_peak_max"] is not None, f"{key} must always have a true-peak safety ceiling"

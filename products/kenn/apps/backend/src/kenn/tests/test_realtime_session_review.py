from __future__ import annotations

from typing import Any

import pytest

from kenn.core.realtime_session_review import SCHEMA, build_realtime_session_review


_MISSING_RMS = object()


def test_missing_mute_and_solo_are_unavailable_rather_than_false() -> None:
    # Absence of a mixer reply previously became an observed unmuted, unsoloed track.
    report = build_realtime_session_review({"status": "connected", "tracks": [{"index": 3, "name": "Kick"}]})
    track = report["live_session"]["track_observations"][0]
    assert "muted" not in track and "soloed" not in track
    assert "mixer_state" in report["project_health"]["unavailable_data"]
    assert "device_names" in report["project_health"]["unavailable_data"]


def test_dispatched_or_expired_snapshot_is_not_current() -> None:
    for state in (
        {"status": "dispatched", "tracks": []},
        {"status": "connected", "tracks": [], "freshness": {"current_for_diagnosis": False}},
    ):
        report = build_realtime_session_review(state)
        assert report["ok"] is False
        assert report["status"] == "unavailable"


def test_retained_stale_plugin_frame_is_not_labelled_current() -> None:
    report = build_realtime_session_review(
        {"status": "connected", "tracks": []},
        plugin_review={"ok": True, "live_context": {"peak_dbfs": -0.1, "freshness": {"current_for_diagnosis": False}}},
        plugin_recommendations=[{"title": "stale bus warning"}],
    )
    assert report["plugin_bus"]["status"] == "unavailable"
    assert report["plugin_bus"]["recommendations"] == []


def test_quiet_plugin_frame_withholds_signal_evidence_but_keeps_window_and_live_review() -> None:
    # A large peak or extreme correlation can survive near-silence and look like a fault without an activity gate.
    report = build_realtime_session_review(
        {"status": "connected", "tracks": [{"index": 2, "name": "Bass", "volume": 0.92}]},
        plugin_review={"ok": True, "live_context": {
            "rms_dbfs": -80.1, "peak_dbfs": 0.0, "stereo_correlation": -1.0,
            "stereo_width": 0.9, "clipped_samples": 20, "low_energy": 1.0,
            "pink_noise_reference": {"status": "complete", "largest_deviation": {"center_hz": 80.0, "deviation_db": 12.0}},
            "freshness": {"frame_count": 4, "age_seconds": 1.0, "current_for_diagnosis": True},
            "live_window": {"status": "stable", "sample_count": 4, "window_seconds": 24.0,
                            "pink_noise_shape": {"sample_count": 4, "largest_median_deviation": {"center_hz": 80.0, "median_deviation_db": 12.0}}},
        }},
        plugin_recommendations=[{"title": "quiet signal warning"}],
    )

    bus = report["plugin_bus"]
    assert report["live_session"]["track_observations"][0]["volume"] == 0.92
    assert bus["status"] == "current" and bus["scope"] == "plugin_bus"
    assert bus["metrics"] == {}
    assert bus["pink_noise_reference"] is None
    assert bus["live_window"] == {"status": "stable", "sample_count": 4, "window_seconds": 24.0}
    assert bus["recommendations"] == []
    assert "at/below -80 dBFS" in bus["limitations"][0]
    assert bus["advisory_only"] is True and bus["capture_requested"] is False


@pytest.mark.parametrize("rms", [
    pytest.param(_MISSING_RMS, id="missing"),
    pytest.param(None, id="null"),
    pytest.param(True, id="boolean"),
    pytest.param(float("nan"), id="nan"),
    pytest.param(float("inf"), id="positive-infinity"),
    pytest.param(float("-inf"), id="negative-infinity"),
    pytest.param(-80.0, id="at-floor"),
    pytest.param(10**1000, id="overflowing-integer"),
])
def test_plugin_activity_floor_rejects_missing_invalid_and_quiet_rms(rms: Any) -> None:
    context = {
        "peak_dbfs": 0.0,
        "stereo_correlation": -1.0,
        "pink_noise_reference": {"status": "complete", "largest_deviation": {"center_hz": 80.0, "deviation_db": 12.0}},
    }
    if rms is not _MISSING_RMS:
        context["rms_dbfs"] = rms
    report = build_realtime_session_review(
        {"status": "connected", "tracks": []},
        plugin_review={"ok": True, "live_context": context},
        plugin_recommendations=[{"title": "quiet signal warning"}],
    )

    bus = report["plugin_bus"]
    assert bus["metrics"] == {}
    assert bus["pink_noise_reference"] is None
    assert bus["recommendations"] == []


def test_active_plugin_frame_publishes_signal_evidence_and_recommendations() -> None:
    report = build_realtime_session_review(
        {"status": "connected", "tracks": []},
        plugin_review={"ok": True, "live_context": {
            "rms_dbfs": -79.9, "peak_dbfs": -0.2, "stereo_correlation": -0.1,
            "pink_noise_reference": {"status": "complete", "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0}},
        }},
        plugin_recommendations=[{"title": "active signal warning"}],
    )

    bus = report["plugin_bus"]
    assert bus["metrics"] == {"rms_dbfs": -79.9, "peak_dbfs": -0.2, "stereo_correlation": -0.1}
    assert bus["pink_noise_reference"]["largest_deviation"]["center_hz"] == 315.0
    assert bus["recommendations"][0]["title"] == "active signal warning"
    assert "limitations" not in bus


def test_malformed_optional_fields_do_not_crash_or_create_observations() -> None:
    report = build_realtime_session_review({"status": "connected", "tracks": [
        None, {"index": "invalid", "name": "wrong"},
        {"index": 3, "name": "Vocal", "devices": "unknown", "muted": "false", "output_meter_level": float("nan")},
    ]})
    assert report["live_session"]["track_observations"] == [{"track_index": 3, "track_name": "Vocal"}]
    assert report["project_health"]["recommendations"] == []


def test_realtime_session_review_keeps_live_and_plugin_scopes_separate() -> None:
    result = build_realtime_session_review(
        {
            "status": "connected",
            "tracks": [
                {"index": 3, "name": "Kick", "muted": False, "output_meter_level": 0.99},
                {"index": 4, "name": "Bass", "muted": False, "output_meter_level": 0.72},
            ],
        },
        mixing_alerts=[{
            "id": "meter-headroom-3", "type": "headroom", "severity": "warning",
            "track_index": 3, "track_name": "Kick", "message": "near ceiling",
            "fix_action": "inspect", "secret_internal_field": "must not escape",
        }],
        plugin_review={
            "ok": True,
            "live_context": {
                "peak_dbfs": -0.2,
                "rms_dbfs": -18.0,
                "freshness": {"frame_count": 4, "age_seconds": 1.2, "private": "drop"},
                "pink_noise_reference": {
                    "status": "complete", "anchor_frequency_hz": 1000.0,
                    "bands": [{"center_hz": 315.0, "deviation_db": 5.0, "raw_audio": "drop"}],
                    "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
                },
                "live_window": {
                    "status": "stable", "sample_count": 4, "window_seconds": 24.0,
                    "pink_noise_shape": {"sample_count": 4, "largest_median_deviation": {"center_hz": 315.0, "median_deviation_db": 4.8}},
                },
            },
        },
        plugin_recommendations=[{
            "title": "Realtime bus: limited peak headroom",
            "category": "realtime_mix",
            "severity": "warning",
            "description": "listen",
            "private": "drop",
        }],
    )

    assert result["schema"] == SCHEMA
    assert result["status"] == "current"
    assert result["live_session"]["metered_track_count"] == 2
    assert result["live_session"]["track_observations"][0]["track_index"] == 3
    assert result["mixing_doctor"]["alerts"][0]["track_index"] == 3
    assert "secret_internal_field" not in result["mixing_doctor"]["alerts"][0]
    assert result["plugin_bus"]["scope"] == "plugin_bus"
    assert result["plugin_bus"]["metrics"] == {"peak_dbfs": -0.2, "rms_dbfs": -18.0}
    assert "private" not in result["plugin_bus"]["freshness"]
    assert "private" not in result["plugin_bus"]["recommendations"][0]
    assert result["plugin_bus"]["live_window"]["status"] == "stable"
    assert result["plugin_bus"]["pink_noise_reference"]["largest_deviation"] == {"center_hz": 315.0, "deviation_db": 5.0}
    assert result["plugin_bus"]["live_window"]["pink_noise_shape"]["largest_median_deviation"]["median_deviation_db"] == 4.8
    assert "raw_audio" not in result["plugin_bus"]["pink_noise_reference"]["bands"][0]
    assert result["advisory_only"] is True
    assert result["mutation_authorized"] is False
    assert result["capture_requested"] is False


def test_realtime_session_review_fails_closed_without_current_live_state() -> None:
    result = build_realtime_session_review(
        {"status": "offline", "tracks": [{"index": 0, "name": "Kick"}]},
        mixing_alerts=[{"id": "stale", "message": "do not expose"}],
    )

    assert result["ok"] is False
    assert result["status"] == "unavailable"
    assert result["live_session"]["track_observations"] == [{
        "track_index": 0, "track_name": "Kick",
    }]
    assert result["mixing_doctor"]["alerts"] == []
    assert "no Live analysis was inferred" in result["error"]

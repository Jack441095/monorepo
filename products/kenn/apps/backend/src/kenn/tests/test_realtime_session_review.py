from __future__ import annotations

from kenn.core.realtime_session_review import SCHEMA, build_realtime_session_review


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
    assert result["plugin_bus"]["metrics"] == {"peak_dbfs": -0.2}
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
        "track_index": 0, "track_name": "Kick", "muted": False, "soloed": False,
    }]
    assert result["mixing_doctor"]["alerts"] == []
    assert "no Live analysis was inferred" in result["error"]

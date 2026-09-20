from kenn.core.realtime_mix_comparison import build_realtime_mix_comparison


def test_comparison_keeps_measurement_windows_explicit() -> None:
    result = build_realtime_mix_comparison(
        {
            "status": "completed",
            "metrics": {"peak_dbfs": -1.0, "rms_dbfs": -18.0, "crest_factor_db": 17.0},
            "reference_comparison": {
                "pink_noise_reference": {
                    "largest_deviation": {"center_hz": 296.0, "deviation_db": 5.1},
                },
            },
        },
        {
            "peak_dbfs": -0.1,
            "rms_dbfs": -16.0,
            "crest_db": 16.2,
            "pink_noise_reference": {
                "largest_deviation": {"center_hz": 315.0, "deviation_db": 5.0},
            },
            "freshness": {"current_for_diagnosis": True, "age_seconds": 1.0},
        },
        review_id="reference-review",
        plugin_session_id="mix-session",
    )

    assert result["schema"] == "kenn.realtime_mix_comparison.v1"
    assert result["comparison_available"] is True
    assert result["comparisons"][0]["metric"] == "peak_dbfs"
    assert result["comparisons"][0]["delta_live_minus_uploaded"] == 0.9
    assert result["comparisons"][0]["comparison_status"] == "directional_same_metric_different_window"
    assert result["pink_noise_shape"]["deviation_delta_db"] == -0.1
    assert result["advisory_only"] is True
    assert result["capture_requested"] is False
    assert result["live_target_inference_allowed"] is False


def test_comparison_withholds_stale_live_context() -> None:
    result = build_realtime_mix_comparison(
        {"status": "completed", "metrics": {"peak_dbfs": -1.0}},
        {"peak_dbfs": -0.1, "freshness": {"current_for_diagnosis": False, "age_seconds": 16.0}},
        review_id="review-1",
        plugin_session_id="mix-session",
    )

    assert result["comparisons"] == []
    assert result["pink_noise_shape"] is None
    assert result["comparison_available"] is False
    assert any("stale_or_unknown" in item for item in result["limitations"])

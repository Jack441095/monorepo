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


def _review_and_live(window: dict) -> dict:
    return build_realtime_mix_comparison(
        {"status": "completed", "metrics": {"peak_dbfs": -1.0, "rms_dbfs": -18.0}},
        {
            "peak_dbfs": -0.1, "rms_dbfs": -16.0, "audio_age_seconds": 0.12,
            "measurement_window": window,
            "freshness": {"current_for_diagnosis": True, "age_seconds": 0.2},
        },
        review_id="r", plugin_session_id="s",
    )


def test_comparison_says_which_live_window_it_used() -> None:
    # 14 Oct 2026: mix review compared peak, RMS and crest without saying where in the stream the live side came from.
    result = _review_and_live({"end_sample": 9_600, "source_generation": 3, "dropped_samples": 0, "invalid_samples": 0})

    assert result["live_window"] == {
        "end_sample": 9_600.0, "source_generation": 3.0, "dropped_samples": 0.0,
        "invalid_samples": 0.0, "audio_age_seconds": 0.12,
    }
    assert not any("dropped or invalid" in item for item in result["limitations"])


def test_comparison_warns_when_the_live_window_dropped_audio() -> None:
    result = _review_and_live({"end_sample": 9_600, "source_generation": 3, "dropped_samples": 256, "invalid_samples": 0})

    assert any("dropped or invalid" in item for item in result["limitations"])


def test_comparison_without_a_window_still_compares() -> None:
    # Older plug-in builds publish no measurement window; the levels are still comparable.
    result = build_realtime_mix_comparison(
        {"status": "completed", "metrics": {"peak_dbfs": -1.0}},
        {"peak_dbfs": -0.1, "freshness": {"current_for_diagnosis": True, "age_seconds": 0.2}},
        review_id="r", plugin_session_id="s",
    )

    assert result["live_window"] is None
    assert result["comparison_available"] is True

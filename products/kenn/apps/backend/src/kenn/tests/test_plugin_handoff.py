from __future__ import annotations

import time

import kenn.plugin_handoff as plugin_handoff
from kenn.plugin_handoff import ingest_live_context, live_context_summary, pink_noise_reference_from_spectrum, review_from_handoff, validate_handoff


def _payload(**overrides):
    payload = {
        "schema": "kenn.plugin_handoff.v1",
        "audio_feature_schema": "audio_feature_frame.v1",
        "kind": "mix_review_snapshot",
        "assistant_mode": "suggest",
        "peak_dbfs": -4.0,
        "rms_dbfs": -16.0,
        "stereo_correlation": 0.7,
        "stereo_width": 0.2,
        "sample_rate": 48000.0,
        "analysed_samples": 48000,
        "low_energy": 0.03,
        "mid_energy": 0.01,
        "high_energy": 0.002,
        "plugin_state": {"assistant_mode": "suggest", "analysis_enabled": True},
    }
    payload.update(overrides)
    return payload


def _spectrum():
    return [
        {"center_hz": 315.0, "low_hz": 280.6, "high_hz": 353.6, "energy": 0.1},
        {"center_hz": 1000.0, "low_hz": 891.0, "high_hz": 1122.5, "energy": 0.01},
        {"center_hz": 2000.0, "low_hz": 1782.0, "high_hz": 2245.0, "energy": 0.0025},
    ]


def _evidence():
    return {
        "schema": "kenn.evidence.v1",
        "source": "plugin_bus_snapshot",
        "captured_at_age_seconds": 0.0,
        "observed_at_epoch": None,
        "facts": [{"name": "peak_dbfs", "value": -4.0, "unit": "dBFS", "source": "plugin_bus_snapshot", "confidence": "measured"}],
        "limitations": ["Bus snapshot only."],
    }


def test_handoff_accepts_realtime_band_metrics() -> None:
    checked = validate_handoff(_payload())
    assert checked["ok"] is True
    assert checked["metrics"]["low_energy"] == 0.03

    review = review_from_handoff(_payload())
    assert review["ok"] is True
    assert any(item["title"] == "Realtime tonal snapshot available" for item in review["observations"])


def test_handoff_rejects_raw_audio_and_nonfinite_metrics() -> None:
    assert validate_handoff(_payload(raw_audio=[0.0]))["ok"] is False
    assert validate_handoff(_payload(low_energy=float("nan")))["ok"] is False


def test_handoff_validates_optional_shared_evidence_packet() -> None:
    assert validate_handoff(_payload(evidence=_evidence()))["ok"] is True
    assert validate_handoff(_payload(evidence={**_evidence(), "source": "mix_review_upload"}))["ok"] is False
    bad = _evidence()
    bad["facts"] = [{**bad["facts"][0], "value": float("nan")}]
    assert validate_handoff(_payload(evidence=bad))["ok"] is False


def test_realtime_spectrum_is_validated_and_compared_to_pink_baseline() -> None:
    checked = validate_handoff(_payload(spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()))
    assert checked["ok"] is True
    reference = checked["pink_noise_reference"]
    assert reference["status"] == "complete"
    assert reference["anchor_frequency_hz"] == 1000.0
    largest = reference["largest_deviation"]
    assert largest["center_hz"] == 315.0
    assert largest["deviation_db"] > 0

    review = review_from_handoff(_payload(spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()))
    assert any(item["title"] == "Realtime spectral reference available" for item in review["observations"])
    assert "uncalibrated pink-noise-style shape reference" in review["limitations"]


def test_realtime_spectrum_rejects_bad_bounds_and_order() -> None:
    assert validate_handoff(_payload(spectrum_bands=[{"center_hz": 300.0, "low_hz": 320.0, "high_hz": 400.0, "energy": 0.1}]))["ok"] is False
    assert validate_handoff(_payload(spectrum_bands=[_spectrum()[1], _spectrum()[0]]))["ok"] is False
    assert validate_handoff(_payload(spectrum_bands=[{"center_hz": 300.0, "low_hz": 250.0, "high_hz": 350.0, "energy": 17.0}]))["ok"] is False


def test_pink_reference_abstains_when_anchor_is_silent() -> None:
    assert pink_noise_reference_from_spectrum([{"center_hz": 1000.0, "energy": 0.0}])["status"] == "abstained"


def test_live_context_keeps_bounded_window_and_freshness_receipt() -> None:
    session_id = "window-test"
    for peak in (-5.0, -4.8, -5.1) * 5:
        result = ingest_live_context(
            _payload(session_id=session_id, peak_dbfs=peak, spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()),
            session_id=session_id,
        )
    context = live_context_summary(session_id)
    assert context is not None
    assert context["live_window"]["sample_count"] == 12
    assert context["live_window"]["status"] == "stable"
    assert context["freshness"]["frame_count"] == 12
    assert context["freshness"]["ttl_seconds"] == 1800
    assert context["freshness"]["status"] == "current"
    assert context["freshness"]["current_for_diagnosis"] is True
    assert context["freshness"]["max_current_age_seconds"] == 15.0
    assert result["live_context"]["live_window"]["sample_count"] == 12


def test_live_context_marks_retained_but_old_context_stale_for_diagnosis(monkeypatch) -> None:
    session_id = "stale-diagnosis-test"
    ingest_live_context(_payload(session_id=session_id), session_id=session_id)
    received_at = plugin_handoff._live_contexts[session_id]["received_at"]
    monkeypatch.setattr(plugin_handoff.time, "time", lambda: received_at + 15.01)

    context = live_context_summary(session_id)
    assert context is not None
    assert context["freshness"]["status"] == "stale_or_unknown"
    assert context["freshness"]["current_for_diagnosis"] is False
    assert context["freshness"]["age_seconds"] == 15.01
    assert context["freshness"]["ttl_seconds"] == 1800


def test_ingested_context_exposes_band_metrics_without_audio() -> None:
    result = ingest_live_context(_payload(session_id="handoff-test", spectrum_schema="realtime_spectrum.v1", spectrum_bands=_spectrum()), session_id="handoff-test")
    assert result["ok"] is True
    context = result["live_context"]
    assert context["scope"] == "plugin_bus"
    assert context["low_energy"] == 0.03
    assert context["spectrum_bands"][1]["center_hz"] == 1000.0
    assert context["pink_noise_reference"]["status"] == "complete"
    assert context["evidence"]["schema"] == "kenn.evidence.v1"
    assert context["evidence"]["source"] == "plugin_bus_snapshot"
    assert any(fact["name"] == "peak_dbfs" for fact in context["evidence"]["facts"])
    assert "raw_audio" not in context

"""Command-path coverage for evidence-labelled Live session mix advice."""

from __future__ import annotations

import hashlib
from copy import deepcopy

import pytest

from kenn.core import live_session_advice
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


class AdviceLive:
    backend_name = "advice-test"

    def __init__(self, capture: bytes | None = None, vocal_capture: bytes | None = None) -> None:
        self.capture = capture
        self.vocal_capture = vocal_capture
        self.reads = 0
        self.state = {
            "status": "connected",
            "tracks": [
                {
                    "index": 0,
                    "name": "Kick",
                    "devices": [],
                    "arrangement_clips": [{"start_time_beats": 0, "length_beats": 32}],
                },
                {
                    "index": 1,
                    "name": "Bass",
                    "devices": [],
                    "arrangement_clips": [{"start_time_beats": 16, "length_beats": 48}],
                },
            ],
        }

    def query_session_state(self, **_kwargs):
        self.reads += 1
        return deepcopy(self.state)

    def get_latest_audio_capture(self):
        return self.capture

    def get_latest_vocal_capture(self):
        return self.vocal_capture


@pytest.mark.parametrize(
    "question",
    [
        "How does my mix sound?",
        "Check my low end",
        "How does my low end sound?",
        "Check the vocals for clipping.",
        "Any masking issues?",
        "Analyze my session",
    ],
)
def test_mix_advice_falls_back_to_arrangement_without_claiming_audio_analysis(question: str) -> None:
    live = AdviceLive()

    result = handle_command(question, session_id="advice", service=LiveActionService(live))

    assert result["status"] == "inspected"
    assert result["answer_mode"] == "session_question"
    assert result["advice_mode"] == "arrangement_fallback"
    assert result["advisory_only"] is True
    assert result["changed"] is False
    unavailable = (
        "isolated vocal capture was not available"
        if "vocal" in question.casefold()
        else "Audio was not available"
    )
    assert unavailable in result["answer"]
    assert result["findings"][0]["confidence"] == 0.35
    assert live.reads == 1


def test_vocal_clipping_request_refuses_to_attribute_full_mix_capture() -> None:
    live = AdviceLive(capture=b"RIFF-full-mix")

    result = handle_command("Check the vocals for clipping.", session_id="advice", service=LiveActionService(live))

    assert result["advice_mode"] == "arrangement_fallback"
    assert result["analysis_scope"] == "vocal"
    assert "isolated vocal capture was not available" in result["answer"]


def test_mix_advice_formats_measured_findings_when_capture_is_available(monkeypatch: pytest.MonkeyPatch) -> None:
    live = AdviceLive(capture=b"RIFF-test")

    def fake_analyze(payload: bytes, **kwargs):
        assert payload == b"RIFF-test"
        assert kwargs["include_ltas"] is True
        return {
            "ok": True,
            "analysis_status": "complete",
            "metrics": {"sample_peak_dbfs": -1.2, "rms_dbfs": -14.0},
            "findings": [{
                "type": "possible_masking_candidate",
                "severity": "informational",
                "confidence": 0.72,
                "explanation": "Two measured peaks overlap.",
                "suggested_listening_test": "Solo the kick and bass, then compare in mono.",
            }],
        }

    monkeypatch.setattr(live_session_advice, "analyze_wav", fake_analyze)

    result = handle_command("How does my mix sound?", session_id="advice", service=LiveActionService(live))

    assert result["advice_mode"] == "audio_analysis"
    assert result["findings"][0]["confidence"] == 0.72
    assert "72% confidence" in result["answer"]
    assert "Solo the kick and bass" in result["answer"]
    assert result["changed"] is False
    assert result["analysis_source"] == {
        "filename": "live-session-capture.wav",
        "sha256": hashlib.sha256(b"RIFF-test").hexdigest(),
        "cache_hit": False,
    }


def test_identical_capture_reuses_bounded_content_addressed_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = b"RIFF-cache-regression"
    live = AdviceLive(capture=payload)
    calls = 0

    def fake_analyze(_payload: bytes, **_kwargs):
        nonlocal calls
        calls += 1
        return {
            "ok": True,
            "analysis_status": "complete",
            "metrics": {"sample_peak_dbfs": -1.0},
            "findings": [],
        }

    monkeypatch.setattr(live_session_advice, "analyze_wav", fake_analyze)

    first = handle_command("How does my mix sound?", session_id="cache-1", service=LiveActionService(live))
    second = handle_command("How does my mix sound?", session_id="cache-2", service=LiveActionService(live))

    assert calls == 1
    assert first["analysis_source"]["cache_hit"] is False
    assert second["analysis_source"]["cache_hit"] is True
    assert second["analysis_source"]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_low_end_advice_surfaces_bounded_reference_measurement(monkeypatch: pytest.MonkeyPatch) -> None:
    live = AdviceLive(capture=b"RIFF-mix")

    def fake_analyze(_payload: bytes, **_kwargs):
        return {
            "ok": True,
            "analysis_status": "complete",
            "metrics": {"sample_peak_dbfs": -0.8, "rms_dbfs": -12.0},
            "findings": [],
            "spectral": {
                "band_energy_dbfs": {"low": -9.5},
                "pink_noise_reference": {
                    "status": "complete",
                    "bands": [
                        {"center_hz": 62.5, "deviation_db": 5.2},
                        {"center_hz": 125.0, "deviation_db": 3.1},
                        {"center_hz": 1000.0, "deviation_db": 0.0},
                    ],
                },
            },
        }

    monkeypatch.setattr(live_session_advice, "analyze_wav", fake_analyze)

    result = handle_command("How does my low end sound?", session_id="advice", service=LiveActionService(live))

    assert result["analysis_scope"] == "low_end"
    assert result["findings"][0]["type"] == "possible_low_end_excess"
    assert result["findings"][0]["evidence"]["low_band_rms_dbfs"] == -9.5
    assert "62.5 Hz band is 5.2 dB above" in result["answer"]


def test_vocal_capture_is_used_for_vocal_clipping_request(monkeypatch: pytest.MonkeyPatch) -> None:
    live = AdviceLive(capture=b"RIFF-full-mix", vocal_capture=b"RIFF-vocal")

    def fake_analyze(payload: bytes, **_kwargs):
        assert payload == b"RIFF-vocal"
        return {
            "ok": True,
            "analysis_status": "complete",
            "metrics": {"sample_peak_dbfs": -0.1, "rms_dbfs": -13.0},
            "findings": [
                {
                    "type": "possible_resonance",
                    "severity": "informational",
                    "confidence": 0.5,
                    "explanation": "A narrow peak was measured.",
                    "suggested_listening_test": "Sweep it in context.",
                },
                {
                    "type": "clipping",
                    "severity": "high",
                    "confidence": 0.95,
                    "explanation": "Near-full-scale sample runs were measured.",
                    "suggested_listening_test": "Inspect the loudest phrase with a true-peak meter.",
                },
            ],
        }

    monkeypatch.setattr(live_session_advice, "analyze_wav", fake_analyze)

    result = handle_command("Check the vocals for clipping.", session_id="advice", service=LiveActionService(live))

    assert result["analysis_scope"] == "vocal"
    assert result["findings"][0]["type"] == "clipping"
    assert "isolated vocal capture" in result["answer"]

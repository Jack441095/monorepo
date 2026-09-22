"""Command-path coverage for evidence-labelled Live session mix advice."""

from __future__ import annotations

from copy import deepcopy

import pytest

from kenn.core import live_session_advice
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


class AdviceLive:
    backend_name = "advice-test"

    def __init__(self, capture: bytes | None = None) -> None:
        self.capture = capture
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
    assert "Audio was not available" in result["answer"]
    assert result["findings"][0]["confidence"] == 0.35
    assert live.reads == 1


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

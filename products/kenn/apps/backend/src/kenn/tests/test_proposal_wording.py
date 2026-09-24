"""Volume and pan proposals read in the units Live shows, not raw 0..1 values."""

from __future__ import annotations

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.fixture
def answer(monkeypatch):
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    service = LiveActionService(FakeLiveBackend())
    return lambda command: handle_command(command, session_id="wording", service=service)["answer"]


def test_volume_proposal_reads_in_db_with_the_fader_value(answer) -> None:
    assert "from -14.0 dB (fader 0.5) to -6.0 dB (fader 0.7)" in answer("set the bass volume to -6 dB")


def test_pan_proposal_reads_as_left_right_percent(answer) -> None:
    assert "from centre to 20% left" in answer("pan the synth 20% left")

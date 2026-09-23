import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command


@pytest.mark.parametrize(
    "command",
    ["Pan the Synth center.", "Center the Synth.", "Pan Synth to the middle.", "Centre the Synth pan.",
     "Please recentre the Synth."],
)
def test_centre_phrasings_propose_pan_zero(command: str) -> None:
    live = FakeLiveBackend()
    live.set_track_pan(5, -1.0)

    result = handle_command(command, session_id="pan-centre", service=LiveActionService(live))

    assert result["status"] == "confirmation_required"
    assert result["proposal"]["operation"] == "set_pan"
    assert result["proposal"]["track_name"] == "Synth"
    assert result["proposal"]["after"] == 0.0


def test_centre_frequency_is_not_a_pan_request() -> None:
    result = handle_command(
        "Set the EQ centre frequency on track 5 to 200 Hz.",
        session_id="pan-centre",
        service=LiveActionService(FakeLiveBackend()),
    )
    assert (result.get("proposal") or {}).get("operation") != "set_pan"

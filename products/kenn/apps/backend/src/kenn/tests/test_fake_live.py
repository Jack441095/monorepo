import json

import pytest

from kenn.core.fake_live import DEFAULT_FIXTURE, FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_backend_factory import create_live_backend


def test_factory_selects_fake_only_when_explicitly_requested() -> None:
    assert isinstance(create_live_backend(lambda: "osc", environ={"KENN_LIVE_BACKEND": "fake"}), FakeLiveBackend)
    assert create_live_backend(lambda: "osc", environ={}) == "osc"


def test_fake_reports_itself_as_fake_everywhere() -> None:
    live = FakeLiveBackend()
    assert live.query_session_state()["backend"] == "fake"
    assert live.probe_connection()["backend"] == "fake"
    assert live.capability_report()["transport"] == "fake"


def test_fake_replays_the_recorded_demo_fixture() -> None:
    live = FakeLiveBackend()
    names = [track["name"] for track in live.query_session_state()["tracks"]]
    assert names == ["Kick", "Snare / Clap", "Hi-Hats", "Drum Bus", "Bass", "Synth", "Lead Vocal", "FX Print"]
    assert live.get_selected_device() == {"success": True, "track_index": 3, "device_index": 0}
    assert [r["name"] for r in live.get_return_tracks()] == ["A-Reverb", "B-Delay"]


def test_device_writes_read_back_with_updated_display() -> None:
    live = FakeLiveBackend()
    output = next(p for p in live.get_device_parameters(6, 0)["parameters"] if p["name"] == "Output")
    assert live.get_device_parameter_value_string(6, 0, output["index"])["value_string"] == "0.00 dB"
    assert live.set_device_parameter(6, 0, output["index"], 3.0)
    assert live.get_device_parameters(6, 0)["parameters"][output["index"]]["value"] == 3.0
    assert live.get_device_parameter_value_string(6, 0, output["index"])["value_string"] == "3.00 dB"


def test_insert_and_remove_reindex_the_device_chain() -> None:
    live = FakeLiveBackend()
    inserted = live.insert_device_with_result(5, "EQ Eight", 0)
    assert inserted["success"] and [d["name"] for d in live.query_session_state()["tracks"][5]["devices"]] == ["EQ Eight"]
    assert live.insert_device_with_result(5, "Wavetable", 1)["success"] is False
    assert live.remove_device_with_result(5, 0, "Compressor")["success"] is False
    assert live.remove_device_with_result(5, 0, "EQ Eight")["success"]
    assert live.query_session_state()["tracks"][5]["devices"] == []


def test_rejects_unknown_fixture_schema(tmp_path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"schema": "other"}))
    with pytest.raises(RuntimeError):
        FakeLiveBackend(bad)


def test_live_action_service_round_trip_on_fake_live() -> None:
    live = FakeLiveBackend()
    service = LiveActionService(live)
    proposal = service.propose_track_action("set_pan", track_index=5, value=-1.0, session_id="fake-rt")
    assert proposal.get("ok"), proposal
    applied = service.execute(proposal["proposal"], confirm_token=proposal["proposal"]["confirmation_token"],
                            session_id="fake-rt", idempotency_key="fake-rt-1")
    assert applied.get("ok") and applied["receipt"]["verified"] is True
    assert live.query_session_state()["tracks"][5]["pan"] == -1.0
    assert DEFAULT_FIXTURE.is_file()

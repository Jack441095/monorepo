import json

from kenn.core.fake_live import DEFAULT_FIXTURE, FakeLiveBackend
from kenn.core.live_world_model import WORLD_MODEL_SCHEMA, fingerprint, read_world_model


def _fixture_with_world(tmp_path):
    fixture = json.loads(DEFAULT_FIXTURE.read_text())
    fixture["world"] = {
        "bus_mixer:return:0": {"kind": "return", "index": 0, "name": "A-Reverb", "volume": 0.7, "panning": 0.0,
                               "mute": False, "solo": False, "devices": ["Reverb", "Hybrid Reverb"]},
        "bus_mixer:return:1": {"kind": "return", "index": 1, "name": "B-Delay", "volume": 0.6, "panning": 0.1,
                               "mute": True, "solo": False, "devices": ["Delay"]},
        "bus_mixer:master:-1": {"kind": "master", "index": -1, "name": "Main", "volume": 0.85, "panning": 0.0,
                                "devices": ["Limiter"]},
        "device_tree:track:5": {"kind": "track", "index": 5, "devices": [
            {"name": "Instrument Rack", "class_name": "InstrumentGroupDevice", "can_have_chains": True,
             "chains": [{"name": "Pad", "devices": [{"name": "Wavetable", "class_name": "InstrumentVector",
                                                     "can_have_chains": False}]}]}]},
    }
    path = tmp_path / "world.json"
    path.write_text(json.dumps(fixture))
    return path


def test_world_model_from_recorded_fixture_marks_missing_sections_unavailable() -> None:
    model = read_world_model(FakeLiveBackend())
    assert model["schema"] == WORLD_MODEL_SCHEMA and model["backend"] == "fake"
    assert [t["name"] for t in model["tracks"]][3] == "Drum Bus"
    assert model["tracks"][3]["device_tree"][0]["name"] == "Compressor"
    assert [r["name"] for r in model["returns"]] == ["A-Reverb", "B-Delay"]
    assert model["master"] is None
    assert model["availability"]["master"] is False and model["availability"]["return_mixers"] is False
    assert model["availability"]["track_sends"] is True
    assert "volume" not in model["returns"][0]


def test_world_model_includes_returns_master_and_rack_chains_when_recorded(tmp_path) -> None:
    model = read_world_model(FakeLiveBackend(_fixture_with_world(tmp_path)))
    assert model["availability"]["return_mixers"] is True and model["availability"]["master"] is True
    assert model["returns"][1] | {} and model["returns"][1]["mute"] is True
    assert model["master"]["devices"] == ["Limiter"]
    rack = model["tracks"][5]["device_tree"][0]
    assert rack["can_have_chains"] and rack["chains"][0]["devices"][0]["name"] == "Wavetable"


def test_fingerprint_tracks_mixer_changes_but_ignores_meters() -> None:
    live = FakeLiveBackend()
    first = read_world_model(live)
    live.set_track_volume(0, 0.3)
    changed = read_world_model(live)
    assert first["fingerprint"] != changed["fingerprint"]
    metered = dict(changed)
    metered["tracks"] = [dict(t, output_meter_level=0.9) for t in changed["tracks"]]
    assert fingerprint(metered) == changed["fingerprint"]


def test_world_model_reports_offline_without_inventing_state() -> None:
    class Offline:
        def query_session_understanding(self):
            return {"status": "offline", "error": "no reply"}

    model = read_world_model(Offline())
    assert model["status"] == "offline" and "tracks" not in model

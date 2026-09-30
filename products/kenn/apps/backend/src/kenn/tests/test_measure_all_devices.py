"""One sweep of the open set measures each device type once and never writes to Live."""

from __future__ import annotations

import json

from scripts.measure_all_devices import devices_in_set, sweep


class StubClient:
    """A set with an EQ Eight on two tracks, a Compressor on a return, an Audio Effect Rack, and a Limiter on the master."""

    def __init__(self) -> None:
        self.trees = {
            ("track", 0): [{"name": "EQ Eight", "class_name": "Eq8"}, {"name": "Audio Effect Rack", "class_name": "AudioEffectGroupDevice", "can_have_chains": True}],
            ("track", 1): [{"name": "EQ Eight", "class_name": "Eq8"}],
            ("return", 0): [{"name": "Compressor", "class_name": "Compressor2"}],
            ("master", -1): [{"name": "Limiter", "class_name": "Limiter"}],
        }
        self.writes: list = []

    def query_session_state(self):
        return {"tracks": [{"index": 0, "name": "Bass"}, {"index": 1, "name": "Synth"}], "return_tracks": [{"index": 0, "name": "A-Reverb"}]}

    def get_return_tracks(self):
        return []

    def get_device_tree(self, kind, index):
        return {"success": True, "devices": self.trees.get((kind, index), [])}


def fake_measure(client, kind, index, device_index, samples):
    name = client.trees[(kind, index)][device_index]["name"]
    return {"device": name, "kind": kind, "index": index, "device_index": device_index, "parameters": [{"name": "P", "quantized": False}]}


def test_every_top_level_device_in_the_set_is_found_with_where_it_is() -> None:
    found = devices_in_set(StubClient())
    assert [(d["kind"], d["index"], d["device_index"], d["name"]) for d in found] == [
        ("track", 0, 0, "EQ Eight"), ("track", 0, 1, "Audio Effect Rack"), ("track", 1, 0, "EQ Eight"),
        ("return", 0, 0, "Compressor"), ("master", -1, 0, "Limiter")]


def test_each_device_type_is_measured_once_and_written_with_a_date(tmp_path) -> None:
    summary = sweep(StubClient(), tmp_path, measure=fake_measure, log=lambda _: None)
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["audio-effect-rack.json", "compressor.json", "eq-eight.json", "limiter.json"]
    assert summary["skipped"] == ["EQ Eight on Synth (already measured this run)"]
    saved = json.loads((tmp_path / "eq-eight.json").read_text(encoding="utf-8"))
    assert saved["measured_at"] and saved["class_name"] == "Eq8" and saved["index"] == 0


def test_a_rack_is_measured_for_its_own_controls_and_flagged_as_not_looking_inside(tmp_path) -> None:
    summary = sweep(StubClient(), tmp_path, measure=fake_measure, log=lambda _: None)
    assert summary["racks"] == ["Audio Effect Rack on Bass"]


def test_an_existing_file_is_kept_unless_forced(tmp_path) -> None:
    (tmp_path / "limiter.json").write_text('{"keep": true}', encoding="utf-8")
    summary = sweep(StubClient(), tmp_path, measure=fake_measure, log=lambda _: None)
    assert json.loads((tmp_path / "limiter.json").read_text(encoding="utf-8")) == {"keep": True}
    assert any("Limiter" in line and "has evidence" in line for line in summary["skipped"])
    sweep(StubClient(), tmp_path, measure=fake_measure, force=True, log=lambda _: None)
    assert json.loads((tmp_path / "limiter.json").read_text(encoding="utf-8"))["device"] == "Limiter"


def test_only_limits_the_sweep_to_the_named_devices(tmp_path) -> None:
    summary = sweep(StubClient(), tmp_path, measure=fake_measure, only={"compressor"}, log=lambda _: None)
    assert [p.name for p in tmp_path.glob("*.json")] == ["compressor.json"] and len(summary["measured"]) == 1


def test_one_failing_device_does_not_end_the_sweep(tmp_path) -> None:
    def flaky(client, kind, index, device_index, samples):
        if kind == "return":
            raise SystemExit("Live did not list the device's parameters: timeout")
        return fake_measure(client, kind, index, device_index, samples)

    summary = sweep(StubClient(), tmp_path, measure=flaky, log=lambda _: None)
    assert summary["failed"] == ["Compressor on A-Reverb: Live did not list the device's parameters: timeout"]
    assert (tmp_path / "limiter.json").exists() and not (tmp_path / "compressor.json").exists()

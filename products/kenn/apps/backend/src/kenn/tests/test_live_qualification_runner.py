"""Tests for the HTTP-backed real-Live qualification runner."""

from __future__ import annotations

from copy import deepcopy

from scripts import qualify_ableton_live as snapshot_runner
from scripts import qualify_ableton_live_device as runner
from scripts import qualify_ableton_live_mutations as mutation_runner


def test_snapshot_qualification_uses_the_companion_endpoint(monkeypatch) -> None:
    calls: list[str] = []

    def fake_snapshot(endpoint: str) -> dict:
        calls.append(endpoint)
        return {"status": "connected", "tracks": [{"index": 3, "name": "4-Audio"}]}

    monkeypatch.setattr(snapshot_runner, "_real_snapshot", fake_snapshot)
    result = snapshot_runner.qualify("real", "http://kenn:8090")

    assert result["status"] == "passed"
    assert result["evidence_kind"] == "real_live"
    assert calls == ["http://kenn:8090"]


def test_snapshot_qualification_can_require_the_mcp_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        snapshot_runner,
        "_real_snapshot",
        lambda endpoint: {
            "status": "connected",
            "backend": "ableton-control-deck-mcp",
            "tracks": [{"index": 0, "name": "Drums"}],
        },
    )
    matched = snapshot_runner.qualify(
        "real", "http://kenn:8090", "ableton-control-deck-mcp"
    )
    mismatched = snapshot_runner.qualify("real", "http://kenn:8090", "osc")

    assert matched["status"] == "passed"
    assert matched["checks"]["backend_match"] is True
    assert mismatched["status"] == "blocked"
    assert mismatched["checks"]["backend_match"] is False


def test_qualification_runner_uses_command_status_and_completes_undo(monkeypatch) -> None:
    state = {"value": 0.0}
    calls: list[tuple[str, dict]] = []
    proposal = {
        "schema": "kenn.action_proposal.v1",
        "action_id": "proposal-1",
        "confirmation_token": "token-1",
        "track_index": 3,
        "track_name": "4-Audio",
        "device_index": 0,
        "device_name": "EQ Eight",
        "parameter_index": 7,
        "parameter": "1 Gain A",
        "before": 0.0,
        "after": -3.0,
    }
    receipt = {
        "schema": "kenn.ableton_action_receipt.v1",
        "receipt_id": "receipt-1",
        "action": "set_device_parameter",
        "status": "applied",
        "verified": True,
        "target": {"track_index": 3, "track_name": "4-Audio", "device_index": 0, "device_name": "EQ Eight", "parameter_index": 7, "parameter": "1 Gain A"},
        "before": 0.0,
        "requested": -3.0,
        "readback": -3.0,
    }
    undo = {**proposal, "action_id": "proposal-undo", "confirmation_token": "token-undo", "before": -3.0, "after": 0.0}

    def fake_get(_endpoint: str, path: str) -> dict:
        if path.endswith("/api/ableton/osc/session"):
            return {"status": "connected", "tracks": [{"index": 3, "name": "4-Audio", "devices": [{"index": 0, "name": "EQ Eight"}]}]}
        return {"success": True, "device_name": "EQ Eight", "parameters": [{"index": 7, "name": "1 Gain A", "value": state["value"], "min": -15.0, "max": 15.0}]}

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        calls.append((path, payload))
        if path.endswith("/api/ableton/command") and "proposal" not in payload:
            return {"status": "confirmation_required", "proposal": proposal}
        if path.endswith("/api/ableton/command"):
            state["value"] = -3.0
            return {"status": "applied", "receipt": receipt}
        if path.endswith("/api/ableton/osc/undo") and "proposal" not in payload:
            return {"ok": True, "proposal": undo}
        state["value"] = 0.0
        return {"ok": True, "receipt": {**receipt, "receipt_id": "receipt-undo", "before": -3.0, "requested": 0.0, "readback": 0.0}}

    monkeypatch.setattr(runner, "_get", fake_get)
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(endpoint="http://kenn", track_index=3, device_index=0, parameter_name="1 Gain A", value=-3.0, session_id="runner-test", apply=True)

    assert result["status"] == "passed"
    assert result["replay_rejected"] is True
    assert result["restored_readback"] == 0.0
    assert any(path.endswith("/api/ableton/osc/undo") and "proposal" in payload for path, payload in calls)


def test_mutation_qualification_uses_companion_http_boundary(monkeypatch) -> None:
    calls: list[tuple[str, str, dict]] = []

    def fake_get(endpoint: str, path: str) -> dict:
        calls.append(("GET", path, {}))
        if path.endswith("/api/ableton/osc/session"):
            return {"status": "connected", "tracks": []}
        if path.endswith("/api/ableton/osc/song-time"):
            return {"success": True, "current_song_time": 4.0}
        if path.endswith("/api/ableton/osc/locators"):
            return {"success": True, "locators": []}
        return {"success": True, "has_clip": False, "notes": []}

    def fake_post(endpoint: str, path: str, payload: dict) -> dict:
        calls.append(("POST", path, payload))
        return {"ok": True, "proposal": {"schema": "kenn.ableton_action_proposal.v1"}}

    monkeypatch.setattr(mutation_runner, "_get", fake_get)
    monkeypatch.setattr(mutation_runner, "_post", fake_post)
    client = mutation_runner.CompanionQualificationClient("http://kenn:8090")
    service = mutation_runner.CompanionMutationService(client)

    assert service.snapshot()["status"] == "connected"
    assert service.client.get_current_song_time() == 4.0
    assert service.client.get_locators_with_status() == ([], True)
    service.propose_track_action(
        "set_volume", track_index=2, track_name="Bass", value=0.74, session_id="qualification-http"
    )
    assert calls[-1] == (
        "POST", "/api/ableton/osc/volume",
        {"session_id": "qualification-http", "track_index": 2, "track_name": "Bass", "volume": 0.74},
    )
    assert not any("ableton_osc_bridge" in repr(call) for call in calls)


def test_qualification_runner_records_targeted_display_evidence(monkeypatch) -> None:
    state = {"value": 0.2, "display": "20 %"}
    proposal = {
        "schema": "kenn.action_proposal.v1",
        "action_id": "proposal-display",
        "confirmation_token": "token-display",
        "track_index": 2,
        "track_name": "3-Audio",
        "device_index": 1,
        "device_name": "Drum Buss",
        "parameter_index": 2,
        "parameter": "Drive",
        "before": 0.2,
        "after": 0.35,
    }
    receipt = {"receipt_id": "receipt-display", "action": "set_device_parameter", "status": "applied", "verified": True, "before": 0.2, "requested": 0.35, "readback": 0.35}
    undo = {**proposal, "action_id": "proposal-display-undo", "confirmation_token": "token-display-undo", "before": 0.35, "after": 0.2}

    def fake_get(_endpoint: str, path: str) -> dict:
        if path.endswith("/api/ableton/osc/session"):
            return {"status": "connected", "tracks": [{"index": 2, "name": "3-Audio", "devices": [{"index": 0, "name": "Auto Filter"}, {"index": 1, "name": "Drum Buss"}]}]}
        if "value-string" in path:
            return {"success": True, "value_string": state["display"]}
        return {"success": True, "device_name": "Drum Buss", "parameters": [{"index": 2, "name": "Drive", "value": state["value"], "min": 0.0, "max": 1.0}]}

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        if path.endswith("/api/ableton/command") and "proposal" not in payload:
            return {"status": "confirmation_required", "proposal": proposal}
        if path.endswith("/api/ableton/command"):
            state.update(value=0.35, display="35 %")
            return {"status": "applied", "receipt": receipt}
        if "proposal" not in payload:
            return {"ok": True, "proposal": undo}
        state.update(value=0.2, display="20 %")
        return {"ok": True, "receipt": {**receipt, "receipt_id": "receipt-display-undo", "readback": 0.2}}

    monkeypatch.setattr(runner, "_get", fake_get)
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(endpoint="http://kenn", track_index=2, device_index=1, parameter_name="Drive", value=0.35, session_id="display-test", apply=True)

    assert result["status"] == "passed"
    assert result["target"]["display_before"] == "20 %"
    assert result["display_after"] == "35 %"
    assert result["display_restored"] == "20 %"


def test_device_qualification_is_proposal_only_by_default(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []
    proposal = {
        "action_id": "proposal-1",
        "confirmation_token": "secret-token",
        "track_index": 3,
        "track_name": "4-Audio",
        "device_index": 0,
        "device_name": "Glue Compressor",
        "parameter_index": 1,
        "parameter": "Threshold",
        "before": -20.0,
        "after": -18.0,
        "unit": "dB",
    }

    def fake_get(_endpoint: str, path: str) -> dict:
        if path.endswith("/api/ableton/osc/session"):
            return {"status": "connected", "tracks": [{"index": 3, "name": "4-Audio", "devices": [{"index": 0, "name": "Glue Compressor"}]}]}
        return {"success": True, "device_name": "Glue Compressor", "parameters": [{"index": 1, "name": "Threshold", "value": -20.0, "min": -40.0, "max": 0.0}]}

    def fake_post(_endpoint: str, path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"status": "confirmation_required", "proposal": proposal}

    monkeypatch.setattr(runner, "_get", fake_get)
    monkeypatch.setattr(runner, "_post", fake_post)
    result = runner.qualify(endpoint="http://kenn", track_index=3, device_index=0, parameter_name="Threshold", value=-18.0, session_id="proposal-test")

    assert result["status"] == "proposal_ready"
    assert result["changed"] is False
    assert result["proposal"]["before"] == -20.0
    assert result["proposal"]["after"] == -18.0
    assert "confirmation_token" not in result["proposal"]
    assert len(calls) == 1
    assert calls[0][0].endswith("/api/ableton/command")
    assert "proposal" not in calls[0][1]


def test_mutation_runner_qualifies_temporary_track_rename_and_restoration() -> None:
    class FakeRenameService:
        def __init__(self) -> None:
            self.name = "Vocal"
            self.executed: set[str] = set()

        def snapshot(self) -> dict:
            return {"tracks": [{"index": 0, "name": self.name}]}

        def propose_track_action(self, action: str, *, track_index: int, track_name: str, value: str, session_id: str) -> dict:
            assert action == "rename_track"
            assert track_index == 0 and track_name == self.name
            return {"ok": True, "proposal": {
                "action": action, "action_id": f"action-{len(self.executed)}",
                "confirmation_token": "secret", "track_index": track_index,
                "track_name": track_name, "before": self.name, "after": value,
            }}

        def execute(self, proposal: dict, *, confirm_token: str, session_id: str, idempotency_key: str) -> dict:
            if idempotency_key in self.executed:
                return {"ok": False, "error": "replay rejected"}
            self.executed.add(idempotency_key)
            before = self.name
            self.name = str(proposal["after"])
            return {"ok": True, "receipt": {
                "receipt_id": f"receipt-{idempotency_key}", "action": "rename_track",
                "target": {"track_index": 0, "track_name": before},
                "before": before, "readback": self.name,
                "status": "applied", "verified": True,
            }}

        def propose_undo(self, receipt: dict, *, session_id: str) -> dict:
            return {"ok": True, "proposal": {
                "action": "rename_track", "action_id": "undo-action",
                "confirmation_token": "undo-secret", "track_index": 0,
                "track_name": self.name, "before": self.name, "after": receipt["before"],
            }}

    service = FakeRenameService()
    before = service.name
    result = mutation_runner._run_track_action(
        service, action="rename_track", field="name",
        target_value=lambda item: mutation_runner._rename_test_value(item["name"], 0),
        track_index=0, track_name=before, session_id="rename-test",
    )

    assert result["status"] == "passed"
    assert result["replay_rejected"] is True
    assert result["restored_readback"] == before


def test_mutation_runner_qualifies_temporary_locator_lifecycle() -> None:
    class FakeLocatorLive:
        def __init__(self) -> None:
            self.state = {
                "status": "connected",
                "is_playing": False,
                "current_song_time": 16.0,
                "locators": [],
                "tracks": [],
            }

        def query_session_state(self, **_kwargs) -> dict:
            return self.state.copy() | {"locators": [item.copy() for item in self.state["locators"]]}

        def get_current_song_time(self) -> float:
            return self.state["current_song_time"]

        def get_locators_with_status(self) -> tuple[list[dict], bool]:
            return [item.copy() for item in self.state["locators"]], True

        def add_locator(self, name: str) -> bool:
            self.state["locators"].append({"index": len(self.state["locators"]), "name": name, "time_beats": 16.0})
            return True

        def remove_locator(self, name: str, time_beats: float) -> bool:
            before = len(self.state["locators"])
            self.state["locators"] = [
                item for item in self.state["locators"]
                if not (item["name"] == name and item["time_beats"] == time_beats)
            ]
            return len(self.state["locators"]) == before - 1

    fake = FakeLocatorLive()
    result = mutation_runner._run_locator(fake, locator_name="KENN locator qualification", session_id="locator-runner")

    assert result["status"] == "passed"
    assert result["replay_rejected"] is True
    assert result["restored_readback"] is True


def test_mutation_runner_qualifies_midi_note_replacement_and_clear() -> None:
    original = [
        {"pitch": 36, "start_time": 0.0, "duration": 1.0, "velocity": 110, "mute": False},
        {"pitch": 43, "start_time": 1.0, "duration": 0.5, "velocity": 96, "mute": False},
    ]

    class FakeMidiLive:
        def __init__(self) -> None:
            self.state = {"status": "connected", "tempo": 120.0, "tracks": [{"index": 0, "name": "Bass MIDI", "devices": []}]}
            self.notes = deepcopy(original)
            self.writes: list[str] = []

        def query_session_topology(self) -> dict:
            return deepcopy(self.state)

        def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
            return {
                "success": True,
                "track_index": track_index,
                "track_name": "Bass MIDI",
                "clip_slot_index": clip_slot_index,
                "has_clip": True,
                "is_midi_clip": True,
                "length": 4.0,
                "notes": deepcopy(self.notes),
            }

        def remove_all_midi_notes(self, track_index: int, clip_slot_index: int) -> bool:
            self.writes.append("remove")
            self.notes = []
            return True

        def add_midi_notes(self, track_index: int, clip_slot_index: int, notes: list[dict]) -> bool:
            self.writes.append("add")
            self.notes = deepcopy(notes)
            return True

    fake = FakeMidiLive()
    endpoint = {"track_index": 0, "track_name": "Bass MIDI", "clip_slot_index": 0, "state": fake.get_midi_clip_state(0, 0)}
    replacement = [{"pitch": 48, "start_time": 2.0, "duration": 1.0, "velocity": 100, "mute": False}]

    replaced = mutation_runner._run_midi_clip_update(
        fake, endpoint=endpoint, replacement_notes=replacement, session_id="midi-runner-replace",
    )
    cleared = mutation_runner._run_midi_clip_update(
        fake, endpoint=endpoint, replacement_notes=[], session_id="midi-runner-clear",
    )

    assert replaced["status"] == "passed"
    assert cleared["status"] == "passed"
    assert replaced["replay_rejected"] is True
    assert cleared["replay_rejected"] is True
    assert fake.notes == original
    assert fake.writes == ["remove", "add", "remove", "add", "remove", "remove", "add"]

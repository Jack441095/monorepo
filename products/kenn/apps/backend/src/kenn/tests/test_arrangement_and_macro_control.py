from copy import deepcopy

from kenn.core.live_action_service import (
    LiveActionService,
    ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA,
    ARRANGEMENT_DUPLICATION_RECEIPT_SCHEMA,
    CLIP_AUTOMATION_PROPOSAL_SCHEMA,
    CLIP_AUTOMATION_RECEIPT_SCHEMA,
    RACK_MACRO_PROPOSAL_SCHEMA,
    RACK_MACRO_RECEIPT_SCHEMA,
    MIDI_CLIP_PROPOSAL_SCHEMA,
)


class FakeLiveClient:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tracks": [
                {
                    "index": 0,
                    "name": "Bass",
                    "has_midi_input": True,
                    "devices": [
                        {
                            "index": 0,
                            "name": "Audio Effect Rack",
                            "parameters": [
                                {"index": 0, "name": "Macro 1", "value": 0.0, "min": 0.0, "max": 1.0},
                                {"index": 1, "name": "Filter Freq", "value": 500.0, "min": 20.0, "max": 20000.0},
                            ],
                        }
                    ],
                }
            ],
        }
        self.slots: dict[tuple[int, int], dict] = {
            (0, 0): {
                "has_clip": True,
                "clip_name": "Bass Loop",
                "is_midi_clip": True,
                "length": 4.0,
                "notes": [{"pitch": 36, "start_time": 0.0, "duration": 1.0, "velocity": 100}],
            }
        }
        self.arrangement_clips: dict[int, list[dict]] = {0: []}
        self.automation_writes: list[tuple] = []
        self.macro_mappings: list[tuple] = []

    def query_session_state(self, include_mixer: bool = False) -> dict:
        return deepcopy(self.state)

    def query_session_topology(self) -> dict:
        return deepcopy(self.state)

    def get_clip_slot_state(self, track_index: int, clip_slot_index: int) -> dict:
        slot = self.slots.get((track_index, clip_slot_index))
        if slot is None:
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "has_clip": False}
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, **deepcopy(slot)}

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
        return self.get_clip_slot_state(track_index, clip_slot_index)

    def duplicate_clip_to_arrangement(self, track_index: int, clip_slot_index: int, dest_time: float) -> bool:
        slot = self.slots.get((track_index, clip_slot_index))
        if not slot or not slot.get("has_clip"):
            return False
        self.arrangement_clips.setdefault(track_index, []).append({
            "name": slot["clip_name"],
            "start_time": dest_time,
            "length": slot["length"],
            "is_midi_clip": slot["is_midi_clip"],
        })
        return True

    def get_arrangement_clips(self, track_index: int) -> list[dict]:
        return deepcopy(self.arrangement_clips.get(track_index, []))

    def set_clip_automation(self, track_index: int, clip_slot_index: int, dev_index: int, param_index: int, points: list) -> bool:
        self.automation_writes.append((track_index, clip_slot_index, dev_index, param_index, points))
        return True

    def map_rack_macro(self, track_index: int, dev_index: int, macro_index: int, target_param_index: int) -> bool:
        self.macro_mappings.append((track_index, dev_index, macro_index, target_param_index))
        return True


def test_arrangement_duplication_flow() -> None:
    fake = FakeLiveClient()
    service = LiveActionService(fake)

    # Propose duplicating clip from slot (0, 0) to arrangement beat 16.0
    prop_res = service.propose_arrangement_duplication(
        track_index=0,
        clip_slot_index=0,
        destination_time_beats=16.0,
        session_id="arr-session",
    )
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["schema"] == ARRANGEMENT_DUPLICATION_PROPOSAL_SCHEMA
    assert proposal["destination_time_beats"] == 16.0
    token = proposal["confirmation_token"]

    # Fails without confirmation
    bad_exec = service.execute(proposal, confirm_token="wrong", session_id="arr-session")
    assert bad_exec["ok"] is False

    # Executes with confirmation
    exec_res = service.execute(proposal, confirm_token=token, session_id="arr-session")
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == ARRANGEMENT_DUPLICATION_RECEIPT_SCHEMA
    assert receipt["verified"] is True
    assert len(fake.arrangement_clips[0]) == 1
    assert fake.arrangement_clips[0][0]["start_time"] == 16.0


def test_clip_automation_flow() -> None:
    fake = FakeLiveClient()
    service = LiveActionService(fake)
    curve_points = [
        {"time": 0.0, "value": 200.0},
        {"time": 2.0, "value": 800.0},
        {"time": 4.0, "value": 200.0},
    ]

    prop_res = service.propose_clip_automation(
        track_index=0,
        clip_slot_index=0,
        device_index=0,
        parameter_index=1,
        points=curve_points,
        session_id="auto-session",
    )
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["schema"] == CLIP_AUTOMATION_PROPOSAL_SCHEMA
    assert proposal["point_count"] == 3

    exec_res = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="auto-session")
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == CLIP_AUTOMATION_RECEIPT_SCHEMA
    assert receipt["points_written"] == 3
    assert len(fake.automation_writes) == 1


def test_rack_macro_mapping_flow() -> None:
    fake = FakeLiveClient()
    service = LiveActionService(fake)

    prop_res = service.propose_rack_macro_mapping(
        track_index=0,
        device_index=0,
        macro_index=0,
        target_param_index=1,
        session_id="macro-session",
    )
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["schema"] == RACK_MACRO_PROPOSAL_SCHEMA

    exec_res = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="macro-session")
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == RACK_MACRO_RECEIPT_SCHEMA
    assert receipt["macro_index"] == 0
    assert len(fake.macro_mappings) == 1


def test_read_clip_notes() -> None:
    fake = FakeLiveClient()
    service = LiveActionService(fake)
    notes_state = service.read_clip_notes(0, 0)
    assert notes_state["success"] is True
    assert len(notes_state["notes"]) == 1
    assert notes_state["notes"][0]["pitch"] == 36

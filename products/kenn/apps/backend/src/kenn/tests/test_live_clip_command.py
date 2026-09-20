from copy import deepcopy

from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command, validate_llm_plan


class FakeClipCommandClient:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tracks": [
                {"index": 0, "name": "Drums", "devices": []},
                {"index": 1, "name": "Drums Copy", "devices": []},
            ],
        }
        self.clips = {
            (0, 0): {
                "has_clip": True,
                "clip_name": "Beat",
                "is_midi_clip": False,
                "length": 4.0,
                "notes": [],
            }
        }
        self.writes = []

    def query_session_state(self, **_kwargs):
        return deepcopy(self.state)

    def get_clip_slot_state(self, track_index, clip_slot_index):
        clip = self.clips.get((track_index, clip_slot_index))
        if clip is None:
            return {"success": True, "has_clip": False, "track_index": track_index, "clip_slot_index": clip_slot_index, "clip_name": "", "is_midi_clip": False, "length": 0.0, "notes": []}
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, **deepcopy(clip)}

    def duplicate_clip_to(self, source_track_index, source_slot, target_track_index, target_slot):
        self.writes.append((source_track_index, source_slot, target_track_index, target_slot))
        self.clips[(target_track_index, target_slot)] = deepcopy(self.clips[(source_track_index, source_slot)])
        return True

    def delete_clip(self, track_index, clip_slot_index):
        self.clips.pop((track_index, clip_slot_index), None)
        return True

    def set_clip_name(self, track_index, clip_slot_index, name):
        self.clips[(track_index, clip_slot_index)]["clip_name"] = name
        return True


def test_natural_duplicate_command_returns_confirmation_only_proposal() -> None:
    fake = FakeClipCommandClient()
    result = handle_command(
        "duplicate the clip on track 1 slot 1 to Drums Copy slot 3",
        session_id="natural-clip",
        service=LiveActionService(fake),
        allow_llm=False,
    )
    assert result["status"] == "confirmation_required"
    assert result["proposal_kind"] == "clip_duplication"
    assert result["proposal"]["source"]["track_name"] == "Drums"
    assert result["proposal"]["target"]["clip_slot_index"] == 2
    assert fake.writes == []


def test_natural_clip_rename_command_returns_confirmation_only_proposal() -> None:
    fake = FakeClipCommandClient()
    result = handle_command(
        "rename the clip on track 1 slot 1 to Intro",
        session_id="natural-rename",
        service=LiveActionService(fake),
        allow_llm=False,
    )
    assert result["status"] == "confirmation_required"
    assert result["proposal_kind"] == "clip_rename"
    assert result["proposal"]["new_name"] == "Intro"
    assert fake.writes == []


def test_llm_clip_rename_plan_requires_exact_slot_and_track_identity() -> None:
    snapshot = {"tracks": [{"index": 0, "name": "Drums", "devices": []}]}
    plan = {
        "schema": "kenn.ableton_llm_plan.v1",
        "action": "rename_clip",
        "track_index": 0,
        "track_name": "Drums",
        "clip_slot_index": 1,
        "value": "Verse",
    }
    assert validate_llm_plan(plan, snapshot)["ok"] is True
    bad = {**plan, "track_name": "Other"}
    assert validate_llm_plan(bad, snapshot)["ok"] is False

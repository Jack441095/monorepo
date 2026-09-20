from copy import deepcopy

from kenn.core.clip_duplication_service import (
    ClipDuplicationActionService,
    PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA,
)


class FakeClipLive:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tracks": [
                {"index": 0, "name": "Drums", "devices": []},
                {"index": 1, "name": "Drums Copy", "devices": []},
            ],
        }
        self.clips: dict[tuple[int, int], dict] = {
            (0, 0): {
                "has_clip": True,
                "clip_name": "Beat",
                "is_midi_clip": True,
                "length": 4.0,
                "notes": [{"pitch": 36, "start_time": 0.0, "duration": 1.0, "velocity": 110, "mute": False}],
            },
        }
        self.writes: list[tuple[str, object]] = []

    def query_session_topology(self) -> dict:
        return deepcopy(self.state)

    def get_clip_slot_state(self, track_index: int, clip_slot_index: int) -> dict:
        clip = self.clips.get((track_index, clip_slot_index))
        if clip is None:
            return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, "has_clip": False, "clip_name": "", "is_midi_clip": False, "length": 0.0, "notes": []}
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, **deepcopy(clip)}

    def duplicate_clip_to(self, source_track_index: int, source_slot: int, target_track_index: int, target_slot: int) -> bool:
        self.writes.append(("duplicate", (source_track_index, source_slot, target_track_index, target_slot)))
        self.clips[(target_track_index, target_slot)] = deepcopy(self.clips[(source_track_index, source_slot)])
        return True

    def delete_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("delete", (track_index, clip_slot_index)))
        self.clips.pop((track_index, clip_slot_index), None)
        return True


def _proposal(service: ClipDuplicationActionService, session: str = "clip-dup") -> dict:
    result = service.propose(
        source_track_index=0,
        source_track_name="Drums",
        source_clip_slot_index=0,
        target_track_index=1,
        target_track_name="Drums Copy",
        target_clip_slot_index=2,
        session_id=session,
    )
    assert result["ok"] is True
    assert result["proposal"]["schema"] == PROPOSAL_SCHEMA
    return result["proposal"]


def test_clip_duplication_is_confirmation_gated_and_verifies_midi_readback() -> None:
    fake = FakeClipLive()
    service = ClipDuplicationActionService(fake)
    proposal = _proposal(service)

    assert service.execute(proposal, confirm_token="", session_id="clip-dup")["ok"] is False
    assert fake.writes == []

    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="clip-dup")
    assert result["ok"] is True
    assert result["receipt"]["schema"] == RECEIPT_SCHEMA
    assert result["receipt"]["verified"] is True
    assert len(fake.writes) == 1

    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="clip-dup")
    assert replay["ok"] is False
    assert len(fake.writes) == 1


def test_clip_duplication_supports_audio_metadata_and_verified_undo() -> None:
    fake = FakeClipLive()
    fake.clips[(0, 0)] = {"has_clip": True, "clip_name": "Vocal", "is_midi_clip": False, "length": 8.0, "notes": []}
    service = ClipDuplicationActionService(fake)
    proposal = _proposal(service, session="audio-dup")
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="audio-dup")
    assert applied["ok"] is True

    undo = service.propose_undo(applied["receipt"], session_id="audio-undo")
    assert undo["ok"] is True
    removed = service.execute_undo(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="audio-undo")
    assert removed["ok"] is True
    assert fake.get_clip_slot_state(1, 2)["has_clip"] is False


def test_clip_duplication_rejects_occupied_or_stale_targets_without_writing() -> None:
    fake = FakeClipLive()
    service = ClipDuplicationActionService(fake)
    fake.clips[(1, 2)] = {"has_clip": True, "clip_name": "Existing", "is_midi_clip": False, "length": 2.0, "notes": []}
    occupied = service.propose(
        source_track_index=0, source_track_name="Drums", source_clip_slot_index=0,
        target_track_index=1, target_track_name="Drums Copy", target_clip_slot_index=2, session_id="occupied",
    )
    assert occupied["ok"] is False
    assert fake.writes == []

    fake.clips.pop((1, 2))
    proposal = _proposal(service, session="stale")
    fake.clips[(0, 0)]["clip_name"] = "Changed"
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="stale")
    assert result["ok"] is False
    assert "source clip changed" in result["error"]
    assert fake.writes == []


def test_clip_duplication_undo_rechecks_target_track_identity() -> None:
    fake = FakeClipLive()
    service = ClipDuplicationActionService(fake)
    proposal = _proposal(service, session="dup-undo-identity")
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="dup-undo-identity")
    assert applied["ok"] is True

    fake.state["tracks"][1]["name"] = "Replacement Track"
    stale = service.propose_undo(applied["receipt"], session_id="dup-undo-stale")
    assert stale["ok"] is False
    assert "changed" in stale["error"]

    fake.state["tracks"][1]["name"] = "Drums Copy"
    undo = service.propose_undo(applied["receipt"], session_id="dup-undo-fresh")
    assert undo["ok"] is True
    fake.state["tracks"][1]["name"] = "Replacement Track"
    result = service.execute_undo(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="dup-undo-fresh")
    assert result["ok"] is False
    assert "changed" in result["error"]
    assert not any(write[0] == "delete" for write in fake.writes)

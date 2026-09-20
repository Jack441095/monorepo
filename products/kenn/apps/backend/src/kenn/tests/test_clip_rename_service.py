from copy import deepcopy

from kenn.core.clip_rename_service import ClipRenameActionService, PROPOSAL_SCHEMA, RECEIPT_SCHEMA


class FakeClipRenameLive:
    def __init__(self) -> None:
        self.state = {"status": "connected", "tracks": [{"index": 0, "name": "Drums", "devices": []}]}
        self.clip = {"has_clip": True, "clip_name": "Clip 1", "is_midi_clip": False, "length": 4.0, "notes": []}
        self.writes = []

    def query_session_topology(self):
        return deepcopy(self.state)

    def get_clip_slot_state(self, track_index, clip_slot_index):
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, **deepcopy(self.clip)}

    def set_clip_name(self, track_index, clip_slot_index, name):
        self.writes.append((track_index, clip_slot_index, name))
        self.clip["clip_name"] = name
        return True


def _proposal(service: ClipRenameActionService, session: str = "rename"):
    result = service.propose(track_index=0, track_name="Drums", clip_slot_index=0, new_name="Verse", session_id=session)
    assert result["ok"] is True
    assert result["proposal"]["schema"] == PROPOSAL_SCHEMA
    return result["proposal"]


def test_clip_rename_is_confirmation_gated_replay_protected_and_undoable():
    fake = FakeClipRenameLive()
    service = ClipRenameActionService(fake)
    proposal = _proposal(service)
    assert service.execute(proposal, confirm_token="", session_id="rename")["ok"] is False
    assert fake.writes == []

    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="rename")
    assert applied["ok"] is True
    assert applied["receipt"]["schema"] == RECEIPT_SCHEMA
    assert applied["receipt"]["verified"] is True
    assert fake.clip["clip_name"] == "Verse"

    replay = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="rename")
    assert replay["ok"] is False
    assert len(fake.writes) == 1

    undo = service.propose_undo(applied["receipt"], session_id="rename-undo")
    assert undo["ok"] is True
    removed = service.execute_undo(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="rename-undo")
    assert removed["ok"] is True
    assert fake.clip["clip_name"] == "Clip 1"


def test_clip_rename_rejects_stale_clip_before_writing():
    fake = FakeClipRenameLive()
    service = ClipRenameActionService(fake)
    proposal = _proposal(service, session="stale-rename")
    fake.clip["length"] = 8.0
    result = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="stale-rename")
    assert result["ok"] is False
    assert "changed before rename" in result["error"]
    assert fake.writes == []


def test_clip_rename_undo_rechecks_track_identity():
    fake = FakeClipRenameLive()
    service = ClipRenameActionService(fake)
    proposal = _proposal(service, session="rename-undo-identity")
    applied = service.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="rename-undo-identity")
    assert applied["ok"] is True

    fake.state["tracks"][0]["name"] = "Replacement Track"
    stale = service.propose_undo(applied["receipt"], session_id="rename-undo-stale")
    assert stale["ok"] is False
    assert "changed" in stale["error"]

    fake.state["tracks"][0]["name"] = "Drums"
    undo = service.propose_undo(applied["receipt"], session_id="rename-undo-fresh")
    assert undo["ok"] is True
    fake.state["tracks"][0]["name"] = "Replacement Track"
    result = service.execute_undo(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="rename-undo-fresh")
    assert result["ok"] is False
    assert "changed" in result["error"]
    assert fake.writes == [(0, 0, "Verse")]

from copy import deepcopy

import pytest

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


@pytest.mark.parametrize("altered_field", [None, "before_clip", "after_clip"])
def test_http_clip_undo_retains_recorded_names_and_refuses_edited_clip_state(tmp_path, monkeypatch, altered_field):
    # Mandatory Undo authentication must preserve the original clip state and reject invented restore names.
    from kenn.core import live_receipt_journal as journal
    from kenn.core.live_action_service import LiveActionService
    from kenn.routes import daw_command_handler

    monkeypatch.setattr(journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    fake = FakeClipRenameLive()
    fake.requires_guarded_parameter_targets = True
    rename = ClipRenameActionService(fake)
    proposal = _proposal(rename)
    receipt = rename.execute(proposal, confirm_token=proposal["confirmation_token"], session_id="rename")["receipt"]
    assert journal.record_receipt(receipt, session_id="rename")
    if altered_field:
        receipt[altered_field]["clip_name"] = "Invented name"
    monkeypatch.setattr(daw_command_handler, "_get_live_action_service", lambda: lambda: LiveActionService(fake))
    monkeypatch.setattr(daw_command_handler, "ClipRenameActionService", lambda: rename)

    class Reply:
        def send_json(self, status, body):
            self.status, self.body = status, body

    reply = Reply()
    daw_command_handler.handle_osc_undo(reply, {"session_id": "rename", "receipt": receipt})
    if altered_field:
        assert reply.status == 409, reply.body
        assert "Receipt identity or values changed" in reply.body["error"]
        assert "proposal" not in reply.body
        assert fake.writes == [(0, 0, "Verse")]
    else:
        assert reply.status == 200, reply.body
        inverse = reply.body["proposal"]
        assert rename.execute_undo(inverse, confirm_token=inverse["confirmation_token"], session_id="rename")["ok"]
        assert fake.clip["clip_name"] == "Clip 1"
        assert fake.writes == [(0, 0, "Verse"), (0, 0, "Clip 1")]

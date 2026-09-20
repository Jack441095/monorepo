from __future__ import annotations

from copy import deepcopy

from kenn.core.midi_clip_service import CREATE_PROPOSAL_SCHEMA, MidiClipActionService, RECEIPT_SCHEMA, UPDATE_PROPOSAL_SCHEMA


class FakeMidiLive:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tempo": 120.0,
            "tracks": [{"index": 1, "name": "Bass MIDI", "devices": []}],
        }
        self.clips: dict[tuple[int, int], dict] = {}
        self.writes: list[tuple[str, object]] = []

    def query_session_topology(self) -> dict:
        return deepcopy(self.state)

    def get_track_has_midi_input(self, track_index: int) -> bool:
        assert track_index == 1
        return True

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
        clip = self.clips.get((track_index, clip_slot_index))
        if clip is None:
            return {
                "success": True,
                "track_index": track_index,
                "clip_slot_index": clip_slot_index,
                "has_clip": False,
                "is_midi_clip": False,
                "length": 0.0,
                "notes": [],
            }
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, **deepcopy(clip)}

    def create_midi_clip(self, track_index: int, clip_slot_index: int, length: float) -> bool:
        self.writes.append(("create", (track_index, clip_slot_index, length)))
        self.clips[(track_index, clip_slot_index)] = {
            "has_clip": True,
            "is_midi_clip": True,
            "length": length,
            "notes": [],
        }
        return True

    def add_midi_notes(self, track_index: int, clip_slot_index: int, notes: list[dict]) -> bool:
        self.writes.append(("add_notes", deepcopy(notes)))
        self.clips[(track_index, clip_slot_index)]["notes"] = deepcopy(notes)
        return True

    def remove_all_midi_notes(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("remove_notes", (track_index, clip_slot_index)))
        self.clips[(track_index, clip_slot_index)]["notes"] = []
        return True

    def delete_midi_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("delete", (track_index, clip_slot_index)))
        self.clips.pop((track_index, clip_slot_index), None)
        return True


def _notes() -> list[dict]:
    return [
        {"pitch": 36, "start_time": 0.0, "duration": 1.0, "velocity": 110, "mute": False},
        {"pitch": 43, "start_time": 1.0, "duration": 0.5, "velocity": 96, "mute": False},
    ]


def _context() -> dict:
    return {
        "schema": "kenn.audiogen_live_context.v1",
        "target": {"track_index": 1, "track_name": "Bass MIDI"},
        "live_tempo_bpm": 120.0,
        "source_tempo_bpm": None,
        "tempo_relationship": "unknown",
        "timing_basis": "symbolic MIDI positions are expressed in beats; Live project tempo governs playback",
        "timing_action": "preserve_symbolic_beats",
        "adaptation": "none_required",
        "selected_track_index": 1,
        "limitations": ["AudioGen did not provide a source BPM; tempo relationship is unknown."],
    }


def _proposal(service: MidiClipActionService, session: str = "midi-service") -> dict:
    result = service.propose_create(
        track_index=1,
        track_name="Bass MIDI",
        clip_slot_index=0,
        length=4.0,
        notes=_notes(),
        session_id=session,
        source_artifact_sha256="sha256:" + ("a" * 64),
        source_context=_context(),
    )
    assert result["ok"]
    assert result["proposal"]["schema"] == CREATE_PROPOSAL_SCHEMA
    assert result["proposal"]["source_context"]["live_tempo_bpm"] == 120.0
    return result["proposal"]


def test_midi_clip_receipt_carries_correlation_id_retry_safety_and_stage_timings() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service)
    applied = service.execute_create(
        proposal, confirm_token=proposal["confirmation_token"], session_id="midi-service", correlation_id="caller-corr-midi",
    )
    assert applied["ok"] is True
    receipt = applied["receipt"]
    assert receipt["correlation_id"] == "caller-corr-midi"
    assert receipt["retry_safe"] == "safe"
    assert "write" in receipt["stage_timings_ms"]
    assert "readback" in receipt["stage_timings_ms"]

    undo_proposed = service.propose_undo(receipt, session_id="midi-undo")
    undone = service.execute_remove(
        undo_proposed["proposal"],
        confirm_token=undo_proposed["proposal"]["confirmation_token"],
        session_id="midi-undo",
        correlation_id="caller-corr-undo",
    )
    assert undone["ok"] is True
    assert undone["receipt"]["correlation_id"] == "caller-corr-undo"
    assert undone["receipt"]["retry_safe"] == "safe"


def test_midi_clip_creation_requires_confirmation_and_supports_verified_undo() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service)

    assert service.execute_create(proposal, confirm_token="", session_id="midi-service")["ok"] is False
    assert fake.writes == []

    applied = service.execute_create(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-service",
    )
    assert applied["ok"] is True
    assert applied["receipt"]["schema"] == RECEIPT_SCHEMA
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["source_context"]["timing_action"] == "preserve_symbolic_beats"
    assert len(fake.writes) == 2

    replay = service.execute_create(proposal, confirm_token=proposal["confirmation_token"], session_id="midi-service")
    assert replay["ok"] is False
    assert len(fake.writes) == 2

    undo_proposed = service.propose_undo(applied["receipt"], session_id="midi-undo")
    assert undo_proposed["ok"]
    undone = service.execute_remove(
        undo_proposed["proposal"],
        confirm_token=undo_proposed["proposal"]["confirmation_token"],
        session_id="midi-undo",
    )
    assert undone["ok"] is True
    assert fake.get_midi_clip_state(1, 0)["has_clip"] is False


def test_midi_clip_creation_reconciles_lost_note_acknowledgement() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service, "midi-note-ack")
    original_add = fake.add_midi_notes

    def add_then_lose_ack(track_index: int, clip_slot_index: int, notes: list[dict]) -> bool:
        original_add(track_index, clip_slot_index, notes)
        raise TimeoutError("note acknowledgement lost")

    fake.add_midi_notes = add_then_lose_ack
    result = service.execute_create(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-note-ack",
    )

    assert result["ok"] is True
    assert result["receipt"]["verified"] is True
    assert result["receipt"]["write_acknowledgement"] == "unacknowledged_write_reconciled"
    assert result["receipt"]["retry_safe"] == "safe"
    assert result["receipt"]["readback"]["notes"] == _notes()


def test_midi_clip_creation_marks_partial_note_write_for_inspection() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service, "midi-note-partial")
    original_add = fake.add_midi_notes

    def add_partial_then_fail(track_index: int, clip_slot_index: int, notes: list[dict]) -> bool:
        original_add(track_index, clip_slot_index, notes[:1])
        return False

    fake.add_midi_notes = add_partial_then_fail
    result = service.execute_create(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-note-partial",
    )

    assert result["ok"] is False
    assert result["receipt"]["retry_safe"] == "requires_inspection"
    assert result["receipt"]["readback"]["has_clip"] is True
    assert len(result["receipt"]["readback"]["notes"]) == 1


def test_midi_clip_creation_marks_lost_create_ack_for_inspection() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service, "midi-create-ack")
    original_create = fake.create_midi_clip

    def create_then_lose_ack(track_index: int, clip_slot_index: int, length: float) -> bool:
        original_create(track_index, clip_slot_index, length)
        raise TimeoutError("create acknowledgement lost")

    fake.create_midi_clip = create_then_lose_ack
    result = service.execute_create(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-create-ack",
    )

    assert result["ok"] is False
    assert result["receipt"]["retry_safe"] == "requires_inspection"
    assert result["receipt"]["readback"]["has_clip"] is True
    assert not any(write[0] == "add_notes" for write in fake.writes)


def test_midi_clip_rejects_existing_slot_and_invalid_notes() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    fake.clips[(1, 0)] = {"has_clip": True, "is_midi_clip": True, "length": 4.0, "notes": _notes()}
    occupied = service.propose_create(
        track_index=1,
        track_name="Bass MIDI",
        clip_slot_index=0,
        length=4,
        notes=_notes(),
        session_id="occupied",
    )
    assert occupied["ok"] is False
    assert "already contains" in occupied["error"]

    invalid = service.propose_create(
        track_index=1,
        track_name="Bass MIDI",
        clip_slot_index=1,
        length=4,
        notes=[{"pitch": 128, "start_time": 0, "duration": 1, "velocity": 100}],
        session_id="invalid",
    )
    assert invalid["ok"] is False
    assert "pitch" in invalid["error"]


def test_midi_clip_stale_track_is_rejected_without_a_write() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service, "midi-stale")
    fake.state["tracks"][0]["name"] = "Renamed Bass"
    result = service.execute_create(proposal, confirm_token=proposal["confirmation_token"], session_id="midi-stale")
    assert result["ok"] is False
    assert "changed" in result["error"]
    assert fake.writes == []


def test_midi_clip_undo_rechecks_track_identity_before_proposal_and_delete() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service, "midi-undo-identity")
    applied = service.execute_create(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-undo-identity",
    )
    assert applied["ok"] is True
    receipt = applied["receipt"]

    fake.state["tracks"][0]["name"] = "Replacement Bass"
    stale_proposal = service.propose_undo(receipt, session_id="midi-undo-identity-stale")
    assert stale_proposal["ok"] is False
    assert "changed" in stale_proposal["error"]
    assert fake.writes == [("create", (1, 0, 4.0)), ("add_notes", _notes())]

    fake.state["tracks"][0]["name"] = "Bass MIDI"
    undo = service.propose_undo(receipt, session_id="midi-undo-identity-fresh")
    assert undo["ok"] is True
    fake.state["tracks"][0]["name"] = "Replacement Bass"
    result = service.execute_remove(
        undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        session_id="midi-undo-identity-fresh",
    )
    assert result["ok"] is False
    assert "changed" in result["error"]
    assert not any(write[0] == "delete" for write in fake.writes)


def test_midi_clip_source_context_is_bound_to_confirmation() -> None:
    fake = FakeMidiLive()
    service = MidiClipActionService(fake)
    proposal = _proposal(service, "midi-context-bound")
    proposal["source_context"]["live_tempo_bpm"] = 121.0
    result = service.execute_create(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="midi-context-bound",
    )
    assert result["ok"] is False
    assert "mismatched" in result["error"]
    assert fake.writes == []


def test_midi_clip_update_replaces_notes_with_verified_identity_bound_undo() -> None:
    fake = FakeMidiLive()
    fake.clips[(1, 0)] = {"has_clip": True, "is_midi_clip": True, "length": 4.0, "notes": _notes()}
    service = MidiClipActionService(fake)
    replacement = [{"pitch": 48, "start_time": 2.0, "duration": 1.0, "velocity": 100, "mute": False}]

    proposed = service.propose_update(
        track_index=1, track_name="Bass MIDI", clip_slot_index=0,
        notes=replacement, session_id="midi-update",
        source_receipt_id="receipt-audition-1",
        source_artifact_sha256="sha256:" + ("b" * 64),
        source_artifact_id="audiogen-midi-revision-1",
        source_context=_context(),
    )
    assert proposed["ok"] is True
    assert proposed["proposal"]["schema"] == UPDATE_PROPOSAL_SCHEMA
    assert proposed["proposal"]["source_receipt_id"] == "receipt-audition-1"
    assert proposed["proposal"]["source_artifact_id"] == "audiogen-midi-revision-1"
    assert proposed["proposal"]["source_context"]["live_tempo_bpm"] == 120.0
    assert fake.writes == []

    applied = service.execute_update(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="midi-update",
    )
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["source_artifact_sha256"] == "sha256:" + ("b" * 64)
    assert applied["receipt"]["source_receipt_id"] == "receipt-audition-1"
    assert fake.get_midi_clip_state(1, 0)["notes"] == replacement
    assert fake.writes == [("remove_notes", (1, 0)), ("add_notes", replacement)]

    undo = service.propose_undo(applied["receipt"], session_id="midi-update-undo")
    assert undo["ok"] is True
    restored = service.execute_update(
        undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        session_id="midi-update-undo",
    )
    assert restored["ok"] is True
    assert fake.get_midi_clip_state(1, 0)["notes"] == _notes()


def test_midi_clip_update_rejects_stale_notes_without_writing() -> None:
    fake = FakeMidiLive()
    fake.clips[(1, 0)] = {"has_clip": True, "is_midi_clip": True, "length": 4.0, "notes": _notes()}
    service = MidiClipActionService(fake)
    proposed = service.propose_update(
        track_index=1, track_name="Bass MIDI", clip_slot_index=0,
        notes=[{"pitch": 50, "start_time": 0.0, "duration": 1.0, "velocity": 90}],
        session_id="midi-update-stale",
    )
    assert proposed["ok"] is True
    fake.clips[(1, 0)]["notes"][0]["velocity"] = 80

    result = service.execute_update(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="midi-update-stale",
    )
    assert result["ok"] is False
    assert "changed" in result["error"]
    assert fake.writes == []


def test_midi_clip_update_can_clear_notes_and_restore_them() -> None:
    fake = FakeMidiLive()
    original = _notes()
    fake.clips[(1, 0)] = {"has_clip": True, "is_midi_clip": True, "length": 4.0, "notes": original}
    service = MidiClipActionService(fake)
    proposed = service.propose_update(
        track_index=1, track_name="Bass MIDI", clip_slot_index=0,
        notes=[], session_id="midi-clear",
    )
    assert proposed["ok"] is True

    applied = service.execute_update(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="midi-clear",
    )
    assert applied["ok"] is True
    assert fake.get_midi_clip_state(1, 0)["notes"] == []

    undo = service.propose_undo(applied["receipt"], session_id="midi-clear-undo")
    assert undo["ok"] is True
    restored = service.execute_update(
        undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        session_id="midi-clear-undo",
    )
    assert restored["ok"] is True
    assert fake.get_midi_clip_state(1, 0)["notes"] == original

from __future__ import annotations

from copy import deepcopy

from kenn.core.clip_audition_service import ClipAuditionActionService, clip_fingerprint


class FakeLive:
    def __init__(self) -> None:
        self.clip = {
            "success": True,
            "track_index": 0,
            "clip_slot_index": 0,
            "has_clip": True,
            "is_midi_clip": True,
            "length": 4.0,
            "notes": [{"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 100, "mute": False}],
        }
        self.playing = False
        self.triggered = False
        self.transport_playing = False
        self.writes: list[tuple[str, int, int]] = []

    def query_session_topology(self) -> dict:
        return {"status": "connected", "tempo": 120.0, "tracks": [{"index": 0, "name": "1-MIDI", "devices": []}]}

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
        return deepcopy(self.clip)

    def get_clip_playback_state(self, track_index: int, clip_slot_index: int) -> dict:
        return {
            "success": True,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "is_playing": self.playing,
            "is_triggered": self.triggered,
        }

    def launch_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("fire", track_index, clip_slot_index))
        self.playing = True
        self.triggered = False
        self.transport_playing = True
        return True

    def stop_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("stop", track_index, clip_slot_index))
        self.playing = False
        self.triggered = False
        self.transport_playing = False
        return True

    def get_transport_state(self) -> dict:
        return {"success": True, "is_playing": self.transport_playing}


class ClipReadbackRaceLive(FakeLive):
    """Live double where clip flags clear before transport readback."""

    def launch_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("fire", track_index, clip_slot_index))
        self.playing = False
        self.triggered = False
        self.transport_playing = True
        return True


def test_audition_requires_confirmation_and_verifies_start_and_stop() -> None:
    live = FakeLive()
    service = ClipAuditionActionService(live)
    proposed = service.propose(track_index=0, track_name="1-MIDI", clip_slot_index=0, session_id="audition-test")
    assert proposed["ok"] is True
    proposal = proposed["proposal"]
    assert proposal["schema"] == "kenn.ableton_clip_audition_proposal.v1"
    assert live.writes == []

    applied = service.execute(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="audition-test",
        idempotency_key="audition-apply-1",
    )
    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert live.writes == [("fire", 0, 0)]

    journal_safe_receipt = deepcopy(applied["receipt"])
    journal_safe_receipt.pop("clip_identity", None)
    undo = service.propose_undo(journal_safe_receipt, session_id="audition-test")
    assert undo["ok"] is True
    stopped = service.execute_stop(
        undo["proposal"],
        confirm_token=undo["proposal"]["confirmation_token"],
        session_id="audition-test",
        idempotency_key="audition-stop-1",
    )
    assert stopped["ok"] is True
    assert stopped["receipt"]["verified"] is True
    assert live.writes == [("fire", 0, 0), ("stop", 0, 0)]


def test_clip_fingerprint_is_stable_for_same_clip_state() -> None:
    live = FakeLive()
    first = clip_fingerprint(live.clip)
    reordered = deepcopy(live.clip)
    reordered["notes"] = list(reversed(reordered["notes"]))
    reordered["track_name"] = "ignored-metadata"
    assert first == clip_fingerprint(reordered)


def test_audition_receipt_carries_correlation_id_retry_safety_and_stage_timings() -> None:
    live = FakeLive()
    service = ClipAuditionActionService(live)
    proposed = service.propose(track_index=0, track_name="1-MIDI", clip_slot_index=0, session_id="audition-corr")
    proposal = proposed["proposal"]
    applied = service.execute(
        proposal, confirm_token=proposal["confirmation_token"], session_id="audition-corr", correlation_id="caller-corr-audition",
    )
    assert applied["ok"] is True
    receipt = applied["receipt"]
    assert receipt["correlation_id"] == "caller-corr-audition"
    assert receipt["retry_safe"] == "safe"
    assert "write" in receipt["stage_timings_ms"]
    assert "readback" in receipt["stage_timings_ms"]

    journal_safe_receipt = deepcopy(receipt)
    journal_safe_receipt.pop("clip_identity", None)
    undo = service.propose_undo(journal_safe_receipt, session_id="audition-corr")
    stopped = service.execute_stop(
        undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="audition-corr", correlation_id="caller-corr-stop",
    )
    assert stopped["ok"] is True
    assert stopped["receipt"]["correlation_id"] == "caller-corr-stop"
    assert stopped["receipt"]["retry_safe"] == "safe"


def test_audition_rejects_changed_clip_without_sending_fire() -> None:
    live = FakeLive()
    service = ClipAuditionActionService(live)
    proposed = service.propose(track_index=0, track_name="1-MIDI", clip_slot_index=0, session_id="audition-stale")
    assert proposed["ok"] is True
    live.clip["notes"][0]["pitch"] = 61
    result = service.execute(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="audition-stale",
        idempotency_key="audition-stale-1",
    )
    assert result["ok"] is False
    assert "changed" in result["error"]
    assert live.writes == []


def test_audition_accepts_transport_corroboration_when_clip_flags_race() -> None:
    live = ClipReadbackRaceLive()
    service = ClipAuditionActionService(live)
    proposed = service.propose(track_index=0, track_name="1-MIDI", clip_slot_index=0, session_id="audition-race")
    assert proposed["ok"] is True
    assert proposed["proposal"]["transport_was_playing_before"] is False

    applied = service.execute(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="audition-race",
        idempotency_key="audition-race-1",
    )

    assert applied["ok"] is True
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["readback"]["transport_is_playing"] is True


def test_audition_does_not_use_transport_as_clip_proof_when_already_playing() -> None:
    live = ClipReadbackRaceLive()
    live.transport_playing = True
    service = ClipAuditionActionService(live)
    proposed = service.propose(track_index=0, track_name="1-MIDI", clip_slot_index=0, session_id="audition-race-playing")
    assert proposed["ok"] is True
    assert proposed["proposal"]["transport_was_playing_before"] is True

    applied = service.execute(
        proposed["proposal"],
        confirm_token=proposed["proposal"]["confirmation_token"],
        session_id="audition-race-playing",
        idempotency_key="audition-race-playing-1",
    )

    assert applied["ok"] is False
    assert applied["receipt"]["status"] == "failed_verification"

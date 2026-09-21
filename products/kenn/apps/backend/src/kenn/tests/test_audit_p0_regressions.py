"""P0 regression tests for defects found in the 2026-09-21 KENN product audit.

1. audiogen_artifacts._canonical_midi_notes recorded range errors but still
   appended the invalid note, leaking bad MIDI into artifacts.
2. LiveExecutor.undo_batch_action returned ok=True even when only some
   restore steps succeeded.
3. MidiClipActionService.propose_create accepted notes extending beyond the
   clip length (audiogen_artifacts enforced the bound; this path did not).
"""

from __future__ import annotations

from copy import deepcopy

from kenn.core.audiogen_artifacts import _canonical_midi_notes
from kenn.core.live_executor import LiveExecutor
from kenn.core.midi_clip_service import MidiClipActionService


def test_canonical_midi_notes_drops_invalid_notes_instead_of_leaking_them() -> None:
    raw = [
        {"pitch": 60, "start_time": 0.0, "duration": 1.0, "velocity": 100},
        {"pitch": 200, "start_time": 0.0, "duration": 1.0, "velocity": 100},
        {"pitch": 62, "start_time": -1.0, "duration": 1.0, "velocity": 100},
        {"pitch": 64, "start_time": 0.0, "duration": 0.0, "velocity": 100},
        {"pitch": 65, "start_time": 0.0, "duration": 1.0, "velocity": 0},
    ]
    notes, errors = _canonical_midi_notes(raw)
    assert len(errors) == 4
    assert [n["pitch"] for n in notes] == [60]
    assert all(0 <= n["pitch"] <= 127 for n in notes)
    assert all(1 <= n["velocity"] <= 127 for n in notes)


class _UndoStub:
    """Succeeds for restore_value != -1, fails otherwise."""

    def set_device_parameter(self, *args) -> bool:
        return args[3] != -1.0

    def get_device_parameters(self, track_idx: int, device_idx: int) -> dict:
        value = 1.0 if track_idx == 0 else -1.0
        return {"success": True, "parameters": [{"value": value}]}


def _undo_step(track_index: int, restore_value: float) -> dict:
    return {
        "track_index": track_index,
        "device_index": 0,
        "parameter_index": 0,
        "restore_value": restore_value,
    }


def test_undo_batch_action_reports_partial_failure_honestly() -> None:
    executor = LiveExecutor(osc_client=_UndoStub())
    payload = {
        "batch_id": "batch-1",
        "restore_steps": [_undo_step(0, 1.0), _undo_step(9, -1.0)],
    }
    result = executor.undo_batch_action(payload)
    assert result["ok"] is False
    assert result["status"] == "partially_undone"
    assert result["undone_steps"] == 1
    assert result["total_steps"] == 2


def test_undo_batch_action_reports_full_success() -> None:
    executor = LiveExecutor(osc_client=_UndoStub())
    payload = {
        "batch_id": "batch-2",
        "restore_steps": [_undo_step(0, 1.0)],
    }
    result = executor.undo_batch_action(payload)
    assert result["ok"] is True
    assert result["status"] == "undone"


class _FakeMidiLive:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tempo": 120.0,
            "tracks": [{"index": 1, "name": "Bass MIDI", "devices": []}],
        }
        self.clips: dict[tuple[int, int], dict] = {}

    def query_session_topology(self) -> dict:
        return deepcopy(self.state)

    def get_track_has_midi_input(self, track_index: int) -> bool:
        return True

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
        return {
            "success": True,
            "track_index": track_index,
            "clip_slot_index": clip_slot_index,
            "has_clip": False,
            "is_midi_clip": False,
            "length": 0.0,
            "notes": [],
        }


def test_propose_create_rejects_note_beyond_clip_length() -> None:
    service = MidiClipActionService(_FakeMidiLive())
    result = service.propose_create(
        track_index=1,
        clip_slot_index=0,
        track_name="Bass MIDI",
        length=4.0,
        notes=[{"pitch": 36, "start_time": 3.5, "duration": 1.0, "velocity": 110}],
    )
    assert result["ok"] is False
    assert "clip length" in result["error"]


def test_propose_create_accepts_note_ending_exactly_at_clip_length() -> None:
    service = MidiClipActionService(_FakeMidiLive())
    result = service.propose_create(
        track_index=1,
        clip_slot_index=0,
        track_name="Bass MIDI",
        length=4.0,
        notes=[{"pitch": 36, "start_time": 3.0, "duration": 1.0, "velocity": 110}],
    )
    assert result["ok"] is True

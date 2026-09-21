"""Unit and integration tests for multi-track gain staging and bus grouping."""

from __future__ import annotations

from copy import deepcopy
import pytest

from kenn.core.live_action_service import (
    LiveActionService,
    GAIN_STAGING_PROPOSAL_SCHEMA,
    GAIN_STAGING_RECEIPT_SCHEMA,
    BUS_ORGANIZATION_PROPOSAL_SCHEMA,
    BUS_ORGANIZATION_RECEIPT_SCHEMA,
)
from kenn.core.live_command import handle_command


class MultiTrackFakeLive:
    """Mock Ableton Live client with full multi-track volume and track creation support."""

    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tempo": 124.0,
            "is_playing": False,
            "selected_track_index": 0,
            "tracks": [
                {"index": 0, "name": "Kick", "volume": 0.85, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
                {"index": 1, "name": "Snare", "volume": 0.70, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
                {"index": 2, "name": "Sub Bass", "volume": 0.60, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
                {"index": 3, "name": "Lead Vox", "volume": 0.80, "pan": 0.0, "muted": False, "soloed": False, "armed": False, "devices": []},
            ],
            "scenes": [{"index": 0, "name": "Scene 1"}],
        }
        self.writes: list[tuple] = []
        self.fail_readback = False

    def query_session_state(self) -> dict:
        return deepcopy(self.state)

    def set_track_volume(self, index: int, volume: float) -> bool:
        self.writes.append(("set_track_volume", index, volume))
        if 0 <= index < len(self.state["tracks"]) and not self.fail_readback:
            self.state["tracks"][index]["volume"] = volume
        return True

    def set_track_name(self, index: int, name: str) -> bool:
        self.writes.append(("set_track_name", index, name))
        if 0 <= index < len(self.state["tracks"]):
            self.state["tracks"][index]["name"] = name
        return True

    def create_audio_track(self, insertion_index: int = -1) -> bool:
        self.writes.append(("create_audio_track", insertion_index))
        new_idx = len(self.state["tracks"])
        self.state["tracks"].append({
            "index": new_idx,
            "name": f"Track {new_idx + 1}",
            "volume": 0.85,
            "pan": 0.0,
            "muted": False,
            "soloed": False,
            "armed": False,
            "devices": [],
        })
        return True


def test_propose_gain_staging_offline() -> None:
    fake = MultiTrackFakeLive()
    fake.state["status"] = "offline"
    service = LiveActionService(fake)
    res = service.propose_gain_staging(target_headroom_db=-6.0, session_id="sess-offline")
    assert res["ok"] is False
    assert "offline" in res["error"]


def test_propose_gain_staging_success() -> None:
    fake = MultiTrackFakeLive()
    service = LiveActionService(fake)
    res = service.propose_gain_staging(target_headroom_db=-6.0, session_id="sess-gs-1")
    assert res["ok"] is True
    prop = res["proposal"]
    assert prop["schema"] == GAIN_STAGING_PROPOSAL_SCHEMA
    assert prop["action"] == "gain_stage_tracks"
    assert prop["track_count"] == 4
    assert len(prop["steps"]) == 4
    assert prop["requires_confirmation"] is True
    assert prop["confirmation_token"]
    assert prop["undo_available"] is True

    # Track 0: Kick was 0.85
    step0 = prop["steps"][0]
    assert step0["track_index"] == 0
    assert step0["track_name"] == "Kick"
    assert step0["before"] == 0.85
    assert step0["after"] < 0.85  # Target at -6 dB is lower than unity 0.85


def test_execute_gain_staging_and_readback() -> None:
    fake = MultiTrackFakeLive()
    service = LiveActionService(fake)
    proposed = service.propose_gain_staging(target_headroom_db=-6.0, session_id="sess-gs-exec")
    prop = proposed["proposal"]
    token = prop["confirmation_token"]

    result = service.execute(prop, confirm_token=token, session_id="sess-gs-exec")
    assert result["ok"] is True
    receipt = result["receipt"]
    assert receipt["schema"] == GAIN_STAGING_RECEIPT_SCHEMA
    assert receipt["status"] == "applied"
    assert receipt["verified"] is True
    assert len(receipt["step_receipts"]) == 4

    # Verify that fake live's tracks actually received the new target volume
    state = fake.query_session_state()
    target_vol = prop["target_normalized"]
    for t in state["tracks"]:
        assert abs(t["volume"] - target_vol) < 1e-4


def test_gain_staging_undo_restores_volumes() -> None:
    fake = MultiTrackFakeLive()
    service = LiveActionService(fake)

    # Initial volumes: Kick=0.85, Snare=0.70, Bass=0.60, Vox=0.80
    proposed = service.propose_gain_staging(target_headroom_db=-6.0, session_id="sess-gs-undo")
    executed = service.execute(proposed["proposal"], confirm_token=proposed["proposal"]["confirmation_token"], session_id="sess-gs-undo")
    assert executed["ok"] is True
    receipt = executed["receipt"]

    # Propose undo
    undo_proposed = service.propose_undo(receipt, session_id="sess-gs-undo-2")
    assert undo_proposed["ok"] is True
    undo_prop = undo_proposed["proposal"]
    assert undo_prop["schema"] == GAIN_STAGING_PROPOSAL_SCHEMA

    # Execute undo
    undo_executed = service.execute(undo_prop, confirm_token=undo_prop["confirmation_token"], session_id="sess-gs-undo-2")
    assert undo_executed["ok"] is True

    # Assert tracks restored to initial volumes
    state = fake.query_session_state()
    assert abs(state["tracks"][0]["volume"] - 0.85) < 1e-4
    assert abs(state["tracks"][1]["volume"] - 0.70) < 1e-4
    assert abs(state["tracks"][2]["volume"] - 0.60) < 1e-4
    assert abs(state["tracks"][3]["volume"] - 0.80) < 1e-4


def test_propose_and_execute_track_grouping() -> None:
    fake = MultiTrackFakeLive()
    service = LiveActionService(fake)

    # Group drums tracks (Kick & Snare)
    proposed = service.propose_track_grouping(group_type="drums", session_id="sess-group-1")
    assert proposed["ok"] is True
    prop = proposed["proposal"]
    assert prop["schema"] == BUS_ORGANIZATION_PROPOSAL_SCHEMA
    assert prop["bus_name"] == "Drums Bus"
    assert len(prop["member_tracks"]) == 2  # Kick and Snare

    # Execute track grouping
    executed = service.execute(prop, confirm_token=prop["confirmation_token"], session_id="sess-group-1")
    assert executed["ok"] is True
    receipt = executed["receipt"]
    assert receipt["schema"] == BUS_ORGANIZATION_RECEIPT_SCHEMA
    assert receipt["status"] == "applied"
    assert receipt["verified"] is True
    assert receipt["bus_name"] == "Drums Bus"

    # Verify a new track was appended and named Drums Bus
    state = fake.query_session_state()
    assert len(state["tracks"]) == 5
    assert state["tracks"][4]["name"] == "Drums Bus"


def test_handle_command_natural_language_gain_staging() -> None:
    fake = MultiTrackFakeLive()
    service = LiveActionService(fake)

    # 1. Propose via natural language
    res = handle_command("gain stage all tracks to -6 dB", session_id="sess-nl-gs", service=service)
    assert res["status"] == "confirmation_required"
    assert res["confirmation_required"] is True
    prop = res["proposal"]
    assert prop["schema"] == GAIN_STAGING_PROPOSAL_SCHEMA
    assert "auto gain-stage 4 session track(s) to -6.0 dB" in res["answer"]

    # 2. Confirm and execute
    token = prop["confirmation_token"]
    exec_res = handle_command(
        "",
        session_id="sess-nl-gs",
        service=service,
        proposal=prop,
        confirm_token=token,
    )
    assert exec_res["status"] == "applied"
    assert exec_res["changed"] is True
    assert exec_res["receipt"]["verified"] is True

    # 3. Undo via receipt
    undo_res = service.propose_undo(exec_res["receipt"], session_id="sess-nl-undo")
    assert undo_res["ok"] is True
    undo_exec = service.execute(undo_res["proposal"], confirm_token=undo_res["proposal"]["confirmation_token"], session_id="sess-nl-undo")
    assert undo_exec["ok"] is True


def test_handle_command_natural_language_bus_organization() -> None:
    fake = MultiTrackFakeLive()
    service = LiveActionService(fake)

    # 1. Propose via natural language
    res = handle_command("organize tracks into buses", session_id="sess-nl-bus", service=service)
    assert res["status"] == "confirmation_required"
    prop = res["proposal"]
    assert prop["schema"] == BUS_ORGANIZATION_PROPOSAL_SCHEMA

    # 2. Confirm and execute
    exec_res = handle_command(
        "",
        session_id="sess-nl-bus",
        service=service,
        proposal=prop,
        confirm_token=prop["confirmation_token"],
    )
    assert exec_res["status"] == "applied"
    assert exec_res["changed"] is True
    assert exec_res["receipt"]["verified"] is True

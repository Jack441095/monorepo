"""Unit tests for Tier-3 Ableton Live 12 Full Control Capabilities."""

from __future__ import annotations

import pytest
from typing import Any, Dict, List

from kenn.core.live_action_service import (
    LiveActionService,
    TRACK_ROUTING_PROPOSAL_SCHEMA,
    TRACK_ROUTING_RECEIPT_SCHEMA,
    TRACK_FREEZE_PROPOSAL_SCHEMA,
    TRACK_FREEZE_RECEIPT_SCHEMA,
    RACK_VARIATION_PROPOSAL_SCHEMA,
    RACK_VARIATION_RECEIPT_SCHEMA,
)


class FakeTier3LiveClient:
    def __init__(self):
        self.output_routings = {0: "Master", 1: "Master", 2: "Master"}
        self.input_routings = {0: "Ext: In 1", 1: "Ext. In 1", 2: "Ext. In 1"}
        self.frozen_tracks = {0: False, 1: False, 2: False}
        self.rack_variations = {}
        self.recalled_variations = {}
        self.meters = {
            0: {"output_meter_left": 0.85, "output_meter_right": 0.82},
            1: {"output_meter_left": 0.65, "output_meter_right": 0.65},
        }

    def set_track_output_routing(self, track_index: int, routing_type: str) -> bool:
        self.output_routings[track_index] = routing_type
        return True

    def set_track_input_routing(self, track_index: int, routing_type: str) -> bool:
        self.input_routings[track_index] = routing_type
        return True

    def set_track_freeze(self, track_index: int, frozen: bool) -> bool:
        self.frozen_tracks[track_index] = bool(frozen)
        return True

    def store_rack_variation(self, track_index: int, device_index: int) -> bool:
        key = (track_index, device_index)
        self.rack_variations[key] = self.rack_variations.get(key, 0) + 1
        return True

    def recall_rack_variation(self, track_index: int, device_index: int, variation_index: int) -> bool:
        self.recalled_variations[(track_index, device_index)] = variation_index
        return True

    def get_track_realtime_meters(self, track_index: int) -> dict[str, Any]:
        data = self.meters.get(track_index, {"output_meter_left": 0.0, "output_meter_right": 0.0})
        return {"track_index": track_index, **data}


def test_track_routing_flow():
    fake = FakeTier3LiveClient()
    service = LiveActionService(fake)

    # 1. Output routing proposal
    prop_res = service.propose_track_routing(
        track_index=1,
        routing_type="Drum Bus",
        direction="output",
        session_id="route-sess-1",
    )
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["schema"] == TRACK_ROUTING_PROPOSAL_SCHEMA
    token = proposal["confirmation_token"]

    # Rejects invalid token
    bad_exec = service.execute_track_routing(proposal, confirm_token="bad-token", session_id="route-sess-1")
    assert bad_exec["ok"] is False

    # Executes with valid token
    exec_res = service.execute_track_routing(proposal, confirm_token=token, session_id="route-sess-1")
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == TRACK_ROUTING_RECEIPT_SCHEMA
    assert receipt["verified"] is True
    assert fake.output_routings[1] == "Drum Bus"

    # Input routing proposal
    in_prop = service.propose_track_routing(
        track_index=2,
        routing_type="Ext. In 2",
        direction="input",
        session_id="route-sess-2",
    )
    in_exec = service.execute_track_routing(
        in_prop["proposal"],
        confirm_token=in_prop["proposal"]["confirmation_token"],
        session_id="route-sess-2",
    )
    assert in_exec["ok"] is True
    assert fake.input_routings[2] == "Ext. In 2"


def test_track_freeze_flow():
    fake = FakeTier3LiveClient()
    service = LiveActionService(fake)

    # Propose freeze
    prop_res = service.propose_track_freeze(
        track_index=0,
        freeze=True,
        session_id="freeze-sess-1",
    )
    assert prop_res["ok"] is True
    proposal = prop_res["proposal"]
    assert proposal["schema"] == TRACK_FREEZE_PROPOSAL_SCHEMA

    # Execute freeze
    exec_res = service.execute_track_freeze(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="freeze-sess-1",
    )
    assert exec_res["ok"] is True
    assert exec_res["receipt"]["schema"] == TRACK_FREEZE_RECEIPT_SCHEMA
    assert fake.frozen_tracks[0] is True

    # Propose and execute unfreeze
    unfreeze_prop = service.propose_track_freeze(
        track_index=0,
        freeze=False,
        session_id="freeze-sess-2",
    )
    unfreeze_exec = service.execute_track_freeze(
        unfreeze_prop["proposal"],
        confirm_token=unfreeze_prop["proposal"]["confirmation_token"],
        session_id="freeze-sess-2",
    )
    assert unfreeze_exec["ok"] is True
    assert fake.frozen_tracks[0] is False


def test_rack_variation_flow():
    fake = FakeTier3LiveClient()
    service = LiveActionService(fake)

    # Propose store variation
    store_prop = service.propose_rack_variation(
        track_index=0,
        device_index=0,
        sub_action="store",
        session_id="var-sess-1",
    )
    assert store_prop["ok"] is True
    assert store_prop["proposal"]["schema"] == RACK_VARIATION_PROPOSAL_SCHEMA

    store_exec = service.execute_rack_variation(
        store_prop["proposal"],
        confirm_token=store_prop["proposal"]["confirmation_token"],
        session_id="var-sess-1",
    )
    assert store_exec["ok"] is True
    assert store_exec["receipt"]["schema"] == RACK_VARIATION_RECEIPT_SCHEMA
    assert fake.rack_variations.get((0, 0)) == 1

    # Propose recall variation
    recall_prop = service.propose_rack_variation(
        track_index=0,
        device_index=0,
        sub_action="recall",
        variation_index=2,
        session_id="var-sess-2",
    )
    assert recall_prop["ok"] is True
    recall_exec = service.execute_rack_variation(
        recall_prop["proposal"],
        confirm_token=recall_prop["proposal"]["confirmation_token"],
        session_id="var-sess-2",
    )
    assert recall_exec["ok"] is True
    assert fake.recalled_variations.get((0, 0)) == 2


def test_read_realtime_meters():
    fake = FakeTier3LiveClient()
    service = LiveActionService(fake)

    meters = service.read_track_realtime_meters(0)
    assert meters["track_index"] == 0
    assert meters["output_meter_left"] == 0.85
    assert meters["output_meter_right"] == 0.82


"""Unit tests for KENN Ableton Live 12 100% Full Control Expansion.

Tests the final 4 Tier 1 capabilities:
1. Clip Modulation Envelopes (MPE pitch bend, pan, timbre)
2. Audio Clip Warp Modes (Beats, Tones, Texture, Re-Pitch, Complex, Complex Pro)
3. Max for Live Device Parameter Discovery
4. Master Chain Limiter Ceiling Hardware Safety Lock (<= -0.3 dBFS)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_SOURCE = str(Path(__file__).resolve().parents[2])
if _SOURCE not in sys.path:
    sys.path.insert(0, _SOURCE)

import time
import pytest
from unittest.mock import MagicMock

from kenn.core.live_action_service import (
    LiveActionService,
    CLIP_MODULATION_PROPOSAL_SCHEMA,
    CLIP_MODULATION_RECEIPT_SCHEMA,
    CLIP_WARP_MODE_PROPOSAL_SCHEMA,
    CLIP_WARP_MODE_RECEIPT_SCHEMA,
    MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA,
    MASTER_LIMITER_LOCK_RECEIPT_SCHEMA,
)


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.send.return_value = {"success": True}
    return client


@pytest.fixture
def action_service(mock_client):
    service = LiveActionService()
    service.client = mock_client
    return service


def test_clip_modulation_proposal_and_execution(action_service, mock_client):
    """Verify clip modulation proposal creation and atomic execution."""
    points = [{"time": 0.0, "value": 0.0}, {"time": 1.0, "value": 0.5}]
    res = action_service.propose_clip_modulation(
        track_index=2,
        clip_slot_index=0,
        envelope_type="pitch_bend",
        points=points,
        session_id="test-session",
    )
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["schema"] == CLIP_MODULATION_PROPOSAL_SCHEMA
    assert proposal["track_index"] == 2
    assert proposal["clip_slot_index"] == 0
    assert proposal["envelope_type"] == "pitch_bend"
    assert len(proposal["points"]) == 2

    # Execute with confirmation token
    token = proposal["confirmation_token"]
    exec_res = action_service.execute_clip_modulation(
        proposal=proposal,
        confirm_token=token,
        session_id="test-session",
    )
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == CLIP_MODULATION_RECEIPT_SCHEMA
    assert receipt["verified"] is True
    assert receipt["points_written"] == 2
    mock_client.send.assert_called_with("/live/clip/set_modulation", [2, 0, "pitch_bend", points])


def test_clip_warp_mode_proposal_and_execution(action_service, mock_client):
    """Verify audio clip warp mode proposal and execution."""
    res = action_service.propose_clip_warp_mode(
        track_index=1,
        clip_slot_index=0,
        warp_mode="complex_pro",
        session_id="test-session",
    )
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["schema"] == CLIP_WARP_MODE_PROPOSAL_SCHEMA
    assert proposal["warp_mode"] == 5  # complex_pro mapped to 5

    token = proposal["confirmation_token"]
    exec_res = action_service.execute_clip_warp_mode(
        proposal=proposal,
        confirm_token=token,
        session_id="test-session",
    )
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == CLIP_WARP_MODE_RECEIPT_SCHEMA
    assert receipt["warp_mode"] == 5
    mock_client.send.assert_called_with("/live/clip/set/warp_mode", [1, 0, 5])


def test_read_m4l_device_parameters(action_service, mock_client):
    """Verify Max for Live device parameter introspection."""
    mock_client.send.return_value = {
        "success": True,
        "track_index": 3,
        "device_index": 1,
        "device_name": "LFO",
        "is_m4l": True,
        "parameters": [
            {"index": 0, "name": "Device On", "value": 1.0, "is_quantized": True},
            {"index": 1, "name": "Frequency", "value": 0.25, "min": 0.0, "max": 1.0},
        ],
    }

    res = action_service.read_m4l_device_parameters(track_index=3, device_index=1)
    assert res["success"] is True
    assert res["is_m4l"] is True
    assert len(res["parameters"]) == 2
    mock_client.send.assert_called_with("/live/m4l/get/parameters", [3, 1])


def test_master_limiter_safety_lock(action_service, mock_client):
    """Verify master chain limiter ceiling proposal and strict hardware clamping."""
    # Attempting to set ceiling to +0.5 dBFS must be strictly clamped to <= -0.3 dBFS
    res = action_service.propose_master_limiter_lock(
        ceiling_dbfs=0.5,
        session_id="test-session",
    )
    assert res["ok"] is True
    proposal = res["proposal"]
    assert proposal["schema"] == MASTER_LIMITER_LOCK_PROPOSAL_SCHEMA
    # Safety policy clamping
    assert proposal["ceiling_dbfs"] == -0.3

    token = proposal["confirmation_token"]
    exec_res = action_service.execute_master_limiter_lock(
        proposal=proposal,
        confirm_token=token,
        session_id="test-session",
    )
    assert exec_res["ok"] is True
    receipt = exec_res["receipt"]
    assert receipt["schema"] == MASTER_LIMITER_LOCK_RECEIPT_SCHEMA
    assert receipt["ceiling_dbfs"] == -0.3
    assert receipt["safety_enforced"] is True
    mock_client.send.assert_called_with("/live/master/enforce_safety_limiter", [-0.3])


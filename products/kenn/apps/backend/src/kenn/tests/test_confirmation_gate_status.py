"""Tests ensuring safety confirmation gates return 'requires_confirmation' status rather than 'failed'."""

import pytest
from kenn.core.live_action_service import LiveActionService
from kenn.core.live_command import handle_command
from kenn.core.clip_audition_service import ClipAuditionActionService
from kenn.core.clip_duplication_service import ClipDuplicationActionService
from kenn.core.clip_rename_service import ClipRenameActionService


def test_unconfirmed_device_insertion_returns_requires_confirmation_status():
    service = LiveActionService()
    proposal = {
        "schema": "kenn.ableton_device_insertion_proposal.v1",
        "action": "insert_device",
        "track_index": 3,
        "track_name": "4-Audio",
        "device_name": "EQ Eight",
        "insertion_index": 0,
        "before_device_fingerprint": "",
        "action_id": "test-action-id",
        "requires_confirmation": True,
        "confirmation_token": "token-xyz",
    }
    # Attempting to execute with wrong/missing confirm token
    res = service.execute_device_insertion(proposal, confirm_token="wrong-token", session_id="test-session")
    assert res.get("ok") is False
    assert res.get("status") == "requires_confirmation"
    assert "Explicit confirmation is required" in res.get("error", "")


def test_live_command_unconfirmed_proposal_reports_requires_confirmation():
    proposal = {
        "schema": "kenn.ableton_device_insertion_proposal.v1",
        "action": "insert_device",
        "track_index": 3,
        "track_name": "4-Audio",
        "device_name": "EQ Eight",
        "insertion_index": 0,
        "before_device_fingerprint": "",
        "action_id": "test-action-id-2",
        "requires_confirmation": True,
        "confirmation_token": "token-abc",
    }
    res = handle_command(
        "",
        session_id="test-session",
        proposal=proposal,
        confirm_token="",  # unconfirmed
        idempotency_key="test-key-2",
    )
    # Must be 'requires_confirmation', NEVER 'failed'
    assert res.get("status") == "requires_confirmation"
    assert res.get("changed") is False
    assert "Explicit confirmation is required" in res.get("answer", "")
    assert res.get("lifecycle", {}).get("stage") == "awaiting_confirmation"


def test_clip_audition_gate_status():
    service = ClipAuditionActionService()
    proposal = {
        "schema": "kenn.ableton_clip_audition_proposal.v1",
        "action": "audition_clip",
        "track_index": 0,
        "clip_slot_index": 0,
        "requires_confirmation": True,
        "confirmation_token": "token-audit",
    }
    res = service.execute(proposal, confirm_token="wrong", session_id="s1")
    assert res.get("ok") is False
    assert res.get("status") == "requires_confirmation"
    assert "Explicit confirmation is required" in res.get("error", "")


def test_clip_duplication_gate_status():
    service = ClipDuplicationActionService()
    proposal = {
        "schema": "kenn.ableton_clip_duplication_proposal.v1",
        "action": "duplicate_clip",
        "source_track_index": 0,
        "source_clip_slot_index": 0,
        "target_track_index": 0,
        "target_clip_slot_index": 1,
        "requires_confirmation": True,
        "confirmation_token": "token-dup",
    }
    res = service.execute(proposal, confirm_token="wrong", session_id="s1")
    assert res.get("ok") is False
    assert res.get("status") == "requires_confirmation"
    assert "Explicit confirmation is required" in res.get("error", "")

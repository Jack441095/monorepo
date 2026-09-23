"""Bounded multi-turn context for Live command planning."""

from __future__ import annotations

from kenn.core.session_context import (
    live_conversation_context,
    preprocess_live_command,
    record_live_exchange,
)


def test_repeat_and_anaphora_resolve_from_last_discussed_entities() -> None:
    session_id = "context-repeat"
    record_live_exchange(
        session_id=session_id,
        command="mute the Bass track",
        result={
            "status": "confirmation_required",
            "intent": {
                "action": "set_mute",
                "track": {"index": 1, "name": "Bass"},
                "device": {"index": 0, "name": "Compressor"},
                "parameter": {"name": "Threshold"},
            },
        },
    )

    repeated, repeated_meta = preprocess_live_command("again", session_id=session_id)
    assert repeated == "mute the Bass track"
    assert repeated_meta["resolution"] == "repeat_last_action"

    resolved, meta = preprocess_live_command("make it softer", session_id=session_id)
    assert resolved == "make Threshold on Compressor on Bass softer"
    assert meta["resolution"] == "contextual_direction_requires_value"
    assert meta["target_kind"] == "parameter"
    assert meta["parameter"] == "Threshold"
    assert meta["device"] == "Compressor"
    assert meta["track"] == "Bass"
    assert meta["relative_amount_provided"] is False


def test_device_proposal_parameter_alias_is_retained_for_follow_up_context() -> None:
    session_id = "context-proposal-parameter"
    record_live_exchange(
        session_id=session_id,
        command="set Compressor Output on Vocal to -3 dB",
        result={
            "status": "confirmation_required",
            "proposal": {
                "action": "set_device_parameter",
                "track_name": "Vocal",
                "device_name": "Compressor",
                "parameter": "Output",
            },
        },
    )

    context = live_conversation_context(session_id)
    resolved, metadata = preprocess_live_command("make it louder by 2 dB", session_id=session_id)

    assert context["last_parameter"] == "Output"
    assert context["exchanges"][-1]["parameter"] == "Output"
    assert resolved == "make Output on Compressor on Vocal louder by 2 dB"
    assert metadata["resolution"] == "contextual_direction_requires_value"
    assert metadata["relative_amount_provided"] is True


def test_newer_track_action_supersedes_an_older_device_parameter_target() -> None:
    session_id = "context-newer-track-target"
    record_live_exchange(
        session_id=session_id,
        command="set Compressor Output on Vocal to -3 dB",
        result={
            "status": "confirmation_required",
            "proposal": {
                "action": "set_device_parameter",
                "track_name": "Vocal",
                "device_name": "Compressor",
                "parameter": "Output",
            },
        },
    )
    record_live_exchange(
        session_id=session_id,
        command="mute Bass",
        result={
            "status": "confirmation_required",
            "intent": {"action": "set_mute", "track": {"name": "Bass"}},
            "proposal": {"action": "set_mute", "track_name": "Bass", "parameter": "muted"},
        },
    )

    context = live_conversation_context(session_id)
    resolved, metadata = preprocess_live_command("make it louder", session_id=session_id)

    assert context["last_device"] == ""
    assert context["last_parameter"] == ""
    assert resolved == "make Bass louder"
    assert metadata["target_kind"] == "track"


def test_explicit_different_directional_target_is_not_overridden_by_old_context() -> None:
    session_id = "context-explicit-different-target"
    record_live_exchange(
        session_id=session_id,
        command="set Compressor Output on Bass to -3 dB",
        result={
            "status": "confirmation_required",
            "proposal": {
                "action": "set_device_parameter",
                "track_name": "Bass",
                "device_name": "Compressor",
                "parameter": "Output",
            },
        },
    )

    resolved, metadata = preprocess_live_command("make Vocal louder", session_id=session_id)

    assert resolved == "make Vocal louder"
    assert metadata["resolution"] == "none"


def test_context_ring_buffer_keeps_only_last_ten_exchanges() -> None:
    session_id = "context-ring"
    for index in range(14):
        record_live_exchange(
            session_id=session_id,
            command=f"command {index}",
            result={"status": "inspected", "intent": {"action": "inspect_tracks"}},
        )

    context = live_conversation_context(session_id)
    assert len(context["exchanges"]) == 10
    assert context["exchanges"][0]["command"] == "command 4"
    assert context["exchanges"][-1]["command"] == "command 13"


def test_bare_undo_is_marked_for_last_receipt_resolution() -> None:
    resolved, metadata = preprocess_live_command("undo that", session_id="context-undo")

    assert resolved == "undo"
    assert metadata["resolution"] == "undo_last_receipt"


def test_explicit_track_correction_retargets_the_previous_command() -> None:
    session_id = "context-correct-track"
    record_live_exchange(
        session_id=session_id,
        command="mute track 2",
        result={
            "status": "confirmation_required",
            "intent": {"action": "set_mute", "track": {"index": 1, "name": "Drums"}},
        },
    )

    resolved, metadata = preprocess_live_command("I meant track 3", session_id=session_id)

    assert resolved == "mute track 3"
    assert metadata["resolution"] == "corrected_track_target"
    assert metadata["corrected_target"] == "track 3"


def test_explicit_device_correction_retargets_only_the_known_device() -> None:
    session_id = "context-correct-device"
    record_live_exchange(
        session_id=session_id,
        command="add Compressor to Vocals and set Threshold to -20 dB",
        result={
            "status": "confirmation_required",
            "proposal": {
                "action": "insert_device_with_parameter",
                "track_name": "Vocals",
                "device_name": "Compressor",
                "parameter_name": "Threshold",
            },
        },
    )

    resolved, metadata = preprocess_live_command("not the compressor, the EQ", session_id=session_id)

    assert resolved == "add EQ to Vocals and set Threshold to -20 dB"
    assert metadata["resolution"] == "corrected_device_target"
    assert metadata["corrected_target"] == "EQ"


def test_other_one_is_never_guessed_from_context() -> None:
    resolved, metadata = preprocess_live_command("no, the other one", session_id="context-other-one")

    assert resolved == "no, the other one"
    assert metadata == {
        "resolution": "correction_requires_clarification",
        "original": "no, the other one",
        "reason": "other_one_is_not_an_exact_identity",
    }

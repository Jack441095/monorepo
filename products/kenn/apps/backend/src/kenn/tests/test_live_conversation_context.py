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
    assert resolved == "make Compressor softer on Bass"
    assert meta["resolution"] == "anaphora"


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

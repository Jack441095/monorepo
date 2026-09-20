from __future__ import annotations

from kenn.core import session_memory
from kenn.core.audition_feedback import build_audition_feedback
from kenn.core.audition_revision import build_audition_revision_brief, validate_revision_brief


def _receipt() -> dict:
    return {
        "schema": "kenn.ableton_clip_audition_receipt.v1",
        "receipt_id": "receipt-audition-1",
        "action": "audition_clip",
        "status": "applied",
        "verified": True,
        "target": {"track_index": 0, "track_name": "1-MIDI", "clip_slot_index": 0},
        "clip_fingerprint": "abc123",
        "clip_length": 4.0,
    }


def test_feedback_is_bound_to_verified_receipt_and_advisory() -> None:
    feedback = build_audition_feedback(
        session_id="session-1",
        receipt=_receipt(),
        verdict="revise",
        rating=3,
        comment="The rhythm is good but the ending is too busy.",
        requested_changes=["Simplify the last beat", "Keep the original tempo"],
    )

    assert feedback["schema"] == "kenn.audition_feedback.v1"
    assert feedback["source_receipt_id"] == "receipt-audition-1"
    assert feedback["audition"]["target"]["track_name"] == "1-MIDI"
    assert feedback["advisory_only"] is True


def test_feedback_rejects_unverified_or_unbounded_input() -> None:
    receipt = _receipt()
    receipt["verified"] = False
    try:
        build_audition_feedback(session_id="session-1", receipt=receipt, verdict="keep")
    except ValueError as exc:
        assert "verified" in str(exc)
    else:
        raise AssertionError("unverified audition receipt was accepted")

    try:
        build_audition_feedback(
            session_id="session-1",
            receipt=_receipt(),
            verdict="revise",
            requested_changes=["change"] * 6,
        )
    except ValueError as exc:
        assert "at most 5" in str(exc)
    else:
        raise AssertionError("unbounded requested changes were accepted")


def test_feedback_persists_and_is_scoped(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(session_memory, "DB_PATH", tmp_path / "feedback.db")
    feedback = build_audition_feedback(
        session_id="session-1", receipt=_receipt(), verdict="keep", rating=5
    )

    assert session_memory.save_audition_feedback(feedback) is True
    rows = session_memory.list_audition_feedback("session-1")
    assert len(rows) == 1
    assert rows[0]["feedback_id"] == feedback["feedback_id"]
    assert rows[0]["verdict"] == "keep"
    assert session_memory.list_audition_feedback("other-session") == []


def test_revision_brief_preserves_provenance_and_is_proposal_only() -> None:
    feedback = build_audition_feedback(
        session_id="session-1",
        receipt=_receipt(),
        verdict="revise",
        rating=3,
        comment="The ending is too busy.",
        requested_changes=["Simplify the last beat"],
    )
    brief = build_audition_revision_brief(feedback)

    assert brief["schema"] == "kenn.audition_revision_brief.v1"
    assert brief["source_receipt_id"] == "receipt-audition-1"
    assert brief["target"] == {"track_index": 0, "track_name": "1-MIDI", "clip_slot_index": 0}
    assert brief["listener"]["requested_changes"] == ["Simplify the last beat"]
    assert brief["advisory_only"] is True


def test_revision_brief_can_carry_bounded_audio_comparison_evidence() -> None:
    feedback = build_audition_feedback(
        session_id="session-1", receipt=_receipt(), verdict="revise", rating=3
    )
    comparison = {
        "schema": "kenn.audiogen_audio_comparison.v1",
        "source_a": {"reference": "/portfolio/audio/a.wav", "input_hash": "a"},
        "source_b": {"reference": "/portfolio/audio/b.wav", "input_hash": "b"},
        "metric_deltas": {
            "rms_dbfs": {"a": -20.0, "b": -18.5, "delta_b_minus_a": 1.5},
        },
        "advisory_only": True,
    }
    brief = build_audition_revision_brief(feedback, comparison=comparison)
    safe, errors = validate_revision_brief(
        brief,
        session_id="session-1",
        track_index=0,
        track_name="1-MIDI",
        clip_slot_index=0,
    )

    assert errors == []
    assert safe["comparison"]["metric_deltas"]["rms_dbfs"]["delta_b_minus_a"] == 1.5
    assert safe["comparison"]["advisory_only"] is True


def test_revision_brief_rejects_non_revision_feedback() -> None:
    feedback = build_audition_feedback(session_id="session-1", receipt=_receipt(), verdict="keep")
    try:
        build_audition_revision_brief(feedback)
    except ValueError as exc:
        assert "revise" in str(exc)
    else:
        raise AssertionError("keep feedback unexpectedly produced a revision brief")


def test_revision_brief_must_match_generation_target() -> None:
    feedback = build_audition_feedback(session_id="session-1", receipt=_receipt(), verdict="revise")
    brief = build_audition_revision_brief(feedback)
    safe, errors = validate_revision_brief(
        brief,
        session_id="session-1",
        track_index=0,
        track_name="Different Track",
        clip_slot_index=0,
    )
    assert safe["target"]["track_index"] == 0
    assert any("track name" in error for error in errors)

from __future__ import annotations

from kenn.core.track_classifier import find_tracks_by_question_role, question_mentions_role


def test_question_mentions_role_detects_single_clear_role() -> None:
    assert question_mentions_role("why is my vocal getting masked") == "vocal_lead"
    assert question_mentions_role("how do I make the kick punchier") == "kick"


def test_question_mentions_role_returns_none_for_no_role_or_ambiguous() -> None:
    assert question_mentions_role("what is Max for Live?") is None
    # Both "vocal" and "guitar" present -> ambiguous, never guess one.
    assert question_mentions_role("why is my vocal clashing with the guitar") is None


def test_find_tracks_by_question_role_returns_real_matching_tracks() -> None:
    # "Lead Vocal" is deliberately avoided here: "lead" alone is also a synth
    # pattern, so that name is ambiguous by the classifier's own (correct)
    # honesty rule and resolves to "unknown" rather than "vocal_lead".
    tracks = [
        {"index": 0, "name": "Vocal", "devices": [{"name": "EQ Eight"}, {"name": "Glue Compressor"}]},
        {"index": 1, "name": "Rhythm Guitar", "devices": [{"name": "Saturator"}]},
    ]
    matches = find_tracks_by_question_role("why is my vocal getting masked", tracks)
    assert len(matches) == 1
    assert matches[0]["track_index"] == 0
    assert matches[0]["track_name"] == "Vocal"
    assert matches[0]["devices"] == ["EQ Eight", "Glue Compressor"]


def test_find_tracks_by_question_role_returns_empty_when_no_role_named() -> None:
    tracks = [{"index": 0, "name": "Vocal", "devices": []}]
    assert find_tracks_by_question_role("what is Max for Live?", tracks) == []


def test_find_tracks_by_question_role_returns_empty_when_no_track_matches() -> None:
    tracks = [{"index": 0, "name": "Rhythm Guitar", "devices": []}]
    assert find_tracks_by_question_role("why is my vocal getting masked", tracks) == []


def test_find_tracks_by_question_role_never_fabricates_devices_for_empty_track() -> None:
    tracks = [{"index": 0, "name": "Vocal", "devices": []}]
    matches = find_tracks_by_question_role("why is my vocal getting masked", tracks)
    assert matches[0]["devices"] == []

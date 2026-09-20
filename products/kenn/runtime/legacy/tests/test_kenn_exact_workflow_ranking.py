"""Regression tests for exact-workflow ranking in KENN retrieval.

Broad topic/tag overlap can make a plausible but less specific note win. These
tests protect two cases where that changed the actual advice, not just source
ordering: broad vocal harshness became a de-essing-only answer, and conflicting
streaming targets became a clipper-settings answer.
"""

from __future__ import annotations

from kenn.core.chat_retrieval import note_query_affinity


def _note(title: str, source: str, tags: list[str]) -> dict:
    return {
        "kind": "note",
        "title": title,
        "source": source,
        "tags": tags,
        "text": "",
    }


def test_bright_harsh_vocal_prefers_broad_diagnosis_over_deessing_only() -> None:
    query = "How do I keep vocals bright but stop them sounding harsh?"
    workflow = _note(
        "Harsh Vocal Fix",
        "harsh-vocal-fix.md",
        ["vocals", "harsh", "sibilance", "dynamic eq", "brightness"],
    )
    deessing = _note(
        "Vocal De-Essing And Sibilance",
        "vocal-deessing-and-sibilance.md",
        ["vocals", "harsh", "sibilance", "de-essing", "brightness"],
    )

    assert note_query_affinity(query, workflow) > note_query_affinity(query, deessing)


def test_conflicting_lufs_advice_prefers_streaming_workflow_over_clipper_recipe() -> None:
    query = "One person says master to -14 LUFS and another says go louder. What should I do?"
    streaming = _note(
        "Mastering For Streaming Loudness",
        "mastering-streaming-loudness.md",
        ["mastering", "loudness", "lufs", "limiter", "streaming"],
    )
    clipper = _note(
        "Jack Gandy Mastering Clipper Workflow",
        "jack-mastering-clipper-use.md",
        ["mastering", "loudness", "clipper", "limiter"],
    )

    assert note_query_affinity(query, streaming) > note_query_affinity(query, clipper)


def test_wwise_combat_dropout_prefers_voice_budget_over_loop_clicks() -> None:
    query = "In a Wwise boss fight my impacts vanish when explosions and ambience are playing. Should I just turn the impact WAVs up?"
    budget = _note(
        "Wwise Combat Sounds Drop Out Voice And Memory Budget",
        "wwise-combat-voice-memory-budget.md",
        ["wwise", "combat", "voice_budget", "loudness", "profiler"],
    )
    clicks = _note(
        "Wwise Conversion Loop Clicks Sample Rate And Restarting Events",
        "wwise-conversion-loop-clicks-sample-rate.md",
        ["wwise", "loop", "click", "conversion", "sample-rate", "sample rate", "ambience"],
    )
    assert note_query_affinity(query, budget) > note_query_affinity(query, clicks)


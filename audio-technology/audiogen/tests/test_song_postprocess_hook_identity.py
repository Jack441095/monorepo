"""Hook identity reinforcement for surprise, disapproval, realization, neutral, love."""

from __future__ import annotations

from composition.song_postprocess.form_polish import (
    reinforce_song_hook_identity,
)


def _chorus_lead_events(start: float, pitches: list[int]) -> list:
    events = []
    t = float(start)
    for p in pitches:
        events.append((2, int(p), 80, t, 0.5, [int(p)]))
        t += 0.5
    return events


def test_hook_identity_skips_non_target_emotion():
    events = _chorus_lead_events(0.0, [72, 74, 76, 77]) + _chorus_lead_events(32.0, [60, 62, 64, 65])
    out, meta = reinforce_song_hook_identity(
        events,
        section_bars=[8, 8],
        section_roles=["chorus", "chorus"],
        section_roots=[60, 60],
        section_emotions=["joy", "joy"],
        primary_emotion="joy",
        beats_per_bar=4.0,
    )
    assert meta.get("enabled") is False
    assert len(out) == len(events)


def test_hook_identity_aligns_second_chorus_for_neutral():
    hook = [72, 74, 76, 77, 79]
    divergent = [84, 86, 88, 90]
    events = _chorus_lead_events(0.0, hook) + _chorus_lead_events(32.0, divergent)

    out, meta = reinforce_song_hook_identity(
        events,
        section_bars=[8, 8],
        section_roles=["chorus", "chorus"],
        section_roots=[60, 60],
        section_emotions=["neutral", "neutral"],
        primary_emotion="neutral",
        beats_per_bar=4.0,
        strength=0.85,
    )
    assert meta.get("enabled") is True
    assert int(meta.get("chorus_sections_aligned", 0) or 0) >= 1
    second_open = sorted(
        [ev for ev in out if ev[0] == 2 and 32.0 <= float(ev[3]) < 40.0],
        key=lambda ev: float(ev[3]),
    )
    assert len(second_open) >= 4
    intervals = [int(second_open[i + 1][1]) - int(second_open[i][1]) for i in range(len(second_open) - 1)]
    assert intervals == [int(hook[i + 1]) - int(hook[i]) for i in range(len(intervals))]


def test_hook_identity_aligns_second_chorus_for_love():
    hook = [67, 69, 71, 72, 74]
    divergent = [79, 81, 83, 84]
    events = _chorus_lead_events(0.0, hook) + _chorus_lead_events(32.0, divergent)

    out, meta = reinforce_song_hook_identity(
        events,
        section_bars=[8, 8],
        section_roles=["chorus", "chorus"],
        section_roots=[60, 60],
        section_emotions=["love", "love"],
        primary_emotion="love",
        beats_per_bar=4.0,
        strength=0.85,
    )
    assert meta.get("enabled") is True
    assert int(meta.get("chorus_sections_aligned", 0) or 0) >= 1

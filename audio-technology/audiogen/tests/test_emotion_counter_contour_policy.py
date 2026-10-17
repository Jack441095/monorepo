"""Emotion-specific counter texture floor and descending contour bias."""

from __future__ import annotations

from composition.song_postprocess._common import _emotion_contour_bias
from composition.song_postprocess.texture_floors import reinforce_chorus_counterline_floor


def test_grief_contour_bias_is_stronger_and_earlier():
    bias, begin_at = _emotion_contour_bias("grief", "chorus")
    assert int(bias) <= -2
    assert float(begin_at) < 0.45


def test_sparse_emotion_skips_chorus_counter_floor():
    events = [
        (2, 72, 80, 0.0, 1.0, [72]),
        (2, 71, 78, 4.0, 1.0, [71]),
    ]
    out, meta = reinforce_chorus_counterline_floor(
        events,
        section_bars=[8],
        section_roles=["chorus"],
        section_roots=[60],
        section_emotions=["anger"],
        primary_emotion="anger",
        beats_per_bar=4.0,
    )
    assert int(meta.get("added_counter_events", -1)) == 0
    assert len(out) == len(events)


def test_light_sparse_emotion_gets_minimal_chorus_counter():
    events = [(2, 67, 70, 0.0, 1.0, [67])]
    out, meta = reinforce_chorus_counterline_floor(
        events,
        section_bars=[8],
        section_roles=["chorus"],
        section_roots=[60],
        section_emotions=["embarrassment"],
        primary_emotion="embarrassment",
        beats_per_bar=4.0,
    )
    assert int(meta.get("added_counter_events", 0)) >= 1
    assert any(int(ev[0]) == 5 for ev in out)


def test_light_sparse_emotion_gets_first_verse_counter():
    events = [(2, 67, 70, 0.0, 1.0, [67])]
    out, meta = reinforce_chorus_counterline_floor(
        events,
        section_bars=[8, 8],
        section_roles=["verse", "chorus"],
        section_roots=[60, 60],
        section_emotions=["nervousness", "nervousness"],
        primary_emotion="nervousness",
        beats_per_bar=4.0,
    )
    assert meta.get("light_verse_filled") is True
    assert int(meta.get("added_counter_events", 0)) >= 2


def test_grief_chorus_counter_floor_can_add_gestures():
    events = [(2, 67, 70, 0.0, 1.0, [67])]
    out, meta = reinforce_chorus_counterline_floor(
        events,
        section_bars=[8],
        section_roles=["chorus"],
        section_roots=[60],
        section_emotions=["grief"],
        primary_emotion="grief",
        beats_per_bar=4.0,
        min_gestures=3,
    )
    assert int(meta.get("added_counter_events", 0)) >= 1

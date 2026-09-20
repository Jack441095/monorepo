from collections import deque
from types import SimpleNamespace


def _emotion():
    return SimpleNamespace(name="love", scale_intervals=[0, 2, 4, 5, 7, 9, 11])


def _mem(sig=("I", "V", "vi", "IV"), register=64.0):
    return SimpleNamespace(
        last_chord_signature=tuple(sig),
        last_register_center=register,
        recent_chord_signatures=deque(maxlen=8),
        recent_register_centers=deque(maxlen=8),
    )


def test_sampler_rerank_prefers_lyrical_topline_when_base_score_ties():
    from composition.section_scoring import sampler_musical_adjustment as _sampler_musical_adjustment

    lyrical_events = [
        (2, 60, 90, 0.0, 1.0, [60]),
        (2, 62, 90, 1.0, 1.0, [62]),
        (2, 64, 90, 2.0, 1.0, [64]),
        (2, 62, 90, 4.0, 1.0, [62]),
        (2, 60, 90, 5.0, 1.0, [60]),
        (2, 64, 90, 6.0, 1.0, [64]),
        (2, 62, 90, 8.0, 1.0, [62]),
        (2, 60, 90, 9.0, 1.0, [60]),
    ]
    jumpy_events = [
        (2, 60, 90, 0.0, 0.25, [60]),
        (2, 71, 90, 0.25, 0.25, [71]),
        (2, 61, 90, 0.50, 0.25, [61]),
        (2, 69, 90, 0.75, 0.25, [69]),
        (2, 63, 90, 1.00, 0.25, [63]),
        (2, 70, 90, 1.25, 0.25, [70]),
    ]

    baseline = _mem(sig=("ii", "V", "I", "I"), register=58.0)
    good, good_details = _sampler_musical_adjustment(
        base_score=1.0,
        events=lyrical_events,
        emotion=_emotion(),
        root_note=60,
        section_role="b",
        candidate_song_memory=_mem(register=66.0),
        baseline_song_memory=baseline,
    )
    bad, bad_details = _sampler_musical_adjustment(
        base_score=1.0,
        events=jumpy_events,
        emotion=_emotion(),
        root_note=60,
        section_role="b",
        candidate_song_memory=_mem(register=66.0),
        baseline_song_memory=baseline,
    )

    assert good > bad
    assert good_details["sampler_lyrical_score"] > bad_details["sampler_lyrical_score"]


def test_sampler_rerank_penalizes_recent_harmony_signature():
    from composition.section_scoring import sampler_musical_adjustment as _sampler_musical_adjustment

    events = [
        (2, 60, 90, 0.0, 1.0, [60]),
        (2, 62, 90, 1.0, 1.0, [62]),
        (2, 64, 90, 2.0, 1.0, [64]),
        (2, 60, 90, 3.0, 1.0, [60]),
    ]
    baseline = _mem(sig=("ii", "V", "I", "I"), register=60.0)
    baseline.recent_chord_signatures.append(("I", "V", "vi", "IV"))

    repeated, rep_details = _sampler_musical_adjustment(
        base_score=1.0,
        events=events,
        emotion=_emotion(),
        root_note=60,
        section_role="a",
        candidate_song_memory=_mem(sig=("I", "V", "vi", "IV"), register=64.0),
        baseline_song_memory=baseline,
    )
    fresh, fresh_details = _sampler_musical_adjustment(
        base_score=1.0,
        events=events,
        emotion=_emotion(),
        root_note=60,
        section_role="a",
        candidate_song_memory=_mem(sig=("vi", "IV", "I", "V"), register=64.0),
        baseline_song_memory=baseline,
    )

    assert fresh > repeated
    assert rep_details["sampler_harmony_repeat_penalty"] > 0.0
    assert fresh_details["sampler_harmony_repeat_penalty"] == 0.0

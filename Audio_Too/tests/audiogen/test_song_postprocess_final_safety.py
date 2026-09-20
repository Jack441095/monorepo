from composition.song_postprocess_pipeline import (
    _apply_final_bass_motion_guard,
    _apply_final_bar_velocity_smoother,
    _apply_final_chorus_strength_guard,
    _apply_final_lead_singability_guard,
    _apply_final_phrase_boundary_breath,
)


def test_final_phrase_boundary_breath_trims_long_lead_note():
    events = [
        (2, 72, 80, 15.0, 2.0, [72]),
        (1, 0, 70, 15.0, 4.0, [60, 64, 67]),
    ]

    out, meta = _apply_final_phrase_boundary_breath(
        events,
        section_bars=[8],
        beats_per_bar=4.0,
        breath_beats=0.18,
        min_note_beats=0.20,
    )

    lead = [ev for ev in out if ev[0] == 2][0]
    assert lead[3] == 15.0
    assert round(lead[4], 3) == 0.82
    assert meta["trimmed_events"] == 1


def test_final_phrase_boundary_breath_moves_pickup_out_of_breath_window():
    events = [(2, 79, 78, 15.9, 0.5, [79])]

    out, meta = _apply_final_phrase_boundary_breath(
        events,
        section_bars=[8],
        beats_per_bar=4.0,
        breath_beats=0.18,
        min_note_beats=0.20,
    )

    assert out[0][3] >= 16.0
    assert meta["shifted_pickups"] == 1


def test_final_phrase_boundary_breath_moves_too_short_pre_boundary_note():
    events = [(2, 79, 78, 15.75, 0.249, [79])]

    out, meta = _apply_final_phrase_boundary_breath(
        events,
        section_bars=[8],
        beats_per_bar=4.0,
        breath_beats=0.18,
        min_note_beats=0.20,
    )

    assert out[0][3] >= 16.0
    assert meta["shifted_pickups"] == 1


def test_final_bar_velocity_smoother_limits_nonempty_bar_ratios():
    events = [
        (2, 72, 4, 0.0, 0.5, [72]),
        (2, 74, 90, 4.0, 0.5, [74]),
        (2, 76, 127, 8.0, 0.5, [76]),
        (1, 0, 60, 0.0, 4.0, [60, 64, 67]),
    ]

    out, meta = _apply_final_bar_velocity_smoother(
        events,
        beats_per_bar=4.0,
        ratio=1.35,
        velocity_floor=30,
    )

    lead_velocities = [ev[2] for ev in out if ev[0] == 2]
    assert lead_velocities == [30, 40, 55]
    assert meta["adjusted_events"] == 3


def test_final_bar_velocity_smoother_ignores_long_re_entries():
    events = [
        (3, 67, 90, 0.0, 0.5, [67]),
        (3, 67, 30, 40.0, 0.5, [67]),
    ]

    out, meta = _apply_final_bar_velocity_smoother(events, beats_per_bar=4.0, ratio=1.35)

    assert [ev[2] for ev in out] == [90, 30]
    assert meta == {}


def test_final_lead_singability_guard_reduces_range_and_leaps_by_octave():
    events = [
        (2, 52, 80, 0.0, 0.5, [52]),
        (2, 88, 80, 1.0, 0.5, [88]),
        (2, 55, 80, 2.0, 0.5, [55]),
        (1, 0, 70, 0.0, 4.0, [60, 64, 67]),
    ]

    out, meta = _apply_final_lead_singability_guard(
        events,
        target_range_semitones=24,
        max_leap_semitones=14,
    )

    pitches = [ev[1] for ev in out if ev[0] == 2]
    assert max(pitches) - min(pitches) <= 24
    assert max(abs(b - a) for a, b in zip(pitches, pitches[1:])) <= 14
    assert meta["notes_shifted"] >= 1


def test_final_bass_motion_guard_repairs_static_core_section():
    events = [
        (0, 48, 70, 0.0, 4.0, [48]),
        (0, 48, 70, 4.0, 4.0, [48]),
        (0, 48, 70, 8.0, 4.0, [48]),
        (2, 72, 80, 0.0, 0.5, [72]),
    ]

    out, meta = _apply_final_bass_motion_guard(
        events,
        section_bars=[4],
        section_roles=["a"],
        beats_per_bar=4.0,
    )

    bass_pitches = {ev[1] for ev in out if ev[0] == 0}
    assert len(bass_pitches) > 1
    assert meta["sections_repaired"] == 1


def test_final_chorus_strength_guard_adds_restrained_lead_accents():
    events = []
    for i in range(8):
        events.append((2, 72, 80, float(i) * 0.5, 0.25, [72]))
    events.append((2, 76, 82, 16.5, 0.25, [76]))

    out, meta = _apply_final_chorus_strength_guard(
        events,
        section_bars=[4, 4],
        section_roles=["a", "b"],
        section_roots=[60, 60],
        beats_per_bar=4.0,
        min_chorus_to_verse_ratio=0.90,
    )

    assert len([ev for ev in out if ev[0] == 2]) > len(events)
    assert meta["notes_added"] >= 1

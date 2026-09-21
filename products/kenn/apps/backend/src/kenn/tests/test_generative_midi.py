"""Tests for Live 12 Generative MIDI & Clip Composer Engine."""

from kenn.core.generative_midi import (
    generate_chord_progression,
    generate_drum_pattern,
    generate_euclidean_rhythm,
    get_scale_pitches,
)


def test_get_scale_pitches():
    c_maj = get_scale_pitches("C", "major", octave=3)
    assert 60 in c_maj  # Middle C
    assert 62 in c_maj  # D
    assert 64 in c_maj  # E
    assert 65 in c_maj  # F
    assert 67 in c_maj  # G
    assert 61 not in c_maj  # C# should not be in C major


def test_generate_chord_progression():
    notes = generate_chord_progression("A", "minor", "pop_i_v_vi_iv", beats_per_chord=4.0, seed=42)
    assert len(notes) > 0
    # 4 chords * 3 notes per triad = 12 notes
    assert len(notes) == 12
    # Verify time sequencing
    times = [n["start_time"] for n in notes]
    assert min(times) == 0.0
    assert max(times) == 12.0
    # Verify velocities within valid range
    assert all(1 <= n["velocity"] <= 127 for n in notes)


def test_generate_euclidean_rhythm():
    # 5 hits over 8 steps (tresillo variation)
    notes = generate_euclidean_rhythm(5, 8, pitch=36, step_duration_beats=0.25)
    assert len(notes) == 5
    # Distinct start times
    start_times = [n["start_time"] for n in notes]
    assert len(set(start_times)) == 5
    assert all(n["pitch"] == 36 for n in notes)


def test_generate_drum_pattern_trap():
    trap = generate_drum_pattern("trap", bars=2)
    assert len(trap) > 0
    pitches = {n["pitch"] for n in trap}
    # Must contain kick (36), clap (39), and hats (42)
    assert 36 in pitches
    assert 39 in pitches
    assert 42 in pitches

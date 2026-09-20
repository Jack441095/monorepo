"""Unit tests for KENN Generative In-DAW MIDI Copilot (V6.0)."""

from __future__ import annotations

import pytest
from kenn.core.midi_copilot import MidiCopilot, get_midi_copilot


def test_scale_pitches_conformity():
    """Asserts generated pitches strictly adhere to chosen scale."""
    copilot = MidiCopilot()

    # F Natural Minor: F, G, Ab, Bb, C, Db, Eb
    f_minor_notes = copilot.get_scale_pitches("F", "NATURAL_MINOR", octave_start=3, num_octaves=2)
    assert len(f_minor_notes) == 14

    # F3 is MIDI note 53
    assert 53 in f_minor_notes
    # G3 is MIDI note 55
    assert 55 in f_minor_notes
    # Ab3 (G#3) is MIDI note 56
    assert 56 in f_minor_notes
    # Major 3rd (A3 = 57) must NOT be in F minor
    assert 57 not in f_minor_notes


def test_counterpoint_generation():
    """Verifies counterpoint note counts, scale alignment, and velocity dynamics."""
    copilot = get_midi_copilot()
    clip = copilot.generate_counterpoint(root="F", scale="NATURAL_MINOR", bars=4, swing="MPC_16_SWING_58")

    assert clip.length_bars == 4
    assert len(clip.notes) == 32  # 4 bars * 4 beats * 2 (8th notes)
    assert clip.swing_profile == "MPC_16_SWING_58"

    scale_pitches = set(copilot.get_scale_pitches("F", "NATURAL_MINOR", octave_start=3, num_octaves=4))

    for note in clip.notes:
        # Every note must be in scale
        assert note.pitch in scale_pitches
        # Dynamic velocity within musical range [68, 115]
        assert 68 <= note.velocity <= 115
        assert note.duration > 0.0


def test_rolling_bassline_synthesis():
    """Asserts 16th-note rolling pattern structure and duration constraints."""
    copilot = MidiCopilot()
    clip = copilot.generate_bassline(root="F", scale="NATURAL_MINOR", bars=4, style="ROLLING_16TH")

    assert clip.length_bars == 4
    # 4 bars * 16 steps = 64 notes
    assert len(clip.notes) == 64

    # Low octave root
    assert clip.notes[0].pitch in [29, 41]
    for note in clip.notes:
        assert 0.15 <= note.duration <= 0.25

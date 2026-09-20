"""Tests for KENN Intelligent Session World Model & Neural MIDI Engine (v0.5.0)."""

import pytest
from kenn.core.session_world_model import SessionWorldModel, ROLE_KICK, ROLE_SUB_BASS, ROLE_MID_BASS, ROLE_SYNTH_LEAD, ROLE_DRUMS_BUS
from kenn.core.generative_midi import (
    detect_scale_from_notes,
    apply_audiogen_groove,
    generate_audiogen_bassline,
)


@pytest.fixture
def mock_session_live12():
    return {
        "status": "connected",
        "tempo": 140.0,
        "signature_numerator": 4,
        "signature_denominator": 4,
        "locators": [
            {"name": "Intro Ambient", "time": 1.0},
            {"name": "Build Snare Roll", "time": 17.0},
            {"name": "Main Drop", "time": 33.0},
            {"name": "Outro Reverb Tail", "time": 65.0},
        ],
        "tracks": [
            {
                "index": 0,
                "name": "Kick 808",
                "volume": 0.88,
                "pan": 0.0,
                "devices": ["Drum Bus", "Compressor"],
                "clip_slots": [{"has_clip": True}, {"has_clip": True}],
            },
            {
                "index": 1,
                "name": "Sub Clean",
                "volume": 0.85,
                "pan": 0.0,
                "devices": ["Utility"],
                "clip_slots": [{"has_clip": True}, {"has_clip": False}],
            },
            {
                "index": 2,
                "name": "Track 3 (Neuro)",
                "volume": 0.80,
                "pan": 0.0,
                "devices": ["Roar", "Auto Filter"],
                "clip_slots": [{"has_clip": True}, {"has_clip": True}],
            },
            {
                "index": 3,
                "name": "Wavetable Poly",
                "volume": 0.75,
                "pan": 0.0,
                "devices": ["Wavetable", "Hybrid Reverb"],
                "clip_slots": [{"has_clip": True}, {"has_clip": True}],
            },
        ],
    }


def test_multimodal_role_inference():
    # 1. Name + Device (Roar on bass)
    role, conf = SessionWorldModel.infer_role("Track 3", devices=["Roar", "Auto Filter"], spectral_centroid_hz=180.0)
    assert role == ROLE_MID_BASS
    assert conf >= 0.80

    # 2. Wavetable poly synth
    role_synth, conf_synth = SessionWorldModel.infer_role("Synth Keys", devices=["Wavetable", "Hybrid Reverb"])
    assert role_synth == ROLE_SYNTH_LEAD
    assert conf_synth >= 0.80

    # 3. Drum Bus device fingerprinting
    role_drum, conf_drum = SessionWorldModel.infer_role("Beats 01", devices=["Drum Bus"])
    assert role_drum == ROLE_DRUMS_BUS
    assert conf_drum >= 0.85


def test_arrangement_section_energy_profile(mock_session_live12):
    sections = SessionWorldModel.infer_arrangement_sections(mock_session_live12)
    assert len(sections) == 4

    names = [s["name"] for s in sections]
    kinds = [s["kind"] for s in sections]
    energies = [s["target_energy"] for s in sections]

    assert kinds[0] == "intro"
    assert kinds[1] == "build"
    assert kinds[2] == "drop"
    assert kinds[3] == "outro"

    # Verify dynamic energy contrast between drop and intro
    assert energies[2] > energies[1] > energies[0]
    assert sections[2]["target_energy"] == 1.00
    assert sections[0]["target_energy"] == 0.35


def test_krumhansl_schmuckler_scale_detection():
    # Synthetic C Minor scale notes (C=60, D=62, Eb=63, F=65, G=67, Ab=68, Bb=70)
    c_minor_notes = [
        {"pitch": 60, "duration": 2.0, "velocity": 100},  # C (tonic)
        {"pitch": 63, "duration": 1.0, "velocity": 90},   # Eb (minor 3rd)
        {"pitch": 67, "duration": 2.0, "velocity": 100},  # G (5th)
        {"pitch": 68, "duration": 1.0, "velocity": 85},   # Ab (minor 6th)
        {"pitch": 70, "duration": 1.0, "velocity": 90},   # Bb (minor 7th)
        {"pitch": 60, "duration": 2.0, "velocity": 100},  # C
    ]

    result = detect_scale_from_notes(c_minor_notes)
    assert result["root"] == "C"
    assert result["scale"] == "minor"
    assert result["confidence"] > 0.60
    assert len(result["out_of_scale_notes"]) == 0

    # Introduce an out-of-scale tritone / sharp note (F# = 66)
    c_minor_with_clash = c_minor_notes + [{"pitch": 66, "duration": 1.0, "velocity": 90, "start_time": 4.0}]
    clash_result = detect_scale_from_notes(c_minor_with_clash)
    assert len(clash_result["out_of_scale_notes"]) == 1
    assert clash_result["out_of_scale_notes"][0]["pitch"] == 66


def test_audiogen_groove_and_bassline_generation():
    # Test bassline synthesizer
    bass_notes = generate_audiogen_bassline(
        root="F", scale_name="minor", style="bouncy", bars=2, octave=1, groove="straight"
    )
    assert len(bass_notes) >= 6
    pitches = [n["pitch"] for n in bass_notes]
    assert all(24 <= p <= 48 for p in pitches)  # True bass register

    # Test AudioGen swing groove application
    straight_notes = [
        {"pitch": 60, "start_time": 0.00, "duration": 0.20, "velocity": 100},
        {"pitch": 60, "start_time": 0.25, "duration": 0.20, "velocity": 100},  # Offbeat 16th
        {"pitch": 60, "start_time": 0.50, "duration": 0.20, "velocity": 100},
        {"pitch": 60, "start_time": 0.75, "duration": 0.20, "velocity": 100},  # Offbeat 16th
    ]
    swung = apply_audiogen_groove(straight_notes, groove_name="lofi_swing", seed=42)
    assert len(swung) == 4
    # Offbeats at index 1 and 3 should be shifted later by swing and laidback pocket
    assert swung[1]["start_time"] > 0.25
    assert swung[3]["start_time"] > 0.75


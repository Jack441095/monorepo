"""Unit tests for KENN Session World Model (Semantic Roles & Frequency Priority Matrix)."""

import pytest
from kenn.core.session_world_model import (
    SessionWorldModel,
    ROLE_KICK,
    ROLE_SUB_BASS,
    ROLE_MID_BASS,
    ROLE_LEAD_VOCAL,
    ROLE_SYNTH_LEAD,
    ROLE_PADS_REVERB,
    ROLE_GENERIC,
)


def test_infer_role_by_track_name():
    assert SessionWorldModel.infer_role("Kick Drum", [])[0] == ROLE_KICK
    assert SessionWorldModel.infer_role("808 Sub", [])[0] == ROLE_SUB_BASS
    assert SessionWorldModel.infer_role("Neuro Bass", [])[0] == ROLE_MID_BASS
    assert SessionWorldModel.infer_role("Main Vox Lead", [])[0] == ROLE_LEAD_VOCAL
    assert SessionWorldModel.infer_role("Supersaw Lead", [])[0] == ROLE_SYNTH_LEAD
    assert SessionWorldModel.infer_role("Ambient Pad", [])[0] == ROLE_PADS_REVERB
    assert SessionWorldModel.infer_role("Random Audio 4", [])[0] == ROLE_GENERIC


def test_infer_role_by_device_fallback():
    role, conf = SessionWorldModel.infer_role("Drop 1", ["Operator"])
    assert role in (ROLE_MID_BASS, ROLE_GENERIC)


def test_build_world_model_detects_sub_kick_collision():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Kick", "devices": [{"name": "DrumSampler"}]},
            {"index": 1, "name": "Sub Bass", "devices": [{"name": "Drift"}]},
        ]
    }
    model = SessionWorldModel.build_world_model(session_state)
    assert model["status"] == "success"
    assert model["total_tracks"] == 2
    assert model["roles_inventory"][ROLE_KICK] == 1
    assert model["roles_inventory"][ROLE_SUB_BASS] == 1

    # Should flag missing sidechain/compression collision risk
    conflict_codes = [c["code"] for c in model["conflicts"]]
    assert "SUB_KICK_COLLISION_RISK" in conflict_codes


def test_build_world_model_detects_low_mid_mud():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Lead Synth", "devices": []},
            {"index": 1, "name": "Texture Pad", "devices": []},
            {"index": 2, "name": "Backing Vox", "devices": []},
        ]
    }
    model = SessionWorldModel.build_world_model(session_state)
    conflict_codes = [c["code"] for c in model["conflicts"]]
    assert "LOW_MID_MUD_ACCUMULATION" in conflict_codes


def test_build_world_model_detects_vocal_presence_masking():
    session_state = {
        "tracks": [
            {"index": 0, "name": "Lead Vox", "devices": [{"name": "Compressor"}]},
            {"index": 1, "name": "Supersaw Chords", "devices": [{"name": "EqEight"}]},
        ]
    }
    model = SessionWorldModel.build_world_model(session_state)
    conflict_codes = [c["code"] for c in model["conflicts"]]
    assert "VOCAL_PRESENCE_MASKING" in conflict_codes


def test_arrangement_sections_and_harmonics():
    session_state = {
        "tempo": 128.0,
        "root_note": "F#",
        "scale_name": "Minor",
        "locators": [
            {"name": "Intro", "time": 1.0},
            {"name": "Verse 1", "time": 17.0},
            {"name": "Build Up", "time": 33.0},
            {"name": "Drop 1", "time": 49.0},
            {"name": "Outro", "time": 81.0},
        ],
        "tracks": [
            {"index": 0, "name": "Kick", "devices": []},
        ],
    }
    model = SessionWorldModel.build_world_model(session_state)


    sections = model.get("arrangement_sections", [])
    assert len(sections) == 5
    kinds = [s["kind"] for s in sections]
    assert kinds == ["intro", "verse", "build", "drop", "outro"]

    harmonics = model.get("harmonic_context", {})
    assert harmonics["tempo_bpm"] == 128.0
    assert harmonics["root_note"] == "F#"
    assert harmonics["scale_name"] == "Minor"
    assert harmonics["key_signature"] == "F# Minor"

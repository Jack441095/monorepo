"""Unit tests for KENN Multi-Stem Dynamic Unmasking Engine."""

from __future__ import annotations

import pytest
from kenn.core.stem_unmasking import StemUnmaskingEngine, get_stem_unmasking_engine


def test_kick_bass_erb_unmasking_synthesis():
    engine = StemUnmaskingEngine()
    tracks = [
        {"index": 0, "name": "Kick Drum 909", "volume": 0.90},
        {"index": 1, "name": "Sub Bass 808", "volume": 0.88},
        {"index": 2, "name": "Hihat Closed", "volume": 0.60},
    ]

    collisions = engine.detect_collisions(tracks)
    assert len(collisions) >= 1

    sub_collision = next((c for c in collisions if "kick" in c.masker_track_name.lower()), None)
    assert sub_collision is not None
    assert sub_collision.masked_track_name == "Sub Bass 808"
    assert sub_collision.collision_frequency_hz == 65.0
    assert -3.0 <= sub_collision.recommended_cut_db <= -1.0
    assert 1.4 <= sub_collision.recommended_q <= 2.5

    dag = engine.synthesize_unmasking_dag(collisions)
    assert len(dag) >= 1
    step = dag[0]
    assert step["target_track_name"] == "Sub Bass 808"
    assert step["frequency_hz"] == 65.0
    assert step["gain_delta_db"] >= -3.0  # Safe gain cut clamp
    assert step["filter_type"] == "DynamicBell"


def test_vocal_acoustic_unmasking():
    engine = StemUnmaskingEngine()
    tracks = [
        {"index": 0, "name": "Lead Vocal Main", "volume": 0.85},
        {"index": 1, "name": "Rhythm Guitar Electric", "volume": 0.82},
    ]

    collisions = engine.detect_collisions(tracks)
    assert len(collisions) == 1

    vocal_col = collisions[0]
    assert vocal_col.masker_track_name == "Lead Vocal Main"
    assert vocal_col.masked_track_name == "Rhythm Guitar Electric"
    assert vocal_col.collision_frequency_hz == 1800.0
    assert -3.0 <= vocal_col.recommended_cut_db <= -1.0

    dag = engine.synthesize_unmasking_dag(collisions)
    assert len(dag) == 1
    assert dag[0]["target_track_name"] == "Rhythm Guitar Electric"
    assert dag[0]["frequency_hz"] == 1800.0


def test_hardware_clamp_enforcement():
    engine = StemUnmaskingEngine()
    # Create extreme collision with inflated cut recommendation
    from kenn.core.stem_unmasking import StemCollision
    extreme = StemCollision(
        masker_track_name="Kick",
        masker_track_index=0,
        masked_track_name="Bass",
        masked_track_index=1,
        collision_frequency_hz=60.0,
        masking_depth_db=18.0,
        recommended_cut_db=-9.5,  # Unsafe!
        recommended_q=0.5,        # Too wide!
        filter_type="Bell",
        rationale="Test extreme",
    )

    dag = engine.synthesize_unmasking_dag([extreme])
    assert len(dag) == 1
    # Must clamp strictly to -3.0 dB and Q >= 1.4
    assert dag[0]["gain_delta_db"] == -3.0
    assert dag[0]["q"] == 1.4

"""Tests for the masking de-mask stage in mix_and_render_stems().

Closes the "detected inter-stem masking but rendered zero corrections" funnel
(docs/DETECT_CORRECT_CHAIN_MAP_2026-07-16.md §3): the relationship engine's
actionable dynamic-EQ candidates are now applied to the lower-priority target
stem, gated by MixPlan.apply_masking_corrections (default OFF) and capped.

Verifies the wiring only — the detector/processor primitives are tested in
test_resonance_detection.py / test_dynamic_eq.py.
"""

from __future__ import annotations

import numpy as np

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_renderer import (
    mix_and_render_stems,
    _MAX_MASKING_MOVES_PER_SONG,
)

SR = 44100
DURATION_S = 6.0
N = int(SR * DURATION_S)
_T = np.arange(N) / SR


def _profile(name: str, instrument: str) -> StemProfile:
    return StemProfile(
        name=name, instrument=instrument, peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0,
    )


def _tone(freq: float, seed: int = 2) -> np.ndarray:
    rng = np.random.default_rng(seed)
    harm = sum(np.sin(2 * np.pi * freq * k * _T) / k for k in (1, 2, 3))
    noise = rng.normal(0, 1, N) * 0.03
    return (harm * 0.3 + noise).astype(np.float64)


def _dynamic_eq_relationship(rel_id: str, target: str, freq: float, score: float, status: str = "candidate") -> dict:
    """A minimal relationship dict shaped like relationships.py's to_dict(),
    carrying one actionable dynamic_eq candidate on `target`."""
    return {
        "relationship_id": rel_id,
        "status": status,
        "intervention_target": target,
        "protected_stem": "vocal.wav",
        "candidate_strategies": [
            {
                "candidate_id": f"{rel_id}-candidate-00",
                "strategy": "dynamic_eq",
                "target_stem": target,
                "parameters": {
                    "frequency_hz": freq,
                    "max_reduction_db": 3.0,
                    "q": 1.2,
                    "attack_ms": 20.0,
                    "release_ms": 140.0,
                },
                "score": score,
            }
        ],
    }


def _plan(stems_and_instruments, relationships, apply_masking):
    profiles = [_profile(name, instrument) for name, instrument, _ in stems_and_instruments]
    plan = generate_mix_plan(profiles, genre="pop", target_lufs=-12.0)
    plan.genre = "pop"
    plan.bus.limiter_ceiling_db = -1.0
    plan.relationships = relationships
    plan.apply_masking_corrections = apply_masking
    return plan


def _render(stems_and_instruments, relationships, apply_masking):
    plan = _plan(stems_and_instruments, relationships, apply_masking)
    stem_dicts = [
        {"name": name, "samples": samples, "sample_rate": SR}
        for name, _, samples in stems_and_instruments
    ]
    return mix_and_render_stems(stem_dicts, plan)


STEMS = [
    ("vocal.wav", "vocal", _tone(300.0, seed=1)),
    ("guitar.wav", "guitar", _tone(500.0, seed=2)),
]


class TestMaskingCorrectionGate:
    def test_disabled_by_default_applies_nothing(self) -> None:
        rels = [_dynamic_eq_relationship("rel-001", "guitar.wav", 500.0, 0.8)]
        result = _render(STEMS, rels, apply_masking=False)
        assert result["masking_corrections"] == {}

    def test_enabled_applies_move_to_target_stem(self) -> None:
        rels = [_dynamic_eq_relationship("rel-001", "guitar.wav", 500.0, 0.8)]
        result = _render(STEMS, rels, apply_masking=True)
        assert "guitar.wav" in result["masking_corrections"]
        move = result["masking_corrections"]["guitar.wav"]
        assert move["frequency_hz"] == 500.0
        assert move["max_reduction_db"] == 3.0

    def test_protected_stem_is_never_touched(self) -> None:
        rels = [_dynamic_eq_relationship("rel-001", "guitar.wav", 500.0, 0.8)]
        result = _render(STEMS, rels, apply_masking=True)
        # The protected vocal is not a target -> no move keyed to it.
        assert "vocal.wav" not in result["masking_corrections"]

    def test_review_required_relationship_is_skipped(self) -> None:
        rels = [_dynamic_eq_relationship("rel-001", "guitar.wav", 500.0, 0.8, status="review_required")]
        result = _render(STEMS, rels, apply_masking=True)
        assert result["masking_corrections"] == {}

    def test_enabled_changes_the_audio(self) -> None:
        rels = [_dynamic_eq_relationship("rel-001", "guitar.wav", 500.0, 0.8)]
        off = _render(STEMS, rels, apply_masking=False)
        on = _render(STEMS, rels, apply_masking=True)
        # The de-mask move must actually alter the rendered master.
        diff = float(np.max(np.abs(on["left"] - off["left"])))
        assert diff > 1e-6, "masking correction should change the rendered audio"

    def test_move_budget_is_capped(self) -> None:
        # More distinct target stems than the per-song budget.
        extra = [(f"pad{i}.wav", "synth_pad", _tone(400.0 + 40 * i, seed=10 + i))
                 for i in range(_MAX_MASKING_MOVES_PER_SONG + 4)]
        stems = STEMS + extra
        rels = [
            _dynamic_eq_relationship(f"rel-{i:03d}", f"pad{i}.wav", 400.0 + 40 * i, 0.9 - 0.01 * i)
            for i in range(_MAX_MASKING_MOVES_PER_SONG + 4)
        ]
        result = _render(stems, rels, apply_masking=True)
        assert len(result["masking_corrections"]) <= _MAX_MASKING_MOVES_PER_SONG

    def test_render_still_valid_with_masking_engaged(self) -> None:
        rels = [_dynamic_eq_relationship("rel-001", "guitar.wav", 500.0, 0.8)]
        result = _render(STEMS, rels, apply_masking=True)
        assert isinstance(result["mixdown_wav_bytes"], bytes)
        assert result["sample_rate"] == SR
        max_peak = float(np.max(np.abs(np.vstack([result["left"], result["right"]]))))
        assert max_peak <= 1.0 + 1e-6

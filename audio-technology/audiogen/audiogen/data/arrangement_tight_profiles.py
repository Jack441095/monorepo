from __future__ import annotations

from typing import Any, Dict

TIGHT_PROFILES: Dict[str, Dict[str, Any]] = {
    "pop_ext": {
        # Arrange form defaults
        "arranged_song_mode": "pop_ext",
        "ambient_chord_hold_bars": 1,
        # Chord rerank + schedule
        "chord_k_samples": 5,
        "chord_rerank_change_bonus": 0.10,
        "chord_rerank_cadence_bonus": 0.14,
        "chord_temp_opening_mult": 0.88,
        "chord_temp_continuation_mult": 1.06,
        "chord_temp_answer_mult": 1.00,
        "chord_temp_cadence_mult": 0.86,
        # Melody rerank
        "melody_k_samples": 5,
        "melody_rerank_opening_stepwise_bonus": 0.08,
        "melody_rerank_opening_chord_tone_bonus": 0.07,
        "melody_rerank_cadence_target_bonus": 0.13,
        "melody_rerank_cadence_approach_bonus": 0.05,
    },
    "ambient": {
        "arranged_song_mode": "ambient",
        "ambient_chord_hold_bars": 2,
        "chord_k_samples": 3,
        "chord_rerank_change_bonus": 0.04,
        "chord_rerank_cadence_bonus": 0.10,
        "chord_temp_opening_mult": 0.82,
        "chord_temp_continuation_mult": 0.96,
        "chord_temp_answer_mult": 0.92,
        "chord_temp_cadence_mult": 0.80,
        "melody_k_samples": 3,
        "melody_rerank_opening_stepwise_bonus": 0.05,
        "melody_rerank_opening_chord_tone_bonus": 0.06,
        "melody_rerank_cadence_target_bonus": 0.09,
        "melody_rerank_cadence_approach_bonus": 0.04,
    },
}


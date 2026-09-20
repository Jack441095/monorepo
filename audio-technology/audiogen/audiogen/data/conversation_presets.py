# data/conversation_presets.py
# Project module `conversation_presets` (data).

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict

USER_PRESETS_PATH = Path(__file__).with_name("user_conversation_presets.json")

# Layered electronic / game-OST (e.g. Matsutake-style): slow harmony, arp+pad+lead clarity.
# Explicit preset name ``ambient01`` (legacy baseline); startup default uses ``default_ambient_01``.
_PRESET_MATUSAKE_AMBIENT: Dict[str, Any] = {
    # Use shipped ``samples/default/`` WAVs (``samples/ambient/`` is optional / often absent).
    "sample_pack": "default",
    "emotion_pool": [
        "caring",
        "grief",
        "neutral",
        "realization",
        "remorse",
        "sadness",
        "serenity",
    ],
    "emotion_weights": {
        "serenity": 2.8,
        "sadness": 2.6,
        "neutral": 2.0,
        "realization": 1.8,
        "caring": 1.4,
        "grief": 1.0,
        "remorse": 0.8,
    },
    "root_pool": [52, 55, 57, 60, 64],
    "root_weights": {
        55: 3.0,
        52: 2.0,
        57: 1.8,
        60: 1.2,
        64: 0.9,
    },
    "composition": {
        "default_tempo": 60.0,
        "bars_per_section": 16,
        "bass_density": 1.25,
        "force_change_prob": 0.08,
        "embellishment_prob": 0.08,
        "motif_variation_prob": 0.22,
        "extension_prob": 0.18,
        "interchange_prob": 0.1,
        "secondary_dominant_prob": 0.07,
        "melody_harmony_agreement_preset": "tight",
        "arp_melody_compat_weight": 0.4,
        "arp_melody_strongbeat_mask_weight": 0.84,
        "arp_melody_register_separation_semitones": 6,
        "arp_chord_harmonic_rhythm_shared_enabled": True,
        "arp_refine_against_lead_enabled": True,
        "joint_generation_enabled": True,
        "joint_generation_max_iters": 2,
        "section_k_samples": 4,
        "section_pick_time_budget_s": 1.0,
        "pop_arrangement_strength": 0.0,
        "pop_hook_scoring_strength": 0.0,
        "arranged_song_mode": "ambient",
    },
    "audio": {
        "reverb_wet": 0.38,
    },
}

# Primary startup preset (also keyed ``default`` / ``default_ambient_01``): ambient-forward
# textures + motifs, slow tempo, long reverb, sparse lead, ``ambient`` arrangement arc,
# softer arp–melody coupling. Older Matsutake OST baseline remains ``ambient01``.
_PRESET_DEFAULT_AMBIENT_01: Dict[str, Any] = deepcopy(_PRESET_MATUSAKE_AMBIENT)
_PRESET_DEFAULT_AMBIENT_01["emotion_pool"] = [
    "serenity",
    "neutral",
    "realization",
    "sadness",
    "curiosity",
    "remorse",
    "optimism",
]
_PRESET_DEFAULT_AMBIENT_01["emotion_weights"] = {
    "serenity": 3.2,
    "neutral": 2.8,
    "sadness": 2.4,
    "realization": 2.2,
    "curiosity": 1.8,
    "remorse": 1.4,
    "optimism": 1.0,
}
_PRESET_DEFAULT_AMBIENT_01["root_pool"] = [52, 55, 57, 60, 64]
_PRESET_DEFAULT_AMBIENT_01["root_weights"] = {
    55: 2.8,
    52: 2.2,
    57: 2.0,
    60: 1.5,
    64: 1.2,
}
_da01_comp = dict(_PRESET_DEFAULT_AMBIENT_01.get("composition") or {})
_da01_comp.update(
    {
        # AmosRoddy-like full-song pacing: slow tempo, long sections, gradual evolution, strong motif lifecycle.
        "default_tempo": 70.0,
        "global_tempo_scale": 1.0,
        "bars_per_section": 8,
        "arranged_song_mode": "snowfall",
        "bass_density": 1.15,
        "force_change_prob": 0.08,
        "embellishment_prob": 0.08,
        "extension_prob": 0.50,
        # Ensure *some* sections pick progressions that already contain 7/9/11/13 (and friends),
        # instead of relying only on post-processing extension injection.
        "prefer_extension_rich_progressions_prob": 0.55,
        "interchange_prob": 0.10,
        # More memorable themes: stronger motif reuse, less wandering variation.
        "motif_variation_prob": 0.08,
        "motif_use_chance": 0.92,
        "cross_lane_motif_bus_strength": 0.78,
        "motif_lifecycle_strength": 0.82,
        "arp_motif_coupling_enabled": True,
        "arp_motif_coupling_strength": 0.56,
        "arp_to_melody_motif_feedback_enabled": True,
        "arp_to_melody_motif_feedback_prob": 0.32,
        "texture_fx_gesture_strength": 0.26,
        # Deterministic timing: keep all generators locked to the same grid.
        # (Humanization makes lanes drift relative to each other.)
        "humanization_enabled": False,
        "humanization_amount": 0.0,
        # Default ambient: lean bed-forward (Strobe-like) — fewer lead notes, steadier arp bed.
        "melody_amount_scale": 0.55,
        "melody_rest_prob_mult": 1.15,
        # Keep melodies hook-forward: allow longer literal restatements before forcing a break.
        "melody_break_repeat_max": 10,
        # Reduce section-level novelty picking so phrases feel more "written" than re-rolled.
        "section_sampler_novelty_enabled": False,
        "section_sampler_novelty_weight": 0.0,
        "section_sampler_chord_novelty_weight": 0.0,
        "section_sampler_register_novelty_weight": 0.0,
        "chorus_hook_composer_enabled": True,
        "chorus_hook_composer_strength": 0.82,
        "cadence_contracts_enabled": True,
        "cadence_contracts_strength": 0.84,
        # Lower temperature drift across bars so the topline doesn't "random-walk".
        "melody_bar_temperature_scaling_strength": 0.12,
        "melody_bar_temperature_mult_min": 0.78,
        "melody_bar_temperature_mult_max": 1.08,
        # Stronger hook grid alignment (more consistent rhythm + recognizable contour).
        "motif_melody_alignment_strength": 0.55,
        # Prefer cleaner voiceleading to reduce meandering leaps.
        "melody_voiceleading_rerank_strength": 0.82,
        # Tighten chord-tone pressure for "written" melodies.
        "melody_harmony_agreement_preset": "tight",
        "chorus_melody_duck_with_arp": 0.92,
        "melody_arp_call_response_delay_enabled": True,
        "melody_arp_occupied_masking_enabled": True,
        "melody_arp_occupied_weight_global_scale": 0.62,
        "arp_melody_register_separation_semitones": 9,
        "arp_lane_offset_from_melody": -3,
        "swing_enabled": False,
        "swing_amount": 0.0,
        "melody_swing_enabled": False,
        "melody_swing_amount": 0.0,
        # Key lock disabled by default (2026-07-04): pinning every emotion to C major/
        # A minor was the actual cause of "every generation sounds the same key" --
        # per-song key variation (composition_config.key_variation_enabled) now handles
        # variety instead. Re-enable here if smooth emotion-to-emotion key transitions
        # become more important than per-song variety.
        "key_lock_enabled": False,
        "key_lock_major_root_midi": 60,  # C4
        "key_lock_minor_root_midi": 57,  # A3
        "key_lock_major_scale_intervals": [0, 2, 4, 5, 7, 9, 11],
        "key_lock_minor_scale_intervals": [0, 2, 3, 5, 7, 8, 10],
        # Arp: occasional sustained tonic/fifth note one octave up (bar-length).
        "arp_tonic_fifth_drone_note_enabled": True,
        "arp_tonic_fifth_drone_note_prob": 0.42,
        "arp_tonic_fifth_drone_note_octave_semitones": 12,
        # Arp identity: deterministic per-bar onset patterns (helps “loop that evolves” feel).
        "arp_rhythm_cells_enabled": True,
        "arp_rhythm_cells_strength": 1.0,
        # Keep arp density steady even when melody is busy.
        "arp_density_follow_melody": 0.0,
        # Prefer a denser arp bed with a sparser lead.
        "arp_melody_coupling_mode": "call_response_strong",
        # Subtle anticipation color on the last step of the bar (forward-leaning harmony).
        "arp_next_bar_last_step_hint_prob": 0.14,
        # Grid-based masking: make call/response feel intentional on the arp grid.
        "masking_grid_enabled": True,
        "masking_grid_strength": 0.72,
        # Keep chord voicings more “looped pad” stable across sections.
        "chord_register_anchor_strength": 0.72,
        "joint_generation_enabled": True,
        "joint_generation_max_iters": 2,
        "section_k_samples": 4,
        "section_pick_time_budget_s": 1.0,
        "section_pick_use_wall_clock": True,
        "pop_arrangement_strength": 0.0,
        "pop_hook_scoring_strength": 0.0,
    }
)
_PRESET_DEFAULT_AMBIENT_01["composition"] = _da01_comp
_da01_audio = dict(_PRESET_DEFAULT_AMBIENT_01.get("audio") or {})
_da01_audio["reverb_wet"] = 0.80
_da01_audio["reverb_rt60"] = 20.8
_da01_audio["reverb_damping"] = 0.62
# Make delay more prominent by default (audible echoes, not just subtle thickness).
# Per-channel delay sends already exist in the default mixer strips; this primarily lifts the return.
_da01_audio["delay_bus_enabled"] = True
_da01_audio["delay_bus_return_level"] = 0.50
_da01_audio["delay_bus_feedback"] = 0.30
_da01_audio["delay_bus_time_ms"] = 420.0
_da01_audio["delay_bus_pingpong"] = 0.55
_PRESET_DEFAULT_AMBIENT_01["audio"] = _da01_audio

BUILTIN_CONVERSATION_PRESETS = {
    "default_ambient_01": deepcopy(_PRESET_DEFAULT_AMBIENT_01),
}


def _normalize_preset(preset):
    normalized = deepcopy(preset)
    if "channel_mix" in normalized:
        normalized["channel_mix"] = {
            int(channel): values for channel, values in normalized["channel_mix"].items()
        }
    if "root_weights" in normalized:
        normalized["root_weights"] = {
            int(root): weight for root, weight in normalized["root_weights"].items()
        }
    if "root_pool" in normalized:
        normalized["root_pool"] = [int(root) for root in normalized["root_pool"]]
    return normalized


def load_user_conversation_presets():
    if not USER_PRESETS_PATH.exists():
        return {}
    with USER_PRESETS_PATH.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    return {
        name: _normalize_preset(preset)
        for name, preset in raw.items()
    }


def save_user_conversation_presets(user_presets):
    serializable = {
        name: _normalize_preset(preset)
        for name, preset in user_presets.items()
    }
    USER_PRESETS_PATH.write_text(
        json.dumps(serializable, indent=2, sort_keys=True),
        encoding="utf-8",
    )


CONVERSATION_PRESETS = deepcopy(BUILTIN_CONVERSATION_PRESETS)
CONVERSATION_PRESETS.update(load_user_conversation_presets())

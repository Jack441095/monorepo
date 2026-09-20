"""Declarative mixing rules knowledge base for automated mixdown system.

Defines default mix parameters (gain targets, high-pass cutoff, EQ curves, dynamics,
stereo width, panning, and spatial sends) for each instrument category, and genre-specific
modifiers to adjust the mix aesthetic accordingly.
"""

from __future__ import annotations

# Standard mix rules for instrument roles (default values for modern balanced mix)
INSTRUMENT_RULES: dict[str, dict] = {
    "kick": {
        "gain_anchor": True,
        "target_peak_dbfs": -6.0,
        "highpass_hz": 25.0,
        "pan": 0.0,
        "stereo_width": 0.0,  # Mono
        "compression": {
            "ratio": 4.0,
            "attack_ms": 20.0,
            "release_ms": 150.0,
            "threshold_db": -16.0,
        },
        "reverb_send": 0.0,
        "reverb_type": "room",
        "reverb_decay_s": 1.0,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "peaking", "freq": 60.0, "gain_db": 1.5, "q": 1.0, "reason": "Kick sub weight"},
            {"type": "peaking", "freq": 350.0, "gain_db": -2.0, "q": 1.5, "reason": "Reduce boxiness/mud"},
            {"type": "peaking", "freq": 3000.0, "gain_db": 2.0, "q": 2.0, "reason": "Beater click definition"},
        ],
    },
    "snare": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -1.5,  # dB relative to kick level
        "highpass_hz": 75.0,
        "pan": 0.0,
        "stereo_width": 0.2,  # Mostly mono, slight width
        "compression": {
            "ratio": 3.5,
            "attack_ms": 15.0,
            "release_ms": 120.0,
            "threshold_db": -12.0,
        },
        "reverb_send": 0.18,
        "reverb_type": "room",
        "reverb_decay_s": 1.2,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "peaking", "freq": 200.0, "gain_db": 1.0, "q": 1.2, "reason": "Snare body/thump"},
            {"type": "peaking", "freq": 600.0, "gain_db": -1.5, "q": 1.0, "reason": "Reduce ringing"},
            {"type": "peaking", "freq": 5000.0, "gain_db": 1.5, "q": 1.5, "reason": "Sizzle/snap"},
        ],
    },
    "hihat": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -12.0,
        "highpass_hz": 300.0,
        "pan": -0.25,  # Slightly left
        "stereo_width": 0.4,
        "compression": None,  # Usually uncompressed
        "reverb_send": 0.08,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "highpass", "freq": 300.0, "q": 0.707, "reason": "Cut hihat low rumble"},
            {"type": "highshelf", "freq": 10000.0, "gain_db": 1.0, "q": 0.707, "reason": "Crisp top end/air"},
        ],
    },
    "percussion": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -8.0,
        "highpass_hz": 150.0,
        "pan": 0.3,   # Slightly right
        "stereo_width": 0.6,
        "compression": {
            "ratio": 2.5,
            "attack_ms": 10.0,
            "release_ms": 80.0,
            "threshold_db": -15.0,
        },
        "reverb_send": 0.18,
        "delay_send": 0.05,
        "eq_character": [
            {"type": "peaking", "freq": 400.0, "gain_db": -2.0, "q": 1.0, "reason": "Clean low-mids"},
            {"type": "highshelf", "freq": 8000.0, "gain_db": 1.0, "q": 0.707, "reason": "Percussion brightness"},
        ],
    },
    "sub_bass": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -1.0,
        "highpass_hz": 20.0,
        "pan": 0.0,
        "stereo_width": 0.0,  # Strict mono
        "compression": {
            "ratio": 4.0,
            "attack_ms": 10.0,
            "release_ms": 200.0,
            "threshold_db": -18.0,
        },
        "reverb_send": 0.0,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "highpass", "freq": 25.0, "q": 0.707, "reason": "Cut subsonic rumble"},
            {"type": "lowpass", "freq": 120.0, "q": 0.707, "reason": "Isolate sub frequencies"},
        ],
    },
    "bass": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -2.0,
        "highpass_hz": 35.0,
        "pan": 0.0,
        "stereo_width": 0.0,  # Mono
        "compression": {
            "ratio": 4.0,
            "attack_ms": 15.0,
            "release_ms": 180.0,
            "threshold_db": -15.0,
        },
        "reverb_send": 0.0,
        "reverb_type": "room",
        "reverb_decay_s": 1.0,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "peaking", "freq": 80.0, "gain_db": 1.0, "q": 1.2, "reason": "Bass punch"},
            {"type": "peaking", "freq": 220.0, "gain_db": -2.0, "q": 1.5, "reason": "Carve out mud"},
            {"type": "peaking", "freq": 800.0, "gain_db": 1.5, "q": 1.0, "reason": "Bass growl/articulation"},
        ],
    },
    "vocal": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": 0.5,  # Sit slightly on top of kick
        "highpass_hz": 90.0,
        "pan": 0.0,
        "stereo_width": 0.25,
        "compression": {
            "ratio": 3.5,
            "attack_ms": 10.0,
            "release_ms": 80.0,
            "threshold_db": -16.0,
        },
        "reverb_send": 0.12,
        "reverb_type": "plate",
        "reverb_decay_s": 1.6,
        "delay_send": 0.10,
        "eq_character": [
            {"type": "highpass", "freq": 90.0, "q": 0.707, "reason": "Clean vocal low-end"},
            {"type": "peaking", "freq": 350.0, "gain_db": -1.5, "q": 1.0, "reason": "Reduce proximity/roominess"},
            {"type": "peaking", "freq": 3200.0, "gain_db": 2.0, "q": 1.5, "reason": "Presence/definition"},
            {"type": "highshelf", "freq": 10000.0, "gain_db": 2.0, "q": 0.707, "reason": "Breath/air"},
        ],
    },
    "backing_vocal": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -6.0,
        "highpass_hz": 120.0,
        "pan": -0.4,  # Panned wide by default
        "stereo_width": 0.8,
        "compression": {
            "ratio": 4.0,
            "attack_ms": 8.0,
            "release_ms": 100.0,
            "threshold_db": -18.0,
        },
        "reverb_send": 0.28,
        "delay_send": 0.15,
        "eq_character": [
            {"type": "highpass", "freq": 120.0, "q": 0.707, "reason": "Avoid mud under lead vocal"},
            {"type": "peaking", "freq": 3000.0, "gain_db": -2.0, "q": 1.0, "reason": "Dipe presence to sit behind"},
            {"type": "highshelf", "freq": 12000.0, "gain_db": 1.5, "q": 0.707, "reason": "BVs air"},
        ],
    },
    "synth_lead": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -4.0,
        "highpass_hz": 100.0,
        "pan": 0.15,
        "stereo_width": 0.6,
        "compression": {
            "ratio": 3.0,
            "attack_ms": 12.0,
            "release_ms": 120.0,
            "threshold_db": -14.0,
        },
        "reverb_send": 0.15,
        "delay_send": 0.12,
        "eq_character": [
            {"type": "highpass", "freq": 100.0, "q": 0.707, "reason": "Avoid bass masking"},
            {"type": "peaking", "freq": 1500.0, "gain_db": 1.5, "q": 1.2, "reason": "Synth bite"},
        ],
    },
    "synth_pad": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -8.0,
        "highpass_hz": 120.0,
        "pan": 0.0,
        "stereo_width": 1.2,  # Very wide
        "compression": None,
        "reverb_send": 0.30,
        "reverb_type": "hall",
        "reverb_decay_s": 3.2,
        "delay_send": 0.08,
        "eq_character": [
            {"type": "highpass", "freq": 120.0, "q": 0.707, "reason": "Clean low end for pads"},
            {"type": "peaking", "freq": 300.0, "gain_db": -2.0, "q": 1.0, "reason": "Reduce pad build-up"},
        ],
    },
    "guitar": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -5.0,
        "highpass_hz": 80.0,
        "pan": -0.35,  # Panned left
        "stereo_width": 0.65,
        "compression": {
            "ratio": 2.5,
            "attack_ms": 20.0,
            "release_ms": 150.0,
            "threshold_db": -12.0,
        },
        "reverb_send": 0.12,
        "delay_send": 0.03,
        "eq_character": [
            {"type": "highpass", "freq": 80.0, "q": 0.707, "reason": "Avoid guitar mud"},
            {"type": "peaking", "freq": 3000.0, "gain_db": 1.0, "q": 1.5, "reason": "Guitar bite"},
        ],
    },
    "keys": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -5.0,
        "highpass_hz": 85.0,
        "pan": 0.35,  # Panned right (opposite guitar)
        "stereo_width": 0.7,
        "compression": {
            "ratio": 2.0,
            "attack_ms": 25.0,
            "release_ms": 180.0,
            "threshold_db": -10.0,
        },
        "reverb_send": 0.20,
        "delay_send": 0.06,
        "eq_character": [
            {"type": "peaking", "freq": 250.0, "gain_db": -1.5, "q": 1.0, "reason": "Carve key boxiness"},
        ],
    },
    "strings": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -7.0,
        "highpass_hz": 90.0,
        "pan": 0.0,
        "stereo_width": 0.9,  # Quite wide
        "compression": None,
        "reverb_send": 0.35,
        "reverb_type": "hall",
        "reverb_decay_s": 3.0,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "highpass", "freq": 90.0, "q": 0.707, "reason": "Clean low strings"},
            {"type": "highshelf", "freq": 8000.0, "gain_db": 1.5, "q": 0.707, "reason": "String sheen"},
        ],
    },
    "brass": {
        # Distinct from "strings": brass wants upfront punch and midrange
        # bite, not a lush, wide, long-reverb pad. Light compression tames
        # swell/stab dynamics without choking the natural attack.
        "gain_anchor": False,
        "target_level_relative_to_anchor": -6.0,
        "highpass_hz": 100.0,
        "pan": 0.0,
        "stereo_width": 0.6,
        "compression": {
            "ratio": 2.5,
            "attack_ms": 12.0,
            "release_ms": 120.0,
            "threshold_db": -14.0,
        },
        "reverb_send": 0.20,
        "reverb_type": "room",
        "reverb_decay_s": 1.4,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "highpass", "freq": 100.0, "q": 0.707, "reason": "Clean low brass rumble"},
            {"type": "peaking", "freq": 500.0, "gain_db": -1.5, "q": 1.2, "reason": "Reduce boxy midrange buildup"},
            {"type": "peaking", "freq": 3000.0, "gain_db": 2.0, "q": 1.5, "reason": "Brass bite/presence"},
        ],
    },
    "fx": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -12.0,
        "highpass_hz": 120.0,
        "pan": 0.45,
        "stereo_width": 0.8,
        "compression": None,
        "reverb_send": 0.25,
        "delay_send": 0.20,
        "eq_character": [
            {"type": "highpass", "freq": 150.0, "q": 0.707, "reason": "Avoid FX rumble"},
        ],
    },
    "ambient": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -15.0,
        "highpass_hz": 150.0,
        "pan": 0.0,
        "stereo_width": 1.5,  # Ambient should be ultra-wide
        "compression": None,
        "reverb_send": 0.40,
        "delay_send": 0.10,
        "eq_character": [],
    },
    "full_drum_bus": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -1.0,
        "highpass_hz": 25.0,
        "pan": 0.0,
        "stereo_width": 0.35,
        "compression": {
            "ratio": 2.5,
            "attack_ms": 30.0,
            "release_ms": 100.0,
            "threshold_db": -14.0,
        },
        "reverb_send": 0.05,
        "delay_send": 0.0,
        "eq_character": [
            {"type": "peaking", "freq": 60.0, "gain_db": 1.0, "q": 1.0, "reason": "Drum bus weight"},
            {"type": "peaking", "freq": 400.0, "gain_db": -1.5, "q": 1.0, "reason": "Clean drum low-mids"},
        ],
    },
    "other": {
        "gain_anchor": False,
        "target_level_relative_to_anchor": -8.0,
        "highpass_hz": 100.0,
        "pan": 0.0,
        "stereo_width": 0.5,
        "compression": None,
        "reverb_send": 0.10,
        "delay_send": 0.0,
        "eq_character": [],
    },
}

# Instrument priority hierarchy for frequency carving decisions
# Lower number = higher priority (gets to keep its frequencies)
INSTRUMENT_PRIORITY: dict[str, int] = {
    "vocal": 1,
    "kick": 2,
    "snare": 3,
    "bass": 4,
    "sub_bass": 5,
    "synth_lead": 6,
    "guitar": 7,
    "keys": 8,
    "backing_vocal": 9,
    "strings": 10,
    "brass": 7,  # cuts through like guitar/keys, not a background pad like strings
    "synth_pad": 11,
    "full_drum_bus": 12,
    "percussion": 13,
    "hihat": 14,
    "fx": 15,
    "ambient": 16,
    "other": 17,
}


# Genre-specific overrides to modify the standard rules
GENRE_MODIFIERS: dict[str, dict] = {
    "hip_hop": {
        "sub_bass": {"target_level_relative_to_anchor": +1.5, "compression": {"ratio": 4.5, "threshold_db": -20.0}},
        "kick": {"target_peak_dbfs": -4.0, "compression": {"ratio": 5.0, "attack_ms": 25.0}},
        "vocal": {"reverb_send": 0.08, "delay_send": 0.18, "compression": {"ratio": 4.0, "threshold_db": -18.0}},
        "hihat": {"target_level_relative_to_anchor": -8.0},
        "master_bus": {"saturation_db": 1.5, "compression_ratio": 2.0, "multiband_low_hz": 140.0, "multiband_high_hz": 4500.0, "multiband_mid_ratio": 1.8},
    },
    "rock": {
        "guitar": {"target_level_relative_to_anchor": -2.0, "pan": -0.45, "stereo_width": 0.95},
        "snare": {"reverb_send": 0.22, "compression": {"ratio": 4.0, "attack_ms": 12.0}},
        "kick": {"target_peak_dbfs": -5.0},
        "bass": {"target_level_relative_to_anchor": -3.0},
        "vocal": {"reverb_send": 0.14, "delay_send": 0.05},
        "master_bus": {"saturation_db": 0.8, "compression_ratio": 1.5, "multiband_low_hz": 200.0, "multiband_high_hz": 5000.0, "multiband_mid_ratio": 1.6},
    },
    "pop": {
        "vocal": {
            "target_level_relative_to_anchor": +1.5,
            "reverb_send": 0.22,
            "delay_send": 0.15,
            "eq_character": [
                {"type": "highpass", "freq": 95.0, "q": 0.707, "reason": "Avoid vocal rumble"},
                {"type": "peaking", "freq": 3000.0, "gain_db": 3.0, "q": 1.5, "reason": "Pop vocal bite"},
                {"type": "highshelf", "freq": 10000.0, "gain_db": 3.5, "q": 0.707, "reason": "Pop vocal breath/air"},
            ],
        },
        "kick": {"target_peak_dbfs": -5.5},
        "synth_lead": {"target_level_relative_to_anchor": -3.0},
        "master_bus": {"saturation_db": 0.5, "compression_ratio": 2.5, "multiband_low_hz": 180.0, "multiband_high_hz": 5000.0, "multiband_mid_ratio": 1.8},
    },
    "edm": {
        "sub_bass": {"target_level_relative_to_anchor": +1.0, "stereo_width": 0.0},
        "kick": {"target_peak_dbfs": -3.5, "compression": {"ratio": 6.0, "attack_ms": 30.0}},
        "synth_pad": {"stereo_width": 1.5, "reverb_send": 0.35},
        "synth_lead": {"stereo_width": 0.9, "reverb_send": 0.20, "delay_send": 0.20},
        "master_bus": {"saturation_db": 2.0, "compression_ratio": 3.0, "limit_ceiling_db": -0.5, "multiband_low_hz": 120.0, "multiband_high_hz": 4000.0, "multiband_mid_ratio": 2.0},
    },
    "acoustic": {
        "vocal": {"compression": {"ratio": 2.0, "threshold_db": -10.0}, "reverb_send": 0.14},
        "guitar": {"target_level_relative_to_anchor": -3.0, "compression": None, "reverb_send": 0.15},
        "keys": {"compression": None, "reverb_send": 0.22},
        "kick": {"target_peak_dbfs": -8.0, "compression": {"ratio": 2.0, "threshold_db": -8.0}},
        "snare": {"compression": {"ratio": 2.0, "threshold_db": -8.0}, "reverb_send": 0.12},
        "master_bus": {"saturation_db": 0.0, "compression_ratio": 1.2, "multiband_low_hz": 160.0, "multiband_high_hz": 6000.0, "multiband_mid_ratio": 1.4},
    },
    "jazz": {
        "vocal": {"compression": {"ratio": 1.5, "threshold_db": -6.0}, "reverb_send": 0.18},
        "guitar": {"compression": None, "reverb_send": 0.10},
        "keys": {"compression": None, "reverb_send": 0.15},
        "bass": {"target_level_relative_to_anchor": -4.0, "compression": {"ratio": 2.0, "threshold_db": -8.0}},
        "kick": {"target_peak_dbfs": -10.0, "compression": None},
        "snare": {"compression": None},
        "brass": {"compression": None, "reverb_send": 0.15},  # let horn section swells breathe naturally
        "master_bus": {"saturation_db": 0.0, "compression_ratio": 1.0, "multiband_low_hz": 160.0, "multiband_high_hz": 6000.0, "multiband_mid_ratio": 1.2},  # Preservation of natural dynamics
    },
    "cinematic": {
        "strings": {"target_level_relative_to_anchor": -4.0, "reverb_send": 0.45},
        "brass": {"target_level_relative_to_anchor": -5.0, "reverb_send": 0.40, "reverb_type": "hall", "reverb_decay_s": 2.2},
        "ambient": {"reverb_send": 0.50},
        "vocal": {"reverb_send": 0.35, "delay_send": 0.25},
        "master_bus": {"saturation_db": 0.2, "compression_ratio": 1.3, "multiband_low_hz": 150.0, "multiband_high_hz": 5500.0, "multiband_mid_ratio": 1.5},
    },
    "podcast": {
        "vocal": {
            "target_level_relative_to_anchor": 0.0,
            "pan": 0.0,
            "stereo_width": 0.0,  # Mono podcast voice
            "compression": {"ratio": 4.0, "threshold_db": -22.0, "attack_ms": 5.0, "release_ms": 60.0},
            "reverb_send": 0.0,
            "delay_send": 0.0,
            "eq_character": [
                {"type": "highpass", "freq": 90.0, "q": 0.707, "reason": "Avoid vocal rumble"},
                {"type": "peaking", "freq": 250.0, "gain_db": -2.0, "q": 1.0, "reason": "Cut mud/room resonance"},
                {"type": "peaking", "freq": 2500.0, "gain_db": 1.5, "q": 1.5, "reason": "Speech intelligibility"},
            ],
        },
        "other": {"target_level_relative_to_anchor": -18.0},
        "bg_music": {"target_level_relative_to_anchor": -20.0},
        "master_bus": {"saturation_db": 0.0, "compression_ratio": 3.0, "target_lufs": -16.0, "multiband_low_hz": 180.0, "multiband_high_hz": 5000.0, "multiband_mid_ratio": 1.8},
    },
}


def get_rule_for_instrument(instrument: str, genre: str | None = None) -> dict:
    """Get the merged rule configuration for a specific instrument and genre.

    Combines standard rules with genre modifications.
    """
    # Start with a copy of the default instrument rules
    base = INSTRUMENT_RULES.get(instrument, INSTRUMENT_RULES["other"]).copy()
    
    # Handle nested dictionaries in copy
    if "compression" in base and base["compression"] is not None:
        base["compression"] = base["compression"].copy()
    if "eq_character" in base:
        base["eq_character"] = [x.copy() for x in base["eq_character"]]

    if not genre or genre not in GENRE_MODIFIERS:
        return base

    genre_mod = GENRE_MODIFIERS[genre]
    if instrument in genre_mod:
        instrument_mod = genre_mod[instrument]
        for key, val in instrument_mod.items():
            if isinstance(val, dict) and key in base and isinstance(base[key], dict):
                # Merge nested dictionaries (like compression)
                base[key].update(val)
            else:
                base[key] = val

    return base

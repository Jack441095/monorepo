"""KENN Dynamic Audio Effect Rack Builder for Ableton Live 12.

Constructs pre-calibrated multi-chain Audio Effect Racks with automatic
8-macro knob assignment, bounded parameter ranges, target device parameter
bindings, and multi-state macro variation snapshots.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SCHEMA = "kenn.audio_effect_rack_proposal.v1"

RACK_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "neuro_bass_rack": {
        "id": "neuro_bass_rack",
        "name": "Neuro Bass Parallel Multi-Band Rack",
        "category": "bass",
        "description": "3-way frequency split: mono clean sub, saturated mid bite with Roar, and dimensional stereo high air.",
        "target_track_type": "bass",
        "chains": [
            {
                "name": "Sub Clean",
                "frequency_range": "20 - 90 Hz",
                "devices": [
                    {"name": "Utility", "parameters": {"mono": True, "bass_mono": True, "bass_mono_freq": 90.0}},
                    {"name": "Compressor", "parameters": {"ratio": 4.0, "attack": 15.0, "release": 60.0}},
                ],
            },
            {
                "name": "Mid Grunt",
                "frequency_range": "90 - 3500 Hz",
                "devices": [
                    {"name": "Roar", "parameters": {"drive": 6.5, "tone": 0.5, "routing": 0}},
                    {"name": "Auto Filter", "parameters": {"frequency": 850.0, "resonance": 1.8}},
                ],
            },
            {
                "name": "High Air",
                "frequency_range": "3500 - 20000 Hz",
                "devices": [
                    {"name": "Chorus-Ensemble", "parameters": {"rate": 0.8, "amount": 0.45}},
                    {"name": "Hybrid Reverb", "parameters": {"decay_time": 1.2, "dry_wet": 0.20}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Sub/Mid Balance", "default": 0.50, "unit": "norm", "min": 0.0, "max": 1.0, "target_device": "Chain Faders", "target_parameter": "Chain Balance"},
            {"index": 1, "name": "Roar Drive", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.85, "target_device": "Roar", "target_parameter": "Drive"},
            {"index": 2, "name": "Filter Cutoff", "default": 0.60, "unit": "norm", "min": 0.1, "max": 0.95, "target_device": "Auto Filter", "target_parameter": "Frequency"},
            {"index": 3, "name": "Filter Reso", "default": 0.35, "unit": "norm", "min": 0.0, "max": 0.75, "target_device": "Auto Filter", "target_parameter": "Resonance"},
            {"index": 4, "name": "Stereo Width", "default": 0.50, "unit": "norm", "min": 0.0, "max": 1.0, "target_device": "Chorus-Ensemble", "target_parameter": "Width"},
            {"index": 5, "name": "Reverb Space", "default": 0.20, "unit": "norm", "min": 0.0, "max": 0.50, "target_device": "Hybrid Reverb", "target_parameter": "Dry/Wet"},
            {"index": 6, "name": "Sub Punch", "default": 0.45, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "Compressor", "target_parameter": "Threshold"},
            {"index": 7, "name": "Master Out", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.50, 0.40, 0.60, 0.35, 0.50, 0.20, 0.45, 0.85]},
            {"name": "Heavy Distortion", "macro_values": [0.40, 0.80, 0.75, 0.60, 0.70, 0.30, 0.60, 0.80]},
            {"name": "Deep Sub Focus", "macro_values": [0.75, 0.20, 0.40, 0.20, 0.25, 0.10, 0.70, 0.85]},
        ],
    },
    "nyc_drum_crush_rack": {
        "id": "nyc_drum_crush_rack",
        "name": "NYC Parallel Drum Crush Rack",
        "category": "drums",
        "description": "New York style parallel dynamic crusher combining uncompressed transients with heavily saturated Glue Compressor punch.",
        "target_track_type": "drums",
        "chains": [
            {
                "name": "Dry Direct",
                "frequency_range": "full",
                "devices": [
                    {"name": "Utility", "parameters": {"gain": 0.0}},
                ],
            },
            {
                "name": "Crush Parallel",
                "frequency_range": "full",
                "devices": [
                    {"name": "Glue Compressor", "parameters": {"ratio": 10.0, "attack": 0.1, "release": 0.2, "dry_wet": 1.0}},
                    {"name": "Saturator", "parameters": {"drive": 4.5, "color": 0.3}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Crush Blend", "default": 0.35, "unit": "norm", "min": 0.0, "max": 0.70, "target_device": "Crush Parallel Chain", "target_parameter": "Volume"},
            {"index": 1, "name": "Glue Thresh", "default": 0.55, "unit": "norm", "min": 0.1, "max": 0.90, "target_device": "Glue Compressor", "target_parameter": "Threshold"},
            {"index": 2, "name": "Sat Drive", "default": 0.30, "unit": "norm", "min": 0.0, "max": 0.75, "target_device": "Saturator", "target_parameter": "Drive"},
            {"index": 3, "name": "Kick Sub", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "EQ Eight", "target_parameter": "Band 1 Gain"},
            {"index": 4, "name": "Snare Crack", "default": 0.60, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "EQ Eight", "target_parameter": "Band 4 Gain"},
            {"index": 5, "name": "Hat Air", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.70, "target_device": "EQ Eight", "target_parameter": "Band 8 Gain"},
            {"index": 6, "name": "Soft Clip", "default": 1.0, "unit": "toggle", "min": 0.0, "max": 1.0, "target_device": "Saturator", "target_parameter": "Soft Clip"},
            {"index": 7, "name": "Mix Headroom", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.35, 0.55, 0.30, 0.50, 0.60, 0.40, 1.0, 0.85]},
            {"name": "Aggressive Smash", "macro_values": [0.65, 0.80, 0.65, 0.60, 0.75, 0.55, 1.0, 0.80]},
            {"name": "Subtle Glue", "macro_values": [0.20, 0.40, 0.15, 0.50, 0.50, 0.30, 0.0, 0.88]},
        ],
    },
    "vocal_presence_strip": {
        "id": "vocal_presence_strip",
        "name": "Modern Vocal Presence & Air Strip",
        "category": "vocals",
        "description": "Multi-stage vocal chain: low-cut cleanup, 300 Hz de-mud, optical leveling, 3 kHz presence, and 12 kHz air shelf.",
        "target_track_type": "vocals",
        "chains": [
            {
                "name": "Vocal Core",
                "frequency_range": "full",
                "devices": [
                    {"name": "EQ Eight", "parameters": {"band1_hp": 85.0, "band3_cut": 280.0, "band5_boost": 3200.0, "band8_shelf": 12500.0}},
                    {"name": "Compressor", "parameters": {"ratio": 3.0, "attack": 20.0, "release": 80.0}},
                    {"name": "Saturator", "parameters": {"drive": 1.5, "curve": "soft_sine"}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Vocal Clarity", "default": 0.55, "unit": "norm", "min": 0.1, "max": 0.90, "target_device": "EQ Eight", "target_parameter": "Band 5 Gain"},
            {"index": 1, "name": "Air Sparkle", "default": 0.50, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "EQ Eight", "target_parameter": "Band 8 Gain"},
            {"index": 2, "name": "De-Mud Trim", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.70, "target_device": "EQ Eight", "target_parameter": "Band 3 Cut"},
            {"index": 3, "name": "Opto Level", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "Compressor", "target_parameter": "Threshold"},
            {"index": 4, "name": "Tube Warmth", "default": 0.30, "unit": "norm", "min": 0.0, "max": 0.60, "target_device": "Saturator", "target_parameter": "Drive"},
            {"index": 5, "name": "Space Depth", "default": 0.25, "unit": "norm", "min": 0.0, "max": 0.55, "target_device": "Hybrid Reverb", "target_parameter": "Dry/Wet"},
            {"index": 6, "name": "Width Spread", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "Chorus-Ensemble", "target_parameter": "Amount"},
            {"index": 7, "name": "Output Trim", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.55, 0.50, 0.40, 0.50, 0.30, 0.25, 0.40, 0.85]},
            {"name": "Bright Radio Vox", "macro_values": [0.75, 0.70, 0.55, 0.65, 0.40, 0.35, 0.50, 0.82]},
            {"name": "Warm Intimate", "macro_values": [0.40, 0.30, 0.25, 0.40, 0.50, 0.15, 0.20, 0.88]},
        ],
    },
    "neuro_reese_saturator": {
        "id": "neuro_reese_saturator",
        "name": "Neuro Reese Motion & Drive",
        "category": "bass",
        "description": "Multi-stage Roar distortion with synced Auto Filter notch movement and chorus widening for heavy neuro/DnB basslines.",
        "target_track_type": "bass",
        "chains": [
            {
                "name": "Sub Layer",
                "frequency_range": "20 - 90 Hz",
                "devices": [
                    {"name": "Utility", "parameters": {"mono": True, "bass_mono": True, "bass_mono_freq": 90.0}},
                ],
            },
            {
                "name": "Roar Reese Motion",
                "frequency_range": "90 - 20000 Hz",
                "devices": [
                    {"name": "Roar", "parameters": {"drive": 8.0, "tone": 0.45, "feedback": 0.25}},
                    {"name": "Auto Filter", "parameters": {"frequency": 1200.0, "resonance": 2.2, "lfo_rate": "1/4"}},
                    {"name": "Chorus-Ensemble", "parameters": {"rate": 0.4, "amount": 0.60}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Roar Drive", "default": 0.55, "unit": "norm", "min": 0.1, "max": 0.95, "target_device": "Roar", "target_parameter": "Drive"},
            {"index": 1, "name": "Roar Tone", "default": 0.50, "unit": "norm", "min": 0.0, "max": 1.0, "target_device": "Roar", "target_parameter": "Tone"},
            {"index": 2, "name": "Notch Speed", "default": 0.45, "unit": "norm", "min": 0.1, "max": 0.90, "target_device": "Auto Filter", "target_parameter": "LFO Rate"},
            {"index": 3, "name": "Notch Reso", "default": 0.60, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "Auto Filter", "target_parameter": "Resonance"},
            {"index": 4, "name": "Stereo Spread", "default": 0.65, "unit": "norm", "min": 0.0, "max": 1.0, "target_device": "Chorus-Ensemble", "target_parameter": "Amount"},
            {"index": 5, "name": "Sub Mono Level", "default": 0.70, "unit": "norm", "min": 0.3, "max": 1.0, "target_device": "Sub Layer Chain", "target_parameter": "Volume"},
            {"index": 6, "name": "Feedback Grunt", "default": 0.30, "unit": "norm", "min": 0.0, "max": 0.60, "target_device": "Roar", "target_parameter": "Feedback"},
            {"index": 7, "name": "Master Trim", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.55, 0.50, 0.45, 0.60, 0.65, 0.70, 0.30, 0.85]},
            {"name": "Hyper Crushed", "macro_values": [0.90, 0.65, 0.70, 0.80, 0.85, 0.65, 0.50, 0.80]},
            {"name": "Subtle Rolling", "macro_values": [0.35, 0.40, 0.30, 0.40, 0.45, 0.85, 0.10, 0.88]},
        ],
    },
    "ott_drum_smasher": {
        "id": "ott_drum_smasher",
        "name": "OTT Aggressive Drum Smasher",
        "category": "drums",
        "description": "Multi-band upward/downward dynamic compression with soft-clip saturation for hyper-dense modern electronic drums.",
        "target_track_type": "drums",
        "chains": [
            {
                "name": "Dry Direct",
                "frequency_range": "full",
                "devices": [{"name": "Utility", "parameters": {"gain": 0.0}}],
            },
            {
                "name": "OTT Smashed",
                "frequency_range": "full",
                "devices": [
                    {"name": "Multiband Dynamics", "parameters": {"preset": "OTT", "dry_wet": 0.75, "time": 1.0}},
                    {"name": "Saturator", "parameters": {"drive": 3.0, "soft_clip": True}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "OTT Depth", "default": 0.65, "unit": "norm", "min": 0.1, "max": 1.0, "target_device": "Multiband Dynamics", "target_parameter": "Amount"},
            {"index": 1, "name": "Upward Push", "default": 0.50, "unit": "norm", "min": 0.0, "max": 0.90, "target_device": "Multiband Dynamics", "target_parameter": "Upward Comp"},
            {"index": 2, "name": "Downward Clamp", "default": 0.55, "unit": "norm", "min": 0.1, "max": 0.95, "target_device": "Multiband Dynamics", "target_parameter": "Downward Comp"},
            {"index": 3, "name": "Sat Color", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "Saturator", "target_parameter": "Drive"},
            {"index": 4, "name": "High Band Bias", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "Multiband Dynamics", "target_parameter": "High Gain"},
            {"index": 5, "name": "Mid Band Punch", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "Multiband Dynamics", "target_parameter": "Mid Gain"},
            {"index": 6, "name": "Parallel Mix", "default": 0.50, "unit": "norm", "min": 0.1, "max": 0.85, "target_device": "OTT Smashed Chain", "target_parameter": "Volume"},
            {"index": 7, "name": "Final Headroom", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.65, 0.50, 0.55, 0.40, 0.50, 0.50, 0.50, 0.85]},
            {"name": "Wall of Sound", "macro_values": [0.95, 0.80, 0.85, 0.70, 0.65, 0.60, 0.75, 0.80]},
            {"name": "Transient Polish", "macro_values": [0.35, 0.30, 0.35, 0.20, 0.50, 0.50, 0.30, 0.88]},
        ],
    },
    "midside_stereo_widener": {
        "id": "midside_stereo_widener",
        "name": "Mid-Side Spatializer & Sculptor",
        "category": "spatial",
        "description": "Precision mid/side processor: maintains solid mono center while widening and brightening stereo sides.",
        "target_track_type": "synths",
        "chains": [
            {
                "name": "Mid Center",
                "frequency_range": "mono",
                "devices": [
                    {"name": "Utility", "parameters": {"mono": True}},
                    {"name": "EQ Eight", "parameters": {"band1_hp": 60.0}},
                ],
            },
            {
                "name": "Side Wings",
                "frequency_range": "side",
                "devices": [
                    {"name": "EQ Eight", "parameters": {"band1_hp": 150.0, "band8_shelf": 10000.0, "band8_gain": 2.5}},
                    {"name": "Delay", "parameters": {"time_l": "1.0 ms", "time_r": "8.5 ms", "dry_wet": 0.35}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Side Width", "default": 0.60, "unit": "norm", "min": 0.0, "max": 1.0, "target_device": "Side Wings Chain", "target_parameter": "Volume"},
            {"index": 1, "name": "Side Air Boost", "default": 0.50, "unit": "norm", "min": 0.0, "max": 0.85, "target_device": "EQ Eight", "target_parameter": "Band 8 Gain"},
            {"index": 2, "name": "Side Low Cut", "default": 0.40, "unit": "norm", "min": 0.1, "max": 0.80, "target_device": "EQ Eight", "target_parameter": "Band 1 HP"},
            {"index": 3, "name": "Center Focus", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "Mid Center Chain", "target_parameter": "Volume"},
            {"index": 4, "name": "Micro Delay L", "default": 0.10, "unit": "norm", "min": 0.0, "max": 0.50, "target_device": "Delay", "target_parameter": "Delay L"},
            {"index": 5, "name": "Micro Delay R", "default": 0.45, "unit": "norm", "min": 0.0, "max": 0.70, "target_device": "Delay", "target_parameter": "Delay R"},
            {"index": 6, "name": "Mono Center Lows", "default": 1.0, "unit": "toggle", "min": 0.0, "max": 1.0, "target_device": "Utility", "target_parameter": "Bass Mono"},
            {"index": 7, "name": "Master Level", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.60, 0.50, 0.40, 0.50, 0.10, 0.45, 1.0, 0.85]},
            {"name": "Ultra Wide Shimmer", "macro_values": [0.85, 0.75, 0.50, 0.40, 0.20, 0.65, 1.0, 0.82]},
            {"name": "Natural Room Spread", "macro_values": [0.35, 0.30, 0.30, 0.65, 0.05, 0.25, 1.0, 0.88]},
        ],
    },
    "clean_808_saturator": {
        "id": "clean_808_saturator",
        "name": "Clean 808 Sub-Harmonic Warmer",
        "category": "bass",
        "description": "Pedal-driven sub-bass saturator with mono sub clamping under 90 Hz and upper-harmonic clarity for phone speaker audibility.",
        "target_track_type": "bass",
        "chains": [
            {
                "name": "Sub Mono 808",
                "frequency_range": "20 - 90 Hz",
                "devices": [
                    {"name": "Utility", "parameters": {"mono": True, "bass_mono": True, "bass_mono_freq": 90.0}},
                    {"name": "Glue Compressor", "parameters": {"attack": 30.0, "release": 0.1, "ratio": 4.0}},
                ],
            },
            {
                "name": "Harmonic Overtones",
                "frequency_range": "90 - 4000 Hz",
                "devices": [
                    {"name": "Pedal", "parameters": {"type": "OD", "gain": 4.0, "bass": 0.0, "mid": 2.0, "treble": -2.0}},
                    {"name": "Saturator", "parameters": {"drive": 2.0, "soft_clip": True}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Overdrive Heat", "default": 0.45, "unit": "norm", "min": 0.0, "max": 0.85, "target_device": "Pedal", "target_parameter": "Gain"},
            {"index": 1, "name": "Mid Bite (Audibility)", "default": 0.50, "unit": "norm", "min": 0.1, "max": 0.85, "target_device": "Pedal", "target_parameter": "Mid"},
            {"index": 2, "name": "Sub Weight", "default": 0.65, "unit": "norm", "min": 0.3, "max": 0.95, "target_device": "Sub Mono 808 Chain", "target_parameter": "Volume"},
            {"index": 3, "name": "Harmonic Mix", "default": 0.35, "unit": "norm", "min": 0.0, "max": 0.75, "target_device": "Harmonic Overtones Chain", "target_parameter": "Volume"},
            {"index": 4, "name": "Attack Punch", "default": 0.40, "unit": "norm", "min": 0.1, "max": 0.80, "target_device": "Glue Compressor", "target_parameter": "Attack"},
            {"index": 5, "name": "Soft Clip Warmth", "default": 0.50, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "Saturator", "target_parameter": "Drive"},
            {"index": 6, "name": "Tight Sub Cut", "default": 0.25, "unit": "norm", "min": 0.0, "max": 0.60, "target_device": "Utility", "target_parameter": "Bass Mono Freq"},
            {"index": 7, "name": "808 Output", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.45, 0.50, 0.65, 0.35, 0.40, 0.50, 0.25, 0.85]},
            {"name": "Distorted Trap 808", "macro_values": [0.80, 0.75, 0.55, 0.65, 0.60, 0.80, 0.25, 0.80]},
            {"name": "Deep Pure Sine", "macro_values": [0.10, 0.15, 0.85, 0.10, 0.20, 0.15, 0.25, 0.88]},
        ],
    },
    "dynamic_vocal_air": {
        "id": "dynamic_vocal_air",
        "name": "Dynamic Vocal Bloom & Air",
        "category": "vocals",
        "description": "High-end sheen and blooming reverb space with intelligent dynamic ducking on vocal phrases.",
        "target_track_type": "vocals",
        "chains": [
            {
                "name": "Vocal Dry Clean",
                "frequency_range": "full",
                "devices": [{"name": "EQ Eight", "parameters": {"band8_shelf": 12000.0, "band8_gain": 3.0}}],
            },
            {
                "name": "Air Bloom Space",
                "frequency_range": "high-air",
                "devices": [
                    {"name": "Hybrid Reverb", "parameters": {"decay_time": 2.4, "dry_wet": 1.0, "freeze": False}},
                    {"name": "Compressor", "parameters": {"sidechain": True, "ratio": 4.0, "threshold": -18.0}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Air Sheen", "default": 0.55, "unit": "norm", "min": 0.1, "max": 0.90, "target_device": "EQ Eight", "target_parameter": "Band 8 Gain"},
            {"index": 1, "name": "Bloom Reverb Amount", "default": 0.30, "unit": "norm", "min": 0.0, "max": 0.70, "target_device": "Air Bloom Space Chain", "target_parameter": "Volume"},
            {"index": 2, "name": "Reverb Decay", "default": 0.45, "unit": "norm", "min": 0.1, "max": 0.85, "target_device": "Hybrid Reverb", "target_parameter": "Decay Time"},
            {"index": 3, "name": "Ducking Depth", "default": 0.60, "unit": "norm", "min": 0.1, "max": 0.95, "target_device": "Compressor", "target_parameter": "Threshold"},
            {"index": 4, "name": "Ducking Recovery", "default": 0.40, "unit": "norm", "min": 0.1, "max": 0.80, "target_device": "Compressor", "target_parameter": "Release"},
            {"index": 5, "name": "Low-Cut Reverb", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "Hybrid Reverb", "target_parameter": "Low Cut"},
            {"index": 6, "name": "Stereo Spread", "default": 0.70, "unit": "norm", "min": 0.2, "max": 1.0, "target_device": "Hybrid Reverb", "target_parameter": "Stereo Width"},
            {"index": 7, "name": "Vocal Master Out", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.55, 0.30, 0.45, 0.60, 0.40, 0.50, 0.70, 0.85]},
            {"name": "Ethereal Cloud", "macro_values": [0.70, 0.60, 0.80, 0.35, 0.60, 0.40, 0.90, 0.80]},
            {"name": "Dry Tight Pop", "macro_values": [0.60, 0.12, 0.25, 0.80, 0.25, 0.65, 0.50, 0.88]},
        ],
    },
    "lofi_tape_warmer": {
        "id": "lofi_tape_warmer",
        "name": "Lo-Fi Vintage Cassette Warmer",
        "category": "color",
        "description": "Analog cassette tape coloration rack with subtle wow/flutter pitch modulation, tube warmth, and vintage bandwidth shaping.",
        "target_track_type": "master",
        "chains": [
            {
                "name": "Cassette Path",
                "frequency_range": "300 - 4500 Hz",
                "devices": [
                    {"name": "EQ Eight", "parameters": {"band1_hp": 220.0, "band8_lp": 6500.0}},
                    {"name": "Saturator", "parameters": {"drive": 3.0, "curve": "analog_clip"}},
                    {"name": "Vinyl Distortion", "parameters": {"crackle": 0.15, "tracing_dist": 0.30}},
                    {"name": "Echo", "parameters": {"time": "1 ms", "feedback": 0.0, "mod_rate": 0.4, "mod_amount": 0.35}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Tape Saturation", "default": 0.45, "unit": "norm", "min": 0.0, "max": 0.85, "target_device": "Saturator", "target_parameter": "Drive"},
            {"index": 1, "name": "Tape Flutter", "default": 0.35, "unit": "norm", "min": 0.0, "max": 0.75, "target_device": "Echo", "target_parameter": "Modulation Amount"},
            {"index": 2, "name": "Cassette Bandwidth", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.90, "target_device": "EQ Eight", "target_parameter": "Band 8 LP"},
            {"index": 3, "name": "Vinyl Dust & Hiss", "default": 0.20, "unit": "norm", "min": 0.0, "max": 0.60, "target_device": "Vinyl Distortion", "target_parameter": "Crackle"},
            {"index": 4, "name": "Analog Color", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "Vinyl Distortion", "target_parameter": "Tracing"},
            {"index": 5, "name": "Sub Bass Roll-off", "default": 0.30, "unit": "norm", "min": 0.0, "max": 0.70, "target_device": "EQ Eight", "target_parameter": "Band 1 HP"},
            {"index": 6, "name": "Dry/Tape Blend", "default": 0.70, "unit": "norm", "min": 0.2, "max": 1.0, "target_device": "Audio Effect Rack", "target_parameter": "Dry/Wet"},
            {"index": 7, "name": "Output Trim", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.45, 0.35, 0.50, 0.20, 0.40, 0.30, 0.70, 0.85]},
            {"name": "Worn Out Tape", "macro_values": [0.75, 0.70, 0.30, 0.55, 0.70, 0.50, 1.00, 0.80]},
            {"name": "Subtle Analog Vibe", "macro_values": [0.25, 0.15, 0.75, 0.05, 0.20, 0.15, 0.45, 0.88]},
        ],
    },
    "parallel_glue_punch": {
        "id": "parallel_glue_punch",
        "name": "Parallel Master & Bus Glue Punch",
        "category": "master",
        "description": "Bus glue rack preserving sharp dynamic transients while providing parallel high-ratio peak control.",
        "target_track_type": "master",
        "chains": [
            {
                "name": "Direct Unprocessed",
                "frequency_range": "full",
                "devices": [{"name": "Utility", "parameters": {"gain": 0.0}}],
            },
            {
                "name": "Parallel Glue Squeeze",
                "frequency_range": "full",
                "devices": [
                    {"name": "Glue Compressor", "parameters": {"attack": 30.0, "release": 0.2, "ratio": 10.0, "dry_wet": 1.0}},
                    {"name": "Utility", "parameters": {"gain": 2.0}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Parallel Punch Blend", "default": 0.30, "unit": "norm", "min": 0.0, "max": 0.65, "target_device": "Parallel Glue Squeeze Chain", "target_parameter": "Volume"},
            {"index": 1, "name": "Compression Threshold", "default": 0.50, "unit": "norm", "min": 0.1, "max": 0.90, "target_device": "Glue Compressor", "target_parameter": "Threshold"},
            {"index": 2, "name": "Glue Attack Speed", "default": 0.70, "unit": "norm", "min": 0.2, "max": 1.0, "target_device": "Glue Compressor", "target_parameter": "Attack"},
            {"index": 3, "name": "Release Recovery", "default": 0.30, "unit": "norm", "min": 0.1, "max": 0.85, "target_device": "Glue Compressor", "target_parameter": "Release"},
            {"index": 4, "name": "Sidechain Highpass", "default": 0.40, "unit": "norm", "min": 0.1, "max": 0.80, "target_device": "Glue Compressor", "target_parameter": "Sidechain HP"},
            {"index": 5, "name": "Makeup Volume", "default": 0.45, "unit": "norm", "min": 0.1, "max": 0.85, "target_device": "Utility", "target_parameter": "Gain"},
            {"index": 6, "name": "Soft Clip Guard", "default": 1.0, "unit": "toggle", "min": 0.0, "max": 1.0, "target_device": "Glue Compressor", "target_parameter": "Soft Clip"},
            {"index": 7, "name": "Master Bus Ceiling", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.30, 0.50, 0.70, 0.30, 0.40, 0.45, 1.0, 0.85]},
            {"name": "Punchy Drum Bus", "macro_values": [0.55, 0.65, 0.85, 0.20, 0.55, 0.60, 1.0, 0.82]},
            {"name": "Gentle Mix Bus", "macro_values": [0.20, 0.35, 0.60, 0.40, 0.30, 0.30, 0.0, 0.88]},
        ],
    },
    "acid_resonance_lead": {
        "id": "acid_resonance_lead",
        "name": "Acid 303 Resonance Lead Rack",
        "category": "synth",
        "description": "Screaming diode distortion, resonant bandpass envelope follower, and sync delay for acid bass and leads.",
        "target_track_type": "synth",
        "chains": [
            {
                "name": "Acid Channel",
                "frequency_range": "full",
                "devices": [
                    {"name": "Roar", "parameters": {"drive": 7.5, "tone": 0.65, "shaper": "diode"}},
                    {"name": "Auto Filter", "parameters": {"filter_type": "bandpass", "frequency": 1400.0, "resonance": 3.2, "envelope": 0.65}},
                    {"name": "Delay", "parameters": {"time_l": "3/16", "time_r": "1/8", "feedback": 0.45, "dry_wet": 0.25}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Cutoff Frequency", "default": 0.45, "unit": "norm", "min": 0.1, "max": 0.95, "target_device": "Auto Filter", "target_parameter": "Frequency"},
            {"index": 1, "name": "Acid Resonance", "default": 0.75, "unit": "norm", "min": 0.3, "max": 0.98, "target_device": "Auto Filter", "target_parameter": "Resonance"},
            {"index": 2, "name": "Envelope Modulation", "default": 0.65, "unit": "norm", "min": 0.1, "max": 1.0, "target_device": "Auto Filter", "target_parameter": "Envelope"},
            {"index": 3, "name": "Diode Roar Drive", "default": 0.60, "unit": "norm", "min": 0.1, "max": 0.95, "target_device": "Roar", "target_parameter": "Drive"},
            {"index": 4, "name": "Roar Tone", "default": 0.55, "unit": "norm", "min": 0.1, "max": 0.90, "target_device": "Roar", "target_parameter": "Tone"},
            {"index": 5, "name": "Echo Feedback", "default": 0.40, "unit": "norm", "min": 0.0, "max": 0.80, "target_device": "Delay", "target_parameter": "Feedback"},
            {"index": 6, "name": "Delay Mix", "default": 0.25, "unit": "norm", "min": 0.0, "max": 0.60, "target_device": "Delay", "target_parameter": "Dry/Wet"},
            {"index": 7, "name": "Output Volume", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.45, 0.75, 0.65, 0.60, 0.55, 0.40, 0.25, 0.85]},
            {"name": "Extreme Acid Squelch", "macro_values": [0.35, 0.95, 0.85, 0.85, 0.70, 0.55, 0.35, 0.80]},
            {"name": "Smooth Pluck", "macro_values": [0.60, 0.40, 0.35, 0.30, 0.40, 0.25, 0.15, 0.88]},
        ],
    },
    "sub_bass_monomaker": {
        "id": "sub_bass_monomaker",
        "name": "Precision Club Sub-Mono Sculptor",
        "category": "utility",
        "description": "Steep 24dB/oct rumble high-pass at 28 Hz, clean mono collapsing below 90 Hz, and subtle 2nd-harmonic exciter for punchy sub translation.",
        "target_track_type": "bass",
        "chains": [
            {
                "name": "Clean Sub Core",
                "frequency_range": "28 - 120 Hz",
                "devices": [
                    {"name": "EQ Eight", "parameters": {"band1_hp": 28.0, "band1_slope": 24}},
                    {"name": "Utility", "parameters": {"mono": True, "bass_mono": True, "bass_mono_freq": 90.0}},
                    {"name": "Saturator", "parameters": {"drive": 1.2, "curve": "soft_sine"}},
                ],
            },
        ],
        "macros": [
            {"index": 0, "name": "Infrasonic Cut", "default": 0.28, "unit": "norm", "min": 0.15, "max": 0.45, "target_device": "EQ Eight", "target_parameter": "Band 1 Cutoff"},
            {"index": 1, "name": "Mono Crossover Freq", "default": 0.35, "unit": "norm", "min": 0.20, "max": 0.60, "target_device": "Utility", "target_parameter": "Bass Mono Frequency"},
            {"index": 2, "name": "Harmonic Warmth", "default": 0.25, "unit": "norm", "min": 0.0, "max": 0.65, "target_device": "Saturator", "target_parameter": "Drive"},
            {"index": 3, "name": "Sub Level (60Hz)", "default": 0.50, "unit": "norm", "min": 0.2, "max": 0.85, "target_device": "EQ Eight", "target_parameter": "Band 2 Gain"},
            {"index": 4, "name": "Punch Q Resonance", "default": 0.20, "unit": "norm", "min": 0.0, "max": 0.50, "target_device": "EQ Eight", "target_parameter": "Band 1 Q"},
            {"index": 5, "name": "Soft Clip Protect", "default": 1.0, "unit": "toggle", "min": 0.0, "max": 1.0, "target_device": "Saturator", "target_parameter": "Soft Clip"},
            {"index": 6, "name": "Stereo Width > 120Hz", "default": 0.50, "unit": "norm", "min": 0.0, "max": 1.0, "target_device": "Utility", "target_parameter": "Width"},
            {"index": 7, "name": "Sub Trim Output", "default": 0.85, "unit": "norm", "min": 0.5, "max": 0.95, "target_device": "Utility", "target_parameter": "Gain"},
        ],
        "variations": [
            {"name": "Default Calibrated", "macro_values": [0.28, 0.35, 0.25, 0.50, 0.20, 1.0, 0.50, 0.85]},
            {"name": "Heavy Sound-System Sub", "macro_values": [0.25, 0.45, 0.45, 0.70, 0.35, 1.0, 0.30, 0.85]},
            {"name": "Ultra Clean Surgical", "macro_values": [0.32, 0.30, 0.05, 0.50, 0.10, 1.0, 0.50, 0.88]},
        ],
    },
}


def list_available_racks() -> List[Dict[str, Any]]:
    """Return all pre-calibrated rack templates."""
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "category": r["category"],
            "description": r["description"],
            "target_track_type": r["target_track_type"],
            "chain_count": len(r["chains"]),
            "macro_count": len(r["macros"]),
            "variation_count": len(r.get("variations", [])),
        }
        for r in RACK_TEMPLATES.values()
    ]


def get_rack_template(rack_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve template details for a rack."""
    return RACK_TEMPLATES.get(rack_id)


def synthesize_rack_proposal(
    rack_id: str,
    track_index: int,
    track_name: str = "",
    session_id: str = "",
) -> Dict[str, Any]:
    """Synthesize an actionable, confirmation-gated recipe proposal to build the rack."""
    template = get_rack_template(rack_id)
    if not template:
        return {
            "ok": False,
            "error": f"Unknown rack template: {rack_id}. Available: {list(RACK_TEMPLATES.keys())}",
        }

    steps: List[Dict[str, Any]] = [
        {
            "action": "insert_device",
            "track_index": track_index,
            "track_name": track_name or f"Track {track_index}",
            "device_name": "Audio Effect Rack",
            "position": -1,  # Append to end of chain
        },
    ]

    for macro in template["macros"]:
        steps.append({
            "action": "map_macro",
            "track_index": track_index,
            "macro_index": macro["index"],
            "macro_name": macro["name"],
            "default_value": macro["default"],
            "min_value": macro["min"],
            "max_value": macro["max"],
            "target_device": macro.get("target_device", ""),
            "target_parameter": macro.get("target_parameter", ""),
        })

    primary_var = template.get("variations", [{}])[0].get("name", "Default Calibrated State")
    steps.append({
        "action": "store_rack_variation",
        "track_index": track_index,
        "variation_name": primary_var,
    })

    token_src = f"{session_id}_{rack_id}_{track_index}_{len(steps)}"
    token = f"rack_{hashlib.sha256(token_src.encode()).hexdigest()[:16]}"

    proposal = {
        "schema": SCHEMA,
        "session_id": session_id,
        "rack_id": rack_id,
        "rack_name": template["name"],
        "category": template.get("category", ""),
        "track_index": track_index,
        "track_name": track_name or f"Track {track_index}",
        "reason": f"Synthesize {template['name']} on {track_name or f'Track {track_index}'}",
        "step_count": len(steps),
        "steps": steps,
        "chains": template.get("chains", []),
        "variations": template.get("variations", []),
        "requires_confirmation": True,
        "confirmation_token": token,
        "is_rack_synthesis": True,
    }

    return {"ok": True, "proposal": proposal}


__all__ = [
    "SCHEMA",
    "RACK_TEMPLATES",
    "list_available_racks",
    "get_rack_template",
    "synthesize_rack_proposal",
]

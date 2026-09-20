# data/arp_curve_defaults.py — arp defaults, modes, and emotion curves (not the realtime engine).
from __future__ import annotations

from typing import Dict, Optional, Tuple

from data.emotion_aliases import canonical_emotion_name


ALLOWED_ARP_MODES: Tuple[str, ...] = (
    "up",
    "down",
    "updown",
    "updown_excl",
    "downup",
    "converge",
    "diverge",
)

ARPEGGIATOR_CURVE_DEFAULTS = {
    "arp_enabled": 0.0,
    # Keep arp rate inside a clear musical window:
    # 4 notes/bar = quarter notes, 16 notes/bar = sixteenth notes.
    "arp_target_notes_per_bar": 16.0,
    "arp_density_mult": 1.0,
    # Loudness stability: keep velocity scaling neutral by default.
    "arp_velocity_scale": 1.0,
    "arp_swing": 0.0,
    "arp_lead_ducking": 0.15,
    # Ableton-like Up&Down where endpoints are not repeated (more "whole chord" feel).
    "arp_mode": "updown_excl",
}


DEFAULT_ROLE_ARP_MODES: Dict[str, str] = {
    "intro": "updown",
    "a": "updown",
    "b": "downup",
    "pre_chorus": "updown",
    "tag": "downup",
    "a_prime": "downup",
    "outro": "updown",
}


POP_EXT_ROLE_ARP_MODES: Dict[str, str] = {
    "intro": "updown",
    "a": "updown",
    "pre_chorus": "updown",
    "b": "downup",
    "a_prime": "downup",
    "tag": "downup",
    "outro": "updown",
}


CONTOUR_TO_ARP_MODE: Dict[str, str] = {
    "asc": "updown",
    "desc": "downup",
    "arch": "updown",
    "static": "updown",
}


EMOTION_ARP_PROFILES: Dict[str, Dict[str, float | str]] = {
    # Gold standard targets (reference-matched): optimism / neutral / admiration
    "admiration": {
        "speed_mult": 0.84,
        "target_notes_per_bar": 5.0,
        "mode": "updown",
        # References align strongly to a 16th grid; keep it sparse via target_notes_per_bar.
        "grid": 0.25,
        "syncopation_prob": 0.06,
        "accent_strength": 0.08,
        "octave_reach_prob": 0.06,
    },
    "amusement": {"speed_mult": 1.12, "target_notes_per_bar": 10.0, "mode": "updown", "grid": 0.25, "syncopation_prob": 0.16},
    "anger": {"speed_mult": 1.06, "target_notes_per_bar": 9.0, "mode": "downup", "grid": 0.25, "syncopation_prob": 0.18},
    "annoyance": {"speed_mult": 0.94, "target_notes_per_bar": 6.0, "mode": "downup", "grid": 0.25},
    "approval": {"speed_mult": 0.90, "target_notes_per_bar": 6.0, "mode": "updown", "grid": 0.25},
    "caring": {"speed_mult": 0.82, "target_notes_per_bar": 6.0, "mode": "updown", "grid": 0.5},
    "confusion": {"speed_mult": 0.98, "target_notes_per_bar": 7.0, "mode": "downup", "grid": 0.25},
    "curiosity": {"speed_mult": 1.06, "target_notes_per_bar": 9.0, "mode": "updown", "grid": 0.25, "syncopation_prob": 0.12},
    "desire": {"speed_mult": 0.88, "target_notes_per_bar": 5.0, "mode": "updown", "grid": 0.5},
    "disappointment": {"speed_mult": 0.78, "target_notes_per_bar": 4.0, "mode": "downup", "grid": 0.5},
    "disapproval": {"speed_mult": 0.92, "target_notes_per_bar": 6.0, "mode": "downup", "grid": 0.25},
    # If enabled (some modes/forms override `arp_allowed`), keep it glitchy and tense rather than a smooth bed.
    "disgust": {
        "speed_mult": 1.00,
        "target_notes_per_bar": 8.0,
        "mode": "downup",
        "grid": 0.25,
        "syncopation_prob": 0.22,
        "accent_strength": 0.18,
        "octave_reach_prob": 0.04,
    },
    "embarrassment": {"speed_mult": 0.90, "target_notes_per_bar": 6.0, "mode": "updown", "grid": 0.25},
    # Keep energetic, but avoid hard-saturating into a constant 16th wall.
    "excitement": {"speed_mult": 1.28, "target_notes_per_bar": 10.0, "mode": "downup", "grid": 0.25, "syncopation_prob": 0.20},
    "fear": {
        "speed_mult": 0.92,
        # Reference-derived: moderate-high activity on a 16th grid (texture still tense).
        "target_notes_per_bar": 5.29,
        "mode": "downup",
        "grid": 0.25,
        "syncopation_prob": 0.116,
        "accent_strength": 0.144,
        "octave_reach_prob": 0.137,
    },
    "gratitude": {"speed_mult": 0.82, "target_notes_per_bar": 6.0, "mode": "updown", "grid": 0.25},
    "grief": {"speed_mult": 0.72, "target_notes_per_bar": 4.0, "mode": "downup", "grid": 0.5},
    "joy": {
        "speed_mult": 1.18,
        "target_notes_per_bar": 5.57,
        "mode": "updown",
        "grid": 0.25,
        "syncopation_prob": 0.116,
        "accent_strength": 0.144,
        "octave_reach_prob": 0.136,
    },
    "love": {
        "speed_mult": 0.84,
        "target_notes_per_bar": 5.94,
        "mode": "updown",
        "grid": 0.25,
        "syncopation_prob": 0.106,
        "accent_strength": 0.154,
        "octave_reach_prob": 0.148,
    },
    "nervousness": {"speed_mult": 1.10, "target_notes_per_bar": 10.0, "mode": "downup", "grid": 0.25, "syncopation_prob": 0.22},
    "optimism": {
        "speed_mult": 1.08,
        "target_notes_per_bar": 5.29,
        "mode": "updown",
        # reference-like driven 16ths with groove
        "grid": 0.25,
        "syncopation_prob": 0.113,
        "accent_strength": 0.147,
        "octave_reach_prob": 0.141,
    },
    "pride": {"speed_mult": 0.98, "target_notes_per_bar": 7.0, "mode": "updown", "grid": 0.25},
    "realization": {
        "speed_mult": 0.82,
        "target_notes_per_bar": 4.34,
        "mode": "updown",
        "grid": 0.25,
        "syncopation_prob": 0.121,
        "accent_strength": 0.139,
        "octave_reach_prob": 0.131,
    },
    "relief": {"speed_mult": 0.70, "target_notes_per_bar": 4.0, "mode": "updown", "grid": 0.25},
    "remorse": {"speed_mult": 0.76, "target_notes_per_bar": 4.0, "mode": "downup", "grid": 0.5},
    "sadness": {"speed_mult": 0.78, "target_notes_per_bar": 4.0, "mode": "downup", "grid": 0.5},
    "surprise": {"speed_mult": 1.18, "target_notes_per_bar": 12.0, "mode": "downup", "grid": 0.25, "syncopation_prob": 0.20},
    "neutral": {
        "speed_mult": 0.88,
        "target_notes_per_bar": 6.0,
        "mode": "updown",
        # Default: 16th-note grid (cleaner modern bed); density is still controlled by target_notes_per_bar.
        "grid": 0.25,
        "syncopation_prob": 0.10,
        "accent_strength": 0.10,
        "octave_reach_prob": 0.08,
    },
    "calm": {"speed_mult": 0.74, "target_notes_per_bar": 4.0, "mode": "updown", "grid": 0.5},
    "peaceful": {"speed_mult": 0.74, "target_notes_per_bar": 4.0, "mode": "updown", "grid": 0.5},
    "serenity": {"speed_mult": 0.72, "target_notes_per_bar": 4.0, "mode": "updown", "grid": 0.5},
}


def normalize_arp_mode(mode: Optional[str], default: str = "updown") -> str:
    candidate = (mode or "").strip().lower()
    # Backward-compat: older configs used "up" as a shorthand for ascending.
    if candidate in {"asc", "ascending"}:
        candidate = "up"
    if candidate in {"desc", "descending"}:
        candidate = "down"
    # Ableton-ish aliasing / user-friendly spellings.
    if candidate in {"up&down_excl", "up+down_excl", "up_down_excl", "up-down_excl", "updown_no_repeat", "updown_exclusive"}:
        candidate = "updown_excl"
    if candidate in {"up&down", "up+down", "up_down", "up-down"}:
        candidate = "updown"
    if candidate in ALLOWED_ARP_MODES:
        return candidate
    return default if default in ALLOWED_ARP_MODES else "updown"


def arp_mode_for_role(role: str, *, form_mode: str = "default") -> str:
    role_key = (role or "").strip().lower()
    if form_mode == "pop_ext":
        return normalize_arp_mode(POP_EXT_ROLE_ARP_MODES.get(role_key), default="updown")
    return normalize_arp_mode(DEFAULT_ROLE_ARP_MODES.get(role_key), default="updown")


def arp_profile_for_emotion(emotion_name: str) -> Dict[str, float | str]:
    key = canonical_emotion_name(emotion_name)
    return dict(EMOTION_ARP_PROFILES.get(key, {}))

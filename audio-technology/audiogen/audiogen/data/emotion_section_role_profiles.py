from __future__ import annotations

from typing import Any, Dict

from data.emotion_aliases import canonical_emotion_name


# Emotion x section-role production intent. Values are intentionally small
# multipliers layered on top of the existing arrangement curve.
EMOTION_SECTION_ROLE_PROFILES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "grief": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.82, "arp_target_notes_per_bar": 4.8, "arp_velocity_scale": 0.82},
        "a": {"melody_density_mult": 0.98, "chord_motion_mult": 0.90, "arp_enabled": 1.0, "arp_density_mult": 0.92, "arp_target_notes_per_bar": 5.0, "section_dynamic": 0.94},
        "pre_chorus": {"melody_density_mult": 1.00, "chord_motion_mult": 0.96, "arp_density_mult": 0.98, "tension_mult": 1.04},
        "b": {"melody_density_mult": 1.02, "chord_motion_mult": 0.92, "arp_density_mult": 0.94, "section_dynamic": 0.98},
        "tag": {"melody_density_mult": 0.96, "section_dynamic": 0.94},
    },
    "sadness": {
        # Compensate intro after emotion×role blend so low-valence intros stay singable (tests + musical floor).
        "intro": {"melody_density_mult": 1.36, "melody_total_notes_mult": 1.08, "markov_rest_prob_mult": 0.92, "arp_enabled": 1.0, "arp_density_mult": 1.10, "arp_target_notes_per_bar": 5.2, "arp_velocity_scale": 0.90},
        "a": {"melody_density_mult": 1.18, "melody_total_notes_mult": 1.08, "markov_rest_prob_mult": 0.92, "chord_motion_mult": 0.94, "arp_enabled": 1.0, "arp_density_mult": 1.12, "arp_target_notes_per_bar": 5.6, "arp_velocity_scale": 0.92},
        "pre_chorus": {"melody_density_mult": 1.06, "chord_motion_mult": 1.00, "arp_density_mult": 1.08, "tension_mult": 1.04},
        "b": {"melody_density_mult": 1.06, "chord_motion_mult": 0.96, "arp_density_mult": 1.02, "section_dynamic": 1.00},
    },
    "remorse": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.88, "arp_target_notes_per_bar": 4.8, "arp_velocity_scale": 0.80},
        "a": {"melody_density_mult": 1.00, "chord_motion_mult": 0.90, "arp_enabled": 1.0, "arp_density_mult": 0.96, "arp_target_notes_per_bar": 5.0},
        "pre_chorus": {"melody_density_mult": 1.02, "arp_density_mult": 1.00, "tension_mult": 1.06},
        "b": {"melody_density_mult": 1.04, "chord_motion_mult": 0.94, "arp_density_mult": 0.96, "section_dynamic": 0.98},
    },
    "relief": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.92, "arp_target_notes_per_bar": 5.0, "arp_velocity_scale": 0.84},
        "a": {"melody_density_mult": 1.00, "chord_motion_mult": 0.94, "arp_enabled": 1.0, "arp_density_mult": 1.00, "arp_target_notes_per_bar": 5.2, "section_dynamic": 0.96},
        "pre_chorus": {"melody_density_mult": 1.04, "chord_motion_mult": 1.02, "arp_density_mult": 1.04, "tension_mult": 0.96},
        "b": {"melody_density_mult": 1.08, "chord_motion_mult": 0.98, "arp_density_mult": 1.02, "section_dynamic": 1.04, "motif_prob_mult": 1.08},
    },
    "fear": {
        "a": {"melody_density_mult": 0.98, "chord_motion_mult": 0.98, "tension_mult": 1.10, "section_dynamic": 0.96},
        "pre_chorus": {"melody_density_mult": 1.05, "chord_motion_mult": 1.08, "tension_mult": 1.18},
        "b": {"melody_density_mult": 1.02, "chord_motion_mult": 1.06, "tension_mult": 1.16, "section_dynamic": 0.98},
    },
    "joy": {
        "a": {"melody_density_mult": 1.02, "arp_density_mult": 1.04},
        "pre_chorus": {"melody_density_mult": 1.08, "chord_motion_mult": 1.08, "tension_mult": 1.04},
        "b": {"melody_density_mult": 1.14, "arp_density_mult": 1.12, "section_dynamic": 1.08, "motif_prob_mult": 1.12},
        "tag": {"melody_density_mult": 1.10, "section_dynamic": 1.06},
    },
    "excitement": {
        "a": {"melody_density_mult": 1.04},
        "pre_chorus": {"melody_density_mult": 1.10, "chord_motion_mult": 1.10, "tension_mult": 1.06},
        "b": {"melody_density_mult": 1.16, "arp_density_mult": 1.10, "section_dynamic": 1.08, "motif_prob_mult": 1.10},
    },
    "optimism": {
        "a": {"melody_density_mult": 1.00},
        "pre_chorus": {"melody_density_mult": 1.08, "chord_motion_mult": 1.06},
        "b": {"melody_density_mult": 1.12, "section_dynamic": 1.06, "motif_prob_mult": 1.10},
    },
    "desire": {
        "a": {"melody_density_mult": 0.96, "chord_motion_mult": 0.94, "arp_density_mult": 0.90},
        "pre_chorus": {"melody_density_mult": 1.00, "tension_mult": 1.05},
        "b": {"melody_density_mult": 1.04, "section_dynamic": 1.02, "motif_prob_mult": 1.08},
    },
    "calm": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.92, "arp_target_notes_per_bar": 5.0, "arp_velocity_scale": 0.82},
        "a": {"arp_enabled": 1.0, "arp_density_mult": 1.00, "arp_target_notes_per_bar": 5.2, "arp_velocity_scale": 0.84},
    },
    "peaceful": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.90, "arp_target_notes_per_bar": 4.8, "arp_velocity_scale": 0.80},
        "a": {"arp_enabled": 1.0, "arp_density_mult": 0.98, "arp_target_notes_per_bar": 5.0, "arp_velocity_scale": 0.82},
    },
    "serenity": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.88, "arp_target_notes_per_bar": 4.8, "arp_velocity_scale": 0.80},
        "a": {"arp_enabled": 1.0, "arp_density_mult": 0.96, "arp_target_notes_per_bar": 5.0, "arp_velocity_scale": 0.82},
    },
    "caring": {
        "intro": {"arp_enabled": 1.0, "arp_density_mult": 0.88, "arp_target_notes_per_bar": 4.8, "arp_velocity_scale": 0.82},
        "a": {"arp_enabled": 1.0, "arp_density_mult": 0.96, "arp_target_notes_per_bar": 5.0, "arp_velocity_scale": 0.84},
    },
}


_MULT_KEYS = {
    "melody_density_mult",
    "melody_total_notes_mult",
    "markov_rest_prob_mult",
    "chord_motion_mult",
    "chord_rhythm_mult",
    "arp_density_mult",
    "section_dynamic",
    "motif_prob_mult",
    "tension_mult",
}


def apply_emotion_section_role_profile(curve: Dict[str, Any], *, emotion_name: str, role: str) -> Dict[str, Any]:
    out = dict(curve or {})
    emo = canonical_emotion_name(emotion_name or "")
    role_lc = str(role or "").strip().lower()
    if role_lc in {"chorus", "hook"}:
        role_lc = "b"
    prof = dict(EMOTION_SECTION_ROLE_PROFILES.get(emo, {}).get(role_lc, {}) or {})
    if not prof:
        return out
    for key, val in prof.items():
        try:
            if key in _MULT_KEYS:
                out[key] = float(out.get(key, 1.0) or 1.0) * float(val)
            else:
                out[key] = val
        except Exception:
            out[key] = val
    return out

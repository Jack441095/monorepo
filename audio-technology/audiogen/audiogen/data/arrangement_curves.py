from __future__ import annotations

from typing import Any, Dict

from data.arp_curve_defaults import ARPEGGIATOR_CURVE_DEFAULTS

# Defaults: "A" section - full but not maxed.
BASE_CURVE: Dict[str, Any] = {
    "melody_density_mult": 1.0,
    **ARPEGGIATOR_CURVE_DEFAULTS,
    "drone_enabled": 1.0,
    "temperature_mult": 1.0,
    "motif_prob_mult": 1.0,
    "phrase_repeat_mult": 1.0,
    "bass_vel_scale": 1.0,
    "chord_vel_scale": 1.0,
    # Loudness stability: avoid section/emotion-dependent velocity staging here.
    "melody_vel_scale": 1.0,
    "arp_vel_scale": 1.0,
    "drone_vel_scale": 1.0,
    "section_dynamic": 1.0,
    "melody_total_notes_mult": 1.0,
    "harmonic_color_mult": 1.0,
    "markov_rest_prob_mult": 1.0,
    "chord_rhythm_mult": 1.0,
    "chord_motion_mult": 1.0,
    "harmony_temperature_mult": 1.0,
}


FORM_GLOBAL_CURVES: Dict[str, Dict[str, Any]] = {
    "default": {
        "song_cohesion_strength": 0.89,
        "theme_recall_strength": 0.89,
        "section_contrast_strength": 0.74,
        "arrangement_variation_depth": 0.28,
        "arp_mode_variation_prob": 0.10,
        "chord_template_diversity_mult": 1.02,
        "melody_contour_variation_mult": 0.96,
        "arp_swing": 0.0,
        "fx_return_mult": 1.0,
        "reverb_send_mult": 1.0,
        "delay_send_mult": 1.02,
        "distortion_send_mult": 0.98,
        "texture_fx_gesture_mult": 1.0,
        "velocity_ride_mult": 1.0,
        "temperature_mult": 1.0,
        "harmony_temperature_mult": 1.0,
    },
    "swing": {
        "song_cohesion_strength": 0.84,
        "theme_recall_strength": 0.84,
        "section_contrast_strength": 0.74,
        "arrangement_variation_depth": 0.32,
        "arp_mode_variation_prob": 0.12,
        "chord_template_diversity_mult": 1.04,
        "melody_contour_variation_mult": 0.98,
        "arp_swing": 0.08,
        "fx_return_mult": 1.0,
        "reverb_send_mult": 1.0,
        "delay_send_mult": 1.02,
        "distortion_send_mult": 0.98,
        "texture_fx_gesture_mult": 1.0,
        "velocity_ride_mult": 1.0,
        "temperature_mult": 1.0,
        "harmony_temperature_mult": 1.0,
    },
}


def _clip(x: float, lo: float, hi: float) -> float:
    return float(max(float(lo), min(float(hi), float(x))))


def global_curve(form_mode: str, *, energy: float) -> Dict[str, Any]:
    """
    Form-level global arrangement controls.

    Merged after BASE_CURVE and before role_curve so sections keep role identity
    while sharing whole-song variation + FX intent.
    """
    fm = str(form_mode or "default").strip().lower()
    base = dict(FORM_GLOBAL_CURVES.get(fm, FORM_GLOBAL_CURVES["default"]))
    if fm == "ambient":
        e = _clip(float(energy), 0.55, 1.45)
        ev = _clip((e - 1.0) / 0.28, -1.0, 1.0)
    else:
        e = _clip(float(energy), 0.65, 1.35)
        ev = _clip((e - 1.0) / 0.35, -1.0, 1.0)
    try:
        base["arrangement_variation_depth"] = _clip(
            float(base.get("arrangement_variation_depth", 0.5)) * (1.0 + 0.22 * ev),
            0.20,
            0.90,
        )
        base["arp_mode_variation_prob"] = _clip(
            float(base.get("arp_mode_variation_prob", 0.18)) * (1.0 + 0.30 * ev),
            0.06,
            0.42,
        )
        base["chord_template_diversity_mult"] = _clip(
            float(base.get("chord_template_diversity_mult", 1.0)) * (1.0 + 0.12 * ev),
            0.88,
            1.28,
        )
        base["melody_contour_variation_mult"] = _clip(
            float(base.get("melody_contour_variation_mult", 1.0)) * (1.0 + 0.10 * ev),
            0.90,
            1.22,
        )
        base["section_contrast_strength"] = _clip(
            float(base.get("section_contrast_strength", 0.7)) * (1.0 + 0.16 * ev),
            0.50,
            1.08,
        )
        base["texture_fx_gesture_mult"] = _clip(
            float(base.get("texture_fx_gesture_mult", 1.0)) * (1.0 + 0.20 * ev),
            0.75,
            1.28,
        )
        base["fx_return_mult"] = _clip(
            float(base.get("fx_return_mult", 1.0)) * (1.0 + 0.08 * ev),
            0.86,
            1.20,
        )
        if fm == "ambient":
            base["harmony_temperature_mult"] = _clip(
                float(base.get("harmony_temperature_mult", 1.0)) * (1.0 + 0.10 * ev),
                0.90,
                1.12,
            )
    except Exception:
        pass
    return base


def role_curve(role: str, *, energy: float) -> Dict[str, Any]:
    """Return the per-role curve overrides (pure data + light energy gating)."""
    r = (role or "").lower()
    if r == "intro":
        return {
            # Default arrangement contract: intro is chords + drone only.
            # Keep the lead lanes silent so the verse feels like the song begins.
            "melody_density_mult": 0.0,
            "melody_total_notes_mult": 0.0,
            # Always-on drone in intro (per user goal).
            "drone_enabled": 1.0,
            "temperature_mult": 0.90,
            "motif_prob_mult": 0.50,
            "phrase_repeat_mult": 0.62,
            # Bed-forward: chords + optional drone; bass deferred until first chorus (`b`).
            "bass_enabled": 0.0,
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 1.0,
            # Keep loudness transitions gentle across section roles.
            "section_dynamic": 0.90,
            "melody_max_notes_per_phrase": 11,
            "harmonic_color_mult": 0.86,
            "markov_rest_prob_mult": 1.04,
            "chord_rhythm_mult": 0.84,
            "chord_motion_mult": 0.82,
            "harmony_temperature_mult": 0.93,
            # No arp in the intro (contract: chords + drone only).
            "arp_enabled": 0.0,
            "arp_grid": 0.25,
            "arp_density_mult": 0.0,
            # Cadence shaping: intros should not hard-resolve.
            "cadence_strength_mult": 0.78,
            # Song-level register arc: start a bit lower.
            "melody_lane_center_offset": -4,
            # Orchestration automation (produced contrast).
            "counter_melody_enabled_mult": 0.0,
            "chord_comping_strength_mult": 0.60,
        }
    if r == "a":
        return {
            # Verse: chords + light melody; keep arp silent so the pre/chorus lift reads clearly.
            "melody_density_mult": 0.78,
            "drone_enabled": 0.0,
            "temperature_mult": 0.97,
            "motif_prob_mult": 0.88,
            "phrase_repeat_mult": 0.98,
            # No arp in verse (contract).
            "arp_enabled": 0.0,
            "arp_grid": 0.25,
            "arp_density_mult": 0.0,
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 1.0,
            "section_dynamic": 1.0,
            "melody_total_notes_mult": 1.00,
            "melody_max_notes_per_phrase": 17,
            "harmonic_color_mult": 0.96,
            "markov_rest_prob_mult": 1.06,
            "chord_rhythm_mult": 0.94,
            "chord_motion_mult": 1.02,
            "harmony_temperature_mult": 1.02,
            # Verses: keep endings a bit more open.
            "cadence_strength_mult": 0.92,
            # Verse baseline.
            "melody_lane_center_offset": 0,
            "counter_melody_enabled_mult": 0.0,
            "chord_comping_strength_mult": 0.78,
        }
    if r == "b":
        return {
            "melody_density_mult": 1.30,
            "drone_enabled": 0.0,
            "temperature_mult": 1.09,
            "motif_prob_mult": 0.82,
            "phrase_repeat_mult": 0.92,
            # Hybrid arp feel: chorus-like driven 16ths + higher density.
            "arp_enabled": 1.0,
            "arp_grid": 0.5,
            "arp_density_mult": 1.20,
            # Lift: more harmonic motion + brighter mid.
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 0.0,
            "section_dynamic": 1.05,
            "melody_total_notes_mult": 0.98,
            "melody_max_notes_per_phrase": 22,
            "harmonic_color_mult": 1.14,
            "markov_rest_prob_mult": 0.96,
            "chord_rhythm_mult": 0.92,
            "chord_motion_mult": 1.08,
            "harmony_temperature_mult": 1.06,
            # Choruses: clearer cadences read as hooks.
            "cadence_strength_mult": 1.18,
            # Chorus peak.
            "melody_lane_center_offset": 6,
            "counter_melody_enabled_mult": 1.0,
            "chord_comping_strength_mult": 0.88,
            "arp_lead_ducking": 0.86,
        }
    if r == "pre_chorus":
        return {
            # Pre-chorus: chords + light melody + light arps (lift without going full chorus).
            "melody_density_mult": 0.92,
            "drone_enabled": 0.0,
            "temperature_mult": 1.07,
            "motif_prob_mult": 0.78,
            "phrase_repeat_mult": 0.85,
            # Light arp bed on 16ths.
            "arp_enabled": 1.0,
            "arp_grid": 0.5,
            "arp_density_mult": 0.70,
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 0.0,
            "section_dynamic": 1.06,
            "melody_total_notes_mult": 1.06,
            "melody_max_notes_per_phrase": 21,
            "harmonic_color_mult": 1.08,
            "markov_rest_prob_mult": 0.96,
            "chord_rhythm_mult": 0.92,
            "chord_motion_mult": 1.05,
            "harmony_temperature_mult": 1.05,
            # Pre-chorus: avoid full closure; set up the chorus lift.
            "cadence_strength_mult": 0.72,
            # Lift into chorus.
            "melody_lane_center_offset": 3,
            "counter_melody_enabled_mult": 0.25,
            "chord_comping_strength_mult": 0.82,
            "arp_lead_ducking": 0.68,
        }
    if r == "tag":
        return {
            "melody_density_mult": 1.20,
            "drone_enabled": 0.0,
            "temperature_mult": 1.05,
            "motif_prob_mult": 1.38,
            "phrase_repeat_mult": 1.14,
            # Tag is often a peak: keep driven 16ths and fairly high density.
            "arp_enabled": 1.0,
            "arp_grid": 0.5,
            "arp_density_mult": 1.22,
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 0.0,
            "section_dynamic": 1.04,
            "melody_total_notes_mult": 1.00,
            "melody_max_notes_per_phrase": 24,
            "harmonic_color_mult": 1.02,
            "markov_rest_prob_mult": 0.98,
            "chord_rhythm_mult": 0.92,
            "chord_motion_mult": 1.06,
            "harmony_temperature_mult": 1.03,
            "cadence_strength_mult": 1.08,
            "melody_lane_center_offset": 5,
            "counter_melody_enabled_mult": 0.6,
            "chord_comping_strength_mult": 0.88,
        }
    if r == "a_prime":
        return {
            "melody_density_mult": 1.12,
            "drone_enabled": 0.0,
            "temperature_mult": 1.05,
            "motif_prob_mult": 1.32,
            "phrase_repeat_mult": 1.12,
            # Return section: keep 16th grid but not as dense as chorus/tag.
            "arp_enabled": 1.0,
            "arp_grid": 0.5,
            "arp_density_mult": 1.10,
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 0.0,
            "section_dynamic": 1.03,
            "melody_total_notes_mult": 0.98,
            "melody_max_notes_per_phrase": 20,
            "harmonic_color_mult": 1.06,
            "markov_rest_prob_mult": 0.98,
            "chord_rhythm_mult": 0.92,
            "chord_motion_mult": 1.08,
            "harmony_temperature_mult": 1.04,
            "cadence_strength_mult": 1.12,
            "melody_lane_center_offset": 2,
            "counter_melody_enabled_mult": 0.45,
            "chord_comping_strength_mult": 0.84,
        }
    if r == "outro":
        return {
            "melody_density_mult": 0.56,
            "drone_enabled": 1.0,
            "temperature_mult": 0.88,
            "motif_prob_mult": 0.55,
            "phrase_repeat_mult": 0.66,
            # Outro: keep 16th grid but very sparse.
            "arp_enabled": 0.0,
            "arp_grid": 0.25,
            "arp_density_mult": 0.65,
            "bass_vel_scale": 1.0,
            "chord_vel_scale": 1.0,
            "melody_vel_scale": 1.0,
            "drone_vel_scale": 1.0,
            "section_dynamic": 0.90,
            "melody_total_notes_mult": 0.78,
            "melody_max_notes_per_phrase": 10,
            "harmonic_color_mult": 0.88,
            "markov_rest_prob_mult": 1.1,
            "chord_rhythm_mult": 0.86,
            "chord_motion_mult": 0.86,
            "harmony_temperature_mult": 0.91,
            "cadence_strength_mult": 1.26,
            # Outro falls back down.
            "melody_lane_center_offset": -5,
            "counter_melody_enabled_mult": 0.0,
            "chord_comping_strength_mult": 0.55,
        }
    return {}


POP_EXT_OVERRIDES = {
    # Arp should support verse + chorus primarily (Ableton-style bed).
    "arp_enabled_roles": {"a", "b"},
    "intro": {
        "melody_density_mult": 0.62,
        "melody_total_notes_mult": 0.82,
        "melody_max_notes_per_phrase": 10,
        "arp_enabled": 0.0,
    },
    "a__pre_chorus": {
        "arp_density_mult": 0.88,
        "arp_vel_scale": 1.0,
    },
    "b__a_prime__tag": {
        # Pop-ext: keep chorus/return/tag closer to the role-curve peak (1.52 for ``b``);
        # 1.18 was noticeably thinning the arp bed vs default-form chorus.
        "arp_density_mult": 1.34,
        "arp_vel_scale": 1.0,
    },
    "outro": {"arp_enabled": 0.0},
}


BOUNDARY_DEFAULTS = {
    "intro": {"boundary_bar0_vel_mult": None, "boundary_first_phrase_note_mult": 1.0},
    "a": {"boundary_bar0_vel_mult": 0.98, "boundary_first_phrase_note_mult": 1.0},
    "pre_chorus": {"boundary_bar0_vel_mult": 0.95, "boundary_first_phrase_note_mult": 0.94},
    "b": {"boundary_bar0_vel_mult": 0.96, "boundary_first_phrase_note_mult": 0.92},
    "a_prime": {"boundary_bar0_vel_mult": 1.0, "boundary_first_phrase_note_mult": 1.0},
    "tag": {"boundary_bar0_vel_mult": 1.0, "boundary_first_phrase_note_mult": 1.0},
    "outro": {"boundary_bar0_vel_mult": 1.0, "boundary_first_phrase_note_mult": 1.0},
}

# Per-arrangement-role multiplier for master FX return wet level (reverb/delay/distortion returns).
# Values are intentionally subtle; combine with ``arrangement_fx_return_strength`` on audio config.
_ARRANGEMENT_ROLE_FX_RETURN_BASE: Dict[str, float] = {
    "intro": 0.90,
    "a": 0.94,
    "pre_chorus": 1.02,
    "b": 1.08,
    "a_prime": 0.98,
    "tag": 1.05,
    "outro": 0.88,
}


def arrangement_role_fx_return_mult(role: str, *, strength: float = 1.0) -> float:
    """
    Scale factor for ``MasterBus`` FX return level by song-section role.

    When ``strength`` is 1.0, chorus (`b`) is slightly wetter; intro/outro slightly drier.
    ``strength`` 0 disables the effect; values above 1 exaggerate the spread (clamp gently).
    """
    r = str(role or "").strip().lower()
    if not r:
        return 1.0
    try:
        s = float(strength)
    except Exception:
        s = 1.0
    s = float(max(0.0, min(2.0, s)))
    if s <= 0.0:
        return 1.0
    base = float(_ARRANGEMENT_ROLE_FX_RETURN_BASE.get(r, 1.0))
    # Blend toward neutral so strength acts as a dial: 1 + (base - 1) * s
    out = 1.0 + (base - 1.0) * s
    return float(max(0.5, min(1.35, out)))


# Post-render stem gain ride (multiplies all channels except drone in ``apply_drone_and_velocity``).
_ARRANGEMENT_ROLE_VELOCITY_RIDE_BASE: Dict[str, float] = {
    "intro": 0.97,
    "a": 0.99,
    "pre_chorus": 1.02,
    "b": 1.045,
    "a_prime": 1.01,
    "tag": 1.04,
    "outro": 0.96,
}


def arrangement_role_velocity_ride_mult(
    role: str,
    *,
    strength: float = 1.0,
    pre_chorus_last_bar: bool = False,
    pre_chorus_swell_strength: float = 1.0,
) -> float:
    """
    Linear gain applied to rendered stems (except drone buffer) for section-role dynamics.

    When ``pre_chorus_last_bar`` is True and role is ``pre_chorus``, adds a small extra lift
    on the last bar before the chorus for a "telegraphed" build.
    """
    r = str(role or "").strip().lower()
    if not r:
        return 1.0
    try:
        s = float(strength)
    except Exception:
        s = 1.0
    s = float(max(0.0, min(2.0, s)))
    if s <= 0.0:
        return 1.0
    base = float(_ARRANGEMENT_ROLE_VELOCITY_RIDE_BASE.get(r, 1.0))
    out = 1.0 + (base - 1.0) * s
    if pre_chorus_last_bar and r == "pre_chorus":
        try:
            ps = float(pre_chorus_swell_strength)
        except Exception:
            ps = 1.0
        ps = float(max(0.0, min(2.0, ps)))
        # +~3% extra at full strength (scales with arrangement_velocity_ride_strength via caller).
        swell = 1.0 + 0.04 * ps * s
        out *= swell
    return float(max(0.82, min(1.12, out)))

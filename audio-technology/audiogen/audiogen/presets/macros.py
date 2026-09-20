from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(float(lo), min(float(hi), float(x)))


@dataclass
class MacroMapping:
    """
    Authoritative mapping from user macros -> internal config fields.
    Values are normalized 0..1 unless otherwise noted.
    """

    tempo_min_scale: float = 0.55
    tempo_max_scale: float = 1.55

    swing_max: float = 0.18

    melodic_intensity_min: float = 0.55
    melodic_intensity_max: float = 1.20

    familiarity_motif_use_min: float = 0.15
    familiarity_motif_use_max: float = 0.92

    # Composition (DAW-like feel)
    lead_feel_swing_max: float = 0.14
    lead_feel_microtiming_max_ms: float = 12.0
    hook_strength_min: float = 0.35
    hook_strength_max: float = 1.0
    hook_development_variation_min: float = 0.15
    hook_development_variation_max: float = 0.85
    counter_melody_enable_threshold: float = 0.25
    harmony_development_strength_max: float = 0.6

    # Offline/quality selection (may no-op if those knobs are removed later)
    selection_quality_k_max: int = 6
    selection_quality_enable_threshold: float = 0.12
    selection_quality_temp_jitter_max: float = 0.18

    # FX sends/returns
    space_delay_send_min: float = 0.00
    space_delay_send_max: float = 0.36
    space_delay_return_min: float = 0.00
    space_delay_return_max: float = 0.34
    space_reverb_send_min: float = 0.00
    space_reverb_send_max: float = 0.30

    width_delay_send_min: float = 0.00
    width_delay_send_max: float = 0.28
    width_delay_return_min: float = 0.00
    width_delay_return_max: float = 0.24

    grit_dist_send_min: float = 0.00
    grit_dist_send_max: float = 0.10
    grit_dist_return_min: float = 0.00
    grit_dist_return_max: float = 0.14


def apply_macros_to_config(
    cfg: Any,
    macros: Dict[str, float],
    *,
    mapping: MacroMapping | None = None,
) -> Dict[str, float]:
    """
    Apply supported macros to CONFIG in a safe, clamped way.
    Returns the normalized macro values that were applied.
    """

    mapping = mapping or MacroMapping()
    comp = getattr(cfg, "composition", cfg)
    audio = getattr(cfg, "audio", cfg)

    applied: Dict[str, float] = {}
    for k, v in (macros or {}).items():
        try:
            applied[str(k)] = _clamp(float(v), 0.0, 1.0)
        except Exception:
            continue

    # tempo: normalized -> global tempo scale multiplier
    if "tempo" in applied:
        t = applied["tempo"]
        scale = mapping.tempo_min_scale + (mapping.tempo_max_scale - mapping.tempo_min_scale) * float(t)
        try:
            setattr(comp, "global_tempo_scale", float(scale))
        except Exception:
            pass

    # swing: normalized -> enable + amount (0..swing_max)
    if "swing" in applied:
        s = applied["swing"]
        amt = float(mapping.swing_max) * float(s)
        try:
            setattr(comp, "swing_enabled", bool(amt > 1e-4))
            setattr(comp, "swing_amount", float(amt))
        except Exception:
            pass

    # melodic_intensity: drive lead note budget + rest probability (inverse)
    if "melodic_intensity" in applied:
        m = applied["melodic_intensity"]
        scale = mapping.melodic_intensity_min + (mapping.melodic_intensity_max - mapping.melodic_intensity_min) * float(m)
        try:
            setattr(comp, "melody_amount_scale", float(scale))
        except Exception:
            pass
        try:
            # Lower intensity -> more rests; higher intensity -> fewer rests.
            rest = 1.25 - 0.50 * float(m)  # 0 -> 1.25, 1 -> 0.75
            setattr(comp, "melody_rest_prob_mult", float(_clamp(rest, 0.70, 1.40)))
        except Exception:
            pass

    # motif_familiarity: prefer restatement + motif usage, reduce variation a bit
    if "motif_familiarity" in applied:
        f = applied["motif_familiarity"]
        use = mapping.familiarity_motif_use_min + (mapping.familiarity_motif_use_max - mapping.familiarity_motif_use_min) * float(f)
        try:
            setattr(comp, "motif_use_chance", float(_clamp(use, 0.0, 1.0)))
        except Exception:
            pass
        try:
            # Higher familiarity -> fewer variations
            var = 0.55 - 0.35 * float(f)  # 0 -> 0.55, 1 -> 0.20
            setattr(comp, "motif_variation_prob", float(_clamp(var, 0.05, 0.75)))
        except Exception:
            pass

    # lead_feel: drives melody swing + microtiming.
    if "lead_feel" in applied:
        lf = applied["lead_feel"]
        try:
            swing_amt = float(mapping.lead_feel_swing_max) * float(lf)
            mt_ms = float(mapping.lead_feel_microtiming_max_ms) * float(lf)
            setattr(comp, "melody_swing_enabled", bool(swing_amt > 1e-4))
            setattr(comp, "melody_swing_amount", float(_clamp(swing_amt, 0.0, 0.25)))
            setattr(comp, "melody_microtiming_enabled", bool(mt_ms > 1e-4))
            setattr(comp, "melody_microtiming_max_ms", float(_clamp(mt_ms, 0.0, 25.0)))
        except Exception:
            pass

    # hook_strength: scales hook restatement intensity (motif + phrase repetition).
    if "hook_strength" in applied:
        hs = applied["hook_strength"]
        try:
            mult = mapping.hook_strength_min + (mapping.hook_strength_max - mapping.hook_strength_min) * float(hs)
            setattr(comp, "motif_use_chance", float(_clamp(getattr(comp, "motif_use_chance", 0.5) * mult, 0.0, 1.0)))
            setattr(comp, "melody_avoid_recent_openings", bool(hs < 0.85))
            var = 0.55 - 0.40 * float(hs)
            setattr(comp, "motif_variation_prob", float(_clamp(var, 0.05, 0.75)))
        except Exception:
            pass

    # hook_development: controls how quickly the hook evolves across loop iterations.
    # Higher = more variation/fragmentation sooner; lower = clearer repeated statements.
    if "hook_development" in applied:
        hdv = applied["hook_development"]
        try:
            setattr(comp, "hook_development", float(_clamp(float(hdv), 0.0, 1.0)))
        except Exception:
            pass
        try:
            # Drive motif variation probability upward with development.
            vmin = float(getattr(mapping, "hook_development_variation_min", 0.15))
            vmax = float(getattr(mapping, "hook_development_variation_max", 0.85))
            var = float(vmin) + (float(vmax) - float(vmin)) * float(hdv)
            setattr(comp, "motif_variation_prob", float(_clamp(var, 0.05, 0.95)))
        except Exception:
            pass

    # counter_melody: enable/disable sparse counterline.
    if "counter_melody" in applied:
        cm = applied["counter_melody"]
        try:
            setattr(comp, "counter_melody_enabled", bool(float(cm) >= float(mapping.counter_melody_enable_threshold)))
        except Exception:
            pass

    # harmony_development: scale 16-bar development strength (color/motion scheduling).
    if "harmony_development" in applied:
        hd = applied["harmony_development"]
        try:
            setattr(comp, "harmony_development_enabled", True)
            setattr(comp, "harmony_development_strength", float(_clamp(float(hd) * float(mapping.harmony_development_strength_max), 0.0, 1.0)))
        except Exception:
            pass

    # selection_quality: enable offline best-of-K selection + set K/jitter.
    if "selection_quality" in applied:
        q = applied["selection_quality"]
        try:
            enable = bool(float(q) >= float(mapping.selection_quality_enable_threshold))
            setattr(comp, "bestofk_enabled", bool(enable))
            k_max = max(2, int(getattr(mapping, "selection_quality_k_max", 6) or 6))
            k = 1 if not enable else int(round(2 + float(q) * float(k_max - 2)))
            setattr(comp, "bestofk_k", int(max(1, min(12, k))))
            jitter = float(mapping.selection_quality_temp_jitter_max) * float(q)
            setattr(comp, "bestofk_temperature_jitter", float(_clamp(jitter, 0.0, 0.35)))
        except Exception:
            pass

    # ------------------------------------------------------------
    # FX macros (optional): space / width / grit
    # ------------------------------------------------------------
    if "space" in applied:
        s = applied["space"]
        try:
            d_send = mapping.space_delay_send_min + (mapping.space_delay_send_max - mapping.space_delay_send_min) * float(s)
            r_send = mapping.space_reverb_send_min + (mapping.space_reverb_send_max - mapping.space_reverb_send_min) * float(s)
            d_ret = mapping.space_delay_return_min + (mapping.space_delay_return_max - mapping.space_delay_return_min) * float(s)
            try:
                setattr(audio, "delay_bus_enabled", bool(d_ret > 1e-4))
                setattr(audio, "delay_bus_return_level", float(_clamp(d_ret, 0.0, 1.0)))
            except Exception:
                pass
            strips = getattr(audio, "mixer_strips", None) or {}
            for _ch, strip in strips.items():
                try:
                    strip.reverb_send = float(_clamp(r_send, 0.0, 1.0))
                    strip.delay_send = float(_clamp(d_send, 0.0, 1.0))
                except Exception:
                    continue
        except Exception:
            pass

    if "width" in applied:
        w = applied["width"]
        try:
            d_send = mapping.width_delay_send_min + (mapping.width_delay_send_max - mapping.width_delay_send_min) * float(w)
            d_ret = mapping.width_delay_return_min + (mapping.width_delay_return_max - mapping.width_delay_return_min) * float(w)
            try:
                setattr(audio, "delay_bus_enabled", bool(d_ret > 1e-4 or d_send > 1e-4))
                base_ret = float(getattr(audio, "delay_bus_return_level", 0.32) or 0.32)
                setattr(audio, "delay_bus_return_level", float(_clamp(base_ret + d_ret, 0.0, 0.55)))
            except Exception:
                pass
            strips = getattr(audio, "mixer_strips", None) or {}
            for ch_id, strip in strips.items():
                try:
                    ch_i = int(ch_id)
                    if ch_i in (2, 3, 5):
                        cur = float(getattr(strip, "delay_send", 0.0) or 0.0)
                        strip.delay_send = float(_clamp(cur + d_send, 0.0, 1.0))
                except Exception:
                    continue
        except Exception:
            pass

    if "grit" in applied:
        g = applied["grit"]
        try:
            d_send = mapping.grit_dist_send_min + (mapping.grit_dist_send_max - mapping.grit_dist_send_min) * float(g)
            d_ret = mapping.grit_dist_return_min + (mapping.grit_dist_return_max - mapping.grit_dist_return_min) * float(g)
            try:
                setattr(audio, "distortion_bus_enabled", bool(d_ret > 1e-4))
                setattr(audio, "distortion_bus_return_level", float(_clamp(d_ret, 0.0, 1.0)))
            except Exception:
                pass
            strips = getattr(audio, "mixer_strips", None) or {}
            for _ch, strip in strips.items():
                try:
                    strip.distortion_send = float(_clamp(d_send, 0.0, 1.0))
                except Exception:
                    continue
        except Exception:
            pass

    return applied


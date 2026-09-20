from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Optional


def apply_startup_overrides(
    *,
    args: Any,
    config: Any,
    prompt_arrangement_form_selection: Callable[..., Optional[str]],
) -> Optional[int]:
    from audiogen_core.composition_config import apply_melody_staged_experimental_bundle

    list_flags = {
        "list_preset_families": bool(getattr(args, "list_preset_families", False)),
        "list_meta_presets": bool(getattr(args, "list_meta_presets", False)),
        "list_packs": bool(getattr(args, "list_packs", False)),
        "list_styles": bool(getattr(args, "list_styles", False)),
        "list_style_architectures": bool(getattr(args, "list_style_architectures", False)),
        "list_fx": bool(getattr(args, "list_fx", False)),
        "list_arrangements": bool(getattr(args, "list_arrangements", False)),
        "list_producer_macros": bool(getattr(args, "list_producer_macros", False)),
    }
    if any(list_flags.values()):
        logging.info("Preset/style listing is disabled in this default-only repo.")
        return 0

    config.set_performance_mode(str(getattr(args, "performance", "high") or "high"))
    try:
        c = getattr(config, "composition", None)
        if c is not None:
            nl = getattr(args, "note_log", None)
            if nl is not None:
                setattr(c, "note_log_enabled", bool(nl))
            p_nl = getattr(args, "note_log_path", None)
            if p_nl:
                setattr(c, "note_log_path", str(Path(str(p_nl)).expanduser()))
            nl_c = getattr(args, "note_log_console", None)
            if nl_c is not None:
                setattr(c, "note_log_console_enabled", bool(nl_c))
        a = getattr(config, "audio", None)
        if a is not None:
            sd = getattr(args, "sampler_debug_log", None)
            if sd is not None:
                setattr(a, "sampler_debug_log_enabled", bool(sd))
            p_sd = getattr(args, "sampler_debug_log_path", None)
            if p_sd:
                setattr(a, "sampler_debug_log_path", str(Path(str(p_sd)).expanduser()))
            mm = getattr(args, "mixer_master_debug_log", None)
            if mm is not None:
                setattr(a, "mixer_master_debug_log_enabled", bool(mm))
            p_mm = getattr(args, "mixer_master_debug_log_path", None)
            if p_mm:
                setattr(a, "mixer_master_debug_log_path", str(Path(str(p_mm)).expanduser()))
    except Exception:
        pass
    arrangement_form = None
    try:
        arrangement_form = str(getattr(args, "arrangement_form", "") or "").strip() or None
    except Exception:
        arrangement_form = None
    if arrangement_form is None:
        try:
            arrangement_form = str(getattr(args, "arrangement", "") or "").strip() or None
        except Exception:
            arrangement_form = None
    if not arrangement_form and not bool(getattr(args, "quiet", False)):
        try:
            current = str(getattr(getattr(config, "composition", None), "arranged_song_mode", "default") or "default")
        except Exception:
            current = "default"
        try:
            chosen = prompt_arrangement_form_selection(current=current)
        except Exception:
            chosen = None
        if chosen:
            arrangement_form = str(chosen).strip() or arrangement_form
    if arrangement_form:
        try:
            comp = getattr(config, "composition", None)
            if comp is not None:
                setattr(comp, "arranged_song_mode", str(arrangement_form))
                setattr(comp, "arranged_songs_default", True)
                setattr(comp, "realtime_form_mode_override", str(arrangement_form))
                try:
                    setattr(comp, "per_emotion_arranged_song_mode_pool", [str(arrangement_form)])
                except Exception:
                    pass
                try:
                    setattr(comp, "per_emotion_arranged_song_mode_map", {})
                except Exception:
                    pass
        except Exception:
            pass
    if bool(getattr(args, "arp_octave_reach", False)):
        try:
            config.composition.arp_octave_reach_enabled = True
            logging.info("Arp octave reach enabled (--arp-octave-reach)")
        except Exception:
            pass
    if args.transition_bars is not None:
        try:
            config.audio.emotion_transition_boundary_bars = max(1, int(args.transition_bars))
        except Exception:
            pass
    if args.blend_bars is not None:
        try:
            config.composition.transition_blend_bars = max(0, int(args.blend_bars))
        except Exception:
            pass
    if args.handoff_fade_scale is not None:
        try:
            config.audio.emotion_handoff_crossfade_scale = float(args.handoff_fade_scale)
        except Exception:
            pass
    if args.handoff_fade_max is not None:
        try:
            config.audio.emotion_handoff_crossfade_max_seconds = float(args.handoff_fade_max)
        except Exception:
            pass
    if bool(getattr(args, "melody_staged_experimental", False)):
        config.composition.melody_staged_experimental_bundle_enabled = True
    try:
        v = float(getattr(args, "variety", 1.0))
    except Exception:
        v = 1.0
    v = max(0.0, min(1.0, float(v)))
    c = getattr(config, "composition", None)
    if c is not None:
        try:
            c.section_sampler_novelty_enabled = bool(v > 1e-6)
            c.section_sampler_novelty_weight = float(0.10 + 0.25 * v)
            c.section_sampler_chord_novelty_weight = float(0.06 + 0.18 * v)
            c.section_sampler_register_novelty_weight = float(0.04 + 0.12 * v)
        except Exception:
            pass
        try:
            c.arp_style_table_strength = float(max(0.0, min(1.0, 0.95 - 0.75 * v)))
            c.arp_allow_mode_variation_enabled = bool(v >= 0.25)
        except Exception:
            pass
        try:
            c.arp_preset_variations_enabled = bool(v >= 0.35)
            c.arp_preset_variations_prob = float(max(0.0, min(1.0, 0.40 + 0.50 * v)))
        except Exception:
            pass
        try:
            c.melody_bar_temperature_mult_max = float(max(1.0, min(3.0, 1.35 + 0.65 * v)))
            c.melody_bar_temperature_mult_min = float(max(0.3, min(1.0, 0.80 - 0.30 * v)))
        except Exception:
            pass
        try:
            c.motif_use_chance = float(max(0.15, min(0.95, 0.88 - 0.35 * v)))
            c.motif_variation_prob = float(max(0.0, min(1.0, 0.12 + 0.55 * v)))
        except Exception:
            pass
        try:
            logging.info(
                "Startup variety=%.2f applied (arp_style_strength=%.2f novelty=%s fresh_on_start=%s)",
                float(v),
                float(getattr(c, "arp_style_table_strength", 0.0) or 0.0),
                "on" if bool(getattr(c, "section_sampler_novelty_enabled", False)) else "off",
                "on" if bool(getattr(args, "fresh_on_start", True)) else "off",
            )
        except Exception:
            pass
    if getattr(config.composition, "melody_staged_experimental_bundle_enabled", False):
        apply_melody_staged_experimental_bundle(config.composition)
    if bool(getattr(args, "export_live_melody_training", False)):
        config.composition.export_live_melody_training_enabled = True
    p_export = getattr(args, "export_live_melody_training_path", None)
    if p_export:
        config.composition.export_live_melody_training_path = str(p_export)
    # Tri-state: None -> keep config default (now on); True/False -> explicit override
    # from --melody-retrained-markov / --no-melody-retrained-markov.
    _mk_flag = getattr(args, "melody_retrained_markov", None)
    if _mk_flag is not None:
        try:
            config.composition.melody_retrained_markov_enabled = bool(_mk_flag)
        except Exception:
            pass
    p_mk = getattr(args, "melody_retrained_markov_path", None)
    if p_mk:
        try:
            config.composition.melody_retrained_markov_path = str(p_mk)
        except Exception:
            pass
    if bool(getattr(args, "melody_retrained_markov_hot_reload", False)):
        try:
            config.composition.melody_retrained_markov_hot_reload_enabled = True
        except Exception:
            pass
    p_mk_reload = getattr(args, "melody_retrained_markov_hot_reload_interval", None)
    if p_mk_reload is not None:
        try:
            config.composition.melody_retrained_markov_hot_reload_interval_seconds = float(p_mk_reload)
        except Exception:
            pass
    if bool(getattr(args, "melody_neural_logit_residual", False)):
        try:
            config.composition.melody_neural_logit_residual_enabled = True
        except Exception:
            pass
    p_nr = getattr(args, "melody_neural_logit_residual_path", None)
    if p_nr:
        try:
            config.composition.melody_neural_logit_residual_path = str(p_nr)
        except Exception:
            pass
    if bool(getattr(args, "replay_chords", False)):
        try:
            config.composition.chord_progression_pool_only_enabled = True
            config.composition.chord_progression_replay_enabled = True
        except Exception:
            pass
    if bool(getattr(args, "chorus_ref_wavs", False)):
        try:
            config.composition.chorus_reference_arp_enabled = True
        except Exception:
            pass
    p_ref = getattr(args, "chorus_ref_wavs_path", None)
    if p_ref:
        try:
            config.composition.chorus_reference_arp_path = str(p_ref)
        except Exception:
            pass
    ref_strength = getattr(args, "chorus_ref_strength", None)
    if ref_strength is not None:
        try:
            config.composition.chorus_reference_arp_strength = float(ref_strength)
        except Exception:
            pass
    ref_boost = getattr(args, "chorus_ref_target_boost", None)
    if ref_boost is not None:
        try:
            config.composition.chorus_reference_arp_target_boost = float(ref_boost)
        except Exception:
            pass
    if bool(getattr(args, "chorus_ref_melody", False)):
        try:
            config.composition.chorus_reference_melody_enabled = True
        except Exception:
            pass
    p_ref_mel = getattr(args, "chorus_ref_melody_path", None)
    if p_ref_mel:
        try:
            config.composition.chorus_reference_melody_path = str(p_ref_mel)
        except Exception:
            pass
    ref_mel_strength = getattr(args, "chorus_ref_melody_strength", None)
    if ref_mel_strength is not None:
        try:
            config.composition.chorus_reference_melody_strength = float(ref_mel_strength)
        except Exception:
            pass
    ref_mel_boost = getattr(args, "chorus_ref_melody_target_boost", None)
    if ref_mel_boost is not None:
        try:
            config.composition.chorus_reference_melody_target_boost = float(ref_mel_boost)
        except Exception:
            pass
    try:
        config.rebuild_samplers()
    except Exception:
        pass
    return None

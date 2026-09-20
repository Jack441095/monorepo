import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

class _ConsoleQuietFilter(logging.Filter):
    _SUBSTRINGS = (
        "Slow bar render",
        "Attempting audio stream recovery",
        "BUFFER UNDERRUN",
        "PortAudio output_underflow",
        "Unexpected audio shape",
        "Dropped stale pre-generated section",
        "Pre-generation produced no events",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        for s in self._SUBSTRINGS:
            if s in msg:
                return False
        return True


class _ConsoleNoWarningsFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            lvl = int(getattr(record, "levelno", 0) or 0)
        except Exception:
            return True
        return lvl != logging.WARNING


class _WarningsOnlyFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            lvl = int(getattr(record, "levelno", 0) or 0)
        except Exception:
            return False
        return lvl == logging.WARNING


def setup_logging(*, verbose: bool = False, quiet: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers:
        return

    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        logs_dir = None

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(stream=sys.stdout)
    if bool(quiet):
        console.setLevel(logging.ERROR)
    elif bool(verbose):
        console.setLevel(logging.DEBUG)
    else:
        console.setLevel(logging.INFO)
    console.setFormatter(fmt)

    if not bool(verbose):
        console.addFilter(_ConsoleQuietFilter())
        console.addFilter(_ConsoleNoWarningsFilter())
    root.addHandler(console)

    if logs_dir is not None:
        log_path = logs_dir / "runtime.log"
        fileh = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=10,
            encoding="utf-8",
        )
        fileh.setLevel(logging.DEBUG)
        fileh.setFormatter(fmt)
        root.addHandler(fileh)

        warnings_path = logs_dir / "warnings.log"
        warnh = logging.handlers.RotatingFileHandler(
            str(warnings_path),
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=5,
            encoding="utf-8",
        )
        warnh.setLevel(logging.WARNING)
        warnh.setFormatter(fmt)
        warnh.addFilter(_WarningsOnlyFilter())
        root.addHandler(warnh)


def safe_sorted_str_keys(mapping_obj) -> List[str]:
    try:
        return sorted(str(k) for k in dict(mapping_obj or {}).keys())
    except Exception:
        return []


def discover_preset_families(config) -> Dict[str, List[str]]:
    families: Dict[str, List[str]] = {
        "meta_presets": [],
        "sample_packs": safe_sorted_str_keys(getattr(config, "sample_packs", {})),
        "style_profiles": safe_sorted_str_keys(getattr(config, "style_profiles", {})),
        "conversation_presets": safe_sorted_str_keys(getattr(config, "conversation_presets", {})),
        "fx_presets": safe_sorted_str_keys(getattr(config, "post_process_presets", {})),
        "arrangement_modes": [],
        "style_architectures": [],
        "producer_macros": ["cinematic", "club", "intimate", "narrative"],
    }
    try:
        from presets import list_presets
        families["meta_presets"] = sorted(str(x) for x in list_presets())
    except Exception:
        families["meta_presets"] = []
    try:
        from composition.policies import ArrangementPolicy
        families["arrangement_modes"] = sorted(str(k) for k in dict(getattr(ArrangementPolicy, "_FORM_SEQUENCES", {}) or {}).keys())
    except Exception:
        families["arrangement_modes"] = ["default"]
    try:
        from data.style_architecture_macros import STYLE_ARCHITECTURE_MACROS
        families["style_architectures"] = sorted(str(k) for k in dict(STYLE_ARCHITECTURE_MACROS or {}).keys())
    except Exception:
        families["style_architectures"] = []
    return families


def print_preset_family_block(title: str, values: List[str]) -> None:
    vals = list(values or [])
    print(f"{title} ({len(vals)}):")
    if not vals:
        print("  -")
        return
    for v in vals:
        print(f"  {v}")


def apply_drums_enabled(config, enabled: bool) -> None:
    on = bool(enabled)
    try:
        sc = getattr(getattr(config, "audio", None), "chorus_kick_sidechain", None)
        if sc is not None:
            sc.enabled = on
            sc.kick_enabled = on
            sc.sidechain_enabled = on
    except Exception:
        logging.debug("Could not update chorus_kick_sidechain", exc_info=True)
    try:
        c = getattr(config, "composition", None)
        if c is not None:
            c.percussion_lane_enabled = on
    except Exception:
        logging.debug("Could not update percussion_lane_enabled", exc_info=True)
    logging.info("Drums %s (chorus kick + sidechain pump)", "on" if on else "off")


def resolve_drums_from_args(config, args) -> None:
    drums_arg = getattr(args, "drums", None)
    if drums_arg is None:
        return
    apply_drums_enabled(config, bool(drums_arg))


def resolve_default_preset_name() -> Optional[str]:
    env = str(os.environ.get("AUDIOGEN_DEFAULT_PRESET", "") or "").strip()
    if env:
        return env
    try:
        p = Path(__file__).resolve().parent.parent / ".audiogen" / "default_preset.txt"
        if p.exists():
            name = str(p.read_text(encoding="utf-8")).strip()
            if name:
                return name
    except Exception:
        pass
    return None


def apply_startup_configs(args, config) -> Optional[str]:
    config.set_performance_mode(str(getattr(args, "performance", "high") or "high"))
    try:
        from utils.numba_warmup import warmup_numba_kernels
        warmup_numba_kernels()
    except Exception:
        pass

    preset_name = str(args.preset).strip() if args.preset else resolve_default_preset_name()
    if preset_name:
        from presets import load_preset
        from presets.config_applier import apply_macros_snapshot, apply_preset_to_config
        try:
            p = load_preset(str(preset_name))
            apply_preset_to_config(config, p)
            apply_macros_snapshot(config, dict(getattr(p, "macros", {}) or {}))
            logging.info("Loaded preset: %s", str(preset_name))
        except Exception:
            logging.exception("Failed to load preset: %s", str(preset_name))

    if args.pack:
        config.set_sample_pack(str(args.pack))
    if args.style:
        config.set_style_profile(str(args.style))
    if args.style_architecture:
        try:
            from data.style_architecture_macros import apply_style_architecture, canonical_style_name
            style_key = canonical_style_name(str(args.style_architecture))
            if not apply_style_architecture(getattr(config, "composition", None), style_key):
                logging.warning("Unknown style architecture '%s'", str(args.style_architecture))
        except Exception:
            logging.exception("Failed to apply style architecture: %s", str(args.style_architecture))

    # Conversation preset resolution is done inside ui_realtime_cli when running interactively,
    # or direct apply if options set:
    if args.conversation:
        config.set_conversation_preset(str(args.conversation))
    elif bool(getattr(args, "ambient01", False)):
        config.set_conversation_preset("ambient01")

    if args.fx:
        try:
            config.set_post_process_preset(str(args.fx))
        except Exception:
            config.audio.active_post_process_preset = str(args.fx)

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
    except Exception:
        pass

    if args.arrangement:
        try:
            setattr(config.composition, "arranged_song_mode", str(args.arrangement))
        except Exception:
            pass

    producer_macros = list(getattr(args, "producer_macro", None) or [])
    producer_amount = float(getattr(args, "producer_macro_amount", 1.0) or 1.0)
    for macro_name in producer_macros:
        try:
            config.set_producer_macro(str(macro_name), amount=producer_amount)
            logging.info("Applied producer macro: %s (amount=%.2f)", str(macro_name), float(producer_amount))
        except Exception:
            logging.exception("Failed to apply producer macro: %s", str(macro_name))

    if bool(getattr(args, "narrative_macro", False)):
        narrative_amount = float(getattr(args, "narrative_macro_amount", 1.0) or 1.0)
        try:
            config.set_producer_macro("narrative", amount=narrative_amount)
            logging.info("Applied producer macro: narrative (amount=%.2f)", float(narrative_amount))
        except Exception:
            logging.exception("Failed to apply narrative producer macro")

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

    # Variety amount
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

    if bool(getattr(args, "hook_safe", True)):
        try:
            config.set_composition_hook_safe_mode(True)
        except Exception:
            pass

    from audiogen_core.composition_config import apply_melody_staged_experimental_bundle
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

    full_start = getattr(args, "full_arrangement_start", None)
    if full_start is not None:
        try:
            config.composition.arranged_realtime_full_timeline = bool(full_start)
        except Exception:
            pass

    return preset_name


def initialize_generator(args, config, gen, launch_seed: int) -> None:
    try:
        setattr(config.composition, "seed", int(launch_seed))
        setattr(config.composition, "user_pinned_seed", bool(args.seed is not None))
    except Exception:
        pass
    try:
        config.composition.warm_runtime_profile_cache()
    except Exception:
        pass
    try:
        gen.reseed(int(launch_seed))
    except Exception:
        pass
    try:
        logging.info("Generation seed (this run): %d", int(launch_seed))
    except Exception:
        pass
    if bool(getattr(args, "fresh_on_start", False)):
        try:
            gen.reset_song_arrangement_state()
        except Exception:
            pass

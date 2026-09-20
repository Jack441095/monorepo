
import logging

logger = logging.getLogger(__name__)


def apply_performance_mode(config, mode: str = "balanced"):
    """Apply a named performance profile onto a ConfigurationManager instance."""
    raw = str(mode or "").strip().lower()
    # Canonical two-mode interface:
    # - "high": higher CPU / richer audio (legacy "quality")
    # - "low": lower CPU / most RT-safe (legacy "maximum")
    #
    # Backwards compatible inputs:
    # - "quality" -> "high"
    # - "maximum" -> "low"
    # - "balanced" -> "low" (closest intent; warn once here)
    if raw in ("high", "quality"):
        mode = "high"
    elif raw in ("low", "maximum"):
        mode = "low"
    elif raw == "balanced":
        mode = "low"
        logger.warning("Performance mode 'balanced' is deprecated; mapping to 'low'")
    else:
        raise ValueError(f"Unknown performance mode '{mode}' (expected: high|low)")

    config._performance_mode = mode
    if mode == "low":
        config.audio.sample_rate = 44100
        config.audio.buffer_size = 8192
        config.audio.fade_samples = 32
        # Keep the shared return reverb active even in low CPU mode. It is part of the
        # global mix glue; runtime quality tiers already reduce its cost under pressure.
        config.audio.reverb_enabled = True
        config.audio.reverb_rt60 = 10.0
        config.audio.reverb_damping = 0.62
        config.audio.reverb_wet = 0.22
        config.audio.rt_reverb_default_tier = "safe"
        config.audio.rt_reverb_min_quality_tier = "safe"
        config.audio.rt_reverb_adaptive_high_enabled = False
        config.audio.rt_master_proactive_fast_path = True
        config.audio.rt_fast_master_ratio = 0.80
        config.audio.cold_start_preview_bars = 1
        config.audio.cold_start_preview_runtime_mode = "preview"
        config.audio.cold_start_preview_planner_effort = "minimal"
        config.audio.cold_start_defer_pregen_until_first_bar = True
        config.composition.arranged_emotion_switch_preview_sections = 1
        config.audio.distortion_enabled = False
        config.audio.distortion_mix = 0.0
        config.audio.master_limiter_lookahead_ms = 3.0
        for sampler in config.samplers:
            sampler_name = str(getattr(sampler, "name", "") or "")
            sampler.filter_order = 1
            sampler.quality_mode = config.QualityMode.LOW
            # Keep LPF envelopes on all channels except drone (CPU savings come from
            # lower filter order / low quality mode rather than disabling articulation).
            sampler.filter_envelope_enabled = bool(sampler_name != "drone")
            # Keep low mode realtime-safe.
            try:
                sampler.transposition_quality_mode = "fast"
            except Exception:
                pass
            try:
                sampler.note_cache_maxsize = max(192, int(getattr(sampler, "note_cache_maxsize", 64) or 64))
            except Exception:
                pass
            if sampler_name == "chords":
                # Chord random-start makes every sustained pad unique, which intentionally
                # disables note/chord caches. In low CPU mode the cache wins: arrangement and
                # humanization still vary the music, while repeated pad renders become reusable.
                sampler.filter_envelope_enabled = False
                try:
                    sampler.random_start_within_loop = False
                except Exception:
                    pass
                try:
                    sampler.shimmer_enabled = False
                except Exception:
                    pass
                try:
                    sampler.note_cache_maxsize = max(256, int(getattr(sampler, "note_cache_maxsize", 64) or 64))
                except Exception:
                    pass
        # Keep staged melody upgrades off for low CPU mode.
        try:
            config.composition.melody_staged_experimental_bundle_enabled = False
        except Exception:
            pass
        try:
            config.composition.section_pick_use_wall_clock = True
        except Exception:
            pass
        try:
            from utils.numba_warmup import warmup_numba_kernels

            warmup_numba_kernels()
        except Exception:
            pass
        logger.info("Performance mode: LOW CPU")
    elif mode == "high":
        from audiogen_core.composition_config import apply_melody_staged_experimental_bundle

        config.audio.sample_rate = 48000
        config.audio.buffer_size = 4096
        config.audio.fade_samples = 128
        config.audio.reverb_enabled = True
        # Global long return; low end is removed on the reverb return for clarity.
        config.audio.reverb_rt60 = 10.0
        config.audio.reverb_damping = 0.62
        config.audio.reverb_wet = 0.24
        for sampler in config.samplers:
            sampler_name = str(getattr(sampler, "name", "") or "")
            sampler.filter_order = 4
            sampler.quality_mode = config.QualityMode.HIGH
            sampler.filter_envelope_enabled = True
            # "auto" picks cubic interpolation when quality mode is HIGH.
            try:
                sampler.transposition_quality_mode = "fast" if sampler_name == "drone" else "auto"
            except Exception:
                pass
            if sampler_name == "chords":
                try:
                    sampler.random_start_within_loop = False
                except Exception:
                    pass
        # Quality mode should enable staged Markov melody upgrades by default.
        try:
            config.composition.melody_staged_experimental_bundle_enabled = True
            apply_melody_staged_experimental_bundle(config.composition)
        except Exception:
            pass
        try:
            config.composition.section_pick_use_wall_clock = True
        except Exception:
            pass
        try:
            config.audio.rt_reverb_default_tier = "high_rt"
            config.audio.rt_reverb_min_quality_tier = "balanced"
            config.audio.rt_reverb_adaptive_high_enabled = True
            config.audio.cold_start_preview_bars = 2
            config.audio.cold_start_preview_runtime_mode = "normal"
            config.audio.cold_start_preview_planner_effort = "full"
            config.audio.cold_start_defer_pregen_until_first_bar = False
            config.composition.arranged_emotion_switch_preview_sections = 2
            config.audio.rt_bypass_master_multiband = True
            config.audio.rt_bypass_master_eq = False
            config.audio.rt_fast_master_ratio = 0.88
        except Exception:
            pass
        try:
            from utils.numba_warmup import warmup_numba_kernels

            warmup_numba_kernels()
        except Exception:
            pass
        logger.info("Performance mode: HIGH CPU")

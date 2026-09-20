from audiogen_core.config import ConfigurationManager


def _sampler_by_name(config: ConfigurationManager, name: str):
    for sampler in config.samplers:
        if str(getattr(sampler, "name", "") or "") == name:
            return sampler
    raise AssertionError(f"missing sampler {name!r}")


def test_low_performance_makes_chords_cacheable():
    config = ConfigurationManager()

    config.set_performance_mode("low")
    chords = _sampler_by_name(config, "chords")

    assert chords.random_start_within_loop is False
    assert chords.shimmer_enabled is False
    assert chords.filter_envelope_enabled is False
    assert chords.transposition_quality_mode == "fast"
    assert chords.note_cache_maxsize >= 256
    assert config.audio.rt_reverb_default_tier == "safe"
    assert config.audio.rt_reverb_min_quality_tier == "safe"
    assert config.audio.rt_reverb_adaptive_high_enabled is False
    assert config.audio.cold_start_preview_bars == 1
    assert config.audio.cold_start_preview_runtime_mode == "preview"
    assert config.audio.cold_start_preview_planner_effort == "minimal"
    assert config.audio.cold_start_defer_pregen_until_first_bar is True
    assert config.composition.arranged_emotion_switch_preview_sections == 1


def test_high_performance_restores_chord_texture_random_start():
    config = ConfigurationManager()

    config.set_performance_mode("low")
    config.set_performance_mode("high")
    chords = _sampler_by_name(config, "chords")

    assert chords.random_start_within_loop is False
    assert chords.transposition_quality_mode == "auto"
    assert config.audio.rt_reverb_default_tier == "high_rt"
    assert config.audio.rt_reverb_min_quality_tier == "balanced"
    assert config.audio.rt_reverb_adaptive_high_enabled is True
    assert config.audio.cold_start_preview_bars == 2
    assert config.audio.cold_start_preview_runtime_mode == "normal"
    assert config.audio.cold_start_preview_planner_effort == "full"
    assert config.audio.cold_start_defer_pregen_until_first_bar is False
    assert config.composition.arranged_emotion_switch_preview_sections == 2


def test_rebuild_samplers_preserves_active_performance_mode():
    config = ConfigurationManager()

    config.set_performance_mode("low")
    config.rebuild_samplers()
    chords = _sampler_by_name(config, "chords")

    assert chords.random_start_within_loop is False
    assert chords.transposition_quality_mode == "fast"

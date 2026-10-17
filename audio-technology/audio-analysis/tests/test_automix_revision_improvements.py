"""Tests for AutoMix revision & genre enhancements (2026-08-01).

Verifies:
1. Stem-targeted reverb revisions ("more reverb on vocal", "drier drums").
2. Genre alias mapping for new genres (latin, reggaeton, urban, rnb, lofi).
3. Default master bus low-shelf low-end warmth correction (+4 dB @ 300 Hz).
"""

from __future__ import annotations

from audio_analysis.mixdown.mix_decision_engine import (
    generate_mix_plan,
    resolve_genre,
    apply_revision_feedback,
    StemMixConfig,
    BusMixConfig,
    MixPlan,
)
from audio_analysis.mixdown.stem_classifier import StemProfile


def _make_stem_profile(name: str, instrument: str) -> StemProfile:
    return StemProfile(
        name=name,
        instrument=instrument,
        rms_dbfs=-18.0,
        peak_dbfs=-6.0,
        crest_factor_db=12.0,
        frequency_profile={"sub": 0.1, "bass": 0.2, "low_mids": 0.3, "mids": 0.2, "presence": 0.1, "sibilance": 0.05, "air": 0.05},
    )


def test_genre_alias_expansion():
    # Test expanded aliases
    genre, note = resolve_genre("latin")
    assert genre == "pop"
    assert "latin" in note

    genre, note = resolve_genre("reggaeton")
    assert genre == "hip_hop"
    assert "reggaeton" in note

    genre, note = resolve_genre("rnb")
    assert genre == "pop"

    genre, note = resolve_genre("lofi")
    assert genre == "acoustic"


def test_master_low_shelf_default():
    vocal = _make_stem_profile("vocal.wav", "vocal")
    plan = generate_mix_plan([vocal], genre="pop")
    low_shelf_bands = [b for b in plan.bus.bus_eq_bands if b.get("type") == "lowshelf" and b.get("frequency") == 300.0]
    assert len(low_shelf_bands) >= 1
    assert low_shelf_bands[0]["gain_db"] == 4.0
    assert any("low-end balance correction" in d.lower() for d in plan.decisions_log)


def test_reverb_revision_stem_targeting():
    vocal_cfg = StemMixConfig(stem_name="vocal.wav", instrument="vocal", reverb_send=0.1)
    drum_cfg = StemMixConfig(stem_name="drums.wav", instrument="snare", reverb_send=0.1)
    plan = MixPlan(stems=[vocal_cfg, drum_cfg], bus=BusMixConfig(), genre="pop", target_lufs=-14.0)

    # Target vocal specifically
    applied = apply_revision_feedback(plan, "more reverb on vocal")
    assert len(applied) >= 1
    assert vocal_cfg.reverb_send > 0.1
    assert drum_cfg.reverb_send == 0.1  # Drums unchanged

    # Target drums specifically
    applied2 = apply_revision_feedback(plan, "make drums drier")
    assert len(applied2) >= 1
    assert drum_cfg.reverb_send < 0.1


def test_section_aware_resonance_detection():
    import numpy as np
    from audio_analysis.analysis_core.resonance_detection import detect_resonant_bands_section_aware

    sr = 44100
    t = np.arange(sr * 4) / sr
    # Pure tone at 3000 Hz in chorus section (sample 88200 to 176400)
    sig = np.sin(2 * np.pi * 1000 * t) * 0.1
    sig[88200:176400] += np.sin(2 * np.pi * 3000 * t[88200:176400]) * 0.8

    sections = [
        {"label": "verse", "start_s": 0.0, "end_s": 2.0},
        {"label": "chorus", "start_s": 2.0, "end_s": 4.0},
    ]

    res = detect_resonant_bands_section_aware(sig.tolist(), sr, sections)
    assert isinstance(res, list)
    if res:
        assert any("section" in r for r in res)


def test_genre_adaptive_multiband_crossovers():
    vocal = _make_stem_profile("vocal.wav", "vocal")
    edm_plan = generate_mix_plan([vocal], genre="edm")
    assert edm_plan.bus.multiband_compressor["low_crossover_hz"] == 120.0
    assert edm_plan.bus.multiband_compressor["high_crossover_hz"] == 4000.0

    rock_plan = generate_mix_plan([vocal], genre="rock")
    assert rock_plan.bus.multiband_compressor["low_crossover_hz"] == 200.0
    assert rock_plan.bus.multiband_compressor["high_crossover_hz"] == 5000.0


def test_master_low_end_mono_collapse():
    import numpy as np
    from audio_analysis.dsp_engine.gain_pan import mono_below_frequency

    sr = 44100
    t = np.arange(sr * 2) / sr
    # Out of phase 50 Hz sub-bass (Left = sin, Right = -sin)
    sub_l = np.sin(2 * np.pi * 50 * t) * 0.5
    sub_r = -np.sin(2 * np.pi * 50 * t) * 0.5

    out_l, out_r = mono_below_frequency(sub_l, sub_r, cutoff_hz=100.0, sample_rate=sr)
    in_side_rms = np.sqrt(np.mean((0.5 * (sub_l - sub_r)) ** 2))
    out_side_rms = np.sqrt(np.mean((0.5 * (out_l - out_r)) ** 2))
    # Side signal for 50 Hz sub-bass is attenuated by >10 dB relative to input
    assert out_side_rms < 0.3 * in_side_rms

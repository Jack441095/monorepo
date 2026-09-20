"""Closed-loop integration test connecting AudioGen and AutoMix pipelines."""

from __future__ import annotations

import io
import numpy as np
import scipy.io.wavfile as wavfile

from composition.groove_engine import apply_groove_to_events
from utils.automix_export import export_automix_meta
from audio_analysis.mixdown.mix_decision_engine import MixPlan, StemMixConfig, BusMixConfig
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
from audio_analysis.analysis_core.loudness_api import calculate_lufs


def _make_stem_wav_bytes(sr: int = 44100, freq: float = 440.0, dur_s: float = 2.0, amp: float = 0.5) -> bytes:
    t = np.linspace(0, dur_s, int(sr * dur_s))
    sig = amp * np.sin(2 * np.pi * freq * t)
    pcm = (sig * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    wavfile.write(buf, sr, pcm)
    return buf.getvalue()


def test_audiogen_automix_closed_loop_pipeline(tmp_path):
    # 1. Simulate AudioGen MIDI event generation with GrooveEngine
    raw_events = [
        {"start_tick": 0, "duration_ticks": 120, "velocity": 90, "role": "kick"},
        {"start_tick": 120, "duration_ticks": 120, "velocity": 80, "role": "snare"},
        {"start_tick": 240, "duration_ticks": 120, "velocity": 85, "role": "vocal"},
    ]
    grooved_events = apply_groove_to_events(raw_events, groove="edm", ticks_per_16th=120, seed=42)
    assert len(grooved_events) == 3

    # 2. Export stems and automix_meta.json
    sr = 44100
    dur_s = 2.0
    stems_dict = {
        "kick.wav": ("kick", 60.0, 0.7),
        "bass.wav": ("bass", 110.0, 0.5),
        "vocal.wav": ("vocal", 440.0, 0.6),
        "pad.wav": ("pad", 880.0, 0.3),
    }

    prepared_stems = []
    stem_roles = {}

    for fname, (role, freq, amp) in stems_dict.items():
        wav_b = _make_stem_wav_bytes(sr=sr, freq=freq, dur_s=dur_s, amp=amp)
        # Parse WAV samples for AutoMix renderer
        rate, data = wavfile.read(io.BytesIO(wav_b))
        norm_data = data.astype(np.float64) / 32768.0
        prepared_stems.append({
            "name": fname,
            "samples": norm_data,
            "sample_rate": sr,
        })
        stem_roles[fname] = role

    meta_path = export_automix_meta(
        output_dir=tmp_path,
        stem_roles=stem_roles,
        genre="pop",
        target_lufs=-14.0,
        bpm=120.0,
        key="C_major",
    )
    assert meta_path.exists()

    # 3. Create AutoMix MixPlan
    stem_configs = [
        StemMixConfig(stem_name=fname, instrument=role, gain_db=0.0)
        for fname, (role, _, _) in stems_dict.items()
    ]
    bus_config = BusMixConfig(limiter_ceiling_db=-1.0)
    mix_plan = MixPlan(
        stems=stem_configs,
        bus=bus_config,
        genre="pop",
        target_lufs=-14.0,
        apply_masking_corrections=True,
        apply_proactive_crest_reduction=True,
    )

    # 4. Render Master Mixdown
    render = mix_and_render_stems(prepared_stems, mix_plan)
    assert "mixdown_wav_bytes" in render
    assert "left" in render
    assert "right" in render

    left = render["left"]
    right = render["right"]

    # 5. Independent Output Quality Audits
    from audio_analysis.analysis_core.loudness import calculate_true_peak_numpy
    max_tp = calculate_true_peak_numpy(left, right)

    # True-peak must be at or below -1.0 dBTP ceiling
    assert max_tp <= -0.85  # Margin allowance for resampling

    lufs = calculate_lufs(left.tolist(), right.tolist(), sr)
    # Output integrated LUFS must be within professional tolerance
    assert abs(lufs - (-14.0)) <= 1.0

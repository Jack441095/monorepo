"""Tests for render_unprocessed_stem_sum() -- the "before AutoMix touched it"
raw baseline used by the before/after comparison (business/app/automix_worker.py).
Unlike mix_and_render_stems(), this applies zero DSP: no gain staging, EQ,
compression, panning, or bus processing, and it must never silently drop or
attenuate a stem.
"""

from __future__ import annotations

import numpy as np
import pytest

from audio_analysis.mixdown.mix_renderer import render_unprocessed_stem_sum
from audio_analysis.utils.audio_io import read_wav_mono

SR = 44100
N = 4410  # 0.1s


def _mono_stem(name: str, level: float) -> dict:
    return {"name": name, "sample_rate": SR, "samples": np.full(N, level, dtype=np.float64)}


def _stereo_stem(name: str, left_level: float, right_level: float) -> dict:
    return {
        "name": name,
        "sample_rate": SR,
        "samples": np.full(N, (left_level + right_level) * 0.5, dtype=np.float64),
        "left_samples": np.full(N, left_level, dtype=np.float64),
        "right_samples": np.full(N, right_level, dtype=np.float64),
        "stereo_preserved": True,
    }


def _decode(wav_bytes: bytes):
    d = read_wav_mono(wav_bytes, max_samples=0)
    return d


def test_stereo_stems_sum_independently_not_mono_averaged():
    stems = [_stereo_stem("a.wav", 0.10, 0.20), _stereo_stem("b.wav", 0.05, 0.05)]
    result = render_unprocessed_stem_sum(stems)

    assert np.allclose(result["left"], 0.15, atol=1e-6)
    assert np.allclose(result["right"], 0.25, atol=1e-6)
    # A mono-average approach would have collapsed left/right to the same
    # value; the real stereo image must survive.
    assert not np.allclose(result["left"], result["right"])


def test_mono_stem_duplicated_to_both_channels():
    stems = [_mono_stem("kick.wav", 0.2)]
    result = render_unprocessed_stem_sum(stems)

    assert np.allclose(result["left"], 0.2, atol=1e-6)
    assert np.allclose(result["right"], 0.2, atol=1e-6)


def test_mixed_mono_and_stereo_stems_sum_together():
    stems = [_mono_stem("kick.wav", 0.1), _stereo_stem("pad.wav", 0.05, -0.05)]
    result = render_unprocessed_stem_sum(stems)

    assert np.allclose(result["left"], 0.15, atol=1e-6)
    assert np.allclose(result["right"], 0.05, atol=1e-6)


def test_no_gain_reduction_is_applied():
    """The whole point of the baseline is an honest, unprocessed sum -- three
    stems at 0.2 must sum to 0.6, not be auto-normalized down."""
    stems = [_mono_stem(f"s{i}.wav", 0.2) for i in range(3)]
    result = render_unprocessed_stem_sum(stems)

    assert np.allclose(result["left"], 0.6, atol=1e-6)


def test_returns_decodable_wav_bytes_at_correct_sample_rate():
    stems = [_stereo_stem("a.wav", 0.1, 0.1)]
    result = render_unprocessed_stem_sum(stems)

    assert isinstance(result["mixdown_wav_bytes"], bytes)
    assert len(result["mixdown_wav_bytes"]) > 44  # bigger than a bare WAV header
    decoded = _decode(result["mixdown_wav_bytes"])
    assert decoded["sample_rate"] == SR


def test_stem_audio_breakdown_matches_the_raw_per_stem_channels():
    stems = [_stereo_stem("a.wav", 0.10, 0.20), _mono_stem("b.wav", 0.3)]
    result = render_unprocessed_stem_sum(stems)

    assert set(result["stem_audio"]) == {"a.wav", "b.wav"}
    a_left, a_right = result["stem_audio"]["a.wav"]
    assert np.allclose(a_left, 0.10, atol=1e-6)
    assert np.allclose(a_right, 0.20, atol=1e-6)
    b_left, b_right = result["stem_audio"]["b.wav"]
    assert np.allclose(b_left, 0.3, atol=1e-6)
    assert np.allclose(b_right, 0.3, atol=1e-6)


def test_empty_prepared_stems_raises():
    with pytest.raises(ValueError):
        render_unprocessed_stem_sum([])


def test_unaligned_stereo_stem_raises():
    good = _stereo_stem("a.wav", 0.1, 0.1)
    bad = _stereo_stem("b.wav", 0.1, 0.1)
    bad["left_samples"] = bad["left_samples"][:-10]
    with pytest.raises(ValueError):
        render_unprocessed_stem_sum([good, bad])


def test_unaligned_mono_stem_raises():
    good = _mono_stem("a.wav", 0.1)
    bad = _mono_stem("b.wav", 0.1)
    bad["samples"] = bad["samples"][:-10]
    with pytest.raises(ValueError):
        render_unprocessed_stem_sum([good, bad])

"""Reference spectral match (mixdown/spectral_match.py) — the engine that powers
`automix_local --match-reference` and the automix worker's reference matching.
Self-contained: synthetic bass-light "mix" vs bass-heavy "reference".
"""

from __future__ import annotations

import io
import wave
from pathlib import Path

import numpy as np
import pytest

from audio_analysis.mixdown.spectral_match import (
    compute_reference_dynamics_comp,
    compute_reference_match_bands,
    compute_reference_width_factor,
    reference_target_40band,
    reference_target_stereo_width,
)

SR = 44100


def _wav_bytes(sig: np.ndarray) -> bytes:
    pcm = (np.clip(sig, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return out.getvalue()


def _stereo_wav_bytes(mid: np.ndarray, side: np.ndarray) -> bytes:
    """Build a stereo WAV directly from mid/side components so the resulting
    overall stereo width (side/mid RMS ratio) is controllable and known."""
    left = np.clip(mid + side, -1.0, 1.0)
    right = np.clip(mid - side, -1.0, 1.0)
    interleaved = np.empty(left.size + right.size, dtype=np.float64)
    interleaved[0::2] = left
    interleaved[1::2] = right
    pcm = (interleaved * 32767.0).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    return out.getvalue()


def _mid_side_signal(seconds: float = 6.0, *, side_amplitude: float = 0.1, seed: int = 4) -> tuple[np.ndarray, np.ndarray]:
    """A broadband mid signal plus a decorrelated side signal scaled to
    ``side_amplitude`` -- controls the resulting stereo width directly."""
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    rng = np.random.default_rng(seed)
    mid = 0.3 * sum(np.sin(2 * np.pi * f * t) for f in (110.0, 440.0, 2000.0))
    side = side_amplitude * rng.standard_normal(len(t))
    return mid.astype(np.float64), side.astype(np.float64)


def _tone_mix(weights: dict[float, float], seconds: float = 6.0) -> np.ndarray:
    """Sum of tones at given freqs with given amplitudes + light noise."""
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
    sig = sum(a * np.sin(2 * np.pi * f * t) for f, a in weights.items())
    sig += 0.01 * np.random.default_rng(1).standard_normal(len(t))
    return sig.astype(np.float64)


def test_match_boosts_low_end_toward_bassy_reference(tmp_path: Path) -> None:
    # Mix: bright / bass-light. Reference: bass-heavy.
    mix = _wav_bytes(_tone_mix({60: 0.02, 250: 0.05, 3000: 0.4, 9000: 0.3}))
    ref_path = tmp_path / "reference.wav"
    ref_path.write_bytes(_wav_bytes(_tone_mix({60: 0.5, 250: 0.35, 3000: 0.1, 9000: 0.05})))

    bands = compute_reference_match_bands(mix, ref_path)
    assert bands, "match should produce correction bands for a clearly mismatched pair"
    # Iterative passes revisit the same log centres. Delivery must contain one
    # bounded, explainable move per centre rather than a repeated cascade.
    assert len(bands) <= 10
    assert len({(b["type"], b["frequency"], b["q"]) for b in bands}) == len(bands)
    # Every band is a peaking bell with the documented shape.
    for b in bands:
        assert b["type"] == "peaking"
        assert 20.0 <= b["frequency"] <= 20000.0
        assert -3.0 <= b["gain_db"] <= 6.0  # boost-biased clamp

    # Net low-end move must be a BOOST (mix is bass-light vs the reference).
    low_gain = sum(b["gain_db"] for b in bands if b["frequency"] < 300)
    high_gain = sum(b["gain_db"] for b in bands if b["frequency"] > 3000)
    assert low_gain > 0, f"expected net low-end boost, got {low_gain:+.1f} dB"
    # Boost-biased: low-end boost should dominate the (scaled) high-end cuts.
    assert low_gain > abs(high_gain)


def test_genre_average_target_median_over_directory(tmp_path: Path) -> None:
    # Two bass-heavy refs + one outlier bright ref; median should stay bass-forward.
    d = tmp_path / "refs"
    d.mkdir()
    (d / "a.wav").write_bytes(_wav_bytes(_tone_mix({60: 0.5, 250: 0.3, 3000: 0.1})))
    (d / "b.wav").write_bytes(_wav_bytes(_tone_mix({60: 0.45, 250: 0.35, 3000: 0.1})))
    (d / "c.wav").write_bytes(_wav_bytes(_tone_mix({60: 0.0, 250: 0.02, 8000: 0.6})))  # outlier

    target, n_refs = reference_target_40band(d)
    assert n_refs == 3
    assert target.shape == (40,)
    assert abs(float(target.sum()) - 1.0) < 1e-6  # renormalised
    # Median rejects the bright outlier -> low bands retain real energy.
    assert float(target[:8].sum()) > 0.05


def test_no_reference_audio_raises(tmp_path: Path) -> None:
    (tmp_path / "not_audio.txt").write_text("nope")
    with pytest.raises(ValueError):
        reference_target_40band(tmp_path)


class TestReferenceTargetStereoWidth:
    def test_wider_reference_yields_a_higher_target_than_narrower(self, tmp_path: Path) -> None:
        mid_n, side_n = _mid_side_signal(side_amplitude=0.03, seed=1)
        mid_w, side_w = _mid_side_signal(side_amplitude=0.35, seed=2)
        narrow = tmp_path / "narrow.wav"
        wide = tmp_path / "wide.wav"
        narrow.write_bytes(_stereo_wav_bytes(mid_n, side_n))
        wide.write_bytes(_stereo_wav_bytes(mid_w, side_w))

        w_narrow = reference_target_stereo_width(narrow)
        w_wide = reference_target_stereo_width(wide)
        assert w_narrow is not None and w_wide is not None
        assert w_wide > w_narrow

    def test_median_over_a_reference_folder(self, tmp_path: Path) -> None:
        d = tmp_path / "refs"
        d.mkdir()
        for i, amp in enumerate((0.10, 0.15, 0.90)):  # 0.90 is a wide outlier
            mid, side = _mid_side_signal(side_amplitude=amp, seed=10 + i)
            (d / f"r{i}.wav").write_bytes(_stereo_wav_bytes(mid, side))

        target = reference_target_stereo_width(d)
        low = reference_target_stereo_width(d / "r0.wav")
        outlier = reference_target_stereo_width(d / "r2.wav")
        assert target is not None
        # Median sits between the tight pair and the outlier, closer to the pair.
        assert low < target < outlier

    def test_mono_only_references_return_none(self, tmp_path: Path) -> None:
        d = tmp_path / "mono_refs"
        d.mkdir()
        (d / "a.wav").write_bytes(_wav_bytes(_tone_mix({220: 0.3})))
        assert reference_target_stereo_width(d) is None


class TestComputeReferenceWidthFactor:
    def test_nudges_up_toward_a_wider_reference_but_stays_within_the_clamp(self, tmp_path: Path) -> None:
        mid_mix, side_mix = _mid_side_signal(side_amplitude=0.03, seed=5)  # narrow mix
        mid_ref, side_ref = _mid_side_signal(side_amplitude=0.9, seed=6)  # much wider reference
        mix_bytes = _stereo_wav_bytes(mid_mix, side_mix)
        ref_path = tmp_path / "wide_ref.wav"
        ref_path.write_bytes(_stereo_wav_bytes(mid_ref, side_ref))

        factor = compute_reference_width_factor(mix_bytes, ref_path)
        assert factor is not None
        assert factor > 1.0, "reference is much wider -- should nudge width UP"
        # Hard safety clamp: never more than a 15% widen, no matter the gap.
        assert factor <= 1.15 + 1e-9

    def test_nudges_down_toward_a_narrower_reference(self, tmp_path: Path) -> None:
        mid_mix, side_mix = _mid_side_signal(side_amplitude=0.9, seed=7)  # wide mix
        mid_ref, side_ref = _mid_side_signal(side_amplitude=0.03, seed=8)  # much narrower reference
        mix_bytes = _stereo_wav_bytes(mid_mix, side_mix)
        ref_path = tmp_path / "narrow_ref.wav"
        ref_path.write_bytes(_stereo_wav_bytes(mid_ref, side_ref))

        factor = compute_reference_width_factor(mix_bytes, ref_path)
        assert factor is not None
        assert factor < 1.0, "reference is much narrower -- should nudge width DOWN"
        assert factor >= 0.85 - 1e-9

    def test_within_deadband_makes_no_correction(self, tmp_path: Path) -> None:
        # Same side_amplitude on both sides -> negligible relative gap, well
        # under the 15% deadband; not worth correcting.
        mid_mix, side_mix = _mid_side_signal(side_amplitude=0.2, seed=9)
        mid_ref, side_ref = _mid_side_signal(side_amplitude=0.21, seed=11)
        mix_bytes = _stereo_wav_bytes(mid_mix, side_mix)
        ref_path = tmp_path / "close_ref.wav"
        ref_path.write_bytes(_stereo_wav_bytes(mid_ref, side_ref))

        assert compute_reference_width_factor(mix_bytes, ref_path) is None

    def test_mono_mixdown_returns_none(self, tmp_path: Path) -> None:
        mid_ref, side_ref = _mid_side_signal(side_amplitude=0.5, seed=12)
        ref_path = tmp_path / "ref.wav"
        ref_path.write_bytes(_stereo_wav_bytes(mid_ref, side_ref))
        mono_mix = _wav_bytes(_tone_mix({220: 0.3}))

        assert compute_reference_width_factor(mono_mix, ref_path) is None


class TestComputeReferenceDynamicsComp:
    """compute_reference_dynamics_comp switched both its read_wav_mono() calls
    to as_arrays=True (avoids the per-chunk decode-time list growth that made
    reading a full mixdown slow), which hands reference_matching.dynamics_comparison
    ndarray-derived data via a single whole-array .tolist() at the call site
    (dynamics_comparison's own rolling-window internals still assume list input
    as of this change). These tests confirm that plumbing runs end-to-end
    without crashing and produces the expected shape of result."""

    def _bursty_mix(self, seconds: float = 4.0) -> np.ndarray:
        n = int(SR * seconds)
        t = np.arange(n)
        # Sharp, high-crest-factor bursts every 100ms.
        sig = np.where((t % 4410) < 441, 0.9, 0.02).astype(np.float64)
        return sig

    def _steady_reference(self, seconds: float = 4.0) -> np.ndarray:
        t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)
        return (0.3 * np.sin(2 * np.pi * 440 * t)).astype(np.float64)

    def test_more_dynamic_mix_returns_compressor_settings(self, tmp_path: Path) -> None:
        mix_bytes = _wav_bytes(self._bursty_mix())
        ref_path = tmp_path / "steady_ref.wav"
        ref_path.write_bytes(_wav_bytes(self._steady_reference()))

        settings = compute_reference_dynamics_comp(mix_bytes, ref_path)

        assert settings is not None
        for key in ("attack_ms", "release_ms", "ratio", "threshold_db", "makeup_gain_db"):
            assert key in settings

    def test_similar_dynamics_returns_none(self, tmp_path: Path) -> None:
        sig = self._steady_reference()
        mix_bytes = _wav_bytes(sig)
        ref_path = tmp_path / "same_ref.wav"
        ref_path.write_bytes(_wav_bytes(sig.copy()))

        assert compute_reference_dynamics_comp(mix_bytes, ref_path) is None

    def test_genre_average_directory_uses_first_file(self, tmp_path: Path) -> None:
        d = tmp_path / "refs"
        d.mkdir()
        (d / "a.wav").write_bytes(_wav_bytes(self._steady_reference()))
        (d / "b.wav").write_bytes(_wav_bytes(self._steady_reference()))
        mix_bytes = _wav_bytes(self._bursty_mix())

        settings = compute_reference_dynamics_comp(mix_bytes, d)
        assert settings is not None

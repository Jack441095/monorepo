"""Streaming DSP core — proves block-based, state-carrying processing equals the
offline render. This equivalence is the correctness contract that lets the
streaming core (the real-time / game-middleware seed) be trusted against the
existing offline DSP.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.ndimage import maximum_filter1d

from audio_analysis.dsp_engine.dynamics import Compressor, Gate, _smooth_attack_release
from audio_analysis.dsp_engine.eq import ParametricEQ
from audio_analysis.dsp_engine.streaming import (
    StreamingCompressor,
    StreamingEQ,
    StreamingGate,
    StreamingLimiter,
)


def _bands(eq):
    eq.add_band("highpass", 80.0, q=0.707)
    eq.add_band("peaking", 300.0, gain_db=-3.0, q=1.2)
    eq.add_band("peaking", 3000.0, gain_db=2.5, q=1.0)
    eq.add_band("highshelf", 8000.0, gain_db=1.5, q=0.707)
    return eq


def _signal(seconds: float = 2.0, sample_rate: int = 48000) -> np.ndarray:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    rng = np.random.default_rng(5)
    x = sum(0.1 * np.sin(2 * np.pi * f * t) for f in (60, 220, 1000, 5000, 12000))
    x += 0.02 * rng.standard_normal(len(t))
    return x.astype(np.float64)


@pytest.mark.parametrize("block_size", [1, 64, 128, 256, 512, 999])
def test_streamed_equals_offline(block_size: int) -> None:
    """StreamingEQ block processing is bit-identical to the offline whole-signal
    render, for any block size (including one that doesn't divide the length)."""
    sr = 48000
    x = _signal(sample_rate=sr)
    offline = _bands(ParametricEQ(sr)).apply(x, linear_phase=False)
    streamed = _bands(StreamingEQ(sr)).process_stream(x, block_size=block_size)
    assert streamed.shape == offline.shape
    assert np.max(np.abs(offline - streamed)) < 1e-9


def test_state_is_carried_not_reset_per_block() -> None:
    """Sanity: without carried state, block-by-block output would differ from
    offline. Prove the difference is real by comparing against a naive
    reset-every-block processing of the same signal."""
    sr = 48000
    x = _signal(sample_rate=sr)
    offline = _bands(ParametricEQ(sr)).apply(x, linear_phase=False)

    # Correct streaming (state carried) matches offline.
    good = _bands(StreamingEQ(sr)).process_stream(x, block_size=128)
    assert np.max(np.abs(offline - good)) < 1e-9

    # Naive per-block filtering that resets state each block does NOT match —
    # confirms carried state is what makes the streaming render correct.
    naive_eq = _bands(ParametricEQ(sr))
    bs = 128
    naive = np.concatenate([
        naive_eq.apply(x[i:i + bs], linear_phase=False)
        for i in range(0, len(x), bs)
    ])
    assert np.max(np.abs(offline - naive)) > 1e-6


def test_process_block_requires_reset() -> None:
    eq = StreamingEQ(48000).add_band("peaking", 1000.0, gain_db=3.0)
    with pytest.raises(RuntimeError):
        eq.process_block(np.zeros(128))
    eq.reset(block_size=128)
    out = eq.process_block(np.zeros(128))
    assert out.shape == (128,)


# --- StreamingCompressor: the stateful/nonlinear real-time proof ---

def _dynamic_signal(seconds: float = 2.0, sample_rate: int = 48000) -> np.ndarray:
    t = np.arange(int(sample_rate * seconds)) / sample_rate
    rng = np.random.default_rng(9)
    # amplitude-modulated tone + noise so the compressor genuinely acts
    env = 0.4 + 0.6 * np.abs(np.sin(2 * np.pi * 3 * t))
    return (0.5 * np.sin(2 * np.pi * 200 * t) * env + 0.05 * rng.standard_normal(len(t))).astype(np.float64)


@pytest.mark.parametrize("block_size", [1, 64, 128, 257, 1024])
@pytest.mark.parametrize("cfg", [
    {"detection_mode": "rms"},
    {"detection_mode": "peak", "attack_ms": 1.0, "release_ms": 50.0},
    {"detection_mode": "rms", "sidechain_hpf_hz": 120.0, "makeup_gain_db": 3.0, "ratio": 6.0, "knee_db": 8.0},
])
def test_streaming_compressor_equals_offline(block_size: int, cfg: dict) -> None:
    """StreamingCompressor block processing is bit-identical to the offline
    Compressor for every mode (rms/peak/sidechain) and block size — including
    block=1 and a size that doesn't divide the signal length. This proves the
    streaming core carries sidechain/RMS/attack-release state correctly."""
    sr = 48000
    x = _dynamic_signal(sample_rate=sr)
    offline = Compressor(sample_rate=sr, **cfg).apply(x)
    streamed = StreamingCompressor(sample_rate=sr, **cfg).process_stream(x, block_size=block_size)
    assert streamed.shape == offline.shape
    assert np.max(np.abs(offline - streamed)) < 1e-9


def test_streaming_compressor_requires_reset() -> None:
    comp = StreamingCompressor(48000, threshold_db=-18.0, ratio=4.0)
    with pytest.raises(RuntimeError):
        comp.process_block(np.zeros(128))
    comp.reset(block_size=128)
    out = comp.process_block(np.zeros(128))
    assert out.shape == (128,)


# --- StreamingGate: discrete state-machine (open/closed + hold) real-time proof ---

def _gated_signal(seconds: float = 2.0, sample_rate: int = 48000) -> np.ndarray:
    t = np.arange(int(sample_rate * seconds)) / sample_rate
    rng = np.random.default_rng(4)
    # tone bursts separated by near-silence so the gate opens/closes and holds
    env = (np.sin(2 * np.pi * 0.7 * t) > 0.2).astype(float)
    return (0.4 * np.sin(2 * np.pi * 300 * t) * env + 0.003 * rng.standard_normal(len(t))).astype(np.float64)


@pytest.mark.parametrize("block_size", [1, 64, 128, 257, 1024])
@pytest.mark.parametrize("cfg", [
    {},
    {"hold_ms": 80.0, "attack_ms": 1.0, "release_ms": 200.0},
    {"sidechain_hpf_hz": 100.0, "range_db": -70.0, "threshold_db": -35.0},
])
def test_streaming_gate_equals_offline(block_size: int, cfg: dict) -> None:
    """StreamingGate is bit-identical to the offline Gate for every config and
    block size — proving the gate's boolean/hold-counter state machine carries
    correctly across block boundaries."""
    sr = 48000
    x = _gated_signal(sample_rate=sr)
    offline = Gate(sample_rate=sr, **cfg).apply(x)
    streamed = StreamingGate(sample_rate=sr, **cfg).process_stream(x, block_size=block_size)
    assert streamed.shape == offline.shape
    assert np.max(np.abs(offline - streamed)) < 1e-9


def test_streaming_gate_requires_reset() -> None:
    gate = StreamingGate(48000, threshold_db=-40.0)
    with pytest.raises(RuntimeError):
        gate.process_block(np.zeros(128))
    gate.reset(block_size=128)
    assert gate.process_block(np.zeros(128)).shape == (128,)


# --- StreamingLimiter: the look-ahead / latency-budget case ---

def _offline_limiter_gain_down(x, fs, threshold_db, ceiling_db, release_ms, lookahead_ms):
    """Reference gain envelope, mirroring dynamics.Limiter's true_peak=False path
    exactly (same maximum_filter1d window + release smoothing)."""
    input_gain = 10.0 ** (-threshold_db / 20.0)
    x_g = x * input_gain
    L = max(1, int(fs * (lookahead_ms / 1000.0)))
    abs_x = np.abs(x_g)
    padded = np.pad(abs_x, (0, L - 1), constant_values=0.0)
    peaks = maximum_filter1d(padded, size=L, origin=-(L // 2))[:len(x_g)]
    ceiling = 10.0 ** (ceiling_db / 20.0)
    target = np.ones_like(peaks)
    over = peaks > ceiling
    target[over] = ceiling / peaks[over]
    alpha_rel = math.exp(-1.0 / (fs * (release_ms / 1000.0)))
    return _smooth_attack_release(target, 0.0, alpha_rel, 1.0, attack_when_less=False)


def _spiky_signal(seconds: float = 1.5, sample_rate: int = 48000) -> np.ndarray:
    t = np.arange(int(sample_rate * seconds)) / sample_rate
    rng = np.random.default_rng(2)
    x = (0.7 * np.sin(2 * np.pi * 150 * t) + 0.5 * np.sin(2 * np.pi * 2000 * t)
         + 0.2 * rng.standard_normal(len(t)))
    x[5000:5010] += 3.0  # a nasty over-ceiling transient to force limiting
    return x.astype(np.float64)


@pytest.mark.parametrize("block_size", [32, 128, 257, 1024])
@pytest.mark.parametrize("cfg", [
    {"threshold_db": 0.0, "ceiling_db": -1.0, "release_ms": 50.0, "lookahead_ms": 5.0},
    {"threshold_db": -3.0, "ceiling_db": -0.3, "release_ms": 100.0, "lookahead_ms": 2.0},
])
def test_streaming_limiter_gain_matches_offline(block_size: int, cfg: dict) -> None:
    """The streaming limiter's per-sample gain envelope is bit-identical to the
    offline limiter's gain_down (same look-ahead peak detection + release), and
    the limited output never exceeds the ceiling."""
    sr = 48000
    x = _spiky_signal(sample_rate=sr)
    gd = _offline_limiter_gain_down(x, sr, **cfg)
    lim = StreamingLimiter(sample_rate=sr, **cfg)
    out, gain = lim.process_stream(x, block_size=block_size)
    assert out.shape == x.shape
    assert np.max(np.abs(gain - gd)) < 1e-9
    ceiling = 10.0 ** (cfg["ceiling_db"] / 20.0)
    assert np.max(np.abs(out)) <= ceiling + 1e-9


def test_streaming_limiter_declares_lookahead_latency() -> None:
    """A look-ahead limiter is NOT zero-latency; the delay must be declared."""
    sr = 48000
    lim = StreamingLimiter(sample_rate=sr, lookahead_ms=5.0).reset(block_size=128)
    assert lim.latency_samples == max(1, int(sr * 0.005)) - 1  # L - 1
    assert abs(lim.latency_samples / sr * 1000.0 - 5.0) < 0.1

"""ITU-R BS.1770-4 loudness measurement (K-weighting + gated integrated loudness).

Nothing in this codebase actually computed LUFS before this (docs/AUDIOGEN_COMPOSITION_PLAN.md,
auto-mixer work 2026-07-04) -- `composition/song_rerank_model.py` reads an "integrated_lufs"
dict key that nothing ever populates, defaulting to -18.0 always. This module is the real
analyzer: a from-scratch BS.1770 implementation.

K-weighting filter coefficients are re-derived per sample rate from the standard's analog
prototype (not hardcoded 48kHz tables), so this is correct at this project's 44100Hz:
  - Stage 1 (head effect, high shelf):  f0=1681.9744509555319 Hz, Q=0.7071752369554193, gain=+4.0 dB
  - Stage 2 (RLB weighting, high pass): f0=38.13547087613982 Hz,  Q=0.5003270373238773
These are the widely-used analog design values (same ones libebur128/pyloudnorm re-derive
from) that make the K-weighting filter sample-rate-correct instead of only valid at 48kHz.
"""
from __future__ import annotations

import numpy as np

try:
    import scipy.signal as _sp_signal  # type: ignore
except Exception:  # pragma: no cover
    _sp_signal = None

_STAGE1_F0 = 1681.9744509555319
_STAGE1_Q = 0.7071752369554193
_STAGE1_GAIN_DB = 4.0

_STAGE2_F0 = 38.13547087613982
_STAGE2_Q = 0.5003270373238773

_ABSOLUTE_GATE_LUFS = -70.0
_RELATIVE_GATE_LU = -10.0
_BLOCK_MS = 400.0
_OVERLAP = 0.75


def _rbj_highshelf_coeffs(f0: float, q: float, gain_db: float, sample_rate: int):
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * np.pi * f0 / float(sample_rate)
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = (sin_w0 / 2.0) * np.sqrt((a + 1.0 / a) * (1.0 / q - 1.0) + 2.0)
    two_sqrt_a_alpha = 2.0 * np.sqrt(a) * alpha

    b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0)
    a2 = (a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float64)
    aa = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)
    return b, aa


def _rbj_highpass_coeffs(f0: float, q: float, sample_rate: int):
    w0 = 2.0 * np.pi * f0 / float(sample_rate)
    cos_w0 = np.cos(w0)
    sin_w0 = np.sin(w0)
    alpha = sin_w0 / (2.0 * q)

    b0 = (1.0 + cos_w0) / 2.0
    b1 = -(1.0 + cos_w0)
    b2 = (1.0 + cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float64)
    aa = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float64)
    return b, aa


def k_weighting_filters(sample_rate: int):
    """Returns ((b1, a1), (b2, a2)) -- the two cascaded biquads of the K-weighting filter."""
    b1, a1 = _rbj_highshelf_coeffs(_STAGE1_F0, _STAGE1_Q, _STAGE1_GAIN_DB, sample_rate)
    b2, a2 = _rbj_highpass_coeffs(_STAGE2_F0, _STAGE2_Q, sample_rate)
    return (b1, a1), (b2, a2)


def _lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray, zi: np.ndarray | None = None):
    """Stateful biquad. Vectorized via scipy (required dependency, see requirements.txt) --
    a pure-Python per-sample loop here was measured at ~220ms per 4s bar (the same
    "100x slower pure-Python DSP" pitfall this project already hit once with numba/numpy;
    see docs/AUDIOGEN_COMPOSITION_PLAN.md). scipy.signal.lfilter is a vectorized C loop."""
    if _sp_signal is not None:
        if zi is None:
            zi = _sp_signal.lfiltic(b, a, np.zeros(max(len(b), len(a)) - 1))
        y, zf = _sp_signal.lfilter(b, a, x, zi=zi)
        return y.astype(np.float64, copy=False), zf

    if zi is None:
        zi = np.zeros(2, dtype=np.float64)
    y = np.empty_like(x, dtype=np.float64)
    z1, z2 = float(zi[0]), float(zi[1])
    b0, b1, b2 = float(b[0]), float(b[1]), float(b[2])
    a1, a2 = float(a[1]), float(a[2])
    for i in range(x.shape[0]):
        xi = float(x[i])
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y, np.array([z1, z2], dtype=np.float64)


def apply_k_weighting(mono: np.ndarray, sample_rate: int, state=None) -> tuple[np.ndarray, tuple]:
    """K-weight a mono signal. `state` (if continuing a stream) is a pair of (zi1, zi2)."""
    (b1, a1), (b2, a2) = k_weighting_filters(sample_rate)
    zi1, zi2 = state if state is not None else (None, None)
    y1, zi1_out = _lfilter(b1, a1, np.asarray(mono, dtype=np.float64), zi1)
    y2, zi2_out = _lfilter(b2, a2, y1, zi2)
    return y2.astype(np.float32), (zi1_out, zi2_out)


def _to_mono(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 2 and x.shape[1] >= 2:
        return 0.5 * (x[:, 0] + x[:, 1])
    return x.reshape(-1)


def _channel_mean_square_blocks(audio: np.ndarray, sample_rate: int, block_ms: float, overlap: float):
    """K-weighted mean-square per block, per BS.1770 (mono/stereo-summed here; this project
    doesn't need multichannel surround weighting)."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    n_channels = x.shape[1]
    block_len = max(1, int(round(sample_rate * block_ms / 1000.0)))
    hop = max(1, int(round(block_len * (1.0 - overlap))))
    n = x.shape[0]
    if n < block_len:
        return np.zeros(0, dtype=np.float64)

    weighted = np.empty_like(x, dtype=np.float64)
    for c in range(n_channels):
        weighted[:, c], _ = apply_k_weighting(x[:, c], sample_rate)

    n_blocks = 1 + (n - block_len) // hop
    ms_per_block = np.empty(n_blocks, dtype=np.float64)
    for i in range(n_blocks):
        start = i * hop
        seg = weighted[start:start + block_len, :]
        # Sum of per-channel mean-square (BS.1770 channel weighting G_i == 1.0 for L/R).
        ms_per_block[i] = float(np.mean(np.sum(seg * seg, axis=1)))
    return ms_per_block


def _ms_to_lufs(mean_square: float) -> float:
    if mean_square <= 1e-15:
        return -np.inf
    return -0.691 + 10.0 * np.log10(mean_square)


def integrated_lufs(audio: np.ndarray, sample_rate: int) -> float:
    """Full ITU-R BS.1770-4 gated integrated loudness, in LUFS.

    Two-stage gating: blocks below an absolute threshold of -70 LUFS are discarded, then
    blocks more than 10 LU below the mean of the surviving blocks are discarded too, and
    the integrated loudness is the mean-square average of what's left.
    """
    ms_blocks = _channel_mean_square_blocks(audio, sample_rate, _BLOCK_MS, _OVERLAP)
    if ms_blocks.size == 0:
        return -np.inf

    absolute_mask = ms_blocks > (10.0 ** ((_ABSOLUTE_GATE_LUFS + 0.691) / 10.0))
    if not np.any(absolute_mask):
        return -np.inf
    gated = ms_blocks[absolute_mask]

    ungated_mean_lufs = _ms_to_lufs(float(np.mean(gated)))
    relative_threshold_lufs = ungated_mean_lufs + _RELATIVE_GATE_LU
    relative_mask = gated > (10.0 ** ((relative_threshold_lufs + 0.691) / 10.0))
    if not np.any(relative_mask):
        return ungated_mean_lufs
    final = gated[relative_mask]
    return _ms_to_lufs(float(np.mean(final)))


class RollingKWeightedLoudness:
    """Realtime-tractable running loudness estimate for continuous generative playback.

    True BS.1770 *integrated* loudness needs a whole finished program (gating requires the
    complete block history) -- meaningless for endless generative playback that never ends.
    This instead keeps a persistent K-weighting filter state across calls (click-free at
    block/bar boundaries) and an EMA of the K-weighted mean-square, which approximates
    "momentary loudness" the way a live broadcast loudness meter would report it continuously.
    """

    def __init__(self, sample_rate: int, ema_alpha: float = 0.25):
        self.sample_rate = int(sample_rate)
        self.ema_alpha = float(np.clip(ema_alpha, 0.01, 0.95))
        self._state_l: tuple | None = None
        self._state_r: tuple | None = None
        self._ema_ms: float = 0.0
        self._warm = False

    def reset(self) -> None:
        self._state_l = None
        self._state_r = None
        self._ema_ms = 0.0
        self._warm = False

    def process(self, audio_stereo: np.ndarray) -> float:
        """Feed one block of stereo audio, return the updated running loudness in LUFS."""
        x = np.asarray(audio_stereo, dtype=np.float64)
        if x.ndim == 1:
            x = np.stack([x, x], axis=1)
        left, self._state_l = apply_k_weighting(x[:, 0], self.sample_rate, self._state_l)
        right, self._state_r = apply_k_weighting(x[:, 1], self.sample_rate, self._state_r)
        block_ms = float(np.mean(left.astype(np.float64) ** 2 + right.astype(np.float64) ** 2))
        if not self._warm:
            self._ema_ms = block_ms
            self._warm = True
        else:
            self._ema_ms = (1.0 - self.ema_alpha) * self._ema_ms + self.ema_alpha * block_ms
        return _ms_to_lufs(self._ema_ms)

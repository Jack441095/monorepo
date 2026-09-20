"""Streaming (block-based, state-carrying) DSP core — the real-time seed.

WHY THIS EXISTS
---------------
Everything else in ``dsp_engine`` is *offline*: it takes a whole signal and
returns a whole signal (``sosfilt``/``lfilter`` over the full array). That is
correct for rendering files, but it is the wrong shape for a real-time audio
callback — the world of game-audio middleware (Wwise/FMOD), live monitoring,
and low-latency plugins — where audio arrives in small fixed-size blocks and
each block must be processed as it comes, carrying filter state across block
boundaries, with no dependence on future samples.

This module expresses a processor in that real-time shape without leaving
Python, so the discipline can be proven and *measured* before anyone commits to
a C/C++ middleware plugin:

  * ``reset(sample_rate, block_size)`` — compile coefficients, clear state.
  * ``process_block(x) -> y`` — process one block, carrying state forward.

The correctness guarantee is exact, not approximate: ``scipy.signal.sosfilt``
with carried ``zi`` state produces output **bit-identical** to a single
whole-signal ``sosfilt`` call. So a streamed render equals the offline render —
that equality is the proof the streaming core is right (see
``scripts/eval/streaming_dsp_budget.py`` and ``tests/audio_analysis/
test_streaming_dsp.py``).

It reuses :class:`~audio_analysis.dsp_engine.eq.ParametricEQ` for the RBJ
coefficient math — it does not re-derive it. Only the causal (minimum-phase)
path can stream; zero-phase ``filtfilt`` is inherently non-causal and therefore
offline-only.
"""

from __future__ import annotations

import math
from collections import deque

from audio_analysis.dsp_engine.eq import ParametricEQ
from audio_analysis.dsp_engine.dynamics import _smooth_attack_release

try:
    import numpy as np
    import scipy.signal as sig
    NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover - matches eq.py's own guard
    NUMPY_AVAILABLE = False

# Optional JIT for the gate's per-sample state-machine loop, mirroring the
# offline dynamics.py pattern. Deliberately a *separate* kernel from
# dynamics._gate_envelope (which is untouched — its header warns it feeds
# render-path LUFS/true-peak to the millidecibel): this one carries the gate's
# (open, hold_counter, gain) state across blocks and returns it, which the
# offline kernel's interface can't. Bit-exactness vs offline Gate is asserted in
# the tests, so the duplicated recurrence cannot silently drift.
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None


def _gate_step_py(level_db, threshold, alpha_att, alpha_rel, hold_samples,
                  target_open, target_closed, gate_open, hold_counter, current_gain):
    n = level_db.shape[0]
    g_out = np.empty(n, dtype=np.float64)
    for i in range(n):
        level = level_db[i]
        if level > threshold:
            gate_open = True
            hold_counter = hold_samples
        else:
            if hold_counter > 0:
                hold_counter -= 1
            else:
                gate_open = False
        target = target_open if gate_open else target_closed
        if target > current_gain:
            current_gain = alpha_att * current_gain + (1.0 - alpha_att) * target
        else:
            current_gain = alpha_rel * current_gain + (1.0 - alpha_rel) * target
        g_out[i] = current_gain
    return g_out, gate_open, hold_counter, current_gain


if _nb is not None:  # pragma: no cover
    _gate_step = _nb.njit(cache=True)(_gate_step_py)
else:  # pragma: no cover
    _gate_step = _gate_step_py


class StreamingEQ:
    """A parametric EQ in real-time, block-based form.

    Same bands and coefficients as :class:`ParametricEQ`, but processed one
    fixed-size block at a time with filter state carried across calls, so it can
    run inside an audio callback. Streamed output equals the offline
    ``ParametricEQ.apply(...)`` (causal mode) to floating-point exactness.
    """

    def __init__(self, sample_rate: int = 48000):
        if not NUMPY_AVAILABLE:
            raise RuntimeError("StreamingEQ requires numpy/scipy.")
        self._eq = ParametricEQ(sample_rate)
        self._sos: np.ndarray | None = None
        self._zi: np.ndarray | None = None
        self.block_size: int | None = None

    @property
    def sample_rate(self) -> int:
        return self._eq.sample_rate

    def add_band(self, type: str, frequency: float, gain_db: float = 0.0, q: float = 0.707) -> "StreamingEQ":
        """Add a band (delegates to ParametricEQ). Invalidates compiled state —
        call :meth:`reset` before streaming."""
        self._eq.add_band(type, frequency, gain_db, q)
        self._sos = None
        self._zi = None
        return self

    def reset(self, sample_rate: int | None = None, block_size: int | None = None) -> "StreamingEQ":
        """Compile the cascaded biquads and clear filter state to rest.

        Must be called before :meth:`process_block`. After ``reset`` the steady
        state is zero, exactly as an offline ``sosfilt(sos, x)`` call assumes, so
        the first streamed block lines up with the offline render."""
        if sample_rate is not None:
            self._eq.sample_rate = sample_rate
        self.block_size = block_size
        self._sos = self._eq.get_sos(linear_phase=False)
        # One [z1, z2] state pair per second-order section, all at rest.
        self._zi = np.zeros((self._sos.shape[0], 2), dtype=np.float64)
        return self

    def process_block(self, x) -> np.ndarray:
        """Process one block of samples, carrying filter state to the next call.

        After ``reset`` this allocates only the output block (plus scipy's
        internal work) — no coefficient recompute, no per-sample Python loop."""
        if self._sos is None or self._zi is None:
            raise RuntimeError("Call reset() before process_block().")
        block = np.asarray(x, dtype=np.float64)
        if block.size == 0:
            return block
        y, self._zi = sig.sosfilt(self._sos, block, zi=self._zi)
        return y

    def process_stream(self, samples, block_size: int) -> np.ndarray:
        """Convenience: run a whole signal through in fixed-size blocks and
        concatenate — i.e. simulate the real-time callback offline. Equals
        ``ParametricEQ.apply(samples)`` (causal) to floating-point exactness."""
        self.reset(block_size=block_size)
        data = np.asarray(samples, dtype=np.float64)
        out = np.empty_like(data)
        for start in range(0, len(data), block_size):
            end = start + block_size
            out[start:end] = self.process_block(data[start:end])
        return out


class StreamingCompressor:
    """A feed-forward compressor in real-time, block-based form.

    Mirrors :class:`~audio_analysis.dsp_engine.dynamics.Compressor` exactly, but
    processes fixed-size blocks carrying every piece of state across calls: the
    sidechain high-pass filter state, the RMS one-pole detector state, and the
    attack/release envelope state. Because the offline compressor is fully
    causal (no look-ahead), the streamed render equals ``Compressor.apply(...)``
    to floating-point exactness — proving the streaming core generalises from a
    linear filter (EQ) to a stateful, nonlinear dynamics processor, which is the
    harder and more representative real-time case.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_ms: float = 10.0,
        release_ms: float = 100.0,
        knee_db: float = 5.0,
        makeup_gain_db: float = 0.0,
        detection_mode: str = "rms",
        sidechain_hpf_hz: float | None = None,
    ):
        if not NUMPY_AVAILABLE:
            raise RuntimeError("StreamingCompressor requires numpy/scipy.")
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.ratio = ratio
        self.attack_ms = attack_ms
        self.release_ms = release_ms
        self.knee_db = knee_db
        self.makeup_gain_db = makeup_gain_db
        self.detection_mode = detection_mode.lower()
        self.sidechain_hpf_hz = sidechain_hpf_hz
        self.block_size: int | None = None
        self._compiled = False

    def reset(self, sample_rate: int | None = None, block_size: int | None = None) -> "StreamingCompressor":
        """Compile fs-dependent coefficients and clear all detector/envelope
        state to rest, matching a fresh offline ``Compressor.apply`` call."""
        if sample_rate is not None:
            self.sample_rate = sample_rate
        self.block_size = block_size
        fs = float(self.sample_rate)

        # Sidechain high-pass (same design as Compressor.apply), state at rest.
        self._sc_sos = None
        self._sc_zi = None
        if self.sidechain_hpf_hz is not None and self.sidechain_hpf_hz > 0:
            nyquist = fs / 2.0
            cutoff = min(self.sidechain_hpf_hz, nyquist * 0.99)
            self._sc_sos = sig.butter(2, cutoff / nyquist, btype="highpass", output="sos")
            self._sc_zi = np.zeros((self._sc_sos.shape[0], 2), dtype=np.float64)

        # RMS one-pole detector coefficients + rest state (lfilter zero state).
        tau_rms = 0.010
        self._alpha_rms = math.exp(-1.0 / (fs * tau_rms))
        self._rms_b = np.array([1.0 - self._alpha_rms])
        self._rms_a = np.array([1.0, -self._alpha_rms])
        self._rms_zi = np.zeros(1, dtype=np.float64)

        # Attack/release envelope coefficients + state (offline init is 0.0 dB).
        self._alpha_att = math.exp(-1.0 / (fs * (self.attack_ms / 1000.0)))
        self._alpha_rel = math.exp(-1.0 / (fs * (self.release_ms / 1000.0)))
        self._smooth_state = 0.0
        self._compiled = True
        return self

    def process_block(self, x) -> np.ndarray:
        """Process one block, carrying sidechain/RMS/envelope state forward.
        Byte-for-byte equal to the matching slice of ``Compressor.apply`` over
        the whole signal."""
        if not self._compiled:
            raise RuntimeError("Call reset() before process_block().")
        block = np.asarray(x, dtype=np.float64)
        if block.size == 0:
            return block

        # 1. Sidechain signal
        sc_sig = block.copy()
        if self._sc_sos is not None:
            sc_sig, self._sc_zi = sig.sosfilt(self._sc_sos, sc_sig, zi=self._sc_zi)

        # 2. Level detection
        if self.detection_mode == "rms":
            squared = sc_sig * sc_sig
            ms, self._rms_zi = sig.lfilter(self._rms_b, self._rms_a, squared, zi=self._rms_zi)
            level = np.sqrt(np.maximum(ms, 1e-12))
        else:
            level = np.abs(sc_sig)
        level_db = 20.0 * np.log10(np.maximum(level, 1e-12))

        # 3. Static gain curve with soft knee (pointwise; matches Compressor)
        t = self.threshold_db
        w = max(0.1, self.knee_db)
        r = self.ratio
        y_db = level_db.copy()
        below_knee = level_db < (t - w / 2.0)
        above_knee = level_db > (t + w / 2.0)
        in_knee = ~(below_knee | above_knee)
        if np.any(in_knee):
            diff = level_db[in_knee] - t + w / 2.0
            y_db[in_knee] = level_db[in_knee] + ((1.0 / r - 1.0) * (diff ** 2)) / (2.0 * w)
        if np.any(above_knee):
            y_db[above_knee] = t + (level_db[above_knee] - t) / r
        gr_db = y_db - level_db

        # 4. Attack/release smoothing, carrying the envelope state across blocks
        smoothed_gr_db = _smooth_attack_release(
            gr_db, self._alpha_att, self._alpha_rel, self._smooth_state, attack_when_less=True
        )
        self._smooth_state = float(smoothed_gr_db[-1])

        # 5. Apply gain + makeup
        total_gain_db = smoothed_gr_db + self.makeup_gain_db
        linear_gain = 10.0 ** (total_gain_db / 20.0)
        return block * linear_gain

    def process_stream(self, samples, block_size: int) -> np.ndarray:
        """Run a whole signal in fixed-size blocks; equals
        ``Compressor.apply(samples)`` to floating-point exactness."""
        self.reset(block_size=block_size)
        data = np.asarray(samples, dtype=np.float64)
        out = np.empty_like(data)
        for start in range(0, len(data), block_size):
            end = start + block_size
            out[start:end] = self.process_block(data[start:end])
        return out


class StreamingGate:
    """A noise gate in real-time, block-based form.

    Mirrors :class:`~audio_analysis.dsp_engine.dynamics.Gate` exactly, carrying
    the sidechain-HPF state plus the gate's discrete state machine
    (open/closed, hold counter) and the smoothed gain across blocks. The offline
    gate is fully causal, so the streamed render is bit-identical to
    ``Gate.apply(...)``. This is a meaningfully different streaming case from the
    EQ/compressor: the carried state includes a boolean and an integer counter,
    not just filter memory."""

    def __init__(
        self,
        sample_rate: int = 48000,
        threshold_db: float = -40.0,
        attack_ms: float = 2.0,
        hold_ms: float = 50.0,
        release_ms: float = 150.0,
        range_db: float = -60.0,
        sidechain_hpf_hz: float | None = None,
    ):
        if not NUMPY_AVAILABLE:
            raise RuntimeError("StreamingGate requires numpy/scipy.")
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.attack_ms = attack_ms
        self.hold_ms = hold_ms
        self.release_ms = release_ms
        self.range_db = range_db
        self.sidechain_hpf_hz = sidechain_hpf_hz
        self.block_size: int | None = None
        self._compiled = False

    def reset(self, sample_rate: int | None = None, block_size: int | None = None) -> "StreamingGate":
        if sample_rate is not None:
            self.sample_rate = sample_rate
        self.block_size = block_size
        fs = float(self.sample_rate)

        self._sc_sos = None
        self._sc_zi = None
        if self.sidechain_hpf_hz is not None and self.sidechain_hpf_hz > 0:
            nyquist = fs / 2.0
            cutoff = min(self.sidechain_hpf_hz, nyquist * 0.99)
            self._sc_sos = sig.butter(2, cutoff / nyquist, btype="highpass", output="sos")
            self._sc_zi = np.zeros((self._sc_sos.shape[0], 2), dtype=np.float64)

        self._target_open = 1.0
        self._target_closed = 10.0 ** (self.range_db / 20.0)
        self._alpha_att = math.exp(-1.0 / (fs * (self.attack_ms / 1000.0)))
        self._alpha_rel = math.exp(-1.0 / (fs * (self.release_ms / 1000.0)))
        self._hold_samples = int(fs * (self.hold_ms / 1000.0))

        # Gate state at rest, matching a fresh offline Gate.apply call.
        self._gate_open = False
        self._hold_counter = 0
        self._current_gain = self._target_closed
        self._compiled = True
        return self

    def process_block(self, x) -> np.ndarray:
        if not self._compiled:
            raise RuntimeError("Call reset() before process_block().")
        block = np.asarray(x, dtype=np.float64)
        if block.size == 0:
            return block

        sc_sig = block.copy()
        if self._sc_sos is not None:
            sc_sig, self._sc_zi = sig.sosfilt(self._sc_sos, sc_sig, zi=self._sc_zi)
        level_db = 20.0 * np.log10(np.maximum(np.abs(sc_sig), 1e-12))

        g_out, self._gate_open, self._hold_counter, self._current_gain = _gate_step(
            level_db, self.threshold_db, self._alpha_att, self._alpha_rel,
            self._hold_samples, self._target_open, self._target_closed,
            self._gate_open, self._hold_counter, self._current_gain,
        )
        return block * g_out

    def process_stream(self, samples, block_size: int) -> np.ndarray:
        """Run a whole signal in fixed-size blocks; equals ``Gate.apply(samples)``
        to floating-point exactness."""
        self.reset(block_size=block_size)
        data = np.asarray(samples, dtype=np.float64)
        out = np.empty_like(data)
        for start in range(0, len(data), block_size):
            end = start + block_size
            out[start:end] = self.process_block(data[start:end])
        return out


class StreamingLimiter:
    """A look-ahead brickwall limiter in real-time, block-based form — the
    honest hard case, because it is NOT zero-latency.

    A limiter must see a few milliseconds *ahead* to clamp a peak before it
    happens (offline: ``peaks[i] = max(|x|[i : i+L])``). In a real-time
    callback you cannot see the future, so a streaming limiter must **delay its
    output** by the look-ahead length. That delay is a real cost that has to be
    declared and budgeted — it is exposed here as :attr:`latency_samples`. This
    is the design point: EQ/compressor/gate stream at zero added latency;
    the limiter cannot, and pretending otherwise would be wrong.

    Implementation: the forward-window peak is tracked with a monotonic deque
    (O(1) amortised sliding-window maximum), the release envelope is the same
    instant-attack / smoothed-release one-pole as the offline
    :class:`~audio_analysis.dsp_engine.dynamics.Limiter`, and :meth:`flush`
    zero-pads the tail exactly as the offline zero-pads its max filter. The
    per-sample **gain envelope** produced by streaming is therefore bit-identical
    to the offline limiter's ``gain_down`` (asserted in the tests); the streamed
    output is that gain applied to the input, delayed by ``latency_samples``.

    Scope: ``true_peak=False`` (base-rate detection). True-peak limiting
    oversamples 4× with a polyphase filter whose state would also have to be
    carried block-to-block — a worthwhile but separate extension, deliberately
    not faked here.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        threshold_db: float = 0.0,
        ceiling_db: float = -1.0,
        release_ms: float = 50.0,
        lookahead_ms: float = 5.0,
    ):
        if not NUMPY_AVAILABLE:
            raise RuntimeError("StreamingLimiter requires numpy/scipy.")
        self.sample_rate = sample_rate
        self.threshold_db = threshold_db
        self.ceiling_db = ceiling_db
        self.release_ms = release_ms
        self.lookahead_ms = lookahead_ms
        self.block_size: int | None = None
        self.latency_samples = 0
        self._compiled = False

    def reset(self, sample_rate: int | None = None, block_size: int | None = None) -> "StreamingLimiter":
        if sample_rate is not None:
            self.sample_rate = sample_rate
        self.block_size = block_size
        fs = float(self.sample_rate)

        self.input_gain = 10.0 ** (-self.threshold_db / 20.0)
        self.ceiling_linear = 10.0 ** (self.ceiling_db / 20.0)
        self._L = max(1, int(fs * (self.lookahead_ms / 1000.0)))
        # gain[i] needs |x| up to index i+L-1, so the minimum causal latency is L-1.
        self.latency_samples = self._L - 1
        self._alpha_rel = math.exp(-1.0 / (fs * (self.release_ms / 1000.0)))

        self._mono: deque = deque()        # monotonic-decreasing (index, |x_g|) for window max
        self._pending: deque = deque()     # (index, x_g) awaiting gain application
        self._release_state = 1.0
        self._n_in = 0                     # count of real input samples fed
        self._compiled = True
        return self

    def _finalize(self, i: int, out: list) -> None:
        """Finalize gain for input index i (its full look-ahead window is in)."""
        while self._mono[0][0] < i:        # evict entries left of the window
            self._mono.popleft()
        window_max = self._mono[0][1]
        target = self.ceiling_linear / window_max if window_max > self.ceiling_linear else 1.0
        if target <= self._release_state:  # instant attack (offline alpha_att = 0)
            self._release_state = target
        else:                              # smoothed release
            self._release_state = self._alpha_rel * self._release_state + (1.0 - self._alpha_rel) * target
        _, x_g = self._pending.popleft()
        out.append(x_g * self._release_state)

    def _feed_sample(self, sample: float, is_pad: bool, out: list) -> None:
        j = self._n_in
        if is_pad:
            a = 0.0                         # tail zero-pad: extends windows, no real audio
        else:
            x_g = sample * self.input_gain
            a = abs(x_g)
            self._pending.append((j, x_g))
        while self._mono and self._mono[-1][1] <= a:
            self._mono.pop()
        self._mono.append((j, a))
        self._n_in += 1
        if j >= self._L - 1:                # window [i, i+L-1] complete for i = j-(L-1)
            self._finalize(j - (self._L - 1), out)

    def process_block(self, x) -> np.ndarray:
        """Feed one block; return the limited output samples that became ready
        this call. Due to the look-ahead delay the first ``latency_samples`` of
        output arrive over subsequent calls — that delay is :attr:`latency_samples`.
        Call :meth:`flush` at end-of-stream to drain the tail."""
        if not self._compiled:
            raise RuntimeError("Call reset() before process_block().")
        block = np.asarray(x, dtype=np.float64)
        out: list = []
        for s in block:
            self._feed_sample(float(s), False, out)
        return np.asarray(out, dtype=np.float64)

    def flush(self) -> np.ndarray:
        """Drain the look-ahead buffer at end-of-stream (zero-pads the final
        window, matching the offline max-filter's zero padding)."""
        out: list = []
        for _ in range(self._L - 1):
            self._feed_sample(0.0, True, out)
        return np.asarray(out, dtype=np.float64)

    def process_stream(self, samples, block_size: int):
        """Run a whole signal in fixed-size blocks and drain. Returns
        ``(output, gain)`` where ``gain`` is the per-input-sample limiter gain
        (bit-identical to the offline limiter's ``gain_down``) and ``output`` is
        ``x_g * gain`` — i.e. the limited signal on the input timeline (the
        real-time stream would emit this same sequence delayed by
        ``latency_samples``)."""
        self.reset(block_size=block_size)
        data = np.asarray(samples, dtype=np.float64)
        pieces = [self.process_block(data[i:i + block_size])
                  for i in range(0, len(data), block_size)]
        pieces.append(self.flush())
        output = np.concatenate(pieces) if pieces else np.zeros(0)
        # gain = output / x_g, recovered where x_g != 0; but return gain directly
        # is cleaner — recompute from output and input for the caller's assert.
        x_g = data * self.input_gain
        gain = np.ones_like(output)
        nz = x_g != 0.0
        gain[nz] = output[nz] / x_g[nz]
        return output, gain

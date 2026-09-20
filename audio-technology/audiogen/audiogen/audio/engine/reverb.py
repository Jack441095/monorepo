# audio/engine/reverb.py
# Project module `reverb` (audio).

import numpy as np

import os

# Numba accelerates the per-sample comb/allpass loops (~70% of RT master time).
# Disable with LLM_AUDIOGEN_DISABLE_NUMBA_REVERB=1 if import/JIT causes issues.
NUMBA_AVAILABLE = False
_disable_nb = os.environ.get("LLM_AUDIOGEN_DISABLE_NUMBA_REVERB", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
if not _disable_nb:
    try:
        from numba import njit  # type: ignore
        NUMBA_AVAILABLE = True
    except Exception:
        NUMBA_AVAILABLE = False


if NUMBA_AVAILABLE:
    @njit(cache=True)
    def _apply_predelay_nb(signal, predelay_buffers, predelay_indices, delay_samples):
        if delay_samples <= 0:
            return signal
        y = np.zeros_like(signal)
        ch_count = signal.shape[1]
        if ch_count > 2:
            ch_count = 2
        for ch in range(ch_count):
            buf = predelay_buffers[ch]
            idx = predelay_indices[ch]
            for i in range(signal.shape[0]):
                y[i, ch] = buf[idx]
                buf[idx] = signal[i, ch]
                idx += 1
                if idx >= delay_samples:
                    idx = 0
            predelay_indices[ch] = idx
        return y


    @njit(cache=True)
    def _process_early_reflections_nb(signal, er_buffers, er_indices, tap_delays, tap_gains):
        y = np.zeros_like(signal)
        ch_count = signal.shape[1]
        if ch_count > 2:
            ch_count = 2
        size = er_buffers.shape[1]
        for ch in range(ch_count):
            buf = er_buffers[ch]
            idx = er_indices[ch]
            delays = tap_delays[ch]
            gains = tap_gains[ch]
            for i in range(signal.shape[0]):
                buf[idx] = signal[i, ch]
                acc = 0.0
                for t in range(delays.shape[0]):
                    ridx = idx - delays[t]
                    while ridx < 0:
                        ridx += size
                    acc += gains[t] * buf[ridx]
                y[i, ch] = acc
                idx += 1
                if idx >= size:
                    idx = 0
            er_indices[ch] = idx
        return y


    @njit(cache=True)
    def _return_highpass_nb(signal, alpha, stages, prev_x, prev_y):
        y = np.empty_like(signal)
        ch_count = signal.shape[1]
        if ch_count > 2:
            ch_count = 2
        for ch in range(ch_count):
            for i in range(signal.shape[0]):
                sample = signal[i, ch]
                for stage in range(stages):
                    px = prev_x[ch, stage]
                    py = prev_y[ch, stage]
                    out = alpha * (py + sample - px)
                    prev_x[ch, stage] = sample
                    prev_y[ch, stage] = out
                    sample = out
                y[i, ch] = sample
        for ch in range(ch_count, signal.shape[1]):
            for i in range(signal.shape[0]):
                y[i, ch] = signal[i, ch]
        return y


    @njit(cache=True)
    def _return_lowpass_nb(signal, alpha, stages, prev_y):
        y = np.empty_like(signal)
        ch_count = signal.shape[1]
        if ch_count > 2:
            ch_count = 2
        for ch in range(ch_count):
            for i in range(signal.shape[0]):
                sample = signal[i, ch]
                for stage in range(stages):
                    py = prev_y[ch, stage]
                    out = py + alpha * (sample - py)
                    prev_y[ch, stage] = out
                    sample = out
                y[i, ch] = sample
        for ch in range(ch_count, signal.shape[1]):
            for i in range(signal.shape[0]):
                y[i, ch] = signal[i, ch]
        return y


    @njit(cache=True)
    def _process_comb_bank(
        signal,
        comb_buffers,
        comb_delays,
        comb_indices,
        comb_lp_states,
        comb_gains,
        lp_alpha,
        active_count,
    ):
        comb_out = np.zeros_like(signal)
        limit = active_count
        if limit > comb_buffers.shape[0]:
            limit = comb_buffers.shape[0]
        for i in range(limit):
            buf = comb_buffers[i]
            idx = comb_indices[i]
            lp_state = comb_lp_states[i]
            delay = comb_delays[i]
            comb_gain = comb_gains[i]
            for n in range(signal.shape[0]):
                delayed = buf[idx]
                feedback = delayed * comb_gain
                lp_state = lp_alpha * lp_state + (1.0 - lp_alpha) * feedback
                buf[idx] = signal[n] + lp_state
                comb_out[n] += delayed
                idx += 1
                if idx >= delay:
                    idx = 0
            comb_indices[i] = idx
            comb_lp_states[i] = lp_state
        return comb_out


    @njit(cache=True)
    def _process_allpass_chain(
        signal,
        ap_x_bufs,
        ap_y_bufs,
        allpass_delays,
        ap_x_indices,
        ap_y_indices,
        ap_gain,
        active_count,
    ):
        ap_out = signal.copy()
        limit = active_count
        if limit > ap_x_bufs.shape[0]:
            limit = ap_x_bufs.shape[0]
        for i in range(limit):
            x_buf = ap_x_bufs[i]
            y_buf = ap_y_bufs[i]
            x_idx = ap_x_indices[i]
            y_idx = ap_y_indices[i]
            delay = allpass_delays[i]
            out = np.zeros_like(ap_out)
            for n in range(ap_out.shape[0]):
                x_delayed = x_buf[x_idx]
                y_delayed = y_buf[y_idx]
                y = -ap_gain * ap_out[n] + x_delayed + ap_gain * y_delayed
                out[n] = y
                x_buf[x_idx] = ap_out[n]
                y_buf[y_idx] = y
                x_idx += 1
                y_idx += 1
                if x_idx >= delay:
                    x_idx = 0
                if y_idx >= delay:
                    y_idx = 0
            ap_out = out
            ap_x_indices[i] = x_idx
            ap_y_indices[i] = y_idx
        return ap_out
else:
    _apply_predelay_nb = None
    _process_early_reflections_nb = None
    _return_highpass_nb = None
    _return_lowpass_nb = None

    def _process_comb_bank(
        signal,
        comb_buffers,
        comb_delays,
        comb_indices,
        comb_lp_states,
        comb_gains,
        lp_alpha,
        active_count,
    ):
        comb_out = np.zeros_like(signal)
        limit = int(max(1, min(int(active_count), comb_buffers.shape[0])))
        for i in range(limit):
            buf = comb_buffers[i]
            idx = int(comb_indices[i])
            lp_state = float(comb_lp_states[i])
            delay = int(comb_delays[i])
            comb_gain = float(comb_gains[i])
            for n in range(signal.shape[0]):
                delayed = buf[idx]
                feedback = delayed * comb_gain
                lp_state = lp_alpha * lp_state + (1.0 - lp_alpha) * feedback
                buf[idx] = signal[n] + lp_state
                comb_out[n] += delayed
                idx = (idx + 1) % delay
            comb_indices[i] = idx
            comb_lp_states[i] = lp_state
        return comb_out


    def _process_allpass_chain(
        signal,
        ap_x_bufs,
        ap_y_bufs,
        allpass_delays,
        ap_x_indices,
        ap_y_indices,
        ap_gain,
        active_count,
    ):
        ap_out = signal.copy()
        limit = int(max(0, min(int(active_count), ap_x_bufs.shape[0])))
        for i in range(limit):
            x_buf = ap_x_bufs[i]
            y_buf = ap_y_bufs[i]
            x_idx = int(ap_x_indices[i])
            y_idx = int(ap_y_indices[i])
            delay = int(allpass_delays[i])
            out = np.zeros_like(ap_out)
            for n in range(ap_out.shape[0]):
                x_delayed = x_buf[x_idx]
                y_delayed = y_buf[y_idx]
                y = -ap_gain * ap_out[n] + x_delayed + ap_gain * y_delayed
                out[n] = y
                x_buf[x_idx] = ap_out[n]
                y_buf[y_idx] = y
                x_idx = (x_idx + 1) % delay
                y_idx = (y_idx + 1) % delay
            ap_out = out
            ap_x_indices[i] = x_idx
            ap_y_indices[i] = y_idx
        return ap_out


class RoomReverb:
    """Global send-return Schroeder/Freeverb-style reverb.

    RT60 is the time in seconds for the reverb to decay by 60 dB.
    Damping controls high-frequency absorption (0 = bright, 1 = dark).
    A 12 dB/oct high-pass on the return input keeps the long tail out of the
    low-mid/bass range so the reverb glues the mix without washing it out.
    """

    def __init__(
        self,
        sample_rate: int = 44100,
        rt60: float = 10.0,
        damping: float = 0.62,
        wet: float = 0.24,
        highpass_hz: float = 500.0,
        highpass_slope_db_per_oct: float = 12.0,
        stereo_spread_samples: int = 23,
        predelay_ms: float = 28.0,
        early_reflections_enabled: bool = True,
        early_reflections_level: float = 0.24,
        return_lowpass_hz: float = 9500.0,
        return_lowpass_slope_db_per_oct: float = 12.0,
    ):
        self.sample_rate = sample_rate
        self.rt60 = rt60
        self.damping = damping
        self.wet = wet
        self.highpass_hz = float(highpass_hz)
        self.highpass_slope_db_per_oct = float(highpass_slope_db_per_oct)
        self.stereo_spread_samples = int(max(1, stereo_spread_samples))
        self.predelay_ms = float(predelay_ms)
        self.early_reflections_enabled = bool(early_reflections_enabled)
        self.early_reflections_level = float(np.clip(early_reflections_level, 0.0, 1.0))
        self._predelay_max_ms = 250.0
        self.return_lowpass_hz = float(return_lowpass_hz)
        self.return_lowpass_slope_db_per_oct = float(return_lowpass_slope_db_per_oct)

        # Delay times in samples (Freeverb-like baseline with expanded diffusion).
        # Left/right are slightly decorrelated to widen the stereo tail naturally.
        self._comb_delay_secs = [
            0.0253,
            0.0269,
            0.0289,
            0.0307,
            0.0322,
            0.0336,
            0.0353,
            0.0367,
        ]
        self._allpass_delay_secs = [
            0.0017,
            0.0031,
            0.0050,
            0.0067,
        ]
        spread_s = float(self.stereo_spread_samples) / float(max(1, int(sample_rate)))
        self._comb_delays_arr = np.stack(
            [
                np.asarray([max(3, int(round(s * sample_rate))) for s in self._comb_delay_secs], dtype=np.int32),
                np.asarray([max(3, int(round((s + spread_s) * sample_rate))) for s in self._comb_delay_secs], dtype=np.int32),
            ],
            axis=0,
        )
        self._allpass_delays_arr = np.stack(
            [
                np.asarray([max(2, int(round(s * sample_rate))) for s in self._allpass_delay_secs], dtype=np.int32),
                np.asarray(
                    [max(2, int(round((s + 0.5 * spread_s) * sample_rate))) for s in self._allpass_delay_secs],
                    dtype=np.int32,
                ),
            ],
            axis=0,
        )

        # Independent left/right buffers preserve stereo information in the wet path.
        max_comb = int(np.max(self._comb_delays_arr))
        max_allpass = int(np.max(self._allpass_delays_arr))
        self.comb_buffers = np.zeros((2, self._comb_delays_arr.shape[1], max_comb), dtype=np.float32)
        self.comb_indices = np.zeros((2, self._comb_delays_arr.shape[1]), dtype=np.int32)
        self.comb_lp_states = np.zeros((2, self._comb_delays_arr.shape[1]), dtype=np.float32)
        self.ap_x_bufs = np.zeros((2, self._allpass_delays_arr.shape[1], max_allpass), dtype=np.float32)
        self.ap_y_bufs = np.zeros((2, self._allpass_delays_arr.shape[1], max_allpass), dtype=np.float32)
        self.ap_x_indices = np.zeros((2, self._allpass_delays_arr.shape[1]), dtype=np.int32)
        self.ap_y_indices = np.zeros((2, self._allpass_delays_arr.shape[1]), dtype=np.int32)
        # Pre-delay line.
        self._predelay_delay_samples = 0
        max_predelay_samples = int(max(1, round((self._predelay_max_ms / 1000.0) * self.sample_rate)))
        self._predelay_buffers = np.zeros((2, max_predelay_samples + 2), dtype=np.float32)
        self._predelay_indices = np.zeros(2, dtype=np.int32)
        # Early reflections (short tap network, decorrelated per side).
        self._er_tap_secs_l = [0.0073, 0.0111, 0.0137, 0.0179, 0.0243, 0.0311]
        self._er_tap_gains_l = np.asarray([0.62, 0.50, 0.41, 0.33, 0.27, 0.22], dtype=np.float32)
        self._er_tap_delays_arr = np.zeros((2, len(self._er_tap_secs_l)), dtype=np.int32)
        self._er_tap_gains_arr = np.zeros((2, len(self._er_tap_secs_l)), dtype=np.float32)
        self._er_buffers = None
        self._er_indices = np.zeros(2, dtype=np.int32)
        # Two cascaded first-order high-pass stages = 12 dB/oct.
        self._hp_prev_x = np.zeros((2, 2), dtype=np.float32)
        self._hp_prev_y = np.zeros((2, 2), dtype=np.float32)
        self._hp_alpha = 1.0
        # Two cascaded first-order low-pass stages = 12 dB/oct (return tone).
        self._lp_prev_y = np.zeros((2, 2), dtype=np.float32)
        self._lp_alpha = 1.0

        # Compute initial coefficients
        self.update_coefficients()
        self._build_early_reflections()
        self.set_predelay_ms(self.predelay_ms)

    def update_coefficients(self):
        """Update feedback gains and filter coefficients based on rt60 and damping."""
        # Convert RT60 to comb feedback gain.
        # For a delay line with delay d seconds, the feedback gain f satisfies:
        #   f^(rt60 / d) = 10^(-3)   (because 60 dB = 10^(-60/20) = 10^-3)
        #   => f = 0.001^(d / rt60)
        # Compute per-comb gains so each delay line decays close to the target RT60.
        delay_seconds = self._comb_delays_arr.astype(np.float32) / float(self.sample_rate)
        self.comb_gains = np.clip(np.power(0.001, delay_seconds / float(self.rt60)), 0.0, 0.995).astype(np.float32)

        # Low‑pass coefficient: damping 0 = bright (fc ~10kHz), 1 = dark (fc ~2kHz)
        fc = 2000 + (1.0 - self.damping) * 8000
        self.lp_alpha = np.exp(-2.0 * np.pi * fc / self.sample_rate)

        # All‑pass gain (standard value)
        self.ap_gain = 0.7
        self._update_highpass_coefficients()
        self._update_lowpass_coefficients()

    def _update_highpass_coefficients(self):
        fc = float(np.clip(float(self.highpass_hz), 20.0, max(21.0, float(self.sample_rate) * 0.45)))
        rc = 1.0 / (2.0 * np.pi * fc)
        dt = 1.0 / float(max(1, int(self.sample_rate)))
        self._hp_alpha = float(rc / (rc + dt))

    def _update_lowpass_coefficients(self):
        fc0 = float(getattr(self, "return_lowpass_hz", 0.0) or 0.0)
        if fc0 <= 1e-6:
            self._lp_alpha = 1.0
            return
        fc = float(np.clip(fc0, 20.0, max(21.0, float(self.sample_rate) * 0.45)))
        rc = 1.0 / (2.0 * np.pi * fc)
        dt = 1.0 / float(max(1, int(self.sample_rate)))
        self._lp_alpha = float(dt / (rc + dt))

    def _build_early_reflections(self):
        spread_s = 0.5 * float(self.stereo_spread_samples) / float(max(1, int(self.sample_rate)))
        tap_l = np.asarray([max(1, int(round(s * self.sample_rate))) for s in self._er_tap_secs_l], dtype=np.int32)
        tap_r = np.asarray(
            [max(1, int(round((s + spread_s) * self.sample_rate))) for s in self._er_tap_secs_l],
            dtype=np.int32,
        )
        gains_l = np.asarray(self._er_tap_gains_l, dtype=np.float32)
        gains_r = np.roll(gains_l, 1)
        self._er_tap_delays_arr[0, :] = tap_l
        self._er_tap_delays_arr[1, :] = tap_r
        self._er_tap_gains_arr[0, :] = gains_l
        self._er_tap_gains_arr[1, :] = gains_r
        max_er_delay = int(max(np.max(tap_l), np.max(tap_r)))
        self._er_buffers = np.zeros((2, max_er_delay + 2), dtype=np.float32)
        self._er_indices[:] = 0

    def _apply_predelay(self, signal: np.ndarray) -> np.ndarray:
        d = int(getattr(self, "_predelay_delay_samples", 0) or 0)
        if d <= 0:
            return signal
        x = np.asarray(signal, dtype=np.float32)
        if NUMBA_AVAILABLE and x.ndim == 2:
            return _apply_predelay_nb(
                x,
                self._predelay_buffers,
                self._predelay_indices,
                int(d),
            ).astype(np.float32, copy=False)
        y = np.zeros_like(x)
        for ch in range(min(2, int(x.shape[1]))):
            buf = self._predelay_buffers[ch]
            idx = int(self._predelay_indices[ch])
            src = x[:, ch]
            out = y[:, ch]
            for i in range(src.shape[0]):
                out[i] = buf[idx]
                buf[idx] = src[i]
                idx += 1
                if idx >= d:
                    idx = 0
            self._predelay_indices[ch] = idx
        return y.astype(np.float32, copy=False)

    def _process_early_reflections(self, signal: np.ndarray) -> np.ndarray:
        if not bool(getattr(self, "early_reflections_enabled", True)):
            return np.zeros_like(signal, dtype=np.float32)
        x = np.asarray(signal, dtype=np.float32)
        y = np.zeros_like(x)
        if self._er_buffers is None:
            return y
        if NUMBA_AVAILABLE and x.ndim == 2:
            return _process_early_reflections_nb(
                x,
                self._er_buffers,
                self._er_indices,
                self._er_tap_delays_arr,
                self._er_tap_gains_arr,
            ).astype(np.float32, copy=False)
        for ch in range(min(2, int(x.shape[1]))):
            buf = self._er_buffers[ch]
            idx = int(self._er_indices[ch])
            size = int(buf.shape[0])
            delays = self._er_tap_delays_arr[ch]
            gains = self._er_tap_gains_arr[ch]
            src = x[:, ch]
            out = y[:, ch]
            for i in range(src.shape[0]):
                buf[idx] = src[i]
                acc = 0.0
                for t in range(delays.shape[0]):
                    ridx = idx - int(delays[t])
                    while ridx < 0:
                        ridx += size
                    acc += float(gains[t]) * float(buf[ridx])
                out[i] = acc
                idx += 1
                if idx >= size:
                    idx = 0
            self._er_indices[ch] = idx
        return y.astype(np.float32, copy=False)

    def _apply_return_highpass(self, signal: np.ndarray) -> np.ndarray:
        hp_hz = float(getattr(self, "highpass_hz", 0.0) or 0.0)
        if hp_hz <= 1e-6:
            return signal
        stages = 2 if float(getattr(self, "highpass_slope_db_per_oct", 12.0) or 12.0) >= 12.0 else 1
        stages = max(1, min(2, int(stages)))
        x = np.asarray(signal, dtype=np.float32)
        y = np.empty_like(x)
        alpha = float(getattr(self, "_hp_alpha", 1.0) or 1.0)
        ch_count = min(2, int(x.shape[1]) if x.ndim == 2 else 1)
        if x.ndim == 1:
            x2 = x.reshape((-1, 1))
            y2 = y.reshape((-1, 1))
        else:
            x2 = x
            y2 = y
        if NUMBA_AVAILABLE and x.ndim == 2:
            return _return_highpass_nb(
                x2,
                float(alpha),
                int(stages),
                self._hp_prev_x,
                self._hp_prev_y,
            ).astype(np.float32, copy=False)
        for ch in range(ch_count):
            src = x2[:, ch]
            stage_in = src
            for stage in range(stages):
                prev_x = float(self._hp_prev_x[ch, stage])
                prev_y = float(self._hp_prev_y[ch, stage])
                stage_out = np.empty_like(stage_in)
                for i in range(stage_in.shape[0]):
                    xi = float(stage_in[i])
                    yi = alpha * (prev_y + xi - prev_x)
                    stage_out[i] = yi
                    prev_x = xi
                    prev_y = yi
                self._hp_prev_x[ch, stage] = prev_x
                self._hp_prev_y[ch, stage] = prev_y
                stage_in = stage_out
            y2[:, ch] = stage_in
        if x.ndim == 2 and x.shape[1] > ch_count:
            y2[:, ch_count:] = x2[:, ch_count:]
        return y.astype(np.float32, copy=False)

    def _apply_return_lowpass(self, signal: np.ndarray) -> np.ndarray:
        lp_hz = float(getattr(self, "return_lowpass_hz", 0.0) or 0.0)
        if lp_hz <= 1e-6:
            return signal
        stages = 2 if float(getattr(self, "return_lowpass_slope_db_per_oct", 12.0) or 12.0) >= 12.0 else 1
        stages = max(1, min(2, int(stages)))
        x = np.asarray(signal, dtype=np.float32)
        y = np.empty_like(x)
        alpha = float(getattr(self, "_lp_alpha", 1.0) or 1.0)
        ch_count = min(2, int(x.shape[1]) if x.ndim == 2 else 1)
        if x.ndim == 1:
            x2 = x.reshape((-1, 1))
            y2 = y.reshape((-1, 1))
        else:
            x2 = x
            y2 = y
        if NUMBA_AVAILABLE and x.ndim == 2:
            return _return_lowpass_nb(
                x2,
                float(alpha),
                int(stages),
                self._lp_prev_y,
            ).astype(np.float32, copy=False)
        for ch in range(ch_count):
            src = x2[:, ch]
            stage_in = src
            for stage in range(stages):
                prev_y = float(self._lp_prev_y[ch, stage])
                stage_out = np.empty_like(stage_in)
                for i in range(stage_in.shape[0]):
                    yi = prev_y + alpha * (float(stage_in[i]) - prev_y)
                    stage_out[i] = yi
                    prev_y = yi
                self._lp_prev_y[ch, stage] = prev_y
                stage_in = stage_out
            y2[:, ch] = stage_in
        if x.ndim == 2 and x.shape[1] > ch_count:
            y2[:, ch_count:] = x2[:, ch_count:]
        return y.astype(np.float32, copy=False)

    @staticmethod
    def _resolve_quality_tier(quality_tier: str) -> tuple[int, int, bool]:
        """
        Returns (active_comb_count, active_allpass_count, mono_collapse, early_reflections_allowed).
        """
        qt = str(quality_tier or "high").strip().lower()
        if qt == "high_rt":
            return 7, 3, False, True
        if qt == "balanced":
            return 6, 3, False, True
        if qt == "safe":
            return 3, 2, False, False
        if qt == "emergency":
            return 2, 1, True, False
        return 8, 4, False, True

    def process(self, audio: np.ndarray, wet: float = None, quality_tier: str = "high") -> np.ndarray:
        """
        Apply reverb to a stereo audio buffer.
        If wet is provided, it overrides self.wet (mix).
        Returns wet reverb signal (stereo).
        """
        if wet is None:
            wet = self.wet
        if wet == 0:
            return np.zeros_like(audio)

        if audio.ndim == 1:
            signal = np.stack([audio, audio], axis=1).astype(np.float32, copy=False)
            mono_input = True
        else:
            signal = audio.astype(np.float32, copy=False)
            mono_input = False
        signal = self._apply_predelay(signal)
        active_comb, active_allpass, mono_collapse, er_allowed = self._resolve_quality_tier(quality_tier)
        er = np.zeros_like(signal)
        er_level = float(getattr(self, "early_reflections_level", 0.0) or 0.0)
        if (
            er_allowed
            and er_level > 1e-9
            and bool(getattr(self, "early_reflections_enabled", True))
        ):
            er = self._process_early_reflections(signal)
        signal = self._apply_return_highpass(signal)
        ch_count = 1 if mono_collapse else int(signal.shape[1])
        result = np.zeros_like(signal)
        for ch in range(ch_count):
            src = signal[:, ch]
            if mono_collapse:
                src = np.mean(signal[:, :2], axis=1).astype(np.float32, copy=False)
            comb_out = _process_comb_bank(
                src,
                self.comb_buffers[ch],
                self._comb_delays_arr[ch],
                self.comb_indices[ch],
                self.comb_lp_states[ch],
                self.comb_gains[ch],
                self.lp_alpha,
                int(active_comb),
            )
            comb_out *= 1.0 / max(int(active_comb), 1)
            ap_out = _process_allpass_chain(
                comb_out,
                self.ap_x_bufs[ch],
                self.ap_y_bufs[ch],
                self._allpass_delays_arr[ch],
                self.ap_x_indices[ch],
                self.ap_y_indices[ch],
                self.ap_gain,
                int(active_allpass),
            )

            result[:, ch] = ap_out
        if mono_collapse:
            result[:, 1] = result[:, 0]
            er[:, 1] = er[:, 0]

        if er_level > 1e-9:
            result = result + er_level * er
        result = self._apply_return_lowpass(result)
        if mono_input:
            return (result[:, 0] * wet).astype(np.float32)
        return (result * wet).astype(np.float32)

    # ----- Control methods -----
    def set_rt60(self, seconds: float):
        """Set reverb decay time (RT60) in seconds."""
        # Allow very long tails (e.g. ambient washes) while keeping a cap for stability/CPU.
        self.rt60 = float(np.clip(seconds, 0.05, 16.0))
        self.update_coefficients()

    def set_damping(self, damping: float):
        self.damping = np.clip(damping, 0.0, 1.0)
        self.update_coefficients()

    def set_wet(self, wet: float):
        self.wet = np.clip(wet, 0.0, 1.0)

    def set_return_highpass(self, hz: float, slope_db_per_oct: float = 12.0):
        self.highpass_hz = float(np.clip(float(hz), 0.0, max(20.0, float(self.sample_rate) * 0.45)))
        self.highpass_slope_db_per_oct = float(12.0 if float(slope_db_per_oct) >= 12.0 else 6.0)
        self._update_highpass_coefficients()

    def set_return_lowpass(self, hz: float, slope_db_per_oct: float = 12.0):
        self.return_lowpass_hz = float(np.clip(float(hz), 0.0, max(20.0, float(self.sample_rate) * 0.45)))
        self.return_lowpass_slope_db_per_oct = float(12.0 if float(slope_db_per_oct) >= 12.0 else 6.0)
        self._update_lowpass_coefficients()

    def set_predelay_ms(self, ms: float):
        ms_clamped = float(np.clip(float(ms), 0.0, self._predelay_max_ms))
        self.predelay_ms = ms_clamped
        self._predelay_delay_samples = int(round((ms_clamped / 1000.0) * float(self.sample_rate)))
        self._predelay_indices[:] = 0
        self._predelay_buffers.fill(0.0)

    def set_early_reflections(self, *, enabled: bool, level: float):
        self.early_reflections_enabled = bool(enabled)
        self.early_reflections_level = float(np.clip(float(level), 0.0, 1.0))

# audio/engine/mixer.py
# ---------------------------------------------------------------------------
# Multichannel summing mixer: per-strip gain/pan/EQ and a reverb/delay/distortion *send*
# accumulator. Does not run the reverb DSP or master FX — those live on the
# return tracks inside MasterBus (dry stem + aux sends only).
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

import time

import numpy as np

# Optional acceleration for tight DSP loops (realtime safety: pure-NumPy fallback).
try:  # pragma: no cover
    import numba as _nb  # type: ignore[import]
except Exception:  # pragma: no cover
    _nb = None


def _have_numba() -> bool:
    return _nb is not None


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True, fastmath=True)
    def _delay_process_nb(audio, buf, write_idx, read_idx, delay_samples, feedback, mix):
        n = audio.shape[0]
        out = np.empty_like(audio)
        max_delay = buf.shape[0]
        int_delay = int(delay_samples)
        frac = delay_samples - int_delay
        for i in range(n):
            # Read delayed sample (fractional interp in buffer).
            rp = read_idx
            if frac > 0.0:
                nxt = rp + 1
                if nxt >= max_delay:
                    nxt = 0
                d0_l = buf[rp, 0]
                d0_r = buf[rp, 1]
                d1_l = buf[nxt, 0]
                d1_r = buf[nxt, 1]
                dl = (1.0 - frac) * d0_l + frac * d1_l
                dr = (1.0 - frac) * d0_r + frac * d1_r
            else:
                dl = buf[rp, 0]
                dr = buf[rp, 1]

            in_l = audio[i, 0]
            in_r = audio[i, 1]
            out[i, 0] = (1.0 - mix) * in_l + mix * dl
            out[i, 1] = (1.0 - mix) * in_r + mix * dr

            # Feedback write.
            buf[write_idx, 0] = in_l + feedback * dl
            buf[write_idx, 1] = in_r + feedback * dr

            write_idx += 1
            if write_idx >= max_delay:
                write_idx = 0
            read_idx += 1
            if read_idx >= max_delay:
                read_idx = 0

        return out, write_idx, read_idx


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True, fastmath=True)
    def _delay_process_toned_nb(
        audio,
        buf,
        write_idx,
        read_idx,
        delay_samples,
        feedback,
        mix,
        pingpong,
        use_hp,
        hp_alpha,
        hp_stages,
        hp_prev_x,
        hp_prev_y,
        use_lp,
        lp_alpha,
        lp_stages,
        lp_prev_y,
    ):
        n = audio.shape[0]
        out = np.empty_like(audio)
        max_delay = buf.shape[0]
        frac = delay_samples - int(delay_samples)
        one_minus_mix = 1.0 - mix
        for i in range(n):
            rp = read_idx
            if frac > 0.0:
                nxt = rp + 1
                if nxt >= max_delay:
                    nxt = 0
                dl = (1.0 - frac) * buf[rp, 0] + frac * buf[nxt, 0]
                dr = (1.0 - frac) * buf[rp, 1] + frac * buf[nxt, 1]
            else:
                dl = buf[rp, 0]
                dr = buf[rp, 1]

            in_l = audio[i, 0]
            in_r = audio[i, 1]
            out[i, 0] = one_minus_mix * in_l + mix * dl
            out[i, 1] = one_minus_mix * in_r + mix * dr

            fl = dl
            fr = dr
            if use_hp:
                stage_in_l = fl
                stage_in_r = fr
                for s in range(hp_stages):
                    prev_x_l = hp_prev_x[0, s]
                    prev_y_l = hp_prev_y[0, s]
                    yi_l = hp_alpha * (prev_y_l + stage_in_l - prev_x_l)
                    hp_prev_x[0, s] = stage_in_l
                    hp_prev_y[0, s] = yi_l
                    stage_in_l = yi_l

                    prev_x_r = hp_prev_x[1, s]
                    prev_y_r = hp_prev_y[1, s]
                    yi_r = hp_alpha * (prev_y_r + stage_in_r - prev_x_r)
                    hp_prev_x[1, s] = stage_in_r
                    hp_prev_y[1, s] = yi_r
                    stage_in_r = yi_r
                fl = stage_in_l
                fr = stage_in_r
            if use_lp:
                stage_in_l = fl
                stage_in_r = fr
                for s in range(lp_stages):
                    prev_y_l = lp_prev_y[0, s]
                    yi_l = prev_y_l + lp_alpha * (stage_in_l - prev_y_l)
                    lp_prev_y[0, s] = yi_l
                    stage_in_l = yi_l

                    prev_y_r = lp_prev_y[1, s]
                    yi_r = prev_y_r + lp_alpha * (stage_in_r - prev_y_r)
                    lp_prev_y[1, s] = yi_r
                    stage_in_r = yi_r
                fl = stage_in_l
                fr = stage_in_r

            if pingpong > 1e-6:
                fb_l = (1.0 - pingpong) * fl + pingpong * fr
                fb_r = (1.0 - pingpong) * fr + pingpong * fl
                buf[write_idx, 0] = in_l + feedback * fb_l
                buf[write_idx, 1] = in_r + feedback * fb_r
            else:
                buf[write_idx, 0] = in_l + feedback * fl
                buf[write_idx, 1] = in_r + feedback * fr

            write_idx += 1
            if write_idx >= max_delay:
                write_idx = 0
            read_idx += 1
            if read_idx >= max_delay:
                read_idx = 0

        return out, write_idx, read_idx


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True, fastmath=True)
    def _channel_filter_process_nb(
        audio,
        use_hp,
        hp_alpha,
        hp_stages,
        hp_prev_x,
        hp_prev_y,
        use_lp,
        lp_alpha,
        lp_stages,
        lp_prev_y,
    ):
        n = audio.shape[0]
        out = np.empty_like(audio)
        for i in range(n):
            for ch in range(2):
                y = float(audio[i, ch])
                if use_hp:
                    for s in range(hp_stages):
                        prev_x = float(hp_prev_x[ch, s])
                        prev_y = float(hp_prev_y[ch, s])
                        yi = hp_alpha * (prev_y + y - prev_x)
                        hp_prev_x[ch, s] = y
                        hp_prev_y[ch, s] = yi
                        y = yi
                if use_lp:
                    for s in range(lp_stages):
                        prev_y = float(lp_prev_y[ch, s])
                        yi = prev_y + lp_alpha * (y - prev_y)
                        lp_prev_y[ch, s] = yi
                        y = yi
                out[i, ch] = y
        return out


if _nb is not None:  # pragma: no cover
    @_nb.njit(cache=True, fastmath=True)
    def _biquad_cascade_process_nb(audio, sos, zi):
        n = audio.shape[0]
        sections = sos.shape[0]
        out = np.empty_like(audio)
        for i in range(n):
            for ch in range(2):
                x = float(audio[i, ch])
                for s in range(sections):
                    b0 = float(sos[s, 0])
                    b1 = float(sos[s, 1])
                    b2 = float(sos[s, 2])
                    a1 = float(sos[s, 4])
                    a2 = float(sos[s, 5])
                    y = b0 * x + float(zi[s, ch, 0])
                    zi[s, ch, 0] = b1 * x - a1 * y + float(zi[s, ch, 1])
                    zi[s, ch, 1] = b2 * x - a2 * y
                    x = y
                out[i, ch] = x
        return out


    @_nb.njit(cache=True, fastmath=True)
    def _process_channel_strip_nb(audio, volume, pan, calculate_meters):
        n = audio.shape[0]
        out = np.empty((n, 2), dtype=np.float32)
        if pan != 0.0:
            angle = (pan + 1.0) * np.pi / 4.0
            left_gain = np.cos(angle) * volume
            right_gain = np.sin(angle) * volume
        else:
            left_gain = volume
            right_gain = volume

        rms_sum = 0.0
        peak = 0.0
        for i in range(n):
            l_val = audio[i, 0] * left_gain
            r_val = audio[i, 1] * right_gain
            out[i, 0] = l_val
            out[i, 1] = r_val
            if calculate_meters:
                rms_sum += l_val * l_val + r_val * r_val
                abs_l = abs(l_val)
                abs_r = abs(r_val)
                if abs_l > peak:
                    peak = abs_l
                if abs_r > peak:
                    peak = abs_r

        rms = 0.0
        if calculate_meters and n > 0:
            rms = np.sqrt(rms_sum / (2.0 * n) + 1e-12)

        return out, rms, peak


    @_nb.njit(cache=True, fastmath=True)
    def _accumulate_send_nb(send_buffer, src, send_gain):
        n = src.shape[0]
        for i in range(n):
            send_buffer[i, 0] += src[i, 0] * send_gain
            send_buffer[i, 1] += src[i, 1] * send_gain


    @_nb.njit(cache=True, fastmath=True)
    def _sum_bus_and_meters_nb(bus_buf, calculate_meters):
        n = bus_buf.shape[0]
        rms_sum = 0.0
        peak = 0.0
        for i in range(n):
            l_val = bus_buf[i, 0]
            r_val = bus_buf[i, 1]
            if calculate_meters:
                rms_sum += l_val * l_val + r_val * r_val
                abs_l = abs(l_val)
                abs_r = abs(r_val)
                if abs_l > peak:
                    peak = abs_l
                if abs_r > peak:
                    peak = abs_r
        rms = 0.0
        if calculate_meters and n > 0:
            rms = np.sqrt(rms_sum / (2.0 * n) + 1e-12)
        return rms, peak


# ----------------------------------------------------------------------
# Delay effect
# ----------------------------------------------------------------------
class Delay:
    """Simple stereo delay line with fractional interpolation."""
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.time_ms = 300.0          # default 300 ms
        self.feedback = 0.2
        self.mix = 0.4
        self.enabled = True
        # Stereo + tone controls (premium feel, avoids harsh/boomy repeats).
        # pingpong = 0 -> normal stereo feedback, 1 -> full ping-pong cross feedback.
        self.pingpong = 0.0
        self.feedback_highpass_hz = 0.0
        self.feedback_lowpass_hz = 0.0
        self.feedback_filter_slope_db_per_oct = 12.0

        self._max_delay = int(2.0 * sample_rate)   # 2 seconds max
        self._buffer = np.zeros((self._max_delay, 2), dtype=np.float32)
        self._write_idx = 0
        self._read_idx = 0
        self._delay_samples = 0
        # Feedback filter states (two-stage HP + two-stage LP).
        self._fb_hp_prev_x = np.zeros((2, 2), dtype=np.float32)
        self._fb_hp_prev_y = np.zeros((2, 2), dtype=np.float32)
        self._fb_hp_alpha = 1.0
        self._fb_lp_prev_y = np.zeros((2, 2), dtype=np.float32)
        self._fb_lp_alpha = 1.0
        self._update_delay()
        self._update_feedback_filter_coeffs()

    def set_time_ms(self, ms: float):
        self.time_ms = max(1.0, min(1000.0, ms))
        self._update_delay()

    def set_feedback(self, fb: float):
        self.feedback = np.clip(fb, 0.0, 0.99)

    def set_mix(self, mix: float):
        self.mix = np.clip(mix, 0.0, 1.0)

    def set_pingpong(self, amount: float):
        self.pingpong = float(np.clip(float(amount), 0.0, 1.0))

    def set_feedback_tone(
        self,
        *,
        highpass_hz: float | None = None,
        lowpass_hz: float | None = None,
        slope_db_per_oct: float | None = None,
    ):
        if highpass_hz is not None:
            self.feedback_highpass_hz = float(max(0.0, highpass_hz))
        if lowpass_hz is not None:
            self.feedback_lowpass_hz = float(max(0.0, lowpass_hz))
        if slope_db_per_oct is not None:
            self.feedback_filter_slope_db_per_oct = float(12.0 if float(slope_db_per_oct) >= 12.0 else 6.0)
        self._update_feedback_filter_coeffs()

    def _update_delay(self):
        self._delay_samples = self.time_ms * self.sample_rate / 1000.0
        self._read_idx = (self._write_idx - int(self._delay_samples)) % self._max_delay

    def _update_feedback_filter_coeffs(self):
        # HP alpha uses the classic discrete RC HP form used elsewhere in the project.
        hp = float(getattr(self, "feedback_highpass_hz", 0.0) or 0.0)
        if hp > 1e-6:
            fc = float(np.clip(hp, 20.0, max(21.0, float(self.sample_rate) * 0.45)))
            rc = 1.0 / (2.0 * np.pi * fc)
            dt = 1.0 / float(max(1, int(self.sample_rate)))
            self._fb_hp_alpha = float(rc / (rc + dt))
        else:
            self._fb_hp_alpha = 1.0
        # LP alpha uses y[n] = y[n-1] + a(x - y[n-1]).
        lp = float(getattr(self, "feedback_lowpass_hz", 0.0) or 0.0)
        if lp > 1e-6:
            fc = float(np.clip(lp, 20.0, max(21.0, float(self.sample_rate) * 0.45)))
            rc = 1.0 / (2.0 * np.pi * fc)
            dt = 1.0 / float(max(1, int(self.sample_rate)))
            self._fb_lp_alpha = float(dt / (rc + dt))
        else:
            self._fb_lp_alpha = 1.0

    def _apply_feedback_filters_sample(self, x_lr: np.ndarray) -> np.ndarray:
        """
        Apply HP then LP to the delayed sample used for feedback. 1 or 2 stages (6/12 dB/oct).
        """
        stages = 2 if float(getattr(self, "feedback_filter_slope_db_per_oct", 12.0) or 12.0) >= 12.0 else 1
        stages = max(1, min(2, int(stages)))
        y = x_lr.astype(np.float32, copy=False)

        hp_hz = float(getattr(self, "feedback_highpass_hz", 0.0) or 0.0)
        if hp_hz > 1e-6:
            a = float(getattr(self, "_fb_hp_alpha", 1.0) or 1.0)
            for ch in range(2):
                stage_in = float(y[ch])
                for s in range(stages):
                    prev_x = float(self._fb_hp_prev_x[ch, s])
                    prev_y = float(self._fb_hp_prev_y[ch, s])
                    yi = a * (prev_y + stage_in - prev_x)
                    self._fb_hp_prev_x[ch, s] = stage_in
                    self._fb_hp_prev_y[ch, s] = yi
                    stage_in = yi
                y[ch] = stage_in

        lp_hz = float(getattr(self, "feedback_lowpass_hz", 0.0) or 0.0)
        if lp_hz > 1e-6:
            a = float(getattr(self, "_fb_lp_alpha", 1.0) or 1.0)
            for ch in range(2):
                stage_in = float(y[ch])
                for s in range(stages):
                    prev_y = float(self._fb_lp_prev_y[ch, s])
                    yi = prev_y + a * (stage_in - prev_y)
                    self._fb_lp_prev_y[ch, s] = yi
                    stage_in = yi
                y[ch] = stage_in

        return y

    def process(self, audio: np.ndarray) -> np.ndarray:
        if not self.enabled or self.mix == 0.0:
            return audio

        x = np.asarray(audio, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != 2:
            # Keep it simple/robust for unexpected shapes.
            x = np.column_stack([x.reshape(-1), x.reshape(-1)]).astype(np.float32, copy=False)

        delay_samples = float(self._delay_samples)
        feedback = float(self.feedback)
        mix = float(self.mix)
        pp = float(getattr(self, "pingpong", 0.0) or 0.0)
        feedback_tone_active = (
            float(getattr(self, "feedback_highpass_hz", 0.0) or 0.0) > 1e-6
            or float(getattr(self, "feedback_lowpass_hz", 0.0) or 0.0) > 1e-6
        )

        if _have_numba():
            if pp <= 1e-6 and not feedback_tone_active:
                y, wi, ri = _delay_process_nb(
                    x, self._buffer, int(self._write_idx), int(self._read_idx), delay_samples, feedback, mix
                )
            else:
                stages = 2 if float(getattr(self, "feedback_filter_slope_db_per_oct", 12.0) or 12.0) >= 12.0 else 1
                stages = max(1, min(2, int(stages)))
                y, wi, ri = _delay_process_toned_nb(
                    x,
                    self._buffer,
                    int(self._write_idx),
                    int(self._read_idx),
                    delay_samples,
                    feedback,
                    mix,
                    pp,
                    bool(float(getattr(self, "feedback_highpass_hz", 0.0) or 0.0) > 1e-6),
                    float(getattr(self, "_fb_hp_alpha", 1.0) or 1.0),
                    int(stages),
                    self._fb_hp_prev_x,
                    self._fb_hp_prev_y,
                    bool(float(getattr(self, "feedback_lowpass_hz", 0.0) or 0.0) > 1e-6),
                    float(getattr(self, "_fb_lp_alpha", 1.0) or 1.0),
                    int(stages),
                    self._fb_lp_prev_y,
                )
            self._write_idx = int(wi)
            self._read_idx = int(ri)
            return y.astype(np.float32, copy=False)

        # Fallback: optimized Python loop (avoid extra arrays).
        out = np.empty_like(x)
        int_delay = int(delay_samples)
        frac = delay_samples - int_delay
        wi = int(self._write_idx)
        ri = int(self._read_idx)
        buf = self._buffer
        max_delay = int(self._max_delay)
        one_minus_mix = 1.0 - mix
        for i in range(x.shape[0]):
            rp = ri
            if frac > 0.0:
                nxt = rp + 1
                if nxt >= max_delay:
                    nxt = 0
                delayed = (1.0 - frac) * buf[rp] + frac * buf[nxt]
            else:
                delayed = buf[rp]
            # Tone the feedback path (keeps repeats clean and premium).
            d_filt = self._apply_feedback_filters_sample(delayed.copy())
            out[i] = one_minus_mix * x[i] + mix * delayed
            # Ping-pong cross feedback.
            if pp > 1e-6:
                dl = float(d_filt[0])
                dr = float(d_filt[1])
                xl = float(x[i, 0])
                xr = float(x[i, 1])
                fb_l = (1.0 - pp) * dl + pp * dr
                fb_r = (1.0 - pp) * dr + pp * dl
                buf[wi, 0] = xl + feedback * fb_l
                buf[wi, 1] = xr + feedback * fb_r
            else:
                buf[wi] = x[i] + feedback * d_filt
            wi += 1
            if wi >= max_delay:
                wi = 0
            ri += 1
            if ri >= max_delay:
                ri = 0
        self._write_idx = int(wi)
        self._read_idx = int(ri)
        return out.astype(np.float32, copy=False)


class Distortion:
    """Simple soft-clip distortion for master coloration."""
    def __init__(self):
        self.enabled = False
        self.drive = 1.0
        self.mix = 0.0
        # Tone controls (keeps distortion usable as a return).
        self.tone_highpass_hz = 120.0
        self.tone_lowpass_hz = 8500.0
        self.tone_slope_db_per_oct = 12.0
        self._hp_prev_x = np.zeros((2, 2), dtype=np.float32)
        self._hp_prev_y = np.zeros((2, 2), dtype=np.float32)
        self._hp_alpha = 1.0
        self._lp_prev_y = np.zeros((2, 2), dtype=np.float32)
        self._lp_alpha = 1.0
        self._sample_rate = 44100
        self._update_tone_coeffs()

    def set_sample_rate(self, sample_rate: int):
        sr = int(max(8000, sample_rate))
        if sr == int(getattr(self, "_sample_rate", 44100)):
            return
        self._sample_rate = sr
        self._update_tone_coeffs()

    def set_tone(self, *, highpass_hz: float | None = None, lowpass_hz: float | None = None, slope_db_per_oct: float | None = None):
        if highpass_hz is not None:
            self.tone_highpass_hz = float(max(0.0, highpass_hz))
        if lowpass_hz is not None:
            self.tone_lowpass_hz = float(max(0.0, lowpass_hz))
        if slope_db_per_oct is not None:
            self.tone_slope_db_per_oct = float(12.0 if float(slope_db_per_oct) >= 12.0 else 6.0)
        self._update_tone_coeffs()

    def _update_tone_coeffs(self):
        sr = float(int(getattr(self, "_sample_rate", 44100)))
        hp = float(getattr(self, "tone_highpass_hz", 0.0) or 0.0)
        if hp > 1e-6:
            fc = float(np.clip(hp, 20.0, max(21.0, sr * 0.45)))
            rc = 1.0 / (2.0 * np.pi * fc)
            dt = 1.0 / max(1.0, sr)
            self._hp_alpha = float(rc / (rc + dt))
        else:
            self._hp_alpha = 1.0
        lp = float(getattr(self, "tone_lowpass_hz", 0.0) or 0.0)
        if lp > 1e-6:
            fc = float(np.clip(lp, 20.0, max(21.0, sr * 0.45)))
            rc = 1.0 / (2.0 * np.pi * fc)
            dt = 1.0 / max(1.0, sr)
            self._lp_alpha = float(dt / (rc + dt))
        else:
            self._lp_alpha = 1.0

    def _apply_tone(self, audio: np.ndarray) -> np.ndarray:
        stages = 2 if float(getattr(self, "tone_slope_db_per_oct", 12.0) or 12.0) >= 12.0 else 1
        stages = max(1, min(2, int(stages)))
        x = np.asarray(audio, dtype=np.float32)
        y = x.copy()
        hp = float(getattr(self, "tone_highpass_hz", 0.0) or 0.0)
        if hp > 1e-6:
            a = float(getattr(self, "_hp_alpha", 1.0) or 1.0)
            for ch in range(2):
                src = y[:, ch]
                stage_in = src
                for s in range(stages):
                    prev_x = float(self._hp_prev_x[ch, s])
                    prev_y = float(self._hp_prev_y[ch, s])
                    out = np.empty_like(stage_in)
                    for i in range(stage_in.shape[0]):
                        xi = float(stage_in[i])
                        yi = a * (prev_y + xi - prev_x)
                        out[i] = yi
                        prev_x = xi
                        prev_y = yi
                    self._hp_prev_x[ch, s] = prev_x
                    self._hp_prev_y[ch, s] = prev_y
                    stage_in = out
                y[:, ch] = stage_in
        lp = float(getattr(self, "tone_lowpass_hz", 0.0) or 0.0)
        if lp > 1e-6:
            a = float(getattr(self, "_lp_alpha", 1.0) or 1.0)
            for ch in range(2):
                src = y[:, ch]
                stage_in = src
                for s in range(stages):
                    prev_y = float(self._lp_prev_y[ch, s])
                    out = np.empty_like(stage_in)
                    for i in range(stage_in.shape[0]):
                        yi = prev_y + a * (float(stage_in[i]) - prev_y)
                        out[i] = yi
                        prev_y = yi
                    self._lp_prev_y[ch, s] = prev_y
                    stage_in = out
                y[:, ch] = stage_in
        return y.astype(np.float32, copy=False)

    def process(self, audio: np.ndarray) -> np.ndarray:
        if not self.enabled or self.mix <= 0.0:
            return audio
        drive = max(1.0, float(self.drive))
        x = np.asarray(audio, dtype=np.float32)
        wet = np.tanh(x * drive) / np.tanh(drive)
        wet = self._apply_tone(wet)
        return ((1.0 - self.mix) * audio + self.mix * wet).astype(np.float32)


# ----------------------------------------------------------------------
# EQ class (3‑band)
# ----------------------------------------------------------------------
class EQ:
    """CPU‑efficient 3‑band EQ for one channel (low‑shelf, peaking, high‑shelf)."""
    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.low_gain_db = 0.0
        self.mid_gain_db = 0.0
        self.high_gain_db = 0.0
        self.low_freq = 80.0
        self.mid_freq = 1000.0
        self.high_freq = 5000.0
        self.mid_q = 1.0
        self.enabled = True

        self._sos = np.zeros((0, 6), dtype=np.float32)
        self._zi = np.zeros((0, 2, 2), dtype=np.float32)
        self._last_params = None

    def _update_coeffs(self):
        params = (
            float(self.low_gain_db),
            float(self.mid_gain_db),
            float(self.high_gain_db),
            float(self.low_freq),
            float(self.mid_freq),
            float(self.high_freq),
            float(self.mid_q),
            int(self.sample_rate),
        )
        if params == self._last_params:
            return
        self._last_params = params
        coeffs = []

        sample_rate = float(max(1, int(self.sample_rate)))
        nyquist = sample_rate / 2.0

        # Low‑shelf filter
        if abs(self.low_gain_db) > 0.01:
            fc = min(self.low_freq, nyquist - 1)
            w0 = 2 * np.pi * fc / sample_rate
            A = 10 ** (self.low_gain_db / 40.0)
            cos_w0 = np.cos(w0)
            sin_w0 = np.sin(w0)
            S = 1.0
            alpha = sin_w0 / 2 * np.sqrt((A + 1/A) * (1/S - 1) + 2)
            b0 = A * ((A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
            b1 = 2 * A * ((A - 1) - (A + 1) * cos_w0)
            b2 = A * ((A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
            a1 = -2 * ((A - 1) + (A + 1) * cos_w0)
            a2 = (A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
            b0 /= a0
            b1 /= a0
            b2 /= a0
            a1 /= a0
            a2 /= a0
            coeffs.append([b0, b1, b2, 1.0, a1, a2])

        # Mid (peaking) filter
        if abs(self.mid_gain_db) > 0.01:
            fc = min(self.mid_freq, nyquist - 1)
            w0 = 2 * np.pi * fc / sample_rate
            A = 10 ** (self.mid_gain_db / 40.0)
            cos_w0 = np.cos(w0)
            sin_w0 = np.sin(w0)
            alpha = sin_w0 / (2 * self.mid_q)
            b0 = 1 + alpha * A
            b1 = -2 * cos_w0
            b2 = 1 - alpha * A
            a0 = 1 + alpha / A
            a1 = -2 * cos_w0
            a2 = 1 - alpha / A
            b0 /= a0
            b1 /= a0
            b2 /= a0
            a1 /= a0
            a2 /= a0
            coeffs.append([b0, b1, b2, 1.0, a1, a2])

        # High‑shelf filter
        if abs(self.high_gain_db) > 0.01:
            fc = min(self.high_freq, nyquist - 1)
            w0 = 2 * np.pi * fc / sample_rate
            A = 10 ** (self.high_gain_db / 40.0)
            cos_w0 = np.cos(w0)
            sin_w0 = np.sin(w0)
            S = 1.0
            alpha = sin_w0 / 2 * np.sqrt((A + 1/A) * (1/S - 1) + 2)
            b0 = A * ((A + 1) + (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha)
            b1 = -2 * A * ((A - 1) + (A + 1) * cos_w0)
            b2 = A * ((A + 1) + (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha)
            a0 = (A + 1) - (A - 1) * cos_w0 + 2 * np.sqrt(A) * alpha
            a1 = 2 * ((A - 1) - (A + 1) * cos_w0)
            a2 = (A + 1) - (A - 1) * cos_w0 - 2 * np.sqrt(A) * alpha
            b0 /= a0
            b1 /= a0
            b2 /= a0
            a1 /= a0
            a2 /= a0
            coeffs.append([b0, b1, b2, 1.0, a1, a2])

        self._sos = np.asarray(coeffs, dtype=np.float32).reshape((-1, 6)) if coeffs else np.zeros((0, 6), dtype=np.float32)
        self._zi = np.zeros((self._sos.shape[0], 2, 2), dtype=np.float32)

    def active(self) -> bool:
        if not bool(self.enabled):
            return False
        self._update_coeffs()
        return bool(self._sos.shape[0] > 0)

    def reset(self):
        if self._zi.size:
            self._zi.fill(0.0)

    def process(self, audio: np.ndarray) -> np.ndarray:
        if not bool(self.enabled):
            return np.asarray(audio, dtype=np.float32)
        self._update_coeffs()
        if self._sos.shape[0] == 0:
            return np.asarray(audio, dtype=np.float32)

        x = np.asarray(audio, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != 2:
            x = np.column_stack([x.reshape(-1), x.reshape(-1)]).astype(np.float32, copy=False)
        if _have_numba():
            return _biquad_cascade_process_nb(x, self._sos, self._zi).astype(np.float32, copy=False)

        result = np.empty_like(x)
        for i in range(x.shape[0]):
            for ch in range(2):
                y = float(x[i, ch])
                for section_idx, sos in enumerate(self._sos):
                    b0 = float(sos[0])
                    b1 = float(sos[1])
                    b2 = float(sos[2])
                    a1 = float(sos[4])
                    a2 = float(sos[5])
                    out = b0 * y + float(self._zi[section_idx, ch, 0])
                    self._zi[section_idx, ch, 0] = b1 * y - a1 * out + float(self._zi[section_idx, ch, 1])
                    self._zi[section_idx, ch, 1] = b2 * y - a2 * out
                    y = out
                result[i, ch] = y
        return result.astype(np.float32, copy=False)


class ChannelFilterBank:
    """Per-strip high-pass / low-pass filter bank using cheap stateful one-pole cascades."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = int(sample_rate)
        self.enabled = True
        self.highpass_hz = 0.0
        self.lowpass_hz = 0.0
        self.slope_db_per_oct = 12.0
        self._use_hp = False
        self._use_lp = False
        self._hp_alpha = 1.0
        self._lp_alpha = 1.0
        self._stages = 2
        self._hp_prev_x = np.zeros((2, 4), dtype=np.float32)
        self._hp_prev_y = np.zeros((2, 4), dtype=np.float32)
        self._lp_prev_y = np.zeros((2, 4), dtype=np.float32)
        self._last_params = None

    @staticmethod
    def _order_for_slope(slope_db_per_oct: float) -> int:
        return int(max(1, min(4, round(float(slope_db_per_oct or 12.0) / 6.0))))

    @staticmethod
    def _one_pole_alpha(cutoff_hz: float, sample_rate: int, *, highpass: bool) -> float:
        fc = float(np.clip(float(cutoff_hz), 20.0, max(21.0, float(sample_rate) * 0.45)))
        rc = 1.0 / (2.0 * np.pi * fc)
        dt = 1.0 / float(max(1, int(sample_rate)))
        if bool(highpass):
            return float(rc / (rc + dt))
        return float(dt / (rc + dt))

    def _update_coeffs(self):
        params = (
            bool(self.enabled),
            float(self.highpass_hz),
            float(self.lowpass_hz),
            float(self.slope_db_per_oct),
            int(self.sample_rate),
        )
        if params == self._last_params:
            return
        self._last_params = params
        self._use_hp = False
        self._use_lp = False
        self._hp_alpha = 1.0
        self._lp_alpha = 1.0
        self._stages = self._order_for_slope(float(self.slope_db_per_oct))
        if not bool(self.enabled):
            return

        nyquist = max(1.0, float(self.sample_rate) * 0.5)
        hp = float(max(0.0, self.highpass_hz))
        lp = float(max(0.0, self.lowpass_hz))
        if hp >= 20.0 and hp < nyquist - 1.0:
            self._use_hp = True
            self._hp_alpha = self._one_pole_alpha(hp, int(self.sample_rate), highpass=True)
        if lp >= 20.0 and lp < nyquist - 1.0:
            self._use_lp = True
            self._lp_alpha = self._one_pole_alpha(lp, int(self.sample_rate), highpass=False)

    def active(self) -> bool:
        if not bool(self.enabled):
            return False
        self._update_coeffs()
        return bool(self._use_hp or self._use_lp)

    def process(self, audio: np.ndarray) -> np.ndarray:
        if not bool(self.enabled):
            return np.asarray(audio, dtype=np.float32)
        self._update_coeffs()
        if not bool(self._use_hp or self._use_lp):
            return np.asarray(audio, dtype=np.float32)
        x = np.asarray(audio, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != 2:
            x = np.column_stack([x.reshape(-1), x.reshape(-1)]).astype(np.float32, copy=False)
        stages = int(max(1, min(4, int(self._stages))))
        if _have_numba():
            return _channel_filter_process_nb(
                x,
                bool(self._use_hp),
                float(self._hp_alpha),
                int(stages),
                self._hp_prev_x,
                self._hp_prev_y,
                bool(self._use_lp),
                float(self._lp_alpha),
                int(stages),
                self._lp_prev_y,
            ).astype(np.float32, copy=False)

        result = np.empty_like(x)
        for i in range(x.shape[0]):
            for ch in range(2):
                y = float(x[i, ch])
                if self._use_hp:
                    for s in range(stages):
                        prev_x = float(self._hp_prev_x[ch, s])
                        prev_y = float(self._hp_prev_y[ch, s])
                        yi = float(self._hp_alpha) * (prev_y + y - prev_x)
                        self._hp_prev_x[ch, s] = y
                        self._hp_prev_y[ch, s] = yi
                        y = yi
                if self._use_lp:
                    for s in range(stages):
                        prev_y = float(self._lp_prev_y[ch, s])
                        yi = prev_y + float(self._lp_alpha) * (y - prev_y)
                        self._lp_prev_y[ch, s] = yi
                        y = yi
                result[i, ch] = y
        return result.astype(np.float32, copy=False)

    def reset(self):
        self._hp_prev_x.fill(0.0)
        self._hp_prev_y.fill(0.0)
        self._lp_prev_y.fill(0.0)


# ----------------------------------------------------------------------
# MixerChannel (extended with delay)
# ----------------------------------------------------------------------
@dataclass
class MixerChannel:
    name: str = "Channel"
    index: int = 0
    volume: float = 1.0
    mute: bool = False
    solo: bool = False
    pan: float = 0.0
    reverb_send: float = 0.0
    delay_send: float = 0.0
    distortion_send: float = 0.0
    output_bus: str = "master"
    # Ableton-like per-send staging (None => inherit from sends_pre_fader).
    reverb_send_pre_fader: Optional[bool] = None
    delay_send_pre_fader: Optional[bool] = None
    distortion_send_pre_fader: Optional[bool] = None
    sends_pre_fader: bool = False

    # EQ (off by default; master Fletcher–Munson curve is authoritative)
    eq_enabled: bool = False
    eq_low_gain_db: float = 0.0
    eq_mid_gain_db: float = 0.0
    eq_high_gain_db: float = 0.0
    eq_low_freq: float = 80.0
    eq_mid_freq: float = 1000.0
    eq_high_freq: float = 5000.0
    eq_mid_q: float = 1.0
    filter_enabled: bool = True
    highpass_hz: float = 0.0
    lowpass_hz: float = 0.0
    filter_slope_db_per_oct: float = 12.0

    _eq: EQ = field(init=False, repr=False)
    _filter_bank: ChannelFilterBank = field(init=False, repr=False)
    _delay: Delay = field(init=False, repr=False)

    def __post_init__(self):
        self._eq = EQ()
        self._filter_bank = ChannelFilterBank()
        self._delay = Delay()
        # Delay is now implemented as a shared send/return bus in MasterBus.

    def set_sample_rate(self, sample_rate: int):
        if (
            self._eq.sample_rate == sample_rate
            and self._filter_bank.sample_rate == sample_rate
            and self._delay.sample_rate == sample_rate
        ):
            return
        self._eq.sample_rate = sample_rate
        self._filter_bank.sample_rate = int(sample_rate)
        self._delay = Delay(sample_rate=sample_rate)
        # Delay is now implemented as a shared send/return bus in MasterBus.

    def apply_filters(self, audio: np.ndarray, sample_rate: int = 44100) -> np.ndarray:
        result = np.asarray(audio, dtype=np.float32)
        filter_active = False
        if bool(self.filter_enabled):
            self._filter_bank.sample_rate = int(sample_rate)
            self._filter_bank.enabled = True
            self._filter_bank.highpass_hz = float(self.highpass_hz)
            self._filter_bank.lowpass_hz = float(self.lowpass_hz)
            self._filter_bank.slope_db_per_oct = float(self.filter_slope_db_per_oct)
            filter_active = bool(self._filter_bank.active())

        eq_active = False
        if bool(self.eq_enabled):
            self._eq.sample_rate = sample_rate
            self._eq.enabled = True
            self._eq.low_gain_db = self.eq_low_gain_db
            self._eq.mid_gain_db = self.eq_mid_gain_db
            self._eq.high_gain_db = self.eq_high_gain_db
            self._eq.low_freq = self.eq_low_freq
            self._eq.mid_freq = self.eq_mid_freq
            self._eq.high_freq = self.eq_high_freq
            self._eq.mid_q = self.eq_mid_q
            eq_active = bool(self._eq.active())

        if not eq_active and not filter_active:
            return result.astype(np.float32, copy=False)

        if eq_active:
            result = self._eq.process(result)

        if filter_active:
            result = self._filter_bank.process(result)

        return result.astype(np.float32, copy=False)


@dataclass
class MeterState:
    rms_db: float = -120.0
    peak_db: float = -120.0
    clip_count: int = 0
    updated_at: float = 0.0


# ----------------------------------------------------------------------
# AudioMixer (with delay events)
# ----------------------------------------------------------------------
class AudioMixer:
    def __init__(self, num_channels: int = 7, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        names_default = {
            0: "Bass",
            1: "Chords",
            2: "Melody",
            3: "Arp",
            4: "Drone",
            5: "Counter",
            6: "Kick",
        }
        n = max(1, int(num_channels))
        self.channels = [MixerChannel(name=names_default.get(i, f"Ch_{i}"), index=i) for i in range(n)]
        for channel in self.channels:
            channel.set_sample_rate(sample_rate)
        self._max_block_size = 8192
        self._temp_buffers = [
            np.zeros((self._max_block_size, 2), dtype=np.float32)
            for _ in range(len(self.channels))
        ]
        self._reverb_send_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
        self._delay_send_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
        self._distortion_send_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
        self._dry_mix_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
        self._event_bus = None
        self._meters: Dict[int, MeterState] = {}
        self._bus_meters: Dict[str, MeterState] = {}

    def bus_meters_snapshot(self) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for k, st in (self._bus_meters or {}).items():
            out[str(k)] = {
                "rms_db": float(getattr(st, "rms_db", -120.0)),
                "peak_db": float(getattr(st, "peak_db", -120.0)),
                "clip_count": float(getattr(st, "clip_count", 0)),
                "updated_at": float(getattr(st, "updated_at", 0.0)),
            }
        return out

    @staticmethod
    def _linear_to_db(x: float) -> float:
        return 20.0 * float(np.log10(max(1e-12, float(x))))

    def meters_snapshot(self) -> Dict[int, Dict[str, float]]:
        out: Dict[int, Dict[str, float]] = {}
        for ch, st in (self._meters or {}).items():
            out[int(ch)] = {
                "rms_db": float(getattr(st, "rms_db", -120.0)),
                "peak_db": float(getattr(st, "peak_db", -120.0)),
                "clip_count": float(getattr(st, "clip_count", 0)),
                "updated_at": float(getattr(st, "updated_at", 0.0)),
            }
        return out

    def set_event_bus(self, event_bus):
        self._event_bus = event_bus
        event_bus.subscribe("set_channel_volume", self._on_set_channel_volume)
        event_bus.subscribe("set_channel_reverb", self._on_set_channel_reverb)
        event_bus.subscribe("set_channel_eq_gains", self._on_set_channel_eq_gains)
        event_bus.subscribe("set_channel_eq_freqs", self._on_set_channel_eq_freqs)
        event_bus.subscribe("set_channel_filters", self._on_set_channel_filters)
        event_bus.subscribe("set_channel_sends", self._on_set_channel_sends)

    # Handlers
    def _on_set_channel_volume(self, data):
        self.set_channel_volume(data["index"], data["volume"])

    def _on_set_channel_reverb(self, data):
        self.set_channel_reverb_send(data["index"], data["send"])

    def _on_set_channel_eq_gains(self, data):
        ch = self.get_channel(data["index"])
        if ch:
            if "low_gain_db" in data:
                ch.eq_low_gain_db = data["low_gain_db"]
            if "mid_gain_db" in data:
                ch.eq_mid_gain_db = data["mid_gain_db"]
            if "high_gain_db" in data:
                ch.eq_high_gain_db = data["high_gain_db"]
            if "enabled" in data:
                ch.eq_enabled = data["enabled"]

    def _on_set_channel_eq_freqs(self, data):
        ch = self.get_channel(data["index"])
        if ch:
            if "low_freq" in data:
                ch.eq_low_freq = data["low_freq"]
            if "mid_freq" in data:
                ch.eq_mid_freq = data["mid_freq"]
            if "high_freq" in data:
                ch.eq_high_freq = data["high_freq"]
            if "mid_q" in data:
                ch.eq_mid_q = data["mid_q"]

    def _on_set_channel_filters(self, data):
        ch = self.get_channel(data["index"])
        if ch:
            if "enabled" in data:
                ch.filter_enabled = bool(data["enabled"])
            if "highpass_hz" in data:
                ch.highpass_hz = float(max(0.0, data["highpass_hz"]))
            if "lowpass_hz" in data:
                ch.lowpass_hz = float(max(0.0, data["lowpass_hz"]))
            if "slope_db_per_oct" in data:
                ch.filter_slope_db_per_oct = float(max(6.0, min(24.0, data["slope_db_per_oct"])))

    def _on_set_channel_sends(self, data):
        ch = self.get_channel(data["index"])
        if not ch:
            return
        if "reverb_send" in data:
            ch.reverb_send = float(np.clip(data["reverb_send"], 0.0, 1.0))
        if "delay_send" in data:
            ch.delay_send = float(np.clip(data["delay_send"], 0.0, 1.0))
        if "distortion_send" in data:
            ch.distortion_send = float(np.clip(data["distortion_send"], 0.0, 1.0))

    # Public methods
    def get_channel(self, channel_index: int):
        if 0 <= channel_index < len(self.channels):
            return self.channels[channel_index]
        return None

    def set_channel_volume(self, channel_index: int, volume: float):
        ch = self.get_channel(channel_index)
        if ch:
            ch.volume = np.clip(volume, 0.0, 2.0)

    def set_channel_reverb_send(self, channel_index: int, send: float):
        ch = self.get_channel(channel_index)
        if ch:
            ch.reverb_send = np.clip(send, 0.0, 1.0)

    def set_channel_filters(
        self,
        channel_index: int,
        *,
        highpass_hz: Optional[float] = None,
        lowpass_hz: Optional[float] = None,
        enabled: Optional[bool] = None,
        slope_db_per_oct: Optional[float] = None,
    ) -> None:
        ch = self.get_channel(channel_index)
        if not ch:
            return
        if enabled is not None:
            ch.filter_enabled = bool(enabled)
        if highpass_hz is not None:
            ch.highpass_hz = float(max(0.0, highpass_hz))
        if lowpass_hz is not None:
            ch.lowpass_hz = float(max(0.0, lowpass_hz))
        if slope_db_per_oct is not None:
            ch.filter_slope_db_per_oct = float(max(6.0, min(24.0, slope_db_per_oct)))

    def process_channel_and_meters(
        self, audio: np.ndarray, channel_index: int, calculate_meters: bool = True
    ) -> Tuple[np.ndarray, float, float]:
        channel = self.get_channel(channel_index)
        if not channel or channel.mute or len(audio) == 0:
            z = np.zeros_like(audio)
            return z, 0.0, 0.0
        vol = float(getattr(channel, "volume", 1.0) or 0.0)
        if vol <= 1e-8:
            z = np.zeros_like(audio)
            return z, 0.0, 0.0

        if _have_numba():
            processed, rms, peak = _process_channel_strip_nb(
                np.asarray(audio, dtype=np.float32),
                vol,
                float(channel.pan),
                bool(calculate_meters)
            )
        else:
            processed = audio * vol
            if channel.pan != 0.0:
                angle = (channel.pan + 1.0) * np.pi / 4.0
                left_gain = np.cos(angle)
                right_gain = np.sin(angle)
                processed = processed.copy()
                processed[:, 0] *= left_gain
                processed[:, 1] *= right_gain
            if calculate_meters:
                rms = float(np.sqrt(np.mean(processed * processed) + 1e-12))
                peak = float(np.max(np.abs(processed)))
            else:
                rms, peak = 0.0, 0.0

        processed = channel.apply_filters(processed, self.sample_rate)
        return processed, rms, peak

    def process_channel(self, audio: np.ndarray, channel_index: int) -> np.ndarray:
        processed, _, _ = self.process_channel_and_meters(audio, channel_index, calculate_meters=False)
        return processed

    def _pre_fader_signal(self, audio: np.ndarray, channel: MixerChannel) -> np.ndarray:
        """
        Pre-fader send signal (post-pan/EQ, pre-volume).
        Keeps pre-fader sends musically consistent while allowing fader rides.
        """
        if audio is None or len(audio) == 0:
            return np.zeros_like(audio)
        x = np.asarray(audio, dtype=np.float32)
        if _have_numba():
            processed, _, _ = _process_channel_strip_nb(x, 1.0, float(channel.pan), False)
        else:
            if channel.pan != 0.0:
                angle = (channel.pan + 1.0) * np.pi / 4.0
                left_gain = np.cos(angle)
                right_gain = np.sin(angle)
                x = x.copy()
                x[:, 0] *= left_gain
                x[:, 1] *= right_gain
            processed = x
        processed = channel.apply_filters(processed, self.sample_rate)
        return processed

    def mix_audio(self, channel_audio: Dict[int, np.ndarray]) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (dry, reverb_send, delay_send, distortion_send) buffers."""
        if not channel_audio:
            z = np.zeros((1, 2), dtype=np.float32)
            return z, z.copy(), z.copy(), z.copy()

        soloed_channels = {c.index for c in self.channels if c.solo}
        has_solo = bool(soloed_channels)

        max_len = max(len(a) for a in channel_audio.values())
        if max_len > self._max_block_size:
            self._max_block_size = max_len
            self._temp_buffers = [
                np.zeros((self._max_block_size, 2), dtype=np.float32)
                for _ in range(len(self.channels))
            ]
            self._reverb_send_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
            self._delay_send_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
            self._distortion_send_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)
            self._dry_mix_buffer = np.zeros((self._max_block_size, 2), dtype=np.float32)

        mixed_dry = self._dry_mix_buffer[:max_len]
        mixed_dry.fill(0.0)
        bus_sums: Dict[str, np.ndarray] = {}
        master_meter_needed = False
        self._reverb_send_buffer[:max_len].fill(0.0)
        self._delay_send_buffer[:max_len].fill(0.0)
        self._distortion_send_buffer[:max_len].fill(0.0)

        for ch_idx, audio in channel_audio.items():
            channel = self.get_channel(ch_idx)
            if not channel or channel.mute:
                continue
            if has_solo and ch_idx not in soloed_channels:
                continue

            if ch_idx >= len(self._temp_buffers):
                continue
            temp = self._temp_buffers[ch_idx][:len(audio)]
            temp[:] = audio
            processed, rms, peak = self.process_channel_and_meters(temp, ch_idx, calculate_meters=True)
            send_src_post = processed
            send_src_pre = None
            try:
                want_rev_pre = channel.reverb_send_pre_fader if channel.reverb_send_pre_fader is not None else bool(getattr(channel, "sends_pre_fader", False))
                want_dly_pre = channel.delay_send_pre_fader if channel.delay_send_pre_fader is not None else bool(getattr(channel, "sends_pre_fader", False))
                want_dst_pre = (
                    channel.distortion_send_pre_fader
                    if channel.distortion_send_pre_fader is not None
                    else bool(getattr(channel, "sends_pre_fader", False))
                )
                any_pre = bool(want_rev_pre or want_dly_pre or want_dst_pre)
            except Exception:
                want_rev_pre = bool(getattr(channel, "sends_pre_fader", False))
                want_dly_pre = bool(getattr(channel, "sends_pre_fader", False))
                want_dst_pre = bool(getattr(channel, "sends_pre_fader", False))
                any_pre = bool(want_rev_pre or want_dly_pre or want_dst_pre)
            if any_pre:
                try:
                    vol = float(getattr(channel, "volume", 1.0) or 0.0)
                except Exception:
                    vol = 1.0
                if abs(vol) > 1e-6:
                    # Strip path is linear (pan -> EQ -> fader), so we can recover
                    # pre-fader audio from post-fader without a second EQ pass.
                    send_src_pre = (send_src_post / vol).astype(np.float32, copy=False)
                else:
                    try:
                        send_src_pre = self._pre_fader_signal(temp, channel)
                    except Exception:
                        send_src_pre = send_src_post

            # Meters (post-strip, pre-sum) like a DAW channel meter.
            try:
                st = self._meters.get(int(ch_idx))
                if st is None:
                    st = MeterState()
                    self._meters[int(ch_idx)] = st
                rms_db = self._linear_to_db(rms)
                peak_db = self._linear_to_db(peak)
                # Smooth for UI readability.
                a = 0.15
                st.rms_db = (1.0 - a) * float(st.rms_db) + a * float(rms_db)
                # Peak holds then decays.
                st.peak_db = max(float(st.peak_db) * 0.92, float(peak_db))
                if peak > 1.0:
                    st.clip_count = int(getattr(st, "clip_count", 0) or 0) + 1
                st.updated_at = float(time.time())
            except Exception:
                pass

            bus = str(getattr(channel, "output_bus", "master") or "master").strip().lower()
            if not bus:
                bus = "master"
            if bus == "master":
                mixed_dry[:len(processed)] += processed
                master_meter_needed = True
            else:
                if bus not in bus_sums:
                    bus_sums[bus] = np.zeros((max_len, 2), dtype=np.float32)
                bus_sums[bus][:len(processed)] += processed

            n = len(processed)
            if channel.reverb_send > 0.0:
                src = (send_src_pre if bool(want_rev_pre) and send_src_pre is not None else send_src_post)
                if _have_numba():
                    _accumulate_send_nb(self._reverb_send_buffer[:n], src[:n], float(channel.reverb_send))
                else:
                    self._reverb_send_buffer[:n] += src[:n] * float(channel.reverb_send)
            if getattr(channel, "delay_send", 0.0) > 0.0:
                src = (send_src_pre if bool(want_dly_pre) and send_src_pre is not None else send_src_post)
                if _have_numba():
                    _accumulate_send_nb(self._delay_send_buffer[:n], src[:n], float(getattr(channel, "delay_send", 0.0)))
                else:
                    self._delay_send_buffer[:n] += src[:n] * float(getattr(channel, "delay_send", 0.0))
            if getattr(channel, "distortion_send", 0.0) > 0.0:
                src = (send_src_pre if bool(want_dst_pre) and send_src_pre is not None else send_src_post)
                if _have_numba():
                    _accumulate_send_nb(self._distortion_send_buffer[:n], src[:n], float(getattr(channel, "distortion_send", 0.0)))
                else:
                    self._distortion_send_buffer[:n] += src[:n] * float(getattr(channel, "distortion_send", 0.0))

        # Bus meters (post-bus, pre-master) like DAW submix meters.
        try:
            if master_meter_needed:
                st = self._bus_meters.get("master")
                if st is None:
                    st = MeterState()
                    self._bus_meters["master"] = st
                if _have_numba():
                    rms, peak = _sum_bus_and_meters_nb(mixed_dry, True)
                else:
                    rms = float(np.sqrt(np.mean(mixed_dry * mixed_dry) + 1e-12))
                    peak = float(np.max(np.abs(mixed_dry)))
                rms_db = self._linear_to_db(rms)
                peak_db = self._linear_to_db(peak)
                a = 0.15
                st.rms_db = (1.0 - a) * float(st.rms_db) + a * float(rms_db)
                st.peak_db = max(float(st.peak_db) * 0.92, float(peak_db))
                if peak > 1.0:
                    st.clip_count = int(getattr(st, "clip_count", 0) or 0) + 1
                st.updated_at = float(time.time())
            for bus, buf in (bus_sums or {}).items():
                mixed_dry += buf
                st = self._bus_meters.get(str(bus))
                if st is None:
                    st = MeterState()
                    self._bus_meters[str(bus)] = st
                if _have_numba():
                    rms, peak = _sum_bus_and_meters_nb(buf, True)
                else:
                    rms = float(np.sqrt(np.mean(buf * buf) + 1e-12))
                    peak = float(np.max(np.abs(buf)))
                rms_db = self._linear_to_db(rms)
                peak_db = self._linear_to_db(peak)
                a = 0.15
                st.rms_db = (1.0 - a) * float(st.rms_db) + a * float(rms_db)
                st.peak_db = max(float(st.peak_db) * 0.92, float(peak_db))
                if peak > 1.0:
                    st.clip_count = int(getattr(st, "clip_count", 0) or 0) + 1
                st.updated_at = float(time.time())
        except Exception:
            pass

        rev = self._reverb_send_buffer[:max_len].copy()
        dly = self._delay_send_buffer[:max_len].copy()
        dst = self._distortion_send_buffer[:max_len].copy()
        return mixed_dry.copy(), rev, dly, dst

    def reset_all_filters(self):
        # Legacy hook used during some emotion transitions. Channel EQ/filter states
        # should reset, while delay buffers are intentionally preserved.
        for channel in self.channels:
            channel._eq.reset()
            channel._filter_bank.reset()
        return

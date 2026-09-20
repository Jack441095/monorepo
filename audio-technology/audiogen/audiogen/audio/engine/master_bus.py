# audio/engine/master_bus.py
# ---------------------------------------------------------------------------
# Master bus: sums the dry mix bus with *return tracks* (reverb, delay,
# distortion aux), then applies master fader, multiband + Fletcher–Munson EQ,
# limiter, and optional soft clip.
# Reverb/delay/distortion are fed from per-channel sends; delay is a shared
# return bus (DAW-style).
# ---------------------------------------------------------------------------
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from .lufs import RollingKWeightedLoudness
from .mixer import Distortion, Delay
from .multiband_adapter import MasterMultibandCompressor

try:
    import scipy.signal as _sp_signal  # type: ignore
except Exception:  # pragma: no cover
    _sp_signal = None

try:
    import numba as _nb
except Exception:
    _nb = None


def _have_numba() -> bool:
    return _nb is not None



@dataclass
class MasterBusSettings:
    limiter_enabled: bool = False
    limiter_threshold: float = 0.0
    limiter_lookahead_ms: float = 5.0
    limiter_release: float = 0.25
    soft_clip_enabled: bool = False
    soft_clip_drive: float = 0.95
    target_enabled: bool = False
    target_rms_db: float = -14.0
    target_max_change_db: float = 1.5
    target_ema_alpha: float = 0.25


def _rbj_peaking(freq_hz: float, q: float, gain_db: float, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    f0 = float(np.clip(float(freq_hz), 20.0, float(sample_rate) / 2.0 - 1.0))
    q = float(np.clip(float(q), 0.05, 12.0))
    a = float(10.0 ** (float(gain_db) / 40.0))
    w0 = 2.0 * np.pi * f0 / float(sample_rate)
    cos_w0 = float(np.cos(w0))
    sin_w0 = float(np.sin(w0))
    alpha = sin_w0 / (2.0 * q)

    b0 = 1.0 + alpha * a
    b1 = -2.0 * cos_w0
    b2 = 1.0 - alpha * a
    a0 = 1.0 + alpha / a
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha / a

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float32)
    aa = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float32)
    return b, aa


def _rbj_lowshelf(freq_hz: float, slope: float, gain_db: float, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    f0 = float(np.clip(float(freq_hz), 20.0, float(sample_rate) / 2.0 - 1.0))
    s = float(np.clip(float(slope), 0.1, 2.0))  # shelf slope (S)
    a = float(10.0 ** (float(gain_db) / 40.0))
    w0 = 2.0 * np.pi * f0 / float(sample_rate)
    cos_w0 = float(np.cos(w0))
    sin_w0 = float(np.sin(w0))
    alpha = (sin_w0 / 2.0) * float(np.sqrt((a + 1.0 / a) * (1.0 / s - 1.0) + 2.0))
    two_sqrt_a_alpha = 2.0 * float(np.sqrt(a)) * alpha

    b0 = a * ((a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = 2.0 * a * ((a - 1.0) - (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = -2.0 * ((a - 1.0) + (a + 1.0) * cos_w0)
    a2 = (a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float32)
    aa = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float32)
    return b, aa


def _rbj_highshelf(freq_hz: float, slope: float, gain_db: float, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    f0 = float(np.clip(float(freq_hz), 20.0, float(sample_rate) / 2.0 - 1.0))
    s = float(np.clip(float(slope), 0.1, 2.0))  # shelf slope (S)
    a = float(10.0 ** (float(gain_db) / 40.0))
    w0 = 2.0 * np.pi * f0 / float(sample_rate)
    cos_w0 = float(np.cos(w0))
    sin_w0 = float(np.sin(w0))
    alpha = (sin_w0 / 2.0) * float(np.sqrt((a + 1.0 / a) * (1.0 / s - 1.0) + 2.0))
    two_sqrt_a_alpha = 2.0 * float(np.sqrt(a)) * alpha

    b0 = a * ((a + 1.0) + (a - 1.0) * cos_w0 + two_sqrt_a_alpha)
    b1 = -2.0 * a * ((a - 1.0) + (a + 1.0) * cos_w0)
    b2 = a * ((a + 1.0) + (a - 1.0) * cos_w0 - two_sqrt_a_alpha)
    a0 = (a + 1.0) - (a - 1.0) * cos_w0 + two_sqrt_a_alpha
    a1 = 2.0 * ((a - 1.0) - (a + 1.0) * cos_w0)
    a2 = (a + 1.0) - (a - 1.0) * cos_w0 - two_sqrt_a_alpha

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float32)
    aa = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float32)
    return b, aa


def _fit_stereo_buffer(audio: np.ndarray, n: int) -> np.ndarray:
    """Return float32 stereo length ``n`` with minimal copying."""
    n = max(0, int(n))
    x = _stereo_float32(audio)
    ln = int(x.shape[0])
    if ln == n:
        return x
    if ln > n:
        return x[:n]
    out = np.zeros((n, 2), dtype=np.float32)
    if ln > 0:
        out[:ln] = x
    return out


def _stereo_float32(audio: np.ndarray) -> np.ndarray:
    x = np.asarray(audio, dtype=np.float32)
    if x.ndim == 1:
        x = np.column_stack([x, x])
    elif x.ndim != 2:
        raise ValueError(f"MasterBus expected 1D or 2D audio, got shape {x.shape}")
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    elif x.shape[1] > 2:
        x = x[:, :2].copy()
    return x


def _oversample_stereo(audio_stereo: np.ndarray, factor: int) -> np.ndarray:
    f = int(max(1, factor))
    x = _stereo_float32(audio_stereo)
    if f <= 1 or x.shape[0] <= 1:
        return x
    if _sp_signal is not None:
        y = _sp_signal.resample_poly(x, f, 1, axis=0, window=("kaiser", 8.6))
        return np.asarray(y, dtype=np.float32)
    n = x.shape[0]
    src = np.arange(n, dtype=np.float32)
    dst = np.linspace(0.0, float(n - 1), n * f, dtype=np.float32)
    out = np.empty((len(dst), 2), dtype=np.float32)
    out[:, 0] = np.interp(dst, src, x[:, 0]).astype(np.float32)
    out[:, 1] = np.interp(dst, src, x[:, 1]).astype(np.float32)
    return out


def _downsample_stereo(audio_stereo: np.ndarray, factor: int, target_len: int) -> np.ndarray:
    f = int(max(1, factor))
    x = _stereo_float32(audio_stereo)
    n = int(max(0, target_len))
    if n <= 0:
        return np.zeros((0, 2), dtype=np.float32)
    if f <= 1 or x.shape[0] <= 1:
        y = x
    elif _sp_signal is not None:
        y = _sp_signal.resample_poly(x, 1, f, axis=0, window=("kaiser", 8.6))
    else:
        y = x[::f]
    y = np.asarray(y, dtype=np.float32)
    if y.shape[0] > n:
        return y[:n]
    if y.shape[0] < n:
        padded = np.zeros((n, 2), dtype=np.float32)
        padded[: y.shape[0]] = y
        return padded
    return y


if _nb is not None:
    @_nb.njit(cache=True, fastmath=True)
    def _limiter_gain_nb(required_gain: np.ndarray, lookahead: int, release: float) -> np.ndarray:
        n = required_gain.shape[0]
        gain_raw = np.empty(n, dtype=np.float32)
        q = np.empty(n + lookahead, dtype=np.int32)
        head = 0
        tail = 0
        for i in range(n + lookahead - 1, -1, -1):
            val = required_gain[i] if i < n else 1.0
            while tail > head and (required_gain[q[tail - 1]] if q[tail - 1] < n else 1.0) >= val:
                tail -= 1
            q[tail] = i
            tail += 1
            while q[head] >= i + lookahead:
                head += 1
            if i < n:
                gain_raw[i] = required_gain[q[head]] if q[head] < n else 1.0

        smooth_gain = np.empty(n, dtype=np.float32)
        g = 1.0
        c = float(release)
        inv = 1.0 - c
        for i in range(n):
            gi = gain_raw[i]
            g = min(gi, c * g + inv * gi)
            smooth_gain[i] = g
        return smooth_gain


def lookahead_limiter_mono_gain(
    audio_stereo: np.ndarray,
    sample_rate: int,
    threshold: float,
    lookahead_ms: float,
    release: float,
) -> np.ndarray:
    n = audio_stereo.shape[0]
    if n == 0:
        return audio_stereo

    lookahead = max(2, int(lookahead_ms * 1e-3 * float(sample_rate)))
    envelope = np.max(np.abs(audio_stereo), axis=1).astype(np.float32, copy=False)
    required_gain = np.where(envelope > threshold, threshold / (envelope + 1e-8), 1.0).astype(
        np.float32, copy=False
    )

    if _have_numba():
        smooth_gain = _limiter_gain_nb(required_gain, lookahead, release)
    else:
        padded = np.concatenate([required_gain, np.ones(lookahead, dtype=np.float32)])
        windows = sliding_window_view(padded, lookahead)[:n]
        gain_raw = windows.min(axis=1).astype(np.float32, copy=False)

        smooth_gain = np.empty(n, dtype=np.float32)
        g = 1.0
        c = float(release)
        inv = 1.0 - c
        gr = gain_raw
        for i in range(n):
            gi = float(gr[i])
            g = min(gi, c * g + inv * gi)
            smooth_gain[i] = g

    return (audio_stereo * smooth_gain[:, np.newaxis]).astype(np.float32, copy=False)



def _distortion_wet_only(dist: Distortion, audio_in: np.ndarray) -> np.ndarray:
    prev = float(dist.mix)
    dist.mix = 1.0
    out = dist.process(audio_in)
    dist.mix = prev
    return out


def _delay_wet_only(delay: Delay, audio_in: np.ndarray) -> np.ndarray:
    # Aux-style: delay at 100% wet; return level controls amount into the master.
    prev = float(delay.mix)
    delay.mix = 1.0
    out = delay.process(audio_in)
    delay.mix = prev
    return out


class MasterBus:
    """
    Dry stem + reverb/delay/distortion returns → master fader → multiband + master EQ →
    limiter → (soft clip). Realtime ``fast_path`` still mixes reverb and delay returns.
    """

    def __init__(self, sample_rate: int, settings: Optional[MasterBusSettings] = None):
        self.sample_rate = int(sample_rate)
        self.settings = settings or MasterBusSettings()
        self.distortion = Distortion()
        self.delay = Delay(sample_rate=self.sample_rate)
        self.master_volume = 1.0
        self.master_output_trim_db = 0.0
        self.master_mute = False
        self.reverb_processor = None
        self.reverb_return_wet = 0.5
        self.delay_enabled = True
        self.delay_return_level = 0.32
        self.delay_time_ms = 320.0
        self.delay_feedback = 0.12

        self.distortion_return_level = 0.08
        # Sends are provided by the mixer (post-fader per-channel sends).
        self._event_bus = None
        self.master_eq_enabled: bool = False
        self._master_eq_bands: list[tuple[str, float, float, float]] = []
        self._master_eq_cache_key: Optional[tuple] = None
        self._master_eq_filters: list[tuple[np.ndarray, np.ndarray]] = []
        self._master_eq_zi: Optional[np.ndarray] = None
        self._master_eq_gain_scale: float = 1.0
        self._target_rms_ema_db: float = -120.0
        # Optional 3-band multiband compressor insert (post-fader, pre-limiter).
        self.multiband_enabled: bool = False
        self._multiband: Optional[MasterMultibandCompressor] = None
        # Optional realtime/offline split mastering profile.
        self.master_offline_quality_split_enabled: bool = False
        self.master_offline_multiband_mix: float = 0.72
        self.master_offline_makeup_db: float = 2.0
        self.master_offline_eq_gain_scale: float = 1.15
        self.master_realtime_multiband_mix: float = 0.52
        self.master_realtime_makeup_db: float = 1.10
        self.master_true_peak_enabled: bool = True
        self.master_true_peak_oversample_factor: int = 2
        self.master_true_peak_realtime_enabled: bool = False
        self.master_dither_enabled: bool = False
        self.master_dither_amount: float = 1e-5
        # Optional mid/side stereo width control (post-EQ, pre-target/limiter). New
        # 2026-07-04 (auto-mixer/DSP work) -- off by default since it's unvalidated
        # sonically; 1.0 = unity/no change.
        self.master_stereo_width_enabled: bool = False
        self.master_stereo_width: float = 1.0
        # Optional K-weighted (BS.1770-style) running loudness estimate feeding the
        # target-trim control loop below, instead of plain RMS. New 2026-07-04
        # (auto-mixer/DSP work, see audio/engine/lufs.py) -- a real loudness measurement
        # rather than plain signal RMS, so `master_target_rms_db` effectively becomes an
        # LUFS target (default -14.0, see core/config.py).
        self.master_target_use_k_weighting: bool = True
        self._k_loudness_meter: Optional["RollingKWeightedLoudness"] = None
        self._rt_stem_cap: int = 0
        self._rt_stem_buf = None
        self._rt_send_caps: dict[str, int] = {}
        self._rt_send_bufs: dict[str, np.ndarray] = {}

    def _borrow_stem(self, dry, n: int):
        n = max(0, int(n))
        import numpy as np
        x = _stereo_float32(dry)
        if n <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        cap = max(n, int(self._rt_stem_cap))
        if self._rt_stem_buf is None or int(self._rt_stem_buf.shape[0]) < cap:
            grow = max(cap, int(self._rt_stem_cap) * 2 if self._rt_stem_cap else cap)
            self._rt_stem_buf = np.empty((grow, 2), dtype=np.float32)
            self._rt_stem_cap = int(grow)
        stem = self._rt_stem_buf[:n]
        ln = min(int(x.shape[0]), n)
        if ln > 0:
            np.copyto(stem[:ln], x[:ln])
        if ln < n:
            stem[ln:n].fill(0.0)
        return stem

    def _borrow_send(self, send, n: int, *, key: str = "default"):
        n = max(0, int(n))
        import numpy as np
        if send is None or n <= 0:
            return np.zeros((n, 2), dtype=np.float32)
        x = _stereo_float32(send)
        buf_key = str(key or "default")
        current_cap = int(self._rt_send_caps.get(buf_key, 0) or 0)
        current = self._rt_send_bufs.get(buf_key)
        cap = max(n, current_cap)
        if current is None or int(current.shape[0]) < cap:
            grow = max(cap, current_cap * 2 if current_cap else cap)
            current = np.empty((grow, 2), dtype=np.float32)
            self._rt_send_bufs[buf_key] = current
            self._rt_send_caps[buf_key] = int(grow)
        out = current[:n]
        ln = min(int(x.shape[0]), n)
        if ln > 0:
            np.copyto(out[:ln], x[:ln])
        if ln < n:
            out[ln:n].fill(0.0)
        return out

    def warmup_realtime_path(self, *, n_samples: int = 512, reverb_processor=None, reverb_quality_tier: str = "safe"):
        import numpy as np
        n = max(64, int(n_samples))
        dry = np.zeros((n, 2), dtype=np.float32)
        send = np.full((n, 2), 1e-5, dtype=np.float32)
        try:
            self.process(
                dry,
                send,
                send,
                None,
                reverb_processor=reverb_processor,
                fast_path=True,
                skip_multiband=True,
                skip_master_eq=False,
                reverb_quality_tier=str(reverb_quality_tier or "safe"),
                realtime=True,
                reuse_rt_buffers=True,
            )
        except Exception:
            pass


    @staticmethod
    def _linear_to_db(x: float) -> float:
        return 20.0 * float(np.log10(max(1e-12, float(x))))

    @staticmethod
    def _db_to_linear(db: float) -> float:
        return 10.0 ** (float(db) / 20.0)

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = float(np.clip(volume, 0.0, 2.0))

    def set_master_mute(self, mute: bool) -> None:
        self.master_mute = bool(mute)

    def set_reverb_return_wet(self, wet: float) -> None:
        self.reverb_return_wet = float(np.clip(wet, 0.0, 1.0))

    def set_master_distortion(self, enabled: bool, drive: float, mix: float) -> None:
        self.distortion.enabled = bool(enabled)
        self.distortion.drive = max(1.0, float(drive))
        self.distortion_return_level = float(np.clip(mix, 0.0, 1.0))

    def attach_event_bus(self, event_bus) -> None:
        if self._event_bus is not None:
            return
        self._event_bus = event_bus
        event_bus.subscribe("set_master_volume", self._on_set_master_volume)
        event_bus.subscribe("set_master_mute", self._on_set_master_mute)
        event_bus.subscribe("set_master_reverb", self._on_set_master_reverb)

    def detach_event_bus(self) -> None:
        """Remove this bus from the shared EVENT_BUS (call when the player is torn down)."""
        if self._event_bus is None:
            return
        bus = self._event_bus
        bus.unsubscribe("set_master_volume", self._on_set_master_volume)
        bus.unsubscribe("set_master_mute", self._on_set_master_mute)
        bus.unsubscribe("set_master_reverb", self._on_set_master_reverb)
        self._event_bus = None

    def _on_set_master_volume(self, data):
        self.set_master_volume(data["volume"])

    def _on_set_master_mute(self, data):
        self.set_master_mute(data["mute"])

    def _on_set_master_reverb(self, data):
        self.set_reverb_return_wet(data["wet"])

    @classmethod
    def from_audio_config(cls, config: Any) -> MasterBus:
        audio = getattr(config, "audio", config)
        sr = int(getattr(audio, "sample_rate", 44100))
        settings = MasterBusSettings(
            limiter_enabled=getattr(audio, "master_limiter_enabled", True),
            limiter_threshold=float(getattr(audio, "master_limiter_threshold", 0.9)),
            limiter_lookahead_ms=float(getattr(audio, "master_limiter_lookahead_ms", 5.0)),
            limiter_release=float(getattr(audio, "master_limiter_release", 0.999)),
            soft_clip_enabled=getattr(audio, "master_soft_clip", False),
            soft_clip_drive=float(getattr(audio, "master_soft_clip_drive", 0.95)),
            target_enabled=bool(getattr(audio, "master_target_enabled", False)),
            target_rms_db=float(getattr(audio, "master_target_rms_db", -14.0)),
            target_max_change_db=float(getattr(audio, "master_target_max_change_db", 1.5)),
            target_ema_alpha=float(getattr(audio, "master_target_ema_alpha", 0.25)),
        )
        bus = cls(sr, settings)
        bus.configure_from_audio_config(config)
        return bus

    def configure_from_audio_config(self, config: Any) -> None:
        audio = getattr(config, "audio", config)
        self.sample_rate = int(getattr(audio, "sample_rate", self.sample_rate))
        self.delay.sample_rate = int(self.sample_rate)
        try:
            # Keep distortion tone filters stable when SR changes.
            if hasattr(self.distortion, "set_sample_rate"):
                self.distortion.set_sample_rate(int(self.sample_rate))
        except Exception:
            pass

        self.settings.limiter_enabled = getattr(audio, "master_limiter_enabled", True)
        self.settings.limiter_threshold = float(getattr(audio, "master_limiter_threshold", 0.9))
        self.settings.limiter_lookahead_ms = float(
            getattr(audio, "master_limiter_lookahead_ms", 5.0)
        )
        self.settings.limiter_release = float(getattr(audio, "master_limiter_release", 0.999))
        self.settings.soft_clip_enabled = getattr(audio, "master_soft_clip", False)
        self.settings.soft_clip_drive = float(getattr(audio, "master_soft_clip_drive", 0.95))
        self.settings.target_enabled = bool(getattr(audio, "master_target_enabled", False))
        self.settings.target_rms_db = float(getattr(audio, "master_target_rms_db", -18.0))
        self.settings.target_max_change_db = float(getattr(audio, "master_target_max_change_db", 1.5))
        self.settings.target_ema_alpha = float(getattr(audio, "master_target_ema_alpha", 0.25))

        self.set_master_volume(float(getattr(audio, "master_volume", 0.5)))
        try:
            self.master_output_trim_db = float(getattr(audio, "master_output_trim_db", 0.0) or 0.0)
        except Exception:
            self.master_output_trim_db = 0.0
        self.set_reverb_return_wet(float(getattr(audio, "reverb_wet", 0.5)))
        self.set_master_distortion(
            getattr(audio, "distortion_enabled", True),
            float(getattr(audio, "distortion_drive", 1.35)),
            float(getattr(audio, "distortion_mix", 0.08)),
        )

        # Send/return buses.
        self.delay_enabled = bool(getattr(audio, "delay_bus_enabled", True))
        self.delay_time_ms = float(getattr(audio, "delay_bus_time_ms", 320.0))
        self.delay_feedback = float(getattr(audio, "delay_bus_feedback", 0.12))
        self.delay_return_level = float(getattr(audio, "delay_bus_return_level", 0.32))
        try:
            if hasattr(self.delay, "set_pingpong"):
                self.delay.set_pingpong(float(getattr(audio, "delay_bus_pingpong", 0.0) or 0.0))
            if hasattr(self.delay, "set_feedback_tone"):
                self.delay.set_feedback_tone(
                    highpass_hz=float(getattr(audio, "delay_bus_feedback_highpass_hz", 0.0) or 0.0),
                    lowpass_hz=float(getattr(audio, "delay_bus_feedback_lowpass_hz", 0.0) or 0.0),
                    slope_db_per_oct=float(getattr(audio, "delay_bus_feedback_filter_slope_db_per_oct", 12.0) or 12.0),
                )
        except Exception:
            pass
        # Backwards compatibility: older configs used distortion_mix as the return level.
        self.distortion_return_level = float(
            getattr(audio, "distortion_bus_return_level", getattr(audio, "distortion_mix", self.distortion_return_level))
        )
        try:
            self.distortion.enabled = bool(getattr(audio, "distortion_bus_enabled", True)) and bool(
                getattr(audio, "distortion_enabled", True)
            )
        except Exception:
            pass
        try:
            if hasattr(self.distortion, "set_tone"):
                self.distortion.set_tone(
                    highpass_hz=float(getattr(audio, "distortion_tone_highpass_hz", 0.0) or 0.0),
                    lowpass_hz=float(getattr(audio, "distortion_tone_lowpass_hz", 0.0) or 0.0),
                    slope_db_per_oct=float(getattr(audio, "distortion_tone_slope_db_per_oct", 12.0) or 12.0),
                )
        except Exception:
            pass

        # Optional offline/realtime split mastering controls.
        try:
            self.master_offline_quality_split_enabled = bool(
                getattr(audio, "master_offline_quality_split_enabled", False)
            )
            self.master_offline_multiband_mix = float(
                getattr(audio, "master_offline_multiband_mix", 0.72)
            )
            self.master_offline_makeup_db = float(
                getattr(audio, "master_offline_makeup_db", 2.0)
            )
            self.master_offline_eq_gain_scale = float(
                getattr(audio, "master_offline_eq_gain_scale", 1.15)
            )
            self.master_realtime_multiband_mix = float(
                getattr(audio, "master_realtime_multiband_mix", 0.52)
            )
            self.master_realtime_makeup_db = float(
                getattr(audio, "master_realtime_makeup_db", 1.10)
            )
        except Exception:
            self.master_offline_quality_split_enabled = False

        try:
            self.master_true_peak_enabled = bool(getattr(audio, "master_true_peak_enabled", True))
            self.master_true_peak_oversample_factor = max(
                1, int(getattr(audio, "master_true_peak_oversample_factor", 2) or 2)
            )
            self.master_true_peak_realtime_enabled = bool(
                getattr(audio, "master_true_peak_realtime_enabled", False)
            )
        except Exception:
            self.master_true_peak_enabled = True
            self.master_true_peak_oversample_factor = 2
            self.master_true_peak_realtime_enabled = False
        try:
            self.master_dither_enabled = bool(getattr(audio, "master_dither_enabled", False))
            self.master_dither_amount = float(getattr(audio, "master_dither_amount", 1e-5) or 1e-5)
        except Exception:
            self.master_dither_enabled = False
            self.master_dither_amount = 1e-5

        try:
            self.master_stereo_width_enabled = bool(getattr(audio, "master_stereo_width_enabled", False))
            self.master_stereo_width = float(np.clip(getattr(audio, "master_stereo_width", 1.0) or 1.0, 0.0, 2.0))
        except Exception:
            self.master_stereo_width_enabled = False
            self.master_stereo_width = 1.0

        try:
            self.master_target_use_k_weighting = bool(
                getattr(audio, "master_target_use_k_weighting", True)
            )
        except Exception:
            self.master_target_use_k_weighting = True

        # Master multiband compressor (post-fader insert, pre-limiter).
        try:
            enabled_mb = bool(getattr(audio, "multiband_enabled", False))
            low_x = float(getattr(audio, "multiband_low_crossover_hz", 120.0))
            high_x = float(getattr(audio, "multiband_high_crossover_hz", 2500.0))
            # Clamp to sensible ranges and ordering.
            sr = max(8000.0, float(self.sample_rate))
            nyquist = sr * 0.5
            low_x = float(np.clip(low_x, 40.0, nyquist * 0.4))
            high_x = float(np.clip(high_x, low_x * 1.5, nyquist * 0.9))
            crossovers = [low_x, high_x]

            if enabled_mb:
                if self._multiband is None or int(self.sample_rate) != int(self._multiband.sample_rate):
                    self._multiband = MasterMultibandCompressor(
                        sample_rate=int(self.sample_rate),
                        crossover_frequencies=crossovers,
                    )

                mb = self._multiband
                if mb is not None:
                    # Build per-band parameter vectors (low, mid, high).
                    thr = [
                        float(getattr(audio, "multiband_low_threshold_db", -24.0)),
                        float(getattr(audio, "multiband_mid_threshold_db", -18.0)),
                        float(getattr(audio, "multiband_high_threshold_db", -20.0)),
                    ]
                    rat = [
                        float(getattr(audio, "multiband_low_ratio", 2.0)),
                        float(getattr(audio, "multiband_mid_ratio", 2.5)),
                        float(getattr(audio, "multiband_high_ratio", 2.0)),
                    ]
                    atk = [
                        float(getattr(audio, "multiband_low_attack_ms", 20.0)),
                        float(getattr(audio, "multiband_mid_attack_ms", 15.0)),
                        float(getattr(audio, "multiband_high_attack_ms", 8.0)),
                    ]
                    rel = [
                        float(getattr(audio, "multiband_low_release_ms", 220.0)),
                        float(getattr(audio, "multiband_mid_release_ms", 200.0)),
                        float(getattr(audio, "multiband_high_release_ms", 160.0)),
                    ]
                    knee = float(getattr(audio, "multiband_knee_width_db", 6.0))
                    # Per-band makeup: keep most gain in global makeup to stay gentle.
                    per_band_makeup = [0.0, 0.0, 0.0]
                    mb.update_compressors(
                        attack_ms=atk,
                        release_ms=rel,
                        threshold_db=thr,
                        ratio=rat,
                        makeup_gain_db=per_band_makeup,
                        knee_width_db=knee,
                    )
                    mix = float(getattr(audio, "multiband_mix", 0.6))
                    makeup_db = float(getattr(audio, "multiband_makeup_db", 1.5))
                    mb.set_mix_and_makeup(mix=mix, overall_makeup_db=makeup_db)
                    self.multiband_enabled = mb.enabled
                else:
                    self.multiband_enabled = False
            else:
                self.multiband_enabled = False
        except Exception:
            # Never allow multiband config issues to break audio.
            self.multiband_enabled = False

        # Master EQ (post-fader insert, pre-limiter).
        try:
            self.master_eq_enabled = bool(getattr(audio, "master_eq_enabled", False))
            bands: list[tuple[str, float, float, float]] = []
            for i in range(1, 5):
                b_type = str(getattr(audio, f"master_eq_band{i}_type", "") or "").strip().lower()
                freq = float(getattr(audio, f"master_eq_band{i}_freq_hz", 1000.0))
                gain = float(getattr(audio, f"master_eq_band{i}_gain_db", 0.0))
                q = float(getattr(audio, f"master_eq_band{i}_q", 1.0))
                if not b_type:
                    continue
                bands.append((b_type, freq, gain, q))
            self._master_eq_bands = bands
            # Force coeff refresh on next process call.
            self._master_eq_cache_key = None
        except Exception:
            self.master_eq_enabled = False
            self._master_eq_bands = []
            self._master_eq_cache_key = None
            self._master_eq_filters = []
            self._master_eq_zi = None

    def _apply_master_eq(self, audio_stereo: np.ndarray, *, gain_scale: float = 1.0) -> np.ndarray:
        if not bool(self.master_eq_enabled):
            return audio_stereo
        if _sp_signal is None:
            return audio_stereo
        bands = list(self._master_eq_bands or [])
        if not bands:
            return audio_stereo

        gs = float(max(0.5, min(2.0, float(gain_scale))))
        key = (int(self.sample_rate), float(gs), tuple((t, float(f), float(g), float(q)) for (t, f, g, q) in bands))
        if key != self._master_eq_cache_key:
            filters: list[tuple[np.ndarray, np.ndarray]] = []
            for (t, f, g, q) in bands:
                tt = str(t).lower()
                g_scaled = float(g) * float(gs)
                if tt in {"peak", "peaking", "bell"}:
                    b, a = _rbj_peaking(f, q, g_scaled, self.sample_rate)
                elif tt in {"low", "lowshelf", "low_shelf"}:
                    b, a = _rbj_lowshelf(f, q, g_scaled, self.sample_rate)
                elif tt in {"high", "highshelf", "high_shelf"}:
                    b, a = _rbj_highshelf(f, q, g_scaled, self.sample_rate)
                else:
                    continue
                filters.append((b, a))
            self._master_eq_filters = filters
            self._master_eq_zi = np.zeros((len(filters), 2, 2), dtype=np.float32)
            self._master_eq_cache_key = key

        filters = list(self._master_eq_filters or [])
        if not filters:
            return audio_stereo

        x = np.asarray(audio_stereo, dtype=np.float32)
        zi = self._master_eq_zi
        if zi is None or zi.shape != (len(filters), 2, 2):
            zi = np.zeros((len(filters), 2, 2), dtype=np.float32)
            self._master_eq_zi = zi

        y = x
        for bi, (b, a) in enumerate(filters):
            out = np.empty_like(y)
            for ch in range(2):
                out[:, ch], zf = _sp_signal.lfilter(b, a, y[:, ch], zi=zi[bi, ch])
                zi[bi, ch] = zf.astype(np.float32, copy=False)
            y = out
        return y.astype(np.float32, copy=False)

    def process(
        self,
        dry: np.ndarray,
        reverb_send: Optional[np.ndarray] = None,
        delay_send: Optional[np.ndarray] = None,
        distortion_send: Optional[np.ndarray] = None,
        reverb_processor: Any = None,
        *,
        fast_path: bool = False,
        skip_inserts: bool = False,
        skip_multiband: Optional[bool] = None,
        skip_master_eq: Optional[bool] = None,
        fx_return_scale: float = 1.0,
        reverb_quality_tier: str = "high",
        realtime: bool = False,
        reuse_rt_buffers: bool = False,
    ) -> np.ndarray:
        dry = _stereo_float32(dry)
        n = dry.shape[0]
        if n == 0:
            return np.zeros((0, 2), dtype=np.float32)

        if skip_multiband is None:
            skip_multiband = bool(skip_inserts)
        if skip_master_eq is None:
            skip_master_eq = bool(skip_inserts)

        # RT "fast_path" still runs reverb + delay (core spatial mix). It skips distortion
        # aux and the lookahead limiter / soft-clip tail to save CPU when under stress.
        if bool(reuse_rt_buffers) or bool(realtime):
            stem = self._borrow_stem(dry, n)
        else:
            stem = np.array(dry, dtype=np.float32, copy=True)
        fx_scale = float(np.clip(float(fx_return_scale), 0.0, 1.0))

        rev_proc = reverb_processor if reverb_processor is not None else self.reverb_processor
        rev_wet = float(self.reverb_return_wet) * fx_scale
        if (
            rev_proc is not None
            and rev_wet > 1e-9
            and reverb_send is not None
        ):
            rs = self._borrow_send(reverb_send, n, key="reverb") if (bool(reuse_rt_buffers) or bool(realtime)) else _fit_stereo_buffer(reverb_send, n)
            if np.any(np.abs(rs) > 1e-9):
                try:
                    wet = rev_proc.process(
                        rs,
                        wet=rev_wet,
                        quality_tier=str(reverb_quality_tier or "high"),
                    )
                except TypeError:
                    wet = rev_proc.process(rs, wet=rev_wet)
                wet = _stereo_float32(wet)
                ln = min(int(wet.shape[0]), n)
                if ln > 0:
                    np.add(stem[:ln], wet[:ln], out=stem[:ln])

        # Delay return (shared bus).
        dly_lvl = float(self.delay_return_level) * fx_scale
        if (
            bool(self.delay_enabled)
            and dly_lvl > 1e-9
            and delay_send is not None
        ):
            ds = self._borrow_send(delay_send, n, key="delay") if (bool(reuse_rt_buffers) or bool(realtime)) else _fit_stereo_buffer(delay_send, n)
            if np.any(np.abs(ds) > 1e-9):
                try:
                    self.delay.enabled = True
                    self.delay.set_time_ms(float(self.delay_time_ms))
                    self.delay.set_feedback(float(np.clip(self.delay_feedback, 0.0, 0.99)))
                    self.delay.set_mix(1.0)
                except Exception:
                    pass
                dly_wet = _delay_wet_only(self.delay, ds)
                stem += dly_wet * np.float32(dly_lvl)

        # Distortion return (parallel aux)
        if (
            not bool(fast_path)
            and self.distortion.enabled
            and self.distortion_return_level > 0.0
            and distortion_send is not None
        ):
            ds2 = self._borrow_send(distortion_send, n, key="distortion") if (bool(reuse_rt_buffers) or bool(realtime)) else _fit_stereo_buffer(distortion_send, n)
            if np.any(np.abs(ds2) > 1e-9):
                stem += _distortion_wet_only(self.distortion, ds2) * np.float32(
                    float(self.distortion_return_level) * fx_scale
                )

        gain = 0.0 if self.master_mute else float(self.master_volume)
        stem *= np.float32(gain)

        # DAW-like master output trim (post-returns, pre-inserts/limiter).
        try:
            trim_db = float(getattr(self, "master_output_trim_db", 0.0) or 0.0)
        except Exception:
            trim_db = 0.0
        if abs(float(trim_db)) > 1e-6:
            stem *= np.float32(self._db_to_linear(float(trim_db)))

        if (
            not bool(fast_path)
            and bool(self.master_offline_quality_split_enabled)
            and self._multiband is not None
        ):
            try:
                if bool(fast_path):
                    mb_mix = float(self.master_realtime_multiband_mix)
                    mb_makeup = float(self.master_realtime_makeup_db)
                    self._master_eq_gain_scale = 1.0
                else:
                    mb_mix = float(self.master_offline_multiband_mix)
                    mb_makeup = float(self.master_offline_makeup_db)
                    self._master_eq_gain_scale = float(self.master_offline_eq_gain_scale)
                self._multiband.set_mix_and_makeup(
                    mix=float(np.clip(mb_mix, 0.0, 1.0)),
                    overall_makeup_db=float(np.clip(mb_makeup, -6.0, 9.0)),
                )
            except Exception:
                pass
        else:
            self._master_eq_gain_scale = 1.0

        # Optional multiband compressor insert (post-fader, pre-EQ/limiter).
        if (
            not bool(skip_multiband)
            and bool(self.multiband_enabled)
            and self._multiband is not None
        ):
            try:
                stem = self._multiband.process(stem)
            except Exception:
                # If multiband misbehaves, bypass it but keep audio flowing.
                self.multiband_enabled = False

        # Master EQ insert (Fletcher–Munson-ish curve; post-multiband, pre-limiter).
        if not bool(skip_master_eq):
            try:
                stem = self._apply_master_eq(stem, gain_scale=float(self._master_eq_gain_scale))
            except Exception:
                pass

        # Optional mid/side stereo width (post-EQ, pre-target/limiter so the limiter sees
        # the final stereo image).
        if not bool(fast_path) and bool(self.master_stereo_width_enabled):
            try:
                width = float(self.master_stereo_width)
                if abs(width - 1.0) > 1e-6:
                    mid = (stem[:, 0] + stem[:, 1]) * np.float32(0.5)
                    side = (stem[:, 0] - stem[:, 1]) * np.float32(0.5) * np.float32(width)
                    stem = np.stack([mid + side, mid - side], axis=1).astype(np.float32, copy=False)
            except Exception:
                pass

        s = self.settings
        # Optional master target trim (post fader+inserts, pre limiter). When
        # `master_target_use_k_weighting` is on, the loudness measurement is a running
        # BS.1770 K-weighted estimate (see audio/engine/lufs.py) instead of plain RMS, so
        # `target_rms_db` is effectively an LUFS target (default -14.0). True BS.1770
        # *integrated* loudness needs a whole finished program (gating requires complete
        # block history), which doesn't apply to endless generative playback -- this running
        # estimate is the realtime-tractable equivalent (same EMA+clamp control loop either way).
        if bool(s.target_enabled) and not bool(fast_path):
            try:
                if bool(self.master_target_use_k_weighting):
                    # The meter already carries its own EMA state, so its output IS the
                    # smoothed measurement -- no extra smoothing layered on top.
                    if self._k_loudness_meter is None or self._k_loudness_meter.sample_rate != int(self.sample_rate):
                        self._k_loudness_meter = RollingKWeightedLoudness(
                            int(self.sample_rate), ema_alpha=float(s.target_ema_alpha)
                        )
                    loudness_db = float(self._k_loudness_meter.process(stem))
                    if np.isfinite(loudness_db):
                        self._target_rms_ema_db = loudness_db
                        have_measurement = True
                    else:
                        have_measurement = False
                else:
                    rms = float(np.sqrt(float(np.mean(stem * stem)) + 1e-12))
                    have_measurement = rms > 1e-9
                    if have_measurement:
                        rms_db = self._linear_to_db(rms)
                        a = float(np.clip(float(s.target_ema_alpha), 0.01, 0.95))
                        self._target_rms_ema_db = (1.0 - a) * float(self._target_rms_ema_db) + a * float(rms_db)

                if have_measurement:
                    desired_db = float(s.target_rms_db) - float(self._target_rms_ema_db)
                    md = abs(float(s.target_max_change_db))
                    desired_db = float(np.clip(desired_db, -md, md))
                    stem *= np.float32(self._db_to_linear(desired_db))
            except Exception:
                pass

        if not bool(fast_path) and s.limiter_enabled:
            os_factor = 1
            try:
                true_peak_enabled = bool(getattr(self, "master_true_peak_enabled", True))
                if bool(realtime) and not bool(getattr(self, "master_true_peak_realtime_enabled", False)):
                    true_peak_enabled = False
                if true_peak_enabled:
                    os_factor = max(1, int(getattr(self, "master_true_peak_oversample_factor", 2) or 2))
            except Exception:
                os_factor = 1
            if os_factor > 1:
                stem_os = _oversample_stereo(stem, os_factor)
                stem_os = lookahead_limiter_mono_gain(
                    stem_os,
                    int(self.sample_rate) * int(os_factor),
                    threshold=s.limiter_threshold,
                    lookahead_ms=s.limiter_lookahead_ms,
                    release=s.limiter_release,
                )
                stem = _downsample_stereo(stem_os, os_factor, n)
            else:
                stem = lookahead_limiter_mono_gain(
                    stem,
                    self.sample_rate,
                    threshold=s.limiter_threshold,
                    lookahead_ms=s.limiter_lookahead_ms,
                    release=s.limiter_release,
                )

        if not bool(fast_path) and s.soft_clip_enabled:
            d = float(s.soft_clip_drive)
            stem = np.tanh(stem * d).astype(np.float32, copy=False)

        if not bool(fast_path) and bool(getattr(self, "master_dither_enabled", False)):
            amt = abs(float(getattr(self, "master_dither_amount", 0.0) or 0.0))
            if amt > 0.0:
                r0 = np.random.random(stem.shape).astype(np.float32)
                r1 = np.random.random(stem.shape).astype(np.float32)
                stem = (stem + (r0 - r1) * np.float32(amt)).astype(np.float32, copy=False)

        return stem

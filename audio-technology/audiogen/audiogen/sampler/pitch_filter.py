# pitch_filter.py

import numpy as np
import scipy.signal

from .utils import midi_to_frequency

# Try to use Numba; fall back to pure Python (matches sampler/utils.py's convention).
try:
    from numba import njit

    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False


# 2026-07-03 (docs/AUDIOGEN_COMPOSITION_PLAN.md latency investigation): `DynamicLowPass.
# process` below used a pure-Python per-sample loop -- profiling a full song render showed
# it responsible for 70% of total render time (10.15s of 14.5s for one song), because a
# one-pole filter with a time-varying coefficient is inherently sequential (each output
# sample depends on the previous one) and can't be vectorized with plain numpy ufuncs. At
# 44.1kHz, a single 1-second note means 44,100+ Python-level loop iterations. JIT-compiling
# the identical recursive math with numba (already a real dependency, used the same way in
# `sampler/utils.py`) removes the interpreter overhead without changing the numerics.
if NUMBA_AVAILABLE:

    @njit(cache=True)
    def _dynamic_lowpass_mono(audio: np.ndarray, coeffs: np.ndarray, state0: float) -> np.ndarray:
        out = np.empty_like(audio)
        state = state0
        for i in range(len(audio)):
            state = coeffs[i] * audio[i] + (1.0 - coeffs[i]) * state
            out[i] = state
        return out

    @njit(cache=True)
    def _dynamic_lowpass_stereo(
        audio: np.ndarray, coeffs: np.ndarray, state_l0: float, state_r0: float
    ) -> np.ndarray:
        out = np.empty_like(audio)
        state_l = state_l0
        state_r = state_r0
        for i in range(len(audio)):
            state_l = coeffs[i] * audio[i, 0] + (1.0 - coeffs[i]) * state_l
            state_r = coeffs[i] * audio[i, 1] + (1.0 - coeffs[i]) * state_r
            out[i, 0] = state_l
            out[i, 1] = state_r
        return out


class PitchTrackingFilter:
    """Dynamic filter that tracks the pitch of a note, with selectable filter type and order."""

    def __init__(self, sample_rate: int = 44100, order: int = 2):
        self.sample_rate = sample_rate
        self.order = order
        self.prev_cutoff = -1.0
        self.prev_filter_type = None
        self.sos_coeffs = None
        self.filter_state = None
        # CPU-friendly cache: precomputed SOS + zi per MIDI note for a given settings tuple.
        # Key: (order, filter_type, harmonic_multiplier, min_cutoff, max_cutoff)
        self._midi_cache = {}

    def reset_state(self):
        self.filter_state = None

    def calculate_cutoff(
        self,
        midi_note: int,
        harmonic_multiplier: float = 6.0,
        min_cutoff: float = 100.0,
        max_cutoff: float = 8000.0,
    ) -> float:
        # Map note pitch -> cutoff in a musically smooth way.
        # We track pitch in Hz (f_note * harmonic_multiplier) but blend in log-frequency space
        # so the perceived brightness ramps more like a sampler's keytracking.
        f_note = float(midi_to_frequency(int(midi_note)))
        target = float(
            np.clip(
                f_note * float(harmonic_multiplier), float(min_cutoff), float(max_cutoff)
            )
        )
        lo = float(max(20.0, float(min_cutoff)))
        hi = float(max(lo + 1.0, float(max_cutoff)))
        target = float(np.clip(target, lo, hi))
        # Blend between min_cutoff and target in log domain (equivalent to "expo" keytracking feel).
        # (Amount is implicitly 1.0 for now; harmonic_multiplier + clamps shape the curve.)
        return float(np.exp(np.log(lo) * 0.15 + np.log(target) * 0.85))

    def _get_cached_sos_and_zi(
        self,
        *,
        filter_type: str,
        harmonic_multiplier: float,
        min_cutoff: float,
        max_cutoff: float,
    ):
        key = (
            int(self.order),
            str(filter_type),
            float(harmonic_multiplier),
            float(min_cutoff),
            float(max_cutoff),
        )
        cached = self._midi_cache.get(key)
        if cached is not None:
            return cached

        nyq = float(self.sample_rate) / 2.0
        sos_by_midi = []
        zi_by_midi = []
        for midi in range(128):
            cutoff = self.calculate_cutoff(midi, harmonic_multiplier, min_cutoff, max_cutoff)
            nc = float(cutoff) / nyq
            if nc <= 0.0 or nc >= 1.0:
                sos = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
            else:
                if filter_type == "lowpass":
                    sos = scipy.signal.butter(self.order, nc, btype="low", output="sos").astype(
                        np.float32
                    )
                elif filter_type == "highpass":
                    sos = scipy.signal.butter(
                        self.order, nc, btype="high", output="sos"
                    ).astype(np.float32)
                else:
                    sos = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
            sos_by_midi.append(sos)
            zi_by_midi.append(scipy.signal.sosfilt_zi(sos).astype(np.float32))

        self._midi_cache[key] = (sos_by_midi, zi_by_midi)
        return self._midi_cache[key]

    def update_coeffs(self, cutoff: float, filter_type: str = "lowpass"):
        """Update filter coefficients if cutoff or type changed."""
        if (
            abs(cutoff - self.prev_cutoff) < 0.1
            and filter_type == self.prev_filter_type
            and self.sos_coeffs is not None
        ):
            return
        self.prev_cutoff = cutoff
        self.prev_filter_type = filter_type
        nyq = self.sample_rate / 2.0
        nc = cutoff / nyq
        if nc <= 0.0 or nc >= 1.0:
            # No filtering (passthrough)
            self.sos_coeffs = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        else:
            # Design Butterworth filter with self.order
            if filter_type == "lowpass":
                self.sos_coeffs = scipy.signal.butter(
                    self.order, nc, btype="low", output="sos"
                ).astype(np.float32)
            elif filter_type == "highpass":
                self.sos_coeffs = scipy.signal.butter(
                    self.order, nc, btype="high", output="sos"
                ).astype(np.float32)
            else:
                self.sos_coeffs = np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float32)
        self.filter_state = None

    def apply(
        self,
        audio: np.ndarray,
        midi_note: int,
        harmonic_multiplier: float = 6.0,
        min_cutoff: float = 100.0,
        max_cutoff: float = 3000.0,
        override_cutoff: float = None,
        filter_type: str = "lowpass",
    ) -> np.ndarray:
        """
        Apply the filter to audio.
        filter_type can be 'lowpass', 'highpass', 'bandpass' (bandpass not fully implemented yet).
        """
        if len(audio) == 0:
            return audio
        if override_cutoff is not None:
            cutoff = float(np.clip(override_cutoff, 20.0, self.sample_rate / 2.0 - 1.0))
            self.update_coeffs(cutoff, filter_type)
            sos = self.sos_coeffs
            if sos is None:
                return audio
            zi0 = scipy.signal.sosfilt_zi(sos).astype(np.float32)
        else:
            sos_by_midi, zi_by_midi = self._get_cached_sos_and_zi(
                filter_type=str(filter_type),
                harmonic_multiplier=float(harmonic_multiplier),
                min_cutoff=float(min_cutoff),
                max_cutoff=float(max_cutoff),
            )
            midi_i = int(np.clip(int(midi_note), 0, 127))
            sos = sos_by_midi[midi_i]
            zi0 = zi_by_midi[midi_i]

        # Fresh initial state per call. Sampler.render_note() calls reset_state() before apply().
        if audio.ndim == 1:
            filtered, zf = scipy.signal.sosfilt(sos, audio, zi=zi0)
            self.filter_state = zf
            return filtered.astype(np.float32)

        filtered = np.zeros_like(audio)
        filt_state = np.stack([zi0.copy()] * audio.shape[1], axis=-1)
        for ch in range(audio.shape[1]):
            filtered[:, ch], filt_state[..., ch] = scipy.signal.sosfilt(
                sos, audio[:, ch], zi=filt_state[..., ch]
            )
        self.filter_state = filt_state
        return filtered.astype(np.float32)


class DynamicLowPass:
    """
    One‑pole low‑pass filter with time‑varying cutoff.
    Efficient: cutoff updated per sample with small cost.
    """

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.state = 0.0  # left channel state
        self.state_r = 0.0  # right channel state
        self._coeff = None

    def set_cutoff(self, cutoff_hz: float):
        """Set filter coefficient based on cutoff frequency."""
        if cutoff_hz <= 0:
            self._coeff = 0.0
            return
        alpha = np.exp(-2.0 * np.pi * cutoff_hz / self.sample_rate)
        self._coeff = 1.0 - alpha

    def _compute_coeff_envelope(self, cutoff_envelope: np.ndarray) -> np.ndarray:
        cutoff = np.maximum(cutoff_envelope.astype(np.float32, copy=False), 0.0)
        return (1.0 - np.exp(-2.0 * np.pi * cutoff / self.sample_rate)).astype(np.float32)

    def reset_state(self):
        self.state = 0.0
        self.state_r = 0.0

    def process(self, audio: np.ndarray, cutoff_envelope: np.ndarray) -> np.ndarray:
        """
        Apply filter with cutoff varying per sample.
        cutoff_envelope: array of cutoff frequencies (Hz) same length as audio.
        """
        if len(audio) == 0:
            return audio
        if self._coeff is None:
            self.set_cutoff(20000.0)  # default almost open

        coeffs = self._compute_coeff_envelope(cutoff_envelope)
        if NUMBA_AVAILABLE:
            if audio.ndim == 1:
                out = _dynamic_lowpass_mono(audio, coeffs, float(self.state))
                self.state = float(out[-1])
            else:
                out = _dynamic_lowpass_stereo(audio, coeffs, float(self.state), float(self.state_r))
                self.state = float(out[-1, 0])
                self.state_r = float(out[-1, 1])
            return out

        out = np.empty_like(audio)
        if audio.ndim == 1:
            state = self.state
            for i, (sample, alpha) in enumerate(zip(audio, coeffs)):
                state = alpha * sample + (1.0 - alpha) * state
                out[i] = state
            self.state = state
        else:
            # Stereo
            state_l = self.state
            state_r = self.state_r
            for i, (s_l, s_r, alpha) in enumerate(zip(audio[:, 0], audio[:, 1], coeffs)):
                state_l = alpha * s_l + (1.0 - alpha) * state_l
                state_r = alpha * s_r + (1.0 - alpha) * state_r
                out[i, 0] = state_l
                out[i, 1] = state_r
            self.state = state_l
            self.state_r = state_r
        return out


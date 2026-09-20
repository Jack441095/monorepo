import numpy as np
import scipy.signal

from .utils import midi_to_frequency


def _rbj_lowpass(cutoff_hz: float, q: float, sample_rate: int) -> tuple[np.ndarray, np.ndarray]:
    cutoff_hz = float(np.clip(cutoff_hz, 20.0, sample_rate / 2.0 - 1.0))
    q = float(max(0.05, q))
    w0 = 2.0 * np.pi * cutoff_hz / float(sample_rate)
    cos_w0 = float(np.cos(w0))
    sin_w0 = float(np.sin(w0))
    alpha = sin_w0 / (2.0 * q)

    b0 = (1.0 - cos_w0) / 2.0
    b1 = 1.0 - cos_w0
    b2 = (1.0 - cos_w0) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_w0
    a2 = 1.0 - alpha

    b = np.array([b0 / a0, b1 / a0, b2 / a0], dtype=np.float32)
    a = np.array([1.0, a1 / a0, a2 / a0], dtype=np.float32)
    return b, a


class KeyTrackedBiquadLPF:
    """
    Very lightweight resonant lowpass for sampler playback (Simpler-ish).
    Uses RBJ biquad coefficients and scipy.signal.lfilter for C-speed processing.
    Coeffs are cached per (midi, harmonic_multiplier, min/max, q, vel_bin).
    """

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = int(sample_rate)
        self._cache: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}

    def cutoff_for_note(
        self,
        midi_note: int,
        *,
        harmonic_multiplier: float,
        min_cutoff: float,
        max_cutoff: float,
        vel_to_cutoff: float,
        velocity: int,
        vel_bins: int = 12,
    ) -> float:
        f_note = float(midi_to_frequency(int(midi_note)))
        base = float(
            np.clip(
                f_note * float(harmonic_multiplier),
                float(min_cutoff),
                float(max_cutoff),
            )
        )
        lo = float(max(20.0, float(min_cutoff)))
        hi = float(max(lo + 1.0, float(max_cutoff)))
        base = float(np.clip(base, lo, hi))

        v = float(np.clip(int(velocity) / 127.0, 0.0, 1.0))
        amt = float(np.clip(float(vel_to_cutoff), 0.0, 1.0))
        # Velocity opens the filter by up to ~1 octave at amt=1.0 (tapered).
        octaves = 1.0 * amt
        factor = 2.0 ** ((v - 0.5) * 2.0 * octaves)
        cutoff = float(np.clip(base * factor, lo, hi))
        # mild log smoothing toward lo for stability
        cutoff = float(np.exp(np.log(lo) * 0.10 + np.log(cutoff) * 0.90))
        return cutoff

    def _get_ba(
        self,
        *,
        midi_note: int,
        harmonic_multiplier: float,
        min_cutoff: float,
        max_cutoff: float,
        q: float,
        vel_to_cutoff: float,
        velocity: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        # Quantize velocity so caching stays effective but still expressive.
        vel_bins = 12
        vb = int(
            np.clip(
                int(round((int(velocity) / 127.0) * (vel_bins - 1))),
                0,
                vel_bins - 1,
            )
        )
        key = (
            int(midi_note),
            float(harmonic_multiplier),
            float(min_cutoff),
            float(max_cutoff),
            float(q),
            float(vel_to_cutoff),
            int(vb),
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        vel_mid = int(round((vb / max(1, vel_bins - 1)) * 127))
        cutoff = self.cutoff_for_note(
            int(midi_note),
            harmonic_multiplier=float(harmonic_multiplier),
            min_cutoff=float(min_cutoff),
            max_cutoff=float(max_cutoff),
            vel_to_cutoff=float(vel_to_cutoff),
            velocity=int(vel_mid),
            vel_bins=vel_bins,
        )
        b, a = _rbj_lowpass(cutoff, float(q), self.sample_rate)
        self._cache[key] = (b, a)
        return b, a

    def apply(
        self,
        audio: np.ndarray,
        midi_note: int,
        *,
        velocity: int,
        harmonic_multiplier: float,
        min_cutoff: float,
        max_cutoff: float,
        q: float,
        vel_to_cutoff: float,
        drive: float = 0.0,
    ) -> np.ndarray:
        if audio is None or len(audio) == 0:
            return audio

        x = np.asarray(audio, dtype=np.float32)
        d = float(np.clip(float(drive), 0.0, 0.35))
        if d > 0.0:
            # tiny pre-drive to add presence before filtering
            x = np.tanh(x * (1.0 + 6.0 * d)).astype(np.float32)

        b, a = self._get_ba(
            midi_note=int(midi_note),
            harmonic_multiplier=float(harmonic_multiplier),
            min_cutoff=float(min_cutoff),
            max_cutoff=float(max_cutoff),
            q=float(q),
            vel_to_cutoff=float(vel_to_cutoff),
            velocity=int(velocity),
        )
        if x.ndim == 1:
            return scipy.signal.lfilter(b, a, x).astype(np.float32)
        y = np.empty_like(x)
        for ch in range(x.shape[1]):
            y[:, ch] = scipy.signal.lfilter(b, a, x[:, ch]).astype(np.float32)
        return y


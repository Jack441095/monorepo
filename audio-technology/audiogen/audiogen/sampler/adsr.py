# adsr.py
import numpy as np


class ADSREnvelope:

    def __init__(
        self,
        attack: float,
        decay: float,
        sustain: float,
        release: float,
        sample_rate: int = 44100,
        curve: str = "linear",
    ):
        self.attack_samples = max(1, int(attack * sample_rate))
        self.decay_samples = max(1, int(decay * sample_rate))
        self.sustain_level = np.clip(sustain, 0.0, 1.0)
        self.release_samples = max(1, int(release * sample_rate))
        self.sample_rate = sample_rate
        self.curve = curve

    def _exponential_curve(
        self, length: int, start: float, end: float, rate: float = 8.0
    ) -> np.ndarray:
        t = np.linspace(0, 1, length)
        # exponential mapping: 1 - e^{-rate*t}
        curve = 1.0 - np.exp(-rate * t)
        # normalize to start->end range
        return start + (end - start) * curve

    def _release_curve(self, length: int, start: float) -> np.ndarray:
        if length <= 0:
            return np.zeros(0, dtype=np.float32)
        if self.curve == "exponential":
            return self._exponential_curve(length, start, 0.0, rate=6.0).astype(
                np.float32
            )
        return np.linspace(start, 0.0, length, dtype=np.float32)

    def apply(self, audio: np.ndarray, release_after: int = None) -> np.ndarray:
        total = len(audio)
        env = np.ones(total, dtype=np.float32)

        # Attack
        a_len = min(self.attack_samples, total)
        if a_len > 0:
            if self.curve == "exponential":
                env[:a_len] = self._exponential_curve(a_len, 0.0, 1.0, rate=8.0)
            else:
                env[:a_len] = np.linspace(0.0, 1.0, a_len, dtype=np.float32)

        # Decay
        d_start = a_len
        d_len = min(self.decay_samples, total - d_start)
        if d_len > 0:
            if self.curve == "exponential":
                env[d_start : d_start + d_len] = self._exponential_curve(
                    d_len, 1.0, self.sustain_level, rate=5.0
                )
            else:
                env[d_start : d_start + d_len] = np.linspace(
                    1.0, self.sustain_level, d_len, dtype=np.float32
                )

        # Sustain
        s_start = d_start + d_len
        if release_after is None:
            env[s_start:] = self.sustain_level
        else:
            release_start = min(release_after, total)
            env[s_start:] = self.sustain_level

            if s_start < release_start:
                env[s_start:release_start] = self.sustain_level

            r_len = min(self.release_samples, total - release_start)
            if r_len > 0:
                if release_start > 0:
                    release_level = float(env[release_start - 1])
                else:
                    release_level = float(env[0]) if total > 0 else self.sustain_level
                env[release_start : release_start + r_len] = self._release_curve(
                    r_len, release_level
                )
                env[release_start + r_len :] = 0.0

        # Apply envelope (supports mono and stereo)
        if audio.ndim == 1:
            return audio * env
        else:
            return (audio.T * env).T


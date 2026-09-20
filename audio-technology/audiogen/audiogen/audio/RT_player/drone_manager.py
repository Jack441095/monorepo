# audio/RT_player/drone_manager.py
# Project module `drone_manager` (audio).

# /drone_manager.py
import numpy as np

class DroneManager:
    """
    Manages a continuous drone loop (full sample, with crossfade at wrap).
    """
    def __init__(self, drone_loop: np.ndarray, sample_rate: int, volume: float = 0.4):
        self.drone_loop = drone_loop
        self.sample_rate = sample_rate
        self.volume = volume
        self.pos = 0
        # crossfade length: 10 ms
        self.crossfade_len = min(int(0.01 * sample_rate), len(drone_loop) // 10)

    def get_slice(self, num_samples: int) -> np.ndarray:
        """Return the next `num_samples` of drone audio, wrapping with crossfade."""
        start = self.pos
        end = start + num_samples
        loop_len = len(self.drone_loop)
        if end <= loop_len:
            audio = self.drone_loop[start:end]
        else:
            first_part = self.drone_loop[start:].copy()
            second_part = self.drone_loop[:end - loop_len].copy()
            crossfade_len = min(self.crossfade_len, len(first_part), len(second_part))
            if crossfade_len > 0:
                fade_out = np.linspace(1, 0, crossfade_len)[:, np.newaxis]
                fade_in = np.linspace(0, 1, crossfade_len)[:, np.newaxis]
                first_part[-crossfade_len:] *= fade_out
                second_part[:crossfade_len] *= fade_in
            audio = np.concatenate([first_part, second_part])
        self.pos = end % loop_len
        # ensure stereo (copy before scale — views into drone_loop must not be written in place)
        if audio.ndim == 1:
            audio = np.column_stack([audio, audio])
        else:
            audio = np.asarray(audio, dtype=np.float32, order="C")
        audio = (audio * float(self.volume)).astype(np.float32, copy=True)
        # pad if shorter (should not happen)
        if len(audio) < num_samples:
            pad = num_samples - len(audio)
            audio = np.concatenate([audio, np.zeros((pad, 2), dtype=np.float32)])
        return audio[:num_samples]

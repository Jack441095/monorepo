# audio/RT_player/buffer_controller.py
# Project module `buffer_controller` (audio).

import math
import threading
import time
import numpy as np

from typing import Optional

from .ring_buffer import RingBuffer

class PlaybackBufferController:
    """Owns the chunk queue, active playback slice, and adaptive buffer sizing."""

    def __init__(self, capacity: int, telemetry):
        self.buffer = RingBuffer(capacity=capacity)
        self.telemetry = telemetry
        self._playback_lock = threading.Lock()
        self._active_chunk = None
        self._active_chunk_offset = 0
        self._underrun_backoff_bars = 0
        self._last_underrun_time = 0.0
        # Cap backoff so repeated underruns don't spiral targets into the hundreds of bars.
        # (Large targets can make recovery slower without actually preventing underruns.)
        self._underrun_backoff_cap = max(6, min(24, capacity // 8))

    @property
    def capacity(self) -> int:
        return self.buffer.capacity

    def __len__(self) -> int:
        return len(self.buffer)

    def queued_fill_bars(self) -> int:
        return len(self.buffer)

    def effective_fill_bars(self) -> int:
        with self._playback_lock:
            active = 1 if self._active_chunk is not None else 0
        return len(self.buffer) + active

    def write(self, chunk) -> bool:
        return self.buffer.write(chunk)

    def write_blocking(self, chunk, timeout: Optional[float] = None) -> bool:
        return self.buffer.write_blocking(chunk, timeout)

    def clear(self):
        self.buffer.clear()
        with self._playback_lock:
            self._active_chunk = None
            self._active_chunk_offset = 0

    def trim_queued_bars(self, max_queued_bars: int) -> int:
        return self.buffer.trim_to(max_queued_bars)

    def note_underrun(self):
        self.telemetry.note_underrun()
        self._last_underrun_time = time.time()
        self._underrun_backoff_bars = min(
            self._underrun_backoff_bars + 1,
            int(getattr(self, "_underrun_backoff_cap", 24) or 24),
        )

    def _decay_underrun_backoff(self):
        if self._underrun_backoff_bars <= 0:
            return
        # Decay fairly quickly once audio is stable again.
        if time.time() - self._last_underrun_time >= 3.0:
            self._underrun_backoff_bars = max(0, self._underrun_backoff_bars - 2)
            self._last_underrun_time = time.time()

    def compute_target_buffer_bars(
        self,
        current_bar_seconds: float,
        last_generation_time: float,
        max_generation_time: float,
        minimum_target: int,
    ) -> int:
        self._decay_underrun_backoff()
        render_cost = max(last_generation_time, max_generation_time)
        # Base runway even when generation seems "fast" early on. Real workloads
        # tend to have occasional spikes (sampler lazy-load, cache misses, GC).
        safety_bars = 7
        if render_cost > 0.0:
            # Extra headroom vs real-time so slow bars do not drain the queue to silence.
            safety_bars = max(safety_bars, int(math.ceil((render_cost / current_bar_seconds) * 4.0)) + 2)
        safety_bars += self._underrun_backoff_bars
        reserve = min(128, max(1, self.capacity // 8))
        capacity_ceiling = max(2, self.capacity - reserve)
        return max(2, max(minimum_target, min(capacity_ceiling, safety_bars)))

    def compute_startup_preroll_bars(
        self,
        current_bar_seconds: float,
        last_generation_time: float,
        max_generation_time: float,
        minimum_preroll: int,
        minimum_target: int,
    ) -> int:
        target = self.compute_target_buffer_bars(
            current_bar_seconds=current_bar_seconds,
            last_generation_time=last_generation_time,
            max_generation_time=max_generation_time,
            minimum_target=minimum_target,
        )
        return max(minimum_preroll, min(target, 16))

    def dequeue_audio_frames_into(
        self,
        out: np.ndarray,
        frames: int,
        running: bool,
        paused: bool,
        on_bar_complete,
    ) -> int:
        """
        Copy up to ``frames`` samples into ``out`` (shape ``(frames, 2)``, float32).
        Returns effective queued fill in bars (ring length + active chunk) sampled at
        the start of the dequeue critical section (for telemetry).
        """
        frames = max(0, int(frames))
        if out.shape != (frames, 2) or out.dtype != np.float32:
            raise ValueError(f"out must be float32 with shape ({frames}, 2), got {out.dtype} {out.shape}")

        with self._playback_lock:
            fill_before = len(self.buffer) + (1 if self._active_chunk is not None else 0)
            if frames == 0:
                return fill_before
            if paused or not running:
                out.fill(0.0)
                return fill_before

            written = 0
            while written < frames:
                chunk = self._active_chunk
                if chunk is None:
                    chunk = self.buffer.read()
                    if chunk is None:
                        self.note_underrun()
                        break
                    self._active_chunk = chunk
                    self._active_chunk_offset = 0

                audio = chunk.audio
                start = self._active_chunk_offset
                available = len(audio) - start
                if available <= 0:
                    on_bar_complete()
                    self._active_chunk = None
                    self._active_chunk_offset = 0
                    continue

                take = min(frames - written, available)
                out[written : written + take] = audio[start : start + take]
                written += take
                self._active_chunk_offset += take

                if self._active_chunk_offset >= len(audio):
                    on_bar_complete()
                    self._active_chunk = None
                    self._active_chunk_offset = 0

            if written < frames:
                out[written:frames].fill(0.0)

        return fill_before

    def dequeue_audio_frames(self, frames: int, running: bool, paused: bool, on_bar_complete) -> np.ndarray:
        frames = max(0, int(frames))
        out = np.zeros((frames, 2), dtype=np.float32)
        self.dequeue_audio_frames_into(out, frames, running, paused, on_bar_complete)
        return out

# chord_renderer.py

from collections import OrderedDict
import threading
from typing import List, Optional, Tuple

import numpy as np


class ChordRenderer:
    """Owns chord rendering cache, pan layout, and stereo accumulation."""

    def __init__(self, owner, maxsize: int = 1024, max_bytes: int = 64 * 1024 * 1024):
        self.owner = owner
        self.cache = OrderedDict()
        self.maxsize = maxsize
        self.max_bytes = int(max(0, max_bytes))
        self._cache_bytes = 0
        self._cache_lock = threading.Lock()
        # Reused stereo accumulation buffers per-thread to avoid cross-thread data races.
        self._tls = threading.local()
        self._fade_cache: "OrderedDict[int, np.ndarray]" = OrderedDict()
        self._fade_cache_maxsize = 16
        try:
            cfg = getattr(getattr(owner, "_global_config", None), "audio", None)
            sr = int(getattr(owner, "_sample_rate", 44100))
            ms = float(getattr(cfg, "chord_edge_fade_ms", 1.6) or 1.6)
            self._edge_fade_samples = max(0, int(ms * sr / 1000.0))
        except Exception:
            self._edge_fade_samples = 0

    def _accum_buffer(self, total: int) -> np.ndarray:
        total = int(total)
        if total <= 0:
            return np.zeros((0, 2), dtype=np.float32)
        scratch = getattr(self._tls, "scratch_stereo", None)
        if scratch is None or int(scratch.shape[0]) < total:
            scratch = np.zeros((max(total, 4096), 2), dtype=np.float32)
            self._tls.scratch_stereo = scratch
        out = scratch[:total]
        out.fill(0.0)
        return out

    @staticmethod
    def build_cache_key(
        chord_notes: List[int],
        velocity: int,
        duration_sec: float,
        channel: int,
        tags: Optional[List[str]],
        spread: float,
        sampler_cache_token: Optional[str] = None,
    ) -> Tuple:
        spread_q = round(float(spread), 4)
        notes = tuple(int(n) for n in chord_notes)
        # For mono-centered chords, note order does not affect output: canonicalize for better hits.
        if abs(float(spread_q)) <= 1e-6:
            notes = tuple(sorted(notes))
        tags_key = tuple(sorted(str(t) for t in (tags or ())))
        return (
            notes,
            int(velocity),
            round(float(duration_sec), 4),
            int(channel),
            tags_key,
            spread_q,
            str(sampler_cache_token or ""),
        )

    def get_cached(self, cache_key: Tuple) -> Optional[np.ndarray]:
        with self._cache_lock:
            cached = self.cache.get(cache_key)
            if cached is not None:
                self.cache.move_to_end(cache_key)
                # Read-only for callers; avoids full-buffer copy on every cache hit
                return cached
        return None

    def store(self, cache_key: Tuple, audio: np.ndarray) -> np.ndarray:
        stored = np.asarray(audio, dtype=np.float32, order="C").copy()
        try:
            stored.setflags(write=False)
        except Exception:
            pass
        nbytes = int(getattr(stored, "nbytes", 0) or 0)
        with self._cache_lock:
            prev = self.cache.get(cache_key)
            if prev is not None:
                self._cache_bytes -= int(getattr(prev, "nbytes", 0) or 0)
            self.cache[cache_key] = stored
            self.cache.move_to_end(cache_key)
            self._cache_bytes += nbytes
            while (
                (len(self.cache) > int(self.maxsize))
                or (int(self.max_bytes) > 0 and int(self._cache_bytes) > int(self.max_bytes))
            ):
                try:
                    _, evicted = self.cache.popitem(last=False)
                    self._cache_bytes -= int(getattr(evicted, "nbytes", 0) or 0)
                except Exception:
                    break
            if self._cache_bytes < 0:
                self._cache_bytes = 0
        return stored

    @staticmethod
    def build_pan_positions(n_notes: int, spread: float) -> np.ndarray:
        if n_notes <= 1 or spread <= 0.0:
            return np.zeros(n_notes, dtype=np.float32)
        width = float(np.clip(spread, 0.0, 1.0))
        return np.linspace(-width, width, n_notes, dtype=np.float32)

    @staticmethod
    def pan_gains(pan: float) -> Tuple[float, float]:
        pan = float(np.clip(pan, -1.0, 1.0))
        left_gain = np.sqrt(0.5 * (1.0 - pan))
        right_gain = np.sqrt(0.5 * (1.0 + pan))
        return float(left_gain), float(right_gain)

    def _apply_edge_fade(self, audio: np.ndarray) -> np.ndarray:
        n = int(getattr(audio, "shape", [0])[0] if audio is not None else 0)
        fade = int(getattr(self, "_edge_fade_samples", 0) or 0)
        if n <= 8 or fade <= 0:
            return audio
        fade = min(fade, max(0, n // 8))
        if fade <= 0:
            return audio
        env = self._fade_cache.get(fade)
        if env is None:
            env = np.linspace(0.0, 1.0, fade, dtype=np.float32)[:, np.newaxis]
            self._fade_cache[fade] = env
            while len(self._fade_cache) > int(self._fade_cache_maxsize):
                try:
                    self._fade_cache.popitem(last=False)
                except Exception:
                    break
        out = np.asarray(audio, dtype=np.float32, order="C").copy()
        out[:fade] *= env
        out[-fade:] *= env[::-1]
        return out

    def render(
        self,
        sampler,
        chord_notes: List[int],
        velocity: int,
        duration_sec: float,
        channel: int = 1,
        tags: Optional[List[str]] = None,
        spread: float = 0.0,
    ) -> np.ndarray:
        if not chord_notes:
            return np.zeros(
                (int(duration_sec * self.owner._sample_rate), 2), dtype=np.float32
            )

        # If the sampler randomizes sample start points, caching would defeat the point.
        cfg = getattr(sampler, "config", None)
        cache_allowed = not (
            bool(getattr(cfg, "random_start_within_loop", False))
            or bool(getattr(cfg, "shimmer_enabled", False))
        )
        try:
            sampler_cache_token = str(sampler._transposition_mode_cache_token())
        except Exception:
            sampler_cache_token = ""
        cache_key = self.build_cache_key(
            chord_notes, velocity, duration_sec, channel, tags, spread, sampler_cache_token
        )
        if cache_allowed:
            cached = self.get_cached(cache_key)
            if cached is not None:
                return cached

        total = int(duration_sec * self.owner._sample_rate)
        result = self._accum_buffer(total)
        pan_positions = self.build_pan_positions(len(chord_notes), spread)

        for note, pan in zip(chord_notes, pan_positions):
            note_audio = sampler.render_note(note, velocity, duration_sec)
            n = min(len(note_audio), total)
            if n <= 0:
                continue
            if note_audio.ndim != 2 or note_audio.shape[1] != 2 or abs(pan) < 1e-6:
                result[:n] += note_audio[:n]
                continue
            left_gain, right_gain = self.pan_gains(pan)
            result[:n, 0] += note_audio[:n, 0] * left_gain
            result[:n, 1] += note_audio[:n, 1] * right_gain

        if len(chord_notes) > 1:
            result /= len(chord_notes)

        result = self._apply_edge_fade(result)

        peak = np.max(np.abs(result))
        if peak > 0.98:
            result = np.tanh(result * 0.9) * 0.95

        result = result.astype(np.float32)
        if cache_allowed:
            return self.store(cache_key, result)
        # No cache path: detach from thread-local scratch so downstream calls can't overwrite it.
        return np.array(result, dtype=np.float32, copy=True)

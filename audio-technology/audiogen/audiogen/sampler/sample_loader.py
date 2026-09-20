# sample_loader.py

import time
import os
import random
from pathlib import Path
from typing import Callable, Optional, Tuple
import threading

import numpy as np

from audiogen_core.config_utils import project_path, resolve_project_path

from .utils import apply_fade_in_out, create_silent_sample, dc_block, normalize_audio
from utils.startup_profiler import _truthy_env


_SAMPLE_BANK_LOCK = threading.Lock()
_SAMPLE_BANK: dict[str, np.ndarray] = {}
_CACHE_PRUNE_LOCK = threading.Lock()
_CACHE_LAST_PRUNE_TS = 0.0


def _maybe_prune_sample_cache(cache_dir: Path, cfg: dict) -> None:
    """
    Best-effort bounding of `.cache/sample_cache_v2`.
    Never raises; keeps the hot path resilient.
    """
    global _CACHE_LAST_PRUNE_TS
    try:
        max_mb = float(cfg.get("sample_cache_max_mb", 0.0) or 0.0)
    except Exception:
        max_mb = 0.0
    try:
        max_files = int(cfg.get("sample_cache_max_files", 0) or 0)
    except Exception:
        max_files = 0
    try:
        ttl_days = float(cfg.get("sample_cache_ttl_days", 0.0) or 0.0)
    except Exception:
        ttl_days = 0.0
    try:
        prune_chance = float(cfg.get("sample_cache_prune_chance", 0.02) or 0.02)
    except Exception:
        prune_chance = 0.02

    # Nothing to do if all limits are disabled.
    if max_mb <= 0.0 and max_files <= 0 and ttl_days <= 0.0:
        return

    # Cheap throttle: probabilistic + time-based cooldown.
    now = time.time()
    if prune_chance < 1.0 and random.random() > max(0.0, min(1.0, prune_chance)):
        return
    if (now - float(_CACHE_LAST_PRUNE_TS)) < 10.0:
        return

    with _CACHE_PRUNE_LOCK:
        # Re-check after acquiring lock.
        now = time.time()
        if (now - float(_CACHE_LAST_PRUNE_TS)) < 10.0:
            return
        _CACHE_LAST_PRUNE_TS = now

        try:
            if not cache_dir.exists() or not cache_dir.is_dir():
                return
        except Exception:
            return

        ttl_s = float(ttl_days) * 86400.0 if ttl_days > 0.0 else 0.0
        max_bytes = int(max_mb * 1024.0 * 1024.0) if max_mb > 0.0 else 0

        entries: list[tuple[float, int, Path]] = []
        total_bytes = 0

        try:
            for p in cache_dir.glob("*.npy"):
                try:
                    st = p.stat()
                except Exception:
                    continue
                mtime = float(getattr(st, "st_mtime", 0.0) or 0.0)
                size = int(getattr(st, "st_size", 0) or 0)
                # TTL expiry first.
                if ttl_s > 0.0 and (now - mtime) > ttl_s:
                    try:
                        p.unlink(missing_ok=True)
                    except Exception:
                        pass
                    continue
                entries.append((mtime, size, p))
                total_bytes += size
        except Exception:
            return

        # Enforce caps by deleting oldest first (mtime used as LRU surrogate).
        if (max_files > 0 and len(entries) > max_files) or (max_bytes > 0 and total_bytes > max_bytes):
            entries.sort(key=lambda t: t[0])  # oldest first
            i = 0
            while i < len(entries) and (
                (max_files > 0 and len(entries) > max_files) or (max_bytes > 0 and total_bytes > max_bytes)
            ):
                _, sz, p = entries[i]
                i += 1
                try:
                    p.unlink(missing_ok=True)
                    total_bytes -= int(sz)
                except Exception:
                    pass


class SampleLoader:
    """Loads WAV files using scipy.io.wavfile (no librosa)."""

    def __init__(
        self,
        sample_rate: int,
        logger,
        librosa_module,  # kept for compatibility but not used
        pre_gain_db: float,
        post_gain_db: float,
        db_to_linear: Callable[[float], float],
        normalizer_config: Optional[dict] = None,
        source_dc_enabled: Optional[bool] = None,
        source_dc_cutoff_hz: Optional[float] = None,
    ):
        self.sample_rate = sample_rate
        self.logger = logger
        self.pre_gain_db = pre_gain_db
        self.post_gain_db = post_gain_db
        self.db_to_linear = db_to_linear
        self.normalizer_config = normalizer_config or {}
        if source_dc_enabled is None:
            self.source_dc_enabled = bool(self.normalizer_config.get("sample_dc_block_enabled", True))
        else:
            self.source_dc_enabled = bool(source_dc_enabled)
        try:
            if source_dc_cutoff_hz is None:
                self.source_dc_cutoff_hz = float(
                    self.normalizer_config.get("sample_dc_block_cutoff_hz", 12.0) or 12.0
                )
            else:
                self.source_dc_cutoff_hz = float(source_dc_cutoff_hz)
        except Exception:
            self.source_dc_cutoff_hz = 12.0
        try:
            self.source_dc_min_mean_abs = float(
                self.normalizer_config.get("sample_dc_block_min_mean_abs", 5e-4) or 5e-4
            )
        except Exception:
            self.source_dc_min_mean_abs = 5e-4

    def load_sample(self, path: Path) -> np.ndarray:
        """Load a WAV file, convert to float32, stereo, and resample to target rate."""
        path = self._resolve_sample_path(Path(path))
        profile = _truthy_env("AUDIOGEN_SAMPLELOAD_PROFILE", False)
        t0 = time.perf_counter() if profile else 0.0
        # Fast path: on-disk cache for finalized samples (resample + normalization + fades).
        # This makes repeated startups much faster for any sample pack, regardless of normalization.
        cache_path: Optional[Path] = None
        try:
            import hashlib
            import json

            cfg = dict(self.normalizer_config or {})
            cache_enabled = bool(cfg.get("sample_cache_enabled", True))
            mmap = bool(cfg.get("sample_cache_mmap", True))
            if cache_enabled:
                st = path.stat() if path.exists() else None
                # Cache invalidation note:
                # Some copy tools preserve mtime (and sometimes even size), which would otherwise
                # make the cache incorrectly "stick" after replacing a WAV. Include higher
                # precision timestamps and inode where available to make invalidation robust.
                try:
                    mtime_ns = int(getattr(st, "st_mtime_ns", 0) or 0) if st is not None else 0
                except Exception:
                    mtime_ns = 0
                try:
                    ctime_ns = int(getattr(st, "st_ctime_ns", 0) or 0) if st is not None else 0
                except Exception:
                    ctime_ns = 0
                try:
                    inode = int(getattr(st, "st_ino", 0) or 0) if st is not None else 0
                except Exception:
                    inode = 0
                key_obj = {
                    "p": str(path),
                    "mtime": float(getattr(st, "st_mtime", 0.0) or 0.0),
                    "mtime_ns": int(mtime_ns),
                    "ctime_ns": int(ctime_ns),
                    "size": int(getattr(st, "st_size", 0) or 0),
                    "inode": int(inode),
                    "sr": int(self.sample_rate),
                    "pre_gain_db": float(self.pre_gain_db),
                    "post_gain_db": float(self.post_gain_db),
                    "normalize": bool(cfg.get("normalize_samples_on_load", False)),
                    "norm": {
                        "target": float(cfg.get("normalizer_target_level", -18.0)),
                        "mode": str(cfg.get("normalizer_mode", "rms")),
                        "prevent": bool(cfg.get("normalizer_prevent_clipping", True)),
                        "pre_db": float(cfg.get("normalizer_pre_gain_db", 0.0) or 0.0),
                        "post_db": float(cfg.get("normalizer_post_gain_db", 0.0) or 0.0),
                    },
                    "dc": {
                        "enabled": bool(getattr(self, "source_dc_enabled", True)),
                        "cutoff_hz": float(getattr(self, "source_dc_cutoff_hz", 12.0) or 12.0),
                        "min_mean_abs": float(getattr(self, "source_dc_min_mean_abs", 5e-4) or 5e-4),
                    },
                    "resample_quality": str(cfg.get("sample_resample_quality", "high") or "high"),
                }
                h = hashlib.blake2b(
                    json.dumps(key_obj, sort_keys=True).encode("utf-8"),
                    digest_size=16,
                ).hexdigest()
                cache_dir = project_path(".cache", "sample_cache_v2")
                cache_dir.mkdir(parents=True, exist_ok=True)
                # Best-effort cache bounding (avoid unbounded disk growth).
                try:
                    _maybe_prune_sample_cache(cache_dir, cfg)
                except Exception:
                    pass
                cache_path = cache_dir / f"{h}.npy"
                # Process-level bank: avoid re-reading the same cached sample multiple times
                # when multiple Sampler instances are built in one process.
                try:
                    k = str(cache_path)
                    with _SAMPLE_BANK_LOCK:
                        v = _SAMPLE_BANK.get(k)
                    if v is not None:
                        if profile:
                            dt_ms = (time.perf_counter() - t0) * 1000.0
                            try:
                                self.logger.info("Sample bank hit: %s (%.1fms)", str(path), dt_ms)
                            except Exception:
                                pass
                        return v
                except Exception:
                    pass
                if cache_path.exists():
                    try:
                        cached = np.load(str(cache_path), allow_pickle=False, mmap_mode="r" if mmap else None)
                        # Ensure stereo float32 shape.
                        cached = np.asarray(cached, dtype=np.float32)
                        if cached.ndim == 1:
                            cached = np.column_stack([cached, cached])
                        # Touch mtime to approximate LRU (atime may be disabled on some FS).
                        try:
                            os.utime(cache_path, None)
                        except Exception:
                            pass
                        try:
                            with _SAMPLE_BANK_LOCK:
                                _SAMPLE_BANK[str(cache_path)] = cached
                        except Exception:
                            pass
                        if profile:
                            dt_ms = (time.perf_counter() - t0) * 1000.0
                            try:
                                self.logger.info("Sample cache hit: %s (%.1fms)", str(path), dt_ms)
                            except Exception:
                                pass
                        return cached
                    except Exception:
                        cache_path = None
        except Exception:
            cache_path = None

        if not path.exists():
            # Many sample packs define only root_midi and rely on inferred filenames
            # (e.g. samples/melody_shimmer.wav or samples/shimmer/melody.wav).
            # If those optional assets don't exist, fall back to the default pack
            # rather than returning silence (which makes the channel appear broken).
            fallback = self._fallback_default_path(path)
            if fallback is not None:
                fallback = self._resolve_sample_path(fallback)
            if fallback is not None and fallback.exists():
                self.logger.warning("Sample not found: %s (falling back to %s)", path, fallback)
                path = fallback
            else:
                self.logger.warning("Sample not found: %s", path)
                return create_silent_sample(1.0, self.sample_rate)

        try:
            from scipy.io import wavfile  # local import: speeds cold start
            sr, audio = wavfile.read(str(path))
        except Exception as exc:
            self.logger.exception("Failed to load sample %s: %s", path, exc)
            return create_silent_sample(1.0, self.sample_rate)
        if profile:
            t_read = time.perf_counter()

        # Convert to float32
        audio = self.convert_pcm_to_float(audio)

        # Ensure stereo
        if audio.ndim == 1:
            audio = np.column_stack([audio, audio])
        elif audio.ndim == 2 and audio.shape[1] > 2:
            # Downmix to stereo if more than 2 channels
            audio = audio[:, :2]

        # Resample if needed
        if sr != self.sample_rate:
            try:
                import scipy.signal  # local import: speeds cold start
            except Exception as exc:
                self.logger.exception("SciPy not available for resampling (%s); returning silence", exc)
                return create_silent_sample(1.0, self.sample_rate)
            cfg = dict(self.normalizer_config or {})
            q = str(cfg.get("sample_resample_quality", "high") or "high").strip().lower()
            if q == "best":
                win = ("kaiser", 12.0)
            elif q == "fast":
                win = ("kaiser", 5.0)
            else:
                win = ("kaiser", 8.6)
            audio = scipy.signal.resample_poly(audio, self.sample_rate, sr, axis=0, window=win)
        if profile:
            t_resample = time.perf_counter()

        # Finalise (gain, normalisation, fade)
        audio = self.finalize_loaded_audio(audio, self.sample_rate)
        if profile:
            t_finalize = time.perf_counter()
        # Best-effort cache write (only if cache_path was computed).
        if cache_path is not None:
            try:
                np.save(str(cache_path), np.asarray(audio, dtype=np.float32), allow_pickle=False)
                # Bound the cache after writing too (covers first-time fill bursts).
                try:
                    _maybe_prune_sample_cache(cache_path.parent, dict(self.normalizer_config or {}))
                except Exception:
                    pass
                try:
                    with _SAMPLE_BANK_LOCK:
                        _SAMPLE_BANK[str(cache_path)] = np.asarray(audio, dtype=np.float32)
                except Exception:
                    pass
            except Exception:
                pass
        if profile:
            try:
                dt_total = (time.perf_counter() - t0) * 1000.0
                dt_read = (t_read - t0) * 1000.0 if "t_read" in locals() else None
                dt_res = (t_resample - t_read) * 1000.0 if "t_resample" in locals() and "t_read" in locals() else None
                dt_fin = (t_finalize - t_resample) * 1000.0 if "t_finalize" in locals() and "t_resample" in locals() else None
                self.logger.info(
                    "Sample load: %s total=%.1fms read=%.1fms resample=%.1fms finalize=%.1fms cached=%s",
                    str(path),
                    float(dt_total),
                    float(dt_read or 0.0),
                    float(dt_res or 0.0),
                    float(dt_fin or 0.0),
                    bool(cache_path is not None),
                )
            except Exception:
                pass
        return audio

    @staticmethod
    def _resolve_sample_path(path: Path) -> Path:
        """Return ``path`` if present, else common local aliases (e.g. ``meldoy.wav`` for melody)."""
        try:
            p = resolve_project_path(path)
        except Exception:
            return path
        if p.exists():
            return p
        try:
            if p.name.lower() == "melody.wav":
                alt = p.with_name("meldoy.wav")
                if alt.exists():
                    return alt
        except Exception:
            pass
        return p

    @staticmethod
    def _fallback_default_path(path: Path) -> Optional[Path]:
        """
        Best-effort mapping from inferred pack paths to a default-pack sample.

        Handles both:
        - samples/<sampler>_<pack>.wav  -> samples/default/<sampler>.wav
        - samples/<pack>/<sampler>.wav  -> samples/default/<sampler>.wav
        """
        parts = list(path.parts)
        try:
            samples_idx = parts.index("samples")
        except ValueError:
            return None

        stem = path.stem
        suffix = path.suffix or ".wav"

        base = stem
        if "_" in stem:
            # assume final underscore chunk is a pack name: counter_melody_shimmer -> counter_melody
            base = stem.rsplit("_", 1)[0]

        # Always attempt the default pack first; it's expected to exist in real projects.
        return Path(*parts[: samples_idx + 1]) / "default" / f"{base}{suffix}"

    @staticmethod
    def convert_pcm_to_float(audio: np.ndarray) -> np.ndarray:
        """Convert integer PCM to float32 in range [-1, 1]."""
        if np.issubdtype(audio.dtype, np.integer):
            info = np.iinfo(audio.dtype)
            scale = max(abs(info.min), info.max)
            audio = audio.astype(np.float32) / float(scale)
        else:
            audio = audio.astype(np.float32)
        return audio

    def finalize_loaded_audio(self, audio: np.ndarray, sr: int) -> np.ndarray:
        """Apply pre‑gain, optional safety limiting, and small fades.

        Note: This project intentionally does **not** normalize samples at load time.
        If you want consistent loudness, normalize/export in your DAW before importing WAVs.
        """
        if self.pre_gain_db != 0.0:
            audio *= self.db_to_linear(self.pre_gain_db)

        if self.post_gain_db != 0.0:
            audio *= self.db_to_linear(self.post_gain_db)
            # Post-gain is user-configurable; apply a very light safety limiter
            # to avoid NaNs/infs from downstream processing when users overshoot.
            peak = np.max(np.abs(audio))
            if peak > 1.25:
                audio = np.tanh(audio).astype(np.float32, copy=False)

        # Optional normalization (disabled by default; controlled by CONFIG.audio)
        try:
            if bool(self.normalizer_config.get("normalize_samples_on_load", False)):
                pre_db = float(self.normalizer_config.get("normalizer_pre_gain_db", 0.0) or 0.0)
                post_db = float(self.normalizer_config.get("normalizer_post_gain_db", 0.0) or 0.0)
                if pre_db:
                    audio *= self.db_to_linear(pre_db)
                audio = normalize_audio(
                    audio,
                    target_db=float(self.normalizer_config.get("normalizer_target_level", -3.0)),
                    mode=str(self.normalizer_config.get("normalizer_mode", "peak") or "peak"),
                    prevent_clipping=bool(self.normalizer_config.get("normalizer_prevent_clipping", True)),
                    sample_rate=int(sr),
                ).astype(np.float32, copy=False)
                if post_db:
                    audio *= self.db_to_linear(post_db)
        except Exception:
            # Normalization is best-effort; never break audio load.
            pass

        # Tiny fade in/out to avoid clicks (optional)
        fade_smp = min(int(10 * self.sample_rate / 1000), len(audio) // 2)
        if fade_smp > 0:
            audio = apply_fade_in_out(audio, fade_smp)

        # Source-stage DC blocking (load-time only), with threshold gating.
        try:
            if bool(getattr(self, "source_dc_enabled", True)):
                x = np.asarray(audio, dtype=np.float32)
                if x.ndim == 1:
                    dc_mean = float(abs(float(np.mean(x))))
                else:
                    dc_mean = float(max(abs(float(np.mean(x[:, 0]))), abs(float(np.mean(x[:, 1])))))
                if dc_mean >= float(getattr(self, "source_dc_min_mean_abs", 5e-4) or 5e-4):
                    audio = dc_block(
                        x,
                        sample_rate=int(sr),
                        cutoff_hz=float(getattr(self, "source_dc_cutoff_hz", 12.0) or 12.0),
                    )
        except Exception:
            # Never break sample load due to source DC cleanup.
            pass

        return audio.astype(np.float32)

    # The following methods are kept for compatibility with older code,
    # but they are not used in the simplified sampler.
    def compute_loop_points(self, audio: np.ndarray) -> Tuple[int, int]:
        """Simple loop point detection: last 25% of sample."""
        total = len(audio)
        loop_start = max(0, int(0.75 * total))
        loop_end = total
        return loop_start, loop_end

    @staticmethod
    def find_best_loop_end(
        mono: np.ndarray,
        loop_start: int,
        search_start: int,
        search_end: int,
        min_loop_len: int,
    ) -> int:
        """Dummy – not used in classic sampler."""
        return min(search_end, len(mono))

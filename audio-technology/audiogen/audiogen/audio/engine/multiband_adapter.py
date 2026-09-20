from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

try:
    # Optional dependency: clarity.enhancer.multiband_compressor
    from clarity.enhancer.multiband_compressor import MultibandCompressor as _ClarityMultibandCompressor
except Exception:  # pragma: no cover - optional dependency
    _ClarityMultibandCompressor = None  # type: ignore[assignment]


class MasterMultibandCompressor:


    def __init__(
        self,
        sample_rate: int,
        crossover_frequencies: Sequence[float],
        compressors_params: Optional[dict[str, Any]] = None,
    ) -> None:
        self.sample_rate = int(sample_rate)
        self._enabled_backend = _ClarityMultibandCompressor is not None
        self._log_once_missing = False
        self._mix: float = 0.6
        self._makeup_gain_linear: float = 1.0
        # Reuse buffers to reduce per-call allocations on the master bus.
        self._buf_out: Optional[np.ndarray] = None
        self._buf_tmp: Optional[np.ndarray] = None

        if not self._enabled_backend:
            return

        try:
            self._backend = _ClarityMultibandCompressor(
                crossover_frequencies=list(crossover_frequencies),
                sample_rate=float(self.sample_rate),
                compressors_params=compressors_params or {},
            )
        except Exception:
            logger.exception("Failed to initialize clarity MultibandCompressor; disabling multiband backend.")
            self._backend = None
            self._enabled_backend = False

    def update_compressors(
        self,
        attack_ms: Sequence[float],
        release_ms: Sequence[float],
        threshold_db: Sequence[float],
        ratio: Sequence[float],
        makeup_gain_db: Sequence[float],
        knee_width_db: float,
    ) -> None:
        if not self._enabled_backend or getattr(self, "_backend", None) is None:
            return
        try:
            # clarity MultibandCompressor.set_compressors accepts either scalars or per-band lists.
            self._backend.set_compressors(
                attack=list(attack_ms),
                release=list(release_ms),
                threshold=list(threshold_db),
                ratio=list(ratio),
                makeup_gain=list(makeup_gain_db),
                knee_width=float(knee_width_db),
            )
        except Exception:
            logger.exception("Failed to update multiband compressor parameters; keeping previous settings.")

    def set_mix_and_makeup(self, mix: float, overall_makeup_db: float) -> None:
        mix_clamped = float(np.clip(mix, 0.0, 1.0))
        self._mix = mix_clamped
        self._makeup_gain_linear = float(10.0 ** (float(overall_makeup_db) / 20.0))

    @property
    def enabled(self) -> bool:
        return bool(self._enabled_backend and getattr(self, "_backend", None) is not None and self._mix > 0.0)

    def process(self, audio_stereo: np.ndarray) -> np.ndarray:
        """
        Process a stereo buffer with multiband compression and return the blended result.
        """
        if not self.enabled:
            return audio_stereo

        # Avoid copies if already float32.
        x = audio_stereo if isinstance(audio_stereo, np.ndarray) and audio_stereo.dtype == np.float32 else np.asarray(audio_stereo, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != 2 or x.size == 0:
            return audio_stereo

        try:
            # clarity MultibandCompressor expects shape (channels, samples) by default.
            # Transpose to (channels, frames), process, then transpose back.
            frames, chans = x.shape
            src = x.T  # (2, n_frames)
            backend = getattr(self, "_backend", None)
            if backend is None:
                return audio_stereo
            y = backend(src)  # expected shape (2, n_frames)
            if not isinstance(y, np.ndarray):
                return audio_stereo
            if y.shape != src.shape:
                # Be defensive about unexpected shapes.
                y = np.asarray(y, dtype=np.float32)
                if y.ndim == 2 and y.shape[0] == chans:
                    pass
                else:
                    return audio_stereo
            wet = y.T
            if not isinstance(wet, np.ndarray):
                return audio_stereo
            if wet.dtype != np.float32:
                wet = np.asarray(wet, dtype=np.float32)
            if wet.shape != x.shape:
                return audio_stereo

            mix = float(self._mix)
            if mix <= 0.0:
                return x
            if mix >= 1.0:
                out = wet
                g = np.float32(self._makeup_gain_linear)
                if abs(float(g) - 1.0) > 1e-12:
                    # Use a reusable output buffer to avoid allocating for gain-only.
                    if self._buf_out is None or self._buf_out.shape != out.shape:
                        self._buf_out = np.empty_like(out, dtype=np.float32)
                    np.multiply(out, g, out=self._buf_out)
                    return self._buf_out
                return out.astype(np.float32, copy=False)

            one_minus = np.float32(1.0 - mix)
            mix_f = np.float32(mix)
            g = np.float32(self._makeup_gain_linear)

            # Ensure reusable buffers match current frame count.
            if self._buf_out is None or self._buf_out.shape != x.shape:
                self._buf_out = np.empty_like(x, dtype=np.float32)
            if self._buf_tmp is None or self._buf_tmp.shape != x.shape:
                self._buf_tmp = np.empty_like(x, dtype=np.float32)

            # out = dry*(1-mix) + wet*mix, then apply makeup gain.
            np.multiply(x, one_minus, out=self._buf_out)
            np.multiply(wet, mix_f, out=self._buf_tmp)
            np.add(self._buf_out, self._buf_tmp, out=self._buf_out)
            if abs(float(g) - 1.0) > 1e-12:
                np.multiply(self._buf_out, g, out=self._buf_out)
            return self._buf_out
        except Exception:
            if not self._log_once_missing:
                logger.exception("Error while processing master multiband compressor; temporarily bypassing.")
                self._log_once_missing = True
            return audio_stereo


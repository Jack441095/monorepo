"""Real-time PCM chunk analysis for A8.1 Live Audio Stream Analysis.

Designed for POST-based polling at ~10Hz from the browser: each call
receives one 400ms window of 16-bit signed PCM and returns LUFS,
7-band spectrum, stereo correlation, and L/R balance.
"""

from __future__ import annotations

import math
import struct

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:  # pragma: no cover - numpy is a hard dep in practice
    NUMPY_AVAILABLE = False


def analyze_pcm_chunk(
    pcm_bytes: bytes,
    *,
    sample_rate: int,
    channels: int = 2,
) -> dict:
    """Analyse a single PCM chunk (typically 400ms) for live dashboard updates.

    Args:
        pcm_bytes: Raw 16-bit signed little-endian PCM audio.
        sample_rate: Sample rate in Hz (e.g. 44100 or 48000).
        channels: 1 (mono) or 2 (stereo).

    Returns a dict with:
        lufs_momentary   — momentary LUFS (single ungated BS.1770-3 block)
        bands            — 7-band spectral energy shares (sub/bass/…/air)
        correlation      — L/R correlation in [-1, 1]  (1.0 for mono input)
        balance          — L/R balance in [-1, 1] (positive = right-heavy)
        sample_count     — number of samples decoded per channel
    """
    empty: dict = {
        "lufs_momentary": -70.0,
        "bands": {},
        "correlation": 1.0,
        "balance": 0.0,
        "sample_count": 0,
    }
    if not pcm_bytes or sample_rate <= 0 or channels not in (1, 2):
        return empty

    try:
        n_samples_total = len(pcm_bytes) // 2
        _NORM = 1.0 / 32768.0

        # This runs on every ~10Hz dashboard poll, so it is the one path where
        # latency is literally the product. The numpy branch replaces the
        # per-sample struct.unpack + list-comprehension decode and the per-sample
        # sum(v*v) metric loops with vectorised equivalents; the pure-Python path
        # below is kept byte-for-byte as the numpy-absent fallback.
        if NUMPY_AVAILABLE:
            raw = np.frombuffer(pcm_bytes[:n_samples_total * 2], dtype="<i2").astype(np.float64)
            raw *= _NORM
            if channels == 1:
                lv = rv = raw
            else:
                lv = raw[0::2]
                rv = raw[1::2]
            n = int(min(lv.shape[0], rv.shape[0]))
            if n == 0:
                return empty
            lv = lv[:n]
            rv = rv[:n]

            # --- Momentary LUFS (single ungated 400ms block, BS.1770-3) ---
            lufs_momentary = -70.0
            try:
                from audio_analysis.analysis_core.loudness import _k_filter_samples
                y1, y2 = _k_filter_samples(lv, rv, sample_rate)
                y1 = np.asarray(y1, dtype=np.float64)
                y2 = np.asarray(y2, dtype=np.float64)
                mean_power = float(y1 @ y1 + y2 @ y2) / max(2 * n, 1)
                if mean_power > 1e-10:
                    lufs_momentary = round(10.0 * math.log10(mean_power) - 0.691, 2)
            except Exception:
                mean_power = float(lv @ lv + rv @ rv) / max(2 * n, 1)
                if mean_power > 1e-10:
                    lufs_momentary = round(10.0 * math.log10(mean_power), 2)

            # --- 7-band spectrum (mono mixdown; .tolist() keeps spectral_bands' input type) ---
            bands = {}
            try:
                from audio_analysis.analysis_core.dsp_metrics import spectral_bands
                bands = spectral_bands(((lv + rv) * 0.5).tolist(), sample_rate)
            except Exception:
                pass

            # --- Stereo correlation ---
            correlation = 1.0
            try:
                l_energy = float(lv @ lv)
                r_energy = float(rv @ rv)
                cross = float(lv @ rv)
                denom = math.sqrt(max(l_energy * r_energy, 0.0))
                if denom > 1e-9:
                    correlation = round(max(-1.0, min(1.0, cross / denom)), 3)
            except Exception:
                pass

            # --- L/R balance ---
            balance = 0.0
            try:
                l_rms = math.sqrt(float(lv @ lv) / n)
                r_rms = math.sqrt(float(rv @ rv) / n)
                denom_bal = max(l_rms + r_rms, 1e-9)
                balance = round((r_rms - l_rms) / denom_bal, 3)
            except Exception:
                pass

            return {
                "lufs_momentary": lufs_momentary,
                "bands": bands,
                "correlation": correlation,
                "balance": balance,
                "sample_count": n,
            }

        # --- Decode 16-bit signed PCM to normalised float lists (numpy-absent fallback) ---
        raw = struct.unpack(f"<{n_samples_total}h", pcm_bytes[:n_samples_total * 2])

        if channels == 1:
            left = [v * _NORM for v in raw]
            right = list(left)
        else:
            left = [raw[i] * _NORM for i in range(0, n_samples_total, 2)]
            right = [raw[i] * _NORM for i in range(1, n_samples_total, 2)]

        n = min(len(left), len(right))
        if n == 0:
            return empty

        # --- Momentary LUFS (single ungated 400ms block, BS.1770-3) ---
        lufs_momentary: float = -70.0
        try:
            from audio_analysis.analysis_core.loudness import _k_filter_samples
            y1, y2 = _k_filter_samples(left[:n], right[:n], sample_rate)
            mean_power = (
                sum(v * v for v in y1) + sum(v * v for v in y2)
            ) / max(2 * n, 1)
            if mean_power > 1e-10:
                lufs_momentary = round(10.0 * math.log10(mean_power) - 0.691, 2)
        except Exception:
            # Fallback: simple RMS without K-weighting
            mean_power = (
                sum(v * v for v in left[:n]) + sum(v * v for v in right[:n])
            ) / max(2 * n, 1)
            if mean_power > 1e-10:
                lufs_momentary = round(10.0 * math.log10(mean_power), 2)

        # --- 7-band spectrum (mix to mono for a single representative curve) ---
        bands: dict = {}
        try:
            from audio_analysis.analysis_core.dsp_metrics import spectral_bands
            mono = [(lf + r) * 0.5 for lf, r in zip(left[:n], right[:n])]
            bands = spectral_bands(mono, sample_rate)
        except Exception:
            pass

        # --- Stereo correlation ---
        correlation = 1.0
        try:
            l_energy = sum(v * v for v in left[:n])
            r_energy = sum(v * v for v in right[:n])
            cross = sum(lv * rv for lv, rv in zip(left[:n], right[:n]))
            denom = math.sqrt(max(l_energy * r_energy, 0.0))
            if denom > 1e-9:
                correlation = round(max(-1.0, min(1.0, cross / denom)), 3)
        except Exception:
            pass

        # --- L/R balance ---
        balance = 0.0
        try:
            l_rms = math.sqrt(sum(v * v for v in left[:n]) / n)
            r_rms = math.sqrt(sum(v * v for v in right[:n]) / n)
            denom_bal = max(l_rms + r_rms, 1e-9)
            balance = round((r_rms - l_rms) / denom_bal, 3)
        except Exception:
            pass

        return {
            "lufs_momentary": lufs_momentary,
            "bands": bands,
            "correlation": correlation,
            "balance": balance,
            "sample_count": n,
        }
    except Exception:
        return empty

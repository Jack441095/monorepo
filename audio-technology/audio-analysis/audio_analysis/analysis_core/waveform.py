"""Downsampled waveform peaks for frontend rendering.

No route anywhere in this codebase returns raw/decoded audio samples --
correctly so: a 3-minute song at 44.1kHz is ~7.9M samples per channel, far
too much for one JSON response. What a web waveform view actually needs is
the standard "peaks" shape (min/max per time bucket, the same format
libraries like wavesurfer.js expect) -- a few hundred to a few thousand
points regardless of track length.
"""

from __future__ import annotations

import numpy as np

MIN_POINTS = 50
MAX_POINTS = 5000
DEFAULT_POINTS = 800


def compute_waveform_peaks(
    samples,
    sample_rate: int,
    *,
    target_points: int = DEFAULT_POINTS,
) -> dict:
    """Downsample mono audio into (min, max) pairs across target_points
    evenly-sized time buckets.

    Parameters
    ----------
    samples : array-like
        Mono audio samples, normalised to [-1.0, 1.0].
    sample_rate : int
        Source sample rate, used only to compute duration_seconds.
    target_points : int
        Requested resolution, clamped to [MIN_POINTS, MAX_POINTS]. The last
        bucket may be slightly wider than the others when the sample count
        doesn't divide evenly.

    Returns
    -------
    dict
        - "sample_rate": int
        - "duration_seconds": float
        - "points": int (actual bucket count, <= target_points)
        - "peaks": list[[min, max]] -- one pair per bucket, in [-1.0, 1.0]
    """
    arr = np.asarray(samples, dtype=np.float64)
    n = len(arr)
    if n == 0:
        return {"sample_rate": int(sample_rate), "duration_seconds": 0.0, "points": 0, "peaks": []}

    points = max(MIN_POINTS, min(int(target_points), MAX_POINTS, n))
    bucket_size = max(1, n // points)

    peaks: list[list[float]] = []
    for i in range(points):
        start = i * bucket_size
        if start >= n:
            break
        end = n if i == points - 1 else min(n, start + bucket_size)
        chunk = arr[start:end]
        peaks.append([round(float(chunk.min()), 5), round(float(chunk.max()), 5)])

    duration_seconds = (n / float(sample_rate)) if sample_rate else 0.0
    return {
        "sample_rate": int(sample_rate),
        "duration_seconds": round(duration_seconds, 3),
        "points": len(peaks),
        "peaks": peaks,
    }

"""Saturation and harmonic enhancement module for automated mixdown system.

Implements:
  1. apply_saturation — soft saturation using tanh waveshaping with unity-gain scaling.
  2. Asymmetric waveshaping for even-harmonic emphasis.
  3. 4x oversampled processing to prevent digital aliasing.
All processing runs offline using numpy and scipy.
"""

from __future__ import annotations

import numpy as np
import scipy.signal as sig
from . import native as _native

try:
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def apply_saturation(
    samples: np.ndarray | list[float],
    drive_db: float = 3.0,
    even_harmonics: float = 0.2,  # 0.0 (odd only) to 1.0 (heavy even harmonics)
    mix: float = 1.0,             # Wet/dry mix (0.0 to 1.0)
    oversample: bool = True,
) -> np.ndarray:
    """Apply tape-style soft saturation with optional even-harmonic emphasis.

    Parameters
    ----------
    samples : np.ndarray or list[float]
        Input mono audio samples.
    drive_db : float
        Drive gain in dB. Higher values increase distortion.
    even_harmonics : float
        Intensity of even harmonics (0.0 to 1.0).
    mix : float
        Wet/dry mix factor.
    oversample : bool
        If True, uses 4x oversampling to prevent aliasing.
    """
    x = np.asarray(samples, dtype=np.float64)
    if len(x) == 0:
        return x

    drive_db = max(0.0, drive_db)
    even_harmonics = max(0.0, min(even_harmonics, 1.0))
    mix = max(0.0, min(mix, 1.0))

    if drive_db < 1e-4 and even_harmonics < 1e-4:
        return x

    # 1. Oversampling (4x)
    if oversample:
        x_up = sig.resample_poly(x, 4, 1)
    else:
        x_up = x

    # 2. Waveshaping
    d = 10.0 ** (drive_db / 20.0)
    a = even_harmonics * 0.3

    if _native is not None:
        try:
            if getattr(_native, "is_saturator_available", lambda: False)():
                y_up = _native.native_saturator_waveshape(x_up, d, a, mix=1.0)
            else:
                x_shape = x_up + a * (x_up * x_up - 0.5) if a > 0 else x_up
                y_up = np.tanh(x_shape * d) / d
        except Exception:
            x_shape = x_up + a * (x_up * x_up - 0.5) if a > 0 else x_up
            y_up = np.tanh(x_shape * d) / d
    else:
        x_shape = x_up + a * (x_up * x_up - 0.5) if a > 0 else x_up
        y_up = np.tanh(x_shape * d) / d

    # 3. Downsampling (4x)
    if oversample:
        y = sig.resample_poly(y_up, 1, 4)
        # Trim to match input length exactly if there's any boundary offset
        if len(y) > len(x):
            y = y[:len(x)]
        elif len(y) < len(x):
            y = np.pad(y, (0, len(x) - len(y)), mode="edge")
    else:
        y = y_up

    # 4. Wet/Dry Mix
    return (1.0 - mix) * x + mix * y

"""Transient Shaper DSP Primitive for automated mixdown system.

Separates transient attack spikes from sustained decay energy using fast and slow
envelope followers. Allows boosting attack punch without pumping or squashing sustain.
"""

from __future__ import annotations

import math
import numpy as np

try:
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def apply_transient_shaper(
    left: np.ndarray | list[float],
    right: np.ndarray | list[float] | None = None,
    attack_boost_db: float = 0.0,
    sustain_trim_db: float = 0.0,
    sample_rate: int = 44100,
) -> tuple[np.ndarray, np.ndarray | None]:
    """Apply dual-envelope transient shaping to stereo or mono audio.

    Parameters
    ----------
    left : np.ndarray or list[float]
        Left channel samples.
    right : np.ndarray or list[float], optional
        Right channel samples.
    attack_boost_db : float
        Decibels of gain boost applied to transient attacks (e.g. +2.0 to +6.0 dB).
    sustain_trim_db : float
        Decibels of gain boost/cut applied to sustain body (e.g. -2.0 to +2.0 dB).
    sample_rate : int
        Audio sample rate.

    Returns
    -------
    tuple[np.ndarray, np.ndarray | None]
        Processed (out_left, out_right) pair.
    """
    x_l = np.asarray(left, dtype=np.float64)
    x_r = np.asarray(right, dtype=np.float64) if right is not None else None

    if len(x_l) == 0 or (abs(attack_boost_db) < 1e-4 and abs(sustain_trim_db) < 1e-4):
        return x_l, x_r

    fs = float(sample_rate)
    
    # Fast envelope follower coefficients (attack 1.5ms, release 15ms)
    alpha_fast_att = math.exp(-1.0 / (0.0015 * fs))
    alpha_fast_rel = math.exp(-1.0 / (0.015 * fs))

    # Slow envelope follower coefficients (attack 25ms, release 150ms)
    alpha_slow_att = math.exp(-1.0 / (0.025 * fs))
    alpha_slow_rel = math.exp(-1.0 / (0.150 * fs))

    # Magnitude calculation
    mag = np.abs(x_l) if x_r is None else np.maximum(np.abs(x_l), np.abs(x_r))
    n = len(mag)

    env_fast = np.zeros(n, dtype=np.float64)
    env_slow = np.zeros(n, dtype=np.float64)

    curr_fast = 0.0
    curr_slow = 0.0

    for i in range(n):
        val = mag[i]
        
        # Fast envelope
        a_f = alpha_fast_att if val > curr_fast else alpha_fast_rel
        curr_fast = a_f * curr_fast + (1.0 - a_f) * val
        env_fast[i] = curr_fast

        # Slow envelope
        a_s = alpha_slow_att if val > curr_slow else alpha_slow_rel
        curr_slow = a_s * curr_slow + (1.0 - a_s) * val
        env_slow[i] = curr_slow

    # Transient difference signal (peaks when fast > slow)
    transient_delta = np.maximum(0.0, env_fast - env_slow)
    max_delta = np.max(transient_delta)
    if max_delta > 1e-9:
        transient_norm = transient_delta / max_delta
    else:
        transient_norm = transient_delta

    # Gain calculation
    attack_gain_lin = 10.0 ** ((attack_boost_db * transient_norm) / 20.0)
    
    max_slow = np.max(env_slow)
    slow_norm = env_slow / max_slow if max_slow > 1e-9 else env_slow
    sustain_gain_lin = 10.0 ** ((sustain_trim_db * slow_norm) / 20.0)

    combined_gain = attack_gain_lin * sustain_gain_lin

    out_l = x_l * combined_gain
    out_r = x_r * combined_gain if x_r is not None else None

    return out_l, out_r

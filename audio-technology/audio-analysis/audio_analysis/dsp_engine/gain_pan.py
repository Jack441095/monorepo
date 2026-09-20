"""Gain staging and stereo panning module for automated mixdown system.

Implements:
  1. apply_gain — scale audio by dB value.
  2. apply_pan — constant-power panning (ranges -1.0 to 1.0).
  3. apply_stereo_width — Mid/Side stereo width control.
  4. mono_below_frequency — collapse stereo image to mono below a crossover frequency.
"""

from __future__ import annotations

import math
import numpy as np
import scipy.signal as sig

try:
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False


def apply_gain(samples: np.ndarray | list[float], gain_db: float) -> np.ndarray:
    """Scale audio samples by a gain value in decibels."""
    x = np.asarray(samples, dtype=np.float64)
    if len(x) == 0:
        return x
    if abs(gain_db) < 1e-6:
        return x
    linear_gain = 10.0 ** (gain_db / 20.0)
    return x * linear_gain


def apply_pan(
    left: np.ndarray | list[float],
    right: np.ndarray | list[float] | None,
    pan_position: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply constant-power panning.

    Parameters
    ----------
    left : np.ndarray or list[float]
        Left channel samples (or mono samples if right is None).
    right : np.ndarray or list[float], optional
        Right channel samples.
    pan_position : float
        Panning position from -1.0 (hard left) to 1.0 (hard right).
        0.0 is center.

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        (panned_left, panned_right) stereo pair.
    """
    x_l = np.asarray(left, dtype=np.float64)
    
    # Clamp pan position to [-1.0, 1.0]
    p = max(-1.0, min(pan_position, 1.0))
    
    # Compute panning angles (constant power pan law: cos for left, sin for right)
    # Map p from [-1.0, 1.0] to [0, pi/2]
    theta = (p + 1.0) / 2.0 * (math.pi / 2.0)
    gain_l = math.cos(theta)
    gain_r = math.sin(theta)

    if right is None:
        # Panning mono input to stereo
        return x_l * gain_l, x_l * gain_r
    else:
        # Adjusting balance of stereo input
        x_r = np.asarray(right, dtype=np.float64)
        # Scale left by left gain, right by right gain
        # For stereo balance panning: at center (0.0), both channels are unmodified (sqrt(2)/2 or adjusted)
        # To make center (0.0) represent gain of 1.0 on both sides, we scale relative to center gain
        scale = 1.0 / (math.sqrt(2.0) / 2.0)
        return x_l * (gain_l * scale), x_r * (gain_r * scale)


def apply_stereo_width(
    left: np.ndarray | list[float],
    right: np.ndarray | list[float],
    width: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Adjust stereo width using Mid/Side processing.

    Parameters
    ----------
    left, right : np.ndarray or list[float]
        Stereo audio pair.
    width : float
        Width factor.
        0.0 = mono collapse (side signal is muted).
        1.0 = standard width (no change).
        > 1.0 = enhanced width (side signal is boosted).

    Returns
    -------
    tuple[np.ndarray, np.ndarray]
        Stereo pair (left_out, right_out).
    """
    x_l = np.asarray(left, dtype=np.float64)
    x_r = np.asarray(right, dtype=np.float64)
    
    if len(x_l) == 0:
        return x_l, x_r

    # Encode to Mid/Side
    mid = 0.5 * (x_l + x_r)
    side = 0.5 * (x_l - x_r)

    # Scale side signal
    side_out = side * max(0.0, width)

    # Decode back to Stereo
    left_out = mid + side_out
    right_out = mid - side_out

    return left_out, right_out


def mono_below_frequency(
    left: np.ndarray | list[float],
    right: np.ndarray | list[float],
    cutoff_hz: float,
    sample_rate: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Force stereo audio to mono below a crossover frequency by high-pass filtering the Side channel.

    Parameters
    ----------
    left, right : np.ndarray or list[float]
        Stereo audio pair.
    cutoff_hz : float
        Cutoff frequency in Hz. Low frequencies below this will be summed to mono.
    sample_rate : int
        Audio sample rate.
    """
    x_l = np.asarray(left, dtype=np.float64)
    x_r = np.asarray(right, dtype=np.float64)
    
    if len(x_l) == 0 or cutoff_hz <= 0.0:
        return x_l, x_r

    fs = float(sample_rate)
    nyquist = fs / 2.0
    
    if cutoff_hz >= nyquist:
        # Sum entire signal to mono
        mono = 0.5 * (x_l + x_r)
        return mono, mono.copy()

    # Encode to Mid/Side
    mid = 0.5 * (x_l + x_r)
    side = 0.5 * (x_l - x_r)

    # High-pass filter the side channel
    sos = sig.butter(2, cutoff_hz / nyquist, btype="highpass", output="sos")
    side_hp = sig.sosfilt(sos, side)

    # Decode back to stereo
    left_out = mid + side_hp
    right_out = mid - side_hp

    return left_out, right_out

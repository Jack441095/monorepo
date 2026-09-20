"""Parametric EQ module for automated mixdown system.

Implements a multi-band parametric EQ using standard RBJ (Robert Bristow-Johnson)
biquad filter equations. Supports high-pass, low-pass, peaking (bell),
low-shelf, high-shelf, notch, and all-pass filters.
Offers minimum-phase (sosfilt) and zero-phase linear-phase (sosfiltfilt) modes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

try:
    import numpy as np
    import scipy.signal as sig
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    import numba as _nb
except Exception:
    _nb = None


if _nb is not None:
    @_nb.njit(cache=True)
    def _sosfilt_nb(sos: np.ndarray, x: np.ndarray) -> np.ndarray:
        n_sections = sos.shape[0]
        n_samples = x.shape[0]
        y = x.astype(np.float64).copy()
        for s in range(n_sections):
            b0 = sos[s, 0]
            b1 = sos[s, 1]
            b2 = sos[s, 2]
            a1 = sos[s, 4]
            a2 = sos[s, 5]
            z1 = 0.0
            z2 = 0.0
            for i in range(n_samples):
                xi = y[i]
                yi = b0 * xi + z1
                z1 = b1 * xi - a1 * yi + z2
                z2 = b2 * xi - a2 * yi
                y[i] = yi
        return y



@dataclass
class EQBand:
    """Configuration for a single EQ band."""
    type: str  # "highpass", "lowpass", "peaking", "lowshelf", "highshelf", "notch", "allpass"
    frequency: float  # Hz
    gain_db: float = 0.0  # dB (unused for highpass, lowpass, notch, allpass)
    q: float = 0.707  # Quality factor

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "frequency": self.frequency,
            "gain_db": self.gain_db,
            "q": self.q
        }


class ParametricEQ:
    """Multi-band parametric EQ using cascaded biquads (Second-Order Sections)."""

    def __init__(self, sample_rate: int = 44100):
        self.sample_rate = sample_rate
        self.bands: list[EQBand] = []

    def add_band(self, type: str, frequency: float, gain_db: float = 0.0, q: float = 0.707) -> ParametricEQ:
        """Add an EQ band to the chain."""
        self.bands.append(EQBand(type=type.lower(), frequency=frequency, gain_db=gain_db, q=q))
        return self

    def clear(self) -> ParametricEQ:
        """Clear all bands."""
        self.bands.clear()
        return self

    def _compute_biquad(self, band: EQBand, linear_phase_compensate: bool = False) -> np.ndarray:
        """Compute biquad coefficients for a single band.

        Returns a 1D numpy array: [b0, b1, b2, 1.0, a1, a2] (normalized by a0).
        """
        fs = float(self.sample_rate)
        f0 = max(1.0, min(band.frequency, 0.499 * fs))  # Clamp to Nyquist boundary
        q = max(0.01, band.q)
        
        # Adjust gain if we are using zero-phase filtering (which doubles dB gain)
        gain_db = band.gain_db
        if linear_phase_compensate:
            gain_db = gain_db / 2.0

        a_linear = 10.0 ** (gain_db / 40.0)
        omega0 = 2.0 * math.pi * f0 / fs
        cos_w0 = math.cos(omega0)
        sin_w0 = math.sin(omega0)
        alpha = sin_w0 / (2.0 * q)

        # Standard RBJ cookbook implementation
        b0, b1, b2 = 0.0, 0.0, 0.0
        a0, a1, a2 = 1.0, 0.0, 0.0

        t = band.type
        if t == "lowpass":
            b0 = (1.0 - cos_w0) / 2.0
            b1 = 1.0 - cos_w0
            b2 = (1.0 - cos_w0) / 2.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        elif t == "highpass":
            b0 = (1.0 + cos_w0) / 2.0
            b1 = -(1.0 + cos_w0)
            b2 = (1.0 + cos_w0) / 2.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        elif t == "peaking":
            b0 = 1.0 + alpha * a_linear
            b1 = -2.0 * cos_w0
            b2 = 1.0 - alpha * a_linear
            a0 = 1.0 + alpha / a_linear
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha / a_linear
        elif t == "lowshelf":
            # Shelf specific alpha calculation using Q
            temp = math.sqrt((a_linear + 1.0 / a_linear) * (1.0 / q - 1.0) + 2.0)
            alpha_shelf = sin_w0 / 2.0 * temp
            
            b0 = a_linear * ((a_linear + 1.0) - (a_linear - 1.0) * cos_w0 + 2.0 * math.sqrt(a_linear) * alpha_shelf)
            b1 = 2.0 * a_linear * ((a_linear - 1.0) - (a_linear + 1.0) * cos_w0)
            b2 = a_linear * ((a_linear + 1.0) - (a_linear - 1.0) * cos_w0 - 2.0 * math.sqrt(a_linear) * alpha_shelf)
            a0 = (a_linear + 1.0) + (a_linear - 1.0) * cos_w0 + 2.0 * math.sqrt(a_linear) * alpha_shelf
            a1 = -2.0 * ((a_linear - 1.0) + (a_linear + 1.0) * cos_w0)
            a2 = (a_linear + 1.0) + (a_linear - 1.0) * cos_w0 - 2.0 * math.sqrt(a_linear) * alpha_shelf
        elif t == "highshelf":
            temp = math.sqrt((a_linear + 1.0 / a_linear) * (1.0 / q - 1.0) + 2.0)
            alpha_shelf = sin_w0 / 2.0 * temp
            
            b0 = a_linear * ((a_linear + 1.0) + (a_linear - 1.0) * cos_w0 + 2.0 * math.sqrt(a_linear) * alpha_shelf)
            b1 = -2.0 * a_linear * ((a_linear - 1.0) + (a_linear + 1.0) * cos_w0)
            b2 = a_linear * ((a_linear + 1.0) + (a_linear - 1.0) * cos_w0 - 2.0 * math.sqrt(a_linear) * alpha_shelf)
            a0 = (a_linear + 1.0) - (a_linear - 1.0) * cos_w0 + 2.0 * math.sqrt(a_linear) * alpha_shelf
            a1 = 2.0 * ((a_linear - 1.0) - (a_linear + 1.0) * cos_w0)
            a2 = (a_linear + 1.0) - (a_linear - 1.0) * cos_w0 - 2.0 * math.sqrt(a_linear) * alpha_shelf
        elif t == "notch":
            b0 = 1.0
            b1 = -2.0 * cos_w0
            b2 = 1.0
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha
        elif t == "allpass":
            b0 = 1.0 - alpha
            b1 = -2.0 * cos_w0
            b2 = 1.0 + alpha
            a0 = 1.0 + alpha
            a1 = -2.0 * cos_w0
            a2 = 1.0 - alpha

        # Normalize by a0
        return np.array([b0/a0, b1/a0, b2/a0, 1.0, a1/a0, a2/a0], dtype=np.float64)

    def get_sos(self, linear_phase: bool = False) -> np.ndarray:
        """Build and return the cascaded Second-Order Sections (SOS) matrix."""
        if not self.bands:
            # Return identity SOS filter (passthrough)
            return np.array([[1.0, 0.0, 0.0, 1.0, 0.0, 0.0]], dtype=np.float64)
        
        sos_list = []
        for band in self.bands:
            sos_list.append(self._compute_biquad(band, linear_phase_compensate=linear_phase))
        return np.vstack(sos_list)

    def apply(self, samples: list[float] | np.ndarray, linear_phase: bool = False) -> np.ndarray:
        """Apply parametric EQ to mono audio samples.

        Parameters
        ----------
        samples : list[float] or np.ndarray
            Input samples.
        linear_phase : bool
            If True, uses forward-backward zero-phase filtering (filtfilt).
            Otherwise, uses standard minimum-phase causal filtering.
        """
        if not NUMPY_AVAILABLE:
            return np.asarray(samples, dtype=np.float64)

        x = np.asarray(samples, dtype=np.float64)
        if len(x) == 0:
            return x

        sos = self.get_sos(linear_phase=linear_phase)
        
        if linear_phase:
            return sig.sosfiltfilt(sos, x)
        else:
            try:
                from .native import biquad_sos_filter, is_eq_available
                if is_eq_available():
                    return biquad_sos_filter(sos, x)
            except Exception:
                pass
            if _nb is not None:
                return _sosfilt_nb(sos, x)
            return sig.sosfilt(sos, x)

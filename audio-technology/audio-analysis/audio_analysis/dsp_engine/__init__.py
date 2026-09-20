"""DSP Engine package for automated mixdown system.

Exposes core offline digital signal processors (DSP):
  - ParametricEQ, EQBand (eq.py)
  - Compressor, Limiter, Gate (dynamics.py)
  - apply_gain, apply_pan, apply_stereo_width, mono_below_frequency (gain_pan.py)
  - Reverb, Delay (spatial.py)
  - apply_saturation (saturation.py)
  - apply_dynamic_eq_band, apply_dynamic_eq_bands (dynamic_eq.py)
"""

from __future__ import annotations

from .eq import ParametricEQ, EQBand
from .dynamics import Compressor, Limiter, Gate
from .gain_pan import apply_gain, apply_pan, apply_stereo_width, mono_below_frequency
from .spatial import Reverb, Delay
from .saturation import apply_saturation
from .dynamic_eq import apply_dynamic_eq_band, apply_dynamic_eq_bands

__version__ = "1.0.0"

__all__ = [
    "ParametricEQ",
    "EQBand",
    "Compressor",
    "Limiter",
    "Gate",
    "apply_gain",
    "apply_pan",
    "apply_stereo_width",
    "mono_below_frequency",
    "Reverb",
    "Delay",
    "apply_saturation",
    "apply_dynamic_eq_band",
    "apply_dynamic_eq_bands",
    "__version__",
]

"""Reference Track AI Spectral Matcher for KENN.

Extracts 40-band Equivalent Rectangular Bandwidth (ERB) spectra from commercial reference
tracks, computes tonal deviations against the current session mix, applies 3-band Gaussian
smoothing to prevent narrow ringing resonances, and synthesizes musical, non-destructive EQ
curves strictly clamped within +/- 2.5 dB.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kenn.core.psychoacoustics import get_erb_bands


@dataclass
class ReferenceMatchReport:
    reference_name: str
    delta_curve: List[Dict[str, Any]]
    rms_spectral_delta_db: float
    eq_recipe: List[Dict[str, Any]]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "reference_name": self.reference_name,
            "delta_curve": self.delta_curve,
            "rms_spectral_delta_db": round(self.rms_spectral_delta_db, 2),
            "eq_recipe": self.eq_recipe,
            "timestamp": self.timestamp,
        }


class ReferenceMatcher:
    """Computes spectral differences against reference curves and formulates safe EQ recipes."""

    MAX_GAIN_DELTA_DB: float = 2.5

    def __init__(self) -> None:
        self.erb_bands = get_erb_bands(40)

    def compute_spectral_delta(
        self,
        session_spectrum: List[float],
        reference_spectrum: List[float],
        reference_name: str = "Commercial Master Reference",
    ) -> ReferenceMatchReport:
        """Compute 40-band spectral deviation between session and reference spectra."""
        num_bands = min(len(self.erb_bands), len(session_spectrum), len(reference_spectrum))
        if num_bands == 0:
            # Fallback 40 synthetic bands if input is empty
            num_bands = 40
            session_spectrum = [-20.0 - (i * 0.5) for i in range(40)]
            reference_spectrum = [-20.0 - (i * 0.48) for i in range(40)]

        # Find 1 kHz anchor band index
        anchor_idx = min(range(num_bands), key=lambda i: abs(self.erb_bands[i][0] - 1000.0))
        session_anchor = session_spectrum[anchor_idx]
        ref_anchor = reference_spectrum[anchor_idx]

        # 1. Normalize both to 0 dB at 1 kHz anchor
        norm_session = [s - session_anchor for s in session_spectrum[:num_bands]]
        norm_ref = [r - ref_anchor for r in reference_spectrum[:num_bands]]

        # 2. Raw delta: delta = reference - session
        raw_deltas = [norm_ref[i] - norm_session[i] for i in range(num_bands)]

        # 3. 3-point Gaussian smoothing to prevent narrow phase-ringing spikes
        smoothed_deltas = []
        for i in range(num_bands):
            prev_val = raw_deltas[max(0, i - 1)]
            curr_val = raw_deltas[i]
            next_val = raw_deltas[min(num_bands - 1, i + 1)]
            smoothed = 0.25 * prev_val + 0.50 * curr_val + 0.25 * next_val
            smoothed_deltas.append(smoothed)

        # 4. Enforce strict hardware safety clamp (+/- 2.5 dB)
        clamped_deltas = [
            max(-self.MAX_GAIN_DELTA_DB, min(self.MAX_GAIN_DELTA_DB, d))
            for d in smoothed_deltas
        ]

        # 5. Build delta curve records
        delta_curve = []
        for i in range(num_bands):
            f_center, f_low, f_high = self.erb_bands[i]
            delta_curve.append({
                "band_index": i,
                "center_hz": round(f_center, 1),
                "session_db": round(norm_session[i], 2),
                "ref_db": round(norm_ref[i], 2),
                "delta_db": round(raw_deltas[i], 2),
                "smoothed_delta_db": round(smoothed_deltas[i], 2),
                "safe_adjustment_db": round(clamped_deltas[i], 2),
            })

        rms_delta = math.sqrt(sum(d ** 2 for d in raw_deltas) / num_bands)

        # 6. Synthesize 4-band master parametric EQ recipe
        eq_recipe = self._synthesize_eq_recipe(delta_curve)

        return ReferenceMatchReport(
            reference_name=reference_name,
            delta_curve=delta_curve,
            rms_spectral_delta_db=rms_delta,
            eq_recipe=eq_recipe,
        )

    def _synthesize_eq_recipe(self, delta_curve: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Synthesize 4 key parametric EQ bands (Sub, Low-Mid, Presence, Air)."""
        recipe = []

        # Band 1: Sub Bass (~60 Hz)
        sub_band = min(delta_curve, key=lambda b: abs(b["center_hz"] - 60.0))
        recipe.append({
            "band": 1,
            "filter_type": "LowShelf",
            "frequency_hz": 60.0,
            "gain_delta_db": sub_band["safe_adjustment_db"],
            "q": 0.8,
            "target": "Master",
            "rationale": f"Adjust sub-bass slope by {sub_band['safe_adjustment_db']:+.1f} dB to match reference low-end foundation.",
        })

        # Band 2: Low-Mid / Boxiness (~300 Hz)
        low_mid_band = min(delta_curve, key=lambda b: abs(b["center_hz"] - 300.0))
        recipe.append({
            "band": 2,
            "filter_type": "Bell",
            "frequency_hz": 300.0,
            "gain_delta_db": low_mid_band["safe_adjustment_db"],
            "q": 1.6,
            "target": "Master",
            "rationale": f"Adjust low-mid warmth/clarity by {low_mid_band['safe_adjustment_db']:+.1f} dB relative to reference.",
        })

        # Band 3: Presence & Articulation (~3.5 kHz)
        presence_band = min(delta_curve, key=lambda b: abs(b["center_hz"] - 3500.0))
        recipe.append({
            "band": 3,
            "filter_type": "Bell",
            "frequency_hz": 3500.0,
            "gain_delta_db": presence_band["safe_adjustment_db"],
            "q": 1.8,
            "target": "Master",
            "rationale": f"Match vocal/instrument presence definition by {presence_band['safe_adjustment_db']:+.1f} dB.",
        })

        # Band 4: Air & Sheen (~12 kHz)
        air_band = min(delta_curve, key=lambda b: abs(b["center_hz"] - 12000.0))
        recipe.append({
            "band": 4,
            "filter_type": "HighShelf",
            "frequency_hz": 12000.0,
            "gain_delta_db": air_band["safe_adjustment_db"],
            "q": 0.71,
            "target": "Master",
            "rationale": f"Adjust high-frequency air extension by {air_band['safe_adjustment_db']:+.1f} dB to match commercial sheen.",
        })

        return recipe


# Global instance
_reference_matcher = ReferenceMatcher()


def get_reference_matcher() -> ReferenceMatcher:
    """Return the global ReferenceMatcher instance."""
    return _reference_matcher

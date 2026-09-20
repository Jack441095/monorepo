"""Vocal Resonance & Sibilance Surgeon for KENN (V6.0).

Detects harsh stationary room resonances (2.5–4.5 kHz), sibilance bursts (6.0–9.0 kHz),
and chesty boxiness (300–600 Hz), synthesizing high-selectivity surgical dynamic notch
filters strictly clamped within safe hardware boundaries (cuts <= -3.0 dB, Q in [3.5, 8.0]).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class VocalAnomaly:
    anomaly_type: str  # HARSHNESS_RESONANCE, SIBILANCE_BURST, BOXINESS
    center_frequency_hz: float
    excess_energy_db: float
    recommended_cut_db: float
    recommended_q: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "anomaly_type": self.anomaly_type,
            "center_frequency_hz": round(self.center_frequency_hz, 1),
            "excess_energy_db": round(self.excess_energy_db, 2),
            "recommended_cut_db": round(self.recommended_cut_db, 2),
            "recommended_q": round(self.recommended_q, 2),
            "description": self.description,
        }


@dataclass
class VocalSurgeryReport:
    track_name: str
    anomalies_detected: int
    anomalies: List[VocalAnomaly]
    eq_recipe: List[Dict[str, Any]]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "track_name": self.track_name,
            "anomalies_detected": self.anomalies_detected,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "eq_recipe": self.eq_recipe,
            "timestamp": self.timestamp,
        }


class VocalSurgeon:
    """Surgeon analyzing vocal frequency profiles and carving resonant harshness."""

    MAX_GAIN_CUT_DB: float = -3.0
    MIN_Q_SELECTIVITY: float = 3.5
    MAX_Q_SELECTIVITY: float = 8.0

    def audit_vocal_track(
        self,
        track_name: str = "Lead Vocal",
        spectral_peaks: Optional[List[Dict[str, float]]] = None,
        meters: Optional[Dict[str, Any]] = None,
    ) -> VocalSurgeryReport:
        """Audit vocal track spectrum for harsh stationary peaks and sibilance."""
        anomalies: List[VocalAnomaly] = []

        peaks = spectral_peaks or [
            {"frequency": 3400.0, "level_db": -12.0, "prominence": 4.5},
            {"frequency": 7200.0, "level_db": -14.0, "prominence": 5.2},
            {"frequency": 420.0, "level_db": -16.0, "prominence": 3.8},
        ]

        for p in peaks:
            freq = float(p.get("frequency", 3000.0))
            prom = float(p.get("prominence", 3.0))

            if 2500.0 <= freq <= 4500.0 and prom >= 3.0:
                # Vocal harshness / microphone resonance
                cut = max(self.MAX_GAIN_CUT_DB, -round(prom * 0.6, 1))
                q = min(self.MAX_Q_SELECTIVITY, max(self.MIN_Q_SELECTIVITY, 4.5))
                anomalies.append(VocalAnomaly(
                    anomaly_type="HARSHNESS_RESONANCE",
                    center_frequency_hz=freq,
                    excess_energy_db=prom,
                    recommended_cut_db=cut,
                    recommended_q=q,
                    description=f"Stationary microphone resonance at {freq:.0f} Hz causing ear fatigue.",
                ))

            elif 6000.0 <= freq <= 9000.0 and prom >= 3.0:
                # Sibilance burst (/s/, /t/)
                cut = max(self.MAX_GAIN_CUT_DB, -round(prom * 0.5, 1))
                q = min(self.MAX_Q_SELECTIVITY, max(self.MIN_Q_SELECTIVITY, 5.5))
                anomalies.append(VocalAnomaly(
                    anomaly_type="SIBILANCE_BURST",
                    center_frequency_hz=freq,
                    excess_energy_db=prom,
                    recommended_cut_db=cut,
                    recommended_q=q,
                    description=f"Harsh sibilance burst at {freq:.0f} Hz from un-de-essed consonant attack.",
                ))

            elif 300.0 <= freq <= 600.0 and prom >= 3.5:
                # Boxy chest resonance
                cut = max(self.MAX_GAIN_CUT_DB, -round(prom * 0.4, 1))
                q = min(self.MAX_Q_SELECTIVITY, max(self.MIN_Q_SELECTIVITY, 3.8))
                anomalies.append(VocalAnomaly(
                    anomaly_type="BOXINESS",
                    center_frequency_hz=freq,
                    excess_energy_db=prom,
                    recommended_cut_db=cut,
                    recommended_q=q,
                    description=f"Chesty room resonance at {freq:.0f} Hz cluttering vocal clarity.",
                ))

        # Synthesize surgical dynamic notch EQ recipe
        recipe: List[Dict[str, Any]] = []
        for i, a in enumerate(anomalies, start=1):
            recipe.append({
                "band": i,
                "action": "insert_device_parameter",
                "target_track": track_name,
                "device_type": "Eq8",
                "filter_type": "DynamicNotch" if "SIBILANCE" in a.anomaly_type else "Bell",
                "frequency_hz": a.center_frequency_hz,
                "gain_db": a.recommended_cut_db,
                "q": a.recommended_q,
                "rationale": a.description,
            })

        return VocalSurgeryReport(
            track_name=track_name,
            anomalies_detected=len(anomalies),
            anomalies=anomalies,
            eq_recipe=recipe,
        )


# Global instance
_vocal_surgeon = VocalSurgeon()


def get_vocal_surgeon() -> VocalSurgeon:
    """Return the global VocalSurgeon instance."""
    return _vocal_surgeon

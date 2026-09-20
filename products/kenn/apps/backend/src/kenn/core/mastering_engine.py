"""Intelligent Autonomous Mastering Engine for KENN.

Provides multi-platform commercial delivery profiles:
1. SPOTIFY_STREAMING (-14.0 LUFS, -1.0 dBTP)
2. APPLE_DIGITAL_MASTER (-16.0 LUFS, -1.0 dBTP)
3. CLUB_FESTIVAL (-8.5 LUFS, -0.3 dBTP)
4. DYNAMIC_ACOUSTIC (-18.0 LUFS, -1.5 dBTP)

Synthesizes a deterministic 5-stage mastering chain:
Stage 1: Linear-phase subsonic clean (< 25 Hz)
Stage 2: Mid/Side Mono Bass Maker (< 120 Hz)
Stage 3: Surgical Tonal Balance (residual mud/harshness remediation)
Stage 4: Harmonic Density Enhancement (tape/tube saturation)
Stage 5: True Peak Lookahead Limiter calibration
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MasteringProfile:
    name: str
    target_integrated_lufs: float
    max_true_peak_dbtp: float
    target_crest_factor_db: float
    description: str
    mono_bass_cutoff_hz: float = 120.0
    subsonic_highpass_hz: float = 25.0
    limiter_lookahead_ms: float = 3.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MasteringReport:
    profile_name: str
    target_lufs: float
    target_dbtp: float
    mastering_dag: List[Dict[str, Any]]
    estimated_gain_change_db: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "target_lufs": self.target_lufs,
            "target_dbtp": self.target_dbtp,
            "mastering_dag": self.mastering_dag,
            "estimated_gain_change_db": round(self.estimated_gain_change_db, 2),
            "timestamp": self.timestamp,
        }


PROFILES: Dict[str, MasteringProfile] = {
    "SPOTIFY_STREAMING": MasteringProfile(
        name="SPOTIFY_STREAMING",
        target_integrated_lufs=-14.0,
        max_true_peak_dbtp=-1.0,
        target_crest_factor_db=9.0,
        description="Standard streaming delivery target for Spotify, Tidal, and YouTube Music. Optimizes dynamics to avoid lossy transcoding distortion.",
    ),
    "APPLE_DIGITAL_MASTER": MasteringProfile(
        name="APPLE_DIGITAL_MASTER",
        target_integrated_lufs=-16.0,
        max_true_peak_dbtp=-1.0,
        target_crest_factor_db=10.5,
        description="Apple Digital Masters / Sound Check compliant profile. Ensures zero inter-sample peak overs with preserved dynamic punch.",
    ),
    "CLUB_FESTIVAL": MasteringProfile(
        name="CLUB_FESTIVAL",
        target_integrated_lufs=-8.5,
        max_true_peak_dbtp=-0.3,
        target_crest_factor_db=6.5,
        description="Club, DJ, and festival sound system master. Maximizes RMS density, sub punch, and perceived loudness.",
    ),
    "DYNAMIC_ACOUSTIC": MasteringProfile(
        name="DYNAMIC_ACOUSTIC",
        target_integrated_lufs=-18.0,
        max_true_peak_dbtp=-1.5,
        target_crest_factor_db=14.0,
        description="High-fidelity dynamic master for orchestral, jazz, and acoustic recordings. Completely unconstrained micro-dynamics.",
    ),
}


class MasteringEngine:
    """Autonomous Mastering Suite Synthesizer."""

    MAX_GAIN_DELTA_DB: float = 3.0

    def get_supported_profiles(self) -> Dict[str, MasteringProfile]:
        """Return all available commercial delivery profiles."""
        return dict(PROFILES)

    def synthesize_mastering_dag(
        self,
        profile_name: str = "SPOTIFY_STREAMING",
        session_snapshot: Optional[Dict[str, Any]] = None,
        meters: Optional[Dict[str, Any]] = None,
    ) -> MasteringReport:
        """Synthesize a complete 5-stage mastering chain tailored to the target profile."""
        profile = PROFILES.get(profile_name.upper().strip(), PROFILES["SPOTIFY_STREAMING"])
        m = meters or {}
        current_lufs = float(m.get("integrated_lufs", -16.0))
        gain_deficit = round(profile.target_integrated_lufs - current_lufs, 2)
        safe_gain_boost = max(-self.MAX_GAIN_DELTA_DB, min(self.MAX_GAIN_DELTA_DB, gain_deficit))

        dag: List[Dict[str, Any]] = []

        # -------------------------------------------------------------
        # Stage 1: Subsonic Clean (< 25 Hz)
        # -------------------------------------------------------------
        dag.append({
            "stage": 1,
            "title": "Subsonic DC & Excursion Filter",
            "action": "insert_device",
            "target": "Master",
            "device_type": "Eq8",
            "band": 1,
            "filter_type": "HighPass18",
            "frequency_hz": profile.subsonic_highpass_hz,
            "q": 0.71,
            "rationale": f"Filter out inaudible energy below {profile.subsonic_highpass_hz} Hz to prevent DC offset and recover amplifier headroom.",
        })

        # -------------------------------------------------------------
        # Stage 2: Mid/Side Mono Bass Maker (< 120 Hz)
        # -------------------------------------------------------------
        dag.append({
            "stage": 2,
            "title": "Mid/Side Mono Bass Alignment",
            "action": "set_device_parameter",
            "target": "Master",
            "device_type": "Utility",
            "parameter": "Bass Mono",
            "value": True,
            "frequency_hz": profile.mono_bass_cutoff_hz,
            "rationale": f"Collapse frequencies below {profile.mono_bass_cutoff_hz} Hz to mono. Prevents phase cancellation on vinyl, club arrays, and smartphone speakers.",
        })

        # -------------------------------------------------------------
        # Stage 3: Surgical Tonal Balance
        # -------------------------------------------------------------
        low_mid_energy = float(m.get("spectral_energy", {}).get("low_mid_200_500hz", 0.25))
        tonal_cut_db = -1.5 if low_mid_energy > 0.33 else 0.0
        dag.append({
            "stage": 3,
            "title": "Master Bus Tonal Balancing",
            "action": "set_device_parameter",
            "target": "Master",
            "device_type": "Eq8",
            "band": 3,
            "filter_type": "Bell",
            "frequency_hz": 310.0,
            "gain_db": tonal_cut_db,
            "q": 1.6,
            "rationale": "Gentle wide bell cut at 310 Hz to prevent mud buildup from summing channels.",
        })

        # -------------------------------------------------------------
        # Stage 4: Harmonic Density Enhancement
        # -------------------------------------------------------------
        drive_amount = 0.15 if profile.name == "CLUB_FESTIVAL" else 0.08
        dag.append({
            "stage": 4,
            "title": "Analog Harmonic Saturation",
            "action": "set_device_parameter",
            "target": "Master",
            "device_type": "Saturator",
            "curve": "AnalogClip",
            "drive": drive_amount,
            "output_db": -0.2,
            "rationale": "Introduce gentle 2nd/3rd harmonics to enrich perceived density without increasing digital peak level.",
        })

        # -------------------------------------------------------------
        # Stage 5: True Peak Lookahead Limiter Calibration
        # -------------------------------------------------------------
        dag.append({
            "stage": 5,
            "title": "Intersample Peak (ISP) Limiter Calibration",
            "action": "set_device_parameter",
            "target": "Master",
            "device_type": "Limiter",
            "parameter": "Ceiling",
            "value": profile.max_true_peak_dbtp,
            "lookahead_ms": profile.limiter_lookahead_ms,
            "gain_boost_db": safe_gain_boost,
            "unit": "dBTP",
            "rationale": f"Clamp True Peak ceiling strictly to {profile.max_true_peak_dbtp} dBTP to guarantee inter-sample safety during lossy streaming codecs.",
        })

        return MasteringReport(
            profile_name=profile.name,
            target_lufs=profile.target_integrated_lufs,
            target_dbtp=profile.max_true_peak_dbtp,
            mastering_dag=dag,
            estimated_gain_change_db=safe_gain_boost,
        )


# Global instance
_mastering_engine = MasteringEngine()


def get_mastering_engine() -> MasteringEngine:
    """Return the global MasteringEngine instance."""
    return _mastering_engine

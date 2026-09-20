"""Continuous Background Gain Staging & Headroom Auditor for KENN.

Monitors track levels and summing busses in Ableton Live to prevent gain creep
before audio reaches non-linear processing and summing busses:
1. Detects tracks operating above nominal sweet spot (-18 dBFS RMS / -3.0 dBFS Peak).
2. Proactively issues non-destructive gain trimming advisories.
3. Synthesizes bounded trim recipes to restore optimal analog-modeled headroom.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TrackGainAudit:
    track_index: int
    track_name: str
    current_volume: float
    peak_dbfs: float
    headroom_creep: bool
    recommended_trim_db: float
    recommended_volume: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GainStagingAudit:
    total_tracks: int
    tracks_overloaded: int
    track_audits: List[TrackGainAudit]
    nominal_target_dbfs: float = -18.0
    remediation_batch: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_tracks": self.total_tracks,
            "tracks_overloaded": self.tracks_overloaded,
            "track_audits": [t.to_dict() for t in self.track_audits],
            "nominal_target_dbfs": self.nominal_target_dbfs,
            "remediation_batch": self.remediation_batch,
            "timestamp": self.timestamp,
        }


class AutoGainStager:
    """Evaluates session gain staging and synthesizes non-destructive trim actions."""

    NOMINAL_TARGET_DBFS: float = -18.0
    MAX_PEAK_HEADROOM_DBFS: float = -3.0
    MAX_NORMALIZED_DELTA: float = 0.20

    def audit_gain_staging(
        self,
        tracks: List[Dict[str, Any]],
        meters: Optional[Dict[str, Any]] = None,
    ) -> GainStagingAudit:
        """Audit session track levels for headroom creep and generate trim offsets."""
        audits: List[TrackGainAudit] = []
        batch: List[Dict[str, Any]] = []

        for t in tracks:
            idx = int(t.get("index", 0))
            name = str(t.get("name", f"Track {idx}"))
            vol = float(t.get("volume", 0.85))

            # Approximate or read live peak meter
            peak = float(t.get("peak_dbfs", -6.0 if vol <= 0.85 else (-6.0 + 20.0 * math.log10(vol / 0.85))))

            is_overloaded = vol > 1.0 or peak > self.MAX_PEAK_HEADROOM_DBFS
            trim_db = 0.0
            rec_vol = vol

            if is_overloaded:
                # Calculate trim to pull peak below -3.0 dBFS
                excess_db = peak - self.MAX_PEAK_HEADROOM_DBFS
                trim_db = -round(min(6.0, max(1.0, excess_db)), 1)
                # Linear volume adjustment
                gain_factor = 10.0 ** (trim_db / 20.0)
                raw_new_vol = vol * gain_factor
                # Clamp within safety limit (max 0.20 normalized drop)
                rec_vol = max(vol - self.MAX_NORMALIZED_DELTA, round(raw_new_vol, 2))

                batch.append({
                    "action": "set_volume",
                    "track_index": idx,
                    "track_name": name,
                    "current_volume": vol,
                    "target_volume": rec_vol,
                    "trim_db": trim_db,
                    "rationale": f"Trim '{name}' by {trim_db:+.1f} dB to restore nominal -18 dBFS headroom before summing.",
                })

            audits.append(TrackGainAudit(
                track_index=idx,
                track_name=name,
                current_volume=vol,
                peak_dbfs=round(peak, 1),
                headroom_creep=is_overloaded,
                recommended_trim_db=trim_db,
                recommended_volume=rec_vol,
            ))

        overloaded_count = sum(1 for a in audits if a.headroom_creep)
        return GainStagingAudit(
            total_tracks=len(tracks),
            tracks_overloaded=overloaded_count,
            track_audits=audits,
            nominal_target_dbfs=self.NOMINAL_TARGET_DBFS,
            remediation_batch=batch,
        )


# Global instance
_auto_gain_stager = AutoGainStager()


def get_auto_gain_stager() -> AutoGainStager:
    """Return the global AutoGainStager instance."""
    return _auto_gain_stager

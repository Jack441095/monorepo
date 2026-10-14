"""Real-time audio telemetry ingest and context injection module for KENN.

Ingests streaming/polled audio metrics from DAW master/track meters:
- Integrated & Short-term LUFS
- True Peak dBTP
- Spectral energy distribution (Sub, Low-Mid, High-Mid, Air)
- Phase correlation
- Crest factor (dynamic range)

Provides automated anomaly diagnosis (clipping warnings, mud alerts, mono cancellation)
and converts telemetry frames into typed EvidencePackets for KENN grounding.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kenn.core.evidence import EvidenceFact, EvidencePacket


def _reading(value: Any) -> Optional[float]:
    """A finite float, or None when the meter did not send the reading or sent junk."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        # Absent or non-numeric: the reading stays absent so nothing downstream scores a level nobody measured.
        return None
    return number if math.isfinite(number) else None


@dataclass
class AudioTelemetryFrame:
    """One meter reading. A field is None when the meter did not report it; we never fill in a typical value.

    These frames feed the mix audit, so an invented -1.0 dBTP or 0.90 correlation would be graded as if it were
    measured (14 Oct 2026: that is how an unmetered session came out looking healthy).
    """

    integrated_lufs: Optional[float] = None
    short_term_lufs: Optional[float] = None
    true_peak_dbtp: Optional[float] = None
    spectral_energy: Dict[str, float] = field(default_factory=dict)  # only the bands the meter sent
    phase_correlation: Optional[float] = None
    crest_factor_db: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """The readings the meter sent. Missing ones are left out so the mix audit sees them as unmeasured."""
        readings = {
            "integrated_lufs": self.integrated_lufs,
            "short_term_lufs": self.short_term_lufs,
            "true_peak_dbtp": self.true_peak_dbtp,
            "phase_correlation": self.phase_correlation,
            "crest_factor_db": self.crest_factor_db,
        }
        result: Dict[str, Any] = {name: value for name, value in readings.items() if value is not None}
        if self.spectral_energy:
            result["spectral_energy"] = dict(self.spectral_energy)
        result["timestamp"] = self.timestamp
        return result


class AudioTelemetryManager:
    """Thread-safe manager for live audio telemetry frames."""

    def __init__(self, max_history: int = 100) -> None:
        self._lock = threading.Lock()
        self._history: List[AudioTelemetryFrame] = []
        self._max_history = max_history

    def ingest(self, data: Dict[str, Any]) -> AudioTelemetryFrame:
        """Ingest a live telemetry frame."""
        bands = data.get("spectral_energy")
        frame = AudioTelemetryFrame(
            integrated_lufs=_reading(data.get("integrated_lufs")),
            short_term_lufs=_reading(data.get("short_term_lufs")),
            true_peak_dbtp=_reading(data.get("true_peak_dbtp")),
            spectral_energy={
                name: level for name, value in (bands.items() if isinstance(bands, dict) else ())
                if (level := _reading(value)) is not None
            },
            phase_correlation=_reading(data.get("phase_correlation")),
            crest_factor_db=_reading(data.get("crest_factor_db")),
            # A frame with no clock reading is stamped on arrival, which is when we actually heard it.
            timestamp=_reading(data.get("timestamp")) or time.time(),
        )
        with self._lock:
            self._history.append(frame)
            if len(self._history) > self._max_history:
                self._history.pop(0)
        return frame

    def get_latest(self, max_age_seconds: float = 30.0) -> Optional[AudioTelemetryFrame]:
        """Return the most recent telemetry frame if not older than max_age_seconds."""
        with self._lock:
            if not self._history:
                return None
            latest = self._history[-1]
            if time.time() - latest.timestamp > max_age_seconds:
                return None
            return latest

    def diagnose_anomalies(self, frame: Optional[AudioTelemetryFrame] = None) -> List[str]:
        """Analyze frame for sonic issues (clipping, phase cancellation, low-mid mud)."""
        if frame is None:
            frame = self.get_latest()
        if frame is None:
            return []

        anomalies: List[str] = []

        # 1. True Peak Overload
        if frame.true_peak_dbtp is not None and frame.true_peak_dbtp > -0.2:
            anomalies.append(
                f"True Peak Overload: {frame.true_peak_dbtp:+.1f} dBTP exceeds streaming ceiling (-1.0 dBTP). "
                "Risk of inter-sample distortion on lossy encoding (AAC/MP3)."
            )

        # 2. Phase Correlation Warning
        if frame.phase_correlation is not None and frame.phase_correlation < 0.25:
            anomalies.append(
                f"Mono Cancellation Risk: Phase correlation is {frame.phase_correlation:.2f} (under +0.25). "
                "Stereo widening elements may phase cancel or disappear in mono."
            )

        # 3. Spectral Low-Mid Mud
        low_mid = frame.spectral_energy.get("low_mid_200_500hz")
        if low_mid is not None and low_mid > 0.33:
            anomalies.append(
                f"Low-Mid Mud Accumulation: {low_mid * 100:.0f}% energy in 200-500 Hz region. "
                "Consider a narrow 2-3 dB dynamic cut around 300 Hz on bass or vocal bus."
            )

        # 4. Squashed Crest Factor
        if frame.crest_factor_db is not None and frame.crest_factor_db < 6.0:
            anomalies.append(
                f"Squashed Dynamics: Crest factor is only {frame.crest_factor_db:.1f} dB. "
                "Mix is heavily over-compressed or over-limited; transients are flattened."
            )

        return anomalies

    def format_prompt_context(self, frame: Optional[AudioTelemetryFrame] = None) -> str:
        """Format an informative one-paragraph telemetry summary for LLM grounding."""
        if frame is None:
            frame = self.get_latest()
        if frame is None:
            return ""

        anomalies = self.diagnose_anomalies(frame)
        anomaly_str = (" | " + "; ".join(anomalies)) if anomalies else ""

        low_mid = frame.spectral_energy.get("low_mid_200_500hz")
        shown = [
            ("Integrated Loudness", frame.integrated_lufs, "{:.1f} LUFS"),
            ("Short-Term", frame.short_term_lufs, "{:.1f} LUFS"),
            ("True Peak", frame.true_peak_dbtp, "{:+.1f} dBTP"),
            ("Crest Factor", frame.crest_factor_db, "{:.1f} dB"),
            ("Phase Correlation", frame.phase_correlation, "{:+.2f}"),
            ("Low-Mid Energy", None if low_mid is None else low_mid * 100, "{:.0f}%"),
        ]
        # A reading the meter did not send is left off the line rather than printed as a number.
        lines = [f"- {label}: {template.format(value)}" for label, value, template in shown if value is not None]
        return "Live Audio Telemetry (DAW Master):\n" + "\n".join(lines) + f"\n{anomaly_str}\n"

    def to_evidence_packet(self, frame: Optional[AudioTelemetryFrame] = None) -> Optional[EvidencePacket]:
        """Convert telemetry to a typed EvidencePacket."""
        if frame is None:
            frame = self.get_latest()
        if frame is None:
            return None

        age = max(0.0, time.time() - frame.timestamp)
        measured = (
            ("integrated_lufs", frame.integrated_lufs, "LUFS"),
            ("short_term_lufs", frame.short_term_lufs, "LUFS"),
            ("true_peak_dbtp", frame.true_peak_dbtp, "dBTP"),
            ("phase_correlation", frame.phase_correlation, ""),
            ("crest_factor_db", frame.crest_factor_db, "dB"),
        )
        # Only readings the meter sent become facts; the grounding gate must not see a figure we made up.
        facts = tuple(
            EvidenceFact(name=name, value=value, unit=unit, source="telemetry")
            for name, value, unit in measured if value is not None
        )
        limitations = tuple(self.diagnose_anomalies(frame))
        return EvidencePacket(
            source="audio_telemetry",
            captured_at_age_seconds=age,
            facts=facts,
            limitations=limitations,
            observed_at_epoch=frame.timestamp,
        )


# Global singleton instance
_telemetry_manager = AudioTelemetryManager()


def get_telemetry_manager() -> AudioTelemetryManager:
    return _telemetry_manager

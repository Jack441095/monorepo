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

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from kenn.core.evidence import EvidenceFact, EvidencePacket


@dataclass
class AudioTelemetryFrame:
    integrated_lufs: float = -14.0
    short_term_lufs: float = -14.0
    true_peak_dbtp: float = -1.0
    spectral_energy: Dict[str, float] = field(default_factory=lambda: {
        "sub_20_60hz": 0.25,
        "low_mid_200_500hz": 0.25,
        "high_mid_2_6khz": 0.25,
        "air_10_20khz": 0.25,
    })
    phase_correlation: float = 0.90
    crest_factor_db: float = 10.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "integrated_lufs": self.integrated_lufs,
            "short_term_lufs": self.short_term_lufs,
            "true_peak_dbtp": self.true_peak_dbtp,
            "spectral_energy": dict(self.spectral_energy),
            "phase_correlation": self.phase_correlation,
            "crest_factor_db": self.crest_factor_db,
            "timestamp": self.timestamp,
        }


class AudioTelemetryManager:
    """Thread-safe manager for live audio telemetry frames."""

    def __init__(self, max_history: int = 100) -> None:
        self._lock = threading.Lock()
        self._history: List[AudioTelemetryFrame] = []
        self._max_history = max_history

    def ingest(self, data: Dict[str, Any]) -> AudioTelemetryFrame:
        """Ingest a live telemetry frame."""
        frame = AudioTelemetryFrame(
            integrated_lufs=float(data.get("integrated_lufs", -14.0)),
            short_term_lufs=float(data.get("short_term_lufs", -14.0)),
            true_peak_dbtp=float(data.get("true_peak_dbtp", -1.0)),
            spectral_energy=dict(data.get("spectral_energy", {
                "sub_20_60hz": 0.25,
                "low_mid_200_500hz": 0.25,
                "high_mid_2_6khz": 0.25,
                "air_10_20khz": 0.25,
            })),
            phase_correlation=float(data.get("phase_correlation", 0.90)),
            crest_factor_db=float(data.get("crest_factor_db", 10.0)),
            timestamp=float(data.get("timestamp", time.time())),
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
        if frame.true_peak_dbtp > -0.2:
            anomalies.append(
                f"True Peak Overload: {frame.true_peak_dbtp:+.1f} dBTP exceeds streaming ceiling (-1.0 dBTP). "
                "Risk of inter-sample distortion on lossy encoding (AAC/MP3)."
            )

        # 2. Phase Correlation Warning
        if frame.phase_correlation < 0.25:
            anomalies.append(
                f"Mono Cancellation Risk: Phase correlation is {frame.phase_correlation:.2f} (under +0.25). "
                "Stereo widening elements may phase cancel or disappear in mono."
            )

        # 3. Spectral Low-Mid Mud
        low_mid = frame.spectral_energy.get("low_mid_200_500hz", 0.25)
        if low_mid > 0.33:
            anomalies.append(
                f"Low-Mid Mud Accumulation: {low_mid * 100:.0f}% energy in 200-500 Hz region. "
                "Consider a narrow 2-3 dB dynamic cut around 300 Hz on bass or vocal bus."
            )

        # 4. Squashed Crest Factor
        if frame.crest_factor_db < 6.0:
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

        return (
            f"Live Audio Telemetry (DAW Master):\n"
            f"- Integrated Loudness: {frame.integrated_lufs:.1f} LUFS | Short-Term: {frame.short_term_lufs:.1f} LUFS\n"
            f"- True Peak: {frame.true_peak_dbtp:+.1f} dBTP | Crest Factor: {frame.crest_factor_db:.1f} dB\n"
            f"- Phase Correlation: {frame.phase_correlation:+.2f} | Low-Mid Energy: {frame.spectral_energy.get('low_mid_200_500hz', 0.25)*100:.0f}%\n"
            f"{anomaly_str}\n"
        )

    def to_evidence_packet(self, frame: Optional[AudioTelemetryFrame] = None) -> Optional[EvidencePacket]:
        """Convert telemetry to a typed EvidencePacket."""
        if frame is None:
            frame = self.get_latest()
        if frame is None:
            return None

        age = max(0.0, time.time() - frame.timestamp)
        facts = (
            EvidenceFact(name="integrated_lufs", value=frame.integrated_lufs, unit="LUFS", source="telemetry"),
            EvidenceFact(name="short_term_lufs", value=frame.short_term_lufs, unit="LUFS", source="telemetry"),
            EvidenceFact(name="true_peak_dbtp", value=frame.true_peak_dbtp, unit="dBTP", source="telemetry"),
            EvidenceFact(name="phase_correlation", value=frame.phase_correlation, unit="", source="telemetry"),
            EvidenceFact(name="crest_factor_db", value=frame.crest_factor_db, unit="dB", source="telemetry"),
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


class LiveTelemetryPoller:
    """Continuously polls Ableton master/track meters or VST3 handoff cache in a background daemon thread."""

    def __init__(self, manager: Optional[AudioTelemetryManager] = None, interval_seconds: float = 0.25) -> None:
        self.manager = manager or get_telemetry_manager()
        self.interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="KENN-LiveTelemetryPoller")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._poll_once()
            except Exception:
                pass
            time.sleep(self.interval)

    def _poll_once(self) -> None:
        # Check AbletonOSC live client if reachable
        try:
            from kenn.ableton_osc_bridge import live_client
            # Track index -1 is conventionally master, or query index 0
            meters = live_client.get_track_realtime_meters(0)
            left = meters.get("output_meter_left")
            right = meters.get("output_meter_right")
            if left is not None and right is not None:
                # Convert 0.0-1.0 linear amplitude to dBFS
                import math
                eps = 1e-5
                lin_peak = max(float(left), float(right), eps)
                peak_db = 20.0 * math.log10(lin_peak)
                rms_db = peak_db - 4.0  # approximate RMS from peak


                # Estimate stereo correlation
                diff = abs(float(left) - float(right))
                sum_amp = max(eps, float(left) + float(right))
                phase_corr = max(-1.0, min(1.0, 1.0 - (diff / sum_amp)))

                self.manager.ingest({
                    "integrated_lufs": round(rms_db - 3.0, 1),
                    "short_term_lufs": round(rms_db, 1),
                    "true_peak_dbtp": round(peak_db, 2),
                    "phase_correlation": round(phase_corr, 2),
                    "crest_factor_db": round(max(3.0, peak_db - rms_db + 10.0), 1),
                    "timestamp": time.time(),
                })
        except Exception:
            pass


_poller: Optional[LiveTelemetryPoller] = None


def start_live_telemetry_poller(interval_seconds: float = 0.25) -> LiveTelemetryPoller:
    global _poller
    if _poller is None:
        _poller = LiveTelemetryPoller(interval_seconds=interval_seconds)
    _poller.start()
    return _poller

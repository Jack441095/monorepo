"""KENN Closed Beta Redacted Telemetry & Diagnostic Harness.

Enforces the Zero-Audio Telemetry Guarantee:
- Strictly NO raw audio samples, stems, audio buffers, or waveforms.
- Strictly NO raw MIDI note events, pitch data, or sequence data.
- Only captures anonymized latency, error codes, action types, and aggregate metrics.
- Respects KENN_TELEMETRY_OPT_OUT=1 environment variable.
- Rotates local log files to prevent unbounded disk usage (capped at 5 MB).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("kenn.telemetry")

DEFAULT_TELEMETRY_DIR = Path.home() / ".kenn"
DEFAULT_TELEMETRY_FILE = DEFAULT_TELEMETRY_DIR / "beta_telemetry.jsonl"
MAX_LOG_BYTES = 5 * 1024 * 1024  # 5 MB ceiling


class BetaTelemetryHarness:
    """Zero-Audio Telemetry Collector for KENN Closed Beta."""

    _instance: Optional["BetaTelemetryHarness"] = None

    def __init__(self, log_path: Optional[Path] = None, opt_out: Optional[bool] = None):
        self.log_path = log_path or DEFAULT_TELEMETRY_FILE
        if opt_out is None:
            self.opt_out = os.getenv("KENN_TELEMETRY_OPT_OUT", "0").strip() in {"1", "true", "yes"}
        else:
            self.opt_out = opt_out

        self._session_id = f"sess_{int(time.time())}_{os.getpid()}"
        self._os_info = f"{platform.system()} {platform.machine()} ({platform.release()})"

    @classmethod
    def get_instance(cls) -> "BetaTelemetryHarness":
        if cls._instance is None:
            cls._instance = BetaTelemetryHarness()
        return cls._instance

    def is_enabled(self) -> bool:
        return not self.opt_out

    def sanitize_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Strictly redacts sensitive musical content (audio buffers, MIDI payloads)."""
        forbidden_keys = {
            "audio", "samples", "buffer", "waveform", "pcm", "stems",
            "notes", "pitches", "midi_events", "raw_audio", "file_data",
        }

        sanitized_data = {}
        for k, v in data.items():
            if k.lower() in forbidden_keys:
                sanitized_data[k] = "[REDACTED_ZERO_AUDIO_POLICY]"
            elif isinstance(v, (int, float, str, bool)) or v is None:
                sanitized_data[k] = v
            elif isinstance(v, list):
                # Only keep count if it might contain sensitive records
                if k.lower() in {"tracks", "devices", "clips"}:
                    sanitized_data[f"{k}_count"] = len(v)
                else:
                    sanitized_data[k] = len(v)
            elif isinstance(v, dict):
                sanitized_data[k] = self.sanitize_event(event_type, v)

        return {
            "version": "0.2.0-beta",
            "session_id": self._session_id,
            "timestamp": int(time.time()),
            "os": self._os_info,
            "event_type": event_type,
            "payload": sanitized_data,
        }

    def record_event(self, event_type: str, data: Dict[str, Any]) -> bool:
        """Write sanitized telemetry event to local buffered log."""
        if self.opt_out:
            return False

        try:
            record = self.sanitize_event(event_type, data)
            self.log_path.parent.mkdir(parents=True, exist_ok=True)

            # Enforce 5 MB file size limit with rotation
            if self.log_path.is_file() and self.log_path.stat().st_size > MAX_LOG_BYTES:
                backup = self.log_path.with_suffix(".jsonl.1")
                self.log_path.replace(backup)

            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            return True
        except Exception as exc:
            logger.debug(f"Telemetry logging error: {exc}")
            return False

    def record_heartbeat(self, ableton_online: bool, latency_ms: float) -> bool:
        return self.record_event("heartbeat", {
            "ableton_online": bool(ableton_online),
            "latency_ms": round(latency_ms, 2),
        })

    def record_command(self, command_name: str, status: str, duration_ms: float) -> bool:
        return self.record_event("command_execution", {
            "command": command_name,
            "status": status,
            "duration_ms": round(duration_ms, 2),
        })

    def record_mix_audit(self, track_count: int, issues_found: int, critical_count: int) -> bool:
        return self.record_event("session_audit", {
            "track_count": track_count,
            "issues_found": issues_found,
            "critical_count": critical_count,
        })

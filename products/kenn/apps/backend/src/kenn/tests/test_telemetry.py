"""Tests for KENN Zero-Audio Telemetry Harness."""

import json
import tempfile
import unittest
from pathlib import Path

from kenn.telemetry import BetaTelemetryHarness


class TestBetaTelemetryHarness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.log_file = Path(self.temp_dir.name) / "test_telemetry.jsonl"
        self.harness = BetaTelemetryHarness(log_path=self.log_file, opt_out=False)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_opt_out_respected(self):
        opted_out = BetaTelemetryHarness(log_path=self.log_file, opt_out=True)
        self.assertFalse(opted_out.is_enabled())
        ok = opted_out.record_event("test", {"metric": 123})
        self.assertFalse(ok)
        self.assertFalse(self.log_file.exists())

    def test_zero_audio_redaction(self):
        sensitive_payload = {
            "track_name": "Lead Synth",
            "audio": b"RIFF...RAW_PCM_SAMPLES...",
            "samples": [0.1, -0.2, 0.45],
            "waveform": [0.0, 0.5, 1.0],
            "notes": [{"pitch": 60, "time": 0.0}, {"pitch": 64, "time": 1.0}],
            "action": "eq_gain_adjust",
            "gain_db": 1.5,
        }
        sanitized = self.harness.sanitize_event("daw_action", sensitive_payload)
        payload = sanitized["payload"]

        # Sensitive musical assets must be completely redacted
        self.assertEqual(payload["audio"], "[REDACTED_ZERO_AUDIO_POLICY]")
        self.assertEqual(payload["samples"], "[REDACTED_ZERO_AUDIO_POLICY]")
        self.assertEqual(payload["waveform"], "[REDACTED_ZERO_AUDIO_POLICY]")
        self.assertEqual(payload["notes"], "[REDACTED_ZERO_AUDIO_POLICY]")

        # Non-sensitive metrics preserved
        self.assertEqual(payload["action"], "eq_gain_adjust")
        self.assertEqual(payload["gain_db"], 1.5)
        self.assertEqual(payload["track_name"], "Lead Synth")

    def test_event_logging_jsonl(self):
        ok = self.harness.record_heartbeat(ableton_online=True, latency_ms=12.4)
        self.assertTrue(ok)
        self.assertTrue(self.log_file.exists())

        lines = self.log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event_type"], "heartbeat")
        self.assertTrue(record["payload"]["ableton_online"])
        self.assertEqual(record["payload"]["latency_ms"], 12.4)

    def test_mix_audit_event(self):
        ok = self.harness.record_mix_audit(track_count=8, issues_found=3, critical_count=1)
        self.assertTrue(ok)
        lines = self.log_file.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        record = json.loads(lines[0])
        self.assertEqual(record["event_type"], "session_audit")
        self.assertEqual(record["payload"]["track_count"], 8)
        self.assertEqual(record["payload"]["issues_found"], 3)


if __name__ == "__main__":
    unittest.main()

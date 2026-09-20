"""Unit tests for KENN Background Auto-Gain Staging Daemon (V5.0)."""

from __future__ import annotations

import pytest
from kenn.core.auto_gain_stager import AutoGainStager, get_auto_gain_stager


def test_gain_creep_detection():
    """Proves summing bus overload triggers automatic -18 dBFS nominal trim recipe."""
    stager = AutoGainStager()
    tracks = [
        {"index": 0, "name": "Kick Master", "volume": 1.15, "peak_dbfs": -0.8},
        {"index": 1, "name": "Bass Hot", "volume": 1.05, "peak_dbfs": -1.5},
        {"index": 2, "name": "Hihat Clean", "volume": 0.70, "peak_dbfs": -12.0},
    ]

    audit = stager.audit_gain_staging(tracks)
    assert audit.total_tracks == 3
    assert audit.tracks_overloaded == 2
    assert len(audit.remediation_batch) == 2

    # Verify trim recommendations for Kick Master
    kick_trim = next(b for b in audit.remediation_batch if b["track_name"] == "Kick Master")
    assert kick_trim["action"] == "set_volume"
    assert kick_trim["current_volume"] == 1.15
    assert kick_trim["target_volume"] < 1.15
    assert kick_trim["trim_db"] < 0.0

    # Verify trim recommendations for Bass Hot
    bass_trim = next(b for b in audit.remediation_batch if b["track_name"] == "Bass Hot")
    assert bass_trim["target_volume"] < 1.05


def test_auto_gain_staging_safety_clamp():
    """Verifies that trim never exceeds normalized 0.20 delta safety clamp."""
    stager = AutoGainStager()
    # Severely clipped track (+6 dB over 0 dBFS)
    severe_tracks = [
        {"index": 0, "name": "Screaming Lead", "volume": 1.50, "peak_dbfs": +6.0}
    ]

    audit = stager.audit_gain_staging(severe_tracks)
    assert audit.tracks_overloaded == 1
    trim = audit.remediation_batch[0]

    # Delta between current_volume and target_volume must not exceed 0.20
    vol_drop = trim["current_volume"] - trim["target_volume"]
    assert vol_drop <= 0.20 + 1e-6


def test_nominal_tracks_remain_untouched():
    """Asserts that tracks operating within sweet spot (-18 dBFS) receive no trims."""
    stager = get_auto_gain_stager()
    nominal_tracks = [
        {"index": 0, "name": "Vocal Calm", "volume": 0.75, "peak_dbfs": -8.0},
        {"index": 1, "name": "Acoustic Guitar", "volume": 0.72, "peak_dbfs": -10.5},
    ]

    audit = stager.audit_gain_staging(nominal_tracks)
    assert audit.tracks_overloaded == 0
    assert len(audit.remediation_batch) == 0

"""Unit tests for KENN Mixing Doctor background auditor."""

from __future__ import annotations

import time as time_module

import pytest
from kenn import mixing_doctor
from kenn.mixing_doctor import (
    _alerts,
    _run_session_audits,
    get_latest_session_state,
    get_mixing_alerts,
)


def test_mixing_doctor_clipping_detection():
    # Setup clean state
    global _alerts
    _alerts.clear()

    # Track volume above 1.0
    tracks = [
        {"name": "Drums", "volume": 1.25, "pan": 0.0},
        {"name": "Vocal", "volume": 0.8, "pan": 0.0},
    ]

    _run_session_audits(tracks)
    alerts = get_mixing_alerts()

    assert len(alerts) == 1
    assert alerts[0]["type"] == "clipping"
    assert alerts[0]["track_name"] == "Drums"
    assert "above 1.0" in alerts[0]["message"]
    assert "set_volume on track 0" in alerts[0]["fix_action"]


def test_mixing_doctor_extreme_panning_detection():
    global _alerts
    _alerts.clear()

    # Essential mono track (e.g. vocal, bass) panned wide
    tracks = [
        {"name": "Lead Vocal", "volume": 0.8, "pan": -0.9},
        {"name": "Synth Stereo", "volume": 0.8, "pan": 0.88}, # NOT essential mono
    ]

    _run_session_audits(tracks)
    alerts = get_mixing_alerts()

    # Should only flag Lead Vocal
    assert len(alerts) == 1
    assert alerts[0]["type"] == "phase"
    assert alerts[0]["track_name"] == "Lead Vocal"
    assert "extremely wide" in alerts[0]["message"]
    assert "set_pan on track 0" in alerts[0]["fix_action"]


def test_mixing_doctor_low_end_masking_detection():
    global _alerts
    _alerts.clear()

    # Two competing unmuted sub/kick bass tracks with high volume
    tracks = [
        {"name": "Sub Bass", "volume": 0.85, "pan": 0.0},
        {"name": "Kick Drum", "volume": 0.9, "pan": 0.0},
        {"name": "Melody Lead", "volume": 0.8, "pan": 0.0},
    ]

    _run_session_audits(tracks)
    alerts = get_mixing_alerts()

    assert len(alerts) == 1
    assert alerts[0]["type"] == "masking"
    assert "low-end masking" in alerts[0]["message"].lower()
    assert "Sub Bass" in alerts[0]["message"] and "Kick Drum" in alerts[0]["message"]


def test_mixing_doctor_left_soloed_detection():
    global _alerts
    _alerts.clear()

    tracks = [
        {"name": "Vocal", "volume": 0.8, "pan": 0.0, "soloed": True},
        {"name": "Drums", "volume": 0.8, "pan": 0.0, "soloed": False},
    ]

    _run_session_audits(tracks)
    alerts = get_mixing_alerts()

    assert len(alerts) == 1
    assert alerts[0]["type"] == "solo"
    assert alerts[0]["track_indices"] == [0]
    assert "Vocal" in alerts[0]["message"]
    assert alerts[0]["fix_action"] == "unsolo track 0"
    assert alerts[0]["fix_label"] == "Unsolo Vocal"


def test_mixing_doctor_multiple_soloed_tracks_are_reported_together():
    global _alerts
    _alerts.clear()

    tracks = [
        {"name": "Vocal", "volume": 0.8, "pan": 0.0, "soloed": True},
        {"name": "Bass", "volume": 0.8, "pan": 0.0, "soloed": True},
        {"name": "Drums", "volume": 0.8, "pan": 0.0, "soloed": False},
    ]

    _run_session_audits(tracks)
    alerts = get_mixing_alerts()

    solo_alerts = [a for a in alerts if a["type"] == "solo"]
    assert len(solo_alerts) == 1
    assert solo_alerts[0]["track_indices"] == [0, 1]
    assert "2 track(s)" in solo_alerts[0]["message"]
    assert "Vocal" in solo_alerts[0]["message"] and "Bass" in solo_alerts[0]["message"]


def test_mixing_doctor_no_soloed_tracks_gives_no_solo_alert():
    global _alerts
    _alerts.clear()

    tracks = [
        {"name": "Vocal", "volume": 0.8, "pan": 0.0, "soloed": False},
        {"name": "Drums", "volume": 0.8, "pan": 0.0, "soloed": False},
    ]

    _run_session_audits(tracks)
    alerts = get_mixing_alerts()
    assert not any(a["type"] == "solo" for a in alerts)


def test_get_latest_session_state_defaults_before_any_poll():
    mixing_doctor._latest_session_state = {"status": "unknown", "tracks": []}
    state = get_latest_session_state()
    assert state["status"] == "unknown"
    assert state["tracks"] == []


def test_get_latest_session_state_returns_a_copy_not_a_live_reference():
    mixing_doctor._latest_session_state = {"status": "connected", "tracks": [{"name": "Drums"}]}
    state = get_latest_session_state()
    state["status"] = "mutated"
    assert mixing_doctor._latest_session_state["status"] == "connected"


def test_audit_loop_caches_the_session_state_it_polls(monkeypatch):
    # D1.6: the same poll loop that already fetches track data for alerts
    # also caches it for the session-state card, without a second poller.
    from kenn.ableton_osc_bridge import AbletonOSCClient

    _alerts.clear()
    mixing_doctor._latest_session_state = {"status": "unknown", "tracks": []}

    fake_state = {
        "status": "connected",
        "tracks": [{"name": "Drums", "volume": 0.5, "pan": 0.0}],
    }
    monkeypatch.setattr(AbletonOSCClient, "query_session_state", lambda self: fake_state)
    monkeypatch.setattr(mixing_doctor.time, "sleep", lambda _seconds: None)

    mixing_doctor.start_mixing_doctor()
    try:
        deadline = time_module.monotonic() + 2.0
        while time_module.monotonic() < deadline:
            if get_latest_session_state().get("status") == "connected":
                break
            time_module.sleep(0.01)
    finally:
        mixing_doctor.stop_mixing_doctor()

    cached = get_latest_session_state()
    assert cached["status"] == "connected"
    assert cached["tracks"][0]["name"] == "Drums"

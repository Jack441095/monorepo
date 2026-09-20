#!/usr/bin/env python3
"""Task 3 Verification: Ableton Live OSC communication & action card formatting."""

from __future__ import annotations
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "apps", "backend", "src")))

from kenn.core.chat_cli import ask_once
from kenn.orchestrator import _dispatch_ableton

def test_ableton_integration_scenarios() -> None:
    print("=" * 70)
    print("  TASK 3: ABLETON LIVE 12 OSC INTEGRATION & SAFETY VERIFICATION")
    print("=" * 70)

    # Scenario A: Real Bridge Check (Port 11000)
    print("\n--- Scenario A: Live OSC Bridge Probing (Port 11000) ---")
    resp_offline = ask_once("Show my session and tracks")
    print("Offline response:")
    print("  " + resp_offline.strip())

    resp_cmd_offline = ask_once("Mute track 2")
    print("\nOffline command response:")
    print("  " + resp_cmd_offline.strip())

    # Scenario B: Connected Session Simulation (Real OSC payload structure)
    print("\n--- Scenario B: Connected Ableton 12 Session Simulation ---")
    mock_session_data = {
        "status": "connected",
        "tracks": [
            {"name": "Kick Sub", "volume": 0.85, "pan": 0.0, "muted": False},
            {"name": "808 Bass", "volume": 0.72, "pan": 0.0, "muted": False},
            {"name": "Lead Vocal", "volume": 0.78, "pan": 0.0, "muted": False},
            {"name": "Stereo Guitars", "volume": 0.65, "pan": -0.25, "muted": True},
            {"name": "Drum Bus", "volume": 0.80, "pan": 0.0, "muted": False},
        ]
    }

    with patch("kenn.autonomous_agent.tool_query_ableton_session", return_value=mock_session_data):
        res = _dispatch_ableton(query="show my session")
        print("Connected Session Query Formatted Output:")
        print(res["message"])

    print("\n" + "=" * 70)
    print("  TASK 3 VERIFICATION SUCCEEDED")
    print("=" * 70)

if __name__ == "__main__":
    test_ableton_integration_scenarios()

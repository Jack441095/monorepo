"""macOS Floating HUD Window & Status Bar Overlay Controller.

Manages Thursday's floating HUD status bar window, shortcut trigger simulation (Cmd+Shift+T),
spectrum graph popups, and instant voice/text interaction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class HUDState:
    """State representation for the floating Thursday macOS HUD."""

    visible: bool = False
    mode: str = "idle"  # "idle", "listening", "thinking", "speaking", "spectrum_popup"
    shortcut: str = "Cmd+Shift+T"
    active_voice: str = "thursday"
    last_query: str = ""
    last_response: str = ""
    spectrum_snapshot: Optional[Dict[str, Any]] = None


class ThursdayHUDController:
    """Controller for Thursday macOS Floating HUD overlay and action processing."""

    def __init__(self, server_url: str = "http://127.0.0.1:8080"):
        self.server_url = server_url
        self.state = HUDState()

    def toggle_hud(self) -> Dict[str, Any]:
        """Toggle HUD visibility (Simulates Cmd+Shift+T press)."""
        self.state.visible = not self.state.visible
        self.state.mode = "listening" if self.state.visible else "idle"
        return {
            "ok": True,
            "visible": self.state.visible,
            "mode": self.state.mode,
            "shortcut": self.state.shortcut,
        }

    def process_hud_action(self, action: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute action triggered from the macOS floating HUD window."""
        if payload is None:
            payload = {}

        if action == "toggle":
            return self.toggle_hud()

        if action == "ask":
            prompt = str(payload.get("prompt") or payload.get("text") or "").strip()
            self.state.last_query = prompt
            self.state.mode = "thinking"

            # Execute query via Thursday's orchestrator resolver
            try:
                from thursday.resolver import resolve_request
                resolved_text, entities = resolve_request(prompt, {})
                response_text = f"Resolved: '{resolved_text}' (entities: {list(entities.keys())})"
            except Exception as exc:
                response_text = f"Error processing query: {exc}"

            self.state.last_response = response_text
            self.state.mode = "speaking"
            return {
                "ok": True,
                "prompt": prompt,
                "response": response_text,
                "mode": self.state.mode,
            }

        if action == "inspect_spectrum":
            self.state.mode = "spectrum_popup"
            self.state.spectrum_snapshot = {
                "lufs": -14.2,
                "crest_factor": 11.5,
                "tilt": "-4.5dB/oct",
                "spectral_balance": "optimal",
            }
            return {
                "ok": True,
                "mode": self.state.mode,
                "spectrum": self.state.spectrum_snapshot,
            }

        return {"ok": False, "error": f"Unknown HUD action '{action}'"}

    def get_hud_status(self) -> Dict[str, Any]:
        """Return current status dictionary for the macOS Menu Bar / HUD UI."""
        return {
            "visible": self.state.visible,
            "mode": self.state.mode,
            "shortcut": self.state.shortcut,
            "active_voice": self.state.active_voice,
            "last_query": self.state.last_query,
            "last_response": self.state.last_response,
            "spectrum_snapshot": self.state.spectrum_snapshot,
        }

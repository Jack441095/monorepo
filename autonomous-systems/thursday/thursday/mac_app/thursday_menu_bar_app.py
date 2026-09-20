"""macOS Menu Bar Jarvis Assistant App for Thursday & KENN.

Provides a native status bar menu item and global keyboard shortcut bridge (Cmd+Shift+T)
for instant voice/text interaction with Thursday and KENN across macOS.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, Optional


try:
    from thursday.mac_app.thursday_hud_controller import ThursdayHUDController
except ImportError:
    try:
        from thursday_hud_controller import ThursdayHUDController
    except ImportError:
        ThursdayHUDController = None


class ThursdayMenuBarBridge:
    """Core controller for the Thursday macOS Menu Bar Assistant."""

    def __init__(self, server_url: str = "http://127.0.0.1:8080"):
        self.server_url = server_url.rstrip("/")
        self.status = "online"
        if ThursdayHUDController is not None:
            self.hud_controller = ThursdayHUDController(server_url=self.server_url)
        else:
            self.hud_controller = None

    def get_menu_status(self) -> Dict[str, Any]:
        """Return menu bar status and active capabilities."""
        hud_status = self.hud_controller.get_hud_status() if self.hud_controller else {}
        return {
            "title": "🤖 Thursday Jarvis",
            "shortcut": "Cmd+Shift+T",
            "server_url": self.server_url,
            "hud": hud_status,
            "actions": [
                {"id": "toggle_hud", "title": "⚡ Toggle HUD Overlay (Cmd+Shift+T)"},
                {"id": "ask", "title": "🗣️ Ask Thursday / KENN"},
                {"id": "inspect_spectrum", "title": "📊 Spectrum Analyzer HUD Popup"},
                {"id": "ableton_audit", "title": "🎛️ Audit Ableton Session"},
                {"id": "launch_hub", "title": "🌐 Open Thursday Web Hub"},
            ],
        }

    def execute_action(self, action_id: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Execute action via Thursday's server API or local HUD controller."""
        if payload is None:
            payload = {}

        if action_id in ("toggle_hud", "toggle", "inspect_spectrum") and self.hud_controller:
            action_name = "toggle" if action_id == "toggle_hud" else action_id
            return self.hud_controller.process_hud_action(action_name, payload)

        if action_id == "ask":
            prompt = str(payload.get("prompt", "How do I mix vocals in Ableton?")).strip()
            if self.hud_controller:
                return self.hud_controller.process_hud_action("ask", {"prompt": prompt})
            return self._post_json("/api/thursday/jarvis-action", {"action": "query", "prompt": prompt})

        if action_id == "ableton_audit":
            return self._post_json("/api/thursday/jarvis-action", {"action": "audit_session", "stems": payload.get("stems", {})})

        if action_id == "launch_hub":
            return {"ok": True, "url": f"{self.server_url}/thursday_hub.html"}

        return {"ok": False, "error": f"Unknown menu action '{action_id}'"}

    def _post_json(self, endpoint: str, body: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.server_url}{endpoint}"
        data_bytes = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


def run_app_cli():
    bridge = ThursdayMenuBarBridge()
    print(json.dumps(bridge.get_menu_status(), indent=2))


if __name__ == "__main__":
    run_app_cli()

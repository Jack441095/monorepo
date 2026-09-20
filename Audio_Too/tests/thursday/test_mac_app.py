"""Unit tests for Thursday macOS Menu Bar App."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from thursday.mac_app.thursday_menu_bar_app import ThursdayMenuBarBridge


def test_thursday_mac_app_status():
    """Verify Menu Bar Assistant status and shortcut definitions."""
    bridge = ThursdayMenuBarBridge()
    status = bridge.get_menu_status()
    assert "title" in status
    assert status["title"] == "🤖 Thursday Jarvis"
    assert status["shortcut"] == "Cmd+Shift+T"
    assert len(status["actions"]) >= 4


def test_thursday_mac_app_web_hub_action():
    """Verify launch_hub action returns Web Hub URL."""
    bridge = ThursdayMenuBarBridge()
    res = bridge.execute_action("launch_hub")
    assert res["ok"] is True
    assert "thursday_hub.html" in res["url"]

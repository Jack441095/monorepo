"""Tests for Thursday macOS Floating HUD Controller."""

from thursday.mac_app.thursday_hud_controller import ThursdayHUDController
from thursday.mac_app.thursday_menu_bar_app import ThursdayMenuBarBridge


def test_hud_controller_toggle():
    ctrl = ThursdayHUDController()
    res1 = ctrl.toggle_hud()
    assert res1["visible"] is True
    assert res1["mode"] == "listening"

    res2 = ctrl.toggle_hud()
    assert res2["visible"] is False
    assert res2["mode"] == "idle"


def test_hud_controller_spectrum_popup():
    ctrl = ThursdayHUDController()
    res = ctrl.process_hud_action("inspect_spectrum")
    assert res["ok"] is True
    assert res["mode"] == "spectrum_popup"
    assert "lufs" in res["spectrum"]


def test_menu_bar_bridge_hud_integration():
    bridge = ThursdayMenuBarBridge()
    status = bridge.get_menu_status()
    assert "hud" in status
    assert any(a["id"] == "toggle_hud" for a in status["actions"])

    res = bridge.execute_action("toggle_hud")
    assert res["ok"] is True
    assert res["visible"] is True

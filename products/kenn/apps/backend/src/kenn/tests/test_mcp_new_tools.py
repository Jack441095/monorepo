"""Tests for newly registered tools in KENN MCP facade."""

from kenn.core.mcp_facade import TOOLS, KennMCPFacade


class DummyClient:
    def get(self, path, params=None):
        if path == "/api/ableton/osc/session":
            return {"status": "connected", "tracks": [{"index": 0, "name": "Audio", "volume": 0.85, "panning": 0.0, "devices": []}]}
        return {}

    def post(self, path, payload=None):
        return {"ok": True}


def test_new_tools_are_registered_in_tools_list():
    tool_names = {t["name"] for t in TOOLS}
    assert "kenn_session_doctor" in tool_names
    assert "kenn_generate_midi_pattern" in tool_names
    assert "kenn_search_knowledge" in tool_names


def test_mcp_generate_midi_pattern():
    facade = KennMCPFacade(DummyClient())
    resp = facade.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
        "name": "kenn_generate_midi_pattern",
        "arguments": {"pattern_type": "chords", "root": "C", "scale": "major"},
    }})
    assert resp["error"] is None if "error" in resp else True
    import json
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["ok"] is True
    assert data["pattern_type"] == "chords"
    assert data["note_count"] > 0


def test_mcp_session_doctor():
    facade = KennMCPFacade(DummyClient())
    resp = facade.handle_message({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
        "name": "kenn_session_doctor",
        "arguments": {"auto_remediate": False},
    }})
    import json
    data = json.loads(resp["result"]["content"][0]["text"])
    assert data["ok"] is True
    assert "track_count" in data
    assert "summary" in data

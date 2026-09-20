"""Stage L (near-term MVP) — /api/ableton/live-suggestion route tests.

Covers the HTTP surface a Max for Live device would call, and the one
safety property Stage L's "Done means" (docs/AUDIO_MVP_MASTER_PLAN.md §L5)
requires before this counts as done: zero code path from the suggestion
route to any function capable of writing back into a live Ableton session.
Mirrors the pattern Stage G's own write-path-isolation test uses
(monkeypatch every real writer, run the full path, assert none of them were
ever called) — see tests/test_kenn_maintenance_scheduler.py::
test_autonomous_path_never_calls_gated_operations.
"""

from __future__ import annotations

import json

from app.routes import ableton_routes


class FakeHandler:
    def __init__(self, body: dict) -> None:
        self._body = json.dumps(body).encode("utf-8")
        self.status = 0
        self.payload: dict = {}

    def read_json_body(self) -> dict:
        return json.loads(self._body.decode("utf-8"))

    def send_json(self, status: int, payload: dict) -> None:
        self.status = status
        self.payload = payload


def _stub_answer_payload(monkeypatch) -> None:
    def fake(question, limit=4, history=None, *, allow_llm=True, profile=False, session_id=""):
        return {
            "answer": "Reduce the 300 Hz build-up by 2 dB.",
            "sources": ["automix-dynamic-eq.md"],
            "weak_match": False,
            "found": True,
        }

    monkeypatch.setattr("kenn.core.chat_answer.answer_payload", fake)


def test_missing_track_name_is_rejected(monkeypatch) -> None:
    _stub_answer_payload(monkeypatch)
    handler = FakeHandler({"device_chain": ["EQ Eight"]})
    handled = ableton_routes.handle_ableton_post(handler, "/api/ableton/live-suggestion", "/tmp", log_event=lambda *a: None)
    assert handled is True
    assert handler.status == 400


def test_valid_request_returns_grounded_suggestion(monkeypatch) -> None:
    _stub_answer_payload(monkeypatch)
    handler = FakeHandler(
        {
            "track_name": "Lead Vocal",
            "device_chain": ["EQ Eight", "Compressor"],
            "key_params": {"Compressor.Ratio": "4:1"},
            "genre": "pop",
        }
    )
    handled = ableton_routes.handle_ableton_post(handler, "/api/ableton/live-suggestion", "/tmp", log_event=lambda *a: None)
    assert handled is True
    assert handler.status == 200
    assert handler.payload["live_track_name"] == "Lead Vocal"
    assert handler.payload["answer"] == "Reduce the 300 Hz build-up by 2 dB."
    assert handler.payload["weak_match"] is False


def test_live_suggestion_route_never_writes_to_a_live_ableton_session(monkeypatch) -> None:
    """The critical Stage L §L5 guarantee: this read-only suggestion path
    must never reach any function capable of mutating a live Ableton
    session (OSC parameter writes, repair-chain application) or KENN's own
    write-capable operations (note authoring/approval, index rebuilds)."""
    _stub_answer_payload(monkeypatch)

    from app.routes.ableton_routes import ableton_bridge
    from agents.MixReview.ableton_live_api import AbletonOSCClient

    calls: list[str] = []

    def spy(name):
        def _inner(*args, **kwargs):
            calls.append(name)
            return None
        return _inner

    monkeypatch.setattr(AbletonOSCClient, "send", spy("osc_send"))
    monkeypatch.setattr(AbletonOSCClient, "set_parameter", spy("osc_set_parameter"))
    monkeypatch.setattr(AbletonOSCClient, "apply_repair_chain", spy("osc_apply_repair_chain"))
    monkeypatch.setattr(ableton_bridge, "write_note", spy("write_note"))
    monkeypatch.setattr(ableton_bridge, "approve_note", spy("approve_note"))
    monkeypatch.setattr(ableton_bridge, "build_index", spy("build_index"))
    monkeypatch.setattr(ableton_bridge, "save_mix_version", spy("save_mix_version"))

    handler = FakeHandler(
        {
            "track_name": "Kick",
            "device_chain": ["Saturator", "Compressor"],
            "key_params": {"Saturator.Drive": "3dB"},
            "genre": "edm",
        }
    )
    handled = ableton_routes.handle_ableton_post(handler, "/api/ableton/live-suggestion", "/tmp", log_event=lambda *a: None)

    assert handled is True
    assert handler.status == 200
    assert calls == [], f"live-suggestion route reached write-capable operation(s): {calls}"

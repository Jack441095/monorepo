"""POST /api/admin/audiogen/render-song -- the HTTP surface for AudioGen's
full-song render queue, including the optional chain_to_automix/genre/
style_prefs fields that chain a render's generated stems straight into an
AutoMix job (business/app/audiogen_bridge.py::enqueue_full_song_render).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server" / "app"))

import audiogen_bridge  # noqa: E402
from app.routes import creative_lab_routes  # noqa: E402


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


def _noop_log_event(*args, **kwargs) -> None:
    pass


def test_render_song_passes_chain_fields_through_to_bridge(monkeypatch) -> None:
    captured = {}

    def fake_enqueue(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "job": {"id": "job-1", "status": "queued"}}

    monkeypatch.setattr(audiogen_bridge, "enqueue_full_song_render", fake_enqueue)

    handler = FakeHandler(
        {
            "emotion": "joy",
            "bars": 8,
            "k": 1,
            "project_id": "proj-1",
            "chain_to_automix": True,
            "genre": "pop",
            "style_prefs": {"masking_corrections": True},
        }
    )

    handled = creative_lab_routes.handle_creative_lab_post(
        handler, "/api/admin/audiogen/render-song", log_event=_noop_log_event
    )

    assert handled is True
    assert handler.status == 202
    assert captured["chain_to_automix"] is True
    assert captured["genre"] == "pop"
    assert captured["style_prefs"] == {"masking_corrections": True}


def test_render_song_defaults_chain_fields_to_off(monkeypatch) -> None:
    captured = {}

    def fake_enqueue(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "job": {"id": "job-1", "status": "queued"}}

    monkeypatch.setattr(audiogen_bridge, "enqueue_full_song_render", fake_enqueue)

    handler = FakeHandler({"emotion": "joy", "bars": 4, "k": 1})

    handled = creative_lab_routes.handle_creative_lab_post(
        handler, "/api/admin/audiogen/render-song", log_event=_noop_log_event
    )

    assert handled is True
    assert captured["chain_to_automix"] is False
    assert captured["genre"] == ""
    assert captured["style_prefs"] is None


def test_render_song_rejects_non_object_style_prefs() -> None:
    handler = FakeHandler({"emotion": "joy", "bars": 4, "k": 1, "style_prefs": "not-an-object"})

    handled = creative_lab_routes.handle_creative_lab_post(
        handler, "/api/admin/audiogen/render-song", log_event=_noop_log_event
    )

    assert handled is True
    assert handler.status == 400

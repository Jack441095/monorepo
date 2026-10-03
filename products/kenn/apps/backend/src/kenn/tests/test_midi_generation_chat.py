import json
import threading
from collections import defaultdict, deque
from urllib.request import Request, urlopen

import pytest

from kenn.core import answer_upgrades, confirmation, live_action_service
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.midi_clip_service import MidiClipActionService
from kenn.core.midi_generation_chat import generation_kind, propose_generated_clip


def _with_midi_track() -> tuple[FakeLiveBackend, LiveActionService]:
    live = FakeLiveBackend()
    live.create_midi_track()
    live.set_track_name(8, "Pads")
    return live, LiveActionService(live)


@pytest.mark.parametrize(
    ("text", "kind"),
    [("Write a 4-bar chord progression in D minor", "chords"), ("make a drum pattern", "drums"),
     ("Generate a bassline", "bassline"), ("What chords are in this song?", None), ("Pan the Synth left", None)],
)
def test_generation_kind_needs_a_creative_verb_and_a_known_idea(text: str, kind) -> None:
    assert generation_kind(text) == kind


def test_no_midi_track_is_explained_not_worked_around() -> None:
    result = propose_generated_clip("Write chords in D minor", session_id="g", service=LiveActionService(FakeLiveBackend()))
    assert result["status"] == "clarification_required" and "Create a MIDI track" in result["answer"]


def test_chords_use_the_stated_key_and_apply_with_readback_then_undo() -> None:
    live, service = _with_midi_track()
    result = propose_generated_clip("Write a 4-bar chord progression in D minor on the Pads track",
                                    session_id="g", service=service)
    assert result["status"] == "confirmation_required" and result["changed"] is False
    assert "D minor" in result["answer"] and result["generation"]["key"] == "D minor"
    assert live.get_midi_clip_state(8, 0)["has_clip"] is False
    proposal = result["proposal"]
    midi = MidiClipActionService(live)
    applied = midi.execute_create(proposal, confirm_token=proposal["confirmation_token"], session_id="g",
                                  idempotency_key="g-apply")
    assert applied["ok"] and applied["receipt"]["verified"] is True
    assert {n["pitch"] % 12 for n in live.get_midi_clip_state(8, 0)["notes"]} <= {2, 4, 5, 7, 9, 10, 0}
    undo = midi.propose_undo(applied["receipt"], session_id="g")
    assert undo["ok"]
    removed = midi.execute_remove(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"],
                                  session_id="g", idempotency_key="g-undo")
    assert removed["ok"] and live.get_midi_clip_state(8, 0)["has_clip"] is False


def test_key_falls_back_to_lives_scale_setting_and_slots_advance() -> None:
    live, service = _with_midi_track()
    first = propose_generated_clip("Generate a bassline", session_id="g", service=service)
    assert first["generation"]["key"] == "C major"  # the fixture's Live scale setting
    p = first["proposal"]
    MidiClipActionService(live).execute_create(p, confirm_token=p["confirmation_token"], session_id="g",
                                               idempotency_key="g-bass")
    second = propose_generated_clip("make a drum pattern", session_id="g", service=service)
    assert second["generation"]["key"] is None and "slot 2" in second["answer"]


def test_same_request_previews_exactly_the_same_notes() -> None:
    _live, service = _with_midi_track()
    a = propose_generated_clip("Write chords in A minor", session_id="g", service=service)
    b = propose_generated_clip("Write chords in A minor", session_id="g", service=service)
    assert a["generation"]["seed"] == b["generation"]["seed"]
    assert a["proposal"]["notes"] == b["proposal"]["notes"]


@pytest.fixture
def ask_clip(monkeypatch):
    import kenn.server as server
    import kenn.server_rate_limit as rate_limit

    live, _ = _with_midi_track()
    monkeypatch.setattr(live_action_service, "live_client", live)
    monkeypatch.setattr(rate_limit, "RATE_BUCKETS", defaultdict(deque))
    monkeypatch.setattr(answer_upgrades, "_TURNS", {})
    monkeypatch.setattr(answer_upgrades, "_RESULTS", {})
    monkeypatch.setattr(confirmation, "_USED_TOKENS", set())
    monkeypatch.setattr(confirmation, "_ISSUED_TOKENS", {})
    monkeypatch.setattr(confirmation, "_REVOKED_TOKENS", set())
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    worker = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=0.01), daemon=True)
    worker.start()

    def post(payload):
        request = Request(f"http://127.0.0.1:{httpd.server_port}/api/ask", data=json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    try:
        yield post, live
    finally:
        httpd.shutdown()
        worker.join(timeout=5)
        httpd.server_close()


@pytest.mark.parametrize("session_id", [None, "", "   ", 7, "x" * 129])
def test_a_generated_clip_is_never_prepared_for_a_chat_without_an_owner(ask_clip, session_id):
    # Every unnamed caller used to share the owner "chat", so one could dismiss or apply another's clip.
    post, live = ask_clip
    before = live.query_session_state()

    result = post({"question": "Write a 4-bar chord progression in D minor", "stream": False, "session_id": session_id})

    assert "session ID is required" in result["answer"]
    assert not result.get("proposal")
    assert not result.get("confirmation_token")
    assert result["requires_confirmation"] is False
    assert confirmation._ISSUED_TOKENS == {}
    assert live.query_session_state() == before


def test_a_generated_clip_belongs_to_the_chat_that_asked_for_it(ask_clip):
    post, live = ask_clip
    result = post({"question": "Write a 4-bar chord progression in D minor", "stream": False, "session_id": " song-a "})

    assert result["requires_confirmation"] is True
    token = result["confirmation_token"]
    assert confirmation.pending_confirmation_count(session_id="song-a") == 1
    assert not confirmation.revoke_confirmation(token, session_id="song-b")
    assert not confirmation.revoke_confirmation(token, session_id="chat")
    assert confirmation.revoke_confirmation(token, session_id="song-a")

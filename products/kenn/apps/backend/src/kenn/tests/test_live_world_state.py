from kenn.core import live_receipt_journal
from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_world_state import WorldModelState


def test_version_is_monotonic_and_only_moves_when_live_changes() -> None:
    live, state = FakeLiveBackend(), WorldModelState()
    first = state.current(live)
    assert first["version"] == 1
    assert state.current(live, force=True)["version"] == 1
    live.set_track_pan(5, -1.0)
    assert state.current(live, force=True)["version"] == 2
    assert state.current(live, force=True)["version"] == 2


def test_cached_model_is_reused_until_invalidated() -> None:
    reads = []

    def reader(client):
        reads.append(1)
        return {"status": "connected", "fingerprint": f"fp-{len(reads)}", "tracks": []}

    state, client = WorldModelState(reader), object()
    state.current(client)
    state.current(client)
    assert len(reads) == 1
    state.current(object())
    assert len(reads) == 2, "a different client must never be served another client's model"
    state.invalidate()
    assert state.current(client)["version"] == 3 and len(reads) == 3


def test_recording_a_receipt_invalidates_the_shared_state(tmp_path, monkeypatch) -> None:
    from kenn.core import live_world_state

    monkeypatch.setattr(live_receipt_journal, "JOURNAL_PATH", tmp_path / "receipts.jsonl")
    reads = []
    shared = WorldModelState(lambda client: reads.append(1) or {"status": "connected", "fingerprint": "same"})
    monkeypatch.setattr(live_world_state, "world_state", shared)
    client = object()
    shared.current(client)
    live_receipt_journal.record_receipt({"receipt_id": "r1", "action": "set_pan"}, session_id="s")
    shared.current(client)
    assert len(reads) == 2


def test_offline_read_is_returned_without_bumping_the_version() -> None:
    state = WorldModelState(lambda client: {"status": "offline", "error": "no reply"})
    assert state.current(object()) == {"status": "offline", "error": "no reply"}
    assert state.version == 0

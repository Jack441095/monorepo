from __future__ import annotations

from copy import deepcopy

from kenn.core.sample_import_service import (
    IMPORT_PROPOSAL_SCHEMA,
    RECEIPT_SCHEMA,
    REMOVE_PROPOSAL_SCHEMA,
    SampleImportService,
)


class FakeImportLive:
    def __init__(self) -> None:
        self.state = {
            "status": "connected",
            "tracks": [{"index": 2, "name": "3-Audio", "devices": []}],
        }
        self.clips: dict[tuple[int, int], dict] = {}
        self.writes: list[tuple[str, object]] = []
        self.import_should_fail = False

    def query_session_topology(self) -> dict:
        return deepcopy(self.state)

    def get_midi_clip_state(self, track_index: int, clip_slot_index: int) -> dict:
        clip = self.clips.get((track_index, clip_slot_index))
        if clip is None:
            return {
                "success": True,
                "track_index": track_index,
                "clip_slot_index": clip_slot_index,
                "has_clip": False,
                "is_midi_clip": False,
                "length": 0.0,
                "notes": [],
            }
        return {"success": True, "track_index": track_index, "clip_slot_index": clip_slot_index, **deepcopy(clip)}

    def import_sample_to_clip_slot(self, track_index: int, clip_slot_index: int, absolute_path: str) -> dict:
        self.writes.append(("import", (track_index, clip_slot_index, absolute_path)))
        if self.import_should_fail:
            return {"success": False, "error": "AbletonOSC reported the import failed."}
        self.clips[(track_index, clip_slot_index)] = {
            "has_clip": True,
            "is_midi_clip": False,
            "length": 4.0,
            "notes": [],
        }
        return {"success": True, "clip_name": "Fake Kick One"}

    def delete_midi_clip(self, track_index: int, clip_slot_index: int) -> bool:
        self.writes.append(("delete", (track_index, clip_slot_index)))
        self.clips.pop((track_index, clip_slot_index), None)
        return True


def _make_library(tmp_path):
    (tmp_path / "Pack").mkdir()
    (tmp_path / "Pack" / "Kick One.wav").write_bytes(b"RIFF" + b"\x00" * 40)
    return tmp_path


def _sample_id(root):
    from kenn.core.sample_library import scan_sample_library
    entries = scan_sample_library(root)
    return entries[0].id


def _proposal(service, sample_id, session: str = "import-service") -> dict:
    result = service.propose_import(
        track_index=2,
        track_name="3-Audio",
        clip_slot_index=0,
        sample_id=sample_id,
        session_id=session,
    )
    assert result["ok"], result
    assert result["proposal"]["schema"] == IMPORT_PROPOSAL_SCHEMA
    return result["proposal"]


def test_sample_import_receipt_carries_correlation_id_retry_safety_and_stage_timings(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    sample_id = _sample_id(root)
    fake = FakeImportLive()
    service = SampleImportService(fake)
    proposal = _proposal(service, sample_id)
    applied = service.execute_import(
        proposal, confirm_token=proposal["confirmation_token"], session_id="import-service", correlation_id="caller-corr-import",
    )
    assert applied["ok"] is True
    receipt = applied["receipt"]
    assert receipt["correlation_id"] == "caller-corr-import"
    assert receipt["retry_safe"] == "safe"
    assert "write" in receipt["stage_timings_ms"]
    assert "readback" in receipt["stage_timings_ms"]

    undo_proposed = service.propose_undo(receipt, session_id="import-undo")
    undone = service.execute_remove(
        undo_proposed["proposal"], confirm_token=undo_proposed["proposal"]["confirmation_token"], session_id="import-undo", correlation_id="caller-corr-remove",
    )
    assert undone["ok"] is True
    assert undone["receipt"]["correlation_id"] == "caller-corr-remove"
    assert undone["receipt"]["retry_safe"] == "safe"


def test_sample_import_requires_confirmation_and_supports_verified_undo(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    sample_id = _sample_id(root)
    fake = FakeImportLive()
    service = SampleImportService(fake)
    proposal = _proposal(service, sample_id)

    assert service.execute_import(proposal, confirm_token="", session_id="import-service")["ok"] is False
    assert fake.writes == []

    applied = service.execute_import(
        proposal,
        confirm_token=proposal["confirmation_token"],
        session_id="import-service",
    )
    assert applied["ok"] is True
    assert applied["receipt"]["schema"] == RECEIPT_SCHEMA
    assert applied["receipt"]["verified"] is True
    assert applied["receipt"]["sample_filename"] == "Kick One.wav"
    assert len(fake.writes) == 1
    # The absolute path was sent to AbletonOSC (localhost transport, same
    # trust boundary as everything else) but never appeared in the proposal
    # or receipt returned to the caller.
    assert str(root) not in str(proposal)
    assert str(root) not in str(applied["receipt"])

    replay = service.execute_import(proposal, confirm_token=proposal["confirmation_token"], session_id="import-service")
    assert replay["ok"] is False
    assert len(fake.writes) == 1

    undo_proposed = service.propose_undo(applied["receipt"], session_id="import-undo")
    assert undo_proposed["ok"]
    assert undo_proposed["proposal"]["schema"] == REMOVE_PROPOSAL_SCHEMA
    undone = service.execute_remove(
        undo_proposed["proposal"],
        confirm_token=undo_proposed["proposal"]["confirmation_token"],
        session_id="import-undo",
    )
    assert undone["ok"] is True
    assert fake.get_midi_clip_state(2, 0)["has_clip"] is False


def test_sample_import_rejects_occupied_clip_slot(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    sample_id = _sample_id(root)
    fake = FakeImportLive()
    fake.clips[(2, 0)] = {"has_clip": True, "is_midi_clip": False, "length": 2.0, "notes": []}
    service = SampleImportService(fake)
    result = service.propose_import(
        track_index=2, track_name="3-Audio", clip_slot_index=0, sample_id=sample_id, session_id="s",
    )
    assert result["ok"] is False
    assert "already contains a clip" in result["error"]


def test_sample_import_rejects_unknown_sample_id(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    fake = FakeImportLive()
    service = SampleImportService(fake)
    result = service.propose_import(
        track_index=2, track_name="3-Audio", clip_slot_index=0, sample_id="0000000000000000", session_id="s",
    )
    assert result["ok"] is False
    assert "No sample with that id" in result["error"]


def test_sample_import_honestly_reports_ableton_side_failure(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    sample_id = _sample_id(root)
    fake = FakeImportLive()
    fake.import_should_fail = True
    service = SampleImportService(fake)
    proposal = _proposal(service, sample_id)
    result = service.execute_import(proposal, confirm_token=proposal["confirmation_token"], session_id="import-service")
    assert result["ok"] is False
    assert result["receipt"]["status"] == "failed"


def test_sample_import_undo_refuses_when_clip_no_longer_present(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    sample_id = _sample_id(root)
    fake = FakeImportLive()
    service = SampleImportService(fake)
    proposal = _proposal(service, sample_id)
    applied = service.execute_import(proposal, confirm_token=proposal["confirmation_token"], session_id="import-service")
    assert applied["ok"] is True
    fake.clips.pop((2, 0))  # someone/something else already removed the clip
    undo_proposed = service.propose_undo(applied["receipt"], session_id="import-undo")
    assert undo_proposed["ok"] is False
    assert "no longer present" in undo_proposed["error"]


def test_sample_import_undo_rechecks_track_identity(tmp_path, monkeypatch) -> None:
    root = _make_library(tmp_path)
    monkeypatch.setenv("KENN_SAMPLE_LIBRARY_ROOT", str(root))
    fake = FakeImportLive()
    service = SampleImportService(fake)
    proposal = _proposal(service, _sample_id(root), session="import-undo-identity")
    applied = service.execute_import(proposal, confirm_token=proposal["confirmation_token"], session_id="import-undo-identity")
    assert applied["ok"] is True

    fake.state["tracks"][0]["name"] = "Replacement Track"
    stale = service.propose_undo(applied["receipt"], session_id="import-undo-stale")
    assert stale["ok"] is False
    assert "identity" in stale["error"] or "changed" in stale["error"]

    fake.state["tracks"][0]["name"] = "3-Audio"
    undo = service.propose_undo(applied["receipt"], session_id="import-undo-fresh")
    assert undo["ok"] is True
    fake.state["tracks"][0]["name"] = "Replacement Track"
    result = service.execute_remove(undo["proposal"], confirm_token=undo["proposal"]["confirmation_token"], session_id="import-undo-fresh")
    assert result["ok"] is False
    assert "identity" in result["error"] or "changed" in result["error"]
    assert not any(write[0] == "delete" for write in fake.writes)

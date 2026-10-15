from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import json
import math
import os
from pathlib import Path
from threading import Event
import time
import wave

import pytest

from kenn.core import offline_scan
from kenn.core.offline_scan import OfflineScanService


def _source():
    return {"source_kind": "arrangement_main", "fingerprint": "synthetic-set-revision-1", "range_confirmed": True, "tail_policy": "within_range"}


def _request():
    return {"live_pid": 12345, "expected_window_title": "Disposable synthetic set", "render_start": "1.1.1", "render_length": "4.0.0", "sample_rate": 48000, "timeout_seconds": 10}


def _wav(*, sample_rate=48000, channels=2, sample_width=3, frames=48000, amplitude=0.125):
    output = BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(sample_width)
        handle.setframerate(sample_rate)
        peak = int(((1 << (sample_width * 8 - 1)) - 1) * amplitude)
        payload = b"".join(int(peak * math.sin(2 * math.pi * 400 * index / sample_rate)).to_bytes(sample_width, "little", signed=True) * channels for index in range(frames))
        handle.writeframes(payload)
    return output.getvalue()


def _receipt(request, **changes):
    return {"schema": "kenn.live_export_receipt.v1", "status": "completed", "writer_closed": True, "channels": 2, **{key: request[key] for key in ("live_pid", "output_path", "render_start", "render_length", "sample_rate")}, **changes}


class _Reviewer:
    def __init__(self):
        self.calls = []

    def save_review(self, payload, filename):
        self.calls.append((payload, filename))
        return {"ok": True, "review": {"status": "completed", "metrics": {"fixture": True}, "action_plan": [{"evidence": "synthetic fixture"}]}}


def _service(tmp_path, *, exporter=None, reviewer=None, fingerprint=None):
    def export(request, cancel):
        Path(request["output_path"]).write_bytes(_wav(frames=4800))
        return _receipt(request)

    return OfflineScanService(tmp_path, exporter=exporter or export, reviewer=reviewer or _Reviewer(), read_source_fingerprint=fingerprint or (lambda: _source()["fingerprint"]))


def _finished(service, job_id, owner="owner-a"):
    deadline = time.monotonic() + 20  # 20 seconds bounds the real local analyzer fixture.
    while time.monotonic() < deadline:
        result = service.status(owner, job_id)
        if result.get("state") not in {"exporting", "analyzing"}:
            # Worker releases its flock just after the terminal receipt write.
            while job_id in service._events and time.monotonic() < deadline:
                time.sleep(0.005)
            return result
        time.sleep(0.005)
    pytest.fail("Offline scan worker did not finish.")


def test_generated_wav_uses_real_mix_review_and_reloads_advice_after_audio_deletion(tmp_path):
    # One real analyzer path proves metadata and grounded advice survive disposal.
    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(_wav(amplitude=0.99))
        return _receipt(request)

    service = OfflineScanService(tmp_path, exporter=exporter, read_source_fingerprint=lambda: _source()["fingerprint"])
    accepted = service.start("owner-a", _source(), _request())
    result = _finished(service, accepted["job_id"])

    assert result["state"] == "completed"
    assert result["audio_deleted"] is True
    assert result["review"]["status"] == "completed"
    assert result["review"]["metrics"]
    assert result["review"]["action_plan"]
    assert result["review"]["audio_retained"] is False
    assert not list(tmp_path.rglob("*.wav"))
    restored = _service(tmp_path).status("owner-a", accepted["job_id"])
    assert restored == result
    assert (tmp_path / accepted["job_id"]).stat().st_mode & 0o777 == 0o700
    assert (tmp_path / accepted["job_id"] / "receipt.json").stat().st_mode & 0o777 == 0o600


def test_preview_does_not_create_a_job_and_rejects_an_old_source(tmp_path):
    service = _service(tmp_path)
    assert service.validate_current(_source(), _request())["export_request"]["action"] == "export"
    assert not list(tmp_path.glob("scan-*"))
    source = {**_source(), "fingerprint": "old-revision"}
    with pytest.raises(ValueError, match="source changed"):
        service.validate_current(source, _request())


@pytest.mark.parametrize("source_change,request_change", [
    ({"range_confirmed": False}, {}),
    ({"tail_policy": "automatic_tail"}, {}),
    ({"source_kind": "first_bounce"}, {}),
    ({"fingerprint": ""}, {}),
    ({}, {"output_path": "/not-owned.wav"}),
    ({}, {"sample_rate": 44100}),
    ({}, {"sample_rate": 48000.0}),
    ({}, {"timeout_seconds": 601}),
    ({}, {"timeout_seconds": 0}),
    ({}, {"timeout_seconds": 0.5}),
    ({}, {"timeout_seconds": 1.0}),
    ({}, {"timeout_seconds": True}),
    ({}, {"timeout_seconds": float("nan")}),
    ({}, {"live_pid": True}),
    ({}, {"live_pid": 2_147_483_648}),
    ({}, {"expected_window_title": "title\nother window"}),
    ({}, {"expected_window_title": "界" * 171}),
    ({}, {"render_start": "guess from bounce"}),
    ({}, {"render_length": "0.0.0"}),
])
def test_scan_requires_exact_confirmed_source_range_and_fixed_export_limits(tmp_path, source_change, request_change):
    service = _service(tmp_path)
    with pytest.raises(ValueError):
        service.start("owner-a", {**_source(), **source_change}, {**_request(), **request_change})
    assert not list(tmp_path.glob("scan-*"))


@pytest.mark.parametrize("timeout", [1, 600])
def test_export_timeout_accepts_exact_integer_endpoints_only(tmp_path, timeout):
    service = _service(tmp_path)
    assert service.validate_current(_source(), {**_request(), "timeout_seconds": timeout})["export_request"]["timeout_seconds"] == timeout


def test_request_accepts_exact_pid_and_utf8_title_upper_bounds(tmp_path):
    service = _service(tmp_path)
    validated = service.validate_current(_source(), {**_request(), "live_pid": 2_147_483_647, "expected_window_title": "界" * 170 + "ab"})
    assert validated["export_request"]["live_pid"] == 2_147_483_647
    assert len(validated["export_request"]["expected_window_title"].encode("utf-8")) == 512


def test_foreign_owner_cannot_read_cancel_or_guess_a_job_and_other_instance_cannot_start(tmp_path):
    entered, release = Event(), Event()

    def exporter(request, cancel):
        entered.set()
        assert release.wait(5)
        Path(request["output_path"]).write_bytes(_wav(frames=10))
        return _receipt(request)

    service = _service(tmp_path, exporter=exporter)
    accepted = service.start("owner-a", _source(), _request())
    assert entered.wait(5)
    for action in (service.status, service.cancel):
        assert action("owner-b", accepted["job_id"]) == action("owner-b", "scan-" + "f" * 32)
        assert action("owner-b", "../outside")["ok"] is False
    other = _service(tmp_path)
    with pytest.raises(RuntimeError, match="active"):
        other.start("owner-b", _source(), _request())
    with pytest.raises(RuntimeError, match="active"):
        other.recover_abandoned(writer_is_absent=lambda request: True)
    release.set()
    assert _finished(service, accepted["job_id"])["state"] == "completed"
    second = other.start("owner-b", _source(), _request())
    assert second["job_id"] != accepted["job_id"]
    assert _finished(other, second["job_id"], "owner-b")["state"] == "completed"
    assert service.status("owner-a", second["job_id"])["ok"] is False


@pytest.mark.parametrize("changes", [{"writer_closed": False}, {"output_path": "/foreign.wav"}, {"render_length": "8.0.0"}, {"live_pid": 54321}, {"schema": "wrong"}])
def test_unproven_or_mismatched_export_never_decodes_or_deletes_an_open_writer(tmp_path, changes):
    reviewer = _Reviewer()

    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(b"writer still owns this")
        return _receipt(request, **changes)

    service = _service(tmp_path, exporter=exporter, reviewer=reviewer)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "cleanup_pending"
    assert "review" not in result and reviewer.calls == []
    assert Path(result["export_request"]["output_path"]).read_bytes() == b"writer still owns this"
    assert service.recover_abandoned(writer_is_absent=lambda request: False) == []
    assert service.recover_abandoned(writer_is_absent=lambda request: True)[0]["audio_deleted"] is True
    assert not list(tmp_path.rglob("*.wav"))


def test_crashed_export_helper_does_not_prove_that_live_stopped_writing(tmp_path):
    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(b"partial render")
        raise TimeoutError("helper crashed")

    service = _service(tmp_path, exporter=exporter)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "cleanup_pending"
    assert result["audio_deleted"] is False
    assert "TimeoutError" in result["error"]


def test_prelaunch_refusal_can_prove_no_writer_without_inventing_audio(tmp_path):
    reviewer = _Reviewer()

    def exporter(request, cancel):
        return _receipt(request, status="unavailable", writer_closed=True)

    service = _service(tmp_path, exporter=exporter, reviewer=reviewer)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "failed" and result["audio_deleted"] is True
    assert reviewer.calls == [] and "review" not in result


@pytest.mark.parametrize("payload", [
    b"not audio",
    _wav(sample_width=2, frames=100),
    _wav(channels=1, frames=100),
    _wav(sample_rate=44100, frames=100),
    _wav(frames=100)[:-1],
])
def test_closed_invalid_wav_is_disposed_without_calling_analyzer(tmp_path, payload):
    reviewer = _Reviewer()

    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(payload)
        return _receipt(request)

    service = _service(tmp_path, exporter=exporter, reviewer=reviewer)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "failed"
    assert result["audio_deleted"] is True and reviewer.calls == []
    assert not list(tmp_path.rglob("*.wav"))


@pytest.mark.parametrize("limit", ["bytes", "duration"])
def test_byte_and_duration_limits_are_checked_before_decode(tmp_path, monkeypatch, limit):
    reviewer = _Reviewer()
    if limit == "bytes":
        monkeypatch.setattr(offline_scan, "MAX_UPLOAD_BYTES", 50)
    else:
        monkeypatch.setattr(offline_scan, "MAX_DURATION_SECONDS", 0.001)
    service = _service(tmp_path, reviewer=reviewer)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "failed" and reviewer.calls == []
    assert result["audio_deleted"] is True


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink"])
def test_imported_original_and_linked_export_are_never_deleted(tmp_path, link_kind):
    original = tmp_path / "user-export.wav"
    original.write_bytes(_wav(frames=100))
    reviewer = _Reviewer()

    def exporter(request, cancel):
        destination = Path(request["output_path"])
        if link_kind == "symlink":
            destination.symlink_to(original)
        else:
            os.link(original, destination)
        return _receipt(request)

    service = _service(tmp_path / "jobs", exporter=exporter, reviewer=reviewer)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "cleanup_pending" and reviewer.calls == []
    assert original.exists() and Path(result["export_request"]["output_path"]).exists()
    assert service.recover_abandoned(writer_is_absent=lambda request: True) == []


def test_cancel_during_export_signals_marker_and_discards_late_completed_export(tmp_path):
    entered, release = Event(), Event()
    reviewer = _Reviewer()

    def exporter(request, cancel):
        entered.set()
        assert release.wait(5)
        assert cancel.is_set()
        assert (Path(request["output_path"]).parent / "cancel.requested").exists()
        Path(request["output_path"]).write_bytes(_wav(frames=100))
        return _receipt(request)

    service = _service(tmp_path, exporter=exporter, reviewer=reviewer)
    job = service.start("owner-a", _source(), _request())
    assert entered.wait(5)
    assert service.cancel("owner-a", job["job_id"])["cancel_requested"] is True
    release.set()
    result = _finished(service, job["job_id"])
    assert result["state"] == "cancelled" and result["audio_deleted"] is True
    assert reviewer.calls == [] and "review" not in result
    assert not list(tmp_path.rglob("cancel.requested"))


def test_cancel_during_analysis_discards_late_report_and_keeps_unrelated_files(tmp_path):
    entered, release = Event(), Event()

    class SlowReviewer(_Reviewer):
        def save_review(self, payload, filename):
            entered.set()
            assert release.wait(5)
            return super().save_review(payload, filename)

    service = _service(tmp_path, reviewer=SlowReviewer())
    job = service.start("owner-a", _source(), _request())
    assert entered.wait(5)
    unrelated = tmp_path / job["job_id"] / "producer-notes.txt"
    unrelated.write_text("keep me")
    service.cancel("owner-a", job["job_id"])
    release.set()
    result = _finished(service, job["job_id"])
    assert result["state"] == "cancelled" and "review" not in result
    assert result["audio_deleted"] is True and unrelated.read_text() == "keep me"


@pytest.mark.parametrize("change_at", ["export", "analysis", "status"])
def test_set_changes_never_publish_a_fresh_report(tmp_path, change_at):
    current = [_source()["fingerprint"]]
    reviewer = _Reviewer()

    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(_wav(frames=100))
        if change_at == "export":
            current[0] = "changed-set"
        return _receipt(request)

    class ChangingReviewer(_Reviewer):
        def save_review(self, payload, filename):
            current[0] = "changed-set"
            return super().save_review(payload, filename)

    service = _service(tmp_path, exporter=exporter, reviewer=ChangingReviewer() if change_at == "analysis" else reviewer, fingerprint=lambda: current[0])
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    if change_at == "status":
        assert result["state"] == "completed"
        current[0] = "changed-set"
        result = service.status("owner-a", job["job_id"])
        assert result["review"]["status"] == "completed"
    else:
        assert "review" not in result
    assert result["state"] == "stale" and result["audio_deleted"] is True


def test_changed_wav_identity_after_analysis_refuses_cleanup_and_publication(tmp_path):
    class ReplacingReviewer(_Reviewer):
        def save_review(self, payload, filename):
            wav = next(tmp_path.rglob("*.wav"))
            replacement = wav.with_name("replacement.wav")
            replacement.write_bytes(b"foreign replacement")
            replacement.replace(wav)
            return super().save_review(payload, filename)

    service = _service(tmp_path, reviewer=ReplacingReviewer())
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "cleanup_pending" and "review" not in result
    assert Path(result["export_request"]["output_path"]).read_bytes() == b"foreign replacement"


def test_abandoned_recovery_ignores_foreign_manifest_and_metadata_storage_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(offline_scan, "MAX_JOBS", 2)
    service = _service(tmp_path)
    first = service.start("owner-a", _source(), _request())
    _finished(service, first["job_id"])
    second = service.start("owner-b", _source(), _request())
    _finished(service, second["job_id"], "owner-b")
    third = service.start("owner-a", _source(), _request())
    _finished(service, third["job_id"])
    assert service.status("owner-a", first["job_id"])["ok"] is False
    assert len(list(tmp_path.glob("scan-*"))) == 2
    foreign = tmp_path / ("scan-" + "a" * 32)
    foreign.mkdir()
    (foreign / "manifest.json").write_text(json.dumps({"job_id": "other"}))
    original = foreign / "kenn-analysis.wav"
    original.write_bytes(b"not owned")
    assert service.recover_abandoned(writer_is_absent=lambda request: True) == []
    assert original.read_bytes() == b"not owned"


def test_unclosed_abandoned_exports_fill_the_bound_without_sweeping_them(tmp_path, monkeypatch):
    monkeypatch.setattr(offline_scan, "MAX_JOBS", 1)

    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(b"partial")
        return _receipt(request, writer_closed=False)

    service = _service(tmp_path, exporter=exporter)
    job = service.start("owner-a", _source(), _request())
    _finished(service, job["job_id"])
    with pytest.raises(RuntimeError, match="requires recovery"):
        service.start("owner-a", _source(), _request())
    assert Path(job["export_request"]["output_path"]).read_bytes() == b"partial"


def test_restart_cannot_launch_an_export_while_an_old_writer_is_unresolved(tmp_path):
    def exporter(request, cancel):
        Path(request["output_path"]).write_bytes(b"partial")
        return _receipt(request, writer_closed=False)

    service = _service(tmp_path, exporter=exporter)
    job = service.start("owner-a", _source(), _request())
    _finished(service, job["job_id"])
    restarted = _service(tmp_path)
    with pytest.raises(RuntimeError, match="requires recovery"):
        restarted.start("owner-b", _source(), _request())
    restarted.recover_abandoned(writer_is_absent=lambda request: True)
    next_job = restarted.start("owner-b", _source(), _request())
    assert _finished(restarted, next_job["job_id"], "owner-b")["state"] == "completed"


def test_same_owner_cancel_from_another_instance_reaches_an_active_analyzer(tmp_path):
    entered, release = Event(), Event()

    class SlowReviewer(_Reviewer):
        def save_review(self, payload, filename):
            entered.set()
            assert release.wait(5)
            return super().save_review(payload, filename)

    service = _service(tmp_path, reviewer=SlowReviewer())
    job = service.start("owner-a", _source(), _request())
    assert entered.wait(5)
    other = _service(tmp_path)
    assert other.cancel("owner-a", job["job_id"])["cancel_requested"] is True
    assert other.status("owner-a", job["job_id"])["cancel_requested"] is True
    release.set()
    result = _finished(service, job["job_id"])
    assert result["state"] == "cancelled" and "review" not in result


def test_cancel_marker_arriving_during_disposal_cannot_publish_a_late_report(tmp_path, monkeypatch):
    service = _service(tmp_path)
    original_cleanup = service._cleanup

    def cleanup(manifest):
        # Reproduce the cross-backend race after the analyzer's source check.
        (tmp_path / manifest["job_id"] / "cancel.requested").touch(mode=0o600)
        return original_cleanup(manifest)

    monkeypatch.setattr(service, "_cleanup", cleanup)
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "cancelled" and "review" not in result
    assert result["audio_deleted"] is True


def test_final_publication_and_cross_instance_cancel_have_one_commit_order(tmp_path, monkeypatch):
    # Cancellation used to acknowledge the prior analyzing receipt while the
    # worker was already committing completed, allowing a late report to escape.
    service = _service(tmp_path)
    other = _service(tmp_path)
    original_persist = service._persist
    entered, returned = Event(), Event()
    pending = []

    def cancel(job_id):
        entered.set()
        result = other.cancel("owner-a", job_id)
        returned.set()
        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        def persist(manifest, receipt):
            if receipt["state"] == "completed":
                pending.append(pool.submit(cancel, receipt["job_id"]))
                assert entered.wait(5)
                assert not returned.wait(0.05)  # 50 ms proves cancel waits for the commit lock.
            return original_persist(manifest, receipt)

        monkeypatch.setattr(service, "_persist", persist)
        job = service.start("owner-a", _source(), _request())
        result = _finished(service, job["job_id"])
        cancelled = pending[0].result(timeout=5)
    assert result["state"] == cancelled["state"] == "completed"
    assert "cancel_requested" not in cancelled
    assert result["review"]["status"] == "completed"


def test_cancellation_marker_on_completed_receipt_drops_late_review(tmp_path):
    service = _service(tmp_path)
    job = service.start("owner-a", _source(), _request())
    _finished(service, job["job_id"])
    (tmp_path / job["job_id"] / "cancel.requested").touch(mode=0o600)
    result = service.status("owner-a", job["job_id"])
    assert result["state"] == "cancelled" and "review" not in result


def test_worker_start_failure_leaves_no_live_writer_claim_or_unbounded_events(tmp_path, monkeypatch):
    class FailedThread:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            raise RuntimeError("synthetic thread exhaustion")

    monkeypatch.setattr(offline_scan, "Thread", FailedThread)
    service = _service(tmp_path)
    for _ in range(3):
        with pytest.raises(RuntimeError, match="thread exhaustion"):
            service.start("owner-a", _source(), _request())
        assert service._events == {}
        assert service.recover_abandoned(writer_is_absent=lambda request: False) == []
    for directory in tmp_path.glob("scan-*"):
        result = service.status("owner-a", directory.name)
        assert result["state"] == "failed" and result["audio_deleted"] is True


def test_oversized_analysis_metadata_fails_without_leaving_analyzing_status(tmp_path, monkeypatch):
    class LargeReviewer(_Reviewer):
        def save_review(self, payload, filename):
            return {"ok": True, "review": {"status": "completed", "metrics": {"too_large": "x" * 6000}}}

    monkeypatch.setattr(offline_scan, "MAX_METADATA_BYTES", 8192)
    service = _service(tmp_path, reviewer=LargeReviewer())
    job = service.start("owner-a", _source(), _request())
    result = _finished(service, job["job_id"])
    assert result["state"] == "failed" and result["audio_deleted"] is True
    assert "metadata exceeds" in result["error"]

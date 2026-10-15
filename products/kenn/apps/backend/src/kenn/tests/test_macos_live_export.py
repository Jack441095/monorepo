from __future__ import annotations

import json
from pathlib import Path
import sys
from threading import Event, Timer
import time

import pytest

from kenn.core.macos_live_export import MacOSLiveExportHelper


@pytest.fixture
def request_payload(tmp_path):
    job = tmp_path / "scan-synthetic"
    job.mkdir(mode=0o700)
    return {"schema": "kenn.live_export_request.v1", "action": "export", "live_pid": 12345,
            "expected_window_title": "Disposable synthetic set", "output_path": str(job.resolve() / "kenn-analysis.wav"),
            "render_start": "1.1.1", "render_length": "4.0.0", "sample_rate": 48000, "timeout_seconds": 2}


def _helper(tmp_path, body):
    path = tmp_path / "fake-export-helper"
    path.write_text(f"#!{sys.executable}\nimport json, os, sys, time\nfrom pathlib import Path\n"
                    "assert sys.argv[1:] == ['--supervised-test']\n"
                    "assert os.environ['KENN_EXPERIMENTAL_LIVE_EXPORT'] == '1'\n"
                    "request = json.load(sys.stdin)\n" + body, encoding="utf-8")
    path.chmod(0o700)
    return path


def _receipt_code(**changes):
    return ("receipt = {'schema':'kenn.live_export_receipt.v1','status':'completed','writer_closed':True,'channels':2,"
            "**{key:request[key] for key in ('live_pid','output_path','render_start','render_length','sample_rate')}}\n"
            f"receipt.update({changes!r})\nprint(json.dumps(receipt))\n")


def _adapter(path, monkeypatch):
    monkeypatch.setattr("kenn.core.macos_live_export.sys.platform", "darwin")
    return MacOSLiveExportHelper(path, enabled=True, supervised_test=True)


def test_disabled_helper_never_launches_and_returns_matching_no_writer_receipt(tmp_path, request_payload, monkeypatch):
    # Inheriting the environment flag alone must not authorize a process launch.
    monkeypatch.setenv("KENN_EXPERIMENTAL_LIVE_EXPORT", "1")
    marker = tmp_path / "launched"
    helper = _helper(tmp_path, f"Path({str(marker)!r}).touch()\n")
    for flags in ({}, {"enabled": True}, {"supervised_test": True}):
        result = MacOSLiveExportHelper(helper, **flags)(request_payload, Event())
        assert result["error_code"] == "experimental_export_disabled"
        assert result["writer_closed"] is True
        assert result["live_pid"] == request_payload["live_pid"]
        assert result["output_path"] == request_payload["output_path"]
    assert not marker.exists()


def test_fixed_helper_receipt_is_accepted_with_exact_identity(tmp_path, request_payload, monkeypatch):
    helper = _helper(tmp_path, _receipt_code())
    result = _adapter(helper, monkeypatch)(request_payload, Event())
    assert result["status"] == "completed"
    assert result["writer_closed"] is True
    assert result["output_path"] == request_payload["output_path"]


@pytest.mark.parametrize("change", [{"output_path": "/foreign/kenn-analysis.wav"}, {"live_pid": 999}, {"render_length": "9.0.0"}, {"sample_rate": 44100}, {"writer_closed": "yes"}, {"channels": 1}])
def test_foreign_or_incomplete_receipt_never_proves_writer_closure(tmp_path, request_payload, monkeypatch, change):
    helper = _helper(tmp_path, _receipt_code(**change))
    result = _adapter(helper, monkeypatch)(request_payload, Event())
    assert result["error_code"] == "invalid_helper_receipt"
    assert result["writer_closed"] is False


@pytest.mark.parametrize("body,code", [("print('not json')\n", "invalid_helper_receipt"), ("print('x'*70000)\n", "helper_output_limit"), ("time.sleep(10)\n", "helper_timeout")])
def test_launched_helper_protocol_failures_leave_writer_unknown(tmp_path, request_payload, monkeypatch, body, code):
    request_payload["timeout_seconds"] = 1
    helper = _helper(tmp_path, body)
    start = time.monotonic()
    result = _adapter(helper, monkeypatch)(request_payload, Event())
    assert result["error_code"] == code
    assert result["writer_closed"] is False
    assert time.monotonic() - start < 4  # Four seconds includes timeout and bounded subprocess teardown.


def test_cancellation_marker_is_cooperative_and_matching_receipt_preserves_closed_writer(tmp_path, request_payload, monkeypatch):
    helper = _helper(tmp_path,
                     "marker=Path(request['output_path']).parent/'cancel.requested'\n"
                     "while not marker.exists(): time.sleep(0.01)\n" + _receipt_code(status="cancelled"))
    event = Event()
    timer = Timer(0.1, event.set)
    timer.start()
    try:
        result = _adapter(helper, monkeypatch)(request_payload, event)
    finally:
        timer.cancel()
    assert result["status"] == "cancelled"
    assert result["writer_closed"] is True
    assert (Path(request_payload["output_path"]).parent / "cancel.requested").exists()


def test_cancellation_before_launch_is_known_no_writer(tmp_path, request_payload, monkeypatch):
    helper = _helper(tmp_path, "raise RuntimeError('must not launch')\n")
    event = Event()
    event.set()
    result = _adapter(helper, monkeypatch)(request_payload, event)
    assert result["status"] == "cancelled"
    assert result["writer_closed"] is True


def test_unknown_file_or_shared_directory_prevents_helper_launch(tmp_path, request_payload, monkeypatch):
    helper = _helper(tmp_path, "raise RuntimeError('must not launch')\n")
    parent = Path(request_payload["output_path"]).parent
    foreign = parent / "original.wav"
    foreign.write_bytes(b"untouched")
    adapter = _adapter(helper, monkeypatch)
    result = adapter(request_payload, Event())
    assert result["error_code"] == "invalid_helper_request"
    assert result["writer_closed"] is True
    assert foreign.read_bytes() == b"untouched"
    foreign.unlink()
    parent.chmod(0o755)
    assert adapter(request_payload, Event())["error_code"] == "invalid_helper_request"


def test_non_macos_never_uses_an_alternate_exporter(tmp_path, request_payload, monkeypatch):
    monkeypatch.setattr("kenn.core.macos_live_export.sys.platform", "linux")
    helper = _helper(tmp_path, "raise RuntimeError('must not launch')\n")
    result = MacOSLiveExportHelper(helper, enabled=True, supervised_test=True)(request_payload, Event())
    assert result["error_code"] == "unsupported_platform"
    assert result["writer_closed"] is True


def test_missing_output_path_returns_prelaunch_failure(tmp_path, request_payload, monkeypatch):
    helper = _helper(tmp_path, "raise RuntimeError('must not launch')\n")
    del request_payload["output_path"]
    result = _adapter(helper, monkeypatch)(request_payload, Event())
    assert result["error_code"] == "invalid_helper_request"
    assert result["writer_closed"] is True


def test_hardlinked_job_metadata_is_rejected_before_launch(tmp_path, request_payload, monkeypatch):
    helper = _helper(tmp_path, "raise RuntimeError('must not launch')\n")
    source = tmp_path / "foreign-metadata.json"
    source.write_text("{}")
    (Path(request_payload["output_path"]).parent / "manifest.json").hardlink_to(source)
    result = _adapter(helper, monkeypatch)(request_payload, Event())
    assert result["error_code"] == "invalid_helper_request"
    assert source.read_text() == "{}"


@pytest.mark.parametrize("change", [
    {"render_start": "0.1.1"},
    {"render_length": "00.00.00"},
    {"render_start": "١.١.١"},
    {"render_length": "１.０.０"},
    {"render_start": "1000000.1.1"},
    {"render_start": "1.100.1"},
    {"render_length": "1.0.100"},
])
def test_invalid_musical_ranges_never_launch_the_helper(tmp_path, request_payload, monkeypatch, change):
    # The adapter must enforce the same musical-string bounds as job confirmation.
    marker = tmp_path / "launched"
    helper = _helper(tmp_path, f"Path({str(marker)!r}).touch()\n" + _receipt_code())
    result = _adapter(helper, monkeypatch)({**request_payload, **change}, Event())
    assert result["error_code"] == "invalid_helper_request"
    assert result["writer_closed"] is True
    assert not marker.exists()


@pytest.mark.parametrize("character", ["\x00", "\x1f", "\x7f", "\x85", "\u200b", "\u202e", "\U000e0001"])
def test_control_and_format_characters_in_title_never_launch_the_helper(tmp_path, request_payload, monkeypatch, character):
    marker = tmp_path / "launched"
    helper = _helper(tmp_path, f"Path({str(marker)!r}).touch()\n" + _receipt_code())
    result = _adapter(helper, monkeypatch)({**request_payload, "expected_window_title": f"Synthetic{character} set"}, Event())
    assert result["error_code"] == "invalid_helper_request"
    assert result["writer_closed"] is True
    assert not marker.exists()


@pytest.mark.parametrize("start,length", [("000001.01.01", "0.00.01"), ("999999.99.99", "999999.99.99")])
def test_exact_bounded_ascii_ranges_and_unicode_titles_reach_helper_unchanged(tmp_path, request_payload, monkeypatch, start, length):
    expected = {**request_payload, "render_start": start, "render_length": length, "expected_window_title": "Synthetic café 界 set"}
    helper = _helper(tmp_path, f"assert request == {expected!r}\n" + _receipt_code())
    result = _adapter(helper, monkeypatch)(expected, Event())
    assert result["status"] == "completed"
    assert result["render_start"] == start
    assert result["render_length"] == length

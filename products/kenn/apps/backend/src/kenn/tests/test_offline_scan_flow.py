from __future__ import annotations

from io import BytesIO
import math
from pathlib import Path
import time
import wave

import pytest

from kenn.core.fake_live import FakeLiveBackend
from kenn.core.live_action_service import LiveActionService
from kenn.core.offline_scan import OfflineScanService


@pytest.fixture
def confirmed_scan(tmp_path, monkeypatch):
    monkeypatch.setenv("KENN_LIVE_BACKEND", "fake")
    monkeypatch.setenv("KENN_EXPERIMENTAL_LIVE_EXPORT", "1")
    monkeypatch.setenv("KENN_ALLOW_DAW_CONTROL", "1")
    live = FakeLiveBackend()
    revision = ["synthetic-arrangement-revision-1"]
    exports = []

    def export(request, cancelled):
        # A one-second, near-ceiling stereo tone exercises real grounded advice
        # without reading private audio or touching the running Live process.
        output = BytesIO()
        with wave.open(output, "wb") as audio:
            audio.setparams((2, 3, 48000, 0, "NONE", "not compressed"))
            samples = (int(0.99 * 8388607 * math.sin(2 * math.pi * 400 * i / 48000))
                       for i in range(48000))
            audio.writeframes(b"".join(sample.to_bytes(3, "little", signed=True) * 2 for sample in samples))
        Path(request["output_path"]).write_bytes(output.getvalue())
        exports.append(dict(request))
        return {
            "schema": "kenn.live_export_receipt.v1", "status": "completed",
            "writer_closed": True, "channels": 2,
            **{key: request[key] for key in ("output_path", "live_pid", "render_start", "render_length", "sample_rate")},
        }

    jobs = OfflineScanService(tmp_path, exporter=export, read_source_fingerprint=lambda: revision[0])
    actions = LiveActionService(live, offline_scans=jobs)
    result = actions.propose_offline_scan(
        source={"source_kind": "arrangement_main", "fingerprint": revision[0],
                "range_confirmed": True, "tail_policy": "within_range"},
        export_request={"live_pid": 12345, "expected_window_title": "Synthetic disposable set",
                        "render_start": "1.1.1", "render_length": "1.0.0",
                        "sample_rate": 48000, "timeout_seconds": 10},
        session_id="synthetic-owner",
    )
    assert result["ok"] is True and not exports
    return actions, jobs, live, revision, exports, result["proposal"]


def _execute(actions, proposal):
    return actions.execute(proposal, confirm_token=proposal["confirmation_token"],
                           session_id="synthetic-owner", idempotency_key=proposal["action_id"])


def test_confirmed_action_reaches_real_analysis_and_reload_after_owned_wav_disposal(confirmed_scan, tmp_path):
    # This crosses the authority/job/analyzer seam that isolated action stubs cannot verify.
    actions, jobs, live, _, exports, proposal = confirmed_scan
    accepted = _execute(actions, proposal)
    assert accepted["ok"] is True
    deadline = time.monotonic() + 20  # 20 seconds bounds local DSP on this synthetic one-second fixture.
    while time.monotonic() < deadline:
        result = jobs.status("synthetic-owner", accepted["job_id"])
        if result.get("state") not in {"exporting", "analyzing"}:
            break
        time.sleep(0.005)
    else:
        pytest.fail("Confirmed offline scan did not finish within 20 seconds.")

    assert result["state"] == "completed", result
    assert result["audio_deleted"] is True and len(exports) == 1
    assert result["review"]["metrics"] and result["review"]["action_plan"]
    assert result["review"]["audio_retained"] is False
    assert not list(tmp_path.rglob("*.wav"))
    restored = OfflineScanService(tmp_path, exporter=lambda *_: pytest.fail("Reload must not export"),
                                  read_source_fingerprint=lambda: proposal["source"]["fingerprint"])
    assert restored.status("synthetic-owner", accepted["job_id"])["review"] == result["review"]
    assert _execute(actions, proposal)["ok"] is False and len(exports) == 1
    assert live.writes == []


def test_source_change_after_confirmation_prevents_export_and_consumes_the_old_action(confirmed_scan):
    actions, _, live, revision, exports, proposal = confirmed_scan
    revision[0] = "synthetic-arrangement-revision-2"

    assert _execute(actions, proposal)["ok"] is False
    assert _execute(actions, proposal)["ok"] is False
    assert exports == [] and live.writes == []

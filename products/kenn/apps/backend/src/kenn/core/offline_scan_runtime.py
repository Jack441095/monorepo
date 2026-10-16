"""Process-wide OfflineScanService for FakeLive; real Live gets no exporter here.

The scan job module is deliberately inert until someone injects an exporter. This
file is the only place that injects one, and only when KENN_LIVE_BACKEND=fake, so
the HTTP routes can be exercised end to end without any Live UI action. Wiring the
macOS helper in as well waits on Jack's supervised disposable-set run (KENN_PLAN.md,
"Offline Scan audio"); until then a real-Live backend gets ``None`` and callers
report "no qualified candidate".
"""

from __future__ import annotations

from io import BytesIO
import math
import os
from pathlib import Path
import tempfile
from threading import Event, Lock
from typing import Any
import wave

from kenn.core.offline_scan import OfflineScanService


FAKE_ARRANGEMENT_FINGERPRINT = "fake-live-arrangement-v1"

_lock = Lock()
_service: OfflineScanService | None = None
_recovered = False


def _fake_live_selected() -> bool:
    return os.getenv("KENN_LIVE_BACKEND", "osc").strip().casefold() == "fake"


def fake_tone_exporter(request: dict[str, Any], cancelled: Event) -> dict[str, Any]:
    """Write a one-second stereo 24-bit/48 kHz tone to the job's own output path.

    The tone sits at 0.99 of full scale so the real analyzer produces a
    near-ceiling finding to carry through to the report. It reads no private audio
    and touches no running Live process. The receipt mirrors what the macOS helper
    returns once its writer has closed.
    """
    sample_rate = 48000  # Matches the only rate OfflineScanService accepts.
    buffer = BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setparams((2, 3, sample_rate, 0, "NONE", "not compressed"))
        frames = bytearray()
        for i in range(sample_rate):  # 48000 frames = 1 second.
            value = int(0.99 * 8388607 * math.sin(2 * math.pi * 400 * i / sample_rate))  # 400 Hz tone; 8388607 = 2**23 - 1.
            frames += value.to_bytes(3, "little", signed=True) * 2  # Same sample on both channels.
        audio.writeframes(bytes(frames))
    Path(request["output_path"]).write_bytes(buffer.getvalue())
    return {
        "schema": "kenn.live_export_receipt.v1", "status": "completed",
        "writer_closed": True, "channels": 2,
        **{key: request[key] for key in ("output_path", "live_pid", "render_start", "render_length", "sample_rate")},
    }


def _fake_fingerprint() -> str:
    # FakeLive has no arrangement the scan could observe changing, so one constant
    # stands in for the set revision. Tests that need a "source changed" outcome
    # build their own service rather than mutating this one.
    return FAKE_ARRANGEMENT_FINGERPRINT


def get_offline_scan_service() -> OfflineScanService | None:
    """Return the shared FakeLive scan service, or None when Live is real."""
    global _service, _recovered
    if not _fake_live_selected():
        # Real Live has no qualified exporter yet; None keeps every caller on the
        # "no qualified offline export candidate" refusal.
        return None
    with _lock:
        if _service is None:
            runtime_dir = os.getenv(
                "KENN_OFFLINE_SCAN_RUNTIME_DIR",
                # Fake-only name: recovery below assumes no writer can survive, which would
                # be false for a future real exporter sharing this directory.
                str(Path(tempfile.gettempdir()) / "nite-kenn-offline-scan-fake"),
            )
            service = OfflineScanService(
                runtime_dir, exporter=fake_tone_exporter, read_source_fingerprint=_fake_fingerprint,
            )
            _service = service
        if not _recovered:
            try:
                # A previous backend that died mid-scan left its job directory behind.
                # The fake exporter writes in-process, so with that process gone no
                # writer can still hold the WAV and absence is provable here. A real
                # exporter must supply its own Live-side readback instead.
                _service.recover_abandoned(writer_is_absent=lambda request: True)
                _recovered = True
            except RuntimeError:
                # Another backend sharing this directory holds the scan lease, so it owns
                # a live job and we must not touch its WAV. Serve requests now and retry
                # recovery on the next call instead of failing every route until restart.
                pass
        return _service


def reset_offline_scan_service() -> None:
    """Drop the cached service so the next call rebuilds it from the environment."""
    global _service, _recovered
    with _lock:
        _service = None
        _recovered = False

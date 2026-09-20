from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import adapter  # noqa: E402
from contracts import receipt_errors  # noqa: E402


def test_rejects_missing_path_without_calling_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("missing path reached the analysis engine")

    monkeypatch.setattr(adapter, "engine_validate_wav_upload", fail_if_called)
    receipt = adapter.analyze_local_path(tmp_path / "missing.wav")
    assert receipt["status"] == "rejected"
    assert receipt["audio_uploaded"] is False


def test_rejected_validation_does_not_analyse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "probe.wav"
    audio_bytes = b"synthetic-local-audio"
    audio_path.write_bytes(audio_bytes)
    monkeypatch.setattr(adapter, "engine_validate_wav_upload", lambda *args, **kwargs: {"ok": False, "error": "bad fixture"})
    monkeypatch.setattr(adapter, "engine_analyze_wav", lambda *args, **kwargs: pytest.fail("analysis should not run"))
    receipt = adapter.analyze_local_path(audio_path)
    assert receipt["status"] == "rejected"
    assert receipt["source"]["sha256"] == hashlib.sha256(audio_bytes).hexdigest()
    assert receipt["error"] == "bad fixture"


def test_completed_receipt_is_memory_only_and_source_hashed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "probe.wav"
    audio_bytes = b"synthetic-local-audio"
    audio_path.write_bytes(audio_bytes)
    monkeypatch.setattr(adapter, "engine_validate_wav_upload", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        adapter,
        "engine_analyze_wav",
        lambda *args, **kwargs: {"ok": True, "flags": [], "metrics": {"fixture": True}},
    )
    receipt = adapter.analyze_local_path(audio_path, light=True, include_bands=False)
    assert receipt["status"] == "completed"
    assert receipt["source"]["sha256"] == hashlib.sha256(audio_bytes).hexdigest()
    assert receipt["storage"] == "memory_only"
    assert receipt["audio_uploaded"] is False
    assert receipt["external_network"] is False
    assert receipt["analysis"]["metrics"]["fixture"] is True
    assert receipt_errors(receipt) == []

from __future__ import annotations

import hashlib
import io
import sys
import wave
from pathlib import Path

import numpy as np
import pytest


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

import adapter  # noqa: E402


SR = 48_000


def _write_wav(path: Path, left: np.ndarray, right: np.ndarray, sr: int = SR) -> None:
    stereo = np.empty((len(left), 2), dtype=np.int16)
    stereo[:, 0] = np.clip(left * 32767, -32768, 32767).astype(np.int16)
    stereo[:, 1] = np.clip(right * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())


def _tone(amplitude: float, seconds: float = 1.0, freq: float = 440.0, sr: int = SR) -> np.ndarray:
    t = np.arange(int(sr * seconds)) / sr
    return amplitude * np.sin(2 * np.pi * freq * t)


def _findings_by_family(receipt: dict) -> dict[str, dict]:
    return {f["fault_family"]: f for f in receipt["findings"]}


def test_rejects_missing_path_without_calling_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("missing path reached the analysis engine")

    monkeypatch.setattr(adapter, "engine_validate_wav_upload", fail_if_called)
    receipt = adapter.analyze_local_path(tmp_path / "missing.wav")
    assert receipt["status"] == "rejected"
    assert receipt["audio_uploaded"] is False


def test_rejects_unsupported_format_without_calling_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("unsupported format reached the analysis engine")

    monkeypatch.setattr(adapter, "engine_validate_wav_upload", fail_if_called)
    path = tmp_path / "notes.txt"
    path.write_text("not audio")
    receipt = adapter.analyze_local_path(path)
    assert receipt["status"] == "rejected"
    assert "format" in receipt["error"].lower()


def test_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(adapter, "MAX_UPLOAD_BYTES", 16)
    path = tmp_path / "probe.wav"
    _write_wav(path, _tone(0.2), _tone(0.2))
    receipt = adapter.analyze_local_path(path)
    assert receipt["status"] == "rejected"
    assert "size" in receipt["error"].lower()


def test_rejected_validation_does_not_analyse(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    audio_path = tmp_path / "probe.wav"
    audio_bytes = b"synthetic-local-audio"
    audio_path.write_bytes(audio_bytes)
    monkeypatch.setattr(adapter, "engine_validate_wav_upload", lambda *a, **k: {"ok": False, "error": "bad fixture"})
    receipt = adapter.analyze_local_path(audio_path)
    assert receipt["status"] == "rejected"
    assert receipt["source"]["sha256"] == hashlib.sha256(audio_bytes).hexdigest()
    assert receipt["error"] == "bad fixture"


def test_invalid_wav_bytes_fail_cleanly_not_as_a_finding(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.wav"
    path.write_bytes(b"RIFF" + b"\x00" * 40)  # RIFF/WAVE-shaped but truncated/invalid
    receipt = adapter.analyze_local_path(path)
    assert receipt["status"] in ("rejected", "failed")
    assert "error" in receipt
    assert "findings" not in receipt


def test_healthy_mix_is_memory_only_and_source_hashed(tmp_path: Path) -> None:
    path = tmp_path / "healthy.wav"
    left = _tone(0.3)
    right = _tone(0.3)
    audio_bytes = _make_bytes(left, right)
    path.write_bytes(audio_bytes)

    receipt = adapter.analyze_local_path(path, scope="mix_in_progress")
    assert receipt["status"] == "completed"
    assert receipt["source"]["sha256"] == hashlib.sha256(audio_bytes).hexdigest()
    assert receipt["storage"] == "memory_only"
    assert receipt["audio_uploaded"] is False
    assert receipt["external_network"] is False
    assert len(receipt["findings"]) == 3

    findings = _findings_by_family(receipt)
    assert findings["clipping"]["status"] == "no_issue_detected"
    assert findings["headroom"]["status"] == "no_issue_detected"
    assert findings["lr_imbalance"]["status"] == "no_issue_detected"
    for f in findings.values():
        assert f["suggested_next_step"] is None


def test_healthy_mix_default_scope_shows_headroom_as_observational_only(tmp_path: Path) -> None:
    # Frozen qualified behaviour: headroom is only ever an actionable finding
    # when the caller explicitly says this is a mix-in-progress bus. Without
    # that, it is always "observed_not_actionable" -- never a false "no issue"
    # claim and never a false finding.
    path = tmp_path / "healthy.wav"
    _write_wav(path, _tone(0.3), _tone(0.3))
    receipt = adapter.analyze_local_path(path)  # default scope="unknown"
    headroom = _findings_by_family(receipt)["headroom"]
    assert headroom["status"] == "observed_not_actionable"
    assert headroom["suggested_next_step"] is None
    assert "scope" in headroom["explanation"].lower()


def test_clipping_is_flagged_as_a_qualified_finding(tmp_path: Path) -> None:
    path = tmp_path / "clipped.wav"
    clipped = np.clip(_tone(5.0), -1.0, 1.0)
    _write_wav(path, clipped, clipped)
    receipt = adapter.analyze_local_path(path)
    clipping = _findings_by_family(receipt)["clipping"]
    assert clipping["status"] == "finding"
    assert clipping["suggested_next_step"] is not None
    assert clipping["score"] > 0.74  # strong_recommend boundary


def test_low_headroom_is_a_finding_only_with_mix_in_progress_scope(tmp_path: Path) -> None:
    path = tmp_path / "hot.wav"
    hot = _tone(0.95)
    _write_wav(path, hot, hot)

    receipt_scoped = adapter.analyze_local_path(path, scope="mix_in_progress")
    headroom_scoped = _findings_by_family(receipt_scoped)["headroom"]
    assert headroom_scoped["status"] == "finding"
    assert headroom_scoped["suggested_next_step"] is not None

    receipt_unscoped = adapter.analyze_local_path(path)
    headroom_unscoped = _findings_by_family(receipt_unscoped)["headroom"]
    assert headroom_unscoped["status"] == "observed_not_actionable"


def test_persistent_lr_imbalance_is_flagged(tmp_path: Path) -> None:
    path = tmp_path / "panned.wav"
    _write_wav(path, _tone(0.4), _tone(0.05))
    receipt = adapter.analyze_local_path(path)
    imbalance = _findings_by_family(receipt)["lr_imbalance"]
    assert imbalance["status"] == "finding"
    assert imbalance["suggested_next_step"] is not None


def test_silence_abstains_rather_than_fabricating_a_finding(tmp_path: Path) -> None:
    path = tmp_path / "silence.wav"
    silence = np.zeros(SR)
    _write_wav(path, silence, silence)
    receipt = adapter.analyze_local_path(path, scope="mix_in_progress")
    assert receipt["status"] == "completed"
    for finding in receipt["findings"]:
        assert finding["status"] == "no_issue_detected"
        assert finding["suggested_next_step"] is None


def test_receipt_carries_provenance_and_scope_boundary(tmp_path: Path) -> None:
    path = tmp_path / "healthy.wav"
    _write_wav(path, _tone(0.3), _tone(0.3))
    receipt = adapter.analyze_local_path(path)
    assert receipt["qualified_fault_families"] == ["clipping", "headroom", "lr_imbalance"]
    assert receipt["human_qualified"] is False
    assert receipt["provenance"]["qualification_report"].endswith("KENN_V2D_FINAL_REPORT.md")
    assert "unqualified_scope_note" in receipt
    assert receipt["receipt_id"]
    assert receipt["generated_at"]


def _make_bytes(left: np.ndarray, right: np.ndarray, sr: int = SR) -> bytes:
    stereo = np.empty((len(left), 2), dtype=np.int16)
    stereo[:, 0] = np.clip(left * 32767, -32768, 32767).astype(np.int16)
    stereo[:, 1] = np.clip(right * 32767, -32768, 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
    return buffer.getvalue()

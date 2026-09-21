from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "adapter.py"
SPEC = importlib.util.spec_from_file_location("kenn_automix_adapter_test", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def _write_stub_wav(path: Path) -> None:
    import wave

    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 800)


def test_requires_approval_without_calling_engine(tmp_path: Path) -> None:
    stem = tmp_path / "kick.wav"
    _write_stub_wav(stem)

    with patch.object(adapter, "_load_engine_runner") as load_engine:
        receipt = adapter.run_approved_local_automix(tmp_path)

    assert receipt["status"] == "awaiting_human_approval"
    assert receipt["human_approval"] is False
    assert receipt["audio_uploaded"] is False
    assert receipt["source"]["sha256"]["kick.wav"] == hashlib.sha256(stem.read_bytes()).hexdigest()
    load_engine.assert_not_called()


def test_rejects_output_inside_audio_too(tmp_path: Path) -> None:
    stem_dir = tmp_path / "stems"
    stem_dir.mkdir()
    _write_stub_wav(stem_dir / "kick.wav")

    with patch.object(adapter, "AUDIO_TOO_ROOT", tmp_path / "audio-too"):
        output = tmp_path / "audio-too" / "outputs"
        receipt = adapter.run_approved_local_automix(
            stem_dir, approved=True, output_dir=output
        )

    assert receipt["status"] == "rejected"
    assert "outside" in receipt["error"]


def test_approved_run_returns_metadata_only_receipt(tmp_path: Path) -> None:
    stem_dir = tmp_path / "stems"
    stem_dir.mkdir()
    stem = stem_dir / "kick.wav"
    _write_stub_wav(stem)
    output = tmp_path / "out"
    delivery = {
        "ok": True,
        "project_id": "demo",
        "version": 1,
        "wav_path": str(output / "mix.wav"),
        "zip_path": str(output / "mix.zip"),
        "manifest_path": str(output / "manifest.json"),
        "report_path": str(output / "report.json"),
        "private_audio_bytes": b"must not appear",
    }

    with patch.object(adapter, "_ENGINE_RUNNER", lambda *args, **kwargs: delivery):
        receipt = adapter.run_approved_local_automix(
            stem_dir, approved=True, output_dir=output, project_id="Demo Mix"
        )

    assert receipt["status"] == "completed"
    assert receipt["project_id"] == "Demo-Mix"
    assert receipt["audio_uploaded"] is False
    assert receipt["external_network"] is False
    assert receipt["storage"] == "local_output_only"
    assert "private_audio_bytes" not in receipt["delivery"]
    assert receipt["delivery"]["wav_path"] == str(output / "mix.wav")


def test_engine_failure_is_reported_honestly(tmp_path: Path) -> None:
    stem_dir = tmp_path / "stems"
    stem_dir.mkdir()
    _write_stub_wav(stem_dir / "kick.wav")

    def fail(*args, **kwargs):
        raise RuntimeError("Mix failed delivery safety gate: clipping")

    with patch.object(adapter, "_ENGINE_RUNNER", fail):
        receipt = adapter.run_approved_local_automix(stem_dir, approved=True)

    assert receipt["status"] == "failed"
    assert "delivery safety gate" in receipt["error"]

"""Local and queued routes preserve effective preview Hz without decoding twice."""

from __future__ import annotations

import wave

import numpy as np
import pytest

import automix_local
import automix_worker
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking


class _MaskingCaptured(Exception):
    """Stop before mix planning; the test qualifies only the preparation handoff."""


@pytest.mark.parametrize("queued", [False, True], ids=["local", "queued"])
def test_automix_routes_reuse_decimated_preview_with_effective_rate(tmp_path, monkeypatch, queued):
    sample_rate = 44100
    time = np.arange(sample_rate * 4) / sample_rate  # Four seconds forces 2x preview decimation.
    upload_root = tmp_path / "uploads"
    stem_dir = upload_root / "generated-preview"
    stem_dir.mkdir(parents=True)
    for name, frequency_hz in [("bass.wav", 100), ("keys.wav", 440)]:
        with wave.open(str(stem_dir / name), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes((0.2 * np.sin(2 * np.pi * frequency_hz * time) * 32767).astype("<i2").tobytes())
    route = automix_worker if queued else automix_local
    monkeypatch.setattr(route, "classify_stems", lambda *args, **kwargs: [])
    monkeypatch.setattr(route, "correct_stem_polarity", lambda stems, rate: ([], {}))
    captured = []

    def reject_redecode(*args, **kwargs):
        # A metadata regression must fail rather than hide behind a second WAV decode.
        raise AssertionError("Masking re-decoded audio instead of reusing the qualified preview")

    def capture_masking(stems, **kwargs):
        result = analyze_stems_masking(stems, read_wav_mono=reject_redecode, spectral_bands=kwargs["spectral_bands"])
        captured.append(result)
        raise _MaskingCaptured()

    monkeypatch.setattr(route, "analyze_stems_masking", capture_masking)
    if queued:
        # Exercise the real queued path without a job database or background worker.
        monkeypatch.setattr(route, "UPLOAD_ROOT", upload_root)
        monkeypatch.setattr(route.stem_uploads, "require_source_ready", lambda *args, **kwargs: None)
        monkeypatch.setattr(route, "_update_job_status", lambda *args, **kwargs: None)
        monkeypatch.setattr(route, "_resource_snapshot", lambda *args: {"elapsed_ms": 0.0})
        monkeypatch.setattr(route, "render_unprocessed_stem_sum", lambda stems: {"mixdown_wav_bytes": b"", "stem_audio": {}})
        route._process_job({"id": "generated-job", "project_id": stem_dir.name})
    else:
        with pytest.raises(_MaskingCaptured):
            route.run_local_automix(stem_dir, output_dir=tmp_path / "out")
    assert len(captured) == 1
    assert {stem["name"] for stem in captured[0]["stems"]} == {"bass", "keys"}
    assert {source["sample_rate"] for source in captured[0]["activity"]["sources"]} == {22050.0}
    assert captured[0]["activity"]["pairs"][0]["simultaneously_active_frame_count"] == 16

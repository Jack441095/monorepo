"""Per-stem WAV export from package_mixdown_delivery().

When a render is run with capture_stem_audio=True, each fully-processed stem
(exactly as it summed into the master bus) is written under stems_v{version}/
so per-stem corrections can be auditioned in isolation. Delivery writes nothing
extra when the render did not capture stems (backward compatible).
"""

from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import numpy as np

from audio_analysis.mixdown.stem_classifier import StemProfile
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
from audio_analysis.mixdown.mix_delivery import package_mixdown_delivery
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems

SR = 44100
N = SR * 3
_T = np.arange(N) / SR


def _profile(name: str, instrument: str) -> StemProfile:
    return StemProfile(
        name=name, instrument=instrument, peak_dbfs=-6.0, rms_dbfs=-18.0, crest_factor_db=12.0,
    )


def _stems():
    return [
        ("vox.wav", "vocal", (0.3 * np.sin(2 * np.pi * 300 * _T)).astype(np.float64)),
        ("gtr.wav", "guitar", (0.3 * np.sin(2 * np.pi * 500 * _T)).astype(np.float64)),
    ]


def _plan_and_dicts():
    stems = _stems()
    profiles = [_profile(n, i) for n, i, _ in stems]
    plan = generate_mix_plan(profiles, genre="pop", target_lufs=-12.0)
    plan.genre = "pop"
    plan.bus.limiter_ceiling_db = -1.0
    stem_dicts = [{"name": n, "samples": s, "sample_rate": SR} for n, _, s in stems]
    return plan, stem_dicts


def test_stems_written_when_captured():
    plan, stem_dicts = _plan_and_dicts()
    result = mix_and_render_stems(stem_dicts, plan, capture_stem_audio=True)
    assert result.get("stem_audio"), "render should capture stem_audio when asked"

    with tempfile.TemporaryDirectory() as td:
        delivery = package_mixdown_delivery(project_id="proj", render_result=result, output_dir=td)
        stem_paths = delivery.get("stem_paths") or {}
        assert set(stem_paths) == {"vox.wav", "gtr.wav"}
        for path in stem_paths.values():
            p = Path(path)
            assert p.exists() and p.stat().st_size > 44
            assert "stems_v1" in str(p)
            # Each is a valid, full-length stereo WAV.
            with wave.open(str(p), "rb") as w:
                assert w.getnchannels() == 2
                assert w.getframerate() == SR
                assert w.getnframes() == N


def test_no_stems_written_without_capture():
    plan, stem_dicts = _plan_and_dicts()
    result = mix_and_render_stems(stem_dicts, plan, capture_stem_audio=False)
    with tempfile.TemporaryDirectory() as td:
        delivery = package_mixdown_delivery(project_id="proj", render_result=result, output_dir=td)
        assert delivery.get("stem_paths") == {}
        assert not (Path(td) / "proj" / "stems_v1").exists()


def test_master_package_unchanged_by_stem_export():
    """Stem export must not alter the master WAV/zip contract."""
    plan, stem_dicts = _plan_and_dicts()
    result = mix_and_render_stems(stem_dicts, plan, capture_stem_audio=True)
    with tempfile.TemporaryDirectory() as td:
        delivery = package_mixdown_delivery(project_id="proj", render_result=result, output_dir=td)
        assert Path(delivery["wav_path"]).exists()
        assert Path(delivery["zip_path"]).exists()
        assert delivery["ok"] is True

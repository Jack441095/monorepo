from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import soundfile as sf
import pytest


MODULE_PATH = Path(__file__).with_name("audio_segment_windows.py")
SPEC = importlib.util.spec_from_file_location("audio_segment_windows", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_segmenter_finds_separated_active_windows(tmp_path: Path):
    y = np.zeros(32_000, dtype=np.float32)
    y[1_000:3_000] = 0.8
    y[20_000:23_000] = 0.7
    path = tmp_path / "pulses.wav"
    sf.write(path, y, 16_000)
    result = MODULE.segment(path)
    assert result["record_type"] == "slo_audio_segment_windows"
    assert len(result["windows"]) == 2
    assert result["windows"][0]["end_seconds"] < result["windows"][1]["start_seconds"]
    assert result["safety"]["semantic_labels_created"] is False


def test_segmenter_falls_back_to_one_window_for_silence(tmp_path: Path):
    path = tmp_path / "silence.wav"
    sf.write(path, np.zeros(8_000, dtype=np.float32), 16_000)
    result = MODULE.segment(path)
    assert len(result["windows"]) == 1
    assert result["windows"][0]["start_seconds"] == 0.0


def test_segmenter_rejects_invalid_parameters(tmp_path: Path):
    path = tmp_path / "tone.wav"
    sf.write(path, np.ones(1_000, dtype=np.float32), 16_000)
    with pytest.raises(ValueError, match="invalid segmentation"):
        MODULE.segment(path, max_segments=0)

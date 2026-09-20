from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


MODULE_PATH = Path(__file__).with_name("fft_drum_selective_benchmark.py")
SPEC = importlib.util.spec_from_file_location("fft_drum_selective", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def test_selective_metrics_tracks_precision_and_coverage():
    y = np.asarray(["Kick", "Snare", "Kick", "Clap"])
    pred = np.asarray(["Kick", "Clap", "Kick", "Snare"])
    confidence = np.asarray([0.95, 0.91, 0.55, 0.4])
    result = MODULE.selective_metrics(y, pred, confidence, 0.9)
    assert result["accepted"] == 2
    assert result["coverage"] == 50.0
    assert result["precision"] == 50.0


def test_selective_metrics_empty_operating_point():
    y = np.asarray(["Kick"])
    pred = np.asarray(["Kick"])
    confidence = np.asarray([0.5])
    result = MODULE.selective_metrics(y, pred, confidence, 0.9)
    assert result["accepted"] == 0
    assert result["coverage"] == 0.0
    assert result["precision"] == 0.0

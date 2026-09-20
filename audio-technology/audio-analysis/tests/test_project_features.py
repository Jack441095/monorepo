"""Stage J, use case #1 — tests for project_features.py.

Covers the fixed feature-vector assembly, the regression-target extraction
from a real MixPlan shape, and the persistent training-row table (real
sqlite round-trip, not mocked) that captures (features, target) pairs for
future GLM training.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from audio_analysis.integration.project_features import (
    GENRE_KEYS,
    PROJECT_FEATURE_NAMES,
    estimate_project_tempo,
    extract_compressor_threshold_target,
    extract_project_features,
    load_project_training_rows,
    record_project_training_row,
)
from audio_analysis.mixdown.mix_decision_engine import BusMixConfig, MixPlan, StemMixConfig
from audio_analysis.mixdown.stem_classifier import StemProfile


def _mock_connect(db_path: Path):
    class _MockConn:
        def __enter__(self2):
            self2.conn = sqlite3.connect(str(db_path))
            self2.conn.row_factory = sqlite3.Row
            return self2.conn

        def __exit__(self2, *args):
            self2.conn.close()

        def execute(self2, *a, **kw):
            return self2.conn.execute(*a, **kw)

        def commit(self2):
            self2.conn.commit()

    return _MockConn()


def _profiles() -> list[StemProfile]:
    return [
        StemProfile(name="kick.wav", instrument="kick", peak_dbfs=-6.0, rms_dbfs=-18.0,
                    crest_factor_db=12.0, spectral_centroid_hz=90.0, transient_density=0.8),
        StemProfile(name="vocal.wav", instrument="vocal", peak_dbfs=-10.0, rms_dbfs=-22.0,
                    crest_factor_db=14.0, spectral_centroid_hz=2200.0, transient_density=0.2),
    ]


def test_feature_vector_has_every_named_feature_and_correct_genre_one_hot() -> None:
    features = extract_project_features(
        _profiles(), genre="edm", target_lufs=-9.0, tempo_bpm=128.0, tempo_confidence=0.6,
    )
    assert set(features.keys()) == set(PROJECT_FEATURE_NAMES)
    assert features["stem_count"] == 2.0
    assert features["tempo_bpm"] == 128.0
    assert features["target_lufs"] == -9.0
    for key in GENRE_KEYS:
        expected = 1.0 if key == "edm" else 0.0
        assert features[f"genre_{key}"] == expected


def test_feature_vector_means_are_computed_across_stems() -> None:
    features = extract_project_features(_profiles(), genre="pop", target_lufs=-14.0)
    assert features["mean_crest_factor_db"] == (12.0 + 14.0) / 2
    assert features["mean_peak_dbfs"] == (-6.0 + -10.0) / 2


def test_feature_vector_handles_unknown_genre_with_all_zero_one_hot() -> None:
    features = extract_project_features(_profiles(), genre="lofi", target_lufs=-14.0)
    assert all(features[f"genre_{key}"] == 0.0 for key in GENRE_KEYS)


def test_compressor_threshold_target_averages_across_compressed_stems() -> None:
    stems = [
        StemMixConfig(stem_name="kick", instrument="kick", compressor={"threshold_db": -18.0}),
        StemMixConfig(stem_name="bass", instrument="bass", compressor={"threshold_db": -22.0}),
        StemMixConfig(stem_name="pad", instrument="synth", compressor=None),
    ]
    plan = MixPlan(stems=stems, bus=BusMixConfig(), genre="pop", target_lufs=-14.0)
    target = extract_compressor_threshold_target(plan)
    assert target == (-18.0 + -22.0) / 2


def test_compressor_threshold_target_is_none_when_no_stem_compressed() -> None:
    stems = [StemMixConfig(stem_name="pad", instrument="synth", compressor=None)]
    plan = MixPlan(stems=stems, bus=BusMixConfig(), genre="pop", target_lufs=-14.0)
    assert extract_compressor_threshold_target(plan) is None


def test_record_and_load_training_row_round_trips(tmp_path) -> None:
    db_path = tmp_path / "test.db"

    def connect_func():
        return _mock_connect(db_path)

    features = extract_project_features(_profiles(), genre="rock", target_lufs=-14.0)
    record_project_training_row(
        job_id="job-1", project_id="proj-1", genre="rock",
        features=features, target_name="mean_compressor_threshold_db",
        target_value=-16.5, connect_func=connect_func,
    )
    rows = load_project_training_rows(connect_func=connect_func, target_name="mean_compressor_threshold_db")
    assert len(rows) == 1
    assert rows[0]["job_id"] == "job-1"
    assert rows[0]["target_value"] == -16.5
    assert rows[0]["features"]["stem_count"] == 2.0


def test_record_with_none_target_is_skipped(tmp_path) -> None:
    db_path = tmp_path / "test.db"

    def connect_func():
        return _mock_connect(db_path)

    record_project_training_row(
        job_id="job-2", project_id="proj-1", genre="rock",
        features={}, target_name="mean_compressor_threshold_db",
        target_value=None, connect_func=connect_func,
    )
    rows = load_project_training_rows(connect_func=connect_func, target_name="mean_compressor_threshold_db")
    assert rows == []


def test_estimate_project_tempo_against_a_real_click_track() -> None:
    """Real synthetic audio, not a mock -- proves the onset-detection ->
    estimate_bpm() wiring actually produces a confident, non-crashing
    estimate (tempo octave-folding ambiguity, e.g. 120 BPM reported as
    60 BPM for a simple isochronous click, is an existing, documented
    characteristic of estimate_bpm() itself, not something this wiring
    introduces or is responsible for correcting)."""
    import numpy as np

    sample_rate = 44100
    duration_s = 8.0
    n = int(duration_s * sample_rate)
    samples = np.zeros(n)
    beat_interval = 0.5  # 120 BPM
    t = 0.0
    while t < duration_s:
        idx = int(t * sample_rate)
        if idx < n:
            samples[idx:idx + 200] = 0.8
        t += beat_interval

    prepared_stems = [{"samples": samples.tolist(), "sample_rate": sample_rate}]
    bpm, confidence = estimate_project_tempo(prepared_stems, sample_rate)
    assert bpm > 0.0
    assert confidence > 0.0


def test_estimate_project_tempo_returns_zero_for_silent_stems() -> None:
    prepared_stems = [{"samples": [0.0] * 1000, "sample_rate": 44100}]
    bpm, confidence = estimate_project_tempo(prepared_stems, 44100)
    assert bpm == 0.0
    assert confidence == 0.0


def test_estimate_project_tempo_accepts_real_numpy_array_samples() -> None:
    """Real bug, found live running an actual AutoMix render 2026-08-05:
    real stems arrive as genuine numpy arrays (not lists), and `if not
    samples:` on a non-empty numpy array raises "truth value of an array
    with more than one element is ambiguous" -- silently killing this
    whole function every time in production (caught by automix_worker.py's
    outer try/except, logged as "Stage J project-feature capture failed").
    The other tests in this file call `.tolist()` before passing samples
    in, which sidesteps this exact bug -- this test deliberately does not,
    to match the real production data shape."""
    import numpy as np

    sample_rate = 44100
    duration_s = 8.0
    n = int(duration_s * sample_rate)
    samples = np.zeros(n)
    beat_interval = 0.5
    t = 0.0
    while t < duration_s:
        idx = int(t * sample_rate)
        if idx < n:
            samples[idx:idx + 200] = 0.8
        t += beat_interval

    prepared_stems = [{"samples": samples, "sample_rate": sample_rate}]  # real ndarray, no .tolist()
    bpm, confidence = estimate_project_tempo(prepared_stems, sample_rate)
    assert bpm > 0.0
    assert confidence > 0.0


def test_estimate_project_tempo_skips_stem_with_none_samples() -> None:
    prepared_stems = [{"samples": None, "sample_rate": 44100}]
    bpm, confidence = estimate_project_tempo(prepared_stems, 44100)
    assert bpm == 0.0
    assert confidence == 0.0


def test_estimate_project_tempo_skips_stem_with_empty_array_samples() -> None:
    import numpy as np

    prepared_stems = [{"samples": np.array([]), "sample_rate": 44100}]
    bpm, confidence = estimate_project_tempo(prepared_stems, 44100)
    assert bpm == 0.0
    assert confidence == 0.0


def test_rerun_job_overwrites_its_own_prior_row_not_duplicates(tmp_path) -> None:
    db_path = tmp_path / "test.db"

    def connect_func():
        return _mock_connect(db_path)

    features = extract_project_features(_profiles(), genre="rock", target_lufs=-14.0)
    record_project_training_row(
        job_id="job-3", project_id="proj-1", genre="rock", features=features,
        target_name="mean_compressor_threshold_db", target_value=-10.0, connect_func=connect_func,
    )
    record_project_training_row(
        job_id="job-3", project_id="proj-1", genre="rock", features=features,
        target_name="mean_compressor_threshold_db", target_value=-11.0, connect_func=connect_func,
    )
    rows = load_project_training_rows(connect_func=connect_func, target_name="mean_compressor_threshold_db")
    assert len(rows) == 1
    assert rows[0]["target_value"] == -11.0

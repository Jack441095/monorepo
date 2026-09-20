import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("aspect_similarity.py")
SPEC = importlib.util.spec_from_file_location("aspect_similarity", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _card(path="x.wav", pitch=220.0, centroid=1000.0, low=0.5):
    return {
        "path": path,
        "source": {"analysis_duration_seconds": 1.0},
        "signal": {"rms_dbfs": -20.0, "peak_dbfs": -3.0, "crest_factor": 4.0,
                   "leading_silence_seconds": 0.0},
        "spectrum": {"spectral_centroid_hz": centroid, "spectral_rolloff_hz": 2000.0,
                     "spectral_flatness": 0.1, "low_band_energy_ratio": low,
                     "high_band_energy_ratio": 0.2, "harmonic_energy_ratio": 0.8,
                     "zero_crossing_rate": 0.03},
        "pitch": {"median_f0_hz": pitch, "voiced_frame_fraction": 0.8},
        "temporal": {"onset_density_per_second": 1.0, "periodicity_strength": 0.5,
                     "periodicity_seconds": 1.0},
        "spatial": {"stereo_correlation": 1.0},
    }


def test_identical_cards_score_one():
    result = MODULE.compare_cards(_card(), _card())
    assert result["similarity"]["overall"] == 1.0
    assert all(v == 1.0 for v in result["similarity"]["aspects"].values())


def test_aspects_can_disagree_and_remain_explainable():
    result = MODULE.compare_cards(_card(), _card(pitch=880.0, centroid=6000.0, low=0.05))
    assert result["similarity"]["aspects"]["pitch"] < 1.0
    assert result["similarity"]["aspects"]["spectrum"] < 1.0
    assert result["safety"]["human_calibration_required"] is True

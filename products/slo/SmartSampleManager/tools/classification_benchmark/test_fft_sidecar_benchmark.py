import numpy as np
import soundfile as sf

from fft_sidecar_benchmark import FEATURE_NAMES, extract


def test_extract_matches_sidecar_schema(tmp_path):
    sr = 32000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    y = (0.2 * np.sin(2 * np.pi * 110 * t)).astype(np.float32)
    y[:: sr // 2] += 0.7
    path = tmp_path / "fixture.wav"
    sf.write(path, y, sr)
    value = extract(str(path))
    assert value is not None
    assert value.shape == (len(FEATURE_NAMES),)
    assert np.isfinite(value).all()
    assert np.isclose(value[2:5].sum(), 1.0, atol=1e-3)
    assert value[0] == 2.0


def test_short_audio_abstains(tmp_path):
    path = tmp_path / "short.wav"
    sf.write(path, np.zeros(1024, dtype=np.float32), 32000)
    assert extract(str(path)) is None

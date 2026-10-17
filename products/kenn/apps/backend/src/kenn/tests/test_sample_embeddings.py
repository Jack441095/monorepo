from __future__ import annotations

import math
import struct
import wave

import pytest

from kenn.core import sample_embeddings
from kenn.core.sample_embeddings import cosine_similarity, extract_embedding, rank_by_similarity


def _tone_wav(tmp_path, name, *, freq=440.0, seconds=2.0, framerate=32000):
    n = int(seconds * framerate)
    path = tmp_path / name
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(framerate)
        scale = (1 << 15) - 1
        frames = bytearray()
        for i in range(n):
            v = 0.8 * math.sin(2 * math.pi * freq * i / framerate)
            frames += struct.pack("<h", int(v * scale))
        handle.writeframes(bytes(frames))
    return path


def _requires_model():
    if sample_embeddings._get_session() is None:
        pytest.skip("PANNs embedding model/onnxruntime is not available in this environment")


def test_extract_embedding_returns_expected_dimension(tmp_path) -> None:
    _requires_model()
    path = _tone_wav(tmp_path, "tone.wav")
    vector, reason = extract_embedding(path)
    assert reason is None
    assert vector is not None
    assert vector.shape == (sample_embeddings.EMBEDDING_DIM,)


def test_extract_embedding_abstains_on_missing_file(tmp_path) -> None:
    _requires_model()
    vector, reason = extract_embedding(tmp_path / "missing.wav")
    assert vector is None
    assert "not found" in reason


def test_extract_embedding_abstains_honestly_without_onnxruntime(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sample_embeddings, "_ort", None)
    monkeypatch.setattr(sample_embeddings, "_session", None)
    monkeypatch.setattr(sample_embeddings, "_session_load_failed", False)
    path = _tone_wav(tmp_path, "tone.wav")
    vector, reason = extract_embedding(path)
    assert vector is None
    assert "not installed" in reason


def test_decode_and_resample_window_decodes_wav_and_aiff_natively_and_abstains_on_broken_aiff(tmp_path) -> None:
    broken_aiff = tmp_path / "broken.aif"
    broken_aiff.write_bytes(b"FORM" + b"\x00" * 40)
    window, aiff_reason = sample_embeddings._decode_and_resample_window(broken_aiff)
    assert window is None
    assert "AIFF could not be decoded" in aiff_reason

    rate = 44100
    frames = rate
    pcm_be = b"".join(
        struct.pack(">h", int(0.6 * math.sin(2.0 * math.pi * 440.0 * i / rate) * 32767))
        for i in range(frames)
    )
    comm_data = struct.pack(">hIhHQ", 1, frames, 16, 0x400E, 0xAC44000000000000)
    ssnd_data = struct.pack(">II", 0, 0) + pcm_be
    form_body = b"AIFF" + b"COMM" + struct.pack(">I", len(comm_data)) + comm_data + b"SSND" + struct.pack(">I", len(ssnd_data)) + ssnd_data
    valid_aiff = tmp_path / "tone.aif"
    valid_aiff.write_bytes(b"FORM" + struct.pack(">I", len(form_body)) + form_body)
    aiff_window, valid_aiff_reason = sample_embeddings._decode_and_resample_window(valid_aiff)
    assert valid_aiff_reason is None
    assert aiff_window is not None
    assert aiff_window.shape == (sample_embeddings.TARGET_WINDOW_SAMPLES,)

    wav_path = _tone_wav(tmp_path, "tone.wav", framerate=44100)
    wav_window, wav_reason = sample_embeddings._decode_and_resample_window(wav_path)
    assert wav_reason is None
    assert wav_window is not None
    assert wav_window.shape == (sample_embeddings.TARGET_WINDOW_SAMPLES,)


def test_native_resample_mono_window_folds_stereo_and_pads_or_truncates_to_5_seconds(tmp_path) -> None:
    from kenn.core import native_fft

    if not native_fft.available() or sample_embeddings._np is None:
        pytest.skip("native DSP extension or numpy is not available in this environment")
    np = sample_embeddings._np

    # 1.5 s stereo 48 kHz 440 Hz tone -> resampled to 48,000 active samples + 112,000 zero-padded tail at 32 kHz
    sr = 48000
    t = np.arange(int(1.5 * sr), dtype=np.float64) / sr
    left = (0.6 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    right = (0.2 * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.float32)
    window = native_fft.resample_mono_window([left, right], sr)
    assert window is not None
    assert window.shape == (sample_embeddings.TARGET_WINDOW_SAMPLES,)
    # Active region (skipping 20-sample filter edge transient) has peak ~0.4 (mean of 0.6 and 0.2)
    assert float(np.max(np.abs(window[100:47900]))) == pytest.approx(0.4, abs=0.01)
    # Tail beyond 1.5 s (48,000 samples at 32 kHz) is zero-padded
    assert float(np.max(np.abs(window[48005:]))) == 0.0

    # Coprime sample rate (44,101 Hz) exercises the continuous-time Kaiser-sinc branch
    t_coprime = np.arange(44101, dtype=np.float64) / 44101.0
    mono_coprime = (0.5 * np.sin(2.0 * np.pi * 440.0 * t_coprime)).astype(np.float32)
    coprime_win = native_fft.resample_mono_window([mono_coprime], 44101)
    assert coprime_win.shape == (sample_embeddings.TARGET_WINDOW_SAMPLES,)
    assert float(np.max(np.abs(coprime_win[100:31900]))) == pytest.approx(0.5, abs=0.01)
    assert float(np.max(np.abs(coprime_win[32005:]))) == 0.0


def test_decode_and_resample_window_rejects_out_of_range_rates_nan_and_stale_extension(tmp_path, monkeypatch) -> None:
    from kenn.core import native_fft

    if not native_fft.available() or sample_embeddings._np is None:
        pytest.skip("native DSP extension or numpy is not available in this environment")
    np = sample_embeddings._np

    for bad_rate, label in ((2, "2 Hz"), (60_000_000, "60000000 Hz")):
        bad_wav = tmp_path / f"rate_{bad_rate}.wav"
        with wave.open(str(bad_wav), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(bad_rate)
            handle.writeframes(np.full(2000, 1000, dtype="<i2").tobytes())
        y, reason = sample_embeddings._decode_and_resample_window(bad_wav)
        assert y is None
        assert label in reason

    with pytest.raises(ValueError, match="finite"):
        native_fft.resample_mono_window([np.array([0.1, float("nan"), 0.2], dtype=np.float32)], 44100)

    monkeypatch.setenv("KENN_DSP_NATIVE", "0")
    y_off, off_reason = sample_embeddings._decode_and_resample_window(_tone_wav(tmp_path, "off.wav"))
    assert y_off is None
    assert "not built or is disabled" in off_reason
    monkeypatch.delenv("KENN_DSP_NATIVE", raising=False)

    real_module = native_fft._load()

    class _StaleModule:
        decode_pcm = staticmethod(real_module.decode_pcm)

    monkeypatch.setattr(native_fft, "_load", lambda: _StaleModule)
    y_stale, stale_reason = sample_embeddings._decode_and_resample_window(_tone_wav(tmp_path, "stale.wav"))
    assert y_stale is None
    assert "out of date" in stale_reason


def test_cosine_similarity_of_identical_vectors_is_one() -> None:
    if sample_embeddings._np is None:
        pytest.skip("numpy is not installed in this environment")
    v = sample_embeddings._np.array([1.0, 2.0, 3.0])
    assert cosine_similarity(v, v) == pytest.approx(1.0)


def test_cosine_similarity_of_zero_vector_is_honestly_zero_not_nan() -> None:
    if sample_embeddings._np is None:
        pytest.skip("numpy is not installed in this environment")
    zero = sample_embeddings._np.zeros(4)
    other = sample_embeddings._np.array([1.0, 0.0, 0.0, 0.0])
    assert cosine_similarity(zero, other) == 0.0


def test_rank_by_similarity_ranks_more_similar_tones_higher(tmp_path) -> None:
    _requires_model()
    target = _tone_wav(tmp_path, "target_440.wav", freq=440.0)
    close = _tone_wav(tmp_path, "close_445.wav", freq=445.0)
    far = _tone_wav(tmp_path, "far_noise.wav", freq=1.0, seconds=0.01)  # near-silent/short, very different
    candidates = [("close", close), ("far", far)]
    ranked, reason = rank_by_similarity(target, candidates, limit=10)
    assert reason is None
    assert [r["sample_id"] for r in ranked][0] == "close"


def test_rank_by_similarity_excludes_target_path_from_its_own_candidates(tmp_path) -> None:
    _requires_model()
    target = _tone_wav(tmp_path, "target.wav")
    candidates = [("self", target)]
    ranked, reason = rank_by_similarity(target, candidates, limit=10)
    assert reason == "none of the candidate files could be embedded"
    assert ranked is None


def test_rank_by_similarity_bounds_candidate_pool_size(tmp_path) -> None:
    _requires_model()
    target = _tone_wav(tmp_path, "target.wav")
    many = [(f"c{i}", _tone_wav(tmp_path, f"c{i}.wav", freq=440.0 + i)) for i in range(3)]
    ranked, reason = rank_by_similarity(target, many, limit=10)
    assert reason is None
    assert len(ranked) <= sample_embeddings.MAX_CANDIDATES


def test_rank_by_similarity_abstains_when_target_cannot_be_embedded(tmp_path) -> None:
    ranked, reason = rank_by_similarity(tmp_path / "missing.wav", [], limit=10)
    assert ranked is None
    assert "could not embed the target file" in reason

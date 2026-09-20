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


def test_extract_embedding_abstains_honestly_without_librosa(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(sample_embeddings, "_librosa", None)
    path = _tone_wav(tmp_path, "tone.wav")
    vector, reason = extract_embedding(path)
    assert vector is None
    assert "not installed" in reason


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

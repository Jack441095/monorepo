"""Bounded, opt-in sample-similarity search using a real audio embedding.

Uses the PANNs Cnn10 512D embedding model, expected at
``kenn/artifacts/models/panns_cnn10/panns_cnn10_embedding.onnx`` (override
with ``KENN_PANNS_MODEL_DIR``) -- see that directory's ``README.md`` for
full provenance and license (MIT code, CC BY 4.0 training data, attribution
required) and how to obtain the file. Like the existing MiniLM retrieval
model under ``artifacts/models/minilm/``, this is a machine-local weight
file, not committed to git (``artifacts/`` is gitignored) -- honest
abstention below covers a checkout where it isn't present. Only the
embedding output is used here; no classifier head or label taxonomy is
reused from the sibling SLO project this model was validated in.

This is deliberately separate from ``sample_library.py``'s bulk filename
scan and from ``analyze_sample_audio``'s BPM/key estimate: computing an
embedding decodes and runs a real neural-network inference pass per file,
which is far too slow to run over an entire (tens-of-thousands-of-file)
library on every request. Callers must supply a bounded candidate list
(e.g. the output of ``search_samples``) -- this module never scans a
whole library on its own.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:  # Optional; abstain honestly rather than fabricate a similarity score.
    import numpy as _np
except ImportError:
    _np = None

try:
    import onnxruntime as _ort
except ImportError:
    _ort = None

try:
    import librosa as _librosa
except ImportError:
    _librosa = None

EMBEDDING_DIM = 512
TARGET_SAMPLE_RATE = 32000
TARGET_WINDOW_SAMPLES = 160_000  # 5 seconds at 32kHz, matching the model's validated input
MAX_CANDIDATES = 25  # bound the per-request inference cost; never a silent full-library scan

_DEFAULT_MODEL_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "models" / "panns_cnn10"

_session: Any = None
_session_load_failed = False


def _model_path() -> Path:
    """Model directory, overridable so a checkout without the (gitignored,
    machine-local, like ``artifacts/models/minilm``) weight file installed
    can point at wherever it was placed -- see this module's docstring and
    ``artifacts/models/panns_cnn10/README.md`` for provenance/license and
    how to obtain the file.
    """
    configured = os.getenv("KENN_PANNS_MODEL_DIR", "").strip()
    model_dir = Path(configured).expanduser() if configured else _DEFAULT_MODEL_DIR
    return model_dir / "panns_cnn10_embedding.onnx"


def _get_session() -> Any | None:
    global _session, _session_load_failed
    if _session is not None:
        return _session
    if _session_load_failed or _ort is None:
        return None
    model_path = _model_path()
    if not model_path.is_file():
        return None
    try:
        _session = _ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    except Exception:
        _session_load_failed = True
        return None
    return _session


def extract_embedding(path: Path) -> tuple[Any, None] | tuple[None, str]:
    """Real 512D embedding for one audio file, or an honest abstention reason.

    Returns ``(vector, None)`` or ``(None, reason)`` -- exactly one is
    ``None``. Decodes at most ``TARGET_WINDOW_SAMPLES`` (padded if shorter),
    matching the model's validated input shape exactly.
    """
    if _np is None:
        return None, "the optional numpy dependency is not installed"
    if _librosa is None:
        return None, "the optional librosa dependency is not installed"
    session = _get_session()
    if session is None:
        if _ort is None:
            return None, "the optional onnxruntime dependency is not installed"
        return None, "the embedding model could not be loaded"
    if not path.is_file():
        return None, "sample file was not found on disk"
    try:
        y, _sr = _librosa.load(str(path), sr=TARGET_SAMPLE_RATE, mono=True, duration=5.0)
    except Exception as exc:
        return None, f"librosa failed to decode this file: {exc}"
    if y.size == 0:
        return None, "audio decoded to zero samples"
    if y.size < TARGET_WINDOW_SAMPLES:
        y = _np.pad(y, (0, TARGET_WINDOW_SAMPLES - y.size))
    else:
        y = y[:TARGET_WINDOW_SAMPLES]
    try:
        output = session.run(None, {"input": y.astype(_np.float32)[None, :]})[0]
    except Exception as exc:
        return None, f"embedding inference raised on this input: {exc}"
    vector = output[0]
    if vector.shape[-1] != EMBEDDING_DIM:
        return None, f"embedding model returned an unexpected shape {vector.shape}"
    return vector, None


def cosine_similarity(a: Any, b: Any) -> float:
    if _np is None:
        raise RuntimeError("numpy is required for cosine_similarity")
    denom = float(_np.linalg.norm(a)) * float(_np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(_np.dot(a, b) / denom)


def rank_by_similarity(
    target_path: Path,
    candidate_paths: list[tuple[str, Path]],
    *,
    limit: int = 10,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Rank a bounded candidate list by embedding similarity to one target file.

    ``candidate_paths`` is ``[(candidate_id, path), ...]`` -- capped at
    ``MAX_CANDIDATES`` (truncated, never silently sampled, mirroring
    ``scan_sample_library``'s own bound). Returns
    ``(ranked_results, None)`` or ``(None, abstain_reason)``. Each ranked
    result is real measured evidence (cosine similarity between two
    embeddings), never a filename-derived guess.
    """
    target_vector, reason = extract_embedding(target_path)
    if target_vector is None:
        return None, f"could not embed the target file: {reason}"

    bounded_candidates = candidate_paths[:MAX_CANDIDATES]
    scored: list[tuple[float, str]] = []
    for candidate_id, candidate_path in bounded_candidates:
        if candidate_path == target_path:
            continue
        vector, candidate_reason = extract_embedding(candidate_path)
        if vector is None:
            continue  # one candidate's failure doesn't abstain the whole ranked list
        scored.append((cosine_similarity(target_vector, vector), candidate_id))

    if not scored and bounded_candidates:
        return None, "none of the candidate files could be embedded"

    scored.sort(key=lambda item: -item[0])
    return [
        {"sample_id": sample_id, "similarity": round(score, 4)}
        for score, sample_id in scored[:limit]
    ], None


__all__ = [
    "EMBEDDING_DIM",
    "MAX_CANDIDATES",
    "TARGET_SAMPLE_RATE",
    "TARGET_WINDOW_SAMPLES",
    "cosine_similarity",
    "extract_embedding",
    "rank_by_similarity",
]

"""Stage J, use case #1 — project-feature extraction and training-row capture.

docs/AUDIO_MVP_MASTER_PLAN.md Stage J found the per-stem/per-track raw
signals mostly already exist (StemProfile, generate_mix_plan()'s inputs),
but no assembled "project features in -> chosen mix parameter out" vector
existed anywhere, and tempo (estimate_bpm()) was real but not wired into
generate_mix_plan()'s inputs at all. This module is that missing assembly
step: a fixed, named project-feature vector (matching the architectural
template studio/audiogen/audiogen/composition/song_rerank_model.py already
established: small, named, GLM-ready) plus a persistent, append-only table
capturing (features, chosen parameter) pairs from real AutoMix jobs as they
run, so a GLM has real data to train on once enough jobs accumulate.

This module only ever reads StemProfile/MixPlan data that already exists
and appends rows to its own table -- it never influences generate_mix_plan()
itself. Nothing here is wired into a live mix decision; see project_glm.py
and Stage J's own J4 guardrail note for why that stays true until a real
fitted model has been reviewed against held-out data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Callable

# Fixed, named feature vector -- keep this list append-only (new features go
# at the end) so historical rows stay interpretable against whichever
# feature_names list is saved alongside a trained model.
GENRE_KEYS = ("pop", "rock", "electronic", "hiphop", "acoustic", "edm")

PROJECT_FEATURE_NAMES = (
    "stem_count",
    "tempo_bpm",
    "tempo_confidence",
    "target_lufs",
    "mean_crest_factor_db",
    "mean_peak_dbfs",
    "mean_rms_dbfs",
    "mean_spectral_centroid_hz",
    "mean_transient_density",
    *(f"genre_{key}" for key in GENRE_KEYS),
)

PROJECT_TRAINING_ROWS_SQL = """
    CREATE TABLE IF NOT EXISTS automix_project_training_rows (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        created_at TEXT NOT NULL,
        genre TEXT DEFAULT '',
        target_name TEXT NOT NULL,
        target_value REAL,
        feature_json TEXT NOT NULL,
        UNIQUE(job_id, target_name)
    )
"""


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def estimate_project_tempo(prepared_stems: list[dict], sample_rate: int) -> tuple[float, float]:
    """Best-effort project tempo estimate: run onset detection + estimate_bpm()
    on whichever stem has the most detected onsets (typically the most
    rhythmically informative stem, e.g. kick/drums), and use that as a
    single project-level tempo. Returns (bpm, confidence); (0.0, 0.0) if no
    stem yields usable onsets.
    """
    try:
        from audio_analysis.analysis_core.transient_groove import detect_transient_onsets, estimate_bpm
    except ImportError:
        return 0.0, 0.0

    best_bpm, best_confidence, best_onset_count = 0.0, 0.0, 0
    for stem in prepared_stems:
        samples = stem.get("samples")
        # `samples` is a numpy array for real stems -- `not samples` raises
        # "truth value of an array with more than one element is
        # ambiguous" for any non-empty array, which silently killed this
        # whole function every time (caught by automix_worker.py's outer
        # try/except, logged as "Stage J project-feature capture failed").
        # Found live running a real AutoMix render 2026-08-05.
        if samples is None or len(samples) == 0:
            continue
        try:
            onsets = detect_transient_onsets(samples, sample_rate)
            if len(onsets) < 3:
                continue
            onset_times = [onset["time_seconds"] for onset in onsets]
            bpm, confidence = estimate_bpm(onset_times)
        except Exception:
            continue
        if bpm > 0.0 and len(onsets) > best_onset_count:
            best_bpm, best_confidence, best_onset_count = bpm, confidence, len(onsets)

    return best_bpm, best_confidence


def extract_project_features(
    stems_profiles: list,
    *,
    genre: str,
    target_lufs: float,
    tempo_bpm: float = 0.0,
    tempo_confidence: float = 0.0,
) -> dict[str, float]:
    """Assemble the fixed, named project-feature vector for one AutoMix job.

    ``stems_profiles`` is the same list of StemProfile objects
    generate_mix_plan() already receives. Never raises: any per-stem field
    that's missing just contributes 0.0 to the relevant mean, matching
    quality_predictor.py's own nan-safe convention.
    """
    crest = [p.crest_factor_db for p in stems_profiles if getattr(p, "crest_factor_db", None) is not None]
    peak = [p.peak_dbfs for p in stems_profiles if getattr(p, "peak_dbfs", None) is not None]
    rms = [p.rms_dbfs for p in stems_profiles if getattr(p, "rms_dbfs", None) is not None]
    centroid = [
        p.spectral_centroid_hz for p in stems_profiles
        if getattr(p, "spectral_centroid_hz", None) is not None
    ]
    transient = [
        p.transient_density for p in stems_profiles
        if getattr(p, "transient_density", None) is not None
    ]

    features = {
        "stem_count": float(len(stems_profiles)),
        "tempo_bpm": float(tempo_bpm),
        "tempo_confidence": float(tempo_confidence),
        "target_lufs": float(target_lufs),
        "mean_crest_factor_db": _mean(crest),
        "mean_peak_dbfs": _mean(peak),
        "mean_rms_dbfs": _mean(rms),
        "mean_spectral_centroid_hz": _mean(centroid),
        "mean_transient_density": _mean(transient),
    }
    normalized_genre = str(genre or "").strip().lower()
    for key in GENRE_KEYS:
        features[f"genre_{key}"] = 1.0 if normalized_genre == key else 0.0

    return {name: features.get(name, 0.0) for name in PROJECT_FEATURE_NAMES}


def extract_compressor_threshold_target(plan) -> float | None:
    """Stage J's first concrete regression target: the mean per-stem
    compressor threshold_db across every stem generate_mix_plan() actually
    gave a compressor to.

    Chosen (over e.g. the master limiter ceiling) because it's real,
    continuous, and driven by each stem's *measured* crest factor
    (mix_decision_engine.py's own pre-compression adjustment), not a pure
    genre-keyed table lookup -- a GLM predicting a pure lookup would just
    relearn the table, not demonstrate anything about project features
    actually mattering. Returns None if no stem in this job got a
    compressor (nothing to learn from for this job).
    """
    thresholds = [
        stem.compressor["threshold_db"]
        for stem in getattr(plan, "stems", [])
        if isinstance(getattr(stem, "compressor", None), dict) and "threshold_db" in stem.compressor
    ]
    return _mean(thresholds) if thresholds else None


def record_project_training_row(
    *,
    job_id: str,
    project_id: str,
    genre: str,
    features: dict[str, float],
    target_name: str,
    target_value: float | None,
    connect_func: Callable,
) -> None:
    """Append one (features, target) row for future GLM training.

    Best-effort and silent on failure -- this must never affect AutoMix job
    delivery. INSERT OR REPLACE on (job_id, target_name) so a job that's
    re-run (e.g. a revision) overwrites its own prior row rather than
    accumulating duplicates for the same job.
    """
    if target_value is None:
        return
    try:
        with connect_func() as conn:
            conn.execute(PROJECT_TRAINING_ROWS_SQL)
            conn.execute(
                """
                INSERT OR REPLACE INTO automix_project_training_rows (
                    job_id, project_id, created_at, genre, target_name, target_value, feature_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(job_id),
                    str(project_id),
                    datetime.now(UTC).isoformat(),
                    str(genre or "")[:40],
                    str(target_name)[:80],
                    float(target_value),
                    json.dumps(features, sort_keys=True),
                ),
            )
            conn.commit()
    except Exception:
        pass


def load_project_training_rows(
    *, connect_func: Callable, target_name: str, limit: int = 2000,
) -> list[dict]:
    """Load persisted (features, target) rows for one regression target."""
    try:
        with connect_func() as conn:
            conn.execute(PROJECT_TRAINING_ROWS_SQL)
            rows = conn.execute(
                "SELECT * FROM automix_project_training_rows WHERE target_name = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (str(target_name), max(1, min(5000, limit))),
            ).fetchall()
    except Exception:
        return []
    out = []
    for row in rows:
        item = dict(row)
        try:
            item["features"] = json.loads(item.pop("feature_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            item["features"] = {}
        out.append(item)
    return out

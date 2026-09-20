"""Learned whole-song reranker (Phase B): ridge model on audit feature columns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple

import numpy as np

from composition.audit_aligned_score import metrics_row_from_rerank_details, professional_quality_score

RERANK_FEATURE_NAMES: Tuple[str, ...] = (
    "in_key_primary_ratio",
    "lead_abs_interval_p95",
    "lead_repeat_frac",
    "lead_arp_overlap",
    "lead_activity",
    "chord_change_rate_per_bar",
    "mh_strongbeat_chord_tone_frac",
    "mh_phrase_end_chord_tone_frac",
    "lead_ceiling_hit_frac",
    "lead_top_band_frac",
    "lead_top_pitch_frac",
    "unique_section_roots",
    "hook_identity_score",
    "chorus_payoff_score",
    "motif_development_score",
    "counter_melody_events_per_bar",
    "emotion_match_score",
    "verse_lead_activity",
    "chorus_lead_activity",
    "register_lift_semitones",
)


def metrics_row_from_audit_csv(row: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize ``run_summary.csv`` row keys for feature extraction."""
    out: Dict[str, Any] = dict(row)
    if "counter_melody_events_per_bar" not in out and "counter_activity" in out:
        out["counter_melody_events_per_bar"] = out.get("counter_activity")
    return out


def feature_vector_from_row(row: Mapping[str, Any]) -> np.ndarray:
    xs: List[float] = []
    for name in RERANK_FEATURE_NAMES:
        try:
            xs.append(float(row.get(name, 0.0) or 0.0))
        except Exception:
            xs.append(0.0)
    return np.asarray(xs, dtype=np.float64)


def feature_vector_from_details(details: Mapping[str, Any]) -> np.ndarray:
    row = metrics_row_from_rerank_details(details)
    row["emotion_match_score"] = float(details.get("emotion_match_score", 0.0) or 0.0)
    row["verse_lead_activity"] = float(details.get("verse_lead_activity", 0.0) or 0.0)
    row["chorus_lead_activity"] = float(details.get("chorus_lead_activity", 0.0) or 0.0)
    row["register_lift_semitones"] = float(details.get("register_lift_semitones", 0.0) or 0.0)
    return feature_vector_from_row(row)


@dataclass
class SongRerankModel:
    """Ridge regression: features -> 0..100 audit composite target."""

    feature_names: Tuple[str, ...]
    weights: np.ndarray
    bias: float
    ridge_lambda: float = 1.0
    target: str = "professional_quality_score"
    version: int = 1

    def predict_row(self, row: Mapping[str, Any]) -> float:
        x = feature_vector_from_row(row)
        return self.predict_vector(x)

    def predict_vector(self, x: np.ndarray) -> float:
        w = np.asarray(self.weights, dtype=np.float64).reshape(-1)
        xv = np.asarray(x, dtype=np.float64).reshape(-1)
        if int(w.shape[0]) != int(xv.shape[0]):
            raise ValueError(f"feature dim mismatch: {w.shape[0]} vs {xv.shape[0]}")
        raw = float(np.dot(w, xv) + float(self.bias))
        return float(max(0.0, min(100.0, raw)))

    def predict_details(self, details: Mapping[str, Any]) -> float:
        return self.predict_vector(feature_vector_from_details(details))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": int(self.version),
            "target": str(self.target),
            "ridge_lambda": float(self.ridge_lambda),
            "feature_names": list(self.feature_names),
            "weights": [float(x) for x in np.asarray(self.weights).reshape(-1)],
            "bias": float(self.bias),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SongRerankModel":
        names = tuple(str(x) for x in list(payload.get("feature_names") or RERANK_FEATURE_NAMES))
        weights = np.asarray(list(payload.get("weights") or []), dtype=np.float64)
        if int(weights.shape[0]) != len(names):
            raise ValueError("weights length must match feature_names")
        return cls(
            feature_names=names,
            weights=weights,
            bias=float(payload.get("bias", 0.0) or 0.0),
            ridge_lambda=float(payload.get("ridge_lambda", 1.0) or 1.0),
            target=str(payload.get("target", "professional_quality_score")),
            version=int(payload.get("version", 1) or 1),
        )

    def save(self, path: str | Path) -> None:
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "SongRerankModel":
        payload = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
        return cls.from_dict(payload)


_MODEL_CACHE: Dict[str, SongRerankModel] = {}


def load_song_rerank_model(path: str | Path, *, cache: bool = True) -> SongRerankModel:
    key = str(Path(path).expanduser().resolve())
    if cache and key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    model = SongRerankModel.load(key)
    if cache:
        _MODEL_CACHE[key] = model
    return model


def fit_ridge_regressor(
    rows: Sequence[Mapping[str, Any]],
    *,
    target_key: str = "professional_quality_score",
    ridge_lambda: float = 2.0,
) -> SongRerankModel:
    """Fit weights to predict ``target_key`` (recompute target if missing)."""
    xs: List[np.ndarray] = []
    ys: List[float] = []
    for row in rows:
        metrics = metrics_row_from_audit_csv(row)
        try:
            y = float(row.get(target_key, 0.0) or 0.0)
        except Exception:
            y = 0.0
        if y <= 1e-6:
            y = float(professional_quality_score(metrics))
        xs.append(feature_vector_from_row({**metrics, **dict(row)}))
        ys.append(float(y))
    if len(xs) < 8:
        raise ValueError(f"need at least 8 training rows, got {len(xs)}")
    X = np.stack(xs, axis=0)
    y = np.asarray(ys, dtype=np.float64)
    n, f = X.shape
    lam = max(0.0, float(ridge_lambda))
    xt_x = X.T @ X + lam * np.eye(f, dtype=np.float64)
    xt_y = X.T @ y
    try:
        w = np.linalg.solve(xt_x, xt_y)
    except np.linalg.LinAlgError:
        w = np.linalg.pinv(xt_x) @ xt_y
    bias = float(np.mean(y - X @ w))
    return SongRerankModel(
        feature_names=RERANK_FEATURE_NAMES,
        weights=np.asarray(w, dtype=np.float64),
        bias=bias,
        ridge_lambda=lam,
        target=str(target_key),
    )


def evaluate_model(model: SongRerankModel, rows: Sequence[Mapping[str, Any]]) -> Dict[str, float]:
    preds: List[float] = []
    actual: List[float] = []
    for row in rows:
        metrics = metrics_row_from_audit_csv(row)
        try:
            y = float(row.get(model.target, 0.0) or 0.0)
        except Exception:
            y = 0.0
        if y <= 1e-6:
            y = float(professional_quality_score(metrics))
        actual.append(float(y))
        preds.append(float(model.predict_row({**metrics, **dict(row)})))
    if not actual:
        return {"n": 0.0, "mae": 0.0, "corr": 0.0}
    a = np.asarray(actual, dtype=np.float64)
    p = np.asarray(preds, dtype=np.float64)
    mae = float(np.mean(np.abs(a - p)))
    if float(np.std(a)) < 1e-9 or float(np.std(p)) < 1e-9:
        corr = 0.0
    else:
        corr = float(np.corrcoef(a, p)[0, 1])
    return {"n": float(len(actual)), "mae": mae, "corr": corr}


def learned_rerank_score_from_details(
    details: Mapping[str, Any],
    *,
    model_path: str = "",
) -> Tuple[float, Dict[str, Any]]:
    """Predict 0..100 score; fall back to heuristic audit composite if no model."""
    row = metrics_row_from_rerank_details(details)
    row["emotion_match_score"] = float(details.get("emotion_match_score", 0.0) or 0.0)
    row["verse_lead_activity"] = float(details.get("verse_lead_activity", 0.0) or 0.0)
    row["chorus_lead_activity"] = float(details.get("chorus_lead_activity", 0.0) or 0.0)
    row["register_lift_semitones"] = float(details.get("register_lift_semitones", 0.0) or 0.0)
    heuristic = float(professional_quality_score(row))
    meta: Dict[str, Any] = {
        "audit_aligned_quality_score": heuristic,
        "rerank_model_path": str(model_path or ""),
    }
    if not str(model_path or "").strip():
        meta["rerank_score_source"] = "heuristic"
        return heuristic, meta
    try:
        model = load_song_rerank_model(str(model_path))
        pred = float(model.predict_details(details))
        meta["rerank_score_source"] = "learned"
        meta["learned_rerank_score"] = pred
        return pred, meta
    except Exception as exc:
        meta["rerank_score_source"] = "heuristic_fallback"
        meta["rerank_model_error"] = str(exc)
        return heuristic, meta


def append_audio_rerank_row(
    song_render: Any,
    audio_metrics: dict,
    csv_path: str = "training_data/rerank_with_audio_features.csv",
) -> None:
    """Extract candidate metrics and audio features and write to CSV."""
    import csv
    from pathlib import Path

    path = Path(csv_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Extract the 20 standard features
    details = {}
    if song_render and hasattr(song_render, "metadata") and song_render.metadata and "candidate_metrics" in song_render.metadata:
        details = song_render.metadata["candidate_metrics"]

    # Use metrics_row_from_rerank_details to extract and normalize standard features
    row = metrics_row_from_rerank_details(details)
    row["emotion_match_score"] = float(details.get("emotion_match_score", 0.0) or 0.0)
    row["verse_lead_activity"] = float(details.get("verse_lead_activity", 0.0) or 0.0)
    row["chorus_lead_activity"] = float(details.get("chorus_lead_activity", 0.0) or 0.0)
    row["register_lift_semitones"] = float(details.get("register_lift_semitones", 0.0) or 0.0)

    # 2. Extract the 4 audio features
    row["spectral_balance_score"] = float(audio_metrics.get("technical_score", 0.0) or 0.0)
    row["crest_factor"] = float(audio_metrics.get("crest_factor_db", 0.0) or 0.0)
    row["stereo_width"] = float(audio_metrics.get("stereo_width_ratio", 0.0) or 0.0)
    
    # Normalize integrated LUFS if present (e.g. if LUFS is -99 or "n/a", default to -18.0)
    lufs = audio_metrics.get("integrated_lufs")
    if lufs in {None, "n/a", -99.0}:
        lufs_val = -18.0
    else:
        try:
            lufs_val = float(lufs)
        except Exception:
            lufs_val = -18.0
    row["perceived_loudness_distribution"] = lufs_val

    # Add target quality score
    row["target_quality_score"] = float(audio_metrics.get("technical_score", 0.0) or 0.0)

    fieldnames = list(RERANK_FEATURE_NAMES) + [
        "spectral_balance_score",
        "crest_factor",
        "stereo_width",
        "perceived_loudness_distribution",
        "target_quality_score"
    ]

    # Clean row to only include defined fieldnames
    final_row = {k: row.get(k, 0.0) for k in fieldnames}

    write_header = not path.exists() or path.stat().st_size == 0
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow(final_row)

"""Stage J, use case #1 — a small, interpretable GLM predicting a mix
parameter from project features.

Follows the same architectural template
studio/audiogen/audiogen/composition/song_rerank_model.py already
established in this codebase (a fixed named feature vector, closed-form
ridge-regularized fit, JSON-serializable coefficients, a held-out
evaluate()) rather than inventing a new model shape -- per Stage J2's own
reasoning: coefficient-level interpretability, small-data-friendly fitting,
and consistency with what's already shipped (quality_predictor.py and
song_rerank_model.py are both linear-family, not neural).

Ridge regression (L2-penalized least squares) rather than a true fitted
GLM with a distributional link function -- same honest caveat J1 already
applies to song_rerank_model.py's own reranker ("not a GLM today... but the
right architectural template"). A generalized-linear-model *family* fit
(e.g. statsmodels' GLM with a Gaussian/link function) would be a drop-in
upgrade to fit_project_glm() later without changing this module's external
shape, exactly the upgrade path J1 describes for quality_predictor.py.

Training readiness is checked explicitly (compute_project_training_readiness)
before any fit is attempted, matching quality_predictor.py's own
compute_training_readiness() discipline -- this module refuses to produce a
"trained" model from too little data rather than silently returning
meaningless coefficients.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from audio_analysis.integration.project_features import PROJECT_FEATURE_NAMES

MIN_TRAINING_ROWS = 15
MIN_HELDOUT_ROWS = 5


@dataclass
class ProjectGLM:
    """Ridge regression: project features -> a single mix-parameter target."""

    feature_names: tuple[str, ...]
    weights: np.ndarray
    bias: float
    target_name: str
    ridge_lambda: float = 2.0
    training_count: int = 0
    version: int = 1

    def predict(self, features: dict[str, float]) -> float:
        x = np.asarray([float(features.get(name, 0.0)) for name in self.feature_names], dtype=np.float64)
        return float(np.dot(self.weights, x) + self.bias)

    def coefficients(self) -> list[dict]:
        """Named, sorted-by-magnitude coefficients -- the point of choosing
        a GLM over a black box: every prediction is traceable to real,
        inspectable numbers, not a hidden weight matrix."""
        pairs = [
            {"feature": name, "weight": round(float(w), 5)}
            for name, w in zip(self.feature_names, self.weights)
        ]
        return sorted(pairs, key=lambda p: abs(p["weight"]), reverse=True)

    def to_dict(self) -> dict:
        return {
            "version": int(self.version),
            "target_name": str(self.target_name),
            "ridge_lambda": float(self.ridge_lambda),
            "feature_names": list(self.feature_names),
            "weights": [float(w) for w in np.asarray(self.weights).reshape(-1)],
            "bias": float(self.bias),
            "training_count": int(self.training_count),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "ProjectGLM":
        names = tuple(str(n) for n in payload.get("feature_names") or PROJECT_FEATURE_NAMES)
        weights = np.asarray(payload.get("weights") or [], dtype=np.float64)
        if weights.shape[0] != len(names):
            raise ValueError("weights length must match feature_names")
        return cls(
            feature_names=names,
            weights=weights,
            bias=float(payload.get("bias", 0.0) or 0.0),
            target_name=str(payload.get("target_name", "")),
            ridge_lambda=float(payload.get("ridge_lambda", 2.0) or 2.0),
            training_count=int(payload.get("training_count", 0) or 0),
            version=int(payload.get("version", 1) or 1),
        )

    def save(self, path: str | Path) -> None:
        out = Path(path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ProjectGLM":
        return cls.from_dict(json.loads(Path(path).expanduser().read_text(encoding="utf-8")))


def compute_project_training_readiness(rows: list[dict]) -> dict:
    """Assess whether enough real (features, target) rows exist to fit a
    meaningful model -- mirrors quality_predictor.py's
    compute_training_readiness() discipline exactly: report the honest
    count and recommendation rather than fitting on insufficient data.
    """
    usable = [r for r in rows if isinstance(r.get("features"), dict) and r.get("target_value") is not None]
    total = len(usable)
    ready = total >= MIN_TRAINING_ROWS + MIN_HELDOUT_ROWS
    if ready:
        recommended = "Training ready. Run fit_project_glm() on a held-out training split."
    else:
        needed = MIN_TRAINING_ROWS + MIN_HELDOUT_ROWS
        recommended = f"Need at least {needed} real AutoMix job rows for this target (have {total})."
    return {"ready": ready, "total": total, "recommended": recommended}


def fit_project_glm(
    rows: list[dict], *, target_name: str, ridge_lambda: float = 2.0,
) -> ProjectGLM:
    """Closed-form ridge fit: (X^T X + lambda*I)^-1 X^T y.

    ``rows`` are dicts with "features" (dict) and "target_value" (float),
    e.g. from project_features.load_project_training_rows(). Raises
    ValueError if fewer than MIN_TRAINING_ROWS usable rows are given --
    callers should check compute_project_training_readiness() first rather
    than relying on this exception as the readiness gate.
    """
    usable = [r for r in rows if isinstance(r.get("features"), dict) and r.get("target_value") is not None]
    if len(usable) < MIN_TRAINING_ROWS:
        raise ValueError(
            f"fit_project_glm requires at least {MIN_TRAINING_ROWS} usable rows, got {len(usable)}"
        )

    x = np.asarray(
        [[float(r["features"].get(name, 0.0)) for name in PROJECT_FEATURE_NAMES] for r in usable],
        dtype=np.float64,
    )
    y = np.asarray([float(r["target_value"]) for r in usable], dtype=np.float64)

    x_mean = x.mean(axis=0)
    x_centered = x - x_mean
    y_mean = float(y.mean())
    y_centered = y - y_mean

    n_features = x_centered.shape[1]
    gram = x_centered.T @ x_centered + ridge_lambda * np.eye(n_features)
    weights = np.linalg.solve(gram, x_centered.T @ y_centered)
    bias = y_mean - float(x_mean @ weights)

    return ProjectGLM(
        feature_names=PROJECT_FEATURE_NAMES,
        weights=weights,
        bias=bias,
        target_name=target_name,
        ridge_lambda=ridge_lambda,
        training_count=len(usable),
    )


def evaluate_project_glm(model: ProjectGLM, rows: list[dict]) -> dict:
    """Held-out MAE + Pearson correlation, matching
    song_rerank_model.py's evaluate_model() shape."""
    usable = [r for r in rows if isinstance(r.get("features"), dict) and r.get("target_value") is not None]
    if not usable:
        return {"n": 0, "mae": 0.0, "corr": 0.0}

    actual = np.asarray([float(r["target_value"]) for r in usable], dtype=np.float64)
    predicted = np.asarray([model.predict(r["features"]) for r in usable], dtype=np.float64)

    mae = float(np.mean(np.abs(predicted - actual)))
    if len(usable) >= 2 and actual.std() > 0 and predicted.std() > 0:
        corr = float(np.corrcoef(actual, predicted)[0, 1])
    else:
        corr = 0.0

    return {"n": len(usable), "mae": round(mae, 4), "corr": round(corr, 4)}

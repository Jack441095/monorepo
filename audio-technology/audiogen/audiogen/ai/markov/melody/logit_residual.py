# ai/markov/melody/logit_residual.py
# Phase 2d: optional linear logit residual on top of Markov interval priors (numpy-only).

from __future__ import annotations

import logging
import math
import hashlib
from functools import lru_cache
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Canonical interval classes for diatonic steps (-6..6) — matches typical Markov support.
INTERVAL_CLASS_MIN = -6
INTERVAL_CLASS_MAX = 6
NUM_INTERVAL_CLASSES = INTERVAL_CLASS_MAX - INTERVAL_CLASS_MIN + 1
LEGACY_FEATURE_EXTRA = 3
CONTEXT_FEATURE_EXTRA = 11


def interval_class_index(iv: int) -> Optional[int]:
    try:
        k = int(iv)
    except Exception:
        return None
    if k < INTERVAL_CLASS_MIN or k > INTERVAL_CLASS_MAX:
        return None
    return k - INTERVAL_CLASS_MIN


def _stable_unit_hash(text: str) -> float:
    raw = hashlib.blake2b(str(text or "").strip().lower().encode("utf-8"), digest_size=8).digest()
    return float(int.from_bytes(raw, "little", signed=False)) / float(2**64 - 1)


def _duration_bucket_value(duration: Optional[float]) -> float:
    if duration is None:
        return 0.0
    try:
        d = abs(float(duration))
    except Exception:
        return 0.0
    if d <= 0.25 + 1e-9:
        return 0.2
    if d <= 0.5 + 1e-9:
        return 0.4
    if d <= 1.0 + 1e-9:
        return 0.6
    if d <= 2.0 + 1e-9:
        return 0.8
    return 1.0


@lru_cache(maxsize=32)
def _load_residual_bundle(path: str) -> Optional[Tuple["object", ...]]:
    """Load (W, order, version) from compressed npz; W shape (NUM_INTERVAL_CLASSES, F)."""
    try:
        import numpy as np

        p = str(path or "").strip()
        if not p:
            return None
        data = np.load(p, allow_pickle=False)
        W = data["W"]
        order = 6
        if "order" in data.files:
            order = int(np.asarray(data["order"]).reshape(-1)[0])
        version = 1
        if "version" in data.files:
            version = int(np.asarray(data["version"]).reshape(-1)[0])
        W = np.asarray(W, dtype=np.float64)
        if W.ndim != 2 or int(W.shape[0]) != NUM_INTERVAL_CLASSES:
            logger.warning("melody logit residual: bad W shape %s", getattr(W, "shape", None))
            return None
        return (W, order, version)
    except Exception:
        logger.debug("melody logit residual: failed to load %s", path, exc_info=True)
        return None


def encode_interval_residual_features(
    interval_context_tail: List[int],
    phrase_pos: float,
    emotion_name: str,
    *,
    order: int = 6,
    section_role: str = "",
    phrase_role: str = "",
    contour: str = "",
    chord_symbol: str = "",
    prev_duration: Optional[float] = None,
    feature_dim: Optional[int] = None,
) -> "object":
    """Feature vector for one interval decision.

    Legacy files use length = order + 3. New training adds contextual hashes and
    duration/harmony features while `apply_*` remains backward-compatible with
    old weight matrices by requesting the legacy feature_dim.
    """
    import numpy as np

    ctx = list(interval_context_tail or [])
    while len(ctx) < int(order):
        ctx.insert(0, 0)
    ctx = [int(x) for x in ctx[-int(order) :]]
    vec = [float(x) / 7.0 for x in ctx]
    try:
        pp = float(phrase_pos)
    except Exception:
        pp = 0.0
    vec.append(max(0.0, min(1.0, pp)))
    name = (emotion_name or "").strip().lower()
    vec.append(_stable_unit_hash(name))

    target_dim = int(feature_dim) if feature_dim is not None else 0
    legacy_dim = int(order) + LEGACY_FEATURE_EXTRA
    if target_dim > 0 and target_dim <= legacy_dim:
        vec.append(1.0)
        return np.asarray(vec[:target_dim], dtype=np.float64)

    chord = str(chord_symbol or "").strip()
    try:
        from ai.markov.melody.harmony_symbol import simplify_harmony_function

        chord_quality = simplify_harmony_function(chord)
    except Exception:
        chord_quality = ""
    vec.extend(
        [
            _stable_unit_hash(section_role),
            _stable_unit_hash(phrase_role),
            _stable_unit_hash(contour),
            _stable_unit_hash(chord_quality),
            _stable_unit_hash(chord),
            _duration_bucket_value(prev_duration),
            1.0 if str(phrase_role or "").strip().lower() == "opening" else 0.0,
            1.0 if str(phrase_role or "").strip().lower() == "cadence" else 0.0,
            1.0 if str(section_role or "").strip().lower() in {"b", "chorus", "hook", "tag"} else 0.0,
            1.0 if "7" in chord or "dim" in chord.lower() or "aug" in chord.lower() else 0.0,
        ]
    )
    vec.append(1.0)
    if target_dim > 0:
        if len(vec) < target_dim:
            vec.extend([0.0] * (target_dim - len(vec)))
        vec = vec[:target_dim]
    return np.asarray(vec, dtype=np.float64)


def apply_interval_logit_residual(
    interval_probs: Dict[int, float],
    *,
    interval_context_tail: List[int],
    phrase_pos: float,
    emotion_name: str,
    strength: float,
    weight_path: str,
    order: int = 6,
    section_role: str = "",
    phrase_role: str = "",
    contour: str = "",
    chord_symbol: str = "",
    prev_duration: Optional[float] = None,
) -> Dict[int, float]:
    """Add linear logit residual in log-space, then renormalize over support keys."""
    if not interval_probs or strength <= 1e-12:
        return interval_probs
    bundle = _load_residual_bundle(str(weight_path or ""))
    if bundle is None:
        return interval_probs
    W, file_order, _ = bundle
    use_order = int(file_order) if int(file_order) > 0 else int(order)
    try:
        import numpy as np

        W = np.asarray(W, dtype=np.float64)
        x = encode_interval_residual_features(
            interval_context_tail,
            phrase_pos,
            emotion_name,
            order=use_order,
            section_role=section_role,
            phrase_role=phrase_role,
            contour=contour,
            chord_symbol=chord_symbol,
            prev_duration=prev_duration,
            feature_dim=int(W.shape[1]),
        )
        if int(W.shape[1]) != int(x.shape[0]):
            logger.warning(
                "melody logit residual: feature dim mismatch W=%s x=%s",
                W.shape,
                x.shape,
            )
            return interval_probs
        s = max(0.0, min(2.0, float(strength)))
        out: Dict[int, float] = {}
        for k, p in interval_probs.items():
            idx = interval_class_index(int(k))
            if idx is None:
                out[k] = float(p)
                continue
            logp = math.log(max(float(p), 1e-12))
            logp += s * float(W[idx] @ x)
            out[k] = math.exp(logp)
        tot = float(sum(out.values()))
        if tot <= 1e-18:
            return interval_probs
        return {k: float(v) / tot for k, v in out.items()}
    except Exception:
        logger.debug("apply_interval_logit_residual failed", exc_info=True)
        return interval_probs


def clear_residual_weight_cache() -> None:
    _load_residual_bundle.cache_clear()

# composition/retrained_markov_loader.py
"""Pickle load and validation for retrained Markov models (melody + chord).

Orchestration (config gating, hot-reload timing, binding into ``CompositionGenerator``) stays
in ``composition.engine``; this module holds the I/O and bundle-shape contract only.
"""
from __future__ import annotations
from audiogen_core.config import resolve_config

import logging
import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from audiogen_core.markov_serving_contract import (
    CHORD_MARKOV_BUNDLE_FORMAT_VERSION_MAX,
    CHORD_MARKOV_BUNDLE_KIND,
    CONFIG_CHORD_RETRAINED_HOT_RELOAD_ENABLED,
    CONFIG_CHORD_RETRAINED_HOT_RELOAD_INTERVAL_S,
    CONFIG_CHORD_RETRAINED_MARKOV_ENABLED,
    CONFIG_CHORD_RETRAINED_MARKOV_PATH,
    CONFIG_MELODY_RETRAINED_HOT_RELOAD_ENABLED,
    CONFIG_MELODY_RETRAINED_HOT_RELOAD_INTERVAL_S,
    CONFIG_MELODY_RETRAINED_MARKOV_ENABLED,
    CONFIG_MELODY_RETRAINED_MARKOV_PATH,
    MARKOV_BUNDLE_FORMAT_VERSION_KEY,
    MELODY_MARKOV_BUNDLE_FORMAT_VERSION_MAX,
    MELODY_MARKOV_BUNDLE_KIND,
)

logger = logging.getLogger(__name__)

__all__ = [
    "RetrainLoadConfig",
    "get_chord_retrain_config",
    "get_melody_retrain_config",
    "load_chord_retrained_pickle",
    "load_melody_retrained_pickle",
    "markov_chain_hyperparams_sane",
]


def _format_version_ok(
    raw: Any,
    *,
    max_version: int,
) -> bool:
    if raw is None:
        return True
    try:
        v = int(raw)
    except Exception:
        return False
    if v < 0 or v > int(max_version):
        return False
    return True


def _bundle_format_raw(bundle: Dict[str, Any]) -> Any:
    """Training scripts historically used ``version``; prefer ``bundle_format_version`` when present."""
    if MARKOV_BUNDLE_FORMAT_VERSION_KEY in bundle:
        return bundle.get(MARKOV_BUNDLE_FORMAT_VERSION_KEY)
    return bundle.get("version")


def markov_chain_hyperparams_sane(obj: object) -> bool:
    """
    Reject pathological or incompatible n-gram chains after unpickle.

    Uses attributes from ``BaseMarkov`` (`order`, `smoothing`, `backoff_decay`).
    """
    try:
        o = int(getattr(obj, "order", 0) or 0)
    except Exception:
        return False
    if not (1 <= o <= 32):
        return False
    try:
        s = float(getattr(obj, "smoothing", 0.0) or 0.0)
    except Exception:
        return False
    if not (1e-12 < s <= 2.0):
        return False
    try:
        b = float(getattr(obj, "backoff_decay", 0.0) or 0.0)
    except Exception:
        return False
    if not (0.0 <= b <= 1.0):
        return False
    if not (hasattr(obj, "get_probabilities") and hasattr(obj, "train") and hasattr(obj, "generate")):
        return False
    return True


def _validate_one_markov_model_set(mset: object) -> bool:
    for attr in ("interval", "rhythm", "phrase"):
        ch = getattr(mset, attr, None)
        if ch is None or not markov_chain_hyperparams_sane(ch):
            return False
    return True


def _validate_melody_bundled_sets(
    loaded: object,
    emotion_models: Dict[str, Any],
    family_models: Dict[str, Any],
) -> bool:
    if not _validate_one_markov_model_set(loaded):
        return False
    for m in list(emotion_models.values())[:64]:
        if m is not None and not _validate_one_markov_model_set(m):
            return False
    for m in list(family_models.values())[:64]:
        if m is not None and not _validate_one_markov_model_set(m):
            return False
    return True


@dataclass(frozen=True)
class RetrainLoadConfig:
    """Snapshot of ``CONFIG.composition`` retrain toggles and paths (see ``core.markov_serving_contract``)."""

    enabled: bool
    raw_path: str
    reload_on: bool
    reload_interval_s: float


def get_melody_retrain_config() -> RetrainLoadConfig:
    return RetrainLoadConfig(
        enabled=bool(resolve_config("composition", CONFIG_MELODY_RETRAINED_MARKOV_ENABLED, False, bool)),
        raw_path=str(resolve_config("composition", CONFIG_MELODY_RETRAINED_MARKOV_PATH, "", str)).strip(),
        reload_on=bool(resolve_config("composition", CONFIG_MELODY_RETRAINED_HOT_RELOAD_ENABLED, False, bool)),
        reload_interval_s=float(resolve_config("composition", CONFIG_MELODY_RETRAINED_HOT_RELOAD_INTERVAL_S, 2.0, float)),
    )
def get_chord_retrain_config() -> RetrainLoadConfig:
    return RetrainLoadConfig(
        enabled=bool(resolve_config("composition", CONFIG_CHORD_RETRAINED_MARKOV_ENABLED, False, bool)),
        raw_path=str(resolve_config("composition", CONFIG_CHORD_RETRAINED_MARKOV_PATH, "", str)).strip(),
        reload_on=bool(resolve_config("composition", CONFIG_CHORD_RETRAINED_HOT_RELOAD_ENABLED, False, bool)),
        reload_interval_s=float(resolve_config("composition", CONFIG_CHORD_RETRAINED_HOT_RELOAD_INTERVAL_S, 2.0, float)),
    )
# 2026-07-04 (docs/AUDIOGEN_COMPOSITION_PLAN.md efficiency work): the melody bundle is a
# ~196MB pickle whose unpickle (~6-7s, rebuilding ~21.5K nested-defaultdict BaseMarkov
# chains via __setstate__) was being paid TWICE per song and again for every new
# CompositionGenerator -- `generate_section` calls the hot-reload path per section and the
# ctor calls the cold path, and neither was cached. Profiled at ~13s of pure redundant
# reloading per retrained song, and 43,104 __setstate__ calls. The file is read-mostly
# (generation only populates each chain's `_prob_cache`), so caching the parsed bundle
# keyed by (resolved path, mtime_ns) and returning the SAME objects is safe and makes
# every load after the first an O(1) dict lookup. Hot-reload correctness is preserved: a
# changed file has a new mtime_ns, so it misses the cache and re-parses.
_MELODY_BUNDLE_CACHE: Dict[Tuple[str, int], Optional[Tuple[Any, Dict[str, Any], Dict[str, Any]]]] = {}
_MELODY_BUNDLE_CACHE_MAX = 3


def _bundle_cache_key(p: Path) -> Optional[Tuple[str, int]]:
    try:
        st = p.stat()
        mtime_ns = int(getattr(st, "st_mtime_ns", int(float(st.st_mtime) * 1e9)))
        return (str(p.resolve()), mtime_ns)
    except Exception:
        return None


def load_melody_retrained_pickle(
    p: Path,
    *,
    hot_reload: bool,
) -> Optional[Tuple[Any, Dict[str, Any], Dict[str, Any]]]:
    """
    Unpickle and validate a retrained melody Markov payload.

    Returns ``(global_model, emotion_models, family_models)`` or ``None`` on failure.
    Parsed bundles are cached by (path, mtime) so repeated loads of the same unchanged
    file are O(1) rather than re-unpickling ~196MB every call.
    """
    _cache_key = _bundle_cache_key(p)
    if _cache_key is not None and _cache_key in _MELODY_BUNDLE_CACHE:
        return _MELODY_BUNDLE_CACHE[_cache_key]
    try:
        with p.open("rb") as f:
            model = pickle.load(f)
    except Exception:
        if hot_reload:
            logger.debug("Failed to hot-reload retrained melody Markov pickle: %s", str(p), exc_info=True)
        else:
            logger.warning("Failed to load retrained melody Markov pickle: %s", str(p), exc_info=True)
        return None
    try:
        from ai.markov.melody.ensemble import MarkovModelSet

        loaded_model = None
        emotion_models: Dict[str, Any] = {}
        family_models: Dict[str, Any] = {}
        if isinstance(model, MarkovModelSet):
            loaded_model = model
        elif isinstance(model, dict) and str(model.get("kind") or "") == MELODY_MARKOV_BUNDLE_KIND:
            vkey = _bundle_format_raw(model)
            if not _format_version_ok(vkey, max_version=MELODY_MARKOV_BUNDLE_FORMAT_VERSION_MAX):
                if hot_reload:
                    logger.debug(
                        "Hot-reload skipped: melody markov bundle format not supported: %r %s",
                        vkey,
                        str(p),
                    )
                else:
                    logger.warning(
                        "Retrained melody Markov bundle has unsupported or invalid %s: %r (%s)",
                        MARKOV_BUNDLE_FORMAT_VERSION_KEY,
                        vkey,
                        str(p),
                    )
                return None
            maybe_global = model.get("global")
            if isinstance(maybe_global, MarkovModelSet):
                loaded_model = maybe_global
                raw_emotion = model.get("emotion_models") or {}
                raw_family = model.get("family_models") or {}
                if isinstance(raw_emotion, dict):
                    emotion_models = {str(k): v for k, v in raw_emotion.items() if isinstance(v, MarkovModelSet)}
                if isinstance(raw_family, dict):
                    family_models = {str(k): v for k, v in raw_family.items() if isinstance(v, MarkovModelSet)}
        if loaded_model is None:
            if hot_reload:
                logger.debug(
                    "Hot-reload skipped: retrained melody Markov pickle has unexpected type: %s",
                    type(model).__name__,
                )
            else:
                logger.warning(
                    "Retrained melody Markov pickle has unexpected type: %s (expected MarkovModelSet or bundle)",
                    type(model).__name__,
                )
            return None
    except Exception:
        if hot_reload:
            logger.debug("Could not validate hot-reloaded melody Markov type: %s", str(p), exc_info=True)
        else:
            logger.warning("Could not validate retrained melody Markov type: %s", str(p), exc_info=True)
        return None
    if isinstance(model, dict) and str(model.get("kind") or "") == MELODY_MARKOV_BUNDLE_KIND:
        if not _validate_melody_bundled_sets(loaded_model, emotion_models, family_models):
            if hot_reload:
                logger.debug("Hot-reload skipped: melody markov failed hyperparam validation: %s", str(p))
            else:
                logger.warning("Retrained melody Markov failed chain hyperparam validation: %s", str(p))
            return None
    elif not _validate_one_markov_model_set(loaded_model):
        if hot_reload:
            logger.debug("Hot-reload skipped: bare melody markov set failed validation: %s", str(p))
        else:
            logger.warning("Retrained bare melody Markov set failed chain hyperparam validation: %s", str(p))
        return None
    result = (loaded_model, emotion_models, family_models)
    # Cache the fully-validated parse (only successes; a failed/partial file is left
    # uncached so a later fixed version re-parses). Bound the cache so repeated
    # hot-reloads to genuinely new files can't grow it without limit.
    if _cache_key is not None:
        if len(_MELODY_BUNDLE_CACHE) >= _MELODY_BUNDLE_CACHE_MAX:
            _MELODY_BUNDLE_CACHE.clear()
        _MELODY_BUNDLE_CACHE[_cache_key] = result
    return result


def load_chord_retrained_pickle(
    p: Path,
    *,
    hot_reload: bool,
) -> Optional[Tuple[Any, Any, Any, Any]]:
    """
    Unpickle and validate a retrained chord Markov bundle.

    Returns ``(degree, bucket, global_degree, global_bucket)`` or ``None`` on failure.
    """
    try:
        with p.open("rb") as f:
            bundle = pickle.load(f)
    except Exception:
        if hot_reload:
            logger.debug("Failed to hot-reload retrained chord Markov pickle: %s", str(p), exc_info=True)
        else:
            logger.warning("Failed to load retrained chord Markov pickle: %s", str(p), exc_info=True)
        return None
    if not isinstance(bundle, dict) or str(bundle.get("kind") or "") != CHORD_MARKOV_BUNDLE_KIND:
        if hot_reload:
            logger.debug("Hot-reload skipped: chord Markov pickle has unexpected type/kind: %s", type(bundle).__name__)
        else:
            logger.warning(
                "Retrained chord Markov pickle has unexpected kind/type (expected %s).",
                CHORD_MARKOV_BUNDLE_KIND,
            )
        return None
    cver = _bundle_format_raw(bundle)
    if not _format_version_ok(cver, max_version=CHORD_MARKOV_BUNDLE_FORMAT_VERSION_MAX):
        if hot_reload:
            logger.debug(
                "Hot-reload skipped: chord markov bundle format not supported: %r %s",
                cver,
                str(p),
            )
        else:
            logger.warning(
                "Retrained chord Markov bundle has unsupported or invalid %s: %r (%s)",
                MARKOV_BUNDLE_FORMAT_VERSION_KEY,
                cver,
                str(p),
            )
        return None
    degree = bundle.get("degree")
    bucket = bundle.get("bucket")
    global_degree = bundle.get("global_degree")
    global_bucket = bundle.get("global_bucket")
    for obj in (degree, bucket, global_degree, global_bucket):
        if obj is None:
            continue
        if not hasattr(obj, "get_probabilities") or not hasattr(obj, "train"):
            logger.warning("Chord Markov bundle contains incompatible object: %s", type(obj).__name__)
            return None
        if not markov_chain_hyperparams_sane(obj):
            if hot_reload:
                logger.debug("Hot-reload skipped: chord markov chain failed hyperparam validation: %s", str(p))
            else:
                logger.warning("Chord Markov object failed chain hyperparam validation: %s", type(obj).__name__)
            return None
    return degree, bucket, global_degree, global_bucket
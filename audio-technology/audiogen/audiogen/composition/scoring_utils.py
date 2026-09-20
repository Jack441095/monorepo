from __future__ import annotations

from typing import Dict, Iterable, List, TypeVar

K = TypeVar("K")

# 2026-07-04 (docs/AUDIOGEN_COMPOSITION_PLAN.md real-time generation-speed work): profiled
# the retrained-melody-model path directly and found `sorted(..., key=repr)` here alone
# cost 13.9s of a ~125s profiled run (580K calls). `BaseMarkov._compute_probabilities`
# (ai/markov/core/base.py) always returns the *full* vocab as keys -- smoothing guarantees
# every vocab entry gets nonzero probability, and no rhythm/interval blend call site here
# passes `top_k` -- so `a` and `b` (both almost always `get_probabilities(...)` outputs)
# have the same key set across a huge number of calls: same two models' vocabs, unioned,
# over and over. Caching the repr-sorted key order per distinct key-set (not per call)
# turns a repeated O(n log n) sort + n `repr()` calls into a dict lookup on the hit path,
# with zero change to output (identical key order, identical math). Capped like this
# module's sibling caches (e.g. `voice_leading_engine.py::_guide_pcs_cache`) so a
# long-running real-time session can't grow it unboundedly.
_SORTED_KEYS_CACHE: Dict[frozenset, List] = {}
_SORTED_KEYS_CACHE_MAX = 512


def _sorted_keys_cached(key_union) -> List:
    fkey = frozenset(key_union)
    cached = _SORTED_KEYS_CACHE.get(fkey)
    if cached is not None:
        return cached
    keys = sorted(key_union, key=repr)
    if len(_SORTED_KEYS_CACHE) > _SORTED_KEYS_CACHE_MAX:
        _SORTED_KEYS_CACHE.clear()
    _SORTED_KEYS_CACHE[fkey] = keys
    return keys


def blend_probs(a: Dict[K, float], b: Dict[K, float], alpha: float) -> Dict[K, float]:
    """
    Blend two probability dicts and renormalize.
    alpha=0 => a, alpha=1 => b.
    """
    x = float(alpha)
    if x <= 1e-9:
        return dict(a)
    if x >= 1.0 - 1e-9:
        return dict(b)
    # Determinism: never iterate over a set for probability outputs, since callers
    # may convert dict keys to lists and sample by index order. Sort key must stay
    # `repr` exactly (not natural order) -- for float/tuple keys these produce
    # different orderings, and downstream samplers pick by list index, so changing
    # the order would silently change which note gets picked for a given random draw.
    keys: Iterable[K] = _sorted_keys_cached(a.keys() | b.keys())
    merged: Dict[K, float] = {}
    for k in keys:
        merged[k] = float(a.get(k, 0.0)) * (1.0 - x) + float(b.get(k, 0.0)) * x
    tot = float(sum(merged.values()))
    if tot > 0.0:
        return {k: float(v) / tot for k, v in merged.items()}
    return dict(a) if a else dict(b)


def circular_distance_mod7(a: int, b: int) -> int:
    d = abs(int(a) - int(b))
    return min(d, 7 - d)


def cadence_symbol_weight(*, target_degree: int, symbol: str) -> float:
    """
    Convert cadence degree intent into simplified-chord symbol preference.
    Degrees are diatonic: 0=tonic, 4=dominant, 2=mediant, 5=submediant (deceptive), 6=leading tone.
    """
    deg = int(target_degree) % 7
    sym = (symbol or "").lower()
    if deg == 0:
        return 1.35 if sym == "maj" else 0.92 if sym == "dom" else 0.9
    if deg == 4:
        return 1.45 if sym == "dom" else 0.88 if sym == "maj" else 0.92
    if deg == 5:
        return 1.25 if sym == "min" else 0.95 if sym == "maj" else 1.0
    if deg == 2:
        return 1.12 if sym in {"maj", "min"} else 0.95
    if deg == 6:
        return 1.18 if sym in {"dom", "dim"} else 0.92
    return 1.0


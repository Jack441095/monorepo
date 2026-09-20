from __future__ import annotations

import math
from typing import Dict, List, Tuple

from .scoring_utils import blend_probs


def entropy_bits(probs: Dict[str, float]) -> float:
    out = 0.0
    for _k, p in (probs or {}).items():
        try:
            pp = float(p)
        except Exception:
            continue
        if pp <= 0.0:
            continue
        out -= pp * math.log(pp, 2)
    return float(out)


def top_k(probs: Dict[str, float], k: int = 5) -> List[Tuple[str, float]]:
    items: List[Tuple[str, float]] = []
    for sym, p in (probs or {}).items():
        try:
            items.append((str(sym), float(p)))
        except Exception:
            continue
    items = [(s, p) for s, p in items if p > 0.0]
    items.sort(key=lambda kv: (-float(kv[1]), kv[0]))
    return list(items[: max(0, int(k))])


def blend_with_backoff(
    primary: Dict[str, float],
    fallback: Dict[str, float],
    *,
    alpha: float,
) -> Dict[str, float]:
    """
    Deterministically blend primary and fallback distributions.

    alpha:
      - 0.0 => primary
      - 1.0 => fallback
    """
    a = max(0.0, min(1.0, float(alpha)))
    if not fallback or a <= 1e-9:
        return dict(primary or {})
    if not primary or a >= 1.0 - 1e-9:
        return dict(fallback or {})
    return dict(blend_probs(dict(primary), dict(fallback), float(a)))


from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

from data.emotion_aliases import canonical_emotion_name

logger = logging.getLogger(__name__)


def _f(x: Any, default: float) -> float:
    try:
        return float(x)
    except Exception:
        return float(default)


def _clip(x: float, lo: float, hi: float) -> float:
    v = float(x)
    return float(lo if v < lo else hi if v > hi else v)


@lru_cache(maxsize=8)
def _load_profiles(path_text: str) -> Dict[str, Dict[str, float]]:
    path = Path(str(path_text)).expanduser()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
    except Exception:
        logger.exception("chorus-ref: failed to parse %s", str(path))
        return {}

    src = payload.get("suggested_arp_profiles") if isinstance(payload, dict) else None
    if not isinstance(src, dict):
        return {}

    out: Dict[str, Dict[str, float]] = {}
    for raw_name, raw_prof in src.items():
        if not isinstance(raw_prof, dict):
            continue
        key = canonical_emotion_name(str(raw_name or ""))
        if not key:
            continue
        prof: Dict[str, float] = {}
        if "target_notes_per_bar" in raw_prof:
            prof["target_notes_per_bar"] = _clip(_f(raw_prof.get("target_notes_per_bar"), 6.0), 4.0, 16.0)
        if "grid" in raw_prof:
            prof["grid"] = _clip(_f(raw_prof.get("grid"), 0.25), 0.125, 2.0)
        if "accent_strength" in raw_prof:
            prof["accent_strength"] = _clip(_f(raw_prof.get("accent_strength"), 0.12), 0.0, 0.35)
        if "octave_reach_prob" in raw_prof:
            prof["octave_reach_prob"] = _clip(_f(raw_prof.get("octave_reach_prob"), 0.12), 0.0, 0.45)
        if "syncopation_prob" in raw_prof:
            prof["syncopation_prob"] = _clip(_f(raw_prof.get("syncopation_prob"), 0.12), 0.0, 0.45)
        if prof:
            out[key] = prof
    return out


def chorus_reference_arp_for_emotion(*, emotion_name: str, profile_path: str) -> Dict[str, float]:
    key = canonical_emotion_name(str(emotion_name or ""))
    if not key:
        return {}
    return dict(_load_profiles(str(profile_path or "")).get(key, {}))


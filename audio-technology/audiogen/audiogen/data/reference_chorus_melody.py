from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Dict

from data.emotion_aliases import canonical_emotion_name

logger = logging.getLogger(__name__)


def _clip(x: float, lo: float, hi: float) -> float:
    v = float(x)
    return float(lo if v < lo else hi if v > hi else v)


def _fmap(src: object) -> Dict[str, float]:
    if not isinstance(src, dict):
        return {}
    out: Dict[str, float] = {}
    for k, v in src.items():
        try:
            out[canonical_emotion_name(str(k or ""))] = float(v)
        except Exception:
            continue
    return out


@lru_cache(maxsize=8)
def _load(path_text: str) -> Dict[str, Dict[str, float]]:
    path = Path(str(path_text)).expanduser()
    if not path.exists():
        return {"npb": {}, "motif": {}}
    try:
        payload = json.loads(path.read_text())
    except Exception:
        logger.exception("chorus-melody-ref: failed to parse %s", str(path))
        return {"npb": {}, "motif": {}}

    derived = payload.get("derived") if isinstance(payload, dict) else None
    if not isinstance(derived, dict):
        return {"npb": {}, "motif": {}}
    return {
        "npb": _fmap(derived.get("notes_per_bar_by_emotion")),
        "motif": _fmap(derived.get("motif_strength_by_emotion")),
    }


def chorus_reference_melody_for_emotion(*, emotion_name: str, profile_path: str) -> Dict[str, float]:
    key = canonical_emotion_name(str(emotion_name or ""))
    if not key:
        return {}
    maps = _load(str(profile_path or ""))
    npb_map = maps.get("npb") or {}
    motif_map = maps.get("motif") or {}
    if key not in npb_map and key not in motif_map:
        return {}

    out: Dict[str, float] = {}
    if key in npb_map:
        out["notes_per_bar"] = _clip(float(npb_map[key]), 2.0, 16.0)
    if key in motif_map:
        out["motif_strength"] = _clip(float(motif_map[key]), 0.0, 1.0)
    return out


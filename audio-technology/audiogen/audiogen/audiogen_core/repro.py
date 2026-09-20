from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Optional


def seed_everything(seed: Optional[int]) -> None:
    """
    Best-effort seeding for deterministic runs.

    This project uses Python's `random` in several modules and uses NumPy in the
    audio/rendering stack. When a seed is provided, seed both.
    """
    if seed is None:
        return
    try:
        import random

        random.seed(int(seed))
    except Exception:
        pass
    try:
        import numpy as np

        np.random.seed(int(seed))
    except Exception:
        pass


def _safe_asdict(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: _safe_asdict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _safe_asdict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_asdict(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    # Avoid unstable reprs (memory addresses) for determinism.
    try:
        return f"<{type(obj).__name__}>"
    except Exception:
        return "<object>"


def generation_metadata(*, seed: Optional[int] = None) -> Dict[str, Any]:
    """
    Best-effort snapshot of parameters that affect generation output.
    Kept JSON-serializable so it can be embedded into MIDI markers/logs.
    """
    meta: Dict[str, Any] = {"seed": int(seed) if seed is not None else None}
    try:
        from audiogen_core.config import CONFIG

        meta["active_sample_pack"] = getattr(CONFIG, "active_sample_pack", None)
        meta["active_style_profile"] = getattr(CONFIG, "active_style_profile", None)
        meta["active_conversation_preset"] = getattr(CONFIG, "active_conversation_preset", None)
        meta["composition"] = _safe_asdict(getattr(CONFIG, "composition", None))
        meta["ai"] = _safe_asdict(getattr(CONFIG, "ai", None))
        # Audio config doesn't affect MIDI note generation, but can affect playback perception.
        meta["audio"] = {"global_tempo": float(getattr(getattr(CONFIG, "audio", None), "global_tempo", 70.0))}
    except Exception:
        pass
    return meta


def generation_metadata_text(*, seed: Optional[int] = None, max_len: int = 1000) -> str:
    """Compact JSON for embedding into a MIDI text/lyric event."""
    try:
        s = json.dumps(generation_metadata(seed=seed), sort_keys=True)
    except Exception:
        s = json.dumps({"seed": int(seed) if seed is not None else None})
    if max_len and len(s) > int(max_len):
        return s[: max(0, int(max_len) - 3)] + "..."
    return s


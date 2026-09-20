from __future__ import annotations

from typing import Any, Dict, List, Tuple

from data.song_theme_profiles import song_theme_profile_for_emotion


ThemeCell = List[Tuple[float, float, int, int]]


def _safe_duration(value: float) -> float:
    try:
        v = float(value)
    except Exception:
        v = 0.5
    return float(max(0.18, min(1.75, v)))


def planned_song_theme_for_emotion(emotion_name: str) -> Dict[str, Any]:
    """Return a compact symbolic whole-song theme plan for an emotion."""

    return dict(song_theme_profile_for_emotion(str(emotion_name or "")))


def planned_theme_cell_for_emotion(
    emotion_name: str,
    *,
    source_velocity: int = 82,
    max_notes: int = 8,
) -> Tuple[ThemeCell, Dict[str, Any]]:
    """Convert the symbolic theme profile into the postprocess motif-cell shape."""

    profile = planned_song_theme_for_emotion(str(emotion_name or ""))
    intervals = [int(v) for v in list(profile.get("intervals", []) or [])]
    rhythms = [_safe_duration(float(v)) for v in list(profile.get("rhythms", []) or [])]
    count = min(max(0, int(max_notes)), len(intervals), len(rhythms))
    if count <= 0:
        return [], dict(profile)

    vel = int(max(48, min(108, int(source_velocity or 82))))
    rows: ThemeCell = []
    cursor = 0.0
    for i in range(count):
        dur = _safe_duration(float(rhythms[i]))
        rows.append((float(cursor), float(dur), int(intervals[i]), int(vel)))
        cursor += float(dur)

    meta = dict(profile)
    meta["theme_notes"] = int(len(rows))
    meta["span_beats"] = float(cursor)
    return rows, meta

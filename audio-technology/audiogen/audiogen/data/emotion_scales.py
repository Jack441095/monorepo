from __future__ import annotations

from typing import Any, Dict, List, Optional

from data.emotion_aliases import canonical_emotion_name


_DEFAULT_MELODY_SCALE_INTERVALS_BY_EMOTION: Dict[str, List[int]] = {
    "admiration": [0, 2, 4, 5, 7, 9, 11],
    "amusement": [0, 2, 4, 5, 7, 9, 10],
    "anger": [0, 1, 4, 5, 7, 8, 10],
    "annoyance": [0, 1, 3, 5, 7, 8, 10],
    "approval": [0, 2, 4, 5, 7, 9, 11],
    "caring": [0, 2, 4, 5, 7, 9, 11],
    "confusion": [0, 1, 3, 5, 6, 8, 10],
    "curiosity": [0, 2, 4, 6, 7, 9, 11],
    "desire": [0, 2, 3, 5, 7, 9, 10],
    "disappointment": [0, 2, 3, 5, 7, 8, 10],
    "disapproval": [0, 1, 3, 5, 7, 8, 10],
    "disgust": [0, 1, 3, 4, 6, 7, 10],
    "embarrassment": [0, 2, 3, 5, 7, 8, 10],
    "excitement": [0, 2, 4, 5, 7, 9, 10],
    "fear": [0, 1, 3, 4, 6, 7, 10],
    "gratitude": [0, 2, 4, 5, 7, 9, 11],
    "grief": [0, 2, 3, 5, 7, 8, 10],
    "joy": [0, 2, 4, 5, 7, 9, 11],
    "love": [0, 2, 4, 5, 7, 9, 11],
    "nervousness": [0, 1, 3, 4, 6, 7, 10],
    "neutral": [0, 2, 4, 5, 7, 9, 11],
    "optimism": [0, 2, 4, 5, 7, 9, 11],
    "pride": [0, 2, 4, 5, 7, 9, 11],
    "realization": [0, 2, 3, 5, 7, 9, 10],
    "relief": [0, 2, 4, 5, 7, 9, 11],
    "remorse": [0, 2, 3, 5, 7, 8, 10],
    "sadness": [0, 2, 3, 5, 7, 8, 10],
    "surprise": [0, 1, 2, 4, 5, 7, 10],
}


def melody_scale_intervals_for_emotion(emotion: Optional[object]) -> List[int]:
    if emotion is None:
        return [0, 2, 4, 5, 7, 9, 11]
    try:
        explicit = list(getattr(emotion, "melody_scale_intervals", None) or [])
    except Exception:
        explicit = []
    if explicit:
        out = []
        seen = set()
        for iv in explicit:
            pc = int(iv) % 12
            if pc in seen:
                continue
            seen.add(pc)
            out.append(pc)
            if len(out) >= 7:
                break
        if len(out) == 7:
            return out
    name = str(getattr(emotion, "name", "") or "").strip().lower()
    if name in _DEFAULT_MELODY_SCALE_INTERVALS_BY_EMOTION:
        return list(_DEFAULT_MELODY_SCALE_INTERVALS_BY_EMOTION[name])
    try:
        base = list(getattr(emotion, "scale_intervals", []) or [])
    except Exception:
        base = []
    out = []
    seen = set()
    for iv in base:
        pc = int(iv) % 12
        if pc in seen:
            continue
        seen.add(pc)
        out.append(pc)
        if len(out) >= 7:
            break
    fallback = [0, 2, 4, 5, 7, 9, 11]
    for iv in fallback:
        if len(out) >= 7:
            break
        if iv not in seen:
            seen.add(iv)
            out.append(iv)
    return out[:7]


def resolve_perceptual_scale_emotion(
    section_emotion: Any,
    *,
    primary_emotion_name: str = "",
) -> Any:
    """
    Return the EmotionProfile whose melody scale should define perceptual mode.

    When a song's primary adjective is set (e.g. sadness), section-level emotion
    arc colors (intro/outro neutral, etc.) must not re-map the lead/harmony to a
    brighter scale and collapse valence contrast between emotions.
    """
    primary = canonical_emotion_name(str(primary_emotion_name or ""))
    if primary:
        try:
            from data.music_data import EMOTION_BY_NAME

            em = EMOTION_BY_NAME.get(primary)
            if em is not None:
                return em
        except Exception:
            pass
    return section_emotion


def emotion_scale_pitch_classes(*, emotion_or_name: Any, root_note: int = 60) -> List[int]:
    """Pitch classes for an emotion's melody scale relative to ``root_note``."""
    try:
        from data.music_data import EMOTION_BY_NAME

        if hasattr(emotion_or_name, "name"):
            emo = emotion_or_name
        else:
            key = canonical_emotion_name(str(emotion_or_name or ""))
            emo = EMOTION_BY_NAME.get(key) if key else None
        intervals = list(melody_scale_intervals_for_emotion(emo) or [])
        root_pc = int(root_note) % 12
        return sorted({int((root_pc + int(iv)) % 12) for iv in intervals})
    except Exception:
        return []

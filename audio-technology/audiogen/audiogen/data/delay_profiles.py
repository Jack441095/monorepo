from __future__ import annotations

from typing import Dict
GLOBAL_DELAY_FEEDBACK_SCALE = 1.0


def delay_feedback_scale_for_emotion(emotion_name: str) -> float:
    del emotion_name
    # Global sonic identity: do not vary delay feedback by emotion.
    return float(GLOBAL_DELAY_FEEDBACK_SCALE)


def delay_feedbacks_for_emotion(
    emotion_name: str,
    *,
    melody_base: float,
    arp_base: float,
    counter_base: float | None = None,
) -> Dict[int, float]:
    scale = delay_feedback_scale_for_emotion(emotion_name)
    counter = float(counter_base if counter_base is not None else melody_base)
    return {
        2: max(0.08, min(0.6, float(melody_base) * scale)),
        3: max(0.06, min(0.5, float(arp_base) * scale)),
        5: max(0.06, min(0.5, float(counter) * scale)),
    }

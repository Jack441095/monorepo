from __future__ import annotations

from typing import Dict, List


EMOTION_MELODY_MOTIF_PROFILES: Dict[str, Dict[str, object]] = {
    "admiration": {"preferred_contours": ["arch", "asc"], "density_target": 0.42, "avg_interval_target": 1.3, "variations": ["augment", "sequence", "transpose"]},
    "amusement": {"preferred_contours": ["asc", "arch"], "density_target": 0.72, "avg_interval_target": 1.7, "variations": ["sequence", "fragment", "retrograde"]},
    "anger": {"preferred_contours": ["asc", "arch"], "density_target": 0.82, "avg_interval_target": 2.1, "variations": ["sequence", "diminish", "fragment"]},
    "annoyance": {"preferred_contours": ["static", "desc"], "density_target": 0.6, "avg_interval_target": 1.4, "variations": ["fragment", "retrograde", "transpose"]},
    "approval": {"preferred_contours": ["asc", "arch"], "density_target": 0.68, "avg_interval_target": 1.6, "variations": ["sequence", "transpose", "augment"]},
    "caring": {"preferred_contours": ["arch", "static"], "density_target": 0.3, "avg_interval_target": 1.1, "variations": ["augment", "transpose", "fragment"]},
    "confusion": {"preferred_contours": ["arch", "static"], "density_target": 0.52, "avg_interval_target": 1.7, "variations": ["fragment", "retrograde", "invert"]},
    "curiosity": {"preferred_contours": ["asc", "arch"], "density_target": 0.7, "avg_interval_target": 1.8, "variations": ["sequence", "transpose", "fragment"]},
    "desire": {"preferred_contours": ["arch", "asc"], "density_target": 0.58, "avg_interval_target": 1.6, "variations": ["sequence", "augment", "transpose"]},
    "disappointment": {"preferred_contours": ["desc", "static"], "density_target": 0.38, "avg_interval_target": 1.2, "variations": ["retrograde", "fragment", "augment"]},
    "disapproval": {"preferred_contours": ["desc", "arch"], "density_target": 0.55, "avg_interval_target": 1.8, "variations": ["fragment", "retrograde", "transpose"]},
    "disgust": {"preferred_contours": ["arch", "desc"], "density_target": 0.62, "avg_interval_target": 2.0, "variations": ["invert", "fragment", "retrograde"]},
    "embarrassment": {"preferred_contours": ["desc", "static"], "density_target": 0.32, "avg_interval_target": 1.3, "variations": ["fragment", "retrograde", "augment"]},
    "excitement": {"preferred_contours": ["asc", "arch"], "density_target": 0.82, "avg_interval_target": 2.3, "variations": ["sequence", "diminish", "transpose"]},
    "fear": {"preferred_contours": ["arch", "desc"], "density_target": 0.68, "avg_interval_target": 1.9, "variations": ["fragment", "retrograde", "invert"]},
    "gratitude": {"preferred_contours": ["arch", "asc"], "density_target": 0.45, "avg_interval_target": 1.4, "variations": ["augment", "sequence", "transpose"]},
    "grief": {"preferred_contours": ["desc", "static"], "density_target": 0.22, "avg_interval_target": 1.0, "variations": ["augment", "retrograde", "fragment"]},
    "joy": {"preferred_contours": ["asc", "arch"], "density_target": 0.78, "avg_interval_target": 2.0, "variations": ["sequence", "diminish", "transpose"]},
    "love": {"preferred_contours": ["arch", "static"], "density_target": 0.34, "avg_interval_target": 1.2, "variations": ["augment", "transpose", "fragment"]},
    "nervousness": {"preferred_contours": ["arch", "asc"], "density_target": 0.82, "avg_interval_target": 1.9, "variations": ["fragment", "sequence", "invert"]},
    "neutral": {"preferred_contours": ["static", "arch"], "density_target": 0.5, "avg_interval_target": 1.4, "variations": ["transpose", "fragment", "augment"]},
    "optimism": {"preferred_contours": ["asc", "arch"], "density_target": 0.74, "avg_interval_target": 1.9, "variations": ["sequence", "transpose", "diminish"]},
    "pride": {"preferred_contours": ["asc", "static"], "density_target": 0.56, "avg_interval_target": 2.2, "variations": ["transpose", "sequence", "augment"]},
    "realization": {"preferred_contours": ["arch", "static"], "density_target": 0.42, "avg_interval_target": 1.5, "variations": ["fragment", "transpose", "retrograde"]},
    "relief": {"preferred_contours": ["desc", "static"], "density_target": 0.26, "avg_interval_target": 1.1, "variations": ["augment", "fragment", "transpose"]},
    "remorse": {"preferred_contours": ["desc", "static"], "density_target": 0.24, "avg_interval_target": 1.0, "variations": ["retrograde", "augment", "fragment"]},
    "sadness": {"preferred_contours": ["desc", "static"], "density_target": 0.3, "avg_interval_target": 1.1, "variations": ["augment", "fragment", "retrograde"]},
    "surprise": {"preferred_contours": ["arch", "asc"], "density_target": 0.76, "avg_interval_target": 2.1, "variations": ["retrograde", "sequence", "diminish"]},
}


def melody_motif_profile_for_emotion(emotion_name: str) -> Dict[str, object]:
    return dict(EMOTION_MELODY_MOTIF_PROFILES.get((emotion_name or "").strip().lower(), {}))


def preferred_motif_variations(emotion_name: str, default: List[str]) -> List[str]:
    profile = melody_motif_profile_for_emotion(emotion_name)
    variations = profile.get("variations")
    if isinstance(variations, list) and variations:
        return [str(v) for v in variations]
    return list(default)

from __future__ import annotations

from typing import Dict, List, Optional


def _profile(
    *,
    contour_template: List[str],
    target_shift: float,
    release_mult: float,
    peak_pos: float,
    peak_weight: float,
    phrase_role_template: Optional[List[str]] = None,
    section_contour_templates: Optional[Dict[str, List[str]]] = None,
    nonfinal_cadence_by_role: Optional[Dict[str, int]] = None,
    final_cadence_default: Optional[int] = None,
    final_cadence_by_section: Optional[Dict[str, int]] = None,
    role_register_shift: Optional[Dict[str, int]] = None,
    second_half_register_lift: int = 1,
    hook_anchor_pool: Optional[List[int]] = None,
    chord_tone_push_by_role: Optional[Dict[str, float]] = None,
    leap_bias: Optional[float] = None,
) -> Dict[str, object]:
    out: Dict[str, object] = {
        "contour_template": list(contour_template),
        "target_shift": float(target_shift),
        "release_mult": float(release_mult),
        "peak_pos": float(peak_pos),
        "peak_weight": float(peak_weight),
        "phrase_role_template": list(
            phrase_role_template or ["opening", "answer", "continuation", "cadence"]
        ),
        "section_contour_templates": dict(section_contour_templates or {}),
        "nonfinal_cadence_by_role": dict(
            nonfinal_cadence_by_role
            or {"opening": 4, "answer": 4, "continuation": 4, "cadence": 4}
        ),
        "final_cadence_default": int(final_cadence_default if final_cadence_default is not None else 0),
        "final_cadence_by_section": dict(final_cadence_by_section or {}),
        "role_register_shift": dict(
            role_register_shift
            or {"opening": -2, "answer": 2, "continuation": 0, "cadence": 1}
        ),
        "second_half_register_lift": int(second_half_register_lift),
        "hook_anchor_pool": list(hook_anchor_pool or [0, 2, 4]),
        "chord_tone_push_by_role": dict(
            chord_tone_push_by_role
            or {"opening": 1.06, "answer": 1.02, "continuation": 1.0, "cadence": 1.12}
        ),
    }
    if leap_bias is not None:
        out["leap_bias"] = float(leap_bias)
    return out


EMOTION_MELODY_PHRASE_PROFILES: Dict[str, Dict[str, object]] = {
    "admiration": _profile(
        contour_template=["arch", "static", "arch", "asc"],
        section_contour_templates={"b": ["arch", "desc", "arch", "asc"]},
        target_shift=0.2,
        release_mult=1.02,
        peak_pos=0.58,
        peak_weight=0.98,
        final_cadence_by_section={"intro": 4, "a": 0, "pre_chorus": 4, "b": 0},
        role_register_shift={"opening": -1, "answer": 1, "continuation": 0, "cadence": 1},
    ),
    "amusement": _profile(
        contour_template=["asc", "arch", "desc", "asc"],
        section_contour_templates={"b": ["asc", "arch", "asc", "arch"]},
        target_shift=0.8,
        release_mult=0.94,
        peak_pos=0.76,
        peak_weight=1.2,
        final_cadence_default=0,
        second_half_register_lift=2,
    ),
    "anger": _profile(
        contour_template=["asc", "asc", "desc", "asc"],
        section_contour_templates={"b": ["asc", "asc", "arch", "asc"]},
        target_shift=1.0,
        release_mult=0.9,
        peak_pos=0.8,
        peak_weight=1.24,
        nonfinal_cadence_by_role={"opening": 4, "answer": 6, "continuation": 4, "cadence": 4},
        final_cadence_default=0,
        final_cadence_by_section={"intro": 4, "a": 4, "pre_chorus": 4, "b": 0},
        role_register_shift={"opening": -1, "answer": 2, "continuation": 1, "cadence": 2},
        second_half_register_lift=2,
        hook_anchor_pool=[0, 4],
    ),
    "annoyance": _profile(
        contour_template=["static", "asc", "static", "desc"],
        target_shift=0.4,
        release_mult=0.92,
        peak_pos=0.7,
        peak_weight=1.1,
        nonfinal_cadence_by_role={"opening": 6, "answer": 4, "continuation": 6, "cadence": 4},
        final_cadence_default=6,
    ),
    "approval": _profile(
        contour_template=["asc", "arch", "static", "asc"],
        target_shift=0.4,
        release_mult=1.0,
        peak_pos=0.64,
        peak_weight=1.02,
        final_cadence_default=0,
    ),
    "caring": _profile(
        contour_template=["arch", "static", "desc", "static"],
        section_contour_templates={"b": ["arch", "static", "arch", "static"]},
        target_shift=-0.5,
        release_mult=1.12,
        peak_pos=0.46,
        peak_weight=0.92,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        nonfinal_cadence_by_role={"opening": 4, "answer": 4, "continuation": 4, "cadence": 4},
        final_cadence_default=0,
        role_register_shift={"opening": -2, "answer": 0, "continuation": -1, "cadence": 0},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.18, "answer": 1.16, "continuation": 1.14, "cadence": 1.30},
    ),
    "confusion": _profile(
        contour_template=["arch", "desc", "asc", "static"],
        target_shift=0.1,
        release_mult=0.94,
        peak_pos=0.6,
        peak_weight=1.04,
        leap_bias=1.10,
        nonfinal_cadence_by_role={"opening": 6, "answer": 4, "continuation": 6, "cadence": 4},
        final_cadence_default=6,
    ),
    "curiosity": _profile(
        contour_template=["asc", "arch", "asc", "arch"],
        target_shift=0.5,
        release_mult=0.96,
        peak_pos=0.72,
        peak_weight=1.14,
        nonfinal_cadence_by_role={"opening": 4, "answer": 6, "continuation": 4, "cadence": 4},
        final_cadence_default=5,
        second_half_register_lift=2,
    ),
    "desire": _profile(
        contour_template=["asc", "arch", "arch", "desc"],
        section_contour_templates={"b": ["arch", "arch", "desc", "static"]},
        target_shift=0.3,
        release_mult=1.02,
        peak_pos=0.66,
        peak_weight=1.08,
        phrase_role_template=["opening", "continuation", "answer", "cadence"],
        final_cadence_default=0,
        role_register_shift={"opening": -1, "answer": 1, "continuation": 0, "cadence": 0},
    ),
    "disappointment": _profile(
        contour_template=["desc", "arch", "desc", "static"],
        section_contour_templates={"b": ["arch", "desc", "arch", "static"]},
        target_shift=-0.8,
        release_mult=1.18,
        peak_pos=0.40,
        peak_weight=0.88,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        final_cadence_default=2,
        final_cadence_by_section={"b": 0},
        role_register_shift={"opening": -2, "answer": 0, "continuation": -1, "cadence": 0},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.10, "answer": 1.06, "continuation": 1.06, "cadence": 1.20},
    ),
    "disapproval": _profile(
        contour_template=["desc", "asc", "static", "desc"],
        target_shift=-0.3,
        release_mult=1.08,
        peak_pos=0.54,
        peak_weight=0.9,
        final_cadence_default=4,
        hook_anchor_pool=[0, 4],
    ),
    "disgust": _profile(
        contour_template=["desc", "arch", "asc", "desc"],
        target_shift=-0.2,
        release_mult=0.94,
        peak_pos=0.56,
        peak_weight=1.06,
        nonfinal_cadence_by_role={"opening": 6, "answer": 4, "continuation": 6, "cadence": 4},
        final_cadence_default=6,
    ),
    "embarrassment": _profile(
        contour_template=["desc", "static", "desc", "static"],
        section_contour_templates={"b": ["arch", "static", "desc", "static"]},
        target_shift=-0.4,
        release_mult=1.12,
        peak_pos=0.48,
        peak_weight=0.92,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        nonfinal_cadence_by_role={"opening": 4, "answer": 2, "continuation": 4, "cadence": 2},
        final_cadence_default=2,
        final_cadence_by_section={"b": 2},
        role_register_shift={"opening": -2, "answer": 0, "continuation": -1, "cadence": -1},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.18, "answer": 1.14, "continuation": 1.14, "cadence": 1.28},
    ),
    "excitement": _profile(
        contour_template=["asc", "asc", "asc", "arch"],
        section_contour_templates={"b": ["asc", "arch", "asc", "asc"]},
        target_shift=1.2,
        release_mult=0.9,
        peak_pos=0.78,
        peak_weight=1.26,
        final_cadence_default=0,
        role_register_shift={"opening": 0, "answer": 2, "continuation": 1, "cadence": 2},
        second_half_register_lift=2,
    ),
    "fear": _profile(
        contour_template=["arch", "desc", "asc", "desc"],
        target_shift=0.2,
        release_mult=0.78,
        peak_pos=0.78,
        peak_weight=1.24,
        leap_bias=1.22,
        nonfinal_cadence_by_role={"opening": 6, "answer": 4, "continuation": 6, "cadence": 4},
        final_cadence_default=6,
        final_cadence_by_section={"b": 6, "pre_chorus": 6},
        second_half_register_lift=2,
    ),
    "gratitude": _profile(
        contour_template=["arch", "static", "arch", "static"],
        section_contour_templates={"b": ["arch", "arch", "desc", "static"]},
        target_shift=0.3,
        release_mult=1.02,
        peak_pos=0.6,
        peak_weight=1.0,
        final_cadence_default=0,
        role_register_shift={"opening": -1, "answer": 1, "continuation": 0, "cadence": 0},
    ),
    "grief": _profile(
        contour_template=["desc", "arch", "static", "desc"],
        target_shift=-1.2,
        release_mult=1.2,
        peak_pos=0.36,
        peak_weight=0.82,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        final_cadence_default=2,
        final_cadence_by_section={"b": 0},
        role_register_shift={"opening": -3, "answer": -1, "continuation": -2, "cadence": -1},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.12, "answer": 1.08, "continuation": 1.06, "cadence": 1.22},
    ),
    "joy": _profile(
        contour_template=["asc", "asc", "arch", "asc"],
        section_contour_templates={"b": ["asc", "arch", "asc", "asc"]},
        target_shift=0.9,
        release_mult=0.94,
        peak_pos=0.74,
        peak_weight=1.2,
        final_cadence_default=0,
        second_half_register_lift=2,
    ),
    "love": _profile(
        contour_template=["arch", "desc", "arch", "desc"],
        section_contour_templates={"b": ["arch", "desc", "arch", "asc"]},
        target_shift=-0.4,
        release_mult=1.14,
        peak_pos=0.44,
        peak_weight=0.94,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        final_cadence_default=0,
        role_register_shift={"opening": -2, "answer": 0, "continuation": -1, "cadence": 0},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.14, "answer": 1.12, "continuation": 1.08, "cadence": 1.22},
    ),
    "nervousness": _profile(
        contour_template=["arch", "asc", "desc", "desc"],
        target_shift=0.3,
        release_mult=0.84,
        peak_pos=0.74,
        peak_weight=1.16,
        nonfinal_cadence_by_role={"opening": 6, "answer": 4, "continuation": 6, "cadence": 4},
        final_cadence_default=6,
        final_cadence_by_section={"b": 6, "pre_chorus": 6},
        second_half_register_lift=2,
    ),
    "neutral": _profile(
        contour_template=["static", "arch", "desc", "arch"],
        target_shift=0.0,
        release_mult=1.0,
        peak_pos=0.6,
        peak_weight=1.0,
        final_cadence_default=0,
    ),
    "optimism": _profile(
        contour_template=["asc", "arch", "asc", "static"],
        section_contour_templates={"b": ["asc", "arch", "asc", "asc"]},
        target_shift=0.8,
        release_mult=0.96,
        peak_pos=0.76,
        peak_weight=1.18,
        final_cadence_default=0,
        second_half_register_lift=2,
    ),
    "pride": _profile(
        contour_template=["asc", "arch", "static", "asc"],
        section_contour_templates={"b": ["arch", "asc", "arch", "asc"]},
        target_shift=0.6,
        release_mult=0.98,
        peak_pos=0.66,
        peak_weight=1.08,
        leap_bias=1.18,
        final_cadence_default=0,
        role_register_shift={"opening": -1, "answer": 2, "continuation": 1, "cadence": 2},
        second_half_register_lift=2,
    ),
    "realization": _profile(
        contour_template=["static", "asc", "desc", "static"],
        target_shift=0.2,
        release_mult=1.0,
        peak_pos=0.58,
        peak_weight=0.96,
        final_cadence_default=5,
        final_cadence_by_section={"b": 0},
    ),
    "relief": _profile(
        contour_template=["desc", "arch", "desc", "static"],
        target_shift=-0.8,
        release_mult=1.28,
        peak_pos=0.40,
        peak_weight=0.84,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        final_cadence_default=0,
        role_register_shift={"opening": -2, "answer": 0, "continuation": -1, "cadence": 0},
        second_half_register_lift=0,
    ),
    "remorse": _profile(
        contour_template=["desc", "desc", "arch", "static"],
        section_contour_templates={"b": ["desc", "arch", "desc", "static"]},
        target_shift=-1.0,
        release_mult=1.18,
        peak_pos=0.38,
        peak_weight=0.86,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        final_cadence_default=2,
        final_cadence_by_section={"b": 0},
        role_register_shift={"opening": -3, "answer": -1, "continuation": -2, "cadence": -1},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.16, "answer": 1.12, "continuation": 1.10, "cadence": 1.24},
    ),
    "sadness": _profile(
        contour_template=["desc", "arch", "desc", "static"],
        section_contour_templates={"b": ["arch", "desc", "arch", "static"]},
        target_shift=-0.9,
        release_mult=1.16,
        peak_pos=0.38,
        peak_weight=0.88,
        phrase_role_template=["opening", "answer", "continuation", "cadence"],
        final_cadence_default=2,
        final_cadence_by_section={"b": 0},
        role_register_shift={"opening": -3, "answer": -1, "continuation": -2, "cadence": -1},
        second_half_register_lift=0,
        chord_tone_push_by_role={"opening": 1.12, "answer": 1.08, "continuation": 1.06, "cadence": 1.22},
    ),
    "surprise": _profile(
        contour_template=["asc", "arch", "desc", "asc"],
        target_shift=0.8,
        release_mult=0.92,
        peak_pos=0.72,
        peak_weight=1.18,
        leap_bias=1.12,
        final_cadence_default=5,
        second_half_register_lift=2,
    ),
    "calm": _profile(
        contour_template=["static", "static", "static", "desc"],
        target_shift=-0.6,
        release_mult=1.18,
        peak_pos=0.46,
        peak_weight=0.8,
        phrase_role_template=["opening", "continuation", "answer", "cadence"],
        final_cadence_default=0,
        role_register_shift={"opening": -3, "answer": -1, "continuation": -2, "cadence": -1},
        second_half_register_lift=0,
    ),
    "peaceful": _profile(
        contour_template=["static", "static", "desc", "static"],
        target_shift=-0.7,
        release_mult=1.2,
        peak_pos=0.44,
        peak_weight=0.78,
        phrase_role_template=["opening", "continuation", "answer", "cadence"],
        final_cadence_default=0,
        role_register_shift={"opening": -3, "answer": -1, "continuation": -2, "cadence": -1},
        second_half_register_lift=0,
    ),
    "serenity": _profile(
        contour_template=["static", "static", "desc", "static"],
        target_shift=-0.7,
        release_mult=1.22,
        peak_pos=0.42,
        peak_weight=0.76,
        phrase_role_template=["opening", "continuation", "answer", "cadence"],
        final_cadence_default=0,
        role_register_shift={"opening": -3, "answer": -1, "continuation": -2, "cadence": -1},
        second_half_register_lift=0,
    ),
}


def melody_phrase_profile_for_emotion(emotion_name: str) -> Dict[str, object]:
    return dict(EMOTION_MELODY_PHRASE_PROFILES.get((emotion_name or "").strip().lower(), {}))


def melody_phrase_contour_sequence_for_emotion(
    emotion_name: str,
    phrases_per_section: int,
    *,
    section_role: Optional[str] = None,
) -> List[str]:
    profile = melody_phrase_profile_for_emotion(emotion_name)
    role_key = str(section_role or "").strip().lower()
    template = list(
        (profile.get("section_contour_templates") or {}).get(role_key)
        or profile.get("contour_template")
        or []
    )
    if not template:
        template = ["static"]
    out: List[str] = []
    n = max(1, int(phrases_per_section))
    while len(out) < n:
        out.extend(str(x or "static") for x in template)
    return out[:n]


def melody_phrase_role_sequence_for_emotion(
    emotion_name: str,
    phrases_per_section: int,
) -> List[str]:
    profile = melody_phrase_profile_for_emotion(emotion_name)
    template = list(profile.get("phrase_role_template") or ["opening", "answer", "continuation", "cadence"])
    if not template:
        template = ["opening", "cadence"]
    out: List[str] = []
    n = max(1, int(phrases_per_section))
    while len(out) < n:
        out.extend(str(x or "continuation") for x in template)
    if n >= 1:
        out[0] = "opening"
    if n >= 2:
        out[-1] = "cadence"
    return out[:n]

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class EmotionProfile:
    """Per-emotion harmony and groove inputs for composition (see CONFIG.composition for policy overrides)."""

    name: str
    scale_intervals: List[int]
    tempo_multiplier: float
    velocity_multiplier: float
    density: float
    chord_progressions: List[List[str]]
    # FIX: humanization was referenced by engine.py but never defined here,
    # so the humanizer silently never fired.
    humanization: Optional[object] = None
    # Forward-looking: short 2-chord cadences for phrase endings (not yet wired
    # into the engine but available for future use).
    cadence_progressions: Optional[List[List[str]]] = None
    # Optional per-arrangement-role progression pools (same symbol vocabulary as chord_progressions).
    # Keys: intro | a | b | a_prime | pre_chorus | tag | outro — match ArrangementPolicy.section_role.
    # If a role is missing, chord_progressions is used for that section.
    arrangement_chord_sets: Optional[Dict[str, List[List[str]]]] = None


def merged_chord_progression_pool(emotion: EmotionProfile) -> List[List[str]]:
    """All progressions for training / artificial melodies (base + arrangement sets)."""
    pools: List[List[str]] = list(emotion.chord_progressions)
    sets = getattr(emotion, "arrangement_chord_sets", None) or {}
    for _role, progs in sorted(sets.items()):
        if progs:
            pools.extend(progs)
    return pools


def chord_progression_pool_for_section_role(
    emotion: EmotionProfile, section_role: Optional[str]
) -> List[List[str]]:
    """Progression list used when generating harmony for one section (A vs B, etc.)."""
    sets = getattr(emotion, "arrangement_chord_sets", None) or {}
    role = (section_role or "").lower() if section_role else ""
    if role and sets.get(role):
        pool = sets[role]
        # Non-empty key but only empty progressions → treat as missing (avoid empty Markov vocab).
        if pool and any(len(p) > 0 for p in pool):
            return pool
    # Auto-derive role-appropriate pools when explicit sets are missing.
    # This keeps the form (A vs B vs outro) emotionally consistent without requiring
    # every emotion to define `arrangement_chord_sets`.
    base = list(emotion.chord_progressions or [])
    if not role or not base:
        return base

    def _is_tonic(sym: str) -> bool:
        s = (sym or "").strip()
        return s.startswith("I") or s.startswith("i")

    def _is_dominantish(sym: str) -> bool:
        s = (sym or "").strip().lower()
        if not s:
            return False
        return s.startswith("v") or "7" in s or "sus" in s

    def _tension_score(prog: List[str]) -> float:
        txt = " ".join(str(x) for x in (prog or [])).lower()
        return (
            1.0 * txt.count("bii")
            + 0.7 * (txt.count("dim") + txt.count("°") + txt.count("ø"))
            + 0.6 * (txt.count("aug") + txt.count("+"))
            + 0.25 * (txt.count("b9") + txt.count("#9"))
        )

    def _pop_role_score(prog: List[str], *, role_name: str) -> float:
        if not prog:
            return -1e9
        first = str(prog[0] or "").strip()
        last = str(prog[-1] or "").strip()
        pen = str(prog[-2] or "").strip() if len(prog) >= 2 else ""
        score = 0.0
        tension = _tension_score(prog)
        score -= 0.35 * float(tension)
        # Prefer radio-pop function signals: open verses, dominant-ish pre, tonic-led chorus.
        if role_name in {"intro", "a"}:
            if not _is_tonic(last):
                score += 1.1
            if _is_tonic(first):
                score += 0.25
            if _is_dominantish(last):
                score -= 0.35
        elif role_name == "pre_chorus":
            if _is_dominantish(last) or _is_dominantish(pen):
                score += 1.25
            if _is_tonic(last):
                score -= 0.9
            score += 0.15 if not _is_tonic(first) else 0.0
        elif role_name in {"b", "a_prime", "tag"}:
            if _is_tonic(first):
                score += 0.95
            if _is_tonic(last):
                score += 1.15
            if _is_dominantish(pen):
                score += 0.45
            score -= 0.20 * float(tension)
        elif role_name == "outro":
            if _is_tonic(last):
                score += 1.35
            if _is_dominantish(last):
                score -= 0.55
            score -= 0.30 * float(tension)
        return score

    # Emotion anchors can express cadence intent (authentic/plagal/avoid/suspended).
    # Use it as a soft bias on which progressions we consider for each role, without
    # eliminating variety.
    cadence = "authentic"
    try:
        from data.emotion_anchors import anchors_for_emotion

        cadence = str(getattr(anchors_for_emotion(emotion), "cadence", "authentic") or "authentic").lower()
    except Exception:
        cadence = "authentic"

    def _cadence_score(prog: List[str]) -> float:
        if not prog:
            return 0.0
        last = str(prog[-1] or "").strip()
        prev = str(prog[-2] or "").strip() if len(prog) >= 2 else ""
        last_l = last.lower()
        prev_l = prev.lower()

        tonic = _is_tonic(last)
        has_sus = ("sus" in last_l) or ("sus" in prev_l)
        has_dom = (prev.startswith("V") or prev.startswith("v") or "v/" in prev_l or "7" in prev_l)
        has_plagal = prev.startswith("IV") or prev.startswith("iv")

        # Small lexical tension hints (used only as tie-breakers).
        tension_hint = 0.0
        tension_hint += 0.15 * last_l.count("bii")
        tension_hint += 0.10 * (last_l.count("dim") + last_l.count("aug") + last_l.count("+"))
        tension_hint += 0.05 * (last_l.count("b9") + last_l.count("#9"))

        if cadence == "avoid":
            # Prefer non-tonic endings; allow darker neighbors/diminished color.
            return (1.0 if not tonic else -1.0) + tension_hint + (0.15 if "dim" in last_l else 0.0)
        if cadence == "plagal":
            # Prefer IV→I-ish closure, otherwise mild preference for tonic endings.
            if tonic and has_plagal:
                return 1.25 + tension_hint
            return (0.45 if tonic else 0.0) + (0.35 if last.startswith("IV") or last.startswith("iv") else 0.0) + tension_hint
        if cadence == "suspended":
            # Prefer unresolved or suspended landings.
            return (1.0 if has_sus or (not tonic) else -0.3) + tension_hint
        # authentic
        return (1.0 if tonic else -0.1) + (0.25 if tonic and has_dom else 0.0) + tension_hint

    def _apply_cadence_bias(pool: List[List[str]], *, role_name: str) -> List[List[str]]:
        if not pool:
            return pool
        if role_name == "pre_chorus":
            ranked = sorted(pool, key=lambda prog: _pop_role_score(prog, role_name=role_name), reverse=True)
            k = max(4, int(round(len(ranked) * 0.65)))
            k = min(len(ranked), max(4, k))
            return ranked[:k] if len(ranked) > 4 else ranked
        # Stable sort so equal scores preserve authored ordering.
        ranked = sorted(
            pool,
            key=lambda prog: (_cadence_score(prog) + _pop_role_score(prog, role_name=role_name)),
            reverse=True,
        )
        # Keep most items to preserve variety; just bias the candidate set.
        keep_frac = 0.70
        if cadence == "avoid" and role_name in {"intro", "a", "pre_chorus"}:
            keep_frac = 0.60
        elif cadence in {"plagal", "authentic"} and role_name in {"outro"}:
            keep_frac = 0.60
        k = max(4, int(round(len(ranked) * keep_frac)))
        k = min(len(ranked), max(4, k))
        return ranked[:k] if len(ranked) > 4 else ranked

    # Verse-like roles: prefer less closure (avoid tonic on last chord).
    if role in {"a", "intro", "pre_chorus"}:
        if cadence == "avoid":
            pool = [p for p in base if p and len(p) >= 2 and (not _is_tonic(str(p[-1])))] or base
        else:
            pool = list(base)
        if role == "pre_chorus":
            pool = sorted(pool, key=lambda prog: _pop_role_score(prog, role_name=role), reverse=True)
            pool = pool[: max(4, int(round(len(pool) * 0.65)))] or pool
        # Intro prefers calmer (less tension) if possible.
        if role == "intro":
            pool2 = sorted(pool, key=_tension_score)
            pool2 = pool2[: max(3, len(pool2) // 2)] or pool
            return _apply_cadence_bias(pool2, role_name=role)
        return _apply_cadence_bias(pool, role_name=role)

    # Chorus/return/outro roles: prefer stronger closure unless the emotion is explicitly "avoidant".
    if role in {"b", "a_prime", "tag", "outro"}:
        if cadence == "avoid":
            pool = [p for p in base if p and len(p) >= 2 and (not _is_tonic(str(p[-1])))] or base
        else:
            pool = [p for p in base if p and _is_tonic(str(p[-1]))] or base
        pool = sorted(pool, key=lambda prog: _pop_role_score(prog, role_name=role), reverse=True)
        pool = pool[: max(4, int(round(len(pool) * (0.60 if role == "outro" else 0.68))))] or pool
        # Chorus/tag tolerate more motion/tension than outro; keep outro gentler.
        if role == "outro":
            pool2 = sorted(pool, key=_tension_score)
            pool2 = pool2[: max(3, len(pool2) // 2)] or pool
            return _apply_cadence_bias(pool2, role_name=role)
        return _apply_cadence_bias(pool, role_name=role)

    return base

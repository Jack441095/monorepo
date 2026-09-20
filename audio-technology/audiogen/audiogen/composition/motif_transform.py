from __future__ import annotations

import random
from typing import List, Sequence, Tuple


def _safe_intervals(values: Sequence[int]) -> List[int]:
    out: List[int] = []
    for v in list(values or []):
        try:
            out.append(int(v))
        except Exception:
            continue
    return out


def _safe_rhythms(values: Sequence[float]) -> List[float]:
    out: List[float] = []
    for v in list(values or []):
        try:
            x = float(v)
        except Exception:
            continue
        if x > 1e-6:
            out.append(float(x))
    return out


def _clamp_rhythm(x: float) -> float:
    # Keep a musically practical floor/ceiling.
    return float(max(0.125, min(4.0, float(x))))


def _identity(intervals: List[int], rhythms: List[float]) -> Tuple[List[int], List[float]]:
    return list(intervals), list(rhythms)


def _invert(intervals: List[int], rhythms: List[float]) -> Tuple[List[int], List[float]]:
    return ([-int(i) for i in list(intervals)], list(rhythms))


def _rhythm_augment(intervals: List[int], rhythms: List[float], factor: float = 1.5) -> Tuple[List[int], List[float]]:
    return (list(intervals), [_clamp_rhythm(float(r) * float(factor)) for r in list(rhythms)])


def _rhythm_diminish(intervals: List[int], rhythms: List[float], factor: float = 0.75) -> Tuple[List[int], List[float]]:
    return (list(intervals), [_clamp_rhythm(float(r) * float(factor)) for r in list(rhythms)])


def _truncate(intervals: List[int], rhythms: List[float], length: int) -> Tuple[List[int], List[float]]:
    n = max(1, min(int(length), min(len(intervals), len(rhythms))))
    return (list(intervals[:n]), list(rhythms[:n]))


def _sequence_shift(intervals: List[int], rhythms: List[float], step: int = 1) -> Tuple[List[int], List[float]]:
    # Shift interval intent gently while preserving contour direction.
    out: List[int] = []
    s = int(step)
    for iv in list(intervals):
        i = int(iv)
        if i == 0:
            out.append(int(0 if s == 0 else (1 if s > 0 else -1)))
        elif i > 0:
            out.append(int(max(1, i + s)))
        else:
            out.append(int(min(-1, i - s)))
    return out, list(rhythms)


def _interval_compress(intervals: List[int], rhythms: List[float]) -> Tuple[List[int], List[float]]:
    out: List[int] = []
    for iv in list(intervals):
        i = int(iv)
        if i == 0:
            out.append(0)
        elif i > 0:
            out.append(max(1, int(round(float(i) * 0.55))))
        else:
            out.append(min(-1, int(round(float(i) * 0.55))))
    return out, list(rhythms)


def transform_motif_for_slot(
    *,
    intervals: Sequence[int],
    rhythms: Sequence[float],
    role: str,
    section_variant: str,
    slot_variant: str,
    slot_index: int,
    total_slots: int,
    strength: float,
    rng: object = random,
) -> Tuple[List[int], List[float], str]:
    """
    Apply a lightweight role-aware motif transform grammar.

    Returns `(intervals, rhythms, transform_name)`.
    """
    iv = _safe_intervals(intervals)
    rh = _safe_rhythms(rhythms)
    if not iv or not rh:
        return [], [], "empty"

    r = str(role or "").strip().lower()
    sv = str(section_variant or "").strip().lower()
    slv = str(slot_variant or "").strip().lower()
    st = max(0.0, min(1.0, float(strength)))
    idx = max(0, int(slot_index))
    n = max(1, int(total_slots))

    # Recall-heavy roles should keep identity stronger.
    recall_role = r in {"b", "chorus", "hook", "tag"}
    if recall_role:
        st *= 0.78
    if slv == "statement":
        st *= 0.65
    if slv in {"answer", "lead_in"}:
        st = min(1.0, st * 1.20 + 0.08)

    if st <= 1e-6:
        return _identity(iv, rh) + ("identity",)

    transform_name = "identity"
    out_iv, out_rh = _identity(iv, rh)

    # Always allow gentle interval compression as a base move at higher strengths.
    if st >= 0.38 and (sv in {"variation", "fragment", "lead_in"} or slv in {"answer"}):
        out_iv, out_rh = _interval_compress(out_iv, out_rh)
        transform_name = "interval_compress"

    # Role/variant-specific transform recipes.
    if sv in {"fragment", "lead_in"} or slv in {"answer"}:
        frag_len = max(2, min(len(out_iv), 3 if n <= 1 else 2 + (1 if idx == 0 else 0)))
        out_iv, out_rh = _truncate(out_iv, out_rh, frag_len)
        transform_name = "truncate"
        if st >= 0.55:
            out_iv, out_rh = _rhythm_diminish(out_iv, out_rh, factor=0.75)
            transform_name = "truncate+diminish"
    elif sv == "variation":
        choices = ["sequence", "invert", "diminish", "augment"]
        weights = [0.34, 0.20, 0.30, 0.16]
        if recall_role:
            # Hooks should vary mostly rhythm/register feel, not contour identity.
            weights = [0.30, 0.10, 0.40, 0.20]
        pick = "sequence"
        try:
            pick = str(getattr(rng, "choices")(choices, weights=weights, k=1)[0])
        except Exception:
            pick = str(choices[0])
        if pick == "invert" and st >= 0.60:
            out_iv, out_rh = _invert(out_iv, out_rh)
            transform_name = "invert"
        elif pick == "augment" and st >= 0.45:
            out_iv, out_rh = _rhythm_augment(out_iv, out_rh, factor=1.5)
            transform_name = "augment"
        elif pick == "diminish":
            out_iv, out_rh = _rhythm_diminish(out_iv, out_rh, factor=0.75)
            transform_name = "diminish"
        else:
            step = 1 if (idx % 2 == 0) else -1
            out_iv, out_rh = _sequence_shift(out_iv, out_rh, step=step)
            transform_name = "sequence"

    # Safety: preserve at least one note and keep lengths aligned.
    m = max(1, min(len(out_iv), len(out_rh)))
    out_iv = list(out_iv[:m])
    out_rh = list(out_rh[:m])
    return out_iv, out_rh, str(transform_name)


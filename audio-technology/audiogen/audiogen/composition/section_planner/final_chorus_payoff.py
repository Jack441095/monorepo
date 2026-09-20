# composition/section_planner/final_chorus_payoff.py
"""Final chorus / tag / outro payoff: detection + timeline/curve shaping."""
from __future__ import annotations
from audiogen_core.config import resolve_config

from typing import Any, Dict, List

from .observability import log_degraded


def resolve_final_chorus_payoff_state(
    owner: Any,
    *,
    role: str,
    section_index: int,
    form_section_count: int,
) -> Dict[str, Any]:
    r = str(role or "").strip().lower()
    idx = max(0, int(section_index))
    form_n = max(1, int(form_section_count))
    try:
        seq = owner.arrangement_policy._FORM_SEQUENCES.get(owner.arrangement_policy.form_mode) or owner.arrangement_policy._FORM_SEQUENCES["default"]
    except Exception as exc:
        log_degraded("resolve_final_chorus_payoff_state.form_seq", exc, section_index=section_index, section_role=role)
        seq = []
    last_chorus = -1
    if isinstance(seq, (list, tuple)) and seq:
        for i, rr in enumerate(seq):
            if str(rr or "").strip().lower() in {"b", "chorus", "hook"}:
                last_chorus = int(i)
    if last_chorus < 0 and r in {"b", "chorus", "hook"}:
        last_chorus = int(idx)
    is_final_chorus = bool(r in {"b", "chorus", "hook"} and idx == int(last_chorus))
    is_post_tag = bool(r in {"tag"} and int(last_chorus) >= 0 and idx >= int(last_chorus) + 1)
    is_final_outro = bool(r in {"outro", "ending"} and idx >= max(0, form_n - 1) and int(last_chorus) >= 0)
    return {
        "enabled": bool(is_final_chorus or is_post_tag or is_final_outro),
        "is_final_chorus": bool(is_final_chorus),
        "is_post_tag": bool(is_post_tag),
        "is_final_outro": bool(is_final_outro),
        "last_chorus_index": int(last_chorus),
    }


def apply_final_chorus_payoff_targets(
    targets: Dict[str, List[float]],
    *,
    payoff_state: Dict[str, Any],
    strength: float,
) -> Dict[str, List[float]]:
    out = {str(k): list(v) for k, v in dict(targets or {}).items()}
    if not bool((payoff_state or {}).get("enabled", False)):
        return out
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out

    n = max(
        len(list(out.get("melody_density", []) or [])),
        len(list(out.get("motif_strength", []) or [])),
        len(list(out.get("tension", []) or [])),
        len(list(out.get("cadence_window", []) or [])),
    )
    if n <= 0:
        return out
    last = n - 1
    pen = max(0, last - 1)

    def _boost(key: str, idx: int, mult: float, lo: float, hi: float) -> None:
        arr = list(out.get(key, []) or [])
        if 0 <= int(idx) < len(arr):
            arr[int(idx)] = float(max(lo, min(hi, float(arr[int(idx)]) * float(mult))))
            out[key] = arr

    def _setmax(key: str, idx: int, value: float, lo: float, hi: float) -> None:
        arr = list(out.get(key, []) or [])
        if 0 <= int(idx) < len(arr):
            arr[int(idx)] = float(max(lo, min(hi, max(float(arr[int(idx)]), float(value)))))
            out[key] = arr

    if bool(payoff_state.get("is_final_chorus", False)):
        start = max(0, int(round(0.35 * float(last))))
        for i in range(start, n):
            _boost("tension", i, 1.04 + 0.10 * s, 0.0, 1.35)
            _boost("motif_strength", i, 1.05 + 0.10 * s, 0.0, 2.0)
        _setmax("cadence_window", pen, 0.76 + 0.18 * s, 0.0, 1.35)
        _setmax("cadence_window", last, 1.06 + 0.20 * s, 0.0, 1.35)
        _boost("melody_density", 0, 1.0 - 0.08 * s, 0.0, 2.25)
    if bool(payoff_state.get("is_post_tag", False)):
        _boost("motif_strength", last, 1.08 + 0.12 * s, 0.0, 2.0)
        _boost("melody_density", last, 1.0 - 0.12 * s, 0.0, 2.25)
        _setmax("cadence_window", last, 1.10 + 0.14 * s, 0.0, 1.35)
    if bool(payoff_state.get("is_final_outro", False)):
        _setmax("cadence_window", pen, 0.92 + 0.14 * s, 0.0, 1.35)
        _setmax("cadence_window", last, 1.16 + 0.14 * s, 0.0, 1.35)
        _boost("tension", pen, 1.02 + 0.06 * s, 0.0, 1.35)
        _boost("melody_density", last, 1.0 - 0.16 * s, 0.0, 2.25)
    return out


def apply_final_chorus_payoff_curve(
    curve: Dict[str, Any],
    *,
    payoff_state: Dict[str, Any],
    strength: float,
) -> Dict[str, Any]:
    out = dict(curve or {})
    if not bool((payoff_state or {}).get("enabled", False)):
        return out
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out

    def _mul(key: str, mult: float, lo: float, hi: float) -> None:
        try:
            base = float(out.get(key, 1.0) or 1.0)
        except Exception:
            base = 1.0
        out[str(key)] = float(max(lo, min(hi, float(base) * float(mult))))

    bump_pr = True
    bump_pr = resolve_config("composition", "melody_final_chorus_payoff_bumps_phrase_repeat", False, bool)
    if bool(payoff_state.get("is_final_chorus", False)):
        _mul("arp_density_mult", 1.06 + 0.10 * s, 0.25, 2.5)
        _mul("motif_prob_mult", 1.06 + 0.08 * s, 0.25, 2.5)
        if bump_pr:
            _mul("phrase_repeat_mult", 1.04 + 0.08 * s, 0.25, 2.5)
        _mul("melody_total_notes_mult", 1.0 - 0.08 * s, 0.35, 2.5)
    if bool(payoff_state.get("is_post_tag", False)):
        _mul("motif_prob_mult", 1.08 + 0.10 * s, 0.25, 2.5)
        _mul("melody_total_notes_mult", 1.0 - 0.10 * s, 0.35, 2.5)
    if bool(payoff_state.get("is_final_outro", False)):
        _mul("markov_rest_prob_mult", 1.05 + 0.10 * s, 0.25, 2.5)
        _mul("melody_total_notes_mult", 1.0 - 0.14 * s, 0.35, 2.5)
    return out
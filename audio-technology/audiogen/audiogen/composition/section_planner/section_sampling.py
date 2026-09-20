# composition/section_planner/section_sampling.py
"""Best-of-K section sampling with optional joint-generation refinement."""
from __future__ import annotations
from audiogen_core.config import resolve_config

import copy
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from ..section_scoring import score_section, score_section_with_sampler_adjustments
from .build_context import SectionBuildSnapshot
from .timeline import _make_timeline_targets


def _snapshot_song_memory(owner: Any) -> Any:
    try:
        sm = getattr(owner, "song_memory", None)
        return copy.deepcopy(sm) if sm is not None else None
    except Exception:
        return None


def _restore_song_memory(owner: Any, snap: Any) -> None:
    if snap is None:
        return
    try:
        setattr(owner, "song_memory", copy.deepcopy(snap))
    except Exception:
        pass


def _capture_selected_song_memory(owner: Any) -> Any:
    return _snapshot_song_memory(owner)


def _publish_sampling_report(
    owner: Any,
    *,
    candidates: List[Dict[str, Any]],
    best_index: Optional[int],
    enabled: bool,
) -> None:
    report_enabled = resolve_config("composition", "section_sampler_debug_report_enabled", True, bool)
    if not report_enabled:
        return
    try:
        setattr(
            owner,
            "_last_section_sampling_report",
            {
                "enabled": bool(enabled),
                "candidate_count": int(len(candidates)),
                "best_index": None if best_index is None else int(best_index),
                "candidates": list(candidates),
            },
        )
    except Exception:
        pass


def _with_temp_comp_overrides(overrides: Dict[str, Any], fn):
    from audiogen_core.config import CONFIG

    comp = getattr(CONFIG, "composition", None)
    if comp is None or not overrides:
        return fn()
    prior = {}
    try:
        for k2, v2 in overrides.items():
            prior[k2] = getattr(comp, k2)
            setattr(comp, k2, v2)
    except Exception:
        pass
    try:
        return fn()
    finally:
        try:
            for k2, v2 in prior.items():
                setattr(comp, k2, v2)
        except Exception:
            pass


def run_best_of_k_section_build(
    planner: Any,
    *,
    owner: Any,
    emotion: Any,
    root_note: int,
    bars: int,
    key_changes: Optional[List[Tuple[int, int]]],
    temperature: float,
    target_notes_per_bar: float,
    melody_style: str,
    humanization_scale: float,
    chord_progression: Optional[List[str]],
    melody_styles: Optional[List[Tuple[int, str]]],
    section_index: int,
    snapshot: SectionBuildSnapshot,
    rt_mode: str,
    effort: str,
) -> List[Tuple]:
    """Score-driven resampling when `section_k_samples` > 1."""
    k = int(snapshot.section_k_samples)
    budget_s = float(snapshot.section_pick_time_budget_s)
    use_wall = bool(snapshot.section_pick_use_wall_clock)

    if rt_mode != "normal":
        eff = str(effort).lower()
        if eff in {"light", "balanced"}:
            k = min(int(k), 2)
        elif eff == "minimal":
            k = 1
    k = max(1, min(9, int(k)))
    budget_s = max(0.05, min(3.0, float(budget_s)))

    if k <= 1:
        return planner._build_section_once(
            emotion=emotion,
            root_note=root_note,
            bars=bars,
            key_changes=key_changes,
            temperature=temperature,
            target_notes_per_bar=target_notes_per_bar,
            melody_style=melody_style,
            humanization_scale=humanization_scale,
            chord_progression=chord_progression,
            melody_styles=melody_styles,
            section_index=section_index,
        )

    joint_on = bool(snapshot.joint_generation_enabled)
    joint_max = int(snapshot.joint_generation_max_iters)
    joint_budget_ms = float(snapshot.joint_generation_budget_ms)
    joint_use_wall = bool(snapshot.joint_generation_use_wall_clock)

    if rt_mode != "normal":
        eff = str(effort).lower()
        if eff in {"light", "balanced"}:
            joint_max = max(1, min(int(joint_max), 2))
        elif eff == "minimal":
            joint_on = False
            joint_max = 1
    joint_max = max(1, min(6, int(joint_max)))
    if rt_mode == "normal" and bool(snapshot.section_pick_use_wall_clock):
        joint_max = min(int(joint_max), 2)
    joint_budget_ms = max(15.0, min(1500.0, float(joint_budget_ms)))

    seed0 = getattr(owner, "seed", None)
    rng0 = getattr(owner, "rng", None)
    t0 = time.time() if use_wall else 0.0
    best_events = None
    best_score = None
    baseline_song_memory = _snapshot_song_memory(owner)
    best_song_memory = None
    picked_candidate = None
    candidates_report: List[Dict[str, Any]] = []
    best_index: Optional[int] = None
    picked_index: Optional[int] = None
    candidate_records: List[Dict[str, Any]] = []

    from audiogen_core.config import CONFIG

    for i in range(int(k)):
        if use_wall and (time.time() - t0) >= budget_s:
            break
        _restore_song_memory(owner, baseline_song_memory)
        try:
            if seed0 is not None:
                owner.seed = int(seed0) + int(i)
        except Exception:
            pass
        try:
            if rng0 is not None and hasattr(rng0, "seed"):
                rng0.seed((int(seed0) if seed0 is not None else 12345) + int(i))
        except Exception:
            pass

        overrides: Dict[str, Any] = {}

        def _build_once():
            return planner._build_section_once(
                emotion=emotion,
                root_note=root_note,
                bars=bars,
                key_changes=key_changes,
                temperature=temperature,
                target_notes_per_bar=target_notes_per_bar,
                melody_style=melody_style,
                humanization_scale=humanization_scale,
                chord_progression=chord_progression,
                melody_styles=melody_styles,
                section_index=section_index,
            )

        evs = None
        iters = 1
        if joint_on:
            iters = joint_max
        t_joint0 = time.time() if joint_use_wall else 0.0
        for ji in range(int(iters)):
            if joint_on and joint_use_wall and ((time.time() - t_joint0) * 1000.0) >= joint_budget_ms:
                break
            evs_try = _with_temp_comp_overrides(overrides, _build_once)
            if not evs_try:
                continue
            try:
                curve = owner.arrangement_policy.arrangement_curve(section_index, emotion)
                role = owner.arrangement_policy.section_role(section_index)
                targets = _make_timeline_targets(role, int(bars), dict(curve))
            except Exception:
                role = ""
                targets = None
            sc_try = score_section(
                evs_try,
                beats_per_bar=4.0,
                bars=int(bars),
                timeline_targets=targets,
                section_role=role,
                emotion_name=str(getattr(emotion, "name", "") or ""),
            )
            det = dict(sc_try.details or {})

            try:
                pc = float(det.get("compat_pc_collision_frac", 0.0) or 0.0)
                strong = float(det.get("compat_strongbeat_masked_frac", 0.0) or 0.0)
                sep_ok = float(det.get("compat_register_sep_ok_frac", 1.0) or 1.0)
            except Exception:
                pc, strong, sep_ok = 0.0, 0.0, 1.0
            good = (pc <= 0.25) and (strong <= 0.75) and (sep_ok >= 0.60)

            evs = evs_try
            if good or (not joint_on):
                break

            try:
                comp = CONFIG.composition
                if not overrides:
                    overrides = {}
                if pc > 0.25:
                    base = float(getattr(comp, "masking_constraints_strength", 0.70) or 0.70)
                    rlc = str(role or "").strip().lower()
                    # Non-chorus roles need readable toplines; avoid reinforcing
                    # collisions by over-tightening masks in verse/pre sections.
                    if rlc in {"intro", "a", "verse", "pre_chorus", "outro"}:
                        overrides["masking_constraints_strength"] = float(max(0.35, min(1.0, base - 0.10)))
                    else:
                        overrides["masking_constraints_strength"] = float(min(0.82, max(0.35, base + 0.04)))
                    overrides["arp_groove_link_mode"] = "complement"
                    base_gl = float(getattr(comp, "arp_melody_groove_link_strength", 0.0) or 0.0)
                    overrides["arp_melody_groove_link_strength"] = float(min(1.0, max(base_gl, 0.35)))
                if strong > 0.75:
                    base_fd = float(getattr(comp, "arp_density_follow_melody", 0.0) or 0.0)
                    overrides["arp_density_follow_melody"] = float(min(1.0, base_fd + 0.15))
                if sep_ok < 0.60:
                    base_sep = int(getattr(comp, "arp_melody_register_separation_semitones", 5) or 5)
                    overrides["arp_melody_register_separation_semitones"] = int(min(12, base_sep + 1))
            except Exception:
                pass

        if not evs:
            continue
        candidate_song_memory = _capture_selected_song_memory(owner)
        try:
            curve = owner.arrangement_policy.arrangement_curve(section_index, emotion)
            role = owner.arrangement_policy.section_role(section_index)
            targets = _make_timeline_targets(role, int(bars), dict(curve))
        except Exception:
            role = ""
            targets = None
        pick = score_section_with_sampler_adjustments(
            evs,
            beats_per_bar=4.0,
            bars=int(bars),
            timeline_targets=targets,
            section_role=role,
            emotion_name=str(getattr(emotion, "name", "") or ""),
            emotion=emotion,
            root_note=int(root_note),
            candidate_song_memory=candidate_song_memory,
            baseline_song_memory=baseline_song_memory,
        )
        adjusted_score = float(pick.score)
        sampler_details = dict(pick.details or {})
        candidate_index = len(candidates_report)
        candidates_report.append(
            {
                "index": int(candidate_index),
                "base_score": float(sampler_details.get("section_score_before_sampler", pick.score)),
                "adjusted_score": float(adjusted_score),
                "section_role": str(role or ""),
                "details": sampler_details,
            }
        )
        if best_score is None or float(adjusted_score) > float(best_score):
            best_score = float(adjusted_score)
            best_events = list(evs)
            best_song_memory = candidate_song_memory
            best_index = int(candidate_index)
        candidate_records.append(
            {
                "index": int(candidate_index),
                "score": float(adjusted_score),
                "events": list(evs),
                "song_memory": candidate_song_memory,
            }
        )

    try:
        owner.seed = seed0
    except Exception:
        pass
    if candidate_records:
        pick_mode = "argmax"
        pick_temp = 0.24
        pick_top_n = 3
        try:
            pick_mode = str(getattr(CONFIG.composition, "section_bestofk_pick_mode", "argmax") or "argmax").strip().lower()
            pick_temp = float(getattr(CONFIG.composition, "section_bestofk_softmax_temp", 0.24) or 0.24)
            pick_top_n = int(getattr(CONFIG.composition, "section_bestofk_softmax_top_n", 3) or 3)
        except Exception:
            pass
        pick_temp = max(0.02, min(2.0, float(pick_temp)))
        pick_top_n = max(1, min(9, int(pick_top_n)))
        if pick_mode == "softmax_topn":
            ranked = sorted(candidate_records, key=lambda r: float(r["score"]), reverse=True)
            shortlist = ranked[: max(1, min(int(pick_top_n), len(ranked)))]
            smax = max(float(r["score"]) for r in shortlist)
            weighted = []
            total_w = 0.0
            for rec in shortlist:
                w = math.exp((float(rec["score"]) - smax) / float(pick_temp))
                weighted.append((w, rec))
                total_w += float(w)
            if total_w > 0.0:
                rr = getattr(owner, "rng", None)
                u = float(rr.random()) if rr is not None and hasattr(rr, "random") else 0.5
                r = u * float(total_w)
                acc = 0.0
                picked_candidate = shortlist[0]
                for w, rec in weighted:
                    acc += float(w)
                    if r <= acc:
                        picked_candidate = rec
                        break
            else:
                picked_candidate = shortlist[0]
            picked_index = int(picked_candidate["index"])
        else:
            picked_candidate = max(candidate_records, key=lambda r: float(r["score"]))
            picked_index = int(picked_candidate["index"])
    if picked_candidate is not None:
        best_events = list(picked_candidate["events"])
        best_song_memory = picked_candidate["song_memory"]
        _restore_song_memory(owner, best_song_memory)
        _publish_sampling_report(
            owner,
            candidates=candidates_report,
            best_index=picked_index if picked_index is not None else best_index,
            enabled=True,
        )
        return best_events
    _restore_song_memory(owner, baseline_song_memory)
    _publish_sampling_report(
        owner,
        candidates=candidates_report,
        best_index=None,
        enabled=True,
    )
    return planner._build_section_once(
        emotion=emotion,
        root_note=root_note,
        bars=bars,
        key_changes=key_changes,
        temperature=temperature,
        target_notes_per_bar=target_notes_per_bar,
        melody_style=melody_style,
        humanization_scale=humanization_scale,
        chord_progression=chord_progression,
        melody_styles=melody_styles,
        section_index=section_index,
    )

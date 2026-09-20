# composition/song_postprocess/form_polish/motif_theme.py
# Song-theme development: the private `_apply_developed_motif_variation` helper
# (thins/shifts a motif cell for non-chorus roles) and its only caller,
# `develop_song_theme_and_rewrite_hooks` (extracts the song's strongest motif
# cell and rewrites verse/pre/chorus restatements from it).
#
# NOTE: `_apply_developed_motif_variation` is private (leading underscore) but is
# imported directly by tests/audiogen/test_song_postprocess_motif_development.py
# (`from composition.song_postprocess.form_polish import _apply_developed_motif_variation`),
# so it must stay re-exported from the `form_polish` package `__init__.py`, not just
# `develop_song_theme_and_rewrite_hooks`.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from composition.theme_planner import planned_theme_cell_for_emotion

from .._common import (
    Event,
    _active_chord_pcs_at,
    _blend_theme_cell_with_planned_profile,
    _build_chord_windows,
    _clamp_lead_pitch,
    _emotion_scale_pcs_for_section,
    _lead_between,
    _lead_pitch,
    _reharmonize_inserted_lead_pitch,
    _section_starts,
    _select_reprise_motif_cell,
    _snap_inserted_pitch_to_section_scale,
)
from ._constants import _HOOK_IDENTITY_EMOTIONS, _MOTIF_DEVELOPMENT_EMOTIONS, _MOTIF_DEVELOPMENT_FAMILIES


def _apply_developed_motif_variation(
    motif_rows: Sequence[Tuple[float, float, int, int]],
    *,
    role: str,
    primary_emotion: str,
    theme_family: str,
) -> List[Tuple[float, float, int, int]]:
    """Shape verse/pre motifs so hook similarity lands near the audit sweet spot (~0.48)."""

    role_l = str(role or "").strip().lower()
    if role_l in {"b", "chorus", "hook", "tag"}:
        return list(motif_rows)

    primary = str(primary_emotion or "").strip().lower()
    family = str(theme_family or "").strip().lower()
    if primary not in _MOTIF_DEVELOPMENT_EMOTIONS and family not in _MOTIF_DEVELOPMENT_FAMILIES:
        return list(motif_rows)

    if role_l in {"a", "verse", "a_prime"}:
        keep = {0, 3, 5}
        pitch_nudge = -2
        time_nudge = 0.25
    elif role_l == "pre_chorus":
        keep = {0, 1, 3, 5}
        pitch_nudge = -1
        time_nudge = 0.125
    else:
        keep = {0, 2}
        pitch_nudge = -3
        time_nudge = 0.0

    developed: List[Tuple[float, float, int, int]] = []
    for row_i, (rel_start, dur, rel_pitch, vel0) in enumerate(motif_rows):
        if int(row_i) not in keep:
            continue
        rs = float(rel_start)
        rp = int(rel_pitch)
        if int(row_i) > 0 and float(time_nudge) > 0.0:
            rs += float(time_nudge)
        if int(row_i) > 0 and int(pitch_nudge) != 0:
            rp += int(pitch_nudge if int(row_i) >= 3 else int(pitch_nudge) // 2)
        developed.append((rs, float(dur), int(rp), int(vel0)))
    return developed if len(developed) >= 3 else list(motif_rows)


def develop_song_theme_and_rewrite_hooks(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    strength: float = 0.74,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Create one song theme and develop it across sections with stronger chorus hooks."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "sections_developed": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    s = max(0.0, min(1.0, float(strength)))
    primary0 = str(primary_emotion or "").strip().lower()
    try:
        from data.emotion_aliases import canonical_emotion_name

        primary0 = canonical_emotion_name(primary0) or primary0
    except Exception:
        pass
    hook_boost = primary0 in _HOOK_IDENTITY_EMOTIONS
    if hook_boost:
        s = max(float(s), 0.88)
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    n = min(len(starts), len(section_bars), len(roles), len(section_roots or []), len(section_emotions or []))
    if n <= 1 or s <= 1e-6:
        return out, {"enabled": False, "sections_developed": 0}

    chord_windows = _build_chord_windows(out)
    if not chord_windows:
        return out, {"enabled": True, "sections_developed": 0, "reason": "no_chord_context"}

    def _is_chorus(role: str) -> bool:
        return str(role or "").strip().lower() in {"b", "chorus", "hook", "tag"}

    def _source_index() -> Optional[int]:
        for wanted in ({"b", "chorus", "hook"}, {"a", "verse"}, {"pre_chorus"}):
            for i in range(n):
                if roles[i] not in wanted:
                    continue
                leads = _lead_between(out, starts[i], starts[i] + min(3.0 * bpb, 12.0))
                if len(leads) >= 4:
                    return int(i)
        return None

    src_idx = _source_index()
    if src_idx is None:
        return out, {"enabled": True, "sections_developed": 0}
    src_start = float(starts[src_idx])
    source_leads = _lead_between(out, src_start, src_start + min(3.0 * bpb, 12.0))
    first_pitch = _lead_pitch(source_leads[0]) if source_leads else None
    if first_pitch is None:
        return out, {"enabled": True, "sections_developed": 0}

    motif_candidates: List[Tuple[float, float, int, int]] = []
    for ev in source_leads[:10]:
        p = _lead_pitch(ev)
        if p is None:
            continue
        try:
            rel_start = max(0.0, float(ev[3]) - src_start)
            dur = max(0.18, min(1.5, float(ev[4])))
            vel = int(ev[2])
        except Exception:
            continue
        motif_candidates.append((float(rel_start), float(dur), int(p) - int(first_pitch), int(vel)))
    if len(motif_candidates) < 4:
        return out, {"enabled": True, "sections_developed": 0}

    theme_cell, theme_meta = _select_reprise_motif_cell(
        motif_candidates,
        strength=max(0.78, float(s)),
        beats_per_bar=float(bpb),
        hook_target=True,
    )
    planned_cell, planned_meta = planned_theme_cell_for_emotion(
        str(primary_emotion or list(section_emotions)[src_idx]),
        source_velocity=int(source_leads[0][2]) if source_leads else 82,
        max_notes=8,
    )
    theme_cell, theme_meta = _blend_theme_cell_with_planned_profile(
        theme_cell,
        theme_meta,
        planned_cell,
        strength=max(0.92, float(s)) if hook_boost else float(s),
    )
    if len(theme_cell) < 4:
        return out, {"enabled": True, "sections_developed": 0}

    def _variant(role: str, sec_i: int) -> Dict[str, Any]:
        role0 = str(role or "").strip().lower()
        primary0 = str(primary_emotion or "").strip().lower()
        reflective0 = primary0 in {"love", "caring", "relief", "sadness", "grief", "remorse", "disappointment"}
        bright_dev0 = primary0 in _MOTIF_DEVELOPMENT_EMOTIONS
        hook_boost0 = primary0 in _HOOK_IDENTITY_EMOTIONS
        if role0 in {"intro"}:
            return {"cap": 2 if reflective0 else 3, "span": 1.75 * bpb, "transpose": -5, "dur": 1.22 if reflective0 else 1.15, "vel": 0.62 if reflective0 else 0.68, "compress": 1.18 if reflective0 else 1.05}
        if role0 in {"outro", "ending"}:
            return {"cap": 2 if reflective0 else 3, "span": 1.75 * bpb, "transpose": -7, "dur": 1.32 if reflective0 else 1.25, "vel": 0.54 if reflective0 else 0.58, "compress": 1.24 if reflective0 else 1.12}
        if role0 in {"a", "verse", "a_prime"}:
            if bright_dev0:
                return {"cap": 4, "span": 2.0 * bpb, "transpose": -4, "dur": 1.06, "vel": 0.78, "compress": 1.14}
            return {"cap": 3 if reflective0 else 4, "span": 2.0 * bpb, "transpose": -3 if reflective0 else -2, "dur": 1.12 if reflective0 else 1.00, "vel": 0.74 if reflective0 else 0.82, "compress": 1.16 if reflective0 else 1.00}
        if role0 == "pre_chorus":
            if bright_dev0:
                return {"cap": 5, "span": 2.25 * bpb, "transpose": 1, "dur": 0.98, "vel": 0.86, "compress": 1.06}
            return {"cap": 4 if reflective0 else 5, "span": 2.25 * bpb, "transpose": 1 if reflective0 else 2, "dur": 1.02 if reflective0 else 0.92, "vel": 0.84 if reflective0 else 0.92, "compress": 1.04 if reflective0 else 0.88}
        if role0 in {"b", "chorus", "hook", "tag"}:
            if hook_boost0:
                return {
                    "cap": 8,
                    "span": 3.5 * bpb,
                    "transpose": 7,
                    "dur": 0.92,
                    "vel": 1.10,
                    "compress": 1.0,
                }
            lift = (3 if int(sec_i) <= int(src_idx) else 5) if reflective0 else (5 if int(sec_i) <= int(src_idx) else 7)
            return {"cap": 5 if reflective0 else 7, "span": 3.0 * bpb, "transpose": lift, "dur": 1.08 if reflective0 else 0.95, "vel": 0.96 if reflective0 else 1.08, "compress": 1.04 if reflective0 else 0.92}
        return {"cap": 4, "span": 2.0 * bpb, "transpose": 0, "dur": 1.0, "vel": 0.82, "compress": 1.0}

    def _target_anchor(sec_i: int, fallback: int) -> int:
        sec_start = float(starts[sec_i])
        leads = _lead_between(out, sec_start, sec_start + min(2.0 * bpb, 8.0))
        pitches = [_lead_pitch(ev) for ev in leads]
        pitches = [int(p) for p in pitches if p is not None]
        if pitches:
            return int(sorted(pitches)[len(pitches) // 2])
        root = int(section_roots[sec_i])
        return _clamp_lead_pitch(int(root) + (16 if _is_chorus(roles[sec_i]) else 7))

    remove_ids: set[int] = set()
    inserted: List[Tuple] = []
    sections_developed = 0
    hook_sections = 0
    for sec in range(n):
        role = roles[sec]
        if role not in {"intro", "a", "verse", "a_prime", "pre_chorus", "b", "chorus", "hook", "tag", "outro", "ending"}:
            continue
        spec = _variant(role, int(sec))
        cap = int(spec["cap"])
        span = float(spec["span"])
        transpose = int(spec["transpose"])
        dur_mul = float(spec["dur"])
        vel_mul = float(spec["vel"])
        compress = float(spec["compress"])
        target_start = float(starts[sec])
        anchor = _target_anchor(int(sec), int(first_pitch))
        base_pitch = int(anchor) + int(transpose)
        if role in {"intro", "outro", "ending"}:
            base_pitch = min(base_pitch, int(first_pitch) - 2)

        motif_rows: List[Tuple[float, float, int, int]] = []
        for rel_start, dur, rel_pitch, vel0 in theme_cell:
            if len(motif_rows) >= cap:
                break
            rel = float(rel_start) * float(compress)
            if rel >= span:
                break
            motif_rows.append((float(rel), max(0.18, min(1.25, float(dur) * dur_mul)), int(rel_pitch), int(vel0)))
        if str(primary_emotion or "").strip().lower() in {"love", "caring", "relief", "sadness", "grief", "remorse", "disappointment"} and role not in {"b", "chorus", "hook", "tag"}:
            varied = [row for row_i, row in enumerate(motif_rows) if row_i == 0 or row_i % 2 == 1]
            if len(varied) >= 2:
                motif_rows = varied
        theme_family = str(planned_meta.get("family", "") or "")
        motif_rows = _apply_developed_motif_variation(
            motif_rows,
            role=str(role),
            primary_emotion=str(primary_emotion or ""),
            theme_family=theme_family,
        )
        if len(motif_rows) < 3:
            continue

        motif_span = max(1.0, min(span, max(float(rs) + float(dur) for rs, dur, _rp, _vel in motif_rows)))
        target_end = target_start + motif_span + 0.05
        motif_onsets = [target_start + float(rs) for rs, _dur, _rp, _vel in motif_rows]
        for ev_i, ev in enumerate(out):
            if _lead_pitch(ev) is None:
                continue
            try:
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if target_start - 1e-6 <= st < target_end - 1e-6:
                if float(dur) >= 0.35 or any(abs(float(st) - float(ms)) <= 0.12 for ms in motif_onsets):
                    remove_ids.add(int(ev_i))

        scale_pcs = _emotion_scale_pcs_for_section(
            emotion_name=str(list(section_emotions)[sec]),
            root_note=int(list(section_roots)[sec]),
        )
        last_pitch: Optional[int] = None
        for rel_start, dur, rel_pitch, vel0 in motif_rows:
            st_abs = target_start + float(rel_start)
            chord_pcs = _active_chord_pcs_at(chord_windows, float(st_abs), beats_per_bar=float(bpb))
            force = _is_chorus(role) and (abs((float(st_abs) % bpb) - 0.0) <= 0.10 or abs((float(st_abs) % bpb) - 2.0) <= 0.10)
            pitch = _reharmonize_inserted_lead_pitch(
                int(base_pitch) + int(rel_pitch),
                start_beat=float(st_abs),
                duration_beats=float(dur),
                chord_windows=chord_windows,
                beats_per_bar=float(bpb),
                force=bool(force),
            )
            pitch = _snap_inserted_pitch_to_section_scale(
                int(pitch),
                scale_pcs=set(scale_pcs),
                chord_pcs=set(chord_pcs),
            )
            if last_pitch is not None and abs(int(pitch) - int(last_pitch)) > 10:
                while int(pitch) - int(last_pitch) > 10 and int(pitch) - 12 >= 48:
                    pitch -= 12
                while int(last_pitch) - int(pitch) > 10 and int(pitch) + 12 <= 84:
                    pitch += 12
            vel = int(max(42, min(116, round(float(vel0) * float(vel_mul)))))
            inserted.append((2, int(pitch), int(vel), float(st_abs), float(dur), [int(pitch)]))
            last_pitch = int(pitch)

        # Make the chorus opening read as a real hook: add a short resolved
        # answer on beat 4 if the motif cell ends too early.
        if _is_chorus(role) and str(primary_emotion or "").strip().lower() not in {"love", "caring", "relief", "sadness", "grief", "remorse", "disappointment"}:
            hook_sections += 1
            answer_st = target_start + min(2.5 * bpb, motif_span + 0.5)
            if answer_st < target_start + float(section_bars[sec]) * bpb - 0.75:
                chord_pcs = _active_chord_pcs_at(chord_windows, float(answer_st), beats_per_bar=float(bpb))
                try:
                    answer_offset = int(planned_meta.get("answer_offset", 0) or 0)
                except Exception:
                    answer_offset = 0
                answer_pitch = _reharmonize_inserted_lead_pitch(
                    int(last_pitch or base_pitch) + int(answer_offset),
                    start_beat=float(answer_st),
                    duration_beats=0.62,
                    chord_windows=chord_windows,
                    beats_per_bar=float(bpb),
                    force=True,
                )
                answer_pitch = _snap_inserted_pitch_to_section_scale(
                    int(answer_pitch),
                    scale_pcs=set(scale_pcs),
                    chord_pcs=set(chord_pcs),
                )
                inserted.append((2, int(answer_pitch), 82, float(answer_st), 0.62, [int(answer_pitch)]))
        sections_developed += 1

    if remove_ids or inserted:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
        out.extend(inserted)
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "source_section": int(src_idx),
        "source_role": str(roles[src_idx]),
        "theme_family": str(planned_meta.get("family", "")),
        "theme_source": str(theme_meta.get("theme_source", "extracted")),
        "planned_profile_used": bool(theme_meta.get("planned_profile_used", False)),
        "theme_notes": int(min(8, len(theme_cell))),
        "theme_score": float(theme_meta.get("cell_score", 0.0) or 0.0),
        "theme_identity_score": float(theme_meta.get("extracted_identity_score", 0.0) or 0.0),
        "sections_developed": int(sections_developed),
        "hook_sections_rewritten": int(hook_sections),
        "notes_added": int(len(inserted)),
        "notes_replaced": int(len(remove_ids)),
    }


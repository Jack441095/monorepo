# composition/song_postprocess/form_polish/reprise_hooks.py
# Full-song melodic reprises and chorus hook-identity reinforcement.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .._common import (
    Event,
    _active_chord_pcs_at,
    _build_chord_windows,
    _emotion_scale_pcs_for_section,
    _lead_between,
    _lead_pitch,
    _reharmonize_inserted_lead_pitch,
    _section_starts,
    _select_reprise_motif_cell,
    _snap_inserted_pitch_to_section_scale,
)
from ._constants import _HOOK_IDENTITY_EMOTIONS


def add_melody_reprises(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Optional[Sequence[int]] = None,
    section_emotions: Optional[Sequence[str]] = None,
    beats_per_bar: float = 4.0,
    strength: float = 0.68,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Restate short lead motifs in later song sections.

    This is a full-song identity pass: it edits only lead notes, and only inside
    the opening window of later repeated/developed roles.
    """

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"reprises_written": 0, "notes_added": 0, "notes_replaced": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"reprises_written": 0, "notes_added": 0, "notes_replaced": 0}

    primary_emo = ""
    try:
        from data.emotion_aliases import canonical_emotion_name

        for raw in list(section_emotions or []):
            name = canonical_emotion_name(str(raw or "").strip().lower())
            if name:
                primary_emo = str(name)
                break
    except Exception:
        primary_emo = str(list(section_emotions or [""])[0] or "").strip().lower()
    if primary_emo in _HOOK_IDENTITY_EMOTIONS:
        s = max(float(s), 0.90)

    starts = _section_starts(section_bars, beats_per_bar=bpb)
    chord_windows = _build_chord_windows(out)
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    n = min(len(starts), len(roles))
    if n <= 1:
        return out, {"reprises_written": 0, "notes_added": 0, "notes_replaced": 0}

    def _source_index_for(source_roles: set[str], *, min_notes: int = 3) -> Optional[int]:
        for i in range(n):
            if roles[i] in source_roles:
                leads = _lead_between(out, starts[i], starts[i] + min(2.5 * bpb, 10.0))
                if len(leads) >= int(max(2, int(min_notes))):
                    return int(i)
        return None

    # Chorus-first identity: prioritize making choruses restate a recognisable hook.
    # Verse->A' restatement is intentionally *not* enforced here because it can
    # make later verse-like sections feel copy/paste instead of varied.
    source_specs: List[Tuple[str, Optional[int], set[str]]] = [
        ("hook", _source_index_for({"b", "chorus", "hook"}), {"b", "chorus", "hook", "tag"}),
        # In short forms and previews there may be only one payoff section.
        # Allow an early verse/pre build cell to become the first chorus hook.
        ("lift", _source_index_for({"a", "verse", "pre_chorus"}, min_notes=2), {"b", "chorus", "hook", "tag"}),
    ]

    inserted: List[Tuple] = []
    remove_ids: set[int] = set()
    reprises = 0
    source_meta: List[Dict[str, Any]] = []
    targeted_sections: set[int] = set()

    for family, src_idx, target_roles in source_specs:
        if src_idx is None:
            continue
        src_start = float(starts[src_idx])
        src_end = src_start + min(3.0 * bpb, 12.0)
        source_leads = _lead_between(out, src_start, src_end)
        if len(source_leads) < 3:
            continue
        first_pitch = _lead_pitch(source_leads[0])
        if first_pitch is None:
            continue
        motif_candidates: List[Tuple[float, float, int, int]] = []
        for ev in source_leads:
            p = _lead_pitch(ev)
            if p is None:
                continue
            try:
                rel_start = max(0.0, float(ev[3]) - src_start)
                dur = max(0.125, min(2.0, float(ev[4])))
                vel = int(ev[2])
            except Exception:
                continue
            motif_candidates.append((float(rel_start), float(dur), int(p) - int(first_pitch), int(vel)))
        if len(motif_candidates) < 3:
            continue

        for idx in range(int(src_idx) + 1, n):
            role = roles[idx]
            if role not in target_roles:
                continue
            if int(idx) in targeted_sections:
                continue
            # Do not overstate every repeated chorus unless strength is high.
            if (
                family == "hook"
                and role in {"b", "chorus", "hook"}
                and reprises >= 2
                and s < 0.85
                and primary_emo not in _HOOK_IDENTITY_EMOTIONS
            ):
                continue
            if family == "lift" and role in {"b", "chorus", "hook"} and any(
                roles[j] in {"b", "chorus", "hook"} for j in range(0, int(idx))
            ):
                continue
            target_start = float(starts[idx])
            target_leads = _lead_between(out, target_start, target_start + min(3.0 * bpb, 12.0) + 0.05)
            anchor = _lead_pitch(target_leads[0]) if target_leads else int(first_pitch)
            if anchor is None:
                anchor = int(first_pitch)
            transpose = int(anchor) - int(first_pitch)
            # Tags and final hook returns can sit slightly higher when the target
            # section already points upward.
            if role == "tag" and s >= 0.65:
                transpose += 2

            hook_target = role in {"b", "chorus", "hook", "tag"}
            selected_cell, selected_meta = _select_reprise_motif_cell(
                motif_candidates,
                strength=float(s),
                beats_per_bar=float(bpb),
                hook_target=bool(hook_target),
            )
            motif_note_cap = 9 if hook_target and primary_emo in _HOOK_IDENTITY_EMOTIONS else (8 if hook_target else 5)
            motif_span_cap = 3.5 * bpb if hook_target and primary_emo in _HOOK_IDENTITY_EMOTIONS else (3.0 * bpb if hook_target else 2.0 * bpb)
            motif_rows: List[Tuple[float, float, int, int]] = []
            for rel_start, dur, rel_pitch, vel0 in selected_cell:
                if len(motif_rows) >= int(motif_note_cap):
                    break
                if float(rel_start) >= float(motif_span_cap):
                    break
                motif_rows.append((float(rel_start), float(dur), int(rel_pitch), int(vel0)))
            if len(motif_rows) < 3:
                continue
            motif_span = max(
                1.0,
                min(float(motif_span_cap), max(float(rs) + float(d) for rs, d, _rp, _v in motif_rows)),
            )
            target_window_end = target_start + motif_span + 0.05

            # Replace only lead material that collides with the reprise cell.
            # Earlier versions cleared the whole opening window, which could
            # collapse a detailed chorus into only the capped motif notes.
            motif_onsets = [round(float(target_start) + float(rs), 6) for rs, _dur, _rp, _v in motif_rows]
            for ev_i, ev in enumerate(out):
                if _lead_pitch(ev) is None:
                    continue
                try:
                    st = float(ev[3])
                    dur = float(ev[4])
                except Exception:
                    continue
                if target_start - 1e-6 <= st < target_window_end - 1e-6:
                    if float(dur) >= 0.45 or any(abs(float(st) - float(ms)) <= 0.10 for ms in motif_onsets):
                        remove_ids.add(int(ev_i))

            for rel_start, dur, rel_pitch, vel0 in motif_rows:
                st_abs = float(target_start) + float(rel_start)
                chord_pcs = _active_chord_pcs_at(
                    chord_windows,
                    float(st_abs),
                    beats_per_bar=float(bpb),
                )
                pitch = _reharmonize_inserted_lead_pitch(
                    int(first_pitch) + int(transpose) + int(rel_pitch),
                    start_beat=float(st_abs),
                    duration_beats=float(dur),
                    chord_windows=chord_windows,
                    beats_per_bar=float(bpb),
                )
                try:
                    target_root = int(list(section_roots or [])[idx])
                    target_emotion = str(list(section_emotions or [])[idx])
                except Exception:
                    target_root = 60
                    target_emotion = ""
                scale_pcs = _emotion_scale_pcs_for_section(
                    emotion_name=str(target_emotion),
                    root_note=int(target_root),
                )
                pitch = _snap_inserted_pitch_to_section_scale(
                    int(pitch),
                    scale_pcs=set(scale_pcs),
                    chord_pcs=set(chord_pcs),
                )
                vel = int(max(45, min(115, round(float(vel0) * (0.86 + 0.16 * s)))))
                inserted.append(
                    (
                        2,
                        int(pitch),
                        int(vel),
                        float(st_abs),
                        float(dur),
                        [int(pitch)],
                    )
                )
            reprises += 1
            targeted_sections.add(int(idx))
            source_meta.append(
                {
                    "family": str(family),
                    "source_index": int(src_idx),
                    "target_index": int(idx),
                    "target_role": str(role),
                    "motif_notes": int(len(motif_rows)),
                    "selected_cell_start": int(selected_meta.get("cell_start", 0) or 0),
                    "selected_cell_score": float(selected_meta.get("cell_score", 0.0) or 0.0),
                }
            )

    if remove_ids or inserted:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
        out.extend(inserted)
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "reprises_written": int(reprises),
        "notes_added": int(len(inserted)),
        "notes_replaced": int(len(remove_ids)),
        "strength": float(s),
        "sources": list(source_meta),
    }


def reinforce_song_hook_identity(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    strength: float = 0.85,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Align later chorus openings with the first chorus hook for weak-identity emotions."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "chorus_sections_aligned": 0}

    primary = str(primary_emotion or "").strip().lower()
    try:
        from data.emotion_aliases import canonical_emotion_name

        primary = canonical_emotion_name(primary) or primary
    except Exception:
        pass
    if primary not in _HOOK_IDENTITY_EMOTIONS:
        return out, {"enabled": False, "chorus_sections_aligned": 0, "primary_emotion": str(primary)}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"enabled": False, "chorus_sections_aligned": 0}

    starts = _section_starts(section_bars, beats_per_bar=bpb)
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    n = min(len(starts), len(section_bars), len(roles), len(section_roots or []), len(section_emotions or []))

    chorus_idxs = [i for i in range(n) if roles[i] in {"b", "chorus", "hook", "tag"}]
    if len(chorus_idxs) < 2:
        return out, {"enabled": True, "chorus_sections_aligned": 0, "reason": "single_chorus"}

    src_idx = int(chorus_idxs[0])
    src_start = float(starts[src_idx])
    hook_window = 8.0
    source_leads = _lead_between(out, src_start, src_start + hook_window)
    if len(source_leads) < 4:
        return out, {"enabled": True, "chorus_sections_aligned": 0, "reason": "sparse_hook"}

    first_pitch = _lead_pitch(source_leads[0])
    if first_pitch is None:
        return out, {"enabled": True, "chorus_sections_aligned": 0}

    hook_cell: List[Tuple[float, float, int, int]] = []
    for ev in source_leads[:9]:
        p = _lead_pitch(ev)
        if p is None:
            continue
        try:
            rel_start = max(0.0, float(ev[3]) - src_start)
            dur = max(0.18, min(1.5, float(ev[4])))
            vel = int(ev[2])
        except Exception:
            continue
        hook_cell.append((float(rel_start), float(dur), int(p) - int(first_pitch), int(vel)))
    if len(hook_cell) < 4:
        return out, {"enabled": True, "chorus_sections_aligned": 0}

    remove_ids: set[int] = set()
    inserted: List[Tuple] = []
    aligned = 0

    for idx in chorus_idxs[1:]:
        target_start = float(starts[idx])
        target_leads = _lead_between(out, target_start, target_start + hook_window)
        tgt_pitches = [_lead_pitch(ev) for ev in target_leads if _lead_pitch(ev) is not None]
        tgt_anchor = int(sorted(tgt_pitches)[len(tgt_pitches) // 2]) if tgt_pitches else int(section_roots[idx]) + 12
        transpose = int(tgt_anchor) - int(first_pitch)

        motif_span = max(1.0, min(3.5 * bpb, max(float(rs) + float(dur) for rs, dur, _rp, _vel in hook_cell)))
        target_end = target_start + motif_span + 0.05
        motif_onsets = [target_start + float(rs) for rs, _dur, _rp, _vel in hook_cell]

        for ev_i, ev in enumerate(out):
            if _lead_pitch(ev) is None:
                continue
            try:
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if target_start - 1e-6 <= st < target_end - 1e-6:
                if float(dur) >= 0.30 or any(abs(float(st) - float(ms)) <= 0.10 for ms in motif_onsets):
                    remove_ids.add(int(ev_i))

        for rel_start, dur, rel_pitch, vel0 in hook_cell:
            st_abs = target_start + float(rel_start)
            # Preserve interval contour for hook-identity scoring (audit window).
            pitch = int(first_pitch) + int(transpose) + int(rel_pitch)
            pitch = int(max(48, min(96, int(pitch))))
            vel = int(max(48, min(118, round(float(vel0) * (0.90 + 0.14 * s)))))
            inserted.append((2, int(pitch), int(vel), float(st_abs), float(dur), [int(pitch)]))
        aligned += 1

    if remove_ids or inserted:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
        out.extend(inserted)
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "primary_emotion": str(primary),
        "source_chorus_index": int(src_idx),
        "chorus_sections_aligned": int(aligned),
        "notes_added": int(len(inserted)),
        "notes_replaced": int(len(remove_ids)),
        "strength": float(s),
    }


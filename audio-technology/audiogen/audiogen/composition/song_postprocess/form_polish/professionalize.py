# composition/song_postprocess/form_polish/professionalize.py
# Whole-song "professionalizer" pass: the largest single pass in form_polish,
# nudging register centers, phrase-end chord tones, and hook fragments toward
# a more polished, single-take feel.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .._common import (
    Event,
    _build_chord_windows,
    _clamp_lead_pitch,
    _lead_between,
    _lead_pitch,
    _primary_register_center_offset,
    _reharmonize_inserted_lead_pitch,
    _section_starts,
)


def professionalize_song_form(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    strength: float = 0.70,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final whole-song polish for more authored song form.

    This pass is intentionally conservative and deterministic. It does not
    invent new harmony; it shapes the stitched timeline so repeated roles feel
    developed, hooks sit in a stronger register, and intro/outro can quote the
    hook instead of sounding unrelated.
    """

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"enabled": False, "strength": 0.0}

    starts = _section_starts(section_bars, beats_per_bar=bpb)
    roles = [str(r or "").strip().lower() for r in list(section_roles or [])]
    n = min(len(starts), len(roles), len(section_bars))
    if n <= 0:
        return out, {"enabled": False}
    chord_windows = _build_chord_windows(out)

    ends: List[float] = []
    for i in range(n):
        ends.append(float(starts[i]) + float(int(section_bars[i])) * bpb)

    role_counts_seen: Dict[str, int] = {}
    role_occurrence: List[int] = []
    for role in roles[:n]:
        role_counts_seen[role] = int(role_counts_seen.get(role, 0)) + 1
        role_occurrence.append(int(role_counts_seen[role]))

    role_total_counts: Dict[str, int] = {}
    for role in roles[:n]:
        role_total_counts[role] = int(role_total_counts.get(role, 0)) + 1

    reg_offset = _primary_register_center_offset(str(primary_emotion or ""))
    target_centers = {
        "intro": 62 + reg_offset,
        "a": 65 + reg_offset,
        "verse": 65 + reg_offset,
        "pre_chorus": 68 + reg_offset,
        "b": 72 + reg_offset,
        "chorus": 72 + reg_offset,
        "hook": 72 + reg_offset,
        "tag": 73 + reg_offset,
        "a_prime": 67 + reg_offset,
        "outro": 61 + reg_offset,
    }
    base_role_vel = {
        "intro": 0.84,
        "a": 0.92,
        "verse": 0.92,
        "pre_chorus": 1.00,
        "b": 1.08,
        "chorus": 1.08,
        "hook": 1.08,
        "tag": 1.10,
        "a_prime": 0.96,
        "outro": 0.78,
    }
    if str(primary_emotion or "").strip():
        try:
            from composition.section_planner.section_dynamics_stage import (
                apply_tension_arc_to_professionalizer_velocities,
            )

            base_role_vel = apply_tension_arc_to_professionalizer_velocities(
                base_role_vel,
                emotion_name=str(primary_emotion),
            )
        except Exception:
            pass

    register_shifts = 0
    velocity_scaled = 0
    thinned = 0
    remove_ids: set[int] = set()
    replace: Dict[int, Tuple] = {}

    def _section_index_for_start(st: float) -> Optional[int]:
        for j in range(n):
            if float(starts[j]) - 1e-6 <= float(st) < float(ends[j]) - 1e-6:
                return int(j)
        return None

    lead_medians: Dict[int, float] = {}
    for j in range(n):
        leads = _lead_between(out, starts[j], ends[j])
        pitches = [_lead_pitch(ev) for ev in leads]
        ints = sorted(int(p) for p in pitches if p is not None)
        if ints:
            lead_medians[j] = float(ints[len(ints) // 2])

    section_shift: Dict[int, int] = {}
    for j, med in lead_medians.items():
        role = roles[j]
        target = int(target_centers.get(role, 66))
        raw = float(target) - float(med)
        shift = int(round(raw / 12.0)) * 12
        shift = max(-12, min(12, int(shift)))
        if abs(raw) < 7.0:
            shift = 0
        if shift:
            section_shift[int(j)] = int(shift)

    # Texture thinning: when a verse/intro/outro lead is active, remove a few
    # weak arp/counter hits in the same phrase window so the topline owns focus.
    sparse_roles = {"intro", "a", "verse", "outro"}
    for ev_i, ev in enumerate(out):
        if not ev or len(ev) != 6:
            continue
        try:
            ch = int(ev[0])
            st = float(ev[3])
            dur = float(ev[4])
            vel0 = int(ev[2])
        except Exception:
            continue
        sec = _section_index_for_start(st)
        if sec is None:
            continue
        role = roles[sec]
        occ = role_occurrence[sec] if sec < len(role_occurrence) else 1
        total_for_role = max(1, int(role_total_counts.get(role, 1)))

        role_mult = float(base_role_vel.get(role, 1.0))
        if role in {"b", "chorus", "hook", "tag"} and occ >= 2:
            role_mult += float(0.04 * min(3, occ - 1))
        if sec == n - 1 and role in {"b", "chorus", "hook", "tag", "outro"}:
            role_mult += 0.03
        if role == "outro":
            role_mult -= 0.04 * max(0, total_for_role - occ)

        # Apply only part of the multiplier so the pass polishes, not remixes.
        mult = 1.0 + (float(role_mult) - 1.0) * float(s)

        notes = ev[5]
        midi = ev[1]
        notes_out = list(notes) if isinstance(notes, list) else notes
        midi_out = midi
        if ch == 2 and sec in section_shift:
            try:
                p = _lead_pitch(ev)
                if p is not None:
                    p2 = _clamp_lead_pitch(int(p) + int(section_shift[sec]))
                    midi_out = int(p2)
                    notes_out = [int(p2)]
                    register_shifts += 1
            except Exception:
                pass

        if ch in {0, 1, 2, 3, 4, 5}:
            # Lead/bass/chords follow the arc more strongly; decorative layers less.
            layer_weight = {0: 0.90, 1: 0.78, 2: 1.00, 3: 0.55, 4: 0.42, 5: 0.58}.get(ch, 0.65)
            vm = 1.0 + (float(mult) - 1.0) * float(layer_weight)
            vel = int(max(1, min(127, round(float(vel0) * vm))))
            if vel != vel0:
                velocity_scaled += 1
        else:
            vel = vel0

        if ch in {3, 5} and role in sparse_roles and s >= 0.45:
            local = float(st) - float(starts[sec])
            # Remove occasional offbeat decorations in sparse roles, especially
            # after the first verse statement has established the part.
            if local < min(2.0 * bpb, 8.0) and (round(local * 2.0) % 2) == 1:
                if occ <= 1 or role in {"intro", "outro"}:
                    remove_ids.add(int(ev_i))
                    thinned += 1
                    continue

        replace[int(ev_i)] = (ch, midi_out, vel, st, dur, notes_out)

    if replace:
        out = [replace.get(i, ev) for i, ev in enumerate(out)]

    inserted: List[Tuple] = []

    def _hook_source() -> Optional[Tuple[int, List[Tuple]]]:
        for j in range(n):
            if roles[j] in {"b", "chorus", "hook"}:
                leads = _lead_between(out, starts[j], starts[j] + min(2.0 * bpb, 8.0))
                if len(leads) >= 3:
                    return int(j), leads[: min(4, len(leads))]
        return None

    hook = _hook_source()
    hook_fragments = 0
    if hook is not None:
        src_idx, motif = hook
        src_start = starts[src_idx]
        first = _lead_pitch(motif[0])
        motif_rows: List[Tuple[float, float, int, int]] = []
        if first is not None:
            for ev in motif[:3]:
                p = _lead_pitch(ev)
                if p is None:
                    continue
                try:
                    motif_rows.append((float(ev[3]) - float(src_start), float(ev[4]), int(p) - int(first), int(ev[2])))
                except Exception:
                    continue
        for j in range(n):
            role = roles[j]
            if role not in {"intro", "outro"} or len(motif_rows) < 2:
                continue
            target_start = starts[j]
            existing = _lead_between(out, target_start, target_start + min(1.5 * bpb, 6.0))
            if existing and role == "intro":
                continue
            anchor = 60 if role == "intro" else 57
            if existing:
                p0 = _lead_pitch(existing[0])
                if p0 is not None:
                    anchor = int(p0)
                    for ev_i, ev in enumerate(out):
                        if _lead_pitch(ev) is None:
                            continue
                        try:
                            st0 = float(ev[3])
                        except Exception:
                            continue
                        if target_start - 1e-6 <= st0 < target_start + min(1.5 * bpb, 6.0):
                            remove_ids.add(int(ev_i))
            for rel, dur, dp, vel0 in motif_rows[:2 if role == "outro" else 3]:
                st_abs = float(target_start) + max(0.0, float(rel))
                dur_out = min(float(dur), 1.5)
                pitch = _reharmonize_inserted_lead_pitch(
                    int(anchor) + int(dp),
                    start_beat=float(st_abs),
                    duration_beats=float(dur_out),
                    chord_windows=chord_windows,
                    beats_per_bar=float(bpb),
                )
                vel = int(max(38, min(104, round(float(vel0) * (0.58 if role == "intro" else 0.50)))))
                inserted.append((2, pitch, vel, float(st_abs), float(dur_out), [pitch]))
                hook_fragments += 1

    if remove_ids or inserted:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
        out.extend(inserted)

    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    return out, {
        "enabled": True,
        "strength": float(s),
        "primary_emotion": str(primary_emotion or ""),
        "register_center_offset": int(reg_offset),
        "register_shifted_notes": int(register_shifts),
        "velocity_scaled_events": int(velocity_scaled),
        "texture_thinned_events": int(thinned),
        "hook_fragment_notes": int(hook_fragments),
        "removed_events": int(len(remove_ids)),
        "inserted_events": int(len(inserted)),
        "section_shift_semitones": {int(k): int(v) for k, v in section_shift.items()},
    }


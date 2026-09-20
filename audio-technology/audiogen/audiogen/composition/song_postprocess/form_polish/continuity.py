# composition/song_postprocess/form_polish/continuity.py
# Cross-section continuity: melodic pickups spanning section boundaries, and
# longer-range arrangement continuity anchors.

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from .._common import (
    Event,
    _build_chord_windows,
    _lead_pitch,
    _reharmonize_inserted_lead_pitch,
    _section_starts,
)


def add_section_boundary_melodic_pickups(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float = 4.0,
    strength: float = 0.72,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Add restrained lead pickups at full-song section boundaries.

    Section generation already writes local handoff gestures. This pass has the
    global timeline, so it can aim the outgoing pickup directly at the next
    section's opening melody note.
    """

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"added_pickups": 0, "boundaries_considered": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    s = max(0.0, min(1.0, float(strength)))
    if s <= 1e-6:
        return out, {"added_pickups": 0, "boundaries_considered": 0}
    chord_windows = _build_chord_windows(out)

    starts: List[float] = []
    acc = 0.0
    for bars in list(section_bars or []):
        starts.append(float(acc))
        try:
            acc += float(int(bars)) * bpb
        except Exception:
            acc += bpb

    lead_events = sorted(
        [tuple(ev) for ev in out if _lead_pitch(ev) is not None],
        key=lambda ev: float(ev[3]),
    )

    def _lead_between(start: float, end: float) -> List[Tuple]:
        rows = []
        for ev in lead_events:
            try:
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if st < float(end) - 1e-6 and (st + dur) > float(start) + 1e-6:
                rows.append(ev)
        return rows

    target_roles = {"a", "pre_chorus", "b", "chorus", "hook", "tag", "a_prime"}
    added = 0
    considered = 0
    inserted: List[Tuple] = []
    for idx in range(1, min(len(starts), len(section_roles))):
        role = str(section_roles[idx] or "").strip().lower()
        if role not in target_roles:
            continue
        boundary = float(starts[idx])
        considered += 1

        next_leads = _lead_between(boundary, boundary + min(2.0 * bpb, 2.5))
        if not next_leads:
            continue
        target_ev = next_leads[0]
        target_pitch = _lead_pitch(target_ev)
        if target_pitch is None:
            continue

        # If the outgoing phrase already has enough lead activity, leave it alone.
        outgoing = _lead_between(boundary - 1.25, boundary)
        if len(outgoing) >= 2:
            continue

        prev_leads = [ev for ev in lead_events if float(ev[3]) < boundary - 1e-6]
        prev_pitch = _lead_pitch(prev_leads[-1]) if prev_leads else None
        direction = 1
        if prev_pitch is not None and int(prev_pitch) > int(target_pitch):
            direction = -1

        count = 2 if (role in {"b", "chorus", "hook", "tag"} and s >= 0.45) else 1
        if role == "pre_chorus" and s >= 0.75:
            count = 2
        starts_local = [boundary - 1.0, boundary - 0.5] if count >= 2 else [boundary - 0.5]
        offsets = [2, 1] if count >= 2 else [1]
        try:
            base_vel = int(target_ev[2])
        except Exception:
            base_vel = 82
        vel = int(max(45, min(112, round(float(base_vel) * (0.72 + 0.20 * s)))))

        for st, off in zip(starts_local, offsets):
            if st < 0.0:
                continue
            if _lead_between(st - 0.04, st + 0.40):
                continue
            pitch = _reharmonize_inserted_lead_pitch(
                int(target_pitch) - int(direction) * int(off),
                start_beat=float(st),
                duration_beats=0.36 if count >= 2 else 0.42,
                chord_windows=chord_windows,
                beats_per_bar=float(bpb),
                force=True,
            )
            dur = 0.36 if count >= 2 else 0.42
            inserted.append((2, int(pitch), int(vel), float(st), float(dur), [int(pitch)]))
            added += 1

    if inserted:
        out.extend(inserted)
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "added_pickups": int(added),
        "boundaries_considered": int(considered),
        "strength": float(s),
    }


def add_arrangement_continuity_anchors(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    beats_per_bar: float = 4.0,
    strength: float = 0.76,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Add simple whole-song arrangement anchors at section boundaries.

    This pass is intentionally conservative:
    - reinforce important section downbeats with a held chord/bass anchor
    - thin early decorative motion when a big chorus drops back to a verse-like role

    The purpose is not to change harmony, only to make the stitched arrangement
    read more like one produced song instead of adjacent sections.
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
    if n <= 1:
        return out, {"enabled": False, "strength": float(s)}

    out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))
    inserted: List[Tuple] = []
    remove_ids: set[int] = set()
    chord_anchors_added = 0
    bass_anchors_added = 0
    release_thins = 0
    entry_thins = 0

    sectionish_roles = {"a", "verse", "pre_chorus", "b", "chorus", "hook", "tag", "a_prime"}
    chorusish_roles = {"b", "chorus", "hook", "tag"}
    verseish_roles = {"a", "verse", "a_prime"}

    def _chord_events_between(start: float, end: float) -> List[Tuple]:
        rows: List[Tuple] = []
        for ev in out:
            try:
                if int(ev[0]) != 1:
                    continue
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if st < float(end) - 1e-6 and (st + dur) > float(start) + 1e-6:
                rows.append(tuple(ev))
        return rows

    def _bass_events_between(start: float, end: float) -> List[Tuple]:
        rows: List[Tuple] = []
        for ev in out:
            try:
                if int(ev[0]) != 0:
                    continue
                st = float(ev[3])
                dur = float(ev[4])
            except Exception:
                continue
            if st < float(end) - 1e-6 and (st + dur) > float(start) + 1e-6:
                rows.append(tuple(ev))
        return rows

    def _has_fresh_onset(ch: int, start: float, window: float) -> bool:
        for ev in out:
            try:
                if int(ev[0]) != int(ch):
                    continue
                st = float(ev[3])
            except Exception:
                continue
            if float(start) - 1e-6 <= st <= float(start) + float(window):
                return True
        return False

    for idx in range(1, n):
        role = roles[idx]
        prev_role = roles[idx - 1]
        if role not in sectionish_roles:
            continue
        sec_start = float(starts[idx])

        chord_refs = _chord_events_between(sec_start, sec_start + bpb)
        bass_refs = _bass_events_between(sec_start, sec_start + bpb)
        chord_notes: List[int] = []
        bass_pitch: Optional[int] = None

        if chord_refs:
            notes = chord_refs[0][5]
            if isinstance(notes, list):
                chord_notes = [int(n) for n in notes if isinstance(n, int)]
        if bass_refs:
            try:
                bass_pitch = int(bass_refs[0][1])
            except Exception:
                notes = bass_refs[0][5]
                if isinstance(notes, list) and notes:
                    try:
                        bass_pitch = int(notes[0])
                    except Exception:
                        bass_pitch = None

        if chord_notes and not _has_fresh_onset(1, sec_start, 0.10):
            chord_dur = 2.0 if role in chorusish_roles else (1.5 if role == "pre_chorus" else 1.0)
            chord_vel = 72 if role in chorusish_roles else (66 if role == "pre_chorus" else 62)
            chord_vel = int(max(40, min(100, round(float(chord_vel) * (0.90 + 0.18 * s)))))
            inserted.append((1, 0, int(chord_vel), float(sec_start), float(chord_dur), list(chord_notes)))
            chord_anchors_added += 1

        if bass_pitch is not None and role in {"pre_chorus", "b", "chorus", "hook", "tag"} and not _has_fresh_onset(0, sec_start, 0.06):
            bass_dur = 1.0 if role == "pre_chorus" else 2.0
            bass_vel = 60 if role == "pre_chorus" else 66
            bass_vel = int(max(36, min(96, round(float(bass_vel) * (0.90 + 0.18 * s)))))
            inserted.append((0, int(bass_pitch), int(bass_vel), float(sec_start), float(bass_dur), [int(bass_pitch)]))
            bass_anchors_added += 1

        if prev_role in chorusish_roles and role in verseish_roles and s >= 0.45:
            for ev_i, ev in enumerate(out):
                try:
                    ch = int(ev[0])
                    st = float(ev[3])
                except Exception:
                    continue
                if ch not in {3, 5}:
                    continue
                if not (float(sec_start) + 0.10 < st < float(sec_start) + 1.00):
                    continue
                local = float(st) - float(sec_start)
                if abs(float(local) - round(float(local) * 2.0) / 2.0) > 1e-6:
                    continue
                remove_ids.add(int(ev_i))
                release_thins += 1

        # Section-start ownership:
        # - chorus-like arrivals should open with bass/chords/lead before decorative chatter
        # - verse returns should clear more space in the first bar after a big section
        for ev_i, ev in enumerate(out):
            try:
                ch = int(ev[0])
                st = float(ev[3])
            except Exception:
                continue
            if ch not in {3, 5}:
                continue
            local = float(st) - float(sec_start)
            if local < -1e-6 or local >= 1.0:
                continue
            if role in chorusish_roles and s >= 0.40:
                # Let the arrival speak first, but keep the chorus arp downbeat
                # anchor: in this system the arp is often part of the hook
                # identity, not just decorative chatter.
                if ch == 3 and abs(float(local)) <= 0.06:
                    continue
                remove_ids.add(int(ev_i))
                entry_thins += 1
            elif prev_role in chorusish_roles and role in verseish_roles and s >= 0.40 and local < 1.5:
                # Stronger verse reset after chorus: first bar should not inherit all the peak texture.
                remove_ids.add(int(ev_i))
                entry_thins += 1

    if remove_ids:
        out = [ev for i, ev in enumerate(out) if int(i) not in remove_ids]
    if inserted:
        out.extend(inserted)
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "strength": float(s),
        "chord_anchors_added": int(chord_anchors_added),
        "bass_anchors_added": int(bass_anchors_added),
        "release_thins": int(release_thins),
        "entry_thins": int(entry_thins),
        "inserted_events": int(len(inserted)),
        "removed_events": int(len(remove_ids)),
    }


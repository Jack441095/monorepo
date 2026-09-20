"""Song postprocess: scale_guards."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple


from ._common import (
    Event,
    _active_chord_pcs_at,
    _build_chord_windows,
    _clamp_lead_pitch,
    _emotion_scale_pcs_for_section,
    _lead_pitch,
    _nearest_pitch_for_pcs,
    _scale_emotion_name_for_section,
    _section_starts,
    _snap_inserted_pitch_to_section_scale,
)



def anchor_strongbeat_lead_to_chords(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
    max_move_semitones: int = 2,
    anchor_long_notes: bool = True,
    anchor_phrase_starts: bool = True,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Nudge strong-beat lead notes onto active chord tones without rewriting motifs."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_anchored": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(len(starts), len(section_bars), len(section_roots or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "notes_anchored": 0}

    ends = [float(starts[i]) + float(int(section_bars[i])) * bpb for i in range(n)]
    chord_windows = _build_chord_windows(out)
    if not chord_windows:
        return out, {"enabled": True, "notes_anchored": 0}
    scale_by_section = [
        _emotion_scale_pcs_for_section(
            emotion_name=_scale_emotion_name_for_section(
                section_emotions=section_emotions,
                section_index=int(i),
                primary_emotion=str(primary_emotion or ""),
            ),
            root_note=int(list(section_roots)[i]),
        )
        for i in range(n)
    ]

    def _section_for_start(st: float) -> Optional[int]:
        for sec_i in range(n):
            if float(starts[sec_i]) - 1e-6 <= float(st) < float(ends[sec_i]) - 1e-6:
                return int(sec_i)
        return None

    def _is_strongbeat(st: float) -> bool:
        local = float(st) % bpb
        return abs(local - 0.0) <= 0.08 or abs(local - 2.0) <= 0.08

    def _is_phrase_start(sec_i: int, st: float) -> bool:
        if not bool(anchor_phrase_starts):
            return False
        try:
            local = max(0.0, float(st) - float(starts[sec_i]))
            phrase = float(2.0 * bpb)
            return abs((local % phrase) - 0.0) <= 0.08
        except Exception:
            return False

    replaced: Dict[int, Tuple] = {}
    anchored = 0
    sections_touched: set[int] = set()
    max_move = max(1, min(5, int(max_move_semitones or 2)))
    for i, ev in enumerate(out):
        p = _lead_pitch(ev)
        if p is None:
            continue
        try:
            st = float(ev[3])
            dur = float(ev[4])
        except Exception:
            continue
        sec = _section_for_start(float(st))
        if sec is None:
            continue
        structural = _is_strongbeat(float(st)) or _is_phrase_start(int(sec), float(st))
        long_note = bool(anchor_long_notes) and float(dur) >= 0.75 - 1e-9
        if not (structural or long_note):
            continue
        chord_pcs = _active_chord_pcs_at(chord_windows, float(st), beats_per_bar=bpb)
        if not chord_pcs or int(p) % 12 in chord_pcs:
            continue
        scale_pcs = set(scale_by_section[sec] or set())
        target_pcs = set(int(pc) % 12 for pc in chord_pcs)
        if scale_pcs:
            in_scale = {int(pc) for pc in target_pcs if int(pc) in scale_pcs}
            target_pcs = set(in_scale or target_pcs)
        p2 = _nearest_pitch_for_pcs(int(p), set(target_pcs))
        p2 = _clamp_lead_pitch(int(p2))
        allowed_move = max_move + (1 if bool(structural) and float(dur) >= 0.5 else 0)
        if abs(int(p2) - int(p)) > int(allowed_move):
            continue
        replaced[int(i)] = (2, int(p2), int(ev[2]), float(st), float(dur), [int(p2)])
        anchored += 1
        sections_touched.add(int(sec))

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "notes_anchored": int(anchored),
        "sections_touched": int(len(sections_touched)),
    }


def snap_lead_to_section_scales(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final guardrail: keep late whole-song melody edits inside section scales."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_snapped": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(len(starts), len(section_bars), len(section_roots or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "notes_snapped": 0}

    try:
        from data.emotion_aliases import canonical_emotion_name

        primary_name = canonical_emotion_name(str(primary_emotion or ""))
    except Exception:
        primary_name = str(primary_emotion or "").strip().lower()

    ends = [float(starts[i]) + float(int(section_bars[i])) * bpb for i in range(n)]
    scale_by_section = []
    for i in range(n):
        emo_for_scale = primary_name if primary_name else str(list(section_emotions)[i])
        scale_by_section.append(
            _emotion_scale_pcs_for_section(
                emotion_name=str(emo_for_scale),
                root_note=int(list(section_roots)[i]),
            )
        )
    chord_windows = _build_chord_windows(out)

    def _section_for_start(st: float) -> Optional[int]:
        for i in range(n):
            if float(starts[i]) - 1e-6 <= float(st) < float(ends[i]) - 1e-6:
                return int(i)
        return None

    replaced: Dict[int, Tuple] = {}
    snapped = 0
    for i, ev in enumerate(out):
        p = _lead_pitch(ev)
        if p is None:
            continue
        try:
            st = float(ev[3])
            dur = float(ev[4])
        except Exception:
            continue
        sec = _section_for_start(float(st))
        if sec is None:
            continue
        scale_pcs = set(scale_by_section[sec] or set())
        if not scale_pcs or int(p) % 12 in scale_pcs:
            continue
        chord_pcs = _active_chord_pcs_at(chord_windows, float(st), beats_per_bar=float(bpb))
        p2 = _snap_inserted_pitch_to_section_scale(int(p), scale_pcs=set(scale_pcs), chord_pcs=set(chord_pcs))
        if int(p2) == int(p):
            continue
        replaced[int(i)] = (2, int(p2), int(ev[2]), float(st), float(dur), [int(p2)])
        snapped += 1

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {"enabled": True, "notes_snapped": int(snapped)}


def snap_song_notes_to_section_scales(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    primary_emotion: str = "",
    beats_per_bar: float = 4.0,
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final safety pass: keep every pitched arrangement layer inside the active section scale."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_snapped": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(len(starts), len(section_bars), len(section_roots or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "notes_snapped": 0}

    ends = [float(starts[i]) + float(int(section_bars[i])) * bpb for i in range(n)]
    scale_by_section = []
    for i in range(n):
        scale_by_section.append(
            _emotion_scale_pcs_for_section(
                emotion_name=_scale_emotion_name_for_section(
                    section_emotions=section_emotions,
                    section_index=int(i),
                    primary_emotion=str(primary_emotion or ""),
                ),
                root_note=int(list(section_roots)[i]),
            )
        )

    def _section_for_start(st: float) -> Optional[int]:
        for sec_i in range(n):
            if float(starts[sec_i]) - 1e-6 <= float(st) < float(ends[sec_i]) - 1e-6:
                return int(sec_i)
        return None

    replaced: Dict[int, Tuple] = {}
    snapped = 0
    sections_touched: set[int] = set()
    for i, ev in enumerate(out):
        try:
            ch = int(ev[0])
            st = float(ev[3])
            notes = list(ev[5]) if isinstance(ev[5], list) else []
        except Exception:
            continue
        if not notes:
            continue
        sec = _section_for_start(float(st))
        if sec is None:
            continue
        scale_pcs = set(scale_by_section[sec] or set())
        if not scale_pcs:
            continue
        new_notes: List[int] = []
        changed = False
        for note in notes:
            try:
                p = int(note)
            except Exception:
                continue
            if int(p) % 12 in scale_pcs:
                new_notes.append(int(p))
                continue
            p2 = _snap_inserted_pitch_to_section_scale(int(p), scale_pcs=set(scale_pcs), chord_pcs=set())
            new_notes.append(int(p2))
            if int(p2) != int(p):
                changed = True
                snapped += 1
        if not changed or not new_notes:
            continue
        midi_field = int(new_notes[0]) if int(ch) in {0, 2, 3, 5} else ev[1]
        replaced[int(i)] = (int(ch), midi_field, int(ev[2]), float(ev[3]), float(ev[4]), list(new_notes))
        sections_touched.add(int(sec))

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {
        "enabled": True,
        "notes_snapped": int(snapped),
        "sections_touched": int(len(sections_touched)),
        "primary_emotion": str(primary_emotion or ""),
    }


# Phase-C audit: sparse reflective melodies miss phrase-end chord-tone landings.
_REFLECTIVE_PHRASE_END_PRIMARIES = frozenset(
    {"love", "caring", "relief", "sadness", "grief", "remorse", "disappointment"}
)
_LOVE_PHRASE_END_PRIMARY = "love"


def repair_song_phrase_end_chord_tones(
    events: Sequence[Event],
    *,
    section_bars: Sequence[int],
    section_roles: Sequence[str],
    section_roots: Sequence[int],
    section_emotions: Sequence[str],
    section_phrase_spans: Optional[Sequence[Dict[str, Any]]] = None,
    beats_per_bar: float = 4.0,
    phrase_length_bars: int = 4,
    eps_beats: float = 1.15,
    primary_emotion: str = "",
) -> Tuple[List[Tuple], Dict[str, Any]]:
    """Final whole-song cadence guard for phrase-ending lead notes."""

    out = [tuple(ev) for ev in list(events or []) if ev and len(ev) == 6]
    if not out or not section_bars:
        return out, {"enabled": False, "notes_repaired": 0}

    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    phrase_len = max(2, min(8, int(phrase_length_bars or 4)))
    eps = max(0.25, min(1.5, float(eps_beats)))
    primary = str(primary_emotion or "").strip().lower()
    if primary in _REFLECTIVE_PHRASE_END_PRIMARIES:
        eps = min(float(eps), 0.85)
    if primary == _LOVE_PHRASE_END_PRIMARY:
        eps = min(float(eps), 0.68)
    if primary == _LOVE_PHRASE_END_PRIMARY:
        cadence_gap = max(0.35, float(eps) * 0.48)
    elif primary in _REFLECTIVE_PHRASE_END_PRIMARIES:
        cadence_gap = max(0.45, float(eps) * 0.65)
    else:
        cadence_gap = max(0.55, float(eps) * 0.75)
    cadence_insert_dur = 0.54 if primary == _LOVE_PHRASE_END_PRIMARY else 0.46
    cadence_st_offset = 0.45 if primary == _LOVE_PHRASE_END_PRIMARY else 0.50
    starts = _section_starts(section_bars, beats_per_bar=bpb)
    n = min(len(starts), len(section_bars), len(section_roles or []), len(section_roots or []), len(section_emotions or []))
    if n <= 0:
        return out, {"enabled": False, "notes_repaired": 0}

    chord_windows = _build_chord_windows(out)
    lead_indices = [
        i for i, ev in enumerate(out)
        if isinstance(ev, tuple) and len(ev) == 6 and _lead_pitch(ev) is not None
    ]
    lead_indices.sort(key=lambda i: float(out[i][3]))
    if not lead_indices:
        return out, {"enabled": True, "notes_repaired": 0}

    scale_by_section = [
        _emotion_scale_pcs_for_section(
            emotion_name=str(list(section_emotions)[i]),
            root_note=int(list(section_roots)[i]),
        )
        for i in range(n)
    ]
    phrase_ends_by_section: Dict[int, List[float]] = {}
    for span in list(section_phrase_spans or []):
        if not isinstance(span, dict):
            continue
        try:
            sec_idx = int(span.get("section_index", -1))
            end_abs = float(span.get("absolute_end_beats", span.get("end_beats")))
        except Exception:
            continue
        if not (0 <= int(sec_idx) < int(n)):
            continue
        sec_start0 = float(starts[int(sec_idx)])
        sec_end0 = sec_start0 + float(int(section_bars[int(sec_idx)])) * bpb
        if sec_start0 - 1e-6 < float(end_abs) <= sec_end0 + 1e-6:
            phrase_ends_by_section.setdefault(int(sec_idx), []).append(float(end_abs))

    def _neighbor_pitch(sorted_pos: int, offset: int) -> Optional[int]:
        j = int(sorted_pos) + int(offset)
        if not (0 <= j < len(lead_indices)):
            return None
        return _lead_pitch(out[lead_indices[j]])

    def _nearest_for_pcs(cur: int, pcs: set[int], prev_pitch: Optional[int], next_pitch: Optional[int]) -> int:
        cands: List[Tuple[float, int]] = []
        for cand in range(int(cur) - 18, int(cur) + 19):
            if int(cand) % 12 not in pcs:
                continue
            try:
                c2 = _clamp_lead_pitch(int(cand))
            except Exception:
                c2 = int(cand)
            move = abs(int(c2) - int(cur))
            cost = float(move)
            if prev_pitch is not None:
                cost += max(0, abs(int(c2) - int(prev_pitch)) - 7) * 2.4
            if next_pitch is not None:
                cost += max(0, abs(int(next_pitch) - int(c2)) - 7) * 1.8
            cands.append((float(cost), int(c2)))
        if not cands:
            return int(cur)
        cands.sort(key=lambda item: (float(item[0]), abs(int(item[1]) - int(cur))))
        return int(cands[0][1])

    repaired = 0
    inserted: List[Tuple] = []
    replaced: Dict[int, Tuple] = {}
    for sec in range(n):
        role = str(list(section_roles)[sec] or "").strip().lower()
        root_pc = int(list(section_roots)[sec]) % 12
        sec_start = float(starts[sec])
        bars = max(1, int(section_bars[sec]))
        scale_pcs = set(scale_by_section[sec] or set())
        target_ends: List[float] = []
        for bar in range(bars):
            if ((int(bar) + 1) % int(phrase_len)) == 0 or int(bar) == int(bars) - 1:
                target_ends.append(float(sec_start) + float(bar + 1) * bpb)
        target_ends.extend(float(x) for x in phrase_ends_by_section.get(int(sec), []))
        # De-dupe endpoints so actual phrase spans and 4-bar fallbacks do not double-insert.
        seen_ends = set()
        deduped_ends: List[float] = []
        for end0 in sorted(target_ends):
            key = int(round(float(end0) * 1000.0))
            if key in seen_ends:
                continue
            seen_ends.add(key)
            deduped_ends.append(float(end0))

        for phrase_end in deduped_ends:
            rel_bar = int(max(0, min(int(bars) - 1, int((float(phrase_end) - float(sec_start) - 1e-6) // bpb))))
            bar_start = float(sec_start) + float(rel_bar) * bpb

            cand_pos: Optional[int] = None
            cand_start = -1.0
            fallback_pos: Optional[int] = None
            fallback_start = -1.0
            for pos, idx in enumerate(lead_indices):
                ev = out[idx]
                try:
                    st = float(ev[3])
                    dur = float(ev[4])
                except Exception:
                    continue
                if st < bar_start - 1e-6 or st >= float(phrase_end) + 1e-6:
                    continue
                if st >= fallback_start:
                    fallback_start = st
                    fallback_pos = pos
                if st + dur < float(phrase_end) - eps:
                    continue
                if st >= cand_start:
                    cand_start = st
                    cand_pos = pos
            if cand_pos is None:
                cand_pos = fallback_pos
            if cand_pos is None:
                pcs0 = _active_chord_pcs_at(chord_windows, float(phrase_end) - 0.50, beats_per_bar=float(bpb))
                if not pcs0:
                    continue
                target_pcs0 = set(int(pc) % 12 for pc in pcs0)
                if scale_pcs:
                    in_scale0 = {int(pc) for pc in target_pcs0 if int(pc) in scale_pcs}
                    target_pcs0 = set(in_scale0 or target_pcs0)
                if role in {"b", "chorus", "hook", "tag", "outro", "ending"} and int(root_pc) in target_pcs0:
                    target_pcs0 = {int(root_pc)}
                elif role == "pre_chorus" and int(root_pc) in target_pcs0 and len(target_pcs0) > 1:
                    target_pcs0.discard(int(root_pc))
                pitch0 = _nearest_for_pcs(int(list(section_roots)[sec]) + 14, set(target_pcs0), None, None)
                st0 = max(float(bar_start), float(phrase_end) - cadence_st_offset)
                ins_vel = 70 if primary == _LOVE_PHRASE_END_PRIMARY else 68
                inserted.append((2, int(pitch0), ins_vel, float(st0), float(cadence_insert_dur), [int(pitch0)]))
                repaired += 1
                continue

            idx = lead_indices[int(cand_pos)]
            ev = out[idx]
            cur = _lead_pitch(ev)
            if cur is None:
                continue
            pcs = _active_chord_pcs_at(chord_windows, float(ev[3]), beats_per_bar=float(bpb))
            if not pcs:
                continue
            target_pcs = set(int(pc) % 12 for pc in pcs)
            if scale_pcs:
                in_scale = {int(pc) for pc in target_pcs if int(pc) in scale_pcs}
                target_pcs = set(in_scale or target_pcs)
            cadence_roles = {"b", "chorus", "hook", "tag", "outro", "ending"}
            if role in cadence_roles and int(root_pc) in target_pcs:
                target_pcs = {int(root_pc)}
            elif role == "pre_chorus" and int(root_pc) in target_pcs and len(target_pcs) > 1:
                target_pcs.discard(int(root_pc))
            if int(cur) % 12 in target_pcs:
                new_pitch = int(cur)
            else:
                new_pitch = _nearest_for_pcs(
                    int(cur),
                    set(target_pcs),
                    _neighbor_pitch(int(cand_pos), -1),
                    _neighbor_pitch(int(cand_pos), 1),
                )
            if abs(int(new_pitch) - int(cur)) <= 12 and int(new_pitch) != int(cur):
                replaced[int(idx)] = (2, int(new_pitch), int(ev[2]), float(ev[3]), float(ev[4]), [int(new_pitch)])
                repaired += 1
            try:
                st_cur = float(ev[3])
            except Exception:
                st_cur = float(phrase_end)
            # If the last phrase note lands too early, add a short chord-tone
            # cadence so phrase-end audits and the listener both hear resolution.
            if st_cur < float(phrase_end) - float(cadence_gap):
                st0 = max(float(bar_start), float(phrase_end) - cadence_st_offset)
                if abs(float(st0) - st_cur) > 0.20:
                    pcs_ins = _active_chord_pcs_at(chord_windows, float(st0), beats_per_bar=float(bpb))
                    target_ins = set(int(pc) % 12 for pc in (pcs_ins or target_pcs))
                    if scale_pcs:
                        in_scale_ins = {int(pc) for pc in target_ins if int(pc) in scale_pcs}
                        target_ins = set(in_scale_ins or target_ins)
                    if role in cadence_roles and int(root_pc) in target_ins:
                        target_ins = {int(root_pc)}
                    p_ins = _nearest_for_pcs(int(new_pitch), set(target_ins), int(new_pitch), _neighbor_pitch(int(cand_pos), 1))
                    inserted.append(
                        (2, int(p_ins), int(max(45, min(112, int(ev[2]) - 4))), float(st0), float(cadence_insert_dur), [int(p_ins)])
                    )
                    repaired += 1

    if replaced:
        out = [replaced.get(i, ev) for i, ev in enumerate(out)]
    if inserted:
        out.extend(inserted)
    if replaced or inserted:
        out.sort(key=lambda ev: (float(ev[3]), int(ev[0]) if len(ev) == 6 else 0))

    return out, {"enabled": True, "notes_repaired": int(repaired), "notes_inserted": int(len(inserted))}



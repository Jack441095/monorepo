#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


CHANNEL_NAMES = {
    0: "bass",
    1: "chords",
    2: "melody",
    3: "arp",
    4: "drone",
    5: "counter_melody",
}

CHORUS_ROLES = {"b", "chorus", "hook", "tag"}
VERSE_ROLES = {"a", "verse", "a_prime"}


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        if v is None or v == "":
            return int(default)
        return int(float(v))
    except Exception:
        return int(default)


def _note_name(midi: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    m = int(midi)
    return f"{names[m % 12]}{(m // 12) - 1}"


def _median(vals: Iterable[float], default: float = 0.0) -> float:
    xs = [float(v) for v in vals]
    return float(statistics.median(xs)) if xs else float(default)


def _mean(vals: Iterable[float], default: float = 0.0) -> float:
    xs = [float(v) for v in vals]
    return float(sum(xs) / len(xs)) if xs else float(default)


def _std(vals: Iterable[float]) -> float:
    xs = [float(v) for v in vals]
    return float(statistics.pstdev(xs)) if len(xs) > 1 else 0.0


def _percentile(vals: Iterable[float], q: float, default: float = 0.0) -> float:
    xs = sorted(float(v) for v in vals)
    if not xs:
        return float(default)
    if len(xs) == 1:
        return float(xs[0])
    pos = (len(xs) - 1) * max(0.0, min(1.0, float(q)))
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(xs[lo])
    frac = pos - lo
    return float(xs[lo] * (1.0 - frac) + xs[hi] * frac)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _interval_overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(float(a1), float(b1)) - max(float(a0), float(b0)))


def _parse_scalar(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    s = v.strip()
    if s == "":
        return ""
    low = s.lower()
    if low in {"true", "false"}:
        return low == "true"
    try:
        if "." in s:
            return float(s)
        return int(s)
    except Exception:
        return s


def _discover_input_files(input_path: Path) -> Tuple[List[Path], List[Path]]:
    p = input_path.expanduser().resolve()
    jsonl_files: List[Path] = []
    csv_files: List[Path] = []
    if p.is_file():
        if p.name.endswith(".json"):
            try:
                payload = json.loads(p.read_text(encoding="utf-8"))
                j = str(payload.get("all_note_events_jsonl", "") or "")
                if j and Path(j).is_file():
                    jsonl_files.append(Path(j).resolve())
            except Exception:
                pass
        elif p.name.endswith(".jsonl"):
            jsonl_files.append(p)
        elif p.name.endswith(".csv"):
            csv_files.append(p)
    elif p.is_dir():
        root_jsonl = p / "all_note_events.jsonl"
        root_csv = p / "all_notes.csv"
        if root_jsonl.is_file():
            jsonl_files.append(root_jsonl)
        if root_csv.is_file():
            csv_files.append(root_csv)
        for child in sorted(p.glob("**/note_events.jsonl")):
            if child.is_file():
                jsonl_files.append(child)
        for child in sorted(p.glob("**/all_notes.csv")):
            if child.is_file():
                csv_files.append(child)
    seen_j: set[str] = set()
    seen_c: set[str] = set()
    jsonl_out = []
    csv_out = []
    for f in jsonl_files:
        s = str(f.resolve())
        if s not in seen_j:
            seen_j.add(s)
            jsonl_out.append(f)
    for f in csv_files:
        s = str(f.resolve())
        if s not in seen_c:
            seen_c.add(s)
            csv_out.append(f)
    return jsonl_out, csv_out


def _normalize_event(raw: Dict[str, Any], *, source_file: Path, row_index: int) -> Dict[str, Any]:
    channel = _safe_int(raw.get("channel", raw.get("ch", -1)), -1)
    midi = _safe_int(raw.get("midi", raw.get("event_midi_field", -1)), -1)
    start = _safe_float(
        raw.get("start_beats", raw.get("start_beats_abs", raw.get("start_beats_local", raw.get("start", 0.0)))),
        0.0,
    )
    duration = _safe_float(raw.get("duration_beats", raw.get("duration", 0.0)), 0.0)
    emotion = str(raw.get("emotion", raw.get("emotion_name", "")) or "").strip().lower()
    section_role = str(raw.get("section_role", "") or "").strip().lower()
    if section_role == "b":
        section_role_norm = "chorus"
    elif section_role == "a":
        section_role_norm = "verse"
    else:
        section_role_norm = section_role
    out = dict(raw)
    out.update(
        {
            "emotion": emotion,
            "run_index": _safe_int(raw.get("run_index", 0), 0),
            "seed": _safe_int(raw.get("seed", raw.get("launch_seed", -1)), -1),
            "channel": channel,
            "channel_name": str(raw.get("channel_name", "") or CHANNEL_NAMES.get(channel, f"ch_{channel}")),
            "start_beats": start,
            "duration_beats": duration,
            "end_beats": float(start + max(0.0, duration)),
            "velocity": _safe_int(raw.get("velocity", 0), 0),
            "midi": midi,
            "note": str(raw.get("note", "") or (_note_name(midi) if midi >= 0 else "")),
            "pc": _safe_int(raw.get("pc", midi % 12 if midi >= 0 else -1), -1),
            "in_key": _safe_int(raw.get("in_key", 1), 1),
            "section_index": _safe_int(raw.get("section_index", raw.get("section", 0)), 0),
            "section_role": section_role,
            "section_role_norm": section_role_norm,
            "section_emotion": str(raw.get("section_emotion", raw.get("emotion", emotion)) or emotion).strip().lower(),
            "section_root_midi": _safe_int(raw.get("section_root_midi", raw.get("root_midi", 60)), 60),
            "source_file": str(source_file),
            "source_row": int(row_index),
        }
    )
    return out


def _finite_end(events: List[Dict[str, Any]]) -> float:
    finite = [
        float(e["end_beats"])
        for e in events
        if not (int(e.get("channel", -1)) == 4 and float(e.get("duration_beats", 0.0)) > 256.0)
    ]
    return max(finite) if finite else max((float(e["end_beats"]) for e in events), default=0.0)


def _effective_duration(ev: Dict[str, Any], *, finite_end: float) -> float:
    start = float(ev["start_beats"])
    dur = max(0.0, float(ev["duration_beats"]))
    if int(ev.get("channel", -1)) == 4 and dur > 256.0:
        return max(0.0, float(finite_end) - start)
    return dur


def _read_events(input_path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    jsonl_files, csv_files = _discover_input_files(input_path)
    warnings: List[str] = []
    events: List[Dict[str, Any]] = []

    for path in jsonl_files:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                s = line.strip()
                if not s:
                    continue
                try:
                    raw = json.loads(s)
                except Exception as exc:
                    warnings.append(f"Failed JSONL parse {path}:{i}: {exc}")
                    continue
                if not isinstance(raw, dict):
                    continue
                raw = {str(k): _parse_scalar(v) for k, v in raw.items()}
                events.append(_normalize_event(raw, source_file=path, row_index=i))

    if not events:
        for path in csv_files:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                for i, raw in enumerate(reader, start=2):
                    raw2 = {str(k): _parse_scalar(v) for k, v in dict(raw).items()}
                    events.append(_normalize_event(raw2, source_file=path, row_index=i))

    _clip_infinite_drone_events(events)
    events.sort(key=lambda e: (str(e["emotion"]), int(e["run_index"]), int(e["seed"]), float(e["start_beats"]), int(e["channel"]), int(e["midi"])))
    if not events:
        warnings.append("No note events found. Use a run that contains all_note_events.jsonl or all_notes.csv.")
    return events, warnings


def _source_run_summary(input_path: Path) -> Dict[Tuple[str, int, int], Dict[str, Any]]:
    p = input_path.expanduser().resolve()
    candidates: List[Path] = []
    if p.is_dir():
        candidates.append(p / "run_summary.csv")
    elif p.is_file():
        candidates.append(p.parent / "run_summary.csv")
    out: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
    for path in candidates:
        if not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                for raw in csv.DictReader(f):
                    row = {str(k): _parse_scalar(v) for k, v in dict(raw).items()}
                    key = (
                        str(row.get("emotion", "") or "").strip().lower(),
                        _safe_int(row.get("run_index", 0), 0),
                        _safe_int(row.get("seed", -1), -1),
                    )
                    if key[0] and key[2] >= 0:
                        out[key] = row
        except Exception:
            continue
    return out


def _apply_source_run_metrics(
    run_rows: List[Dict[str, Any]],
    source_rows: Dict[Tuple[str, int, int], Dict[str, Any]],
) -> int:
    if not source_rows:
        return 0
    # These metrics are more reliable when produced during generation because
    # the generator has phrase-span metadata that plain note CSV/JSONL does not.
    generation_aware_fields = {
        "mh_phrase_end_chord_tone_frac",
        "mh_onset_chord_tone_frac",
        "mh_strongbeat_chord_tone_frac",
        "professional_quality_score",
    }
    changed = 0
    for row in run_rows:
        key = (
            str(row.get("emotion", "") or "").strip().lower(),
            _safe_int(row.get("run_index", 0), 0),
            _safe_int(row.get("seed", -1), -1),
        )
        src = source_rows.get(key)
        if not src:
            continue
        for field in generation_aware_fields:
            if field not in src:
                continue
            row[field] = _safe_float(src.get(field), _safe_float(row.get(field), 0.0))
        changed += 1
    return int(changed)


def _clip_infinite_drone_events(events: List[Dict[str, Any]]) -> None:
    for _key, evs in _group(events, ("emotion", "run_index", "seed")).items():
        finite_end = _finite_end(evs)
        for ev in evs:
            if int(ev.get("channel", -1)) != 4:
                continue
            if float(ev.get("duration_beats", 0.0)) <= 256.0:
                continue
            dur = max(0.0, float(finite_end) - float(ev.get("start_beats", 0.0)))
            ev["duration_beats"] = float(dur)
            ev["end_beats"] = float(float(ev.get("start_beats", 0.0)) + dur)


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _group(events: List[Dict[str, Any]], keys: Tuple[str, ...]) -> Dict[Tuple[Any, ...], List[Dict[str, Any]]]:
    out: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = defaultdict(list)
    for ev in events:
        out[tuple(ev.get(k) for k in keys)].append(ev)
    return out


def _active_chord_pcs(events: List[Dict[str, Any]], t: float) -> set[int]:
    pcs: set[int] = set()
    for ev in events:
        if int(ev["channel"]) != 1:
            continue
        if float(ev["start_beats"]) - 1e-6 <= float(t) < float(ev["end_beats"]) + 1e-6:
            pc = int(ev["pc"])
            if 0 <= pc <= 11:
                pcs.add(pc)
    return pcs


def _lead_metrics(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    leads = [e for e in events if int(e["channel"]) == 2 and int(e["midi"]) >= 0]
    leads.sort(key=lambda e: float(e["start_beats"]))
    pitches = [int(e["midi"]) for e in leads]
    intervals = [abs(b - a) for a, b in zip(pitches, pitches[1:])]
    repeats = sum(1 for a, b in zip(pitches, pitches[1:]) if a == b)
    strong_hits = 0
    strong_total = 0
    onset_ct = 0
    onset_total = 0
    phrase_hits = 0
    phrase_total = 0
    chords = [e for e in events if int(e["channel"]) == 1]
    for e in leads:
        t = float(e["start_beats"])
        pc = int(e["pc"])
        pcs = _active_chord_pcs(chords, t)
        if pcs:
            onset_total += 1
            onset_ct += int(pc in pcs)
            beat = t % 4.0
            if abs(beat - 0.0) <= 0.08 or abs(beat - 2.0) <= 0.08:
                strong_total += 1
                strong_hits += int(pc in pcs)

    # Phrase-end metric: use the final lead note near each 4-bar phrase end and
    # song end. This mirrors the generation audit more closely than checking for
    # notes that happen to end exactly on a barline.
    try:
        finite_end = _finite_end(events)
        bars_n = max(1, int(round(float(finite_end) / 4.0))) if finite_end > 1e-6 else 0
    except Exception:
        bars_n = 0
    phrase_end_bars = set()
    for bi in range(int(bars_n)):
        if (int(bi) % 4) == 3 or int(bi) == int(bars_n) - 1:
            phrase_end_bars.add(int(bi))
    for bi in sorted(phrase_end_bars):
        bar_start = float(bi) * 4.0
        bar_end = float(bar_start) + 4.0
        last = None
        last_st = -1.0
        for e in leads:
            st = float(e["start_beats"])
            # A note starting exactly on the next bar/section boundary belongs
            # to the next phrase, not the phrase that just ended.
            if st < bar_start - 1e-6 or st >= bar_end - 1e-6:
                continue
            if st + float(e["duration_beats"]) < bar_end - 1.15:
                continue
            if st >= last_st:
                last = e
                last_st = st
        if last is None:
            continue
        pcs = _active_chord_pcs(chords, float(last["start_beats"]))
        if not pcs:
            continue
        phrase_total += 1
        phrase_hits += int(int(last["pc"]) in pcs)
    return {
        "lead_note_count": len(leads),
        "lead_pitch_min": min(pitches) if pitches else "",
        "lead_pitch_max": max(pitches) if pitches else "",
        "lead_pitch_range": (max(pitches) - min(pitches)) if pitches else 0,
        "lead_pitch_median": _median(pitches),
        "lead_abs_interval_avg": _mean(intervals),
        "lead_abs_interval_p95": _percentile(intervals, 0.95),
        "lead_max_leap": max(intervals) if intervals else 0,
        "lead_repeat_frac": float(repeats / max(1, len(pitches) - 1)),
        "mh_onset_chord_tone_frac": float(onset_ct / max(1, onset_total)),
        "mh_strongbeat_chord_tone_frac": float(strong_hits / max(1, strong_total)),
        "mh_phrase_end_chord_tone_frac": float(phrase_hits / max(1, phrase_total)),
    }


def _coverage(events: List[Dict[str, Any]], channel: int, total_beats: float, *, finite_end: float) -> float:
    rows = [e for e in events if int(e["channel"]) == int(channel)]
    return float(sum(_effective_duration(e, finite_end=float(finite_end)) for e in rows) / max(1e-9, total_beats))


def _lead_arp_overlap(events: List[Dict[str, Any]]) -> float:
    leads = [e for e in events if int(e["channel"]) == 2]
    arps = [e for e in events if int(e["channel"]) == 3]
    lead_beats = sum(max(0.0, float(e["duration_beats"])) for e in leads)
    overlap = 0.0
    for le in leads:
        a0 = float(le["start_beats"])
        a1 = float(le["end_beats"])
        for ar in arps:
            overlap += _interval_overlap(a0, a1, float(ar["start_beats"]), float(ar["end_beats"]))
    return float(overlap / max(1e-9, lead_beats))


def _run_summary(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for (emotion, run_index, seed), evs in _group(events, ("emotion", "run_index", "seed")).items():
        if not evs:
            continue
        finite_end = _finite_end(evs)
        total_beats = float(finite_end) - min(float(e["start_beats"]) for e in evs)
        lead = _lead_metrics(evs)
        note_count = len(evs)
        in_key = sum(1 for e in evs if _safe_int(e.get("in_key", 1), 1) == 1) / max(1, note_count)
        chord_onsets = len({round(float(e["start_beats"]), 6) for e in evs if int(e["channel"]) == 1})
        bars = max(1.0, total_beats / 4.0)
        overlap = _lead_arp_overlap(evs)
        lead_activity = _coverage(evs, 2, total_beats, finite_end=float(finite_end))
        arp_activity = _coverage(evs, 3, total_beats, finite_end=float(finite_end))
        chord_rate = chord_onsets / bars
        leap_score = _clamp01(1.0 - max(0.0, float(lead["lead_abs_interval_p95"]) - 5.0) / 10.0)
        repeat_score = _clamp01(1.0 - max(0.0, float(lead["lead_repeat_frac"]) - 0.08) / 0.30)
        overlap_score = _clamp01(1.0 - max(0.0, float(overlap) - 0.20) / 0.35)
        if lead_activity < 0.30:
            lead_activity_score = _clamp01(float(lead_activity) / 0.30)
        elif lead_activity <= 0.76:
            lead_activity_score = 1.0
        else:
            lead_activity_score = _clamp01(1.0 - (float(lead_activity) - 0.76) / 0.24)
        if chord_rate <= 0.0:
            chord_score = 0.0
        elif chord_rate < 0.35:
            chord_score = _clamp01(float(chord_rate) / 0.35)
        elif chord_rate <= 1.45:
            chord_score = 1.0
        else:
            chord_score = _clamp01(1.0 - (float(chord_rate) - 1.45) / 0.75)
        arp_score = _clamp01(float(arp_activity) / 0.16)
        score01 = (
            0.24 * _clamp01(in_key)
            + 0.13 * leap_score
            + 0.10 * repeat_score
            + 0.12 * overlap_score
            + 0.10 * lead_activity_score
            + 0.07 * chord_score
            + 0.08 * arp_score
            + 0.08 * _clamp01(float(lead["mh_strongbeat_chord_tone_frac"]))
            + 0.08 * _clamp01(float(lead["mh_phrase_end_chord_tone_frac"]))
        )
        row = {
            "emotion": emotion,
            "run_index": run_index,
            "seed": seed,
            "events": len(evs),
            "notes": note_count,
            "total_bars": total_beats / 4.0,
            "in_key_ratio": in_key,
            "lead_activity": lead_activity,
            "arp_activity": arp_activity,
            "lead_arp_overlap": overlap,
            "chord_change_rate_per_bar": chord_rate,
            "professional_quality_score": float(100.0 * _clamp01(score01)),
            **lead,
        }
        rows.append(row)
    rows.sort(key=lambda r: (str(r["emotion"]), -float(r["professional_quality_score"]), int(r["run_index"])))
    ranks: Dict[str, int] = defaultdict(int)
    for row in rows:
        ranks[str(row["emotion"])] += 1
        row["seed_rank_in_emotion"] = ranks[str(row["emotion"])]
    return rows


def _section_summary(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    keys = ("emotion", "run_index", "seed", "section_index", "section_role_norm")
    for key, evs in _group(events, keys).items():
        emotion, run_index, seed, section_index, role = key
        if not evs:
            continue
        start = min(float(e["start_beats"]) for e in evs)
        end = _finite_end(evs)
        bars = max(0.25, (end - start) / 4.0)
        channels = sorted({int(e["channel"]) for e in evs})
        def layer(ch: int) -> List[Dict[str, Any]]:
            return [e for e in evs if int(e["channel"]) == ch and int(e["midi"]) >= 0]
        lead = layer(2)
        arp = layer(3)
        chords = [e for e in evs if int(e["channel"]) == 1]
        row = {
            "emotion": emotion,
            "run_index": run_index,
            "seed": seed,
            "section_index": section_index,
            "section_role": role,
            "section_emotion": str(evs[0].get("section_emotion", "")),
            "section_bars_est": bars,
            "total_events": len(evs),
            "lead_note_count": len(lead),
            "lead_notes_per_bar": len(lead) / bars,
            "lead_beats_per_bar": sum(_effective_duration(e, finite_end=float(end)) for e in lead) / bars,
            "lead_coverage_ratio": sum(_effective_duration(e, finite_end=float(end)) for e in lead) / max(1e-9, bars * 4.0),
            "lead_register_median": _median(int(e["midi"]) for e in lead),
            "lead_velocity_avg": _mean(int(e["velocity"]) for e in lead),
            "arp_note_count": len(arp),
            "arp_notes_per_bar": len(arp) / bars,
            "arp_beats_per_bar": sum(_effective_duration(e, finite_end=float(end)) for e in arp) / bars,
            "arp_register_median": _median(int(e["midi"]) for e in arp),
            "arp_velocity_avg": _mean(int(e["velocity"]) for e in arp),
            "lead_minus_arp_register_median": _median(int(e["midi"]) for e in lead) - _median(int(e["midi"]) for e in arp),
            "chord_change_rate_per_bar": len({round(float(e["start_beats"]), 6) for e in chords}) / bars,
            "texture_channel_count": len(channels),
            "texture_signature": "+".join(str(c) for c in channels),
        }
        rows.append(row)
    rows.sort(key=lambda r: (str(r["emotion"]), int(r["run_index"]), int(r["section_index"])))
    return rows


def _channel_summary(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for key, evs in _group(events, ("emotion", "run_index", "seed", "channel", "channel_name")).items():
        emotion, run_index, seed, channel, channel_name = key
        mids = [int(e["midi"]) for e in evs if int(e["midi"]) >= 0]
        rows.append(
            {
                "emotion": emotion,
                "run_index": run_index,
                "seed": seed,
                "channel": channel,
                "channel_name": channel_name,
                "events": len(evs),
                "duration_beats_total": sum(_effective_duration(e, finite_end=_finite_end(evs)) for e in evs),
                "velocity_avg": _mean(int(e["velocity"]) for e in evs),
                "midi_min": min(mids) if mids else "",
                "midi_max": max(mids) if mids else "",
                "midi_median": _median(mids),
                "unique_pitch_classes": len({int(e["pc"]) for e in evs if 0 <= int(e["pc"]) <= 11}),
            }
        )
    rows.sort(key=lambda r: (str(r["emotion"]), int(r["run_index"]), int(r["channel"])))
    return rows


def _parameter_summary(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = defaultdict(lambda: {"count": 0, "numeric": [], "values": Counter()})
    for ev in events:
        for k, v in ev.items():
            s = stats[str(k)]
            s["count"] += 1
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                s["numeric"].append(float(v))
            else:
                s["values"][str(v)] += 1
    rows: List[Dict[str, Any]] = []
    for k, s in sorted(stats.items()):
        nums = list(s["numeric"])
        values = s["values"]
        top = ";".join(f"{val}:{cnt}" for val, cnt in values.most_common(8))
        rows.append(
            {
                "parameter": k,
                "count": int(s["count"]),
                "numeric_count": len(nums),
                "numeric_min": min(nums) if nums else "",
                "numeric_max": max(nums) if nums else "",
                "numeric_avg": _mean(nums, 0.0) if nums else "",
                "numeric_std": _std(nums) if nums else "",
                "distinct_non_numeric": len(values),
                "top_values": top,
            }
        )
    return rows


def _emotion_summary(run_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for emotion, vals in _group(run_rows, ("emotion",)).items():
        evs = vals
        def col(name: str) -> List[float]:
            return [_safe_float(v.get(name), 0.0) for v in evs]
        rows.append(
            {
                "emotion": emotion[0],
                "runs": len(evs),
                "in_key_ratio_avg": _mean(col("in_key_ratio")),
                "in_key_ratio_std": _std(col("in_key_ratio")),
                "lead_activity_avg": _mean(col("lead_activity")),
                "arp_activity_avg": _mean(col("arp_activity")),
                "lead_arp_overlap_avg": _mean(col("lead_arp_overlap")),
                "lead_abs_interval_p95_avg": _mean(col("lead_abs_interval_p95")),
                "lead_repeat_frac_avg": _mean(col("lead_repeat_frac")),
                "mh_strongbeat_chord_tone_frac_avg": _mean(col("mh_strongbeat_chord_tone_frac")),
                "mh_phrase_end_chord_tone_frac_avg": _mean(col("mh_phrase_end_chord_tone_frac")),
                "professional_quality_score_avg": _mean(col("professional_quality_score")),
                "professional_quality_score_std": _std(col("professional_quality_score")),
            }
        )
    rows.sort(key=lambda r: str(r["emotion"]))
    return rows


def _emotion_section_summary(section_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for (emotion, role), vals in _group(section_rows, ("emotion", "section_role")).items():
        def col(name: str) -> List[float]:
            return [_safe_float(v.get(name), 0.0) for v in vals]
        rows.append(
            {
                "emotion": emotion,
                "section_role": role,
                "sections": len(vals),
                "lead_notes_per_bar_avg": _mean(col("lead_notes_per_bar")),
                "lead_beats_per_bar_avg": _mean(col("lead_beats_per_bar")),
                "lead_coverage_ratio_avg": _mean(col("lead_coverage_ratio")),
                "lead_register_median_avg": _mean(col("lead_register_median")),
                "lead_velocity_avg_avg": _mean(col("lead_velocity_avg")),
                "arp_notes_per_bar_avg": _mean(col("arp_notes_per_bar")),
                "arp_beats_per_bar_avg": _mean(col("arp_beats_per_bar")),
                "arp_register_median_avg": _mean(col("arp_register_median")),
                "arp_velocity_avg_avg": _mean(col("arp_velocity_avg")),
                "lead_minus_arp_register_median_avg": _mean(col("lead_minus_arp_register_median")),
                "chord_change_rate_per_bar_avg": _mean(col("chord_change_rate_per_bar")),
                "texture_channel_count_avg": _mean(col("texture_channel_count")),
            }
        )
    rows.sort(key=lambda r: (str(r["emotion"]), str(r["section_role"])))
    return rows


def _arrangement_contrast(section_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    by_emotion = _group(section_rows, ("emotion",))
    for (emotion,), vals in by_emotion.items():
        verse = [v for v in vals if str(v["section_role"]) in VERSE_ROLES or str(v["section_role"]) == "verse"]
        chorus = [v for v in vals if str(v["section_role"]) in CHORUS_ROLES or str(v["section_role"]) == "chorus"]
        outro = [v for v in vals if str(v["section_role"]) == "outro"]
        pre = [v for v in vals if str(v["section_role"]) == "pre_chorus"]
        def avg(rows0: List[Dict[str, Any]], name: str) -> float:
            return _mean(_safe_float(r.get(name), 0.0) for r in rows0)
        flags = []
        lead_delta = avg(chorus, "lead_notes_per_bar") - avg(verse, "lead_notes_per_bar")
        arp_delta = avg(chorus, "arp_notes_per_bar") - avg(verse, "arp_notes_per_bar")
        reg_delta = avg(chorus, "lead_register_median") - avg(verse, "lead_register_median")
        if lead_delta < 0.5:
            flags.append("weak_chorus_lead_lift")
        if arp_delta < 2.0:
            flags.append("weak_chorus_arp_bed")
        if reg_delta < 5.0:
            flags.append("weak_chorus_register_lift")
        score = 100.0 - 10.0 * len(flags)
        rows.append(
            {
                "emotion": emotion,
                "verse_to_chorus_lead_notes_per_bar_delta": lead_delta,
                "verse_to_chorus_lead_beats_per_bar_delta": avg(chorus, "lead_beats_per_bar") - avg(verse, "lead_beats_per_bar"),
                "verse_to_chorus_lead_coverage_delta": avg(chorus, "lead_coverage_ratio") - avg(verse, "lead_coverage_ratio"),
                "verse_to_chorus_arp_notes_per_bar_delta": arp_delta,
                "verse_to_chorus_lead_register_delta": reg_delta,
                "intro_to_chorus_lead_velocity_delta": avg(chorus, "lead_velocity_avg") - avg([v for v in vals if str(v["section_role"]) == "intro"], "lead_velocity_avg"),
                "pre_to_chorus_chord_motion_delta": avg(chorus, "chord_change_rate_per_bar") - avg(pre, "chord_change_rate_per_bar"),
                "chorus_to_outro_lead_notes_per_bar_delta": avg(chorus, "lead_notes_per_bar") - avg(outro, "lead_notes_per_bar"),
                "texture_channel_span": max((_safe_float(v.get("texture_channel_count"), 0.0) for v in vals), default=0.0) - min((_safe_float(v.get("texture_channel_count"), 0.0) for v in vals), default=0.0),
                "contrast_issue_count": len(flags),
                "weak_contrast_flags": "|".join(flags),
                "arrangement_contrast_score": max(0.0, score),
            }
        )
    rows.sort(key=lambda r: str(r["emotion"]))
    return rows


def _write_report(path: Path, *, input_path: Path, out_dir: Path, events: List[Dict[str, Any]], run_rows: List[Dict[str, Any]], emotion_rows: List[Dict[str, Any]], contrast_rows: List[Dict[str, Any]], warnings: List[str]) -> None:
    top = sorted(run_rows, key=lambda r: (str(r["emotion"]), -float(r["professional_quality_score"])))
    lines = [
        "# Full Song Seed Audit",
        "",
        f"- Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Input: {input_path}",
        f"- Output folder: {out_dir}",
        f"- Events analysed: {len(events)}",
        f"- Runs analysed: {len(run_rows)}",
        f"- Emotions: {len({str(e.get('emotion')) for e in events})}",
        "",
        "## Files",
        "- `all_notes.csv`: every note/event with normalized fields plus raw parameters.",
        "- `all_note_events.jsonl`: every normalized event as JSON for programmatic analysis.",
        "- `run_summary.csv`: per-seed full song metrics.",
        "- `section_summary.csv`: per-section density/register/texture metrics.",
        "- `channel_summary.csv`: per-layer metrics for each seed.",
        "- `parameter_summary.csv`: every parameter/key observed and numeric distributions.",
        "- `emotion_summary.csv`: averages and variance per emotion.",
        "- `emotion_section_summary.csv`: section-role averages per emotion.",
        "- `arrangement_contrast_summary.csv`: verse/pre/chorus/outro contrast deltas.",
        "",
    ]
    if warnings:
        lines += ["## Warnings"] + [f"- {w}" for w in warnings] + [""]
    lines += ["## Top Seeds Per Emotion", ""]
    by_emotion: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in top:
        by_emotion[str(row["emotion"])].append(row)
    for emotion, vals in sorted(by_emotion.items()):
        lines += [f"### {emotion}", "seed,score,in_key,strongbeat_ct,phrase_end_ct,lead_p95,repeat,overlap"]
        for row in vals[:5]:
            lines.append(
                f"{row['seed']},{float(row['professional_quality_score']):.3f},{float(row['in_key_ratio']):.3f},"
                f"{float(row['mh_strongbeat_chord_tone_frac']):.3f},{float(row['mh_phrase_end_chord_tone_frac']):.3f},"
                f"{float(row['lead_abs_interval_p95']):.3f},{float(row['lead_repeat_frac']):.3f},{float(row['lead_arp_overlap']):.3f}"
            )
        lines.append("")
    lines += ["## Emotion Summary", ""]
    for row in emotion_rows:
        lines.append(
            f"- {row['emotion']}: score_avg={float(row['professional_quality_score_avg']):.3f}, "
            f"lead_arp_overlap_avg={float(row['lead_arp_overlap_avg']):.3f}, "
            f"lead_p95_avg={float(row['lead_abs_interval_p95_avg']):.3f}"
        )
    lines += ["", "## Arrangement Contrast", ""]
    for row in contrast_rows:
        lines.append(
            f"- {row['emotion']}: score={float(row['arrangement_contrast_score']):.3f}, "
            f"arp_delta={float(row['verse_to_chorus_arp_notes_per_bar_delta']):.3f}, "
            f"lead_register_delta={float(row['verse_to_chorus_lead_register_delta']):.3f}, "
            f"flags={row['weak_contrast_flags']}"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deep random seed audit analysis from all_note_events.jsonl or all_notes.csv.")
    parser.add_argument("input", help="Audit summary JSON, audit folder, all_note_events.jsonl, or all_notes.csv.")
    parser.add_argument(
        "--out-root",
        default="logs/current_baseline_sweep_after_fixes",
        help="Parent output directory. Default matches existing baseline sweep folder.",
    )
    parser.add_argument("--tag", default="", help="Optional suffix for output folder name.")
    args = parser.parse_args()

    input_path = Path(args.input)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{args.tag.strip()}" if str(args.tag or "").strip() else ""
    out_dir = Path(args.out_root).expanduser().resolve() / f"full_song_seed_audit_{stamp}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)

    events, warnings = _read_events(input_path)
    run_rows = _run_summary(events)
    source_metric_overrides = _apply_source_run_metrics(run_rows, _source_run_summary(input_path))
    if source_metric_overrides:
        warnings.append(
            f"Applied generation-aware run_summary.csv metric overrides for {source_metric_overrides} runs."
        )
    section_rows = _section_summary(events)
    channel_rows = _channel_summary(events)
    parameter_rows = _parameter_summary(events)
    emotion_rows = _emotion_summary(run_rows)
    emotion_section_rows = _emotion_section_summary(section_rows)
    contrast_rows = _arrangement_contrast(section_rows)

    note_fields = [
        "emotion", "run_index", "seed", "channel", "channel_name", "start_beats", "duration_beats", "end_beats",
        "velocity", "midi", "note", "pc", "in_key", "section_index", "section_role", "section_role_norm",
        "section_emotion", "section_root_midi", "source_file", "source_row", "raw_params_json",
    ]
    note_rows = []
    for ev in events:
        row = dict(ev)
        row["raw_params_json"] = json.dumps(ev, sort_keys=True)
        note_rows.append(row)
    _write_csv(out_dir / "all_notes.csv", note_rows, note_fields)
    with (out_dir / "all_note_events.jsonl").open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, sort_keys=True) + "\n")

    _write_csv(out_dir / "run_summary.csv", run_rows, list(run_rows[0].keys()) if run_rows else ["emotion"])
    _write_csv(out_dir / "section_summary.csv", section_rows, list(section_rows[0].keys()) if section_rows else ["emotion"])
    _write_csv(out_dir / "channel_summary.csv", channel_rows, list(channel_rows[0].keys()) if channel_rows else ["emotion"])
    _write_csv(out_dir / "parameter_summary.csv", parameter_rows, list(parameter_rows[0].keys()) if parameter_rows else ["parameter"])
    _write_csv(out_dir / "emotion_summary.csv", emotion_rows, list(emotion_rows[0].keys()) if emotion_rows else ["emotion"])
    _write_csv(out_dir / "emotion_section_summary.csv", emotion_section_rows, list(emotion_section_rows[0].keys()) if emotion_section_rows else ["emotion"])
    _write_csv(out_dir / "arrangement_contrast_summary.csv", contrast_rows, list(contrast_rows[0].keys()) if contrast_rows else ["emotion"])

    manifest = {
        "input": str(input_path),
        "out_dir": str(out_dir),
        "events": len(events),
        "runs": len(run_rows),
        "warnings": warnings,
        "files": sorted(p.name for p in out_dir.iterdir() if p.is_file()),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_report(
        out_dir / "report.md",
        input_path=input_path,
        out_dir=out_dir,
        events=events,
        run_rows=run_rows,
        emotion_rows=emotion_rows,
        contrast_rows=contrast_rows,
        warnings=warnings,
    )
    print(str(out_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

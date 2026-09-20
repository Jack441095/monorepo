#!/usr/bin/env python3
"""Aggregate stats from live melody training JSONL (export_live_melody_training).

Each line is one JSON object. Typical keys from generator export (see
generator.py live export): ts, emotion, section_role, phrase_contours, phrase_roles,
phrases, melody, chord_sequence, roots, beats_per_bar, accept_score.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def _iter_melody_events(row: Dict[str, Any]) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    mel = row.get("melody")
    if isinstance(mel, list):
        for item in mel:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    out.append((int(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    continue
    if out:
        return out
    phrases = row.get("phrases")
    if isinstance(phrases, list):
        for ph in phrases:
            if not isinstance(ph, list):
                continue
            for item in ph:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        out.append((int(item[0]), float(item[1])))
                    except (TypeError, ValueError):
                        continue
    return out


def _voiced_intervals(events: List[Tuple[int, float]]) -> List[int]:
    voiced = [int(d) for d, _ in events if isinstance(d, int) and int(d) >= 0]
    if len(voiced) < 2:
        return []
    return [voiced[i + 1] - voiced[i] for i in range(len(voiced) - 1)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=".cache/live_melody_training.jsonl",
        help="JSONL file path (default: .cache/live_melody_training.jsonl)",
    )
    parser.add_argument(
        "--min-accept",
        type=float,
        default=None,
        help="Skip rows with accept_score below this (Phase 2e filter).",
    )
    parser.add_argument(
        "--min-notes",
        type=int,
        default=None,
        help="Skip rows with fewer melody events than this.",
    )
    parser.add_argument(
        "--dedup",
        action="store_true",
        help="Count each unique melody (sha256 of degree/duration list) once.",
    )
    parser.add_argument(
        "--write-filtered",
        default=None,
        help="If set, write rows passing filters to this JSONL path.",
    )
    parser.add_argument(
        "--tag-counts",
        action="store_true",
        help="Print top emotion and section_role counts (when present).",
    )
    parser.add_argument(
        "--require-metadata",
        action="store_true",
        help="Fail if rows lack emotion/section_role/phrase roles+contours/chord_sequence, or chord alignment.",
    )
    args = parser.parse_args()
    p = Path(args.path)
    if not p.is_file():
        print(f"File not found: {p}")
        return 1

    try:
        from audiogen_core.config import CONFIG

        min_accept_d = float(getattr(CONFIG.composition, "melody_jsonl_retrain_min_accept_score", 0.0) or 0.0)
        min_notes_d = int(getattr(CONFIG.composition, "melody_jsonl_retrain_min_notes", 4) or 4)
    except Exception:
        min_accept_d = 0.0
        min_notes_d = 4
    min_accept = float(args.min_accept) if args.min_accept is not None else min_accept_d
    min_notes = int(args.min_notes) if args.min_notes is not None else min_notes_d

    dur_c: Counter[float] = Counter()
    iv_c: Counter[int] = Counter()
    emotion_c: Counter[str] = Counter()
    section_c: Counter[str] = Counter()
    contour_c: Counter[str] = Counter()
    phrase_role_c: Counter[str] = Counter()
    chord_token_c: Counter[str] = Counter()
    lines = 0
    lines_used = 0
    notes = 0
    rests = 0
    events_per_line: List[int] = []
    lyrical_scores: List[float] = []
    lyrical_component_sum: Dict[str, float] = {}
    lyrical_component_n: Counter[str] = Counter()
    seen: Set[str] = set()
    out_lines: List[str] = []
    meta_rows_emotion = 0
    meta_rows_section = 0
    meta_rows_contours = 0
    meta_rows_roles = 0
    meta_rows_chords = 0
    meta_rows_chord_aligned = 0

    with p.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            lines += 1
            try:
                if float(row.get("accept_score", 1.0) or 1.0) < float(min_accept):
                    continue
            except Exception:
                pass
            events = _iter_melody_events(row)
            if len(events) < int(min_notes):
                continue
            try:
                if "lyrical_score" in row:
                    ls = float(row.get("lyrical_score", 0.0) or 0.0)
                    comps = row.get("lyrical_components") if isinstance(row.get("lyrical_components"), dict) else {}
                else:
                    from ai.markov.melody.beauty import score_lyrical_melody

                    ls, comps = score_lyrical_melody(events)
                lyrical_scores.append(float(ls))
                for ck, cv in dict(comps or {}).items():
                    key = str(ck)
                    lyrical_component_sum[key] = float(lyrical_component_sum.get(key, 0.0)) + float(cv)
                    lyrical_component_n[key] += 1
            except Exception:
                pass
            if args.dedup:
                try:
                    import hashlib

                    raw = json.dumps([[int(d), float(t)] for d, t in events], separators=(",", ":"))
                    key = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                except Exception:
                    key = str(hash(tuple(events)))
                if key in seen:
                    continue
                seen.add(key)
            lines_used += 1
            events_per_line.append(len(events))
            # Metadata coverage and top counts (for dataset hygiene).
            try:
                em = str(row.get("emotion") or "").strip().lower()
            except Exception:
                em = ""
            if em:
                meta_rows_emotion += 1
            try:
                sr = str(row.get("section_role") or "").strip().lower()
            except Exception:
                sr = ""
            if sr:
                meta_rows_section += 1

            pc = row.get("phrase_contours")
            if isinstance(pc, list) and pc:
                meta_rows_contours += 1
                for c in pc:
                    cc = str(c or "").strip().lower()
                    if cc:
                        contour_c[cc] += 1
            pr = row.get("phrase_roles")
            if isinstance(pr, list) and pr:
                meta_rows_roles += 1
                for r in pr:
                    rr = str(r or "").strip().lower()
                    if rr:
                        phrase_role_c[rr] += 1
            chords = row.get("chord_sequence")
            if isinstance(chords, list) and chords:
                meta_rows_chords += 1
                for ch in chords:
                    s = str(ch or "").strip()
                    if s:
                        chord_token_c[s] += 1
                try:
                    if len(chords) == len(events):
                        meta_rows_chord_aligned += 1
                except Exception:
                    pass
            if args.tag_counts:
                try:
                    em = str(row.get("emotion") or "").strip()
                    if em:
                        emotion_c[em] += 1
                except Exception:
                    pass
                try:
                    sr = str(row.get("section_role") or "").strip()
                    if sr:
                        section_c[sr] += 1
                except Exception:
                    pass
            if args.write_filtered:
                out_lines.append(json.dumps(row, ensure_ascii=False))
            for d, du in events:
                notes += 1
                dur_c[float(du)] += 1
                if isinstance(d, int) and int(d) < 0:
                    rests += 1
            for iv in _voiced_intervals(events):
                iv_c[iv] += 1

    if args.write_filtered:
        wp = Path(str(args.write_filtered))
        wp.parent.mkdir(parents=True, exist_ok=True)
        with wp.open("w", encoding="utf-8") as wf:
            for ol in out_lines:
                wf.write(ol + "\n")

    print(f"lines: {lines}")
    print(f"lines_after_filter: {lines_used}  (min_accept={min_accept}, min_notes={min_notes}, dedup={bool(args.dedup)})")
    if events_per_line:
        mean_n = statistics.mean(events_per_line)
        med = statistics.median(events_per_line)
        print(
            f"events_per_line (melody tokens): min={min(events_per_line)}  "
            f"max={max(events_per_line)}  mean={mean_n:.2f}  median={med:.2f}"
        )
    print(f"notes_total: {notes}  rests: {rests}  rest_rate: {(rests / notes) if notes else 0.0:.4f}")
    if lyrical_scores:
        print(
            "lyrical_score:"
            f" min={min(lyrical_scores):.4f}"
            f" max={max(lyrical_scores):.4f}"
            f" mean={statistics.mean(lyrical_scores):.4f}"
            f" median={statistics.median(lyrical_scores):.4f}"
        )
        print("lyrical_components_mean:")
        for k in sorted(lyrical_component_sum.keys()):
            denom = max(1, int(lyrical_component_n.get(k, 0)))
            print(f"  {k}: {float(lyrical_component_sum[k]) / float(denom):.4f}")
    print(
        "metadata_rows:"
        f" emotion={meta_rows_emotion}"
        f" section_role={meta_rows_section}"
        f" phrase_contours={meta_rows_contours}"
        f" phrase_roles={meta_rows_roles}"
        f" chord_sequence={meta_rows_chords}"
        f" chords_aligned={meta_rows_chord_aligned}"
    )
    if args.require_metadata and lines_used > 0:
        missing = []
        if meta_rows_emotion <= 0:
            missing.append("emotion")
        if meta_rows_section <= 0:
            missing.append("section_role")
        if meta_rows_contours <= 0:
            missing.append("phrase_contours")
        if meta_rows_roles <= 0:
            missing.append("phrase_roles")
        if meta_rows_chords <= 0:
            missing.append("chord_sequence")
        if meta_rows_chord_aligned <= 0:
            missing.append("chord_alignment")
        if missing:
            print("FAIL: missing required metadata: " + ", ".join(missing))
            return 2
    if args.tag_counts and (emotion_c or section_c):
        if emotion_c:
            print("emotion_top:")
            for k, v in emotion_c.most_common(12):
                print(f"  {k!r}: {v}")
        if section_c:
            print("section_role_top:")
            for k, v in section_c.most_common(12):
                print(f"  {k!r}: {v}")
    print("duration_top:")
    for k, v in dur_c.most_common(12):
        print(f"  {k}: {v}")
    print("interval_top (voiced consecutive):")
    for k, v in iv_c.most_common(16):
        print(f"  {k}: {v}")
    if contour_c:
        print("phrase_contour_top:")
        for k, v in contour_c.most_common(12):
            print(f"  {k!r}: {v}")
    if phrase_role_c:
        print("phrase_role_top:")
        for k, v in phrase_role_c.most_common(12):
            print(f"  {k!r}: {v}")
    if chord_token_c:
        print("chord_token_top:")
        for k, v in chord_token_c.most_common(12):
            print(f"  {k!r}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

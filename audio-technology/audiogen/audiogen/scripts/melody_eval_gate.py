#!/usr/bin/env python3
"""Promotion gate for JSONL melody corpora. Exit 0 = pass."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Tuple


def _iter_degree_duration_pairs(seq: Any) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
    if not isinstance(seq, list):
        return out
    for item in seq:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                out.append((int(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    return out


def _iter_melody_events(row: Dict[str, Any]) -> List[Tuple[int, float]]:
    out = _iter_degree_duration_pairs(row.get("melody"))
    if out:
        return out
    phrases = row.get("phrases")
    if isinstance(phrases, list):
        for ph in phrases:
            if not isinstance(ph, list):
                continue
            out.extend(_iter_degree_duration_pairs(ph))
    if out:
        return out
    lead = row.get("lead")
    if isinstance(lead, dict):
        for key in ("degrees", "midi", "pcs"):
            lane = _iter_degree_duration_pairs(lead.get(key))
            if lane:
                return lane
    return out


def _melody_key(events: List[Tuple[int, float]]) -> str:
    try:
        raw = json.dumps([[int(d), float(t)] for d, t in events], separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
    except Exception:
        return str(hash(tuple(events)))


def _entropy_from_hist(counts: Dict[Any, int], total: int) -> float:
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = float(c) / float(total)
        h -= p * math.log(p + 1e-18, 2)
    return h


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "path",
        nargs="?",
        default=".cache/live_melody_training.jsonl",
        help="JSONL file to evaluate.",
    )
    ap.add_argument(
        "--max-rest-rate",
        type=float,
        default=None,
        help="Fail if mean rest rate across lines exceeds this (default: config).",
    )
    ap.add_argument(
        "--min-mean-accept",
        type=float,
        default=None,
        help="Fail if mean accept_score is below this (default: config).",
    )
    ap.add_argument(
        "--min-mean-lyrical",
        type=float,
        default=None,
        help="Fail if mean lyrical_score is below this (default: config).",
    )
    ap.add_argument(
        "--min-lines",
        type=int,
        default=None,
        help="Fail if line count is below this (default: config).",
    )
    ap.add_argument(
        "--min-interval-entropy",
        type=float,
        default=0.0,
        help="Optional: fail if pooled voiced-interval entropy (bits) is below this.",
    )
    ap.add_argument(
        "--min-emotions",
        type=int,
        default=None,
        help="Optional: fail if fewer distinct emotion labels are present.",
    )
    ap.add_argument(
        "--min-section-roles",
        type=int,
        default=None,
        help="Optional: fail if fewer distinct section_role labels are present.",
    )
    ap.add_argument(
        "--max-emotion-share",
        type=float,
        default=None,
        help="Optional: fail if one emotion exceeds this share of labeled rows.",
    )
    ap.add_argument(
        "--require-metadata",
        action="store_true",
        help="Fail if rows lack emotion, phrase role/contour, or chord metadata.",
    )
    ap.add_argument(
        "--require-chord-alignment",
        action="store_true",
        help="With --require-metadata: also require len(chord_sequence) == len(melody) for at least one row.",
    )
    ap.add_argument(
        "--max-dup-rate",
        type=float,
        default=None,
        help="Optional: fail if duplicate melody rate exceeds this (0..1).",
    )
    ap.add_argument(
        "--max-rest-rate-by-emotion",
        type=float,
        default=None,
        help="Optional: fail if any single emotion's rest rate exceeds this (0..1).",
    )
    ap.add_argument(
        "--min-lines-per-emotion",
        type=int,
        default=None,
        help="Optional: fail if any labeled emotion has fewer than this many rows.",
    )
    ap.add_argument(
        "--report",
        default="",
        help="If set, write a JSON report to this path (for promotion manifests).",
    )
    args = ap.parse_args()

    try:
        from audiogen_core.config import CONFIG

        max_rr = args.max_rest_rate
        if max_rr is None:
            max_rr = float(getattr(CONFIG.composition, "melody_jsonl_eval_max_rest_rate", 0.55) or 0.55)
        min_acc = args.min_mean_accept
        if min_acc is None:
            min_acc = float(getattr(CONFIG.composition, "melody_jsonl_eval_min_mean_accept", 0.0) or 0.0)
        min_lyrical = args.min_mean_lyrical
        if min_lyrical is None:
            min_lyrical = float(getattr(CONFIG.composition, "melody_jsonl_eval_min_mean_lyrical", 0.0) or 0.0)
        min_lines = args.min_lines
        if min_lines is None:
            min_lines = int(getattr(CONFIG.composition, "melody_jsonl_eval_min_lines", 1) or 1)
        min_emotions = args.min_emotions
        if min_emotions is None:
            min_emotions = int(getattr(CONFIG.composition, "melody_jsonl_eval_min_emotions", 0) or 0)
        min_section_roles = args.min_section_roles
        if min_section_roles is None:
            min_section_roles = int(getattr(CONFIG.composition, "melody_jsonl_eval_min_section_roles", 0) or 0)
        max_emotion_share = args.max_emotion_share
        if max_emotion_share is None:
            max_emotion_share = float(getattr(CONFIG.composition, "melody_jsonl_eval_max_emotion_share", 1.0) or 1.0)
    except Exception:
        max_rr = float(args.max_rest_rate) if args.max_rest_rate is not None else 0.55
        min_acc = float(args.min_mean_accept) if args.min_mean_accept is not None else 0.0
        min_lines = int(args.min_lines) if args.min_lines is not None else 1
        min_emotions = int(args.min_emotions) if args.min_emotions is not None else 0
        min_section_roles = int(args.min_section_roles) if args.min_section_roles is not None else 0
        max_emotion_share = float(args.max_emotion_share) if args.max_emotion_share is not None else 1.0
        min_lyrical = float(args.min_mean_lyrical) if args.min_mean_lyrical is not None else 0.0

    p = Path(args.path)
    if not p.is_file():
        print(f"File not found: {p}", file=sys.stderr)
        return 1

    lines = 0
    notes = 0
    rests = 0
    acc_sum = 0.0
    acc_n = 0
    lyrical_sum = 0.0
    lyrical_n = 0
    lyrical_component_sum: Dict[str, float] = {}
    lyrical_component_n: Dict[str, int] = {}
    iv_c: Dict[int, int] = {}
    iv_total = 0
    emotion_c: Counter[str] = Counter()
    section_c: Counter[str] = Counter()
    rows_with_contours = 0
    rows_with_roles = 0
    rows_with_chords = 0
    rows_with_chord_alignment = 0
    uniq_melodies: Dict[str, int] = {}
    labeled_lines = 0

    # Per-emotion stats
    emo_notes: Counter[str] = Counter()
    emo_rests: Counter[str] = Counter()
    emo_iv_c: DefaultDict[str, Dict[int, int]] = DefaultDict(dict)
    emo_iv_total: Counter[str] = Counter()

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
                a = float(row.get("accept_score", 0.0) or 0.0)
                acc_sum += a
                acc_n += 1
            except Exception:
                pass
            events = _iter_melody_events(row)
            try:
                if "lyrical_score" in row:
                    ls = float(row.get("lyrical_score", 0.0) or 0.0)
                    comps = row.get("lyrical_components") if isinstance(row.get("lyrical_components"), dict) else {}
                else:
                    from ai.markov.melody.beauty import score_lyrical_melody

                    ls, comps = score_lyrical_melody(events)
                lyrical_sum += float(ls)
                lyrical_n += 1
                for ck, cv in dict(comps or {}).items():
                    try:
                        key = str(ck)
                        lyrical_component_sum[key] = float(lyrical_component_sum.get(key, 0.0)) + float(cv)
                        lyrical_component_n[key] = int(lyrical_component_n.get(key, 0)) + 1
                    except Exception:
                        continue
            except Exception:
                pass
            emotion = str(row.get("emotion") or "").strip().lower()
            section = str(row.get("section_role") or "").strip().lower()
            if emotion:
                emotion_c[emotion] += 1
                labeled_lines += 1
            if section:
                section_c[section] += 1
            if isinstance(row.get("phrase_contours"), list) and row.get("phrase_contours"):
                rows_with_contours += 1
            if isinstance(row.get("phrase_roles"), list) and row.get("phrase_roles"):
                rows_with_roles += 1
            if isinstance(row.get("chord_sequence"), list) and row.get("chord_sequence"):
                rows_with_chords += 1
            if events:
                k = _melody_key(events)
                uniq_melodies[k] = uniq_melodies.get(k, 0) + 1
            try:
                chords = row.get("chord_sequence")
                if isinstance(chords, list) and chords and len(chords) == len(events):
                    rows_with_chord_alignment += 1
            except Exception:
                pass
            voiced = [int(d) for d, _ in events if isinstance(d, int) and int(d) >= 0]
            for d, _ in events:
                notes += 1
                if isinstance(d, int) and int(d) < 0:
                    rests += 1
                if emotion:
                    emo_notes[emotion] += 1
                    if isinstance(d, int) and int(d) < 0:
                        emo_rests[emotion] += 1
            for i in range(len(voiced) - 1):
                iv = int(voiced[i + 1]) - int(voiced[i])
                iv_c[iv] = iv_c.get(iv, 0) + 1
                iv_total += 1
                if emotion:
                    c = emo_iv_c[emotion]
                    c[iv] = c.get(iv, 0) + 1
                    emo_iv_total[emotion] += 1

    rest_rate = (float(rests) / float(notes)) if notes else 0.0
    mean_acc = (acc_sum / float(acc_n)) if acc_n else 0.0
    mean_lyrical = (lyrical_sum / float(lyrical_n)) if lyrical_n else 0.0
    mean_lyrical_components = {
        str(k): float(lyrical_component_sum.get(k, 0.0) / float(max(1, lyrical_component_n.get(k, 0))))
        for k in sorted(lyrical_component_sum.keys())
    }
    iv_ent = _entropy_from_hist(iv_c, iv_total)
    uniq = int(len(uniq_melodies))
    dup_rows = int(sum(v - 1 for v in uniq_melodies.values() if int(v) > 1))
    dup_rate = (float(dup_rows) / float(max(1, lines))) if lines else 0.0

    emo_rest_rate: Dict[str, float] = {}
    emo_iv_ent: Dict[str, float] = {}
    for em in emotion_c.keys():
        n = int(emo_notes.get(em, 0) or 0)
        r = int(emo_rests.get(em, 0) or 0)
        emo_rest_rate[em] = (float(r) / float(n)) if n else 0.0
        emo_iv_ent[em] = _entropy_from_hist(dict(emo_iv_c.get(em, {}) or {}), int(emo_iv_total.get(em, 0) or 0))

    ok = True
    reasons: List[str] = []
    if lines < int(min_lines):
        ok = False
        reasons.append(f"lines {lines} < min_lines {min_lines}")
    if rest_rate > float(max_rr) + 1e-9:
        ok = False
        reasons.append(f"rest_rate {rest_rate:.4f} > max {max_rr}")
    if mean_acc + 1e-9 < float(min_acc):
        ok = False
        reasons.append(f"mean_accept {mean_acc:.4f} < min {min_acc}")
    if mean_lyrical + 1e-9 < float(min_lyrical):
        ok = False
        reasons.append(f"mean_lyrical {mean_lyrical:.4f} < min {min_lyrical}")
    if float(args.min_interval_entropy) > 1e-9 and iv_ent + 1e-9 < float(args.min_interval_entropy):
        ok = False
        reasons.append(f"interval_entropy {iv_ent:.4f} < min {float(args.min_interval_entropy)}")
    if int(min_emotions) > 0 and len(emotion_c) < int(min_emotions):
        ok = False
        reasons.append(f"distinct_emotions {len(emotion_c)} < min {int(min_emotions)}")
    if int(min_section_roles) > 0 and len(section_c) < int(min_section_roles):
        ok = False
        reasons.append(f"distinct_section_roles {len(section_c)} < min {int(min_section_roles)}")
    labeled_emotions = int(sum(emotion_c.values()))
    max_share = 0.0
    if labeled_emotions > 0 and emotion_c:
        max_share = max(float(v) / float(labeled_emotions) for v in emotion_c.values())
    if float(max_emotion_share) < 1.0 and max_share > float(max_emotion_share) + 1e-9:
        ok = False
        reasons.append(f"max_emotion_share {max_share:.4f} > max {float(max_emotion_share)}")
    if bool(args.require_metadata):
        if len(emotion_c) <= 0:
            ok = False
            reasons.append("missing emotion metadata")
        if rows_with_contours <= 0:
            ok = False
            reasons.append("missing phrase_contours metadata")
        if rows_with_roles <= 0:
            ok = False
            reasons.append("missing phrase_roles metadata")
        if rows_with_chords <= 0:
            ok = False
            reasons.append("missing chord_sequence metadata")
        if bool(args.require_chord_alignment) and rows_with_chord_alignment <= 0:
            ok = False
            reasons.append("missing chord_sequence alignment (len(chords) == len(melody))")

    if args.max_dup_rate is not None:
        mdr = float(args.max_dup_rate)
        if mdr < 1.0 and dup_rate > mdr + 1e-9:
            ok = False
            reasons.append(f"dup_rate {dup_rate:.4f} > max {mdr}")

    if args.max_rest_rate_by_emotion is not None:
        mrr = float(args.max_rest_rate_by_emotion)
        worst_em = None
        worst = 0.0
        for em, rr in emo_rest_rate.items():
            if float(rr) > float(worst):
                worst = float(rr)
                worst_em = em
        if worst_em is not None and worst > float(mrr) + 1e-9:
            ok = False
            reasons.append(f"emotion_rest_rate[{worst_em}] {worst:.4f} > max {mrr}")

    if args.min_lines_per_emotion is not None:
        m = int(args.min_lines_per_emotion)
        if m > 0:
            too_small = sorted([em for em, c in emotion_c.items() if int(c) < m])
            if too_small:
                ok = False
                reasons.append(
                    f"emotions_below_min_lines({m}): "
                    + ", ".join(too_small[:8])
                    + (" ..." if len(too_small) > 8 else "")
                )

    print(f"lines: {lines}")
    print(f"notes: {notes}  rests: {rests}  rest_rate: {rest_rate:.4f}")
    print(f"mean_accept: {mean_acc:.4f}  (rows_with_score: {acc_n})")
    print(f"mean_lyrical: {mean_lyrical:.4f}  (rows_with_score: {lyrical_n})")
    print(f"voiced_interval_entropy_bits: {iv_ent:.4f}")
    print(f"unique_melodies: {uniq}  dup_rows: {dup_rows}  dup_rate: {dup_rate:.4f}")
    print(
        f"metadata_rows: contours={rows_with_contours}  roles={rows_with_roles}  "
        f"chords={rows_with_chords}  chords_aligned={rows_with_chord_alignment}"
    )
    print(
        f"distinct_emotions: {len(emotion_c)}  distinct_section_roles: {len(section_c)}  "
        f"max_emotion_share: {max_share:.4f}"
    )

    if str(args.report or "").strip():
        out = Path(str(args.report)).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "path": str(p),
            "lines": int(lines),
            "labeled_lines": int(labeled_lines),
            "notes": int(notes),
            "rests": int(rests),
            "rest_rate": float(rest_rate),
            "mean_accept": float(mean_acc),
            "mean_lyrical": float(mean_lyrical),
            "mean_lyrical_components": mean_lyrical_components,
            "voiced_interval_entropy_bits": float(iv_ent),
            "unique_melodies": int(uniq),
            "dup_rows": int(dup_rows),
            "dup_rate": float(dup_rate),
            "metadata_rows": {
                "phrase_contours": int(rows_with_contours),
                "phrase_roles": int(rows_with_roles),
                "chord_sequence": int(rows_with_chords),
                "chords_aligned": int(rows_with_chord_alignment),
            },
            "distinct": {
                "emotions": int(len(emotion_c)),
                "section_roles": int(len(section_c)),
            },
            "counts": {
                "emotion": dict(sorted(emotion_c.items())),
                "section_role": dict(sorted(section_c.items())),
            },
            "max_emotion_share": float(max_share),
            "per_emotion": {
                "lines": dict(sorted((k, int(v)) for k, v in emotion_c.items())),
                "rest_rate": dict(sorted((k, float(v)) for k, v in emo_rest_rate.items())),
                "voiced_interval_entropy_bits": dict(sorted((k, float(v)) for k, v in emo_iv_ent.items())),
            },
            "ok": bool(ok and not reasons),
            "reasons": list(reasons),
        }
        out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if reasons:
        print("FAIL: " + "; ".join(reasons), file=sys.stderr)
        return 2
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

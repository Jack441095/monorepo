#!/usr/bin/env python3
"""
Fast chord/harmony diagnostics for the joint live-melody JSONL.

This script is intentionally lightweight:
- Streams JSONL (no large in-memory structures)
- Computes basic harmony metrics per emotion using either:
  - `chord_markov_tokens` (preferred, includes degree buckets), and/or
  - `chord_sequence` (fallback)

Designed to complement melody_emotion_diagnostics_fast.py for quick iteration.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.emotion_aliases import canonical_emotion_name
from data.tokens import ChordToken


def _default_jsonl_path(root: Path) -> Optional[Path]:
    candidates = []
    base = root / "artifacts" / "datasets" / "live_melody"
    if base.is_dir():
        candidates.extend(base.glob("*/live_melody_training.with_references.jsonl"))
        candidates.extend(base.glob("*/live_melody_training.jsonl"))
    cache = root / ".cache" / "live_melody_training.jsonl"
    if cache.is_file():
        candidates.append(cache)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            s = line.strip()
            if not s:
                continue
            try:
                row = json.loads(s)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _entropy(counter: Counter[str]) -> float:
    tot = float(sum(counter.values()))
    if tot <= 1e-12:
        return 0.0
    h = 0.0
    for c in counter.values():
        p = float(c) / tot
        if p > 1e-12:
            h -= p * math.log(p + 1e-12, 2)
    return float(h)


def analyze_fast(
    path: Path,
    *,
    min_rows: int = 4,
    max_rows_total: int = 0,
    max_rows_per_emotion: int = 0,
    emotions_allow: Optional[set[str]] = None,
) -> Dict[str, Any]:
    # Streaming per-emotion stats.
    rows_total = 0
    used_rows = 0

    rows_by_emotion: Dict[str, int] = defaultdict(int)
    token_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    bucket_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    degree_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    cadence_bucket_counts: Dict[str, Counter[str]] = defaultdict(Counter)
    chord_repeat_hits: Dict[str, int] = defaultdict(int)
    chord_repeat_den: Dict[str, int] = defaultdict(int)
    chord_change_hits: Dict[str, int] = defaultdict(int)
    chord_change_den: Dict[str, int] = defaultdict(int)
    slots_sum: Dict[str, int] = defaultdict(int)

    for row in _iter_jsonl(path):
        rows_total += 1
        if max_rows_total and used_rows >= int(max_rows_total):
            break

        emotion = canonical_emotion_name(str(row.get("emotion") or "neutral")) or "neutral"
        if emotions_allow is not None and emotion not in emotions_allow:
            continue
        if max_rows_per_emotion and rows_by_emotion[emotion] >= int(max_rows_per_emotion):
            continue

        tokens = row.get("chord_markov_tokens")
        chords = row.get("chord_sequence")
        if not isinstance(tokens, list) and not isinstance(chords, list):
            continue
        # Prefer tokens; fall back to buckets derived from symbols.
        tok_list: list[str] = []
        if isinstance(tokens, list) and tokens:
            tok_list = [str(t or "") for t in tokens if str(t or "").strip()]
        elif isinstance(chords, list) and chords:
            # Minimal fallback: bucketize by token bucket from a synthesized token.
            for ch in chords:
                s = str(ch or "").strip()
                if not s:
                    continue
                # Use a crude bucket guess: if it looks minor, use min else maj.
                # (This is just a fallback; the joint export should include tokens.)
                bucket = "min" if "i" in s[:2] and "I" not in s[:2] else "maj"
                tok_list.append(ChordToken.from_symbol(s, bucket=bucket).serialize(use_degree=True))

        if not tok_list:
            continue

        used_rows += 1
        rows_by_emotion[emotion] += 1
        slots_sum[emotion] += int(len(tok_list))

        tc = token_counts[emotion]
        bc = bucket_counts[emotion]
        dc = degree_counts[emotion]
        for t in tok_list:
            tc[t] += 1
            bc[ChordToken.token_bucket(t)] += 1
            deg = ChordToken.token_degree(t)
            if deg:
                dc[deg] += 1

        # Cadence bucket: last token bucket.
        try:
            cadence_bucket_counts[emotion][ChordToken.token_bucket(tok_list[-1])] += 1
        except Exception:
            pass

        # Repetition / change rates
        if len(tok_list) >= 2:
            for a, b in zip(tok_list, tok_list[1:]):
                chord_repeat_den[emotion] += 1
                chord_change_den[emotion] += 1
                if str(a) == str(b):
                    chord_repeat_hits[emotion] += 1
                else:
                    chord_change_hits[emotion] += 1

    emotions: Dict[str, Dict[str, Any]] = {}
    for name in sorted(rows_by_emotion.keys()):
        rows = int(rows_by_emotion[name])
        tc = token_counts[name]
        bc = bucket_counts[name]
        dc = degree_counts[name]
        rep_den = max(1, int(chord_repeat_den[name]))
        rep_rate = float(chord_repeat_hits[name]) / float(rep_den)
        change_rate = float(chord_change_hits[name]) / float(max(1, int(chord_change_den[name])))

        metrics: Dict[str, Any] = {
            "rows": rows,
            "slots": int(slots_sum[name]),
            "unique_tokens": int(len(tc)),
            "token_entropy_bits": float(_entropy(tc)),
            "repeat_rate": float(rep_rate),
            "change_rate": float(change_rate),
            "bucket_dist": dict(bc.most_common(8)),
            "degree_dist": dict(dc.most_common(10)),
            "cadence_bucket_dist": dict(cadence_bucket_counts[name].most_common(8)),
        }

        warnings: list[str] = []
        if rows < int(min_rows):
            warnings.append(f"low_rows:{rows}")
        if rep_rate > 0.28 and rows >= int(min_rows):
            warnings.append(f"too_repetitive_harmony:{rep_rate:.3f}")
        if metrics["unique_tokens"] <= 6 and rows >= int(min_rows):
            warnings.append(f"low_harmony_diversity:unique={metrics['unique_tokens']}")
        metrics["warnings"] = warnings
        emotions[name] = metrics

    return {
        "path": str(path),
        "rows_total": int(rows_total),
        "rows_used": int(used_rows),
        "emotion_count": int(len(emotions)),
        "emotions": emotions,
    }


def _print_report(report: Dict[str, Any], *, top: int) -> None:
    print(f"path: {report['path']}")
    print(f"rows_total: {report['rows_total']}  rows_used: {report['rows_used']}")
    print(f"emotion_count: {report['emotion_count']}")
    print("")

    rows = sorted(
        report["emotions"].items(),
        key=lambda kv: (len(kv[1].get("warnings", [])), -int(kv[1].get("rows", 0))),
        reverse=True,
    )
    for name, m in rows[: int(top)]:
        warn = ", ".join(m.get("warnings", [])) or "ok"
        print(
            f"{name:15s}"
            f" rows={int(m.get('rows', 0)):4d}"
            f" slots={int(m.get('slots', 0)):5d}"
            f" uniq={int(m.get('unique_tokens', 0)):4d}"
            f" H={float(m.get('token_entropy_bits', 0.0)):.2f}"
            f" rep={float(m.get('repeat_rate', 0.0)):.3f}"
            f" change={float(m.get('change_rate', 0.0)):.3f}"
            f" cadence={str(next(iter(m.get('cadence_bucket_dist', {}) or {}), ''))}"
            f" warn={warn}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=None)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--top", type=int, default=32)
    ap.add_argument("--min-rows", type=int, default=4)
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--max-rows-per-emotion", type=int, default=0)
    ap.add_argument("--emotions", nargs="*", default=None)
    args = ap.parse_args()

    path = Path(args.path) if args.path else _default_jsonl_path(ROOT)
    if path is None or not path.is_file():
        p = str(path) if path is not None else "(none)"
        print(f"JSONL not found: {p}", file=sys.stderr)
        if path is not None and not path.is_file():
            raw_guess = path.parent / f"{path.name}.raw.jsonl"
            if raw_guess.is_file():
                print(
                    f"Found raw rows at {raw_guess}. Finish the split with:\n"
                    f"  python3 scripts/generate_live_melody_training_jsonl.py "
                    f'--out "{path}" --split-existing-raw --dedup-kept',
                    file=sys.stderr,
                )
        else:
            print("Pass a path to live_melody_training.jsonl (or set up the default).", file=sys.stderr)
        return 1

    emotions_allow = None
    if args.emotions:
        emotions_allow = set()
        for raw in list(args.emotions):
            key = canonical_emotion_name(str(raw or "")) or str(raw or "").strip().lower()
            if key:
                emotions_allow.add(key)

    report = analyze_fast(
        path,
        min_rows=int(args.min_rows),
        max_rows_total=int(args.max_rows),
        max_rows_per_emotion=int(args.max_rows_per_emotion),
        emotions_allow=emotions_allow,
    )
    _print_report(report, top=int(args.top))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"json_out: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
"""
Fast emotion diagnostics for live melody JSONL.

This is a speed-optimized alternative to scripts/melody_emotion_diagnostics.py:
- Streams JSONL (no big lists of durations/intervals)
- Computes only the core metrics used for iteration:
  asc/desc/repeat/static_run, short/long rhythm rates, movement, leaps,
  accept_mean and lyrical_mean (if present)
- Optional caps: stop after N rows total and/or N rows per emotion

Use this when you're iterating on generation logic and want quick feedback.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.emotion_aliases import canonical_emotion_name
from data.emotion_melody_priors import emotion_melody_prior_for

MelodyEvent = Tuple[int, float]


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


def _iter_melody_events(row: Dict[str, Any]) -> list[MelodyEvent]:
    out: list[MelodyEvent] = []
    melody = row.get("melody")
    if isinstance(melody, list):
        for item in melody:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    out.append((int(item[0]), float(item[1])))
                except (TypeError, ValueError):
                    continue
    if out:
        return out
    phrases = row.get("phrases")
    if isinstance(phrases, list):
        for phrase in phrases:
            if not isinstance(phrase, list):
                continue
            for item in phrase:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    try:
                        out.append((int(item[0]), float(item[1])))
                    except (TypeError, ValueError):
                        continue
    return out


def _warn_for_emotion(name: str, metrics: Dict[str, Any], min_rows: int) -> list[str]:
    warnings: list[str] = []
    prior = emotion_melody_prior_for(name)
    rows = int(metrics.get("rows", 0) or 0)
    if rows < int(min_rows):
        warnings.append(f"low_rows:{rows}")

    repeat_rate = float(metrics.get("repeat_rate", 0.0) or 0.0)
    if prior.repeat_mult < 0.85 and repeat_rate > 0.22:
        warnings.append(f"too_repetitive:{repeat_rate:.3f}")

    static_run = int(metrics.get("static_run_max", 1) or 1)
    if static_run >= 5:
        warnings.append(f"long_static_run:{static_run}")

    asc = float(metrics.get("ascending_rate", 0.0) or 0.0)
    desc = float(metrics.get("descending_rate", 0.0) or 0.0)
    if prior.ascending_mult > prior.descending_mult * 1.12 and asc <= desc:
        warnings.append(f"not_rising_enough:asc={asc:.3f},desc={desc:.3f}")
    if prior.descending_mult > prior.ascending_mult * 1.12 and desc <= asc:
        warnings.append(f"not_falling_enough:asc={asc:.3f},desc={desc:.3f}")

    short_rate = float(metrics.get("short_duration_rate", 0.0) or 0.0)
    long_rate = float(metrics.get("long_duration_rate", 0.0) or 0.0)
    if prior.long_rhythm_mult > prior.short_rhythm_mult * 1.20 and long_rate < short_rate:
        warnings.append(f"not_long_breathed_enough:short={short_rate:.3f},long={long_rate:.3f}")
    return warnings


def analyze_fast(
    path: Path,
    *,
    min_rows: int = 4,
    max_rows_total: int = 0,
    max_rows_per_emotion: int = 0,
    emotions_allow: Optional[set[str]] = None,
) -> Dict[str, Any]:
    # Per-emotion counters (all streaming).
    buckets: Dict[str, Dict[str, float]] = {}
    int_buckets: Dict[str, Dict[str, int]] = {}

    def _get(name: str) -> tuple[Dict[str, float], Dict[str, int]]:
        if name not in buckets:
            buckets[name] = {
                "accept_sum": 0.0,
                "accept_n": 0.0,
                "lyr_sum": 0.0,
                "lyr_n": 0.0,
            }
            int_buckets[name] = {
                "rows": 0,
                "events": 0,
                "rests": 0,
                "dur_n": 0,
                "short_n": 0,
                "long_n": 0,
                "interval_n": 0,
                "asc_n": 0,
                "desc_n": 0,
                "repeat_n": 0,
                "movement_n": 0,
                "step_n": 0,
                "true_step_n": 0,
                "large_leap_n": 0,
                "static_run_max": 1,
            }
        return buckets[name], int_buckets[name]

    total_rows = 0
    used_rows = 0
    for row in _iter_jsonl(path):
        total_rows += 1
        if max_rows_total and used_rows >= int(max_rows_total):
            break

        events = _iter_melody_events(row)
        if not events:
            continue

        name = canonical_emotion_name(str(row.get("emotion") or "neutral")) or "neutral"
        if emotions_allow is not None and name not in emotions_allow:
            continue

        _fb, ib = _get(name)
        if max_rows_per_emotion and int(ib["rows"]) >= int(max_rows_per_emotion):
            continue

        used_rows += 1
        ib["rows"] += 1
        ib["events"] += len(events)

        # Durations
        for deg, dur in events:
            ib["dur_n"] += 1
            if int(deg) < 0:
                ib["rests"] += 1
            d0 = abs(float(dur))
            if d0 <= 0.5 + 1e-9:
                ib["short_n"] += 1
            elif d0 >= 2.0 - 1e-9:
                ib["long_n"] += 1

        # Intervals + static run
        voiced = [int(d) for d, _dur in events if int(d) >= 0]
        if len(voiced) >= 2:
            run = 1
            max_run = 1
            for a, b in zip(voiced, voiced[1:]):
                iv = int(b) - int(a)
                ib["interval_n"] += 1
                if iv > 0:
                    ib["asc_n"] += 1
                elif iv < 0:
                    ib["desc_n"] += 1
                else:
                    ib["repeat_n"] += 1
                if iv != 0:
                    ib["movement_n"] += 1
                if abs(iv) <= 1:
                    ib["step_n"] += 1
                if abs(iv) == 1:
                    ib["true_step_n"] += 1
                if abs(iv) >= 4:
                    ib["large_leap_n"] += 1

                if iv == 0:
                    run += 1
                    if run > max_run:
                        max_run = run
                else:
                    run = 1
            if max_run > ib["static_run_max"]:
                ib["static_run_max"] = int(max_run)

        # Accept / lyrical means
        try:
            score = float(row.get("accept_score", 0.0) or 0.0)
            _fb["accept_sum"] += float(score)
            _fb["accept_n"] += 1.0
        except Exception:
            pass
        try:
            if "lyrical_score" in row:
                lyr = float(row.get("lyrical_score", 0.0) or 0.0)
                _fb["lyr_sum"] += float(lyr)
                _fb["lyr_n"] += 1.0
        except Exception:
            pass

    emotions: Dict[str, Dict[str, Any]] = {}
    for name in sorted(int_buckets.keys()):
        fb = buckets[name]
        ib = int_buckets[name]

        def _pct(num: int, den: int) -> float:
            return float(num) / float(den) if den else 0.0

        rows = int(ib["rows"])
        interval_n = int(ib["interval_n"])
        dur_n = int(ib["dur_n"])
        metrics: Dict[str, Any] = {
            "rows": rows,
            "events": int(ib["events"]),
            "rests": int(ib["rests"]),
            "rest_rate": _pct(int(ib["rests"]), int(ib["events"])),
            "intervals": interval_n,
            "ascending_rate": _pct(int(ib["asc_n"]), interval_n),
            "descending_rate": _pct(int(ib["desc_n"]), interval_n),
            "repeat_rate": _pct(int(ib["repeat_n"]), interval_n),
            "movement_rate": _pct(int(ib["movement_n"]), interval_n),
            "stepwise_rate": _pct(int(ib["step_n"]), interval_n),
            "true_step_rate": _pct(int(ib["true_step_n"]), interval_n),
            "large_leap_rate": _pct(int(ib["large_leap_n"]), interval_n),
            "short_duration_rate": _pct(int(ib["short_n"]), dur_n),
            "long_duration_rate": _pct(int(ib["long_n"]), dur_n),
            "static_run_max": int(ib["static_run_max"]) if rows else 1,
            "accept_mean": float(fb["accept_sum"]) / float(fb["accept_n"]) if fb["accept_n"] else 0.0,
            "lyrical_mean": float(fb["lyr_sum"]) / float(fb["lyr_n"]) if fb["lyr_n"] else 0.0,
            "prior": asdict(emotion_melody_prior_for(name)),
        }
        metrics["warnings"] = _warn_for_emotion(name, metrics, int(min_rows))
        emotions[name] = metrics

    return {
        "path": str(path),
        "rows_total": int(total_rows),
        "rows_with_melody": int(used_rows),
        "emotion_count": len(emotions),
        "emotions": emotions,
    }


def _print_report(report: Dict[str, Any], *, top: int) -> None:
    print(f"path: {report['path']}")
    print(f"rows_total: {report['rows_total']}  rows_with_melody: {report['rows_with_melody']}")
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
            f" rows={m['rows']:4d}"
            f" lyr={m['lyrical_mean']:.3f}"
            f" acc={m['accept_mean']:.3f}"
            f" move={m['movement_rate']:.3f}"
            f" large={m['large_leap_rate']:.3f}"
            f" asc={m['ascending_rate']:.3f}"
            f" desc={m['descending_rate']:.3f}"
            f" rep={m['repeat_rate']:.3f}"
            f" short={m['short_duration_rate']:.3f}"
            f" long={m['long_duration_rate']:.3f}"
            f" static_run={m['static_run_max']}"
            f" warn={warn}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Live melody JSONL. Defaults to newest artifacts/datasets/live_melody/*/live_melody_training*.jsonl.",
    )
    ap.add_argument("--json-out", default=None, help="Optional path for full JSON diagnostics.")
    ap.add_argument("--top", type=int, default=32, help="Number of emotions to print.")
    ap.add_argument("--min-rows", type=int, default=4, help="Rows required before low_rows warning.")
    ap.add_argument("--max-rows", type=int, default=0, help="Stop after this many used rows total (0 = no cap).")
    ap.add_argument("--max-rows-per-emotion", type=int, default=0, help="Cap used rows per emotion (0 = no cap).")
    ap.add_argument("--emotions", nargs="*", default=None, help="Optional list of emotions to include (canonicalized).")
    args = ap.parse_args()

    path = Path(args.path) if args.path else _default_jsonl_path(ROOT)
    if path is None or not path.is_file():
        print("No melody JSONL found. Pass a path explicitly.")
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


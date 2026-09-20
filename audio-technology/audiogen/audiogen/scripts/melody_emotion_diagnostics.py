#!/usr/bin/env python3
"""Emotion-level diagnostics for live melody training JSONL.

This report is meant for listening calibration. It summarizes how each emotion
actually behaves in generated/training rows, then compares those metrics against
the sampler priors in data/emotion_melody_priors.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.emotion_aliases import canonical_emotion_name
from data.emotion_melody_priors import emotion_melody_prior_for


MelodyEvent = Tuple[int, float]


def _default_jsonl_path(root: Path) -> Optional[Path]:
    candidates: List[Path] = []
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
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                yield row


def _iter_melody_events(row: Dict[str, Any]) -> List[MelodyEvent]:
    out: List[MelodyEvent] = []
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


def _voiced_degrees(events: List[MelodyEvent]) -> List[int]:
    return [int(degree) for degree, _dur in events if int(degree) >= 0]


def _voiced_intervals(events: List[MelodyEvent]) -> List[int]:
    voiced = _voiced_degrees(events)
    return [int(voiced[i + 1]) - int(voiced[i]) for i in range(len(voiced) - 1)]


def _melody_hash(events: List[MelodyEvent]) -> str:
    raw = json.dumps([[int(d), round(float(t), 5)] for d, t in events], separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mean(values: List[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _median(values: List[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _pct(num: float, den: float) -> float:
    return float(num) / float(den) if den else 0.0


def _max_static_run_from_intervals(intervals: List[int]) -> int:
    max_run = 1
    cur = 1
    for iv in list(intervals or []):
        if int(iv) == 0:
            cur += 1
        else:
            max_run = max(int(max_run), int(cur))
            cur = 1
    return max(int(max_run), int(cur))


def _warn_for_emotion(name: str, metrics: Dict[str, Any], min_rows: int) -> List[str]:
    warnings: List[str] = []
    prior = emotion_melody_prior_for(name)
    rows = int(metrics.get("rows", 0) or 0)
    if rows < int(min_rows):
        warnings.append(f"low_rows:{rows}")
    lyrical = float(metrics.get("lyrical_mean", 0.0) or 0.0)
    if lyrical and lyrical < 0.42:
        warnings.append(f"low_lyrical:{lyrical:.3f}")
    rest_rate = float(metrics.get("rest_rate", 0.0) or 0.0)
    if rest_rate > 0.38:
        warnings.append(f"high_rest_rate:{rest_rate:.3f}")
    repeat_rate = float(metrics.get("repeat_rate", 0.0) or 0.0)
    if prior.repeat_mult < 0.85 and repeat_rate > 0.22:
        warnings.append(f"too_repetitive:{repeat_rate:.3f}")
    movement_rate = float(metrics.get("movement_rate", 0.0) or 0.0)
    if movement_rate < 0.28 and int(metrics.get("intervals", 0) or 0) >= 4:
        warnings.append(f"low_movement:{movement_rate:.3f}")
    static_run = int(metrics.get("static_run_max", 1) or 1)
    if static_run >= 5:
        warnings.append(f"long_static_run:{static_run}")
    large_rate = float(metrics.get("large_leap_rate", 0.0) or 0.0)
    if prior.interval_large_leap_mult < 0.70 and large_rate > 0.12:
        warnings.append(f"too_many_large_leaps:{large_rate:.3f}")
    if prior.interval_large_leap_mult > 1.05 and large_rate < 0.04:
        warnings.append(f"not_enough_large_leaps:{large_rate:.3f}")
    asc = float(metrics.get("ascending_rate", 0.0) or 0.0)
    desc = float(metrics.get("descending_rate", 0.0) or 0.0)
    if prior.ascending_mult > prior.descending_mult * 1.12 and asc <= desc:
        warnings.append(f"not_rising_enough:asc={asc:.3f},desc={desc:.3f}")
    if prior.descending_mult > prior.ascending_mult * 1.12 and desc <= asc:
        warnings.append(f"not_falling_enough:asc={asc:.3f},desc={desc:.3f}")
    short_rate = float(metrics.get("short_duration_rate", 0.0) or 0.0)
    long_rate = float(metrics.get("long_duration_rate", 0.0) or 0.0)
    if prior.short_rhythm_mult > prior.long_rhythm_mult * 1.20 and short_rate < long_rate:
        warnings.append(f"not_active_enough:short={short_rate:.3f},long={long_rate:.3f}")
    if prior.long_rhythm_mult > prior.short_rhythm_mult * 1.20 and long_rate < short_rate:
        warnings.append(f"not_long_breathed_enough:short={short_rate:.3f},long={long_rate:.3f}")
    dup = float(metrics.get("duplicate_rate", 0.0) or 0.0)
    if dup > 0.20:
        warnings.append(f"high_duplicate_rate:{dup:.3f}")
    return warnings


def analyze(path: Path, *, min_rows: int = 4) -> Dict[str, Any]:
    grouped: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "rows": 0,
            "events": 0,
            "voiced": 0,
            "rests": 0,
            "durations": [],
            "intervals": [],
            "accept_scores": [],
            "lyrical_scores": [],
            "hashes": Counter(),
            "section_roles": Counter(),
            "phrase_roles": Counter(),
            "phrase_contours": Counter(),
            "cadence_degrees": Counter(),
        }
    )
    total_rows = 0
    used_rows = 0
    for row in _iter_jsonl(path):
        total_rows += 1
        events = _iter_melody_events(row)
        if not events:
            continue
        name = canonical_emotion_name(str(row.get("emotion") or "neutral")) or "neutral"
        bucket = grouped[name]
        bucket["rows"] += 1
        used_rows += 1
        bucket["events"] += len(events)
        voiced = _voiced_degrees(events)
        intervals = _voiced_intervals(events)
        bucket["voiced"] += len(voiced)
        bucket["rests"] += sum(1 for degree, _dur in events if int(degree) < 0)
        bucket["durations"].extend(float(dur) for _degree, dur in events)
        bucket["intervals"].extend(intervals)
        bucket["hashes"][_melody_hash(events)] += 1
        if voiced:
            bucket["cadence_degrees"][int(voiced[-1]) % 7] += 1
        try:
            bucket["accept_scores"].append(float(row.get("accept_score", 0.0) or 0.0))
        except Exception:
            pass
        try:
            if "lyrical_score" in row:
                bucket["lyrical_scores"].append(float(row.get("lyrical_score", 0.0) or 0.0))
        except Exception:
            pass
        section_role = str(row.get("section_role") or "").strip().lower()
        if section_role:
            bucket["section_roles"][section_role] += 1
        for role in row.get("phrase_roles") if isinstance(row.get("phrase_roles"), list) else []:
            role_s = str(role or "").strip().lower()
            if role_s:
                bucket["phrase_roles"][role_s] += 1
        for contour in row.get("phrase_contours") if isinstance(row.get("phrase_contours"), list) else []:
            contour_s = str(contour or "").strip().lower()
            if contour_s:
                bucket["phrase_contours"][contour_s] += 1

    emotions: Dict[str, Dict[str, Any]] = {}
    for name, bucket in sorted(grouped.items()):
        intervals = [int(v) for v in bucket["intervals"]]
        durations = [float(v) for v in bucket["durations"]]
        interval_n = len(intervals)
        duration_n = len(durations)
        asc_n = sum(1 for iv in intervals if iv > 0)
        desc_n = sum(1 for iv in intervals if iv < 0)
        repeat_n = sum(1 for iv in intervals if iv == 0)
        step_n = sum(1 for iv in intervals if abs(iv) <= 1)
        true_step_n = sum(1 for iv in intervals if abs(iv) == 1)
        movement_n = sum(1 for iv in intervals if iv != 0)
        small_leap_n = sum(1 for iv in intervals if 2 <= abs(iv) <= 3)
        large_leap_n = sum(1 for iv in intervals if abs(iv) >= 4)
        short_n = sum(1 for dur in durations if abs(dur) <= 0.5)
        medium_n = sum(1 for dur in durations if 0.5 < abs(dur) < 2.0)
        long_n = sum(1 for dur in durations if abs(dur) >= 2.0)
        hashes = bucket["hashes"]
        duplicate_rows = sum(max(0, int(count) - 1) for count in hashes.values())
        metrics: Dict[str, Any] = {
            "rows": int(bucket["rows"]),
            "events": int(bucket["events"]),
            "voiced": int(bucket["voiced"]),
            "rests": int(bucket["rests"]),
            "rest_rate": _pct(float(bucket["rests"]), float(bucket["events"])),
            "avg_duration": _mean(durations),
            "median_duration": _median(durations),
            "short_duration_rate": _pct(short_n, duration_n),
            "medium_duration_rate": _pct(medium_n, duration_n),
            "long_duration_rate": _pct(long_n, duration_n),
            "intervals": int(interval_n),
            "mean_abs_interval": _mean([abs(float(iv)) for iv in intervals]),
            "ascending_rate": _pct(asc_n, interval_n),
            "descending_rate": _pct(desc_n, interval_n),
            "repeat_rate": _pct(repeat_n, interval_n),
            "stepwise_rate": _pct(step_n, interval_n),
            "true_step_rate": _pct(true_step_n, interval_n),
            "static_step_rate": _pct(repeat_n, interval_n),
            "movement_rate": _pct(movement_n, interval_n),
            "static_run_max": int(_max_static_run_from_intervals(intervals)),
            "small_leap_rate": _pct(small_leap_n, interval_n),
            "large_leap_rate": _pct(large_leap_n, interval_n),
            "accept_mean": _mean([float(v) for v in bucket["accept_scores"]]),
            "lyrical_mean": _mean([float(v) for v in bucket["lyrical_scores"]]),
            "duplicate_rate": _pct(duplicate_rows, int(bucket["rows"])),
            "section_roles": dict(bucket["section_roles"].most_common(8)),
            "phrase_roles": dict(bucket["phrase_roles"].most_common(8)),
            "phrase_contours": dict(bucket["phrase_contours"].most_common(8)),
            "cadence_degrees": {str(k): v for k, v in bucket["cadence_degrees"].most_common(7)},
            "prior": asdict(emotion_melody_prior_for(name)),
        }
        metrics["warnings"] = _warn_for_emotion(name, metrics, min_rows)
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
    for name, metrics in rows[: int(top)]:
        warn = ", ".join(metrics.get("warnings", [])) or "ok"
        print(
            f"{name:15s}"
            f" rows={metrics['rows']:3d}"
            f" lyr={metrics['lyrical_mean']:.3f}"
            f" acc={metrics['accept_mean']:.3f}"
            f" step={metrics['stepwise_rate']:.3f}"
            f" true_step={metrics['true_step_rate']:.3f}"
            f" move={metrics['movement_rate']:.3f}"
            f" large={metrics['large_leap_rate']:.3f}"
            f" asc={metrics['ascending_rate']:.3f}"
            f" desc={metrics['descending_rate']:.3f}"
            f" short={metrics['short_duration_rate']:.3f}"
            f" long={metrics['long_duration_rate']:.3f}"
            f" rest={metrics['rest_rate']:.3f}"
            f" static_run={metrics['static_run_max']}"
            f" warn={warn}"
        )
    if len(rows) > int(top):
        print(f"... {len(rows) - int(top)} more emotions hidden; use --top {len(rows)} to show all.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="Live melody JSONL. Defaults to newest artifacts/datasets/live_melody/*/live_melody_training*.jsonl.",
    )
    parser.add_argument("--json-out", default=None, help="Optional path for full JSON diagnostics.")
    parser.add_argument("--top", type=int, default=32, help="Number of emotions to print.")
    parser.add_argument("--min-rows", type=int, default=4, help="Rows required before low_rows warning.")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    path = Path(args.path) if args.path else _default_jsonl_path(root)
    if path is None or not path.is_file():
        print("No melody JSONL found. Pass a path explicitly.")
        return 1

    report = analyze(path, min_rows=int(args.min_rows))
    _print_report(report, top=int(args.top))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        print(f"json_out: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

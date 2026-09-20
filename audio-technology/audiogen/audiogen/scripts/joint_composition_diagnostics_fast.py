#!/usr/bin/env python3
"""
Fast joint composition diagnostics (melody + harmony) for the joint JSONL.

Focus:
- Melody↔chord fit on strong beats (diatonic chord-tone-in-degree-space)
- Cadence landing agreement (melody final degree vs exported cadence targets)
- Lightweight harmony motion proxies (root leaps, chord repetition)

This is meant for quick iteration. It intentionally avoids expensive parsing,
audio rendering, and full voice-leading search.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.emotion_aliases import canonical_emotion_name

MelodyEvent = Tuple[int, float]

_ROMAN_RE = re.compile(r"^([#b]*)([ivIV]+)")
_ROMAN_TO_DEG = {
    "I": 0,
    "II": 1,
    "III": 2,
    "IV": 3,
    "V": 4,
    "VI": 5,
    "VII": 6,
}


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


def _roman_root_degree(chord_symbol: str) -> Optional[int]:
    s = str(chord_symbol or "").strip()
    if not s:
        return None
    m = _ROMAN_RE.match(s)
    if not m:
        return None
    _acc, roman = m.groups()
    key = str(roman).upper()
    return _ROMAN_TO_DEG.get(key)


def _chord_tone_degrees(chord_symbol: str) -> Optional[set[int]]:
    """
    Approximate chord tones in diatonic degree space.
    For iteration diagnostics we treat most chords as triads over their roman root:
      {root, root+2, root+4} mod 7.
    """
    root = _roman_root_degree(chord_symbol)
    if root is None:
        return None
    return {int(root) % 7, int(root + 2) % 7, int(root + 4) % 7}


def _is_strong_beat(beat_in_bar: float, beats_per_bar: float, *, eps: float) -> bool:
    """
    Strong beat detector with tolerance.
    We treat the bar downbeat (0) and mid-bar (beats_per_bar/2) as strong.
    """
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    x = float(beat_in_bar)
    e = max(1e-9, float(eps))
    # Distance to bar boundary (wrap-aware).
    d0 = min(abs(x - 0.0), abs(x - bpb))
    dmid = abs(x - (bpb / 2.0))
    return (d0 <= e) or (dmid <= e)


def analyze_fast(
    path: Path,
    *,
    min_rows: int = 4,
    max_rows_total: int = 0,
    max_rows_per_emotion: int = 0,
    emotions_allow: Optional[set[str]] = None,
) -> Dict[str, Any]:
    rows_total = 0
    used_rows = 0

    # Per-emotion aggregates
    rows = defaultdict(int)
    strong_hits = defaultdict(int)
    strong_den = defaultdict(int)
    cadence_hits = defaultdict(int)
    cadence_den = defaultdict(int)
    chord_rep_hits = defaultdict(int)
    chord_rep_den = defaultdict(int)
    root_leap_sum = defaultdict(float)
    root_leap_max = defaultdict(float)
    root_leap_n = defaultdict(int)

    for row_obj in _iter_jsonl(path):
        rows_total += 1
        if max_rows_total and used_rows >= int(max_rows_total):
            break

        emo = canonical_emotion_name(str(row_obj.get("emotion") or "neutral")) or "neutral"
        if emotions_allow is not None and emo not in emotions_allow:
            continue
        if max_rows_per_emotion and rows[emo] >= int(max_rows_per_emotion):
            continue

        melody = _iter_melody_events(row_obj)
        chords = row_obj.get("chord_sequence")
        beats_per_bar = float(row_obj.get("beats_per_bar", 4.0) or 4.0)
        if not melody or not isinstance(chords, list) or not chords:
            continue

        used_rows += 1
        rows[emo] += 1

        # Root leap proxy
        roots = row_obj.get("roots")
        if isinstance(roots, list) and len(roots) >= 2:
            try:
                rr = [int(x) for x in roots if x is not None]
                for a, b in zip(rr, rr[1:]):
                    d = abs(int(b) - int(a))
                    root_leap_sum[emo] += float(d)
                    root_leap_max[emo] = max(float(root_leap_max[emo]), float(d))
                    root_leap_n[emo] += 1
            except Exception:
                pass

        # Chord repetition rate (token-based if available)
        toks = row_obj.get("chord_markov_tokens")
        tok_list = [str(t or "") for t in toks] if isinstance(toks, list) and toks else [str(c or "") for c in chords]
        if len(tok_list) >= 2:
            for a, b in zip(tok_list, tok_list[1:]):
                chord_rep_den[emo] += 1
                if str(a) == str(b):
                    chord_rep_hits[emo] += 1

        # Strong-beat chord-tone rate
        try:
            # Keep consistent with runtime: use a small tolerance around strong beats.
            from audiogen_core.config import CONFIG

            eps = float(getattr(CONFIG.composition, "strong_beat_epsilon_beats", 0.06) or 0.06)
        except Exception:
            eps = 0.06
        eps = max(1e-6, min(0.25, float(eps)))
        t = 0.0
        for deg, dur in melody:
            d = int(deg)
            if d < 0:
                t += float(dur)
                continue
            bar = int(t // beats_per_bar) if beats_per_bar > 1e-9 else 0
            if bar < 0:
                bar = 0
            if bar >= len(chords):
                bar = len(chords) - 1
            beat_in_bar = float(t) - float(bar) * float(beats_per_bar)
            strong = _is_strong_beat(float(beat_in_bar), float(beats_per_bar), eps=float(eps))
            if strong:
                strong_den[emo] += 1
                tones = _chord_tone_degrees(str(chords[bar] or ""))
                if tones is not None and (int(d) % 7) in tones:
                    strong_hits[emo] += 1
            t += float(dur)

        # Cadence agreement: compare last voiced degree to last cadence target when present.
        voiced = [int(d) % 7 for d, _dur in melody if int(d) >= 0]
        if voiced:
            cadence_targets = row_obj.get("cadence_targets")
            if isinstance(cadence_targets, list) and cadence_targets:
                last = cadence_targets[-1] if isinstance(cadence_targets[-1], dict) else {}
                cad = last.get("cadence_degree")
                if cad is not None:
                    cadence_den[emo] += 1
                    try:
                        if int(voiced[-1]) == (int(cad) % 7):
                            cadence_hits[emo] += 1
                    except Exception:
                        pass

    emotions: Dict[str, Dict[str, Any]] = {}
    for emo in sorted(rows.keys()):
        r = int(rows[emo])
        sden = max(1, int(strong_den[emo]))
        cden = int(cadence_den[emo])
        repden = max(1, int(chord_rep_den[emo]))
        rn = int(root_leap_n[emo])
        metrics: Dict[str, Any] = {
            "rows": r,
            "strong_beat_chord_tone_rate": float(strong_hits[emo]) / float(sden),
            "cadence_agreement_rate": float(cadence_hits[emo]) / float(cden) if cden else 0.0,
            "cadence_agreement_n": int(cden),
            "chord_repeat_rate": float(chord_rep_hits[emo]) / float(repden),
            "root_leap_mean": float(root_leap_sum[emo]) / float(rn) if rn else 0.0,
            "root_leap_max": float(root_leap_max[emo]) if rn else 0.0,
        }

        warnings: list[str] = []
        if r < int(min_rows):
            warnings.append(f"low_rows:{r}")
        if metrics["strong_beat_chord_tone_rate"] < 0.55 and r >= int(min_rows):
            warnings.append(f"low_chord_tone_fit:{metrics['strong_beat_chord_tone_rate']:.3f}")
        if metrics["cadence_agreement_n"] >= int(min_rows) and metrics["cadence_agreement_rate"] < 0.55:
            warnings.append(f"weak_cadence_agreement:{metrics['cadence_agreement_rate']:.3f}")
        if metrics["chord_repeat_rate"] > 0.28 and r >= int(min_rows):
            warnings.append(f"too_repetitive_harmony:{metrics['chord_repeat_rate']:.3f}")
        metrics["warnings"] = warnings
        emotions[emo] = metrics

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
            f" fit={float(m.get('strong_beat_chord_tone_rate', 0.0)):.3f}"
            f" cad={float(m.get('cadence_agreement_rate', 0.0)):.3f}"
            f" rep={float(m.get('chord_repeat_rate', 0.0)):.3f}"
            f" rootLeapMean={float(m.get('root_leap_mean', 0.0)):.2f}"
            f" rootLeapMax={float(m.get('root_leap_max', 0.0)):.1f}"
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


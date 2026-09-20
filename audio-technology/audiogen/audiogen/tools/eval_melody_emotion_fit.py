from __future__ import annotations

import argparse
import json
import math
import statistics
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _extract_melody_events(events: List[Tuple]) -> List[Tuple[int, int, int, float, float, List[int]]]:
    """
    Filter a full event list down to melody-only events on channel 2.
    """
    out: List[Tuple[int, int, int, float, float, List[int]]] = []
    for ev in events:
        if not isinstance(ev, (list, tuple)) or len(ev) != 6:
            continue
        ch, midi, vel, start, dur, notes = ev
        try:
            ch_i = int(ch)
        except Exception:
            continue
        if ch_i != 2:
            continue
        out.append((int(ch), int(midi), int(vel), float(start), float(dur), list(notes or [])))
    return out


def _melody_features(
    events: List[Tuple[int, int, int, float, float, List[int]]],
    *,
    bars: int,
    beats_per_bar: float,
) -> Dict[str, float]:
    """
    Compute simple melodic features that correlate with emotional profile:
      - mean_pitch / pitch_range
      - step_vs_leap_ratio
      - note_density_per_bar
      - syncopation_ratio (share of onsets off the beat grid)
    """
    if not events:
        return {
            "mean_pitch": 0.0,
            "pitch_range": 0.0,
            "step_vs_leap_ratio": 0.0,
            "notes_per_bar": 0.0,
            "syncopation_ratio": 0.0,
        }

    pitches: List[int] = [int(e[1]) for e in events]
    starts: List[float] = [float(e[3]) for e in events]

    mean_pitch = float(statistics.fmean(pitches)) if pitches else 0.0
    pitch_range = float(max(pitches) - min(pitches)) if pitches else 0.0

    # Step vs leap (in scale degrees approximated by semitone distance).
    steps = 0
    leaps = 0
    for a, b in zip(pitches, pitches[1:]):
        d = abs(int(b) - int(a))
        if d <= 2:
            steps += 1
        elif d >= 4:
            leaps += 1
    step_vs_leap_ratio = float(steps) / float(max(1, leaps)) if leaps > 0 else float(steps)

    notes_per_bar = float(len(events)) / float(max(1.0, float(bars)))

    # Syncopation: fraction of onsets landing more than ~1/12 beat away from nearest 8th-note grid.
    sync_off = 0
    for t in starts:
        q = round(float(t) / 0.5)
        err = abs(float(t) - q * 0.5)
        if err > (1.0 / 12.0):
            sync_off += 1
    syncopation_ratio = float(sync_off) / float(max(1, len(starts)))

    return {
        "mean_pitch": _safe_float(mean_pitch),
        "pitch_range": _safe_float(pitch_range),
        "step_vs_leap_ratio": _safe_float(step_vs_leap_ratio),
        "notes_per_bar": _safe_float(notes_per_bar),
        "syncopation_ratio": _safe_float(syncopation_ratio),
    }


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument(
        "--emotions",
        default="joy,sadness,fear,love,nervousness,neutral",
        help="Comma-separated emotion names to evaluate (default: core contrasting set).",
    )
    ap.add_argument("--bars", type=int, default=16, help="Bars per section (default: 16)")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note (default: 60)")
    ap.add_argument(
        "--samples-per-emotion",
        type=int,
        default=4,
        help="Number of sections to sample per emotion (default: 4)",
    )
    ap.add_argument(
        "--output",
        default=".cache/melody_emotion_metrics.json",
        help="Output JSON path (default: .cache/melody_emotion_metrics.json)",
    )
    args = ap.parse_args()

    from composition.engine import CompositionGenerator
    from composition.policies import ArrangementPolicy
    from data.music_data import EMOTION_BY_NAME

    emotions = [e.strip().lower() for e in str(args.emotions).split(",") if e.strip()]
    bars = int(args.bars)
    beats_per_bar = 4.0
    k = max(1, int(args.samples_per_emotion))

    gen = CompositionGenerator(enable_perf_monitoring=False)
    pol = ArrangementPolicy()
    pol.form_mode = "default"
    gen.arrangement_policy.form_mode = "default"

    out: Dict[str, Any] = {
        "bars": bars,
        "beats_per_bar": beats_per_bar,
        "samples_per_emotion": k,
        "emotions": {},
    }

    # Use roles a (verse-like) and b (chorus-like) as contrasting contexts.
    role_cases = [(1, "a"), (3, "b")]

    for emo in emotions:
        profile = EMOTION_BY_NAME.get(emo)
        if profile is None:
            continue
        emo_res: Dict[str, Any] = {}
        for section_index, role in role_cases:
            samples: List[Dict[str, float]] = []
            for _ in range(k):
                ev = gen.generate_section(profile, root_note=int(args.root), bars=bars, section_index=int(section_index))
                mel = _extract_melody_events(ev)
                feats = _melody_features(mel, bars=bars, beats_per_bar=beats_per_bar)
                samples.append(feats)

            if not samples:
                continue

            agg: Dict[str, float] = {}
            keys = samples[0].keys()
            for key in keys:
                vals = [_safe_float(s.get(key, 0.0)) for s in samples]
                agg[f"{key}_mean"] = _safe_float(statistics.fmean(vals))
                if len(vals) > 1:
                    agg[f"{key}_std"] = _safe_float(statistics.pstdev(vals))
                else:
                    agg[f"{key}_std"] = 0.0

            emo_res[role] = agg

        out["emotions"][emo] = emo_res

    out_path = Path(str(args.output)).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


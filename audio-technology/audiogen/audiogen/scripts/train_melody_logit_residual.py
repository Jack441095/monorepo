#!/usr/bin/env python3
"""Fit Phase-2d linear interval logit residual from live melody JSONL (numpy ridge, one-vs-all)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


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


def _voiced_interval_examples(events: List[Tuple[int, float]]) -> List[Tuple[int, int]]:
    voiced = [(i, int(d)) for i, (d, _) in enumerate(events) if isinstance(d, int) and int(d) >= 0]
    if len(voiced) < 2:
        return []
    return [(voiced[i + 1][1] - voiced[i][1], voiced[i][0]) for i in range(len(voiced) - 1)]


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v or "").strip() for v in value if str(v or "").strip()]


def _event_beats(events: List[Tuple[int, float]]) -> List[float]:
    out: List[float] = []
    beat = 0.0
    for _, dur in events:
        out.append(float(beat))
        try:
            beat += abs(float(dur))
        except Exception:
            beat += 0.5
    return out


def _chord_for_event(row: Dict[str, Any], event_idx: int, event_beat: float) -> str:
    chords = _string_list(row.get("chord_sequence"))
    if not chords:
        return ""
    if 0 <= int(event_idx) < len(chords):
        return str(chords[int(event_idx)])
    try:
        beats_per_bar = max(0.25, float(row.get("beats_per_bar", 4.0) or 4.0))
    except Exception:
        beats_per_bar = 4.0
    bar = int(max(0.0, float(event_beat)) // beats_per_bar)
    return str(chords[min(max(0, bar), len(chords) - 1)])


def _phrase_value(row: Dict[str, Any], key: str, phrase_idx: int) -> str:
    values = _string_list(row.get(key))
    if not values:
        return ""
    return str(values[min(max(0, int(phrase_idx)), len(values) - 1)])


def main() -> int:
    # Ensure repo root is importable when running as a script.
    # (pytest invokes this via subprocess; sys.path[0] would otherwise be /scripts.)
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass

    from ai.markov.melody.logit_residual import (
        NUM_INTERVAL_CLASSES,
        encode_interval_residual_features,
        interval_class_index,
    )

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "jsonl",
        nargs="?",
        default=".cache/live_melody_training.jsonl",
        help="Input JSONL (same schema as export_live_melody_training).",
    )
    ap.add_argument(
        "-o",
        "--output",
        default="training_data/active_models/melody_logit_residual.npz",
        help="Output .npz path (W, order, version).",
    )
    ap.add_argument("--order", type=int, default=6, help="Context length (intervals).")
    ap.add_argument("--ridge", type=float, default=1e-2, help="Ridge lambda.")
    ap.add_argument("--min-accept", type=float, default=0.0, help="Skip rows with accept_score below this.")
    ap.add_argument("--min-notes", type=int, default=4, help="Skip melodies with fewer events.")
    args = ap.parse_args()

    order = max(1, min(24, int(args.order)))
    lam = max(1e-9, float(args.ridge))

    p = Path(args.jsonl)
    if not p.is_file():
        print(f"File not found: {p}", file=sys.stderr)
        return 1

    import numpy as np

    xs: List = []
    ys: List = []
    lines = 0
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
                if float(row.get("accept_score", 1.0) or 1.0) < float(args.min_accept):
                    continue
            except Exception:
                pass
            events = _iter_melody_events(row)
            if len(events) < int(args.min_notes):
                continue
            examples = _voiced_interval_examples(events)
            if len(examples) < 1:
                continue
            intervals = [iv for iv, _ in examples]
            emotion = str(row.get("emotion") or "")
            section_role = str(row.get("section_role") or "")
            beats = _event_beats(events)
            try:
                beats_per_bar = max(0.25, float(row.get("beats_per_bar", 4.0) or 4.0))
            except Exception:
                beats_per_bar = 4.0
            for t, (y, event_idx) in enumerate(examples):
                idx = interval_class_index(int(y))
                if idx is None:
                    continue
                ctx = intervals[max(0, t - order) : t]
                ctx = [0] * (order - len(ctx)) + ctx
                ctx = ctx[-order:]
                pos = float(t) / max(1.0, float(len(intervals) - 1)) if len(intervals) > 1 else 0.0
                event_beat = beats[event_idx] if 0 <= int(event_idx) < len(beats) else 0.0
                phrase_idx = int(max(0.0, float(event_beat)) // max(0.25, beats_per_bar * 4.0))
                x = encode_interval_residual_features(
                    ctx,
                    pos,
                    emotion,
                    order=order,
                    section_role=section_role,
                    phrase_role=_phrase_value(row, "phrase_roles", phrase_idx),
                    contour=_phrase_value(row, "phrase_contours", phrase_idx),
                    chord_symbol=_chord_for_event(row, event_idx, event_beat),
                    prev_duration=events[event_idx][1] if 0 <= int(event_idx) < len(events) else None,
                )
                xs.append(np.asarray(x, dtype=np.float64))
                one = np.zeros(NUM_INTERVAL_CLASSES, dtype=np.float64)
                one[int(idx)] = 1.0
                ys.append(one)

    if len(xs) < 32:
        print(f"Not enough training rows ({len(xs)}); need at least 32.", file=sys.stderr)
        return 2

    X = np.stack(xs, axis=0)
    Y = np.stack(ys, axis=0)
    n, f = X.shape
    xt_x = X.T @ X + lam * np.eye(f, dtype=np.float64)
    try:
        w_block = np.linalg.solve(xt_x, X.T @ Y)
    except np.linalg.LinAlgError:
        w_block = np.linalg.pinv(xt_x) @ (X.T @ Y)
    W = np.asarray(w_block.T, dtype=np.float64)
    if int(W.shape[0]) != NUM_INTERVAL_CLASSES or int(W.shape[1]) != f:
        print("Internal error: bad W shape", W.shape, file=sys.stderr)
        return 3

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        str(out),
        W=W.astype(np.float32),
        order=np.int32(order),
        version=np.int32(2),
        feature_dim=np.int32(f),
    )
    print(f"wrote {out}  W={W.shape}  samples={n}  jsonl_lines_read={lines}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

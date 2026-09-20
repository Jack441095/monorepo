from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _snap_err_mean(starts: List[float], grid: float) -> float:
    g = float(grid)
    if g <= 1e-12 or not starts:
        return 0.0
    errs = []
    for s in starts:
        q = round(float(s) / g)
        errs.append(abs(float(s) - float(q) * g))
    return float(sum(errs) / max(1, len(errs)))


def _motif_slot_windows_for_role(*, role: str, bars: int, beats_per_bar: float) -> List[Tuple[float, float]]:
    """
    Mirrors MotifPlanManager.slots_for_section() for the common 16-bar default case.
    This is intentionally approximate; it’s a regression metric, not a ground-truth proof.
    """
    total_beats = float(bars) * float(beats_per_bar)
    if bars <= 0:
        return []
    role = (role or "").strip().lower()
    if bars == 16:
        bar0 = 0.0
        bar8 = 8.0 * float(beats_per_bar)
        bar12 = 12.0 * float(beats_per_bar)
        if role == "a":
            return [(bar0, min(total_beats, bar0 + 4.0)), (min(bar8, total_beats), min(total_beats, bar8 + 4.0))]
        if role in {"pre_chorus"}:
            return [(min(bar12, total_beats), min(total_beats, bar12 + 4.0))]
        if role in {"b", "chorus", "hook"}:
            return [(bar0, min(total_beats, bar0 + 8.0)), (min(bar12, total_beats), min(total_beats, bar12 + 4.0))]
        if role in {"tag"}:
            return [(bar0, min(total_beats, bar0 + 4.0))]
    # fallback: chorus-like gets early slot, endings get late slot
    chorus_like = role in {"b", "chorus", "hook"}
    ending_like = role in {"tag", "outro", "ending"}
    if chorus_like:
        return [(0.0, min(total_beats, 8.0))]
    if ending_like:
        start = max(0.0, total_beats - min(8.0, total_beats))
        return [(start, min(total_beats, start + 8.0))]
    return []


def _in_any_window(t: float, windows: List[Tuple[float, float]]) -> bool:
    for a, b in windows:
        if float(a) - 1e-9 <= float(t) < float(b) - 1e-9:
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--emotions", default="admiration,neutral,optimism,anger,sadness,grief,relief", help="Comma-separated emotion names to evaluate")
    ap.add_argument("--bars", type=int, default=16, help="Bars per section (default: 16)")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note (default: 60)")
    ap.add_argument("--output", default=".cache/generator_metrics.json", help="Output JSON path (default: .cache/generator_metrics.json)")
    args = ap.parse_args()

    from composition.engine import CompositionGenerator
    from composition.policies import ArrangementPolicy
    from data.music_data import EMOTION_BY_NAME

    emotions = [e.strip().lower() for e in str(args.emotions).split(",") if e.strip()]
    bars = int(args.bars)
    beats_per_bar = 4.0

    gen = CompositionGenerator(enable_perf_monitoring=False)
    pol = ArrangementPolicy()
    pol.form_mode = "default"
    gen.arrangement_policy.form_mode = "default"

    out: Dict[str, Any] = {"bars": bars, "beats_per_bar": beats_per_bar, "emotions": {}}

    # Evaluate role a and role b (default form indices: 1='a', 3='b')
    role_cases = [(1, "a"), (3, "b")]

    for emo in emotions:
        em = EMOTION_BY_NAME.get(emo)
        if em is None:
            continue
        out["emotions"][emo] = {}
        for section_index, role in role_cases:
            ev = gen.generate_section(em, root_note=int(args.root), bars=bars, section_index=int(section_index))
            arp = [e for e in ev if len(e) == 6 and int(e[0]) == 3]
            mel = [e for e in ev if len(e) == 6 and int(e[0]) == 2]

            arp_starts = [float(e[3]) for e in arp]
            mel_starts = [float(e[3]) for e in mel]

            windows = _motif_slot_windows_for_role(role=role, bars=bars, beats_per_bar=beats_per_bar)
            mel_in_slots = sum(1 for t in mel_starts if _in_any_window(float(t), windows))
            mel_slot_share = float(mel_in_slots) / float(max(1, len(mel_starts)))

            # grid adherence: compare to 16th grid (0.25 beats)
            grid16_err_beats = _snap_err_mean(arp_starts, 0.25)

            out["emotions"][emo][role] = {
                "section_index": int(section_index),
                "arp_events": int(len(arp)),
                "arp_events_per_bar": float(len(arp) / max(1, bars)),
                "melody_events": int(len(mel)),
                "melody_events_per_bar": float(len(mel) / max(1, bars)),
                "arp_grid16_mean_abs_err_beats": float(grid16_err_beats),
                "melody_motif_slot_share": float(mel_slot_share),
            }

    out_path = Path(str(args.output)).expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


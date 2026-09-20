#!/usr/bin/env python3
"""
Offline generator for the live JOINT training JSONL.

This mirrors scripts/generate_live_melody_training_jsonl.py but uses the export hook
in composition/section_planner/planner.py to append rows that include:
- chords (+ chord_markov_tokens)
- bass
- lead melody
- arpeggio
- counter melody

Rows are aligned to the section harmonic plan (roots per bar + emotion scale).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


def _canonical(name: str) -> str:
    return str(name or "").strip().lower()


def _resolve_emotion_names(all_emotions: Iterable[object], requested: Optional[List[str]]) -> List[str]:
    names = [str(getattr(e, "name", "") or "") for e in list(all_emotions or [])]
    canon = {_canonical(n): n for n in names if _canonical(n)}
    if not requested:
        return [canon[k] for k in sorted(canon.keys())]
    out: List[str] = []
    for raw in requested:
        key = _canonical(raw)
        if not key:
            continue
        if key in canon:
            out.append(canon[key])
    seen = set()
    uniq: List[str] = []
    for n in out:
        k = _canonical(n)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(n)
    return uniq


def _split_jsonl_by_accept(
    *,
    raw_path: Path,
    kept_path: Path,
    rejects_path: Optional[Path],
    accept_threshold: float,
    dedup_kept: bool,
) -> Tuple[int, int]:
    kept = 0
    rej = 0
    seen_kept = set()
    kept_path.parent.mkdir(parents=True, exist_ok=True)
    if rejects_path is not None:
        rejects_path.parent.mkdir(parents=True, exist_ok=True)
    with raw_path.open("r", encoding="utf-8") as f_in, kept_path.open("w", encoding="utf-8") as f_keep:
        f_rej = rejects_path.open("w", encoding="utf-8") if rejects_path is not None else None
        try:
            for line in f_in:
                s = line.strip()
                if not s:
                    continue
                try:
                    row = json.loads(s)
                except json.JSONDecodeError:
                    continue
                try:
                    score = float(row.get("accept_score", 0.0) or 0.0)
                except Exception:
                    score = 0.0
                if score + 1e-9 >= float(accept_threshold):
                    if dedup_kept:
                        try:
                            # Dedup by chords+lead degrees (stable and small).
                            sig = {
                                "chords": row.get("chord_markov_tokens") or row.get("chord_sequence") or [],
                                "lead": (row.get("lead") or {}).get("degrees") or [],
                            }
                            k = json.dumps(sig, separators=(",", ":"), sort_keys=False)
                        except Exception:
                            k = s
                        if k in seen_kept:
                            continue
                        seen_kept.add(k)
                    f_keep.write(s + "\n")
                    kept += 1
                else:
                    if f_rej is not None:
                        f_rej.write(s + "\n")
                    rej += 1
        finally:
            if f_rej is not None:
                f_rej.close()
    return kept, rej


def main() -> int:
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        default=".cache/live_joint_training.jsonl",
        help="Output JSONL file path for KEPT rows (schema live_joint_training.v1).",
    )
    ap.add_argument(
        "--out-rejects",
        default="",
        help="Optional JSONL path to write rejected/low-score rows.",
    )
    ap.add_argument(
        "--accept-threshold",
        type=float,
        default=0.0,
        help="Split threshold: accept_score >= this is kept; below is reject (default: 0.0).",
    )
    ap.add_argument(
        "--dedup-kept",
        action="store_true",
        help="Deduplicate kept rows by chord+lead signature (recommended).",
    )
    ap.add_argument(
        "--per-emotion",
        type=int,
        default=64,
        help="Number of generated sections per emotion (default: 64).",
    )
    ap.add_argument(
        "--bars",
        type=int,
        default=16,
        help="Bars per generated section (default: 16).",
    )
    ap.add_argument(
        "--target-notes-per-bar",
        type=float,
        default=6.0,
        help="Target lead melody density for generation (default: 6.0).",
    )
    ap.add_argument(
        "--root",
        type=int,
        default=60,
        help="Root MIDI note for generation (default: 60).",
    )
    ap.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Base seed for deterministic generation (default: 0).",
    )
    ap.add_argument(
        "--temperature-min",
        type=float,
        default=0.55,
        help="Min temperature for generation jitter (default: 0.55).",
    )
    ap.add_argument(
        "--temperature-max",
        type=float,
        default=0.95,
        help="Max temperature for generation jitter (default: 0.95).",
    )
    ap.add_argument(
        "--root-jitter-semitones",
        type=int,
        default=5,
        help="Randomize root by +/- this many semitones per section (default: 5).",
    )
    ap.add_argument(
        "--npb-jitter",
        type=float,
        default=1.5,
        help="Randomize target-notes-per-bar by +/- this amount per section (default: 1.5).",
    )
    ap.add_argument(
        "--emotions",
        nargs="*",
        default=None,
        help="Optional list of emotion names to generate (default: all).",
    )
    ap.add_argument(
        "--append",
        action="store_true",
        help="Append to existing JSONL instead of overwriting it.",
    )
    ap.add_argument(
        "--split-existing-raw",
        action="store_true",
        help="Do not generate. Split the existing .raw.jsonl into kept/reject JSONL outputs.",
    )
    ap.add_argument(
        "--generate-only",
        action="store_true",
        help="Generate/append raw rows, but do not split raw into kept/reject outputs yet.",
    )
    ap.add_argument(
        "--disable-retrained-markov",
        action="store_true",
        help="Force-disable retrained melody/chord Markovs while generating the dataset.",
    )
    ap.add_argument(
        "--role-cycle-length",
        type=int,
        default=6,
        help="Cycle section_index through this many values to cover arrangement roles (default: 6).",
    )
    ap.add_argument(
        "--quality-mode",
        action="store_true",
        help="Enable offline-quality generation knobs (slower, cleaner training rows).",
    )
    ap.add_argument(
        "--quality-k-samples",
        type=int,
        default=6,
        help="Best-of-K section samples used by --quality-mode (default: 6; lower is faster).",
    )
    ap.add_argument(
        "--style",
        default="",
        help="Style profile name to apply (e.g. ambient, cinematic_minimal). See data/sample_style_profiles.py.",
    )
    args = ap.parse_args()

    kept_path = Path(str(args.out)).expanduser()
    if not kept_path.is_absolute():
        kept_path = Path.cwd() / kept_path
    rejects_path = None
    if str(args.out_rejects or "").strip():
        rejects_path = Path(str(args.out_rejects)).expanduser()
        if not rejects_path.is_absolute():
            rejects_path = Path.cwd() / rejects_path

    raw_path = kept_path.with_suffix(kept_path.suffix + ".raw.jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and not bool(args.append) and not bool(args.split_existing_raw):
        raw_path.unlink()

    if bool(args.split_existing_raw):
        if not raw_path.exists():
            print(f"raw file not found: {raw_path}", file=sys.stderr)
            return 2
        if kept_path.exists() and not bool(args.append):
            kept_path.unlink()
        if rejects_path is not None and rejects_path.exists() and not bool(args.append):
            rejects_path.unlink()
        kept, rej = _split_jsonl_by_accept(
            raw_path=raw_path,
            kept_path=kept_path,
            rejects_path=rejects_path,
            accept_threshold=float(args.accept_threshold),
            dedup_kept=bool(args.dedup_kept),
        )
        try:
            raw_path.unlink()
        except Exception:
            pass
        msg = f"done: kept={kept} rejects={rej} kept_path={kept_path}"
        if rejects_path is not None:
            msg += f" rejects_path={rejects_path}"
        print(msg)
        return 0

    from audiogen_core.config import CONFIG
    from audiogen_core.config_profiles import set_style_profile
    from data.music_data import EMOTIONS, EMOTION_BY_NAME
    from composition.engine import CompositionGenerator

    style_name = str(getattr(args, "style", "") or "").strip()
    if style_name:
        set_style_profile(CONFIG, style_name)

    # Enable the joint exporter (and disable the melody-only exporter to avoid double-logging).
    CONFIG.composition.export_live_joint_training_enabled = True
    CONFIG.composition.export_live_joint_training_path = str(raw_path)
    try:
        CONFIG.composition.export_live_melody_training_enabled = False
    except Exception:
        pass

    if bool(args.disable_retrained_markov):
        try:
            CONFIG.composition.melody_retrained_markov_enabled = False
        except Exception:
            pass
        try:
            CONFIG.composition.chord_retrained_markov_enabled = False
        except Exception:
            pass

    if bool(args.quality_mode):
        try:
            CONFIG.composition.offline_quality_render_enabled = True
        except Exception:
            pass
        try:
            quality_k = max(1, int(getattr(args, "quality_k_samples", 6) or 6))
            CONFIG.composition.section_k_samples = int(quality_k)
            CONFIG.composition.section_pick_use_wall_clock = False
        except Exception:
            pass

    names = _resolve_emotion_names(EMOTIONS, list(args.emotions) if args.emotions else None)
    if not names:
        print("No emotions selected (check --emotions).", file=sys.stderr)
        return 2

    per_emotion = max(1, int(args.per_emotion))
    bars = max(1, int(args.bars))
    root = int(args.root)
    target_npb = float(args.target_notes_per_bar)
    base_seed = int(args.seed)
    role_cycle = max(1, int(args.role_cycle_length))
    tmin = float(args.temperature_min)
    tmax = float(args.temperature_max)
    if tmax < tmin:
        tmin, tmax = tmax, tmin
    root_j = max(0, int(args.root_jitter_semitones))
    npb_j = max(0.0, float(args.npb_jitter))

    gen = CompositionGenerator(enable_perf_monitoring=False, use_voice_leading=True)

    total = 0
    for emo_idx, emo_name in enumerate(names):
        emo = EMOTION_BY_NAME.get(_canonical(emo_name))
        if emo is None:
            continue
        emo_rng = random.Random(int(base_seed) + (emo_idx * 100_003))
        try:
            gen.reseed(int(base_seed) + (emo_idx * 10_000_019))
        except Exception:
            pass
        try:
            gen.reset_song_arrangement_state()
        except Exception:
            pass
        for i in range(per_emotion):
            section_index = int(i % role_cycle)
            root_i = int(root) + int(emo_rng.randint(-root_j, root_j)) if root_j > 0 else int(root)
            npb_i = float(target_npb) + float(emo_rng.uniform(-npb_j, npb_j)) if npb_j > 1e-9 else float(target_npb)
            npb_i = float(max(1.0, min(16.0, npb_i)))
            temp_i = float(emo_rng.uniform(float(tmin), float(tmax)))
            _ = gen.generate_section(
                emo,
                root_note=int(root_i),
                bars=int(bars),
                temperature=float(temp_i),
                target_notes_per_bar=float(npb_i),
                melody_style="auto",
                humanization_scale=0.0,
                section_index=section_index,
            )
            total += 1
        print(f"generated emotion={emo_name} sections={per_emotion} (total={total}) -> {raw_path}")

    if bool(args.generate_only):
        print(f"generate-only: wrote raw rows to {raw_path}")
        return 0

    if kept_path.exists() and not bool(args.append):
        kept_path.unlink()
    if rejects_path is not None and rejects_path.exists() and not bool(args.append):
        rejects_path.unlink()
    kept, rej = _split_jsonl_by_accept(
        raw_path=raw_path,
        kept_path=kept_path,
        rejects_path=rejects_path,
        accept_threshold=float(args.accept_threshold),
        dedup_kept=bool(args.dedup_kept),
    )
    try:
        raw_path.unlink()
    except Exception:
        pass

    msg = f"done: kept={kept} rejects={rej} kept_path={kept_path}"
    if rejects_path is not None:
        msg += f" rejects_path={rejects_path}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


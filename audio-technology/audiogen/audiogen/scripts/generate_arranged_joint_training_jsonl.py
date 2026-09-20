#!/usr/bin/env python3
"""
Offline generator for **arranged-song** JOINT training JSONL.

Unlike `generate_live_joint_training_jsonl.py` (which generates one section at a time),
this script uses `composition.song_generator.SongGenerator` to generate *full arranged songs*
(intro→verse→pre→chorus... depending on `--form`), while still exporting **one JSONL row per
section** via the existing joint exporter hook.

This gives the planner real multi-section context (handoffs, blueprint, motif lifecycle)
while keeping the training row schema compatible with the existing offline trainers.
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
    # Keep user ordering, but drop duplicates.
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
    # Ensure repo root importable when running as a script.
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=".cache/arranged_joint_training.jsonl", help="Output JSONL file path for KEPT rows.")
    ap.add_argument("--out-rejects", default="", help="Optional JSONL path to write rejected/low-score rows.")
    ap.add_argument("--accept-threshold", type=float, default=0.0, help="Keep rows with accept_score >= this (default: 0.0).")
    ap.add_argument("--dedup-kept", action="store_true", help="Deduplicate kept rows by chord+lead signature (recommended).")

    ap.add_argument("--songs-per-emotion", type=int, default=8, help="How many full songs to generate per emotion (default: 8).")
    ap.add_argument("--bars-per-section", type=int, default=16, help="Base bars-per-section for form builders (default: 16).")
    ap.add_argument("--root", type=int, default=60, help="Root MIDI note for generation (default: 60).")
    ap.add_argument("--seed", type=int, default=0, help="Base seed for deterministic generation (default: 0).")
    ap.add_argument(
        "--form",
        default="default",
        choices=("default", "dialogue (call and response)", "swing"),
        help="Arranged form to generate (default: default).",
    )
    ap.add_argument("--base-tempo", type=float, default=70.0, help="Base tempo before emotion multiplier (default: 70).")
    ap.add_argument("--target-seconds", type=float, default=150.0, help="For forms that support it (e.g. pop_ext/ambient), target duration.")
    ap.add_argument("--max-bars", type=int, default=96, help="For forms that support it (e.g. pop_ext/ambient), cap bars (default: 96).")

    ap.add_argument("--emotions", nargs="*", default=None, help="Optional list of emotion names to generate (default: all).")
    ap.add_argument("--append", action="store_true", help="Append to existing JSONL instead of overwriting it.")
    ap.add_argument("--split-existing-raw", action="store_true", help="Do not generate. Split existing .raw.jsonl into kept/reject outputs.")
    ap.add_argument("--generate-only", action="store_true", help="Generate raw rows but do not split into kept/reject yet.")

    ap.add_argument("--disable-retrained-markov", action="store_true", help="Force-disable retrained melody/chord Markovs while generating.")
    ap.add_argument("--quality-mode", action="store_true", help="Enable offline-quality generation knobs (slower, cleaner).")
    ap.add_argument("--quality-k-samples", type=int, default=6, help="Best-of-K section samples in quality mode (default: 6).")
    ap.add_argument("--style", default="", help="Style profile name to apply (e.g. cinematic_minimal).")

    args = ap.parse_args()

    kept_path = Path(str(args.out)).expanduser()
    rejects_path = Path(str(args.out_rejects)).expanduser() if str(args.out_rejects).strip() else None
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
    from data.music_data import EMOTIONS
    from composition.engine import CompositionGenerator
    from composition.song_generator import SongGenerator

    style_name = str(getattr(args, "style", "") or "").strip()
    if style_name:
        set_style_profile(CONFIG, style_name)

    # Enable the joint exporter (and disable melody-only exporter to avoid double-logging).
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

    songs_per_emotion = max(1, int(args.songs_per_emotion))
    bars_per_section = max(4, int(args.bars_per_section))
    root = int(args.root)
    base_seed = int(args.seed)
    base_tempo = float(args.base_tempo)
    form = str(args.form or "default").strip()

    gen = CompositionGenerator(enable_perf_monitoring=False, use_voice_leading=True)
    sg = SongGenerator(composer=gen)

    total_songs = 0
    for emo_idx, emo_name in enumerate(names):
        emo_rng = random.Random(int(base_seed) + (emo_idx * 100_003))
        for j in range(songs_per_emotion):
            seed_j = int(base_seed) + int(emo_idx) * 10_000_019 + int(j) * 1_000_003
            # Light root drift per song for key variety.
            root_j = int(root) + int(emo_rng.randint(-5, 5))
            if form == "dialogue (call and response)":
                sections = SongGenerator.pop_form(str(emo_name), bars_per_section=int(bars_per_section), root_note=int(root_j))
            elif form == "swing":
                sections = SongGenerator.default_form(str(emo_name), bars_per_section=int(bars_per_section), root_note=int(root_j))
            else:
                sections = SongGenerator.default_form(str(emo_name), bars_per_section=int(bars_per_section), root_note=int(root_j))

            # This generates the whole song; exporter hook writes per-section rows.
            _ = sg.generate_song(sections, base_tempo_bpm=float(base_tempo), arrangement_form=str(form), seed=int(seed_j))
            total_songs += 1
        print(f"generated emotion={emo_name} songs={songs_per_emotion} (total_songs={total_songs}) -> {raw_path}")

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


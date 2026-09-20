#!/usr/bin/env python3
"""
Offline generator for the live melody training JSONL.

This avoids realtime playback: it simply runs the composition generator for each
emotion and relies on the existing JSONL hook inside melody generation to append
rows to the configured output path.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


_TENDER_HARMONY_GATE_EMOTIONS = {
    "love",
    "remorse",
    "caring",
    "embarrassment",
    "sadness",
    "disappointment",
    "relief",
    "grief",
}


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
    uniq = []
    for n in out:
        k = _canonical(n)
        if k in seen:
            continue
        seen.add(k)
        uniq.append(n)
    return uniq


def _iter_melody_events(row: Dict[str, Any]) -> List[Tuple[int, float]]:
    out: List[Tuple[int, float]] = []
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
    roman = []
    i = 0
    while i < len(s) and s[i] in "#b":
        i += 1
    while i < len(s) and s[i] in "ivIV":
        roman.append(s[i])
        i += 1
    if not roman:
        return None
    table = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}
    return table.get("".join(roman).upper())


def _chord_tone_degrees(chord_symbol: str) -> Optional[set[int]]:
    root = _roman_root_degree(chord_symbol)
    if root is None:
        return None
    return {int(root) % 7, int(root + 2) % 7, int(root + 4) % 7}


def _is_strong_beat(beat_in_bar: float, beats_per_bar: float, eps: float = 0.06) -> bool:
    bpb = float(beats_per_bar) if float(beats_per_bar) > 1e-9 else 4.0
    x = float(beat_in_bar)
    e = max(1e-9, float(eps))
    d0 = min(abs(x - 0.0), abs(x - bpb))
    dmid = abs(x - (bpb / 2.0))
    return (d0 <= e) or (dmid <= e)


def _row_strongbeat_chord_tone_rate(row: Dict[str, Any]) -> Optional[float]:
    melody = _iter_melody_events(row)
    chords = row.get("chord_sequence")
    if not melody or not isinstance(chords, list) or not chords:
        return None
    beats_per_bar = float(row.get("beats_per_bar", 4.0) or 4.0)
    strong_hits = 0
    strong_den = 0
    t = 0.0
    for deg, dur in melody:
        d = int(deg)
        if d < 0:
            t += float(dur)
            continue
        bar = int(t // beats_per_bar) if beats_per_bar > 1e-9 else 0
        bar = max(0, min(bar, len(chords) - 1))
        beat_in_bar = float(t) - float(bar) * float(beats_per_bar)
        if _is_strong_beat(beat_in_bar, beats_per_bar):
            strong_den += 1
            tones = _chord_tone_degrees(str(chords[bar] or ""))
            if tones is not None and (int(d) % 7) in tones:
                strong_hits += 1
        t += float(dur)
    if strong_den <= 0:
        return None
    return float(strong_hits) / float(strong_den)


def _split_jsonl_by_accept(
    *,
    raw_path: Path,
    kept_path: Path,
    rejects_path: Optional[Path],
    accept_threshold: float,
    dedup_kept: bool,
    min_strongbeat_fit: float = 0.0,
    tender_min_strongbeat_fit: float = 0.0,
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
                keep = score + 1e-9 >= float(accept_threshold)
                if keep:
                    fit = _row_strongbeat_chord_tone_rate(row)
                    try:
                        emotion_name = _canonical(str(row.get("emotion", "") or ""))
                    except Exception:
                        emotion_name = ""
                    fit_floor = float(min_strongbeat_fit)
                    if emotion_name in _TENDER_HARMONY_GATE_EMOTIONS:
                        fit_floor = max(float(fit_floor), float(tender_min_strongbeat_fit))
                    if fit is not None and fit + 1e-9 < float(fit_floor):
                        keep = False
                        row["split_reject_reason"] = f"low_strongbeat_fit:{fit:.3f}<{fit_floor:.3f}"
                        s = json.dumps(row, ensure_ascii=True)
                if keep:
                    if dedup_kept:
                        try:
                            events = row.get("melody") or []
                            k = json.dumps(events, separators=(",", ":"), sort_keys=False)
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


def _append_file(src: Path, dst) -> int:
    n = 0
    with src.open("r", encoding="utf-8") as f_in:
        for line in f_in:
            if not line:
                continue
            dst.write(line)
            n += 1
    return n


def _parse_bool(s: str) -> bool:
    v = str(s or "").strip().lower()
    if v in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if v in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"invalid boolean: {s!r}")


def _coerce_like(value_s: str, like_value):
    """
    Coerce a CLI string into the type of an existing config value.
    Falls back to float/int/bool parsing heuristics when needed.
    """
    if isinstance(like_value, bool):
        return bool(_parse_bool(value_s))
    if isinstance(like_value, int) and not isinstance(like_value, bool):
        return int(str(value_s).strip())
    if isinstance(like_value, float):
        return float(str(value_s).strip())
    # Fallbacks
    vs = str(value_s).strip()
    try:
        return bool(_parse_bool(vs))
    except Exception:
        pass
    try:
        if "." in vs or "e" in vs.lower():
            return float(vs)
        return int(vs)
    except Exception:
        return vs


def _apply_composition_overrides(pairs: List[str]) -> None:
    if not pairs:
        return
    from audiogen_core.config import CONFIG

    for item in list(pairs or []):
        s = str(item or "").strip()
        if not s:
            continue
        if "=" not in s:
            raise ValueError(f"--set-composition expects KEY=VALUE, got {s!r}")
        k, v = s.split("=", 1)
        key = str(k).strip()
        if not key:
            raise ValueError(f"empty key in override: {s!r}")
        if not hasattr(CONFIG.composition, key):
            raise AttributeError(f"CONFIG.composition has no attribute {key!r}")
        cur = getattr(CONFIG.composition, key)
        new_val = _coerce_like(str(v), cur)
        setattr(CONFIG.composition, key, new_val)


def main() -> int:
    # Ensure repo root is importable when running as a script.
    try:
        root = Path(__file__).resolve().parent.parent
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    except Exception:
        pass

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        default=".cache/live_melody_training.jsonl",
        help="Output JSONL file path for KEPT rows (same schema as export_live_melody_training).",
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
        help="Deduplicate kept rows by melody content (recommended).",
    )
    ap.add_argument(
        "--min-strongbeat-fit",
        type=float,
        default=0.0,
        help="Reject rows whose per-row strong-beat chord-tone rate is below this floor (default: 0.0 = disabled).",
    )
    ap.add_argument(
        "--tender-min-strongbeat-fit",
        type=float,
        default=0.0,
        help="Stricter strong-beat fit floor for tender/low-energy emotions like caring, embarrassment, remorse, sadness (default: 0.0 = disabled).",
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
        help="Target melody density for generation (default: 6.0).",
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
        help="Force-disable melody_retrained_markov while generating the dataset.",
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
    ap.add_argument(
        "--set-composition",
        action="append",
        default=[],
        help="Override CONFIG.composition key/value (repeatable). Example: --set-composition melody_strongbeat_chord_tone_mult=3.25",
    )
    ap.add_argument(
        "--disable-voice-leading",
        action="store_true",
        help="Bypass global harmony voice-leading during dataset generation (much faster; useful for melody training).",
    )
    ap.add_argument(
        "--reset-song-state-every",
        type=int,
        default=0,
        help="If >0, call reset_song_arrangement_state() every N sections (default: 0 = never).",
    )
    ap.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel worker count across emotions (default: 1 = sequential).",
    )
    ap.add_argument(
        "--emotion-seed-offset",
        type=int,
        default=0,
        help="Internal: offset added to per-emotion deterministic seed index.",
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

    # We always write to a raw temp JSONL via the existing export hook, then split.
    raw_path = kept_path.with_suffix(kept_path.suffix + ".raw.jsonl")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    if raw_path.exists() and not bool(args.append) and not bool(args.split_existing_raw):
        raw_path.unlink()

    if bool(args.split_existing_raw):
        if not raw_path.exists():
            print(
                f"raw file not found: {raw_path}\n"
                "  After a full generation, the .raw.jsonl is deleted once split into the kept output.\n"
                "  If you already have the final --out JSONL, nothing to do. Otherwise re-run without "
                "--split-existing-raw, or keep a .raw file from a generation that was interrupted.",
                file=sys.stderr,
            )
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
            min_strongbeat_fit=float(args.min_strongbeat_fit),
            tender_min_strongbeat_fit=float(args.tender_min_strongbeat_fit),
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

    from data.music_data import EMOTIONS, EMOTION_BY_NAME

    names = _resolve_emotion_names(EMOTIONS, list(args.emotions) if args.emotions else None)
    if not names:
        print("No emotions selected (check --emotions).", file=sys.stderr)
        return 2

    jobs = max(1, int(getattr(args, "jobs", 1) or 1))
    if jobs > 1 and len(names) > 1:
        tmp_dir = raw_path.parent / f".parallel_raw_{int(time.time())}_{int(time.process_time_ns() % 1_000_000_000)}"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        workers = min(int(jobs), int(len(names)))
        print(f"parallel generation: emotions={len(names)} jobs={workers} tmp={tmp_dir}")
        procs = []
        worker_raws: List[Tuple[int, str, Path]] = []
        for emo_idx, emo_name in enumerate(names):
            emo_out = tmp_dir / f"{int(emo_idx):03d}_{_canonical(emo_name)}.jsonl"
            worker_cmd = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--out",
                str(emo_out),
                "--per-emotion",
                str(int(args.per_emotion)),
                "--bars",
                str(int(args.bars)),
                "--target-notes-per-bar",
                str(float(args.target_notes_per_bar)),
                "--root",
                str(int(args.root)),
                "--seed",
                str(int(args.seed)),
                "--temperature-min",
                str(float(args.temperature_min)),
                "--temperature-max",
                str(float(args.temperature_max)),
                "--root-jitter-semitones",
                str(int(args.root_jitter_semitones)),
                "--npb-jitter",
                str(float(args.npb_jitter)),
                "--role-cycle-length",
                str(int(args.role_cycle_length)),
                "--reset-song-state-every",
                str(int(args.reset_song_state_every)),
                "--emotions",
                str(emo_name),
                "--generate-only",
                "--jobs",
                "1",
                "--emotion-seed-offset",
                str(int(args.emotion_seed_offset) + int(emo_idx)),
            ]
            if bool(args.disable_retrained_markov):
                worker_cmd.append("--disable-retrained-markov")
            if bool(args.quality_mode):
                worker_cmd.extend(["--quality-mode", "--quality-k-samples", str(int(args.quality_k_samples))])
            if bool(args.disable_voice_leading):
                worker_cmd.append("--disable-voice-leading")
            if str(args.style or "").strip():
                worker_cmd.extend(["--style", str(args.style).strip()])
            procs.append((int(emo_idx), str(emo_name), subprocess.Popen(worker_cmd, cwd=str(root))))
            worker_raws.append((int(emo_idx), str(emo_name), emo_out.with_suffix(emo_out.suffix + ".raw.jsonl")))
            while len(procs) >= workers:
                idx0, name0, p0 = procs.pop(0)
                rc0 = int(p0.wait())
                if rc0 != 0:
                    print(f"parallel worker failed: emotion={name0} rc={rc0}", file=sys.stderr)
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return rc0
        for idx0, name0, p0 in procs:
            rc0 = int(p0.wait())
            if rc0 != 0:
                print(f"parallel worker failed: emotion={name0} rc={rc0}", file=sys.stderr)
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return rc0

        mode = "a" if bool(args.append) else "w"
        merged_lines = 0
        with raw_path.open(mode, encoding="utf-8") as f_raw:
            for emo_idx, emo_name, wr in sorted(worker_raws, key=lambda x: x[0]):
                if not wr.exists():
                    print(f"parallel worker missing raw output: emotion={emo_name} path={wr}", file=sys.stderr)
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                    return 2
                n = _append_file(wr, f_raw)
                merged_lines += int(n)
                print(f"merged emotion={emo_name} lines={n}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"parallel merge complete: lines={merged_lines} -> {raw_path}")

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
            min_strongbeat_fit=float(args.min_strongbeat_fit),
            tender_min_strongbeat_fit=float(args.tender_min_strongbeat_fit),
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
    from composition.engine import CompositionGenerator

    style_name = str(getattr(args, "style", "") or "").strip()
    if style_name:
        set_style_profile(CONFIG, style_name)
    try:
        _apply_composition_overrides(list(getattr(args, "set_composition", []) or []))
    except Exception as exc:
        print(f"failed to apply --set-composition overrides: {exc}", file=sys.stderr)
        return 2

    CONFIG.composition.export_live_melody_training_enabled = True
    CONFIG.composition.export_live_melody_training_path = str(raw_path)
    if bool(args.disable_retrained_markov):
        try:
            CONFIG.composition.melody_retrained_markov_enabled = False
        except Exception:
            pass

    if bool(args.quality_mode):
        # Best-effort: turn on offline-quality tuning knobs when available.
        try:
            CONFIG.composition.offline_quality_render_enabled = True
        except Exception:
            pass
        try:
            # Increase best-of-K attempts (deterministic if wall clock budgets are disabled).
            quality_k = max(1, int(getattr(args, "quality_k_samples", 6) or 6))
            CONFIG.composition.section_k_samples = int(quality_k)
            CONFIG.composition.section_pick_use_wall_clock = False
            CONFIG.composition.section_pick_time_budget_s = float(getattr(CONFIG.composition, "section_pick_time_budget_s", 0.75) or 0.75)
        except Exception:
            pass

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

    gen = CompositionGenerator(
        enable_perf_monitoring=False,
        use_voice_leading=not bool(args.disable_voice_leading),
    )

    total = 0
    seed_offset = int(getattr(args, "emotion_seed_offset", 0) or 0)
    for emo_idx, emo_name in enumerate(names):
        seed_idx = int(seed_offset) + int(emo_idx)
        emo = EMOTION_BY_NAME.get(_canonical(emo_name))
        if emo is None:
            continue
        reset_every = int(getattr(args, "reset_song_state_every", 0) or 0)
        if reset_every < 0:
            reset_every = 0
        # Deterministic but evolving RNG per emotion so we don't repeat identical outputs.
        emo_rng = random.Random(int(base_seed) + (seed_idx * 100_003))
        try:
            gen.reseed(int(base_seed) + (seed_idx * 10_000_019))
        except Exception:
            pass
        # Start each emotion from a clean slate, but do NOT reset every sample (helps reduce duplicates).
        try:
            gen.reset_song_arrangement_state()
        except Exception:
            pass
        for i in range(per_emotion):
            if reset_every > 0 and i > 0 and (i % reset_every) == 0:
                try:
                    gen.reset_song_arrangement_state()
                except Exception:
                    pass
            # Encourage section_role coverage via arrangement_policy.section_role(section_index).
            section_index = int(i % role_cycle)
            root_i = int(root)
            if root_j > 0:
                root_i = int(root) + int(emo_rng.randint(-root_j, root_j))
            npb_i = float(target_npb)
            if npb_j > 1e-9:
                npb_i = float(target_npb) + float(emo_rng.uniform(-npb_j, npb_j))
            npb_i = float(max(1.0, min(16.0, npb_i)))
            temp_i = float(emo_rng.uniform(float(tmin), float(tmax)))
            _ = gen.generate_section(
                emo,
                root_note=int(root_i),
                bars=int(bars),
                temperature=float(temp_i),
                target_notes_per_bar=float(npb_i),
                melody_style="auto",
                humanization_scale=0.0,  # keep training rows aligned with pre-humanization export
                section_index=section_index,
            )
            total += 1
        print(f"generated emotion={emo_name} sections={per_emotion} (total={total}) -> {raw_path}")

    if bool(args.generate_only):
        print(f"generate-only: wrote raw rows to {raw_path}")
        return 0

    # Split raw -> kept/rejects
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
        min_strongbeat_fit=float(args.min_strongbeat_fit),
        tender_min_strongbeat_fit=float(args.tender_min_strongbeat_fit),
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

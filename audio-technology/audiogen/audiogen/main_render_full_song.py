from __future__ import annotations

import argparse
import logging
import os
import random
import re
import sys
from pathlib import Path
from typing import Optional, Sequence

from audiogen_core.config import CONFIG
from audiogen_core.config_utils import resolve_project_path


def _resolve_default_preset_name() -> Optional[str]:
    env = str(os.environ.get("AUDIOGEN_DEFAULT_PRESET", "") or "").strip()
    if env:
        return env
    try:
        p = Path(__file__).resolve().parent / ".audiogen" / "default_preset.txt"
        if p.exists():
            name = str(p.read_text(encoding="utf-8")).strip()
            if name:
                return name
    except Exception:
        pass
    return None


def _list_emotions() -> Sequence[str]:
    try:
        from data.music_data import EMOTION_BY_NAME

        return sorted(str(k) for k in (EMOTION_BY_NAME or {}).keys() if str(k))
    except Exception:
        return []


def _list_presets() -> Sequence[str]:
    # Default-only repo: meta presets are disabled.
    return []


def _pick_emotion_from_pool(pool_name: str, *, seed: Optional[int] = None) -> str:
    from composition.song_generator import SongGenerator

    pools = dict(getattr(SongGenerator, "_EMOTION_POOLS", {}) or {})
    key = str(pool_name or "").strip().lower()
    seq = pools.get(key)
    if not seq:
        raise ValueError(f"Unknown emotion pool '{pool_name}'. Available: {', '.join(sorted(pools.keys()))}")
    rng = random.Random(int(seed)) if seed is not None else random.Random()
    return str(rng.choice(list(seq))).strip().lower()


def _emotion_index_by_name(name: str) -> int:
    from data.music_data import EMOTIONS

    q = str(name or "").strip().lower()
    if not q:
        return -1
    for i, emo in enumerate(list(EMOTIONS or [])):
        try:
            if str(getattr(emo, "name", "") or "").strip().lower() == q:
                return int(i)
        except Exception:
            continue
    return -1


def _select_emotion_compact(*, default_name: str = "neutral") -> str:
    """
    Main-like emotion chooser.

    - shows numbered emotions 0..27
    - accepts name or index
    - '?' shows the list again
    - Enter selects neutral
    """
    from data.music_data import EMOTIONS

    neutral_idx = _emotion_index_by_name(str(default_name))
    neutral_idx = int(neutral_idx) if 0 <= int(neutral_idx) < len(EMOTIONS) else 0
    try:
        if not sys.stdin.isatty():
            return str(getattr(EMOTIONS[int(neutral_idx)], "name", "neutral") or "neutral").strip().lower()
    except Exception:
        return str(getattr(EMOTIONS[int(neutral_idx)], "name", "neutral") or "neutral").strip().lower()

    def _print_emotions() -> None:
        try:
            sys.stdout.write("\nEmotions:\n")
            sys.stdout.write(f"  0: {EMOTIONS[int(neutral_idx)].name} (neutral)\n")
            max_display_index = min(27, len(EMOTIONS) - 1)
            for i in range(1, max_display_index + 1):
                sys.stdout.write(f"  {i}: {getattr(EMOTIONS[int(i)], 'name', f'emo-{i}')}\n")
            sys.stdout.write("\n")
            sys.stdout.flush()
        except Exception:
            pass

    _print_emotions()

    while True:
        try:
            sys.stdout.write("select emotion (name/index, '?' to list, Enter=neutral): ")
            sys.stdout.flush()
            line = sys.stdin.readline()
        except Exception:
            return str(getattr(EMOTIONS[int(neutral_idx)], "name", "neutral") or "neutral").strip().lower()
        if not line:
            return str(getattr(EMOTIONS[int(neutral_idx)], "name", "neutral") or "neutral").strip().lower()
        s = (line or "").strip()
        if s == "":
            return str(getattr(EMOTIONS[int(neutral_idx)], "name", "neutral") or "neutral").strip().lower()
        if s in {"?", "list", "ls"}:
            _print_emotions()
            continue
        if re.fullmatch(r"-?\d+", s):
            try:
                idx = int(s)
            except Exception:
                idx = int(neutral_idx)
            if idx == 0:
                return str(getattr(EMOTIONS[int(neutral_idx)], "name", "neutral") or "neutral").strip().lower()
            if 0 <= idx < len(EMOTIONS) and idx <= 27:
                return str(getattr(EMOTIONS[int(idx)], "name", "neutral") or "neutral").strip().lower()
            sys.stdout.write("Out of range. Use 0-27 (or '?' to list).\n")
            sys.stdout.flush()
            continue
        idx_by_name = _emotion_index_by_name(s)
        if 0 <= int(idx_by_name) < len(EMOTIONS):
            return str(getattr(EMOTIONS[int(idx_by_name)], "name", "neutral") or "neutral").strip().lower()
        sys.stdout.write("Unknown emotion. Type '?' to list.\n")
        sys.stdout.flush()


def _apply_preset_and_overrides(args: argparse.Namespace) -> None:
    CONFIG.set_performance_mode(str(getattr(args, "performance", "quality") or "quality"))
    rerank_model = getattr(args, "song_rerank_model", None)
    if rerank_model:
        CONFIG.composition.song_rerank_model_path = str(rerank_model)
    if bool(getattr(args, "legacy_composition", False)):
        from audiogen_core.song_upgrade_profile import apply_legacy_composition_profile

        apply_legacy_composition_profile(CONFIG)
    elif bool(getattr(args, "song_upgrade_phase_c", False)):
        from audiogen_core.song_upgrade_profile import apply_phase_c_profile

        apply_phase_c_profile(CONFIG)
    elif bool(getattr(args, "song_upgrade_phase_b", False)):
        from audiogen_core.song_upgrade_profile import apply_phase_b_profile

        apply_phase_b_profile(
            CONFIG,
            model_path=str(getattr(args, "song_rerank_model", "") or "artifacts/song_rerank/rerank_v1.json"),
        )
    elif bool(getattr(args, "song_upgrade_phase_a", False)):
        from audiogen_core.song_upgrade_profile import apply_phase_a_profile

        apply_phase_a_profile(CONFIG)
    # Default-only repo: presets/packs/styles/FX macros are intentionally disabled.
    if args.arrangement:
        try:
            CONFIG.composition.arranged_song_mode = str(args.arrangement)
        except Exception:
            pass


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate a full arranged song and export to WAV/MIDI.")
    p.add_argument("--emotion", default=None, help="Emotion name to render (e.g. joy, sadness).")
    p.add_argument(
        "--emotion-type",
        "--emotion-pool",
        dest="emotion_pool",
        default=None,
        help="Pick a random emotion from a pool (warm/bright/dark/tense/curious/calm/resolve). Used only if --emotion is not set.",
    )
    p.add_argument("--list-emotions", action="store_true", help="Print available emotion names and exit.")
    p.add_argument("--list-presets", action="store_true", help="Print available meta presets and exit.")
    p.add_argument(
        "--form",
        default="default",
        choices=["default", "dialogue (call and response)", "swing"],
        help="Arrangement form.",
    )
    p.add_argument("--bars", type=int, default=8, help="Bars per section (varies by form).")
    p.add_argument("--root", type=int, default=60, help="Root MIDI note (e.g. 60=C4).")
    p.add_argument("--tempo", type=float, default=None, help="Base tempo BPM (default: config).")
    p.add_argument("--seed", type=int, default=None, help="Seed for deterministic generation.")
    p.add_argument("--k", type=int, default=1, help="Best-of-K candidates to generate and pick from.")
    p.add_argument("--time-budget-s", type=float, default=None, help="Optional wall-clock budget for best-of-K.")
    p.add_argument("--closed-loop", action="store_true", help="Enable Phase 11 closed-loop self-correction.")
    p.add_argument("--mix-goal", default="club", help="Mix goal for closed-loop analysis (default: club).")

    p.add_argument("--export-dir", default="exports", help="Output directory.")
    p.add_argument("--prefix", default="song", help="Filename prefix.")
    p.add_argument("--no-wav", action="store_true", help="Disable WAV export.")
    p.add_argument("--no-midi", action="store_true", help="Disable MIDI export.")
    p.add_argument("--no-report", action="store_true", help="Disable JSON report export.")
    p.add_argument(
        "--export-stems",
        action="store_true",
        help="Also export one WAV per mixer channel (bass/chords/melody/arp/drone/counter_melody/kick).",
    )

    p.add_argument("--performance", default="quality", help="Performance mode (e.g. quality/high/safe).")
    p.add_argument("--preset", default=None, help="Meta preset name from .audiogen/presets.")
    p.add_argument("--pack", default=None, help="Explicit sample pack override.")
    p.add_argument("--style", default=None, help="Explicit style profile override.")
    p.add_argument("--fx", default=None, help="Explicit FX preset override.")
    p.add_argument("--arrangement", default=None, help="Composition arranged_song_mode override.")
    p.add_argument(
        "--song-upgrade-phase-a",
        action="store_true",
        help="Enable Phase A offline profile: audit-aligned rerank, joint section sampling, stronger best-of-K.",
    )
    p.add_argument(
        "--song-upgrade-phase-b",
        action="store_true",
        help="Enable Phase B: Phase A + learned rerank model path + candidate JSONL logging.",
    )
    p.add_argument(
        "--song-upgrade-phase-c",
        action="store_true",
        help="Re-apply Phase C profile (default on CONFIG; joint plan + Markov hook conditioning).",
    )
    p.add_argument(
        "--legacy-composition",
        action="store_true",
        help="Disable song-upgrade profiles (pre Phase A/C behavior).",
    )
    p.add_argument(
        "--song-rerank-model",
        default=None,
        help="Override song_rerank_model_path (JSON ridge weights).",
    )

    return p


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_arg_parser().parse_args()

    if bool(getattr(args, "list_emotions", False)):
        for nm in _list_emotions():
            print(nm)
        return 0
    if bool(getattr(args, "list_presets", False)):
        logging.info("Meta presets are disabled in this default-only repo.")
        return 0

    _apply_preset_and_overrides(args)

    from composition.song_generator import SongGenerator
    from tools.full_song_render import write_full_song_outputs

    if args.emotion:
        raw = str(args.emotion).strip()
        if re.fullmatch(r"-?\d+", raw):
            from data.music_data import EMOTIONS

            idx = int(raw)
            if idx == 0:
                emotion = "neutral"
            elif 0 <= idx < len(EMOTIONS) and idx <= 27:
                emotion = str(getattr(EMOTIONS[int(idx)], "name", "neutral") or "neutral").strip().lower()
            else:
                raise SystemExit(f"--emotion index out of range: {idx} (allowed 0-27)")
        else:
            emotion = raw.lower()
    elif getattr(args, "emotion_pool", None):
        emotion = _pick_emotion_from_pool(str(args.emotion_pool), seed=getattr(args, "seed", None))
        logging.info("Picked emotion from pool '%s': %s", str(args.emotion_pool), str(emotion))
    else:
        emotion = _select_emotion_compact(default_name="neutral")
    form = str(args.form or "default").strip()
    root = int(args.root)
    bars = int(args.bars)

    tempo = args.tempo
    if tempo is None:
        try:
            tempo = float(getattr(CONFIG.composition, "default_tempo", 70.0) or 70.0)
        except Exception:
            tempo = 70.0

    gen = SongGenerator()
    if form == "dialogue (call and response)":
        # Uses the legacy `pop` section arc, but the user-facing label is "dialogue".
        sections = SongGenerator.pop_form(emotion, bars_per_section=bars, root_note=root)
        arrangement_form = "dialogue (call and response)"
    elif form == "swing":
        sections = SongGenerator.default_form(emotion, bars_per_section=bars, root_note=root)
        arrangement_form = "swing"
    else:
        sections = SongGenerator.default_form(emotion, bars_per_section=bars, root_note=root)
        arrangement_form = "default"

    total_bars = int(sum(int(s.bars) for s in sections)) if sections else 0

    song_render = gen.generate_song_best_of_k(
        sections,
        base_tempo_bpm=float(tempo),
        arrangement_form=str(arrangement_form),
        seed=args.seed,
        k=int(max(1, args.k)),
        time_budget_s=args.time_budget_s,
        closed_loop=bool(args.closed_loop),
        mix_goal=str(args.mix_goal),
    )

    outputs = write_full_song_outputs(
        config=CONFIG,
        song_events=list(getattr(song_render, "events", []) or []),
        total_bars=int(total_bars),
        song_render=song_render,
        export_dir=resolve_project_path(str(args.export_dir)),
        name_prefix=str(args.prefix),
        write_wav=not bool(args.no_wav),
        write_midi=not bool(args.no_midi),
        write_report=not bool(args.no_report),
        export_stems=bool(args.export_stems),
    )

    logging.info("Export complete: %s", outputs)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

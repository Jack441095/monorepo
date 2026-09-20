#!/usr/bin/env python3
"""Generate best-of-K candidates and append rerank feature rows to JSONL (Phase B dataset)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _append_jsonl(path: Path, row: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Log song rerank training rows via best-of-K generation")
    ap.add_argument("--emotion", default="grief")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--seed-base", type=int, default=100000)
    ap.add_argument("--bars", type=int, default=8)
    ap.add_argument("--root", type=int, default=60)
    ap.add_argument(
        "--out",
        default="artifacts/datasets/song_rerank/candidates.jsonl",
        help="Append-only JSONL output",
    )
    ap.add_argument("--phase-a", action="store_true", help="Enable Phase A offline profile")
    ap.add_argument("--phase-b", action="store_true", help="Enable Phase B profile (logging + model if present)")
    args = ap.parse_args()

    from audiogen_core.config import CONFIG
    from audiogen_core.song_upgrade_profile import apply_phase_a_profile, apply_phase_b_profile
    from composition.song_generator import SongGenerator
    from composition.audit_aligned_score import metrics_row_from_rerank_details
    from composition.song_rerank_model import RERANK_FEATURE_NAMES, feature_vector_from_row

    if bool(args.phase_b):
        apply_phase_b_profile(CONFIG)
    elif bool(args.phase_a):
        apply_phase_a_profile(CONFIG)

    emotion = str(args.emotion).strip().lower()
    gen = SongGenerator()
    sections = SongGenerator.default_form(emotion, bars_per_section=int(args.bars), root_note=int(args.root))
    out_path = Path(str(args.out)).expanduser()
    ts = time.strftime("%Y%m%d_%H%M%S")

    for i in range(max(1, int(args.k))):
        seed = int(args.seed_base) + int(i)
        song = gen.generate_song(
            sections,
            base_tempo_bpm=70.0,
            arrangement_form="default",
            seed=int(seed),
        )
        score, details = SongGenerator._score_candidate_song(song, arrangement_form="default")
        metrics = metrics_row_from_rerank_details(details)
        feat = feature_vector_from_row(
            {
                **metrics,
                "emotion_match_score": float(details.get("emotion_match_score", 0.0) or 0.0),
                "verse_lead_activity": float(details.get("verse_lead_activity", 0.0) or 0.0),
                "chorus_lead_activity": float(details.get("chorus_lead_activity", 0.0) or 0.0),
                "register_lift_semitones": float(details.get("register_lift_semitones", 0.0) or 0.0),
            }
        )
        row: Dict[str, Any] = {
            "ts": ts,
            "emotion": emotion,
            "seed": int(seed),
            "candidate_index": int(i),
            "picked_score": float(score),
            "professional_quality_score": float(details.get("audit_aligned_quality_score", 0.0) or 0.0),
            "learned_rerank_score": float(details.get("learned_rerank_score", 0.0) or 0.0),
            "rerank_score_source": str(details.get("rerank_score_source", "")),
            "features": {name: float(feat[j]) for j, name in enumerate(RERANK_FEATURE_NAMES)},
            "metadata": dict(song.metadata or {}),
        }
        _append_jsonl(out_path, row)
        print(f"logged emotion={emotion} seed={seed} score={score:.3f}")

    print(f"wrote rows to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Print key composition knobs for reproducible dataset A/B labels (stdout).

Used by dataset shell scripts to write run_meta.txt next to JSONL outputs.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, List, Tuple

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _get(obj: Any, path: str) -> Any:
    cur: Any = obj
    for part in path.split("."):
        if cur is None:
            return None
        cur = getattr(cur, part, None)
    return cur


def main() -> int:
    keys: List[Tuple[str, str]] = [
        # (label, attribute path on CONFIG)
        ("melody_strongbeat_chord_tone_mult", "composition.melody_strongbeat_chord_tone_mult"),
        ("harmony_antistuck_enabled", "composition.harmony_antistuck_enabled"),
        ("harmony_repeat_penalty_mult", "composition.harmony_repeat_penalty_mult"),
        ("melody_phrase_rerank_cadence_land_bonus", "composition.melody_phrase_rerank_cadence_land_bonus"),
        ("melody_rerank_cadence_target_bonus", "composition.melody_rerank_cadence_target_bonus"),
        ("section_k_samples", "composition.section_k_samples"),
        ("chord_k_samples", "composition.chord_k_samples"),
        ("use_voice_leading", "composition.use_voice_leading"),
    ]
    try:
        from audiogen_core.config import CONFIG
    except Exception as exc:
        print(f"# import error: {exc}", file=sys.stderr)
        return 1

    for label, path in keys:
        val = _get(CONFIG, path)
        print(f"{label}={val!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

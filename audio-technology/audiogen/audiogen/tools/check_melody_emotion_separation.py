from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _load_metrics(path: str) -> Dict[str, Any]:
    p = Path(path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"Metrics file not found: {p}")
    return json.loads(p.read_text())


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument(
        "--metrics",
        default=".cache/melody_emotion_metrics.json",
        help="Path to JSON metrics from eval_melody_emotion_fit.py",
    )
    args = ap.parse_args()

    data = _load_metrics(args.metrics)
    em = data.get("emotions", {})

    def _get(emo: str, role: str, key: str, default: float = 0.0) -> float:
        try:
            return float(em.get(emo, {}).get(role, {}).get(key, default))
        except Exception:
            return float(default)

    # Simple assertions for core emotions (verse role "a"):
    checks = []
    # Joy vs sadness: joy should be higher in pitch and density.
    checks.append(
        (
            "joy_mean_pitch > sadness_mean_pitch",
            _get("joy", "a", "mean_pitch_mean") > _get("sadness", "a", "mean_pitch_mean"),
        )
    )
    checks.append(
        (
            "joy_notes_per_bar > sadness_notes_per_bar",
            _get("joy", "a", "notes_per_bar_mean") > _get("sadness", "a", "notes_per_bar_mean"),
        )
    )
    # Fear vs neutral: fear should be more syncopated.
    checks.append(
        (
            "fear_syncopation > neutral_syncopation",
            _get("fear", "a", "syncopation_ratio_mean") > _get("neutral", "a", "syncopation_ratio_mean"),
        )
    )
    # Nervousness vs love: nervousness should be denser and more syncopated.
    checks.append(
        (
            "nervous_notes_per_bar > love_notes_per_bar",
            _get("nervousness", "a", "notes_per_bar_mean") > _get("love", "a", "notes_per_bar_mean"),
        )
    )
    checks.append(
        (
            "nervous_syncopation > love_syncopation",
            _get("nervousness", "a", "syncopation_ratio_mean") > _get("love", "a", "syncopation_ratio_mean"),
        )
    )

    failed = [name for name, ok in checks if not ok]
    if failed:
        print("Melody emotion separation checks: FAILED")
        for name, ok in checks:
            print(f"- {name}: {'OK' if ok else 'FAIL'}")
        return 1

    print("Melody emotion separation checks: OK")
    for name, ok in checks:
        print(f"- {name}: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


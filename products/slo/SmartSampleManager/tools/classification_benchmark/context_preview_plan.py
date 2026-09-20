#!/usr/bin/env python3
"""Create a non-destructive tempo/pitch preview plan for reviewed samples.

This is intentionally a planning layer: it calculates reversible transform
parameters but does not decode, rewrite, copy, rename, or replace source audio.
Source key detection is not guessed from a single median pitch; unless a
trusted key is present, the receipt says that key alignment is unavailable.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any


VERSION = "context_preview_plan_v1"


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _flatten(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(payload.get("collections"), dict):
        rows = []
        for action, values in payload["collections"].items():
            for value in values:
                if isinstance(value, dict):
                    row = dict(value)
                    row["action"] = action
                    rows.append(row)
        return rows
    if isinstance(payload.get("cards"), list):
        return [value for value in payload["cards"] if isinstance(value, dict)]
    raise ValueError("input must contain cards or review collections")


def _facets(row: dict[str, Any]) -> dict[str, Any]:
    facets = row.get("facets")
    if isinstance(facets, dict):
        return facets
    evidence = row.get("review_evidence")
    if isinstance(evidence, dict) and isinstance(evidence.get("facets"), dict):
        return evidence["facets"]
    return {
        "duration_seconds": row.get("source", {}).get("analysis_duration_seconds"),
        "estimated_tempo_bpm": row.get("temporal", {}).get("estimated_tempo_bpm"),
        "form_hint": row.get("temporal", {}).get("form_hint"),
        "median_f0_hz": row.get("pitch", {}).get("median_f0_hz"),
        "form_hint_confidence": row.get("temporal", {}).get("form_hint_confidence"),
    }


def build_plan(payload: dict[str, Any], target_bpm: float | None = None,
               target_key: str | None = None, pitch_semitones: float | None = None,
               action: str | None = None, limit: int | None = None) -> dict[str, Any]:
    if target_bpm is None and target_key is None and pitch_semitones is None:
        raise ValueError("at least one target transform is required")
    if target_bpm is not None and (not math.isfinite(target_bpm) or target_bpm <= 0):
        raise ValueError("target_bpm must be positive")
    if pitch_semitones is not None and abs(pitch_semitones) > 24:
        raise ValueError("pitch_semitones must be within +/-24")
    rows = _flatten(payload)
    if action:
        rows = [row for row in rows if row.get("action") == action]
    rows.sort(key=lambda row: str(row.get("path", "")))
    if limit is not None:
        rows = rows[:limit]
    previews = []
    for row in rows:
        path = row.get("path")
        facets = _facets(row)
        source_bpm = _number(facets.get("estimated_tempo_bpm"))
        form = facets.get("form_hint")
        tempo_plan = None
        if target_bpm is not None:
            if source_bpm is None or source_bpm <= 0:
                tempo_plan = {"status": "unavailable", "reason": "source_tempo_unknown"}
            else:
                rate = target_bpm / source_bpm
                tempo_plan = {
                    "status": "planned" if 0.5 <= rate <= 2.0 else "caution",
                    "source_bpm": source_bpm,
                    "target_bpm": target_bpm,
                    "time_stretch_rate": round(rate, 8),
                    "duration_multiplier": round(1.0 / rate, 8),
                    "reason": "outside_conservative_rate_range" if not 0.5 <= rate <= 2.0 else None,
                }
        pitch_plan = None
        if target_key is not None or pitch_semitones is not None:
            # A median F0 is not a key estimate. Keep the requested target in
            # the plan, but refuse to invent a source key or automatic shift.
            pitch_plan = {
                "status": "planned_explicit_shift" if pitch_semitones is not None else "unavailable",
                "target_key": target_key,
                "semitones": pitch_semitones,
                "reason": None if pitch_semitones is not None else "source_key_unavailable",
            }
        previews.append({
            "path": path,
            "action": row.get("action"),
            "predicted_class": row.get("predicted_class"),
            "form_hint": form,
            "tempo": tempo_plan,
            "pitch": pitch_plan,
            "render": {
                "status": "plan_only",
                "output_path": None,
                "source_replaced": False,
            },
        })
    return {
        "record_type": "slo_context_preview_plan",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "targets": {"bpm": target_bpm, "key": target_key, "pitch_semitones": pitch_semitones},
        "n_input": len(_flatten(payload)),
        "n_planned": len(previews),
        "previews": previews,
        "safety": {
            "read_only": True,
            "source_audio_modified": False,
            "source_audio_replaced": False,
            "files_created": False,
            "rename_actions": False,
            "key_inferred_from_median_pitch": False,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target-bpm", type=float)
    parser.add_argument("--target-key")
    parser.add_argument("--pitch-semitones", type=float)
    parser.add_argument("--action", choices=("auto_rename", "suggest", "review", "never_act"))
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = build_plan(payload, args.target_bpm, args.target_key, args.pitch_semitones, args.action, args.limit)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"n_input": result["n_input"], "n_planned": result["n_planned"], "safety": result["safety"]}, indent=2))


if __name__ == "__main__":
    main()

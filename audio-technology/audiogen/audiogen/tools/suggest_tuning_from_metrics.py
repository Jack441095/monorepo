from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, Optional

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from audiogen_core.config_utils import resolve_project_path


def _f(x: Any, default: float = 0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def _clip(x: float, lo: float, hi: float) -> float:
    v = _f(x, lo)
    return float(lo if v < lo else hi if v > hi else v)


def _grid_pref_to_grid(pref: Optional[str]) -> float:
    p = (pref or "").strip().lower()
    # Most of your references read as 16ths; keep mapping explicit.
    if p == "8th":
        return 0.5
    return 0.25


def _suggest_target_notes_per_bar(*, bpm: float, onset_rate_hz: float) -> float:
    """
    Convert onset density into an approximate notes-per-bar target.
    We assume 4/4, bars_per_minute = bpm / 4.
      onsets/min = onset_rate_hz * 60
      onsets/bar = onsets/min / (bpm/4) = onset_rate_hz * 60 * 4 / bpm
    Clamp to [4..16] because the arp engine uses that musical window.
    """
    bpm = max(1e-6, float(bpm))
    onsets_per_bar = float(onset_rate_hz) * 240.0 / float(bpm)
    return float(_clip(onsets_per_bar, 4.0, 16.0))


def _motif_strength_from_metrics(*, rhythm_rep: Optional[float], chroma_rep: Optional[float]) -> float:
    """
    0..1 score: higher means more repetition/motifiness in references.
    """
    r = None if rhythm_rep is None else _clip(float(rhythm_rep), 0.0, 1.0)
    c = None if chroma_rep is None else _clip(float(chroma_rep), 0.0, 1.0)
    if r is None and c is None:
        return 0.5
    if r is None:
        return float(c)
    if c is None:
        return float(r)
    return float(0.6 * r + 0.4 * c)


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--metrics", default=".cache/reference_metrics.json", help="Input metrics JSON (default: .cache/reference_metrics.json)")
    ap.add_argument("--output", default=".cache/tuning_suggestions.json", help="Output suggestions JSON (default: .cache/tuning_suggestions.json)")
    ap.add_argument("--assume_beats_per_bar", type=float, default=4.0, help="Assumed beats per bar (default: 4.0)")
    args = ap.parse_args()

    metrics_path = resolve_project_path(str(args.metrics))
    out_path = resolve_project_path(str(args.output))
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(metrics_path.read_text())
    by_emotion = dict(data.get("by_emotion") or {})

    arp_profiles: Dict[str, Dict[str, Any]] = {}
    notes_per_bar_map: Dict[str, float] = {}
    motif_strength_map: Dict[str, float] = {}

    for emo, m in sorted(by_emotion.items(), key=lambda kv: str(kv[0])):
        bpm = _f(m.get("tempo_bpm"), 0.0)
        onset_rate = _f(m.get("onset_rate_hz"), 0.0)
        grid_pref = (m.get("grid_pref") or "16th")
        grid = _grid_pref_to_grid(str(grid_pref))
        # If tempo estimate failed, default to 110bpm-ish behavior.
        bpm_eff = bpm if bpm > 1e-6 else 110.0

        tnpb = _suggest_target_notes_per_bar(bpm=bpm_eff, onset_rate_hz=onset_rate if onset_rate > 1e-9 else 0.6)
        notes_per_bar_map[str(emo)] = float(tnpb)

        motif_strength = _motif_strength_from_metrics(
            rhythm_rep=m.get("motif_rhythm_repetition"),
            chroma_rep=m.get("motif_chroma_repetition"),
        )
        motif_strength_map[str(emo)] = float(motif_strength)

        # Map motifiness to articulation knobs lightly (avoid overfitting).
        # Higher motifiness: stronger accents, slightly more octave motion, less syncopation.
        accent = _clip(0.08 + 0.10 * motif_strength, 0.05, 0.22)
        octave = _clip(0.06 + 0.12 * motif_strength, 0.04, 0.22)
        sync = _clip(0.18 - 0.10 * motif_strength, 0.06, 0.22)

        arp_profiles[str(emo)] = {
            "grid": float(grid),
            "target_notes_per_bar": float(round(tnpb, 2)),
            "accent_strength": float(round(accent, 3)),
            "octave_reach_prob": float(round(octave, 3)),
            "syncopation_prob": float(round(sync, 3)),
        }

    # Global motif/hook suggestions: derive from overall motifiness average.
    if motif_strength_map:
        avg_motif = sum(motif_strength_map.values()) / max(1, len(motif_strength_map))
    else:
        avg_motif = 0.6

    # Strong-hook defaults: still keep bounds so realtime remains stable.
    composition_suggestions = {
        "melody_phrase_k_samples": int(round(_clip(1 + 4 * avg_motif, 2, 5))),
        "motif_use_chance": float(round(_clip(0.55 + 0.40 * avg_motif, 0.55, 0.92), 3)),
        "motif_variation_prob": float(round(_clip(0.28 - 0.18 * avg_motif, 0.08, 0.25), 3)),
        "melody_rest_prob_mult": float(round(_clip(1.05 - 0.30 * avg_motif, 0.75, 1.10), 3)),
    }

    # Role curve suggestions: keep 16th grid and drive contrast via density.
    # These are multipliers; you can merge them into data/arrangement_curves.py by role.
    role_curve_suggestions = {
        "intro": {"arp_grid": 0.25, "arp_density_mult": 0.65},
        "a": {"arp_grid": 0.25, "arp_density_mult": 0.80},
        "pre_chorus": {"arp_grid": 0.25, "arp_density_mult": 1.05},
        "b": {"arp_grid": 0.25, "arp_density_mult": 1.25},
        "a_prime": {"arp_grid": 0.25, "arp_density_mult": 1.05},
        "tag": {"arp_grid": 0.25, "arp_density_mult": 1.18},
        "outro": {"arp_grid": 0.25, "arp_density_mult": 0.60},
    }

    out = {
        "source_metrics": str(metrics_path),
        "suggested_arp_profiles": arp_profiles,
        "suggested_role_curves": role_curve_suggestions,
        "suggested_composition_config": composition_suggestions,
        "derived": {
            "avg_motif_strength": float(round(avg_motif, 3)),
            "notes_per_bar_by_emotion": notes_per_bar_map,
            "motif_strength_by_emotion": motif_strength_map,
        },
    }
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True))
    print(f"Wrote {out_path} (emotions={len(arp_profiles)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

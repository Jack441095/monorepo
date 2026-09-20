#!/usr/bin/env python3
"""Explainable, aspect-specific similarity between two audio files.

This is a research/search aid inspired by aspect-weighted sample browsers. It
does not assign a taxonomy class, create labels, or alter the rename policy.
Scores are explicitly heuristic until calibrated against human similarity
judgements.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


SD = Path(__file__).resolve().parent
VERSION = "aspect_similarity_v1"


def _load_definition_module():
    path = SD / "audio_definition_card.py"
    spec = importlib.util.spec_from_file_location("audio_definition_card", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def _score(values: list[tuple[float | None, float | None, float]]) -> float | None:
    usable = [math.exp(-abs(float(a) - float(b)) / max(scale, 1e-9))
              for a, b, scale in values if a is not None and b is not None
              and np.isfinite(a) and np.isfinite(b)]
    return float(np.mean(usable)) if usable else None


def _log_frequency(value: float | None) -> float | None:
    return math.log2(value) if value is not None and value > 0 else None


def compare_cards(source: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    ss, cs = source, candidate
    spectrum = _score([
        (_log_frequency(ss["spectrum"].get("spectral_centroid_hz")),
         _log_frequency(cs["spectrum"].get("spectral_centroid_hz")), 0.75),
        (_log_frequency(ss["spectrum"].get("spectral_rolloff_hz")),
         _log_frequency(cs["spectrum"].get("spectral_rolloff_hz")), 0.75),
        (ss["spectrum"].get("spectral_flatness"), cs["spectrum"].get("spectral_flatness"), 0.20),
        (ss["spectrum"].get("low_band_energy_ratio"), cs["spectrum"].get("low_band_energy_ratio"), 0.25),
        (ss["spectrum"].get("high_band_energy_ratio"), cs["spectrum"].get("high_band_energy_ratio"), 0.25),
    ])
    timbre = _score([
        (ss["spectrum"].get("harmonic_energy_ratio"), cs["spectrum"].get("harmonic_energy_ratio"), 0.25),
        (ss["spectrum"].get("zero_crossing_rate"), cs["spectrum"].get("zero_crossing_rate"), 0.08),
        (ss["signal"].get("crest_factor"), cs["signal"].get("crest_factor"), 3.0),
        (ss["temporal"].get("onset_density_per_second"), cs["temporal"].get("onset_density_per_second"), 2.0),
    ])
    pitch = _score([
        (_log_frequency(ss["pitch"].get("median_f0_hz")),
         _log_frequency(cs["pitch"].get("median_f0_hz")), 0.5),
        (ss["pitch"].get("voiced_frame_fraction"), cs["pitch"].get("voiced_frame_fraction"), 0.35),
    ])
    amplitude = _score([
        (ss["signal"].get("rms_dbfs"), cs["signal"].get("rms_dbfs"), 8.0),
        (ss["signal"].get("peak_dbfs"), cs["signal"].get("peak_dbfs"), 8.0),
        (ss["signal"].get("crest_factor"), cs["signal"].get("crest_factor"), 3.0),
        (ss["signal"].get("leading_silence_seconds"), cs["signal"].get("leading_silence_seconds"), 0.25),
    ])
    temporal = _score([
        (ss["source"].get("analysis_duration_seconds"), cs["source"].get("analysis_duration_seconds"), 2.0),
        (ss["temporal"].get("onset_density_per_second"), cs["temporal"].get("onset_density_per_second"), 2.0),
        (ss["temporal"].get("periodicity_strength"), cs["temporal"].get("periodicity_strength"), 0.35),
        (ss["temporal"].get("periodicity_seconds"), cs["temporal"].get("periodicity_seconds"), 0.5),
    ])
    spatial = _score([
        (ss["spatial"].get("stereo_correlation"), cs["spatial"].get("stereo_correlation"), 0.35),
    ])
    aspects = {
        "spectrum": spectrum,
        "timbre": timbre,
        "pitch": pitch,
        "amplitude": amplitude,
        "temporal": temporal,
        "spatial": spatial,
    }
    usable = [v for v in aspects.values() if v is not None]
    overall = float(np.mean(usable)) if usable else None
    return {
        "record_type": "slo_aspect_similarity",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "safety": {
            "semantic_label_created": False,
            "rename_action": False,
            "human_calibration_required": True,
        },
        "source": source.get("path"),
        "candidate": candidate.get("path"),
        "similarity": {"overall": overall, "aspects": aspects},
        "interpretation": "Scores are heuristic evidence for search and explanation, not class probabilities.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    analyser = _load_definition_module()
    result = compare_cards(analyser.analyse_file(args.source), analyser.analyse_file(args.candidate))
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["similarity"], indent=2))


if __name__ == "__main__":
    main()

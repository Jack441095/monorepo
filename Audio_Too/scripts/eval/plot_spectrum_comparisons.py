#!/usr/bin/env python3
"""
Averaged-spectrum comparison charts: each low-shelf-corrected render vs the
reference track, mid/side split, with a +3dB/octave tilt applied so the
plotted curves read flat for pink-noise-like balance (matches the earlier
stranger-vs-reference chart Jack asked for). Whole-track average (Welch PSD,
8192-sample Hann windows, 50% overlap), not chorus-scoped like the original
stranger chart -- dream_of_you/reggueton_pop have no established chorus
timestamp, and the whole-track average is what reference_track_comparison.py's
tonal-balance score itself is computed from, so this stays consistent with
that number.

Usage: plot_spectrum_comparisons.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from spectrum_plot import render_mid_side_spectrum_comparison  # noqa: E402

REFERENCE = ROOT / "reference_tracks" / "Stromae,_Pomme_-_Ma_Meilleure_Ennemie_(from_Arcane_Season_2)_[Official_Visualizer]_[_YouConvert.net_].mp3"

SONGS = {
    "stranger": {
        "mix": ROOT / "artifacts/real_stem_validation_2026-07-15/stranger-lowshelf-v2/mixdown_v1.wav",
        "label": "stranger (low-shelf v2)",
    },
    "dream_of_you": {
        "mix": ROOT / "artifacts/real_stem_validation_2026-07-15/dream-lowshelf-v2/mixdown_v1.wav",
        "label": "dream_of_you (low-shelf v2)",
    },
    "reggueton_pop": {
        "mix": ROOT / "artifacts/real_stem_validation_2026-07-15/reggueton-lowshelf-v2/mixdown_v1.wav",
        "label": "reggueton_pop (low-shelf v2)",
    },
}

OUTPUT_DIR = ROOT / "artifacts" / "reference_comparison_2026-07-17"


def _load(path: Path) -> dict:
    data = read_wav_mono(path.read_bytes(), max_samples=0, as_arrays=True)
    left = data["left_samples"] if data["left_samples"] is not None and len(data["left_samples"]) else data["samples"]
    right = data["right_samples"] if data["right_samples"] is not None and len(data["right_samples"]) else data["samples"]
    left = np.asarray(left, dtype=np.float64)
    right = np.asarray(right, dtype=np.float64)
    return {"left": left, "right": right, "sample_rate": int(data["sample_rate"])}


def plot_song(song_key: str, cfg: dict, ref: dict) -> Path:
    mix = _load(cfg["mix"])
    out_path = OUTPUT_DIR / f"{song_key}_lowshelf_v2_vs_reference_spectrum.png"
    return render_mid_side_spectrum_comparison(
        mix_left=mix["left"], mix_right=mix["right"], mix_sr=mix["sample_rate"],
        ref_left=ref["left"], ref_right=ref["right"], ref_sr=ref["sample_rate"],
        mix_label=cfg["label"], ref_label="reference (Stromae/Pomme)",
        output_path=out_path,
    )


def main():
    print(f"Loading reference: {REFERENCE.name}")
    ref = _load(REFERENCE)
    for song_key, cfg in SONGS.items():
        print(f"Plotting {song_key}...")
        out_path = plot_song(song_key, cfg, ref)
        print(f"  -> {out_path}")


if __name__ == "__main__":
    main()

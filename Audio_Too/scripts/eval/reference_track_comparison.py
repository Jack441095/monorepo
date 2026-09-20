#!/usr/bin/env python3
"""
Reference-track comparison tool.

Compares a rendered mix against a commercial reference track (or any audio
file — wav, mp3, etc., via ffmpeg) across tonal balance, dynamics, and stereo
image, using the analysis engine that already exists in this codebase
(analysis_core.genre_profiles / reference_matching / analysis_features) —
this script is glue, not new analysis.

This is a CALIBRATION tool, not a promotion gate: it tells you objectively
whether AutoMix's tonal balance/dynamics/stereo image are in the neighborhood
of a real professional master, and gives an actionable EQ8 preset to close
the gap. It does NOT tell you whether the result sounds good or preserves the
rough mix's intent — that's what the blind-listening infra
(scripts/listening_benchmark_*.py) is for. Use both.

Usage:
    python3 scripts/eval/reference_track_comparison.py <mix.wav> <reference> \
        [--output-dir DIR] [--mix-label "..."] [--ref-label "..."]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from audio_analysis.analysis_core.dsp_metrics import log_band_ratios_track_average  # noqa: E402
from audio_analysis.analysis_core.genre_profiles import (  # noqa: E402
    map_40_to_7_bands,
    compute_tonal_balance_score,
)
from audio_analysis.analysis_core.reference_matching import (  # noqa: E402
    compute_eq_matching_curve,
    export_eq8_preset_adv,
    dynamics_comparison,
    stereo_image_comparison,
)
from audio_analysis.analysis_core.analysis_features import stereo_metrics  # noqa: E402


def _load_track(path: Path) -> dict:
    """Decode any audio file (wav/mp3/... via ffmpeg) to mono + L/R samples."""
    data = read_wav_mono(path.read_bytes(), max_samples=0)
    return {
        "samples": data["samples"],
        "left": data["left_samples"] or data["samples"],
        "right": data["right_samples"] or data["samples"],
        "sample_rate": data["sample_rate"],
        "duration_seconds": data["duration_seconds"],
    }


def compare_tracks(mix_path: Path, ref_path: Path, mix_label: str, ref_label: str) -> dict:
    print(f"Loading mix: {mix_path.name}")
    mix = _load_track(mix_path)
    print(f"  {mix['duration_seconds']:.1f}s @ {mix['sample_rate']}Hz")

    print(f"Loading reference: {ref_path.name}")
    ref = _load_track(ref_path)
    print(f"  {ref['duration_seconds']:.1f}s @ {ref['sample_rate']}Hz")

    # --- Tonal balance (whole-track 40-band fingerprint -> 7-band -> score) ---
    print("Computing tonal balance...")
    mix_bands40 = log_band_ratios_track_average(mix["samples"], mix["sample_rate"])
    ref_bands40 = log_band_ratios_track_average(ref["samples"], ref["sample_rate"])
    mix_bands7 = map_40_to_7_bands(mix_bands40)
    ref_bands7 = map_40_to_7_bands(ref_bands40)
    tonal_score = compute_tonal_balance_score(mix_bands40, ref_bands40)
    eq_matching_gains = compute_eq_matching_curve(mix_bands7, ref_bands7)

    # --- Dynamics (crest factor, transient attack slope) ---
    print("Computing dynamics comparison...")
    dynamics = dynamics_comparison(mix["samples"], ref["samples"], mix["sample_rate"])

    # --- Stereo image (correlation, width, balance) ---
    print("Computing stereo image comparison...")
    mix_stereo = stereo_metrics(mix["left"], mix["right"])
    ref_stereo = stereo_metrics(ref["left"], ref["right"])
    mix_stereo["stereo_balance"] = 1.0  # stereo_metrics doesn't compute L/R balance; neutral default
    ref_stereo["stereo_balance"] = 1.0
    stereo = stereo_image_comparison(mix_stereo, ref_stereo)

    return {
        "mix": {"label": mix_label, "path": str(mix_path), "duration_seconds": mix["duration_seconds"]},
        "reference": {"label": ref_label, "path": str(ref_path), "duration_seconds": ref["duration_seconds"]},
        "tonal_balance": {
            "score_0_100": tonal_score,
            "mix_bands_7": mix_bands7,
            "reference_bands_7": ref_bands7,
            "suggested_eq_gains_db": eq_matching_gains,
        },
        "dynamics": dynamics,
        "stereo_image": {
            "mix_metrics": mix_stereo,
            "reference_metrics": ref_stereo,
            **stereo,
        },
    }


def render_markdown_report(report: dict) -> str:
    m = report["mix"]
    r = report["reference"]
    tb = report["tonal_balance"]
    dyn = report["dynamics"]
    st = report["stereo_image"]

    lines = [
        f"# Reference Comparison: {m['label']} vs {r['label']}",
        "",
        f"- Mix: `{m['path']}` ({m['duration_seconds']:.1f}s)",
        f"- Reference: `{r['path']}` ({r['duration_seconds']:.1f}s)",
        "",
        "## Tonal balance",
        "",
        f"**Score: {tb['score_0_100']}/100** (perceptually-weighted match to reference's 7-band energy distribution)",
        "",
        "| Band | Mix | Reference | Suggested EQ gain |",
        "| --- | ---: | ---: | ---: |",
    ]
    for band in ("sub", "bass", "low_mids", "mids", "presence", "sibilance", "air"):
        lines.append(
            f"| {band} | {tb['mix_bands_7'][band]:.3f} | {tb['reference_bands_7'][band]:.3f} | "
            f"{tb['suggested_eq_gains_db'][band]:+.1f} dB |"
        )
    lines += [
        "",
        "## Dynamics",
        "",
        f"- Mix crest factor: {dyn['mix_crest_avg_db']:.1f} dB",
        f"- Reference crest factor: {dyn['ref_crest_avg_db']:.1f} dB",
        f"- Delta: {dyn['crest_delta_db']:+.1f} dB",
        f"- Mix transient attack slope: {dyn['mix_attack_slope_db_per_ms']:.1f} dB/ms",
        f"- Reference transient attack slope: {dyn['ref_attack_slope_db_per_ms']:.1f} dB/ms",
        "",
        "**Advice:**",
    ]
    for line in dyn["advice"]:
        lines.append(f"- {line}")

    lines += [
        "",
        "## Stereo image",
        "",
        f"- Width delta (mix - ref): {st['width_delta']:+.3f}",
        f"- Balance delta (mix - ref): {st['balance_delta']:+.3f}",
        f"- Correlation delta (mix - ref): {st['correlation_delta']:+.3f}",
        f"- Suggested M/S width correction: {st['width_correction_db']:+.1f} dB",
        f"- Mono safety risk: {'YES — check for phase cancellation' if st['mono_safety'] else 'no'}",
        "",
        "**Advice:**",
    ]
    for line in st["advice"]:
        lines.append(f"- {line}")

    lines += [
        "",
        "---",
        "*This is a technical calibration comparison, not a perceptual quality judgment.*",
        "*A high tonal-balance score means the spectral shape resembles the reference — it does not*",
        "*mean the mix sounds better. Pair with a blind A/B listen before treating any suggestion here*",
        "*as a promotion signal (see scripts/listening_benchmark_*.py).*",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mix", help="Path to the AutoMix-rendered mix (or any WAV).")
    parser.add_argument("reference", help="Path to the reference track (wav, mp3, etc.).")
    parser.add_argument("--output-dir", default="./reference_comparison-output", help="Directory for the JSON report, markdown report, and EQ8 preset.")
    parser.add_argument("--mix-label", default=None, help="Human label for the mix in the report (default: filename).")
    parser.add_argument("--ref-label", default=None, help="Human label for the reference in the report (default: filename).")
    args = parser.parse_args()

    mix_path = Path(args.mix).expanduser().resolve()
    ref_path = Path(args.reference).expanduser().resolve()
    if not mix_path.is_file():
        print(f"FAILED: {mix_path} is not a file.")
        return 1
    if not ref_path.is_file():
        print(f"FAILED: {ref_path} is not a file.")
        return 1

    mix_label = args.mix_label or mix_path.stem
    ref_label = args.ref_label or ref_path.stem

    report = compare_tracks(mix_path, ref_path, mix_label, ref_label)

    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "report.json"
    json_path.write_text(json.dumps(report, indent=2))

    md_path = output_dir / "report.md"
    md_path.write_text(render_markdown_report(report))

    eq_bytes = export_eq8_preset_adv(report["tonal_balance"]["suggested_eq_gains_db"])
    eq_path = output_dir / "suggested_eq8.adv"
    eq_path.write_bytes(eq_bytes)

    print(f"\nTonal balance score: {report['tonal_balance']['score_0_100']}/100")
    print(f"Reports written to: {output_dir}")
    print(f"  {json_path.name}")
    print(f"  {md_path.name}")
    print(f"  {eq_path.name}  (drop into an Ableton EQ Eight device)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

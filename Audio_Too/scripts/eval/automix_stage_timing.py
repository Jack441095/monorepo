#!/usr/bin/env python3
"""
Stage-timing profiler for the AutoMix pipeline (workstream: find the true
dominant render cost). Mirrors run_local_automix()'s stages with wall-clock
timers so we can see whether time goes to ANALYSIS (masking / relationships /
mono-compat / multi-window resonance) or the RENDER/validate loop.

The DSP-loop vectorization (envelope/compressor) was proven ~38x/11x faster in
isolation but did not cut end-to-end wall time — this locates where it actually
goes. Run on the shortest track (dream_of_you, 81s, 15 stems) for a fast read.
"""

from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
sys.path.insert(0, str(ROOT / "business" / "app"))

from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from audio_analysis.analysis_core.dsp_metrics import spectral_bands  # noqa: E402
from audio_analysis.analysis_core.phase_polarity_detection import correct_stem_polarity  # noqa: E402
from audio_analysis.mixdown.stem_classifier import classify_stems  # noqa: E402
from audio_analysis.mixdown.stem_prep import prepare_stems  # noqa: E402
from audio_analysis.mixdown.musical_roles import infer_musical_roles  # noqa: E402
from audio_analysis.mixdown.arrangement import infer_arrangement  # noqa: E402
from audio_analysis.mixdown.relationships import infer_relationships  # noqa: E402
from audio_analysis.mixdown.mono_compatibility import analyze_mono_compatibility  # noqa: E402
from audio_analysis.analysis_core.sidechain_detection import analyze_stems_for_dynamics  # noqa: E402
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking  # noqa: E402
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan  # noqa: E402
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems  # noqa: E402
from audio_analysis.mixdown.mix_validator import validate_and_correct_mix  # noqa: E402

TIMINGS: list[tuple[str, float, float, float]] = []


def _rss_gb() -> float:
    try:
        import resource
        # macOS ru_maxrss is in bytes (Linux: kilobytes). Assume macOS here.
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9
    except Exception:
        return 0.0


@contextmanager
def stage(label: str):
    rss0 = _rss_gb()
    t0 = time.time()
    yield
    dt = time.time() - t0
    rss1 = _rss_gb()
    TIMINGS.append((label, dt, rss1, rss1 - rss0))
    print(f"  [{dt:8.2f}s]  peakRSS {rss1:6.2f}GB (+{rss1-rss0:5.2f})  {label}", flush=True)


def main():
    track = sys.argv[1] if len(sys.argv) > 1 else "dream_of_you"
    wdir = "WAV's" if track == "reggueton_pop" else "WAVs"
    wav_dir = ROOT / "testing_track_stems" / track / wdir
    audio_paths = sorted(p for p in wav_dir.glob("*.wav") if not p.name.startswith("."))
    print(f"Profiling {len(audio_paths)} stems from {wav_dir.name}\n")

    total0 = time.time()
    stems_raw = [{"name": p.name, "file_bytes": p.read_bytes()} for p in audio_paths]

    with stage("classify_stems"):
        profiles = classify_stems(stems_raw, read_wav_mono_fn=read_wav_mono, max_samples=131072)
    with stage("prepare_stems (full-rate decode + align)"):
        prepared_stems = prepare_stems(
            stems_raw, read_wav_mono_fn=read_wav_mono,
            target_sample_rate=44100, trim=True, normalise=False, max_samples=0,
        )
    with stage("correct_stem_polarity"):
        try:
            psr = prepared_stems[0].get("sample_rate", 44100) if prepared_stems else 44100
            prepared_stems, _ = correct_stem_polarity(prepared_stems, psr)
        except Exception as e:
            print(f"    (polarity skipped: {e})")
    with stage("analyze_stems_masking"):
        masking_results = analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)
    with stage("generate_mix_plan"):
        plan = generate_mix_plan(profiles, masking_results, genre="electronic", target_lufs=-14.0)
    with stage("infer_musical_roles"):
        roles = infer_musical_roles(profiles, prepared_stems)
        plan.musical_roles = [r.to_dict() for r in roles]
    with stage("infer_arrangement"):
        plan.arrangement = infer_arrangement(prepared_stems).to_dict()
    with stage("analyze_mono_compatibility"):
        plan.mono_compatibility = analyze_mono_compatibility(prepared_stems, plan.arrangement).to_dict()
    with stage("analyze_stems_for_dynamics"):
        existing_dynamics = analyze_stems_for_dynamics(
            prepared_stems, profiles,
            prepared_stems[0]["sample_rate"] if prepared_stems else 44_100,
        )
    with stage("infer_relationships"):
        plan.relationships = [r.to_dict() for r in infer_relationships(
            profiles, masking_results, roles, plan.arrangement, prepared_stems, existing_dynamics,
        )]
    with stage("validate_and_correct_mix (RENDER loop)"):
        _validated = validate_and_correct_mix(
            prepared_stems, plan, render_fn=mix_and_render_stems, max_iterations=3,
        )
    print(f"  render-loop iterations: {len(_validated.get('history', []))}")
    for h in _validated.get("history", []):
        print(f"    iter {h['iteration']}: score={h['technical_score']} lufs={h['measured_lufs']:.2f}")
    _gain_attempts = _validated.get("loudness_solver", {}).get("gain_attempts", [])
    print(f"  gain-solve attempts (innermost loop, last render): {len(_gain_attempts)}")
    for g in _gain_attempts:
        print(f"    gain={g['makeup_gain_db']:+.2f}dB lufs={g['measured_lufs']:.2f} "
              f"tp={g['true_peak_dbtp']:.2f} safe={g['safe']}")

    total = time.time() - total0
    print(f"\n{'='*68}\nSTAGE BREAKDOWN by TIME (total {total:.1f}s)\n{'='*68}")
    for label, dt, _rss, _d in sorted(TIMINGS, key=lambda x: -x[1]):
        print(f"  {dt/total*100:5.1f}%  {dt:8.2f}s  {label}")
    print(f"\n{'='*68}\nSTAGE BREAKDOWN by PEAK-RSS RAISED (which stage grows memory)\n{'='*68}")
    for label, _dt, rss, drss in sorted(TIMINGS, key=lambda x: -x[3]):
        print(f"  +{drss:6.2f}GB  (peak {rss:6.2f}GB)  {label}")


if __name__ == "__main__":
    main()

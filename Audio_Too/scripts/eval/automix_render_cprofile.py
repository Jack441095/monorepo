#!/usr/bin/env python3
"""
cProfile a single AutoMix render to find the exact hot functions inside the
render loop (the profiled dominant cost, ~49%). Prepares stems once, then
profiles validate_and_correct_mix so iteration overhead is included too.
"""

from __future__ import annotations

import cProfile
import io
import pstats
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))
sys.path.insert(0, str(ROOT / "business" / "app"))

from audio_analysis.utils.audio_io import read_wav_mono  # noqa: E402
from audio_analysis.analysis_core.dsp_metrics import spectral_bands  # noqa: E402
from audio_analysis.mixdown.stem_classifier import classify_stems  # noqa: E402
from audio_analysis.mixdown.stem_prep import prepare_stems  # noqa: E402
from audio_analysis.mixdown.stem_analysis import analyze_stems_masking  # noqa: E402
from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan  # noqa: E402
from audio_analysis.mixdown.mix_renderer import mix_and_render_stems  # noqa: E402
from audio_analysis.mixdown.mix_validator import validate_and_correct_mix  # noqa: E402


def main():
    wav_dir = ROOT / "testing_track_stems" / "dream_of_you" / "WAVs"
    paths = sorted(p for p in wav_dir.glob("*.wav") if not p.name.startswith("."))
    stems_raw = [{"name": p.name, "file_bytes": p.read_bytes()} for p in paths]

    print(f"Preparing {len(paths)} stems (once)...", flush=True)
    profiles = classify_stems(stems_raw, read_wav_mono_fn=read_wav_mono, max_samples=131072)
    prepared = prepare_stems(
        stems_raw, read_wav_mono_fn=read_wav_mono,
        target_sample_rate=44100, trim=True, normalise=False, max_samples=0,
        masking_preview_max_samples=65536,
    )
    _preview_by_name = {
        s["name"]: (s.get("masking_preview_samples"), s.get("masking_preview_sample_rate")) for s in prepared
    }
    for _s in stems_raw:
        _preview = _preview_by_name.get(_s.get("name"))
        if _preview and _preview[0] is not None:
            _s["masking_preview_samples"], _s["masking_preview_sample_rate"] = _preview
    masking = analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)
    plan = generate_mix_plan(profiles, masking, genre="electronic", target_lufs=-14.0)

    # Count render iterations by wrapping the render fn.
    calls = {"n": 0}
    def counting_render(stems, p, **kw):
        calls["n"] += 1
        return mix_and_render_stems(stems, p, **kw)

    print("cProfiling validate_and_correct_mix (single render pass + iterations)...", flush=True)
    pr = cProfile.Profile()
    pr.enable()
    validate_and_correct_mix(prepared, plan, render_fn=counting_render, max_iterations=3)
    pr.disable()

    print(f"\nRender iterations executed: {calls['n']}\n")
    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats("tottime")
    ps.print_stats(28)
    print(s.getvalue())

    # Also dump the cumulative view for call-chain context.
    s2 = io.StringIO()
    pstats.Stats(pr, stream=s2).sort_stats("cumulative").print_stats(20)
    print("=== CUMULATIVE ===")
    print(s2.getvalue())


if __name__ == "__main__":
    main()

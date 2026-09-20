"""Real-multitrack peak-memory regression guard for the AutoMix pipeline.

docs/audits/2026-07-16-detect-correct-and-perf.md and
docs/audits/... 2026-07-17 entries in the same doc root-caused and fixed a
real production incident: peak memory on a full stranger render was 53.1 GB
against this machine's 16 GB physical RAM, causing swap-thrash renders of up
to 62 minutes. Root cause was audio carried as Python list[float] with
constant list<->array round-trips in prepare_stems/read_wav_mono. Fixed down
to 12.21 GB (stranger) via numpy-native decode/prepare.

That fix was verified manually (scripts/eval/automix_stage_timing.py run by
hand, numbers recorded in the audit doc) but nothing in the automated test
suite guards against the same class of regression recurring -- e.g. a future
change reintroducing a `.tolist()` round-trip in the hot path. This closes
that gap using the real dream_of_you fixture (the smallest of the three real
test songs, chosen to keep this test's own runtime bounded).

Skipped when the local-only, gitignored testing_track_stems/ fixture isn't
present (it's ~1-1.5GB of real audio per song, not committed to git).
"""

from __future__ import annotations

import resource
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WAV_DIR = ROOT / "testing_track_stems" / "dream_of_you" / "WAVs"

sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

pytestmark = pytest.mark.slow

# Measured 3.81 GB peak RSS for this exact fixture/pipeline on 2026-07-20
# (post the 53.1GB->12.21GB stranger fix). Budget set well above that measured
# value -- generous enough to absorb legitimate small growth and normal
# machine variance, but tight enough to catch a real regression back toward
# the old list-based-audio blowup pattern (which was multiples of this, not
# a small overshoot).
PEAK_RSS_BUDGET_GB = 6.5


def _rss_gb() -> float:
    # macOS ru_maxrss is bytes; Linux is kilobytes. This repo's release gate
    # runs on macOS (see scripts/eval/automix_stage_timing.py's own note).
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9


@pytest.mark.skipif(not WAV_DIR.exists(), reason="testing_track_stems/ local fixture not present")
def test_dream_of_you_full_pipeline_stays_under_memory_budget():
    from audio_analysis.utils.audio_io import read_wav_mono
    from audio_analysis.analysis_core.dsp_metrics import spectral_bands
    from audio_analysis.analysis_core.phase_polarity_detection import correct_stem_polarity
    from audio_analysis.mixdown.stem_classifier import classify_stems
    from audio_analysis.mixdown.stem_prep import prepare_stems
    from audio_analysis.mixdown.musical_roles import infer_musical_roles
    from audio_analysis.mixdown.arrangement import infer_arrangement
    from audio_analysis.mixdown.relationships import infer_relationships
    from audio_analysis.mixdown.mono_compatibility import analyze_mono_compatibility
    from audio_analysis.analysis_core.sidechain_detection import analyze_stems_for_dynamics
    from audio_analysis.mixdown.stem_analysis import analyze_stems_masking
    from audio_analysis.mixdown.mix_decision_engine import generate_mix_plan
    from audio_analysis.mixdown.mix_renderer import mix_and_render_stems
    from audio_analysis.mixdown.mix_validator import validate_and_correct_mix

    audio_paths = sorted(p for p in WAV_DIR.glob("*.wav") if not p.name.startswith("."))
    assert audio_paths, f"no WAV stems found in {WAV_DIR}"
    stems_raw = [{"name": p.name, "file_bytes": p.read_bytes()} for p in audio_paths]

    baseline_gb = _rss_gb()

    profiles = classify_stems(stems_raw, read_wav_mono_fn=read_wav_mono, max_samples=131072)
    prepared_stems = prepare_stems(
        stems_raw, read_wav_mono_fn=read_wav_mono,
        target_sample_rate=44100, trim=True, normalise=False, max_samples=0,
    )
    psr = prepared_stems[0].get("sample_rate", 44100) if prepared_stems else 44100
    prepared_stems, _ = correct_stem_polarity(prepared_stems, psr)
    masking_results = analyze_stems_masking(stems_raw, read_wav_mono=read_wav_mono, spectral_bands=spectral_bands)
    plan = generate_mix_plan(profiles, masking_results, genre="electronic", target_lufs=-14.0)
    roles = infer_musical_roles(profiles, prepared_stems)
    plan.musical_roles = [r.to_dict() for r in roles]
    plan.arrangement = infer_arrangement(prepared_stems).to_dict()
    plan.mono_compatibility = analyze_mono_compatibility(prepared_stems, plan.arrangement).to_dict()
    existing_dynamics = analyze_stems_for_dynamics(
        prepared_stems, profiles, prepared_stems[0]["sample_rate"] if prepared_stems else 44_100,
    )
    plan.relationships = [r.to_dict() for r in infer_relationships(
        profiles, masking_results, roles, plan.arrangement, prepared_stems, existing_dynamics,
    )]
    render_result = validate_and_correct_mix(
        prepared_stems, plan, render_fn=mix_and_render_stems, max_iterations=3,
    )

    peak_gb = _rss_gb()  # ru_maxrss is a running peak, not a snapshot -- this
    # is the highest RSS reached at any point in this process, including
    # everything above, not just this instant.

    # Correctness sanity -- a memory guard is pointless if it accidentally
    # started asserting against a pipeline that silently failed to render.
    # validate_and_correct_mix's real return shape (verified by reading
    # mix_validator.py's finalize()): {"report": <analyze_wav output>,
    # "quality_gate": {"passed": bool, ...}, "history": [...], ...} -- no
    # "validation" key, despite that being a natural first guess.
    assert render_result is not None
    assert render_result["quality_gate"]["passed"] is True, render_result["quality_gate"]
    metrics = render_result.get("report", {}).get("metrics", {})
    if metrics:
        assert metrics.get("sample_peak", 0) <= 1.0 + 1e-6, "rendered output clipped"

    assert peak_gb < PEAK_RSS_BUDGET_GB, (
        f"AutoMix peak RSS {peak_gb:.2f}GB exceeds the {PEAK_RSS_BUDGET_GB}GB regression budget "
        f"(baseline before pipeline start was {baseline_gb:.2f}GB; measured 3.81GB for this exact "
        f"fixture on 2026-07-20). This is the same class of regression as the 53.1GB incident in "
        f"docs/audits/2026-07-16-detect-correct-and-perf.md -- check for a reintroduced "
        f".tolist()/list-based-audio round-trip in prepare_stems/read_wav_mono or the render loop "
        f"before assuming this is just normal growth."
    )

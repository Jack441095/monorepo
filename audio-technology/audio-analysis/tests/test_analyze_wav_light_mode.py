"""Proves analyze_wav's light=True mode is output-preserving for the exact
fields its two callers (podcast-check, delivery-check) read, matching the
"same numbers, just faster" discipline scripts/eval/golden_metrics.py
already established for the analysis hot path. light=False (the default)
is separately covered bit-exact by golden_metrics.py itself -- this file
is specifically the "light mode doesn't change the kept metrics" proof
that harness's own docstring anticipated: "The analysis hot path is about
to get efficiency refactors... Those refactors are only safe if we can
prove they produce the SAME NUMBERS, just faster."
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "business" / "app"))
sys.path.insert(0, str(ROOT / "scripts" / "eval"))
sys.path.insert(0, str(ROOT / "studio" / "audio_analysis"))

from audio_analysis.mix_review import mix_review  # noqa: E402
from audio_analysis.analysis_core.feature_cache import clear_analysis_cache  # noqa: E402
from golden_metrics import build_corpus  # noqa: E402

# The exact metrics podcast-check (audio_analysis/podcast/podcast_analysis.py)
# and delivery-check (audio_analysis/mixdown/delivery_conform.py) read.
_PODCAST_CHECK_FIELDS = (
    "integrated_lufs", "true_peak_dbfs", "peak_dbfs", "loudness_range_lu", "stereo_correlation",
)
_BAND_FIELDS = ("sub", "low_mids", "sibilance", "presence")
_DELIVERY_CHECK_FIELDS = (
    "integrated_lufs", "true_peak_dbfs", "peak_dbfs", "loudness_range_lu", "stereo_correlation",
)


def test_light_mode_with_bands_matches_full_mode_on_every_used_field():
    corpus = build_corpus()
    for name, wav_bytes in corpus.items():
        full = mix_review.analyze_wav(wav_bytes, f"{name}.wav", mix_goal="premaster")
        light = mix_review.analyze_wav(wav_bytes, f"{name}.wav", mix_goal="premaster", light=True, include_bands=True)

        assert light["ok"] is True
        assert "flags" not in light  # light mode returns metrics only, not a full report
        assert light["feature_set"]["analysis_profile"] == "mix_review.light.v1"
        assert full["feature_set"]["analysis_profile"] == "mix_review.full.v1"
        assert light["feature_set"]["source_hash"] == full["feature_set"]["source_hash"]
        full_m, light_m = full["metrics"], light["metrics"]

        for field in _PODCAST_CHECK_FIELDS:
            assert light_m[field] == full_m[field], f"[{name}] {field} differs: light={light_m[field]!r} full={full_m[field]!r}"
        for band in _BAND_FIELDS:
            assert light_m["bands"].get(band) == full_m["bands"].get(band), f"[{name}] bands.{band} differs"


def test_light_mode_without_bands_still_matches_on_non_band_fields():
    corpus = build_corpus()
    for name, wav_bytes in list(corpus.items())[:2]:  # a couple of clips is enough for this variant
        full = mix_review.analyze_wav(wav_bytes, f"{name}.wav", mix_goal="premaster")
        light = mix_review.analyze_wav(wav_bytes, f"{name}.wav", mix_goal="premaster", light=True, include_bands=False)

        full_m, light_m = full["metrics"], light["metrics"]
        for field in _DELIVERY_CHECK_FIELDS:
            assert light_m[field] == full_m[field], f"[{name}] {field} differs: light={light_m[field]!r} full={full_m[field]!r}"
        assert light_m["bands"] == {}  # not computed -- delivery-check never reads it


def test_light_mode_is_meaningfully_faster():
    """Not a strict benchmark (machine-load-sensitive), just a sanity check
    that light mode isn't accidentally doing MORE work than full mode."""
    import time

    corpus = build_corpus()
    name, wav_bytes = next(iter(corpus.items()))

    clear_analysis_cache()
    start = time.perf_counter()
    mix_review.analyze_wav(wav_bytes, f"{name}.wav", mix_goal="premaster")
    full_elapsed = time.perf_counter() - start

    clear_analysis_cache()
    start = time.perf_counter()
    mix_review.analyze_wav(wav_bytes, f"{name}.wav", mix_goal="premaster", light=True, include_bands=True)
    light_elapsed = time.perf_counter() - start

    assert light_elapsed < full_elapsed

"""Decide whether a DSP stage would actually do anything for a given stem,
using analysis that's already computed (StemProfile.frequency_profile from
stem_classifier.py) rather than adding new measurement cost.

Several render stages currently run unconditionally on every stem regardless
of whether that stem has anything for them to act on -- most notably the
per-stem resonance scan (mix_renderer.py stage 1B), which runs a full
FFT/ERB detection pass even on a pure sub-bass stem with nothing above
150Hz. docs/audits/2026-07-30-automix-cpp-kernel-and-vectorization-pass.md's
own conclusion is that the render loop is already vectorized/optimized and
the remaining lever is doing less DSP, not making the same DSP faster --
this module is that lever.

These are conservative, no-op-preserving skips: a stage is only marked
unneeded when the stem's own measured spectral content makes clear it
wouldn't meaningfully change the output, not a loosening of any correction
threshold. None of this flips a stage's opt-in default (apply_deesser etc.
stay exactly as gated as before) -- it only decides whether an
already-enabled stage is worth running for THIS stem.
"""

from __future__ import annotations

from ..analysis_core.dsp_metrics import BANDS

# A stem is "vocal-ish" (the only roles a de-esser makes sense for -- there
# is no sibilant "s" sound in a bass line or a pad, regardless of what its
# sibilance-band energy ratio happens to read).
_VOCAL_ROLES = frozenset({"vocal", "backing_vocal"})

# Below this share of total spectral energy, a band is "negligible" for the
# purposes of deciding whether a stage aimed at that content is worth
# running. Deliberately conservative -- false negatives (running a stage
# that turns out to be a no-op) cost a little CPU; false positives (skipping
# a stage that would have mattered) cost correctness, so this only fires
# when the energy is clearly absent.
_NEGLIGIBLE_ENERGY_RATIO = 0.02

# Matches podcast/podcast_analysis.py's PODCAST_BAND_HEURISTICS sibilance_max
# -- same "this is elevated enough to be a problem" threshold, reused here
# so the two sibilance judgments in the codebase agree with each other.
_SIBILANCE_ELEVATED_RATIO = 0.09


def _energy_below_hz(frequency_profile: dict[str, float], cutoff_hz: float) -> float | None:
    """Sum the frequency_profile share of every band that lies entirely
    below cutoff_hz, or None if no band resolves that finely (e.g. a
    25Hz cutoff falls inside the 20-60Hz "sub" band itself -- the 7-band
    profile has no way to tell what's below 25Hz specifically)."""
    qualifying = [name for name, _low_hz, high_hz in BANDS if high_hz <= cutoff_hz]
    if not qualifying:
        return None
    return sum(float(frequency_profile.get(name, 0.0)) for name in qualifying)


def needs_highpass(frequency_profile: dict[str, float] | None, cutoff_hz: float) -> bool:
    """False when the stem already has negligible energy below cutoff_hz --
    adding a highpass EQ band there would be a no-op cut. Defaults to True
    (keep the filter) whenever the 7-band profile can't resolve down to
    cutoff_hz finely enough to be confident -- a missed skip costs a little
    CPU, a wrong skip costs correctness."""
    if not frequency_profile or cutoff_hz <= 20.0:
        return True
    energy_below = _energy_below_hz(frequency_profile, cutoff_hz)
    if energy_below is None:
        return True
    return energy_below > _NEGLIGIBLE_ENERGY_RATIO


def needs_resonance_scan(frequency_profile: dict[str, float] | None) -> bool:
    """False when a stem has essentially no energy in the low_mids/mids/
    presence/sibilance/air range the resonance detector targets (e.g. a
    pure sub-bass or kick stem) -- running the full scan has nothing to
    find."""
    if not frequency_profile:
        return True
    upper_bands_energy = sum(
        float(frequency_profile.get(name, 0.0))
        for name, low_hz, _high_hz in BANDS
        if low_hz >= 150.0
    )
    return upper_bands_energy > _NEGLIGIBLE_ENERGY_RATIO


def needs_deesser(frequency_profile: dict[str, float] | None, instrument: str) -> bool:
    """True only for a vocal-ish role whose own measured sibilance-band
    (6-8kHz) energy is already elevated -- a de-esser has nothing to do on
    an instrumental stem or on a vocal that isn't sibilant."""
    if instrument not in _VOCAL_ROLES or not frequency_profile:
        return False
    return float(frequency_profile.get("sibilance", 0.0)) > _SIBILANCE_ELEVATED_RATIO


def needs_mid_carve(frequency_profile: dict[str, float] | None) -> bool:
    """False when a stem has negligible energy in the "mids" band
    (400-2000Hz) -- mix_renderer.py's vocal-lead mid-carve cuts a peaking
    band at 1.5kHz (squarely inside that band, so the 7-band profile
    resolves it cleanly, unlike needs_highpass's low-cutoff case) to make
    room for a lead vocal, on every stem in a role bucket regardless of
    whether that stem has anything there to carve (e.g. a bass-heavy pad
    or a sparse stem in that role)."""
    if not frequency_profile:
        return True
    return float(frequency_profile.get("mids", 0.0)) > _NEGLIGIBLE_ENERGY_RATIO

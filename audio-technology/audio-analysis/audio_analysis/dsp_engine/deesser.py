"""De-esser — a sibilance-tuned instance of the dynamic EQ band processor.

Closes the gap in docs/CODEBASE_FORWARD_PLAN_2026-07-31.md §3.1: mix_plan.
apply_deesser and config.deesser have existed in mix_decision_engine.py for
a while, and mix_renderer.py already calls `from ..dsp_engine.deesser import
apply_deesser` inside a try/except -- but this module never existed, so
enabling the flag silently did nothing.

A de-esser is a split-band compressor: isolate the sibilant band, then
reduce gain based on that band's own level so it only engages during actual
esses, not on every high-frequency transient in the mix. dynamic_eq.py's
apply_dynamic_eq_band already implements exactly that shape (isolate via a
resonant bandpass -> envelope-follow -> gain-reduce -> subtract back), so
this is a thin, sibilance-tuned wrapper over it rather than a new DSP
primitive. Nothing currently sets apply_deesser=True or populates
config.deesser -- per the roadmap this stays opt-in until a vocals-forward
blind A/B promotes it (see the forward-plan doc's guardrails).
"""

from __future__ import annotations

import numpy as np

from .dynamic_eq import apply_dynamic_eq_band

# Matches podcast/podcast_analysis.py's own PODCAST_BAND_HEURISTICS
# sibilance band definition (6-8 kHz); centered within it.
DEFAULT_FREQUENCY_HZ = 7000.0
DEFAULT_Q = 2.0
DEFAULT_THRESHOLD_DB = -24.0
DEFAULT_RATIO = 4.0
# Deliberately conservative -- forward-plan doc F1 specifies "cap <= 4 dB".
DEFAULT_MAX_REDUCTION_DB = 4.0
# Esses are short (tens of ms): fast attack to catch the onset, fast
# release so gain reduction doesn't linger into the following vowel.
DEFAULT_ATTACK_MS = 2.0
DEFAULT_RELEASE_MS = 60.0


def apply_deesser(
    left: np.ndarray,
    right: np.ndarray,
    *,
    sample_rate: int,
    frequency_hz: float = DEFAULT_FREQUENCY_HZ,
    q: float = DEFAULT_Q,
    threshold_db: float = DEFAULT_THRESHOLD_DB,
    ratio: float = DEFAULT_RATIO,
    max_reduction_db: float = DEFAULT_MAX_REDUCTION_DB,
    attack_ms: float = DEFAULT_ATTACK_MS,
    release_ms: float = DEFAULT_RELEASE_MS,
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce sibilance (harsh 's'/'sh' energy) around ``frequency_hz``
    without dulling the rest of the signal -- transparent when the band is
    quiet, capped at ``max_reduction_db`` so a false trigger can't dull a
    vocal."""
    return apply_dynamic_eq_band(
        left,
        right,
        frequency_hz=frequency_hz,
        sample_rate=sample_rate,
        q=q,
        threshold_db=threshold_db,
        ratio=ratio,
        max_reduction_db=max_reduction_db,
        attack_ms=attack_ms,
        release_ms=release_ms,
    )

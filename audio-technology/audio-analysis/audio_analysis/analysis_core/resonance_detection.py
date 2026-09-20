"""Automatic resonance/harshness detector — Phase 0 of the dynamic EQ plan.

See docs/SPECTRAL_DYNAMIC_EQ_PLUGIN_PLAN.md. This is the "detection brain" half
of a FabFilter Pro-Q-style dynamic EQ: given a single spectrum (not multiple
stems — see `stem_analysis.py` for the separate inter-stem masking detector),
find narrow bands that stick out above their own local frequency neighborhood
*and* persist over time, rather than a single transient peak. That combination
(prominence + persistence) is what distinguishes a genuine problem resonance
from an isolated transient or noise-floor blip.

Deliberately reuses the existing ERB (equivalent rectangular bandwidth —
the actual psychoacoustic frequency scale) infrastructure in `erb_masking.py`
rather than inventing a new frequency representation, and the existing FFT
windowing in `dsp_metrics.py` rather than a new spectral analysis path.
"""

from __future__ import annotations

import math

from .dsp_metrics import spectrum_magnitudes
from .erb_masking import compute_erb_profile, get_erb_bands


def _local_neighborhood_prominence_db(
    energies: list[float], band_idx: int, *, neighborhood_bands: int = 4
) -> float:
    """How much band ``band_idx``'s energy exceeds the mean of its nearby
    bands (excluding itself), in dB. Positive means it sticks out.

    A local (not global) comparison is what makes this a *resonance*
    detector rather than a simple "loudest bands" detector — a band that's
    merely part of a broad, gently-sloped spectral tilt (e.g. natural
    high-frequency rolloff) won't trigger this, only a genuinely narrow
    spike relative to its immediate surroundings.
    """
    n = len(energies)
    lo = max(0, band_idx - neighborhood_bands)
    hi = min(n, band_idx + neighborhood_bands + 1)
    neighbor_energies = [energies[i] for i in range(lo, hi) if i != band_idx]
    if not neighbor_energies:
        return 0.0
    neighbor_mean = sum(neighbor_energies) / len(neighbor_energies)
    band_energy = energies[band_idx]
    if neighbor_mean <= 1e-15 or band_energy <= 1e-15:
        return 0.0
    # Energies here are sums of squared FFT magnitudes (power domain, see
    # compute_erb_profile), so the ratio-to-dB conversion is 10*log10, not
    # 20*log10 (which would double-count already-squared quantities).
    return 10.0 * math.log10(band_energy / neighbor_mean)


def detect_resonant_bands(
    samples: list[float],
    sample_rate: int,
    *,
    num_bands: int = 40,
    frame_size: int = 4096,
    num_frames: int = 16,
    prominence_threshold_db: float = 6.0,
    persistence_threshold: float = 0.4,
    min_relative_energy: float = 0.002,
    protect_below_hz: float = 0.0,
) -> list[dict]:
    """Find candidate resonant bands: narrow spectral peaks that consistently
    stick out above their local neighborhood across multiple frames.

    Returns a list of dicts, one per flagged band, each with:
      - ``frequency_hz``: the ERB band's center frequency
      - ``mean_prominence_db``: average dB-above-neighborhood on the frames
        where it exceeded the threshold
      - ``persistence``: fraction of analyzed frames (0.0-1.0) where this
        band exceeded ``prominence_threshold_db`` — the "is this a real,
        sustained problem or just one transient" signal
      - ``band_index``: index into the 0..num_bands-1 ERB band list, for
        callers that need to map back to `get_erb_bands()`

    ``protect_below_hz`` drops any flagged band at or below that frequency.
    This is fundamental protection: a narrow, persistent, prominent peak at a
    kick's ~60-100 Hz or a bass's fundamental IS the instrument's body, not a
    resonance to reduce — dynamically cutting it weakens the low end, the exact
    opposite of the goal. Calibrated 2026-07-16 against real stems, where the
    reggueton kick's own 99 Hz fundamental was being flagged (see
    docs/DETECT_CORRECT_CHAIN_MAP_2026-07-16.md and the resonance calibration
    findings). Default 0.0 keeps the original behavior; the renderer opts in
    per stem based on musical role.

    Sorted by persistence first, then mean prominence — the most
    consistently-problematic bands first, matching how a mixing engineer
    would prioritize which resonance to address first.
    """
    if samples is None or sample_rate <= 0 or len(samples) < frame_size:  # len guard: array-safe
        return []

    erb_bands = get_erb_bands(num_bands=num_bands)
    hop = max(1, (len(samples) - frame_size) // max(1, num_frames - 1))

    # per-band: how many frames it was flagged, and the summed prominence
    # on those flagged frames only (so mean_prominence_db reflects "how bad
    # when it happens", not diluted by frames where it wasn't a problem)
    flagged_frame_count = [0] * num_bands
    flagged_prominence_sum = [0.0] * num_bands
    analyzed_frames = 0

    for f in range(num_frames):
        start = f * hop
        end = start + frame_size
        if end > len(samples):
            break
        frame = samples[start:end]
        mags, n = spectrum_magnitudes(frame, sample_rate, size=frame_size)
        if not mags or n <= 0:
            continue
        energies = compute_erb_profile(mags, sample_rate, n, num_bands=num_bands)
        total_energy = sum(energies) or 1.0
        analyzed_frames += 1

        for band_idx, band_energy in enumerate(energies):
            # Ignore bands with negligible energy in this frame — comparing
            # near-silent bands to their (also near-silent) neighbors
            # produces noisy, meaningless dB ratios.
            if band_energy / total_energy < min_relative_energy:
                continue
            prominence_db = _local_neighborhood_prominence_db(energies, band_idx)
            if prominence_db >= prominence_threshold_db:
                flagged_frame_count[band_idx] += 1
                flagged_prominence_sum[band_idx] += prominence_db

    if analyzed_frames == 0:
        return []

    results = []
    for band_idx in range(num_bands):
        persistence = flagged_frame_count[band_idx] / analyzed_frames
        if persistence < persistence_threshold:
            continue
        mean_prominence_db = flagged_prominence_sum[band_idx] / flagged_frame_count[band_idx]
        center_hz, _, _ = erb_bands[band_idx]
        # Fundamental protection: never flag a band at/below the protected
        # frequency — that region is the instrument's body, not a resonance.
        if protect_below_hz > 0.0 and center_hz <= protect_below_hz:
            continue
        results.append({
            "band_index": band_idx,
            "frequency_hz": round(center_hz, 1),
            "mean_prominence_db": round(mean_prominence_db, 2),
            "persistence": round(persistence, 3),
        })

    results.sort(key=lambda r: (r["persistence"], r["mean_prominence_db"]), reverse=True)
    return results


def detect_resonant_bands_section_aware(
    samples: list[float],
    sample_rate: int,
    sections: list[dict] | None = None,
    *,
    num_bands: int = 40,
    frame_size: int = 4096,
    num_frames_per_section: int = 16,
    prominence_threshold_db: float = 6.0,
    persistence_threshold: float = 0.4,
    min_relative_energy: float = 0.002,
    protect_below_hz: float = 0.0,
) -> list[dict]:
    """Detect resonant bands across song arrangement sections.

    If ``sections`` is provided (list of dicts with ``start_sample``/``end_sample`` or ``start_s``/``end_s``),
    runs resonance detection per section and aggregates results with section metadata, so a resonance
    that occurs only in a specific section (e.g. chorus) is identified with section bounds.
    If ``sections`` is None or empty, falls back to standard ``detect_resonant_bands``.
    """
    if not sections or len(samples) < frame_size:
        return detect_resonant_bands(
            samples,
            sample_rate,
            num_bands=num_bands,
            frame_size=frame_size,
            num_frames=num_frames_per_section,
            prominence_threshold_db=prominence_threshold_db,
            persistence_threshold=persistence_threshold,
            min_relative_energy=min_relative_energy,
            protect_below_hz=protect_below_hz,
        )

    all_results: list[dict] = []
    seen_keys: set[tuple[int, str]] = set()

    for sec in sections:
        sec_name = str(sec.get("label") or sec.get("section") or "section")
        start_idx = sec.get("start_sample")
        end_idx = sec.get("end_sample")
        if start_idx is None and "start_s" in sec:
            start_idx = int(sec["start_s"] * sample_rate)
        if end_idx is None and "end_s" in sec:
            end_idx = int(sec["end_s"] * sample_rate)

        start_idx = max(0, start_idx or 0)
        end_idx = min(len(samples), end_idx or len(samples))

        sec_samples = samples[start_idx:end_idx]
        if len(sec_samples) < frame_size:
            continue

        sec_res = detect_resonant_bands(
            sec_samples,
            sample_rate,
            num_bands=num_bands,
            frame_size=frame_size,
            num_frames=num_frames_per_section,
            prominence_threshold_db=prominence_threshold_db,
            persistence_threshold=persistence_threshold,
            min_relative_energy=min_relative_energy,
            protect_below_hz=protect_below_hz,
        )

        for res in sec_res:
            res_entry = {**res, "section": sec_name, "start_sample": start_idx, "end_sample": end_idx}
            key = (res["band_index"], sec_name)
            if key not in seen_keys:
                seen_keys.add(key)
                all_results.append(res_entry)

    all_results.sort(key=lambda r: (r.get("persistence", 0), r.get("mean_prominence_db", 0)), reverse=True)
    return all_results

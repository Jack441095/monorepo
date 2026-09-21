"""KENN Psychoacoustic Engine: 40-Band ERB Masking & Auditory Visibility Solver.

Implements Equivalent Rectangular Bandwidth (Glasberg & Moore 1990), Terhardt's
Absolute Threshold of Hearing (ATH), simultaneous psychoacoustic masking threshold
curves using Schroeder spreading, and empirical spectral carving action generation
clamped strictly to KENN's Hardware Safety Policy (max cut <= 3.0 dB).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def hz_to_erb(f: float) -> float:
    """Convert frequency in Hz to ERB rate/scale (Glasberg & Moore 1990)."""
    if f <= 0.0:
        return 0.0
    return 21.4 * math.log10(0.00437 * f + 1.0)


def erb_to_hz(erb: float) -> float:
    """Convert ERB rate/scale to frequency in Hz."""
    if erb <= 0.0:
        return 0.0
    return (10.0 ** (erb / 21.4) - 1.0) / 0.00437


def absolute_threshold_of_hearing(f: float) -> float:
    """Terhardt's (1979) Absolute Threshold of Hearing in dB SPL."""
    if f <= 0.0:
        return 100.0  # Inaudible
    f_khz = max(f / 1000.0, 1e-4)
    ath = 3.64 * (f_khz ** -0.8) - 6.5 * math.exp(-0.6 * ((f_khz - 3.3) ** 2)) + 0.001 * (f_khz ** 4)
    return ath


def get_erb_bands(num_bands: int = 40) -> List[Tuple[float, float, float]]:
    """Define center, start, and end frequencies for discrete ERB bands between 20 Hz and 20 kHz."""
    e_min = hz_to_erb(20.0)
    e_max = hz_to_erb(20000.0)
    step = (e_max - e_min) / num_bands

    bands = []
    for i in range(num_bands):
        e_start = e_min + i * step
        e_end = e_min + (i + 1) * step
        e_center = e_start + 0.5 * step

        bands.append((
            erb_to_hz(e_center),
            erb_to_hz(e_start),
            erb_to_hz(e_end)
        ))
    return bands


def compute_erb_spectrum(
    magnitudes: List[float],
    sample_rate: int = 44100,
    fft_size: int = 4096,
    num_bands: int = 40,
) -> List[float]:
    """Group FFT magnitude spectrum bins into discrete ERB bands and return energy per band."""
    energies = [0.0] * num_bands
    if not magnitudes or sample_rate <= 0 or fft_size <= 0:
        return energies

    bin_freq_step = sample_rate / fft_size
    mags = np.asarray(magnitudes, dtype=np.float64)
    freqs = np.arange(len(mags), dtype=np.float64) * bin_freq_step
    valid = (freqs >= 20.0) & (freqs <= 20000.0)
    if not np.any(valid):
        return energies

    e_min = hz_to_erb(20.0)
    e_max = hz_to_erb(20000.0)
    erb_vals = 21.4 * np.log10(0.00437 * freqs[valid] + 1.0)
    band_idx = ((erb_vals - e_min) / (e_max - e_min) * num_bands).astype(np.int64)
    in_range = (band_idx >= 0) & (band_idx < num_bands)

    weights = mags[valid][in_range] ** 2
    summed = np.bincount(band_idx[in_range], weights=weights, minlength=num_bands)[:num_bands]
    return summed.tolist()


def compute_combined_masking_threshold(
    other_tracks_energies: List[List[float]],
    erb_bands: List[Tuple[float, float, float]],
    reference_spl_0dbfs: float = 90.0,
) -> List[float]:
    """Compute simultaneous masking threshold (in dB SPL) using Schroeder spreading.

    Args:
        other_tracks_energies: Energy vectors (length B) for all other competing tracks.
        erb_bands: List of (center_freq, start_freq, end_freq) tuples.
        reference_spl_0dbfs: Calibrated SPL level corresponding to 0 dBFS peak.
    """
    num_bands = len(erb_bands)
    combined_threshold_linear = [0.0] * num_bands

    # Baseline: Absolute Threshold of Hearing (ATH)
    for b_idx, (fc, _, _) in enumerate(erb_bands):
        ath_db = absolute_threshold_of_hearing(fc)
        combined_threshold_linear[b_idx] = 10.0 ** (ath_db / 10.0)

    if not other_tracks_energies:
        return [10.0 * math.log10(max(val, 1e-12)) for val in combined_threshold_linear]

    total_other_energy = [0.0] * num_bands
    for energy_vec in other_tracks_energies:
        for idx, eng in enumerate(energy_vec):
            total_other_energy[idx] += eng

    # Schroeder spreading function across ERB bands
    for masker_idx, energy in enumerate(total_other_energy):
        if energy <= 1e-15:
            continue

        dbfs = 10.0 * math.log10(max(energy, 1e-15))
        masker_spl = dbfs + reference_spl_0dbfs
        fc_masker = erb_bands[masker_idx][0]
        z_masker = hz_to_erb(fc_masker)

        for target_idx, (fc_target, _, _) in enumerate(erb_bands):
            z_target = hz_to_erb(fc_target)
            dz = z_target - z_masker

            # Schroeder asymmetric spreading slope: 25 dB/ERB downward, 15 dB/ERB upward
            attenuation = 25.0 * abs(dz) if dz < 0.0 else 15.0 * abs(dz)
            masking_level_spl = masker_spl - 10.0 - attenuation

            combined_threshold_linear[target_idx] += 10.0 ** (masking_level_spl / 10.0)

    return [10.0 * math.log10(max(val, 1e-12)) for val in combined_threshold_linear]


def calculate_auditory_visibility(
    track_energy: List[float],
    masking_threshold_spl: List[float],
    reference_spl_0dbfs: float = 90.0,
) -> Tuple[float, List[float]]:
    """Calculate the perceptual visibility score (0.0=fully masked, 1.0=fully visible)."""
    num_bands = len(track_energy)
    band_visibilities = [1.0] * num_bands
    total_energy_linear = sum(track_energy)
    if total_energy_linear <= 1e-15:
        return 0.0, [0.0] * num_bands

    visible_energy_sum = 0.0

    for idx, eng in enumerate(track_energy):
        if eng <= 1e-15:
            band_visibilities[idx] = 0.0
            continue

        track_db = 10.0 * math.log10(max(eng, 1e-15))
        track_spl = track_db + reference_spl_0dbfs
        threshold_spl = masking_threshold_spl[idx]

        if track_spl <= threshold_spl:
            band_visibilities[idx] = 0.0
        else:
            visible_linear = (10.0 ** (track_spl / 10.0)) - (10.0 ** (threshold_spl / 10.0))
            ratio = min(1.0, max(0.0, visible_linear / (10.0 ** (track_spl / 10.0))))
            band_visibilities[idx] = ratio
            visible_energy_sum += visible_linear * (10.0 ** (-reference_spl_0dbfs / 10.0))

    overall_visibility = min(1.0, max(0.0, visible_energy_sum / total_energy_linear))
    return overall_visibility, band_visibilities


def compute_track_masking_matrix(
    track_profiles: List[Dict[str, Any]],
    erb_bands: Optional[List[Tuple[float, float, float]]] = None,
    reference_spl_0dbfs: float = 90.0,
) -> Dict[str, Any]:
    """Compute full pairwise masking ratios and auditory visibility scores across all tracks.

    Args:
        track_profiles: List of track dicts with keys: 'index', 'name', 'erb_profile' (length 40).
        erb_bands: Optional precomputed 40-band ERB band definitions.
        reference_spl_0dbfs: Calibration reference.
    """
    if erb_bands is None:
        erb_bands = get_erb_bands(num_bands=40)

    num_tracks = len(track_profiles)
    masking_matrix: Dict[str, Dict[str, float]] = {}
    track_visibilities: Dict[str, float] = {}
    pairwise_clashes: List[Dict[str, Any]] = []

    # 1. Compute overall visibility for each track against all other tracks combined
    for i, target in enumerate(track_profiles):
        t_name = target.get("name", f"Track {i}")
        other_energies = [
            other["erb_profile"]
            for j, other in enumerate(track_profiles)
            if i != j and "erb_profile" in other
        ]
        threshold = compute_combined_masking_threshold(
            other_energies, erb_bands, reference_spl_0dbfs=reference_spl_0dbfs
        )
        vis, band_vis = calculate_auditory_visibility(
            target.get("erb_profile", [0.0] * len(erb_bands)),
            threshold,
            reference_spl_0dbfs=reference_spl_0dbfs,
        )
        track_visibilities[t_name] = round(vis, 3)

    # 2. Compute pairwise masking clashes
    for i, stem_a in enumerate(track_profiles):
        name_a = stem_a.get("name", f"Track {i}")
        energy_a = stem_a.get("erb_profile", [])
        masking_matrix[name_a] = {}

        for j, stem_b in enumerate(track_profiles):
            if i == j:
                continue
            name_b = stem_b.get("name", f"Track {j}")
            energy_b = stem_b.get("erb_profile", [])

            # Measure how severely stem_a masks stem_b in shared active bands
            severe_bands = []
            for b_idx in range(min(len(energy_a), len(energy_b))):
                ea = energy_a[b_idx]
                eb = energy_b[b_idx]
                if ea > 1e-6 and eb > 1e-6:
                    ratio = ea / (ea + eb)
                    if ratio > 0.70:  # stem_a overpowers stem_b by > 70% energy
                        fc, _, _ = erb_bands[b_idx]
                        severe_bands.append({"band_idx": b_idx, "center_hz": round(fc, 1), "masking_ratio": round(ratio, 2)})

            if severe_bands:
                # Average severity in clashed bands
                avg_mask = sum(b["masking_ratio"] for b in severe_bands) / len(severe_bands)
                masking_matrix[name_a][name_b] = round(avg_mask, 3)
                pairwise_clashes.append({
                    "masker_track": name_a,
                    "masker_index": stem_a.get("index", i),
                    "victim_track": name_b,
                    "victim_index": stem_b.get("index", j),
                    "clash_bands": severe_bands,
                    "severity_ratio": round(avg_mask, 3),
                })

    return {
        "status": "success",
        "total_tracks": num_tracks,
        "track_visibilities": track_visibilities,
        "pairwise_clashes": pairwise_clashes,
        "masking_matrix": masking_matrix,
    }


def generate_spectral_carving_proposals(
    masking_matrix_result: Dict[str, Any],
    max_cut_db: float = 3.0,
) -> List[Dict[str, Any]]:
    """Convert psychoacoustic masking clashes into surgical EQ Eight carving actions.

    Adheres strictly to KENN's Hardware Safety Policy: delta gain <= max_cut_db (3.0 dB).
    """
    proposals: List[Dict[str, Any]] = []
    clashes = masking_matrix_result.get("pairwise_clashes", [])

    for clash in clashes:
        masker_name = clash["masker_track"]
        masker_idx = clash["masker_index"]
        victim_name = clash["victim_track"]
        victim_idx = clash["victim_index"]
        bands = clash.get("clash_bands", [])

        if not bands:
            continue

        # Find center of strongest masking clash
        worst_band = max(bands, key=lambda b: b["masking_ratio"])
        fc = worst_band["center_hz"]
        ratio = worst_band["masking_ratio"]

        # Calculate surgical cut: 1.5 dB base to max_cut_db (clamped to 3.0 dB)
        cut_db = min(max_cut_db, round(1.5 + (ratio - 0.7) * 5.0, 1))

        # Determine appropriate Q: Sub/bass uses narrower Q (1.8-2.5), mids use 1.2-1.6
        q_factor = 2.2 if fc < 200.0 else (1.4 if fc < 2000.0 else 1.2)

        proposals.append({
            "code": "PSYCHOACOUSTIC_SPECTRAL_CARVE",
            "masker_track": masker_name,
            "masker_index": masker_idx,
            "victim_track": victim_name,
            "victim_index": victim_idx,
            "target_frequency_hz": fc,
            "q_bandwidth": q_factor,
            "suggested_cut_db": -cut_db,
            "reasoning": f"{masker_name} masks {victim_name} at {fc:.0f} Hz (Masking Ratio: {ratio*100:.0f}%).",
            "action": f"Cut {cut_db:.1f} dB at {fc:.0f} Hz (Q={q_factor}) on {masker_name} to unmask {victim_name}.",
            "proposed_osc_mutation": {
                "device_type": "EqEight",
                "track_index": masker_idx,
                "parameter": "Band_Frequency_Cut",
                "frequency_hz": fc,
                "gain_delta_db": -cut_db,
                "q": q_factor,
            },
        })

    return proposals


def compute_dynamic_sidechain_ducking(
    kick_energy: float,
    bass_energy: float,
    target_band_hz: Tuple[float, float] = (40.0, 90.0),
    max_ducking_db: float = 3.0,
    attack_ms: float = 10.0,
    release_ms: float = 120.0,
) -> Dict[str, Any]:
    """Compute dynamic psychoacoustic sidechain ducking curve for kick & 808/sub-bass collision.

    Dynamically calculates the reduction required in the fundamental collision band
    (default 40-90 Hz), bounded strictly by max_ducking_db (<= 3.0 dB safety limit).

    Returns envelope parameters, gain attenuation, and recommended EQ / Compressor setting.
    """
    if kick_energy <= 0.0 or bass_energy <= 0.0:
        return {
            "ducking_required": False,
            "target_band_hz": target_band_hz,
            "gain_reduction_db": 0.0,
            "attack_ms": attack_ms,
            "release_ms": release_ms,
            "ratio": 1.0,
        }

    # Ratio of kick energy to combined low-end energy
    collision_ratio = kick_energy / (kick_energy + bass_energy)

    # If kick energy accounts for > 40% of low-end energy, apply proportionate ducking
    if collision_ratio > 0.40:
        duck_amount = min(max_ducking_db, round((collision_ratio - 0.40) * 8.0, 1))
        # Ensure at least 1.0 dB ducking if collision triggered
        duck_amount = max(1.0, duck_amount)
    else:
        duck_amount = 0.0

    return {
        "ducking_required": duck_amount > 0.0,
        "target_band_hz": target_band_hz,
        "gain_reduction_db": -duck_amount,
        "collision_ratio": round(collision_ratio, 3),
        "attack_ms": attack_ms,
        "release_ms": release_ms,
        "suggested_threshold_db": -18.0 if duck_amount > 0 else 0.0,
        "suggested_ratio": 3.0 if duck_amount >= 2.0 else 2.0,
    }


__all__ = [
    "hz_to_erb",
    "erb_to_hz",
    "absolute_threshold_of_hearing",
    "get_erb_bands",
    "compute_erb_spectrum",
    "compute_combined_masking_threshold",
    "calculate_auditory_visibility",
    "compute_track_masking_matrix",
    "generate_spectral_carving_proposals",
    "compute_dynamic_sidechain_ducking",
]

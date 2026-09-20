"""ERB critical band masking detector, simultaneous masking threshold curves, and dynamic carving advisor."""

from __future__ import annotations
import math
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
    f_khz = f / 1000.0
    # Guard against division by zero or negative exponents
    f_khz = max(f_khz, 1e-4)
    ath = 3.64 * (f_khz ** -0.8) - 6.5 * math.exp(-0.6 * ((f_khz - 3.3) ** 2)) + 0.001 * (f_khz ** 4)
    return ath


def get_erb_bands(num_bands: int = 40) -> list[tuple[float, float, float]]:
    """Define center, start, and end frequencies for B discrete ERB bands between 20 Hz and 20 kHz."""
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


def compute_erb_profile(
    magnitudes: list[float],
    sample_rate: int,
    fft_size: int,
    num_bands: int = 40
) -> list[float]:
    """Group FFT magnitude spectrum bins into discrete ERB bands and return energy per band."""
    energies = [0.0] * num_bands

    if not magnitudes or sample_rate <= 0 or fft_size <= 0:
        return energies

    bin_freq_step = sample_rate / fft_size

    # Vectorized equivalent of the original per-bin Python loop (measured
    # 2026-07-30: hz_to_erb() was being called ~5570x per real render call of
    # this function -- 3x per in-range bin, including the loop-invariant
    # e_min/e_max recomputed every iteration -- and this function itself
    # dominated infer_relationships' render-time share). np.bincount is the
    # vectorized form of "sum values grouped by an integer band index";
    # everything else here is elementwise math.log10 -> np.log10 (same
    # underlying libm call for scalar-equivalent double inputs) and Python
    # int() truncation -> .astype(int) (equivalent for this function's
    # always-non-negative [0, num_bands] domain).
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
    other_stems_energies: list[list[float]],
    erb_bands: list[tuple[float, float, float]],
    reference_spl_0dbfs: float = 90.0
) -> list[float]:
    """Compute the combined masking threshold (in dB SPL) across ERB bands using Schroeder spreading.

    Args:
        other_stems_energies: List of energy vectors (length B) for all OTHER stems.
        erb_bands: List of (center_freq, start_freq, end_freq) tuples.
        reference_spl_0dbfs: Calibrated SPL level corresponding to 0 dBFS peak.
    """
    num_bands = len(erb_bands)
    combined_threshold_linear = [0.0] * num_bands
    
    # Add absolute threshold of hearing (ATH) first
    for b_idx, (fc, _, _) in enumerate(erb_bands):
        ath_db = absolute_threshold_of_hearing(fc)
        combined_threshold_linear[b_idx] = 10.0 ** (ath_db / 10.0)
        
    if not other_stems_energies:
        return [10.0 * math.log10(max(val, 1e-12)) for val in combined_threshold_linear]

    # Convert energy vectors to estimated dB SPL
    # Sum the energies of all other stems
    total_other_energy = [0.0] * num_bands
    for energy_vec in other_stems_energies:
        for idx, eng in enumerate(energy_vec):
            total_other_energy[idx] += eng
            
    # For each band, calculate its masking contribution to all other bands
    for masker_idx, energy in enumerate(total_other_energy):
        if energy <= 1e-15:
            continue
        
        # Convert total energy in band to dB SPL
        # Normalize by assuming 1.0 energy is roughly -12 dBFS
        dbfs = 10.0 * math.log10(max(energy, 1e-15))
        masker_spl = dbfs + reference_spl_0dbfs
        
        # Center ERB rate
        fc_masker = erb_bands[masker_idx][0]
        z_masker = hz_to_erb(fc_masker)
        
        for target_idx, (fc_target, _, _) in enumerate(erb_bands):
            z_target = hz_to_erb(fc_target)
            dz = z_target - z_masker
            
            # Schroeder spreading function slopes
            if dz < 0.0:
                attenuation = 25.0 * abs(dz)
            else:
                attenuation = 15.0 * abs(dz)
                
            # Tone-masking-noise offset (approx 10 dB)
            masking_level_spl = masker_spl - 10.0 - attenuation
            
            # Accumulate in linear power domain
            combined_threshold_linear[target_idx] += 10.0 ** (masking_level_spl / 10.0)
            
    # Convert back to dB SPL
    return [10.0 * math.log10(max(val, 1e-12)) for val in combined_threshold_linear]


def calculate_visibility(
    stem_energy: list[float],
    masking_threshold_spl: list[float],
    reference_spl_0dbfs: float = 90.0
) -> tuple[float, list[float]]:
    """Calculate the perceptual visibility score (0.0 to 1.0) of a stem.

    Returns:
        overall_visibility: weighted visibility across all bands
        band_visibilities: visibility per band
    """
    num_bands = len(stem_energy)
    band_visibilities = [1.0] * num_bands
    total_energy_linear = sum(stem_energy)
    if total_energy_linear <= 1e-15:
        return 0.0, [0.0] * num_bands
        
    visible_energy_sum = 0.0
    
    for idx, eng in enumerate(stem_energy):
        if eng <= 1e-15:
            band_visibilities[idx] = 0.0
            continue
            
        stem_db = 10.0 * math.log10(max(eng, 1e-15))
        stem_spl = stem_db + reference_spl_0dbfs
        
        threshold_spl = masking_threshold_spl[idx]
        
        # Calculate portion of signal above masking threshold
        if stem_spl <= threshold_spl:
            band_visibilities[idx] = 0.0
        else:
            # visible energy = total_energy - masked_energy
            visible_spl = stem_spl
            masked_spl = threshold_spl
            visible_linear = (10.0 ** (visible_spl / 10.0)) - (10.0 ** (masked_spl / 10.0))
            band_visibilities[idx] = min(1.0, max(0.0, visible_linear / (10.0 ** (visible_spl / 10.0))))
            visible_energy_sum += visible_linear * (10.0 ** (-reference_spl_0dbfs / 10.0)) # Scale back to original domain
            
    overall_visibility = min(1.0, max(0.0, visible_energy_sum / total_energy_linear))
    return overall_visibility, band_visibilities


def generate_carving_suggestions(
    stems: list[dict],
    heatmap: dict,
    erb_bands: list[tuple[float, float, float]],
    reference_spl_0dbfs: float = 90.0
) -> list[dict]:
    """Generate dynamic EQ or sidechain carving suggestions from masking matrix conflicts."""
    suggestions = []
    
    # Analyze each pair of stems
    for stem_idx_a, stem_a in enumerate(stems):
        name_a = stem_a["name"]
        energy_a = stem_a["erb_profile"]
        
        for stem_idx_b, stem_b in enumerate(stems):
            name_b = stem_b["name"]
            if name_a == name_b:
                continue
                
            energy_b = stem_b["erb_profile"]
            
            # Find the bands where stem_a masks stem_b heavily
            # Masking ratio = energy_a / (energy_a + energy_b)
            # Find bands with masking ratio > 0.75 and significant energy in both
            conflicts = []
            for b_idx in range(len(erb_bands)):
                eng_a = energy_a[b_idx]
                eng_b = energy_b[b_idx]
                
                # Check for significant presence
                if eng_a > 1e-6 and eng_b > 1e-6:
                    ratio = eng_a / (eng_a + eng_b)
                    if ratio > 0.75:
                        conflicts.append((b_idx, ratio, eng_a, eng_b))
                        
            if not conflicts:
                continue
                
            # Group conflicts into regions (Low, Low-Mid, Mid-High)
            # Find the band with the highest conflict severity
            worst_conflict = max(conflicts, key=lambda c: c[1] * (c[2] + c[3]))
            b_idx, ratio, eng_a, eng_b = worst_conflict
            fc = erb_bands[b_idx][0]
            
            # Suggest based on frequency range
            if fc < 150.0:
                # Bass region conflict -> Sidechain compression
                # Typical sidechain triggers: Kick masking Bass, or Beat masking Synth
                suggestions.append({
                    "masker": name_a,
                    "masked": name_b,
                    "type": "sidechain_compression",
                    "frequency_hz": round(fc, 1),
                    "description": f"Sidechain the {name_b} to compress briefly when the {name_a} hits (kick/sub range below 150 Hz, fast attack, 60-100ms release).",
                    "daw_move": f"Sidechain {name_b} keyed to {name_a}: Thresh -15 dB, Ratio 4:1, Attack 5ms, Release 80ms"
                })
            elif 150.0 <= fc < 500.0:
                # Low-mid conflict -> Dynamic EQ carve
                suggestions.append({
                    "masker": name_a,
                    "masked": name_b,
                    "type": "dynamic_eq",
                    "frequency_hz": round(fc, 1),
                    "description": f"Apply a dynamic EQ cut on {name_a} at {round(fc, 0)} Hz, keyed to the {name_b} to clear muddy low-mid build-up.",
                    "daw_move": f"Dynamic EQ on {name_a}: -3.0 dB cut at {round(fc, 0)} Hz, Q=1.2, keyed to {name_b}"
                })
            elif 500.0 <= fc < 4000.0:
                # Mids conflict -> Dynamic EQ presence carve
                suggestions.append({
                    "masker": name_a,
                    "masked": name_b,
                    "type": "dynamic_eq",
                    "frequency_hz": round(fc, 1),
                    "description": f"Dipp a dynamic EQ band on {name_a} around {round(fc, 0)} Hz when {name_b} is active to protect mid-range/vocal presence.",
                    "daw_move": f"Dynamic EQ on {name_a}: -2.5 dB cut at {round(fc, 0)} Hz, Q=1.0, keyed to {name_b}"
                })
            else:
                # High frequency conflict -> Static notch / High Shelf
                suggestions.append({
                    "masker": name_a,
                    "masked": name_b,
                    "type": "static_notch",
                    "frequency_hz": round(fc, 1),
                    "description": f"Apply a gentle high-shelf or wide notch cut on {name_a} at {round(fc / 1000.0, 1)} kHz to free up air and sibilance clarity for {name_b}.",
                    "daw_move": f"Static EQ cut on {name_a}: -1.5 dB shelf at {round(fc, 0)} Hz, Q=0.7"
                })
                
    # Sort suggestions to return the most important first
    return suggestions[:8]


def simulate_clarity_improvement(
    stems: list[dict],
    suggestions: list[dict],
    erb_bands: list[tuple[float, float, float]],
    reference_spl_0dbfs: float = 90.0
) -> dict:
    """Simulate clarity improvements for each stem after applying suggestions."""
    improvements = {}
    for s in stems:
        improvements[s["name"]] = {
            "before": round(s["overall_visibility"], 2),
            "after": round(s["overall_visibility"], 2)
        }
        
    # For each stem, simulate the cuts from all suggestions where it is the "masked" (victim) stem
    for s in stems:
        name = s["name"]
        victim_suggestions = [sug for sug in suggestions if sug["masked"] == name]
        if not victim_suggestions:
            continue
            
        num_bands = len(erb_bands)
        num_frames = len(s["erb_profiles"])
        
        # Copy the energy profiles of all stems
        sim_profiles = {other["name"]: [list(p) for p in other["erb_profiles"]] for other in stems}
        
        for sug in victim_suggestions:
            masker_name = sug["masker"]
            freq = sug["frequency_hz"]
            
            # Find the closest ERB band index for this frequency
            e_val = hz_to_erb(freq)
            e_min = hz_to_erb(20.0)
            e_max = hz_to_erb(20000.0)
            b_idx = int((e_val - e_min) / (e_max - e_min) * num_bands)
            b_idx = max(0, min(num_bands - 1, b_idx))
            
            # Apply dynamic/static cut factor (typically -3 dB -> 0.5 linear energy)
            factor = 0.5
            if masker_name in sim_profiles:
                for f_idx in range(num_frames):
                    # Stems may have different durations, so their ERB
                    # profile lists do not necessarily have the same frame
                    # count.  The analysis pass already uses the final
                    # available frame for a shorter stem; mirror that here.
                    masker_profiles = sim_profiles[masker_name]
                    if masker_profiles:
                        masker_profiles[min(f_idx, len(masker_profiles) - 1)][b_idx] *= factor
                    
        # Recalculate visibility for the victim stem with the modified masker profiles
        visible_sum = 0.0
        total_energy_sum = 0.0
        
        for f_idx in range(num_frames):
            other_energies = []
            for other in stems:
                if other["name"] != name:
                    profiles = sim_profiles[other["name"]]
                    other_energies.append(profiles[min(f_idx, len(profiles) - 1)] if profiles else [0.0] * num_bands)
                    
            threshold = compute_combined_masking_threshold(other_energies, erb_bands, reference_spl_0dbfs)
            
            victim_profiles = s["erb_profiles"]
            stem_energy = victim_profiles[min(f_idx, len(victim_profiles) - 1)] if victim_profiles else [0.0] * num_bands
            total_energy_sum += sum(stem_energy)
            
            for b_idx, eng in enumerate(stem_energy):
                if eng <= 1e-15:
                    continue
                stem_spl = 10.0 * math.log10(eng) + reference_spl_0dbfs
                thresh_spl = threshold[b_idx]
                if stem_spl > thresh_spl:
                    visible_linear = (10.0 ** (stem_spl / 10.0)) - (10.0 ** (thresh_spl / 10.0))
                    visible_sum += visible_linear * (10.0 ** (-reference_spl_0dbfs / 10.0))
                    
        after_vis = min(1.0, max(0.0, visible_sum / (total_energy_sum + 1e-12)))
        improvements[name]["after"] = round(after_vis, 2)
        
    return improvements

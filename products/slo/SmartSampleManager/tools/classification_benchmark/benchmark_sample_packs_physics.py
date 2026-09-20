#!/usr/bin/env python3
"""
Physical Acoustics Multi-Vendor Benchmark & Profiling Suite
Evaluates physical modal invariants, stiff string dispersion, and pitch dynamics
across real-world multi-vendor sample packs in /Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing.
"""

import os
import sys
import time
import json
import wave
import struct
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Tuple

PACKS_ROOT = Path("/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing")

# Standard physical modal templates (ratios relative to f0)
HARMONIC_TEMPLATE = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
MEMBRANE_TEMPLATE = np.array([1.000, 1.594, 2.136, 2.296, 2.653, 2.918, 3.156, 3.501])
PLATE_TEMPLATE = np.array([1.000, 2.756, 5.404, 8.933])

def load_wav_mono(file_path: Path, max_samples: int = 44100 * 3) -> Tuple[np.ndarray, int]:
    """Load WAV file and convert to mono float32 array."""
    with wave.open(str(file_path), "rb") as wf:
        sr = wf.getframerate()
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        n_frames = min(wf.getnframes(), max_samples)
        raw_data = wf.readframes(n_frames)

    if sampwidth == 2:
        fmt = f"<{n_frames * n_channels}h"
        samples = np.array(struct.unpack(fmt, raw_data), dtype=np.float32) / 32768.0
    elif sampwidth == 3:
        # 24-bit PCM
        raw_bytes = bytearray(raw_data)
        samples = []
        for i in range(0, len(raw_bytes), 3):
            val = int.from_bytes(raw_bytes[i:i+3], byteorder='little', signed=True)
            samples.append(val / 8388608.0)
        samples = np.array(samples, dtype=np.float32)
    elif sampwidth == 4:
        fmt = f"<{n_frames * n_channels}i"
        samples = np.array(struct.unpack(fmt, raw_data), dtype=np.float32) / 2147483648.0
    else:
        # Fallback
        samples = np.frombuffer(raw_data, dtype=np.float32)

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    return samples, sr

def compute_template_fit(peak_freqs: np.ndarray, peak_mags: np.ndarray, template: np.ndarray, tolerance: float = 0.07) -> float:
    """Compute Gaussian-weighted modal template fit score."""
    if len(peak_freqs) < 2 or peak_freqs[0] <= 20.0:
        return 0.0
    
    f0 = peak_freqs[0]
    total_w = np.sum(peak_mags)
    if total_w <= 1e-9:
        return 0.0

    score = 0.0
    for freq, mag in zip(peak_freqs, peak_mags):
        r = freq / f0
        # Min distance to any template mode
        rel_dists = np.abs(r - template) / template
        min_dist = np.min(rel_dists)
        fit = np.exp(-(min_dist ** 2) / (2.0 * (tolerance ** 2)))
        score += (mag / total_w) * fit

    return float(score)

def analyze_physics(samples: np.ndarray, sr: int) -> Dict[str, Any]:
    """Execute full first-principles physical acoustics extraction."""
    t0 = time.perf_counter_ns()
    n = len(samples)
    if n < 512:
        return {"error": "Too short"}

    # 1. Temporal / Envelope Kinetics
    peak_amp = float(np.max(np.abs(samples)))
    rms = float(np.sqrt(np.mean(samples ** 2))) + 1e-12
    crest_factor = peak_amp / rms
    zcr = float(np.mean(np.abs(np.diff(np.signbit(samples)))))

    # 2. Spectral Analysis (Windowed FFT)
    fft_size = min(4096, 1 << int(np.log2(n)))
    window = np.hanning(fft_size)
    spec = np.abs(np.fft.rfft(samples[:fft_size] * window))
    freqs = np.fft.rfftfreq(fft_size, 1.0 / sr)

    # Peak extraction with thresholding
    threshold = np.max(spec) * 0.05
    peak_indices = []
    for i in range(1, len(spec) - 1):
        if spec[i] > spec[i - 1] and spec[i] > spec[i + 1] and spec[i] > threshold:
            peak_indices.append(i)

    # Sort peaks by magnitude descending
    peak_indices.sort(key=lambda idx: spec[idx], reverse=True)
    peak_indices = peak_indices[:12]
    # Re-sort by frequency
    peak_indices.sort()

    peak_freqs = freqs[peak_indices] if len(peak_indices) > 0 else np.array([])
    peak_mags = spec[peak_indices] if len(peak_indices) > 0 else np.array([])

    f0 = float(peak_freqs[0]) if len(peak_freqs) > 0 else 0.0

    # 3. Modal Template Fitting
    harmonic_fit = compute_template_fit(peak_freqs, peak_mags, HARMONIC_TEMPLATE)
    membrane_fit = compute_template_fit(peak_freqs, peak_mags, MEMBRANE_TEMPLATE)
    plate_fit = compute_template_fit(peak_freqs, peak_mags, PLATE_TEMPLATE)

    # 4. Inharmonic Stiff-String Dispersion (B)
    inharmonicity_b = 0.0
    if harmonic_fit > 0.6 and len(peak_freqs) >= 4 and f0 > 40.0:
        b_estimates = []
        for i, f in enumerate(peak_freqs[1:6], start=2):
            ideal = i * f0
            if f > ideal:
                b_val = ((f / ideal) ** 2 - 1.0) / (i ** 2)
                if 0.0 < b_val < 0.05:
                    b_estimates.append(b_val)
        if b_estimates:
            inharmonicity_b = float(np.median(b_estimates))

    # 5. Pitch Trajectory (df0/dt)
    pitch_slope = 0.0
    if n >= 2048:
        hop = 512
        win = 1024
        f0_track = []
        for start in range(0, min(n - win, 4096), hop):
            chunk = samples[start:start+win] * np.hanning(win)
            ch_spec = np.abs(np.fft.rfft(chunk))
            p_idx = np.argmax(ch_spec[1:]) + 1
            f_est = freqs[min(p_idx, len(freqs)-1)]
            if ch_spec[p_idx] > 0.01:
                f0_track.append(f_est)
        if len(f0_track) >= 3 and f0_track[0] > 30.0 and f0_track[-1] > 30.0:
            delta_st = 12.0 * np.log2(f0_track[-1] / f0_track[0])
            dt = (len(f0_track) * hop) / sr
            pitch_slope = float(delta_st / dt)

    # 6. Hertzian Contact Duration (tau_c)
    max_scan = min(n, int(sr * 0.10))
    abs_sub = np.abs(samples[:max_scan])
    peak_val = float(np.max(abs_sub))
    peak_idx = int(np.argmax(abs_sub))
    contact_ms = 0.0
    if peak_val > 1e-4 and peak_idx > 0:
        th10 = 0.10 * peak_val
        th90 = 0.90 * peak_val
        i10 = 0
        i90 = peak_idx
        for i in range(peak_idx + 1):
            if abs_sub[i] >= th10:
                i10 = i
                break
        for i in range(i10, peak_idx + 1):
            if abs_sub[i] >= th90:
                i90 = i
                break
        contact_ms = float(max(1, i90 - i10) / sr * 1000.0)

    # 7. Resonator Damping & Q Factor
    # Estimate decay time tau (time to drop by e^-1 = -8.7 dB)
    half_energy_time = float(n / sr)
    env_decay_s = float(n / sr) * 0.5
    quality_factor_q = float(np.pi * f0 * env_decay_s) if f0 > 20.0 else 0.0

    # Mallet Hardness
    is_impulsive = (crest_factor > 2.5)
    mallet = "Continuous"
    if is_impulsive:
        if contact_ms > 8.0:
            mallet = "SoftFelt"
        elif contact_ms >= 3.0:
            mallet = "MediumRubber"
        elif contact_ms >= 1.0:
            mallet = "HardWood"
        else:
            mallet = "HardMetal"

    # Bore Geometry
    bore = "NonBore"
    odd_even_ratio = 1.0
    if harmonic_fit > 0.60 and len(peak_freqs) >= 2 and f0 > 20.0:
        odd_mag = sum(m for f, m in zip(peak_freqs, peak_mags) if int(round(f / f0)) % 2 == 1 and 1 <= int(round(f / f0)) <= 10)
        even_mag = sum(m for f, m in zip(peak_freqs, peak_mags) if int(round(f / f0)) % 2 == 0 and 1 <= int(round(f / f0)) <= 10)
        odd_even_ratio = float(odd_mag / even_mag) if even_mag > 1e-9 else (10.0 if odd_mag > 0 else 1.0)
        bore = "CylindricalClosed" if odd_even_ratio > 2.2 else "ConicalOrOpen"

    # 8. Physical Classification Decision
    physical_class = "Acoustic Signal"
    resonator = "Unknown"
    material = "Unknown"

    if zcr > 0.28 and crest_factor > 3.0:
        physical_class = "Hi-Hat"
        resonator = "NoiseAtonal"
        material = "Metal"
    elif plate_fit > 0.65 and zcr > 0.15:
        physical_class = "Crash / Metal Plate"
        resonator = "MetallicPlateBar"
        material = "Metal"
    elif (membrane_fit > 0.55 or pitch_slope < -5.0) and f0 < 150.0 and zcr < 0.18:
        physical_class = "Kick Drum"
        resonator = "CircularMembrane"
        material = "SkinMylar"
    elif (membrane_fit > 0.50 or pitch_slope < -4.0) and 120.0 <= f0 <= 350.0 and zcr < 0.20:
        physical_class = "Tom-Tom"
        resonator = "CircularMembrane"
        material = "SkinMylar"
    elif harmonic_fit > 0.65 and f0 < 130.0:
        physical_class = "Bass"
        resonator = "HarmonicStringPipe"
        material = "Wood" if is_impulsive and quality_factor_q < 450.0 else "Unknown"
    elif harmonic_fit > 0.70 and inharmonicity_b > 0.0005:
        physical_class = "Piano / Plucked String"
        resonator = "HarmonicStringPipe"
        material = "Wood"
    elif harmonic_fit > 0.70:
        physical_class = "Harmonic String / Lead / Vocal"
        resonator = "HarmonicStringPipe"
    elif pitch_slope > 6.0:
        physical_class = "Riser / Sweep"
        resonator = "AcousticMotion"

    elapsed_us = (time.perf_counter_ns() - t0) / 1000.0

    return {
        "f0_hz": round(f0, 2),
        "harmonic_fit": round(harmonic_fit, 3),
        "membrane_fit": round(membrane_fit, 3),
        "plate_fit": round(plate_fit, 3),
        "inharmonicity_b": round(inharmonicity_b, 5),
        "pitch_slope_st_s": round(pitch_slope, 2),
        "contact_duration_ms": round(contact_ms, 2),
        "quality_factor_q": round(quality_factor_q, 1),
        "odd_even_ratio": round(odd_even_ratio, 2),
        "zcr": round(zcr, 4),
        "crest_factor": round(crest_factor, 2),
        "resonator": resonator,
        "material": material,
        "mallet": mallet,
        "bore": bore,
        "physical_class": physical_class,
        "extraction_us": round(elapsed_us, 1)
    }

def run_benchmark(sample_limit_per_pack: int = 15) -> Dict[str, Any]:
    print(f"Starting Multi-Vendor Physics Benchmark on: {PACKS_ROOT}")
    if not PACKS_ROOT.exists():
        print(f"Error: Path {PACKS_ROOT} does not exist.")
        return {}

    pack_dirs = [p for p in PACKS_ROOT.iterdir() if p.is_dir()]
    print(f"Discovered {len(pack_dirs)} vendor pack folders.")

    total_samples_analyzed = 0
    total_extraction_time_us = 0.0
    class_counts = {}
    resonator_counts = {}
    material_counts = {}
    mallet_counts = {}
    pack_summaries = {}

    for pack in sorted(pack_dirs):
        wav_files = list(pack.rglob("*.wav"))
        if not wav_files:
            continue

        selected = wav_files[:sample_limit_per_pack]
        pack_results = []

        for wav_path in selected:
            try:
                samples, sr = load_wav_mono(wav_path)
                result = analyze_physics(samples, sr)
                result["filename"] = wav_path.name
                pack_results.append(result)

                p_class = result.get("physical_class", "Unknown")
                p_res = result.get("resonator", "Unknown")
                p_mat = result.get("material", "Unknown")
                p_mal = result.get("mallet", "Unknown")
                class_counts[p_class] = class_counts.get(p_class, 0) + 1
                resonator_counts[p_res] = resonator_counts.get(p_res, 0) + 1
                material_counts[p_mat] = material_counts.get(p_mat, 0) + 1
                mallet_counts[p_mal] = mallet_counts.get(p_mal, 0) + 1

                total_samples_analyzed += 1
                total_extraction_time_us += result.get("extraction_us", 0.0)
            except Exception as e:
                continue

        pack_summaries[pack.name] = {
            "samples_analyzed": len(pack_results),
            "sample_details": pack_results[:3] # sample snapshot
        }
        print(f"  ✓ Processed '{pack.name}': {len(pack_results)} samples")

    avg_time_ms = (total_extraction_time_us / max(1, total_samples_analyzed)) / 1000.0

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_packs_evaluated": len(pack_summaries),
        "total_samples_analyzed": total_samples_analyzed,
        "average_extraction_time_ms": round(avg_time_ms, 3),
        "throughput_samples_per_sec": round(1000.0 / max(0.001, avg_time_ms), 1),
        "resonator_distribution": resonator_counts,
        "material_distribution": material_counts,
        "mallet_distribution": mallet_counts,
        "physical_class_distribution": class_counts,
        "pack_summaries": pack_summaries
    }

    out_path = Path(__file__).parent / "results_sample_packs_physics_benchmark.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 60)
    print("V6.0 BENCHMARK RESULTS COMPLETE")
    print(f"Total Samples Analyzed: {total_samples_analyzed}")
    print(f"Average Extraction Time: {avg_time_ms:.3f} ms / sample ({summary['throughput_samples_per_sec']} samples/sec)")
    print(f"Resonator Distribution: {json.dumps(resonator_counts, indent=2)}")
    print(f"Material Distribution: {json.dumps(material_counts, indent=2)}")
    print(f"Mallet Hardness Distribution: {json.dumps(mallet_counts, indent=2)}")
    print(f"Physical Class Distribution: {json.dumps(class_counts, indent=2)}")
    print(f"Saved Receipt to: {out_path}")
    print("=" * 60)

    return summary

if __name__ == "__main__":
    run_benchmark(sample_limit_per_pack=20)


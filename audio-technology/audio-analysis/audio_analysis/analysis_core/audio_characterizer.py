"""Dynamic transient and spectral characterization for short audio clips."""

from __future__ import annotations
import math

from audio_analysis.analysis_core.dsp_metrics import spectrum_magnitudes

def characterize_audio(samples: list[float], sample_rate: int) -> dict:
    """Analyze a single audio channel and extract physical characteristics."""
    if not samples or sample_rate <= 0:
        return {
            "attack_time_ms": 0.0,
            "crest_factor_db": 0.0,
            "spectral_centroid_hz": 0.0,
            "low_freq_decay_ms": 0.0,
            "peak_amp": 0.0,
            "rms_db": -99.0
        }

    # 1. Peak Amplitude and RMS
    abs_samples = [abs(s) for s in samples]
    peak_val = max(abs_samples)
    if peak_val < 1e-4:
        return {
            "attack_time_ms": 0.0,
            "crest_factor_db": 0.0,
            "spectral_centroid_hz": 0.0,
            "low_freq_decay_ms": 0.0,
            "peak_amp": float(peak_val),
            "rms_db": -99.0
        }
        
    rms = math.sqrt(sum(s * s for s in samples) / len(samples))
    rms_db = 20 * math.log10(max(rms, 1e-9))
    
    # Crest Factor (ratio of peak to RMS in dB)
    crest_factor_db = 20 * math.log10(peak_val / max(rms, 1e-9))

    # 2. Attack / Rise Time (onset to peak)
    peak_idx = abs_samples.index(peak_val)
    onset_idx = 0
    # Search backwards from the peak for the start of the transient (e.g., 2% of peak)
    threshold = 0.02 * peak_val
    for idx in range(peak_idx, -1, -1):
        if abs_samples[idx] < threshold:
            onset_idx = idx
            break
    attack_time_ms = (peak_idx - onset_idx) / sample_rate * 1000.0

    # 3. Spectral Centroid
    mags, n_fft = spectrum_magnitudes(samples, sample_rate, size=4096)
    centroid_hz = 0.0
    if mags and n_fft > 0:
        sum_mags = sum(mags)
        if sum_mags > 1e-6:
            sum_weighted = 0.0
            for bin_idx, mag in enumerate(mags):
                freq = bin_idx * (sample_rate / n_fft)
                sum_weighted += freq * mag
            centroid_hz = sum_weighted / sum_mags

    # 4. Low-Frequency (Sub-bass) Ring / Decay
    # Apply a simple 1-pole low-pass filter at 80 Hz
    # y[n] = alpha * x[n] + (1 - alpha) * y[n-1]
    fc = 80.0
    alpha = 2 * math.pi * fc / sample_rate
    alpha = max(0.0, min(1.0, alpha))
    
    lp_samples = []
    prev_y = 0.0
    for s in abs_samples:
        y = alpha * s + (1.0 - alpha) * prev_y
        lp_samples.append(y)
        prev_y = y
        
    lp_peak = max(lp_samples)
    low_freq_decay_ms = 0.0
    if lp_peak > 1e-4:
        lp_peak_idx = lp_samples.index(lp_peak)
        # Search forward from the peak for the envelope to decay below 10%
        lp_threshold = 0.10 * lp_peak
        drop_idx = len(lp_samples) - 1
        for idx in range(lp_peak_idx, len(lp_samples)):
            if lp_samples[idx] < lp_threshold:
                drop_idx = idx
                break
        low_freq_decay_ms = (drop_idx - lp_peak_idx) / sample_rate * 1000.0

    return {
        "attack_time_ms": round(attack_time_ms, 2),
        "crest_factor_db": round(crest_factor_db, 2),
        "spectral_centroid_hz": round(centroid_hz, 2),
        "low_freq_decay_ms": round(low_freq_decay_ms, 2),
        "peak_amp": round(float(peak_val), 4),
        "rms_db": round(rms_db, 2)
    }

"""Harmonic distortion, resonance peak, and inter-sample peak (ISP) analysis."""

from __future__ import annotations
import math
import numpy as np


def detect_fundamental_pitch(samples: np.ndarray, fs: int) -> float:
    """Detect dominant fundamental frequency using FFT-based autocorrelation."""
    if len(samples) < 512:
        return 0.0
    
    # Check signal energy
    peak_val = np.max(np.abs(samples))
    if peak_val < 1e-4:
        return 0.0
        
    s = samples - np.mean(samples)
    n = len(s)
    
    # Fast autocorrelation using FFT
    r = np.fft.irfft(np.abs(np.fft.rfft(s, n=2*n))**2)
    r = r[:n]
    
    # Human hearing frequency bounds: 30 Hz to 2500 Hz
    min_lag = int(fs / 2500)
    max_lag = int(fs / 30)
    
    if min_lag >= n or max_lag >= n:
        return 0.0
        
    r_subset = r[min_lag:max_lag]
    if len(r_subset) == 0:
        return 0.0
        
    peak_idx = np.argmax(r_subset) + min_lag
    
    # Verify local maximum peak boundary
    if 0 < peak_idx < n - 1:
        if r[peak_idx] > r[peak_idx - 1] and r[peak_idx] > r[peak_idx + 1]:
            return float(fs / peak_idx)
            
    return 0.0


def analyze_thd_n(samples: np.ndarray, fs: int) -> dict:
    """Compute THD, Even/Odd harmonic distortion ratio, and THD+N."""
    default_res = {
        "thd": 0.0,
        "even_thd": 0.0,
        "odd_thd": 0.0,
        "thd_n": 0.0,
        "fundamental_hz": 0.0
    }
    
    if len(samples) < 512:
        return default_res
        
    f0 = detect_fundamental_pitch(samples, fs)
    if f0 < 30.0 or f0 > 2000.0:
        # Cannot measure harmonics reliably if fundamental is too low or too high
        return default_res

    n = len(samples)
    # Apply Hann window to prevent spectral leakage
    window = np.hanning(n)
    windowed = samples * window
    
    # Zero-padded FFT for high frequency resolution
    fft_len = max(8192, n)
    fft_data = np.fft.rfft(windowed, n=fft_len)
    mags = np.abs(fft_data)
    
    # Find fundamental peak bin index
    idx_f0_rough = int(round(f0 * fft_len / fs))
    if idx_f0_rough < 5 or idx_f0_rough >= len(mags) - 5:
        return default_res
        
    search_start = idx_f0_rough - 4
    search_end = idx_f0_rough + 5
    idx_f0 = np.argmax(mags[search_start:search_end]) + search_start
    f0 = float(idx_f0 * fs / fft_len)
        
    # Accumulate fundamental energy (with 3-bin leakage window)
    fundamental_energy = np.sum(mags[idx_f0 - 2 : idx_f0 + 3] ** 2)
    if fundamental_energy < 1e-12:
        return default_res
        
    even_energy = 0.0
    odd_energy = 0.0
    harmonics_measured_energy = 0.0
    
    # Measure harmonics 2 through 8
    for h in range(2, 9):
        fh = h * f0
        if fh > fs / 2.0 - 50.0:
            break
            
        idx_fh = int(round(fh * fft_len / fs))
        if 0 <= idx_fh < len(mags):
            # Harmonic leakage window
            h_energy = np.sum(mags[max(0, idx_fh - 2) : min(len(mags), idx_fh + 3)] ** 2)
            harmonics_measured_energy += h_energy
            
            if h % 2 == 0:
                even_energy += h_energy
            else:
                odd_energy += h_energy
                
    # Noise/residual calculation: total energy minus fundamental and measured harmonics
    total_energy = np.sum(mags ** 2)
    noise_energy = max(0.0, total_energy - fundamental_energy - harmonics_measured_energy)
    
    thd = math.sqrt(harmonics_measured_energy) / math.sqrt(fundamental_energy)
    even_thd = math.sqrt(even_energy) / math.sqrt(fundamental_energy)
    odd_thd = math.sqrt(odd_energy) / math.sqrt(fundamental_energy)
    thd_n = math.sqrt(harmonics_measured_energy + noise_energy) / math.sqrt(fundamental_energy)
    
    return {
        "thd": round(thd, 5),
        "even_thd": round(even_thd, 5),
        "odd_thd": round(odd_thd, 5),
        "thd_n": round(thd_n, 5),
        "fundamental_hz": round(f0, 1)
    }


def _detect_resonances_single_frame(frame: np.ndarray, fs: int, fft_size: int = 4096) -> list[dict]:
    fft_data = np.fft.rfft(frame)
    freqs = np.fft.rfftfreq(fft_size, d=1.0/fs)
    mags = np.abs(fft_data)
    log_mags = 20 * np.log10(mags + 1e-12)
    
    # Smooth spectral envelope using a running window average (approx 150 Hz width).
    # Vectorised boundary-corrected moving average: identical window (shrinks at
    # the edges) and result as the per-bin np.mean loop this replaces — which
    # profiling clocked at ~64.7k np.mean() calls/analysis — via a single
    # cumulative sum. Differs only in float summation order (verified against the
    # golden-metrics snapshot, incl. the resonance list).
    window = int(150 * fft_size / fs) or 5
    n = len(log_mags)
    idx = np.arange(n)
    start = np.maximum(0, idx - window)
    end = np.minimum(n, idx + window + 1)
    csum = np.concatenate(([0.0], np.cumsum(log_mags)))
    smoothed = (csum[end] - csum[start]) / (end - start)
        
    resonances = []
    for i in range(2, len(log_mags) - 2):
        if freqs[i] < 50.0 or freqs[i] > 18000.0:
            continue
            
        val = log_mags[i]
        if val > log_mags[i-1] and val > log_mags[i+1]:
            diff = val - smoothed[i]
            if diff > 6.0:
                peak_mag = mags[i]
                target_mag = peak_mag * 0.707
                
                idx_l = i
                while idx_l > 0 and mags[idx_l] > target_mag:
                    idx_l -= 1
                f1 = freqs[idx_l]
                
                idx_r = i
                while idx_r < len(mags) - 1 and mags[idx_r] > target_mag:
                    idx_r += 1
                f2 = freqs[idx_r]
                
                bandwidth = max(1.0, f2 - f1)
                q = freqs[i] / bandwidth
                
                if q >= 8.0:
                    resonances.append({
                        "frequency_hz": round(float(freqs[i]), 1),
                        "severity_db": round(float(diff), 1),
                        "q": round(float(q), 1)
                    })
    return resonances


def detect_resonances(samples: np.ndarray, fs: int) -> list[dict]:
    """Find sharp, narrow resonance peaks (ringing frequencies) using multi-window persistence."""
    n = len(samples)
    if n < 512:
        return []
        
    fft_size = 4096
    
    # If the track is short, fall back to a single window (preserves compatibility for synthetic tests)
    if n < fft_size * 4:
        frame = samples[:fft_size] if n >= fft_size else np.pad(samples, (0, fft_size - n))
        res = _detect_resonances_single_frame(frame, fs, fft_size)
        res.sort(key=lambda r: r["severity_db"], reverse=True)
        return res[:5]
        
    # Multi-window analysis
    num_windows = 10
    starts = [int(val) for val in np.linspace(0, n - fft_size, num=num_windows)]
    
    # Analyze active windows
    active_frames = []
    frame_rms = []
    for start in starts:
        frame = samples[start:start + fft_size]
        rms = float(np.sqrt(np.mean(np.square(frame))))
        frame_rms.append(rms)
        active_frames.append((frame, rms))
        
    max_rms = max(frame_rms) if frame_rms else 0.0
    # Keep frames that are not silent (within 24 dB of peak frame RMS, and above absolute noise threshold)
    valid_frames = [
        frame for frame, rms in active_frames
        if rms >= max_rms * 0.063 and rms > 1e-4
    ]
    
    # If no frame qualifies, fallback to the first 4096 samples
    if not valid_frames:
        frame = samples[:fft_size]
        res = _detect_resonances_single_frame(frame, fs, fft_size)
        res.sort(key=lambda r: r["severity_db"], reverse=True)
        return res[:5]
        
    # Detect resonances in each valid frame
    frequency_counts: dict[float, list[dict]] = {}
    
    for frame in valid_frames:
        frame_res = _detect_resonances_single_frame(frame, fs, fft_size)
        for r in frame_res:
            freq = r["frequency_hz"]
            # Group close frequencies within 5 Hz of each other
            matched_freq = None
            for existing in frequency_counts:
                if abs(existing - freq) <= 5.0:
                    matched_freq = existing
                    break
            if matched_freq is None:
                matched_freq = freq
            frequency_counts.setdefault(matched_freq, []).append(r)
            
    # Apply persistence filter (must appear in >= 30% of valid frames)
    min_count = max(1, int(math.ceil(0.30 * len(valid_frames))))
    
    persistent_resonances = []
    for freq, occurrences in frequency_counts.items():
        if len(occurrences) >= min_count:
            # Average the severity and Q across occurrences
            avg_severity = sum(o["severity_db"] for o in occurrences) / len(occurrences)
            avg_q = sum(o["q"] for o in occurrences) / len(occurrences)
            persistent_resonances.append({
                "frequency_hz": round(float(freq), 1),
                "severity_db": round(float(avg_severity), 1),
                "q": round(float(avg_q), 1)
            })
            
    persistent_resonances.sort(key=lambda r: r["severity_db"], reverse=True)
    return persistent_resonances[:5]


def oversample_4x(samples: np.ndarray) -> np.ndarray:
    """Oversample a 1D array by 4x using bandlimited FFT zero-padding."""
    n = len(samples)
    if n == 0:
        return samples
        
    X = np.fft.fft(samples)
    X_padded = np.zeros(4 * n, dtype=complex)
    
    half = (n + 1) // 2
    X_padded[:half] = X[:half]
    
    if n % 2 == 0:
        X_padded[half] = X[half] / 2.0
        X_padded[4 * n - half] = X[half] / 2.0
        X_padded[4 * n - half + 1:] = X[half + 1:]
    else:
        X_padded[4 * n - half + 1:] = X[half:]
        
    X_padded *= 4.0
    return np.real(np.fft.ifft(X_padded))


def detect_isp(samples: np.ndarray) -> tuple[float, float]:
    """Detect regular peak and 4x oversampled Inter-Sample Peak (ISP)."""
    if len(samples) == 0:
        return 0.0, 0.0
        
    sample_peak = float(np.max(np.abs(samples)))
    oversampled = oversample_4x(samples)
    isp = float(np.max(np.abs(oversampled)))
    
    return round(sample_peak, 4), round(isp, 4)

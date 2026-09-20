from __future__ import annotations

import io
import importlib.util
import math
import wave

from audio_analysis.utils.audio_io import _pcm_sample

# Torch is an optional fallback, not the primary loudness implementation.
# Detect it without importing at module load: the Intel-compatible Torch wheel
# emits a large NumPy-2 ABI warning even when every real calculation uses the
# NumPy/SciPy path. Load it only for actual Torch tensor input or after a NumPy
# true-peak failure.
torch = None
TORCH_AVAILABLE = importlib.util.find_spec("torch") is not None


def _load_torch():
    global torch, TORCH_AVAILABLE
    if torch is not None:
        return torch
    if not TORCH_AVAILABLE:
        raise ImportError("Torch is unavailable")
    try:
        import torch as torch_module
    except ImportError:
        TORCH_AVAILABLE = False
        raise
    torch = torch_module
    return torch

try:
    import numpy as np
    import scipy.signal as sig
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

MIN_LUFS_SAMPLE_RATE = 4000
# A separate, much higher floor for the >LUFS_DECIMATION_TRIGGER_SAMPLES
# performance decimation below -- NOT the same thing as MIN_LUFS_SAMPLE_RATE
# above, which is a validity floor (below this, K-weighting isn't meaningful
# at all). ITU-R BS.1770 K-weighting's high-shelf boost centers well above
# 2kHz, so decimating toward MIN_LUFS_SAMPLE_RATE's 4000Hz (Nyquist 2kHz)
# discards exactly the frequency range the filter cares most about. Found
# 2026-07-10: calculate_lufs_numpy's old decimation (`len(left) // 300000`,
# capped at `fs // MIN_LUFS_SAMPLE_RATE`) silently collapsed ANY input over
# 600,000 samples (~12.5s at 48kHz -- i.e. nearly every real song) down to
# ~4000Hz, producing a 5 LU phantom error on a real AutoMix render (measured
# -14.0 here vs. calculate_loudness_profile_numpy's -9.01 on the identical
# signal -- that sibling function has no such internal decimation and was
# always correct). This floor keeps K-weighting accurate for any track up to
# several minutes; only pathologically long inputs decimate at all now, and
# even then only down to this floor, never toward the 4000Hz validity floor.
LUFS_DECIMATION_ACCURACY_FLOOR_HZ = 40000
LUFS_DECIMATION_TRIGGER_SAMPLES = 20_000_000


def _diagnostic(diagnostics: list[str] | None, message: str) -> None:
    if diagnostics is not None:
        diagnostics.append(message)


def get_k_filter_coefficients(fs: float) -> tuple[tuple[float, float, float, float, float], tuple[float, float, float, float, float]]:
    # Stage 1: High-shelving filter
    db_gain = 3.99984380697339
    f0 = 1681.97445095553
    Q = 0.707175236955419
    
    w0 = 2.0 * math.pi * f0 / fs
    alpha = math.sin(w0) / (2.0 * Q)
    A = 10.0 ** (db_gain / 40.0)
    
    b0_1 = A * ((A + 1.0) + (A - 1.0) * math.cos(w0) + 2.0 * math.sqrt(A) * alpha)
    b1_1 = -2.0 * A * ((A - 1.0) + (A + 1.0) * math.cos(w0))
    b2_1 = A * ((A + 1.0) + (A - 1.0) * math.cos(w0) - 2.0 * math.sqrt(A) * alpha)
    a0_1 = (A + 1.0) - (A - 1.0) * math.cos(w0) + 2.0 * math.sqrt(A) * alpha
    a1_1 = 2.0 * ((A - 1.0) - (A + 1.0) * math.cos(w0))
    a2_1 = (A + 1.0) - (A - 1.0) * math.cos(w0) - 2.0 * math.sqrt(A) * alpha
    
    b0_1 /= a0_1
    b1_1 /= a0_1
    b2_1 /= a0_1
    a1_1 /= a0_1
    a2_1 /= a0_1
    
    # Stage 2: High-pass filter
    f0_hp = 38.1354708761398
    Q_hp = 0.5
    w0_hp = 2.0 * math.pi * f0_hp / fs
    alpha_hp = math.sin(w0_hp) / (2.0 * Q_hp)
    cos_w0_hp = math.cos(w0_hp)
    
    b0_2 = (1.0 + cos_w0_hp) / 2.0
    b1_2 = -(1.0 + cos_w0_hp)
    b2_2 = (1.0 + cos_w0_hp) / 2.0
    a0_2 = 1.0 + alpha_hp
    a1_2 = -2.0 * cos_w0_hp
    a2_2 = 1.0 - alpha_hp
    
    b0_2 /= a0_2
    b1_2 /= a0_2
    b2_2 /= a0_2
    a1_2 /= a0_2
    a2_2 /= a0_2
    
    return (b0_1, b1_1, b2_1, a1_1, a2_1), (b0_2, b1_2, b2_2, a1_2, a2_2)


def apply_biquad(x: list[float], b0: float, b1: float, b2: float, a1: float, a2: float) -> list[float]:
    y = [0.0] * len(x)
    x1 = x2 = y1 = y2 = 0.0
    for i in range(len(x)):
        xi = x[i]
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2 = x1
        x1 = xi
        y2 = y1
        y1 = yi
        y[i] = yi
    return y


def calculate_lufs_fallback(left: list[float], right: list[float], fs: int) -> float:
    # Decimate signal to keep fallback calculations fast -- see
    # LUFS_DECIMATION_ACCURACY_FLOOR_HZ's docstring for why this must not
    # collapse toward MIN_LUFS_SAMPLE_RATE the way it used to.
    if len(left) > LUFS_DECIMATION_TRIGGER_SAMPLES:
        max_accuracy_safe_step = max(1, fs // LUFS_DECIMATION_ACCURACY_FLOOR_HZ)
        target_step = max(1, len(left) // LUFS_DECIMATION_TRIGGER_SAMPLES)
        step = min(target_step, max_accuracy_safe_step)
        # Apply anti-aliasing lowpass filter before downsampling
        alpha = 2.51327 / (step + 2.51327)
        left_filtered = []
        right_filtered = []
        l_prev = r_prev = 0.0
        for l_val, r_val in zip(left, right):
            l_prev = alpha * l_val + (1.0 - alpha) * l_prev
            r_prev = alpha * r_val + (1.0 - alpha) * r_prev
            left_filtered.append(l_prev)
            right_filtered.append(r_prev)
        left = left_filtered[::step]
        right = right_filtered[::step]
        fs = int(fs / step)
        
    (b0_1, b1_1, b2_1, a1_1, a2_1), (b0_2, b1_2, b2_2, a1_2, a2_2) = get_k_filter_coefficients(fs)
    y1 = apply_biquad(apply_biquad(left, b0_1, b1_1, b2_1, a1_1, a2_1), b0_2, b1_2, b2_2, a1_2, a2_2)
    y2 = apply_biquad(apply_biquad(right, b0_1, b1_1, b2_1, a1_1, a2_1), b0_2, b1_2, b2_2, a1_2, a2_2)
    
    block_size = int(0.4 * fs)
    hop_size = int(0.1 * fs)
    
    powers = []
    num_blocks = (len(y1) - block_size) // hop_size + 1
    if num_blocks <= 0:
        return -99.0
        
    for j in range(num_blocks):
        start = j * hop_size
        end = start + block_size
        p1 = sum(val * val for val in y1[start:end]) / block_size
        p2 = sum(val * val for val in y2[start:end]) / block_size
        powers.append(p1 + p2)
        
    J = []
    for p in powers:
        J.append(-0.691 + 10.0 * math.log10(max(p, 1e-12)))
        
    abs_gated_indices = [idx for idx, val in enumerate(J) if val > -70.0]
    if not abs_gated_indices:
        return -99.0
        
    sum_abs_powers = sum(powers[idx] for idx in abs_gated_indices)
    j_temp = -0.691 + 10.0 * math.log10(max(sum_abs_powers / len(abs_gated_indices), 1e-12))
    relative_threshold = j_temp - 10.0
    
    final_gated_powers = [powers[idx] for idx in abs_gated_indices if J[idx] > relative_threshold]
    if not final_gated_powers:
        return j_temp
        
    final_lufs = -0.691 + 10.0 * math.log10(max(sum(final_gated_powers) / len(final_gated_powers), 1e-12))
    return final_lufs


def calculate_lufs_torch(left: torch.Tensor, right: torch.Tensor, fs: int) -> float:
    _load_torch()
    # See LUFS_DECIMATION_ACCURACY_FLOOR_HZ's docstring above.
    if len(left) > LUFS_DECIMATION_TRIGGER_SAMPLES:
        max_accuracy_safe_step = max(1, fs // LUFS_DECIMATION_ACCURACY_FLOOR_HZ)
        target_step = max(1, len(left) // LUFS_DECIMATION_TRIGGER_SAMPLES)
        step = min(target_step, max_accuracy_safe_step)
        left = left[::step]
        right = right[::step]
        fs = int(fs / step)
        
    (b0_1, b1_1, b2_1, a1_1, a2_1), (b0_2, b1_2, b2_2, a1_2, a2_2) = get_k_filter_coefficients(fs)
    
    y1_list = apply_biquad(apply_biquad(left.tolist(), b0_1, b1_1, b2_1, a1_1, a2_1), b0_2, b1_2, b2_2, a1_2, a2_2)
    y2_list = apply_biquad(apply_biquad(right.tolist(), b0_1, b1_1, b2_1, a1_1, a2_1), b0_2, b1_2, b2_2, a1_2, a2_2)
    
    y1 = torch.tensor(y1_list, dtype=left.dtype, device=left.device)
    y2 = torch.tensor(y2_list, dtype=right.dtype, device=right.device)
    
    block_size = int(0.4 * fs)
    hop_size = int(0.1 * fs)
    
    y1_blocks = y1.unfold(0, block_size, hop_size)
    y2_blocks = y2.unfold(0, block_size, hop_size)
    
    powers = (y1_blocks ** 2).mean(dim=1) + (y2_blocks ** 2).mean(dim=1)
    powers = torch.clamp(powers, min=1e-12)
    
    J = -0.691 + 10.0 * torch.log10(powers)
    
    abs_gated = J > -70.0
    if not abs_gated.any():
        return -99.0
        
    abs_gated_powers = powers[abs_gated]
    j_temp = -0.691 + 10.0 * torch.log10(abs_gated_powers.mean())
    relative_threshold = j_temp - 10.0
    
    final_gated = abs_gated & (J > relative_threshold)
    if not final_gated.any():
        return float(j_temp.item())
        
    final_lufs = -0.691 + 10.0 * torch.log10(powers[final_gated].mean())
    return float(final_lufs.item())


def calculate_lufs_numpy(left: np.ndarray, right: np.ndarray, fs: int) -> float:
    if fs < MIN_LUFS_SAMPLE_RATE:
        return -99.0
    if len(left) > LUFS_DECIMATION_TRIGGER_SAMPLES:
        max_accuracy_safe_step = max(1, fs // LUFS_DECIMATION_ACCURACY_FLOOR_HZ)
        target_step = max(1, len(left) // LUFS_DECIMATION_TRIGGER_SAMPLES)
        step = min(target_step, max_accuracy_safe_step)
        if step > 1:
            # Apply anti-aliasing lowpass filter before downsampling.
            Wn = 0.8 / step
            b_lp, a_lp = sig.butter(2, Wn, btype='low')
            left = sig.lfilter(b_lp, a_lp, left)[::step]
            right = sig.lfilter(b_lp, a_lp, right)[::step]
            fs = int(fs / step)

    (b0_1, b1_1, b2_1, a1_1, a2_1), (b0_2, b1_2, b2_2, a1_2, a2_2) = get_k_filter_coefficients(fs)
    b1 = np.array([b0_1, b1_1, b2_1])
    a1 = np.array([1.0, a1_1, a2_1])
    b2 = np.array([b0_2, b1_2, b2_2])
    a2 = np.array([1.0, a1_2, a2_2])
    
    y1 = sig.lfilter(b2, a2, sig.lfilter(b1, a1, left))
    y2 = sig.lfilter(b2, a2, sig.lfilter(b1, a1, right))
    
    block_size = int(0.4 * fs)
    hop_size = int(0.1 * fs)
    
    n_samples = len(y1)
    if n_samples < block_size:
        return -99.0
        
    shape = ((n_samples - block_size) // hop_size + 1, block_size)
    strides = (y1.strides[0] * hop_size, y1.strides[0])
    y1_blocks = np.lib.stride_tricks.as_strided(y1, shape=shape, strides=strides)
    y2_blocks = np.lib.stride_tricks.as_strided(y2, shape=shape, strides=strides)
    
    powers = np.mean(y1_blocks**2, axis=-1) + np.mean(y2_blocks**2, axis=-1)
    powers = np.clip(powers, 1e-12, None)
    
    J = -0.691 + 10.0 * np.log10(powers)
    
    abs_gated = J > -70.0
    if not abs_gated.any():
        return -99.0
        
    j_temp = -0.691 + 10.0 * np.log10(np.mean(powers[abs_gated]))
    relative_threshold = j_temp - 10.0
    
    final_gated = abs_gated & (J > relative_threshold)
    if not final_gated.any():
        return float(j_temp)
        
    final_lufs = -0.691 + 10.0 * np.log10(np.mean(powers[final_gated]))
    return float(final_lufs)


def calculate_lufs(left: list[float] | torch.Tensor, right: list[float] | torch.Tensor, fs: int, *, diagnostics: list[str] | None = None) -> float:
    if fs < MIN_LUFS_SAMPLE_RATE:
        _diagnostic(diagnostics, f"LUFS skipped because analysis sample rate {fs} Hz is below {MIN_LUFS_SAMPLE_RATE} Hz.")
        return -99.0
    if NUMPY_AVAILABLE:
        try:
            l_np = left.numpy() if hasattr(left, "numpy") else np.asarray(left, dtype=np.float64)
            r_np = right.numpy() if hasattr(right, "numpy") else np.asarray(right, dtype=np.float64)
            return calculate_lufs_numpy(l_np, r_np, fs)
        except Exception as exc:
            _diagnostic(diagnostics, f"NumPy LUFS path failed ({exc.__class__.__name__}); trying next fallback.")
    else:
        _diagnostic(diagnostics, "NumPy LUFS path unavailable; trying next fallback.")

    torch_inputs = (
        left.__class__.__module__.startswith("torch")
        and right.__class__.__module__.startswith("torch")
    )
    if TORCH_AVAILABLE and torch_inputs:
        try:
            _load_torch()
            return calculate_lufs_torch(left, right, fs)
        except Exception as exc:
            _diagnostic(diagnostics, f"Torch LUFS path failed ({exc.__class__.__name__}); using pure Python fallback.")
    elif not TORCH_AVAILABLE:
        _diagnostic(diagnostics, "Torch LUFS path unavailable; using pure Python fallback.")
    
    l_list = left.tolist() if hasattr(left, "tolist") else list(left)
    r_list = right.tolist() if hasattr(right, "tolist") else list(right)
    _diagnostic(diagnostics, "Pure Python LUFS fallback used.")
    return calculate_lufs_fallback(l_list, r_list, fs)



def oversample_fft_torch(x: torch.Tensor, factor: int = 4) -> torch.Tensor:
    _load_torch()
    N = len(x)
    X = torch.fft.rfft(x)
    target_size = N * factor // 2 + 1
    padded = torch.zeros(target_size, dtype=X.dtype, device=X.device)
    padded[:len(X)] = X
    y = torch.fft.irfft(padded, n=N * factor) * factor
    return y


def calculate_true_peak_torch(samples: torch.Tensor, fs: int) -> float:
    _load_torch()
    peak = 1e-9
    for c in range(samples.shape[1]):
        chan = samples[:, c]
        try:
            upsampled = oversample_fft_torch(chan, factor=4)
            peak = max(peak, torch.max(torch.abs(upsampled)).item())
        except Exception:
            peak = max(peak, torch.max(torch.abs(chan)).item())
    return 20.0 * math.log10(max(peak, 1e-9))


def calculate_true_peak_fallback(left: list[float], right: list[float]) -> float:
    peak_val = 1e-9
    for chan in (left, right):
        for val in chan:
            abs_val = abs(val)
            if abs_val > peak_val:
                peak_val = abs_val
                
    if peak_val < 0.01:
        return 20.0 * math.log10(max(peak_val, 1e-9))
        
    threshold = peak_val * 0.95
    candidates = []
    for chan in (left, right):
        for i in range(8, len(chan) - 8):
            if abs(chan[i]) >= threshold:
                candidates.append((chan, i))
                if len(candidates) >= 50:
                    break
                    
    max_interpolated = peak_val
    for chan, idx in candidates[:50]:
        window = chan[idx-7 : idx+8]
        for offset in (0.25, 0.5, 0.75):
            interp = 0.0
            for n_idx, x_val in enumerate(window):
                t = offset - (n_idx - 7)
                if abs(t) < 1e-9:
                    sinc_val = 1.0
                else:
                    sinc_val = math.sin(math.pi * t) / (math.pi * t)
                interp += x_val * sinc_val
            max_interpolated = max(max_interpolated, abs(interp))
            
    return 20.0 * math.log10(max(max_interpolated, 1e-9))


def calculate_true_peak_numpy(left: np.ndarray, right: np.ndarray) -> float:
    # A windowed-peak-candidate heuristic (oversample only near-peak regions,
    # capped at the first 300 candidate indices) was tried here and reverted
    # 2026-07-30: on a real 88s track it undercounted the candidate windows
    # (723 found, only 300 examined -- missing roughly the back third of the
    # track's loud passages) AND concatenating non-adjacent slices before a
    # single resample_poly call introduced fake discontinuities the FIR
    # filter rings on, together producing a measured 2.04 dB error against
    # the accurate byte-based path on real audio (13x the 0.15 dB safety
    # margin this feeds into mix_renderer.py's gain-solve accept/reject
    # check). Full-array resample_poly is simpler and verified 0.0 dB diff
    # against the byte-based path across real tracks, including near-ceiling
    # limited candidates (tests/audio_analysis/test_true_peak_fast_path.py).
    peak = 1e-9
    for chan in (left, right):
        if len(chan) == 0:
            continue
        try:
            upsampled = sig.resample_poly(chan, 4, 1)
            peak = max(peak, float(np.max(np.abs(upsampled))))
        except Exception:
            peak = max(peak, float(np.max(np.abs(chan))))
    return 20.0 * math.log10(max(peak, 1e-9))


def calculate_true_peak_numpy_efficient(raw_bytes: bytes) -> float:
    chunk_size = 262144
    overlap = 128
    transient_width = 32
    peak = 1e-9
    
    with wave.open(io.BytesIO(raw_bytes), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        if frame_count <= 0 or channels <= 0:
            return -99.0
            
        frame_index = 0
        while frame_index < frame_count:
            read_start = max(0, frame_index - overlap)
            frames_to_read = min(chunk_size, frame_count - read_start)
            if frames_to_read <= 0:
                break
                
            wav.setpos(read_start)
            raw_chunk = wav.readframes(frames_to_read)
            if not raw_chunk:
                break
                
            if sample_width == 1:
                chunk_arr = (np.frombuffer(raw_chunk, dtype=np.uint8).astype(np.float64) - 128.0) / 127.0
            elif sample_width == 2:
                chunk_arr = np.frombuffer(raw_chunk, dtype=np.int16).astype(np.float64) / 32767.0
            elif sample_width == 4:
                chunk_arr = np.frombuffer(raw_chunk, dtype=np.int32).astype(np.float64) / 2147483647.0
            elif sample_width == 3:
                n_samples = len(raw_chunk) // 3
                temp = np.frombuffer(raw_chunk, dtype=np.uint8).reshape(-1, 3)
                padded = np.zeros((n_samples, 4), dtype=np.uint8)
                padded[:, :3] = temp
                sign_mask = temp[:, 2] & 0x80
                padded[:, 3] = np.where(sign_mask, 0xFF, 0x00)
                chunk_arr = padded.view(np.int32).flatten().astype(np.float64) / 8388607.0
            else:
                raise ValueError("Unsupported WAV sample width.")
                
            chunk_np = chunk_arr.reshape(-1, channels)
            
            for ch in range(channels):
                chan_data = chunk_np[:, ch]
                try:
                    upsampled = sig.resample_poly(chan_data, 4, 1)
                    start_idx = 0 if read_start == 0 else transient_width * 4
                    end_idx = len(upsampled) if (read_start + frames_to_read) == frame_count else len(upsampled) - (transient_width * 4)
                    if end_idx > start_idx:
                        peak = max(peak, float(np.max(np.abs(upsampled[start_idx:end_idx]))))
                except Exception:
                    peak = max(peak, float(np.max(np.abs(chan_data))))
                    
            if (read_start + frames_to_read) == frame_count:
                frame_index = frame_count
            else:
                frame_index = (read_start + frames_to_read) - overlap
                
    return 20.0 * math.log10(max(peak, 1e-9))


def calculate_true_peak_fallback_efficient(raw_bytes: bytes) -> float:
    chunk_size = 65536
    
    with wave.open(io.BytesIO(raw_bytes), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        frame_count = wav.getnframes()
        if frame_count <= 0 or channels <= 0:
            return -99.0
            
        max_int = float((1 << (sample_width * 8 - 1)) - 1) if sample_width > 1 else 127.0
        frame_size = channels * sample_width
        
        # Pass 1: Find absolute peak of the file
        peak_val = 1e-9
        frame_index = 0
        while frame_index < frame_count:
            frames_to_read = min(chunk_size, frame_count - frame_index)
            raw_chunk = wav.readframes(frames_to_read)
            if not raw_chunk:
                break
            for i in range(frames_to_read):
                offset = i * frame_size
                for ch in range(channels):
                    start = offset + (ch * sample_width)
                    val_bytes = raw_chunk[start : start + sample_width]
                    if len(val_bytes) < sample_width:
                        continue
                    val = abs(_pcm_sample(val_bytes, sample_width) / max_int)
                    if val > peak_val:
                        peak_val = val
            frame_index += frames_to_read
            
        if peak_val < 0.01:
            return 20.0 * math.log10(max(peak_val, 1e-9))
            
        # Pass 2: Find candidates
        threshold = peak_val * 0.95
        candidates = []
        
        wav.rewind()
        frame_index = 0
        while frame_index < frame_count:
            frames_to_read = min(chunk_size, frame_count - frame_index)
            raw_chunk = wav.readframes(frames_to_read)
            if not raw_chunk:
                break
            for i in range(frames_to_read):
                offset = i * frame_size
                for ch in range(channels):
                    start = offset + (ch * sample_width)
                    val_bytes = raw_chunk[start : start + sample_width]
                    if len(val_bytes) < sample_width:
                        continue
                    val = abs(_pcm_sample(val_bytes, sample_width) / max_int)
                    if val >= threshold:
                        candidates.append((ch, frame_index + i))
                        if len(candidates) >= 50:
                            break
                if len(candidates) >= 50:
                    break
            frame_index += frames_to_read
            if len(candidates) >= 50:
                break
                
        # Sinc-interpolate candidates
        max_interpolated = peak_val
        for ch, idx in candidates:
            start_window = max(0, idx - 7)
            end_window = min(frame_count, idx + 8)
            wav.setpos(start_window)
            raw_window = wav.readframes(end_window - start_window)
            
            window_vals = []
            for i in range(end_window - start_window):
                offset = i * frame_size + (ch * sample_width)
                val_bytes = raw_window[offset : offset + sample_width]
                if len(val_bytes) < sample_width:
                    window_vals.append(0.0)
                else:
                    window_vals.append(_pcm_sample(val_bytes, sample_width) / max_int)
                    
            if start_window == 0:
                pad_len = 7 - idx
                window_vals = [0.0] * pad_len + window_vals
            if len(window_vals) < 15:
                window_vals = window_vals + [0.0] * (15 - len(window_vals))
                
            for offset in (0.25, 0.5, 0.75):
                interp = 0.0
                for n_idx, x_val in enumerate(window_vals):
                    t = offset - (n_idx - 7)
                    if abs(t) < 1e-9:
                        sinc_val = 1.0
                    else:
                        sinc_val = math.sin(math.pi * t) / (math.pi * t)
                    interp += x_val * sinc_val
                max_interpolated = max(max_interpolated, abs(interp))
                
        return 20.0 * math.log10(max(max_interpolated, 1e-9))


def calculate_true_peak(
    left: list[float] | torch.Tensor | np.ndarray,
    right: list[float] | torch.Tensor | np.ndarray,
    fs: int,
    raw_bytes: bytes | None = None,
    *,
    diagnostics: list[str] | None = None,
) -> float:
    if NUMPY_AVAILABLE and (raw_bytes is None or len(raw_bytes) == 0):
        try:
            l_arr = np.asarray(left, dtype=np.float64)
            r_arr = np.asarray(right, dtype=np.float64)
            return calculate_true_peak_numpy(l_arr, r_arr)
        except Exception as exc:
            _diagnostic(diagnostics, f"NumPy direct true-peak path failed ({exc.__class__.__name__}); trying fallback.")

    if raw_bytes is not None and len(raw_bytes) > 0:
        if NUMPY_AVAILABLE:
            try:
                return calculate_true_peak_numpy_efficient(raw_bytes)
            except Exception as exc:
                _diagnostic(diagnostics, f"NumPy true-peak path failed ({exc.__class__.__name__}); trying next fallback.")
        else:
            _diagnostic(diagnostics, "NumPy true-peak path unavailable; trying next fallback.")

        if TORCH_AVAILABLE:
            try:
                _load_torch()
                with wave.open(io.BytesIO(raw_bytes), "rb") as wav:
                    channels = wav.getnchannels()
                    sample_width = wav.getsampwidth()
                    frame_count = wav.getnframes()
                    raw = wav.readframes(frame_count)
                max_int = float((1 << (sample_width * 8 - 1)) - 1) if sample_width > 1 else 127.0
                if sample_width == 2:
                    tensor = torch.frombuffer(bytearray(raw), dtype=torch.int16).clone()
                    tensor = tensor.view(-1, channels).float() / max_int
                    return calculate_true_peak_torch(tensor, fs)
                elif sample_width == 4:
                    tensor = torch.frombuffer(bytearray(raw), dtype=torch.int32).clone()
                    tensor = tensor.view(-1, channels).float() / max_int
                    return calculate_true_peak_torch(tensor, fs)
            except Exception as exc:
                _diagnostic(diagnostics, f"Torch true-peak path failed ({exc.__class__.__name__}); trying efficient fallback.")
        else:
            _diagnostic(diagnostics, "Torch true-peak path unavailable; trying efficient fallback.")
            
        try:
            return calculate_true_peak_fallback_efficient(raw_bytes)
        except Exception as exc:
            _diagnostic(diagnostics, f"Efficient true-peak fallback failed ({exc.__class__.__name__}); using sample-window fallback.")
        
    l_list = left.tolist() if hasattr(left, "tolist") else list(left)
    r_list = right.tolist() if hasattr(right, "tolist") else list(right)
    _diagnostic(diagnostics, "Sample-window true-peak fallback used.")
    return calculate_true_peak_fallback(l_list, r_list)


# ---------------------------------------------------------------------------
# Phase A1 — BS.1770-4 / EBU R128 Loudness Profile
# ---------------------------------------------------------------------------

def _percentile(values: list[float], pct: float) -> float:
    """Compute a percentile from a sorted list (linear interpolation)."""
    if not values:
        return 0.0
    n = len(values)
    k = (n - 1) * pct / 100.0
    f = int(k)
    c = f + 1
    if c >= n:
        return values[-1]
    return values[f] + (k - f) * (values[c] - values[f])


def _k_filter_samples(left, right, fs: int):
    """Apply K-weighting to left/right channels. Returns (y_left, y_right).

    When numpy/scipy are available this uses ``scipy.signal.lfilter`` — the
    same vectorised path :func:`calculate_lufs_numpy` uses — instead of the
    per-sample Python IIR loop in :func:`apply_biquad`, which profiling showed
    to be ~half of ``analyze_wav``'s runtime (this helper drives
    ``loudness_range_by_section`` and both loudness-profile fallbacks). Under
    numpy the return values are ``np.ndarray``; under the pure-Python fallback
    they are ``list``. Every consumer here only iterates or slices them, which
    both support, and the results agree to floating-point summation order
    (verified against the golden-metrics snapshot). Falls back to the exact
    original list path when numpy is absent."""
    (b0_1, b1_1, b2_1, a1_1, a2_1), (b0_2, b1_2, b2_2, a1_2, a2_2) = get_k_filter_coefficients(fs)
    if NUMPY_AVAILABLE:
        l_arr = np.asarray(left, dtype=np.float64)
        r_arr = np.asarray(right, dtype=np.float64)
        b_stage1 = np.array([b0_1, b1_1, b2_1])
        a_stage1 = np.array([1.0, a1_1, a2_1])
        b_stage2 = np.array([b0_2, b1_2, b2_2])
        a_stage2 = np.array([1.0, a1_2, a2_2])
        y1 = sig.lfilter(b_stage2, a_stage2, sig.lfilter(b_stage1, a_stage1, l_arr))
        y2 = sig.lfilter(b_stage2, a_stage2, sig.lfilter(b_stage1, a_stage1, r_arr))
        return y1, y2
    l_list = left.tolist() if hasattr(left, "tolist") else list(left)
    r_list = right.tolist() if hasattr(right, "tolist") else list(right)
    y1 = apply_biquad(apply_biquad(l_list, b0_1, b1_1, b2_1, a1_1, a2_1), b0_2, b1_2, b2_2, a1_2, a2_2)
    y2 = apply_biquad(apply_biquad(r_list, b0_1, b1_1, b2_1, a1_1, a2_1), b0_2, b1_2, b2_2, a1_2, a2_2)
    return y1, y2


def _block_powers_400ms(y1, y2, fs: int) -> list[float]:
    """Compute 400ms block mean powers with 75% overlap (100ms hop) per BS.1770-4.

    Vectorised (stride-trick sliding window, same technique as
    :func:`calculate_lufs_numpy`) when numpy is available — this replaces a
    per-sample ``sum(v * v for v in ...)`` generator that profiling clocked at
    6.17M calls per analysis. Pure-Python fallback preserved bit-for-bit."""
    block_size = int(0.4 * fs)
    hop_size = int(0.1 * fs)
    if block_size <= 0 or hop_size <= 0:
        return []
    n_samples = min(len(y1), len(y2))
    n_blocks = (n_samples - block_size) // hop_size + 1
    if n_blocks <= 0:
        return []
    if NUMPY_AVAILABLE:
        a1 = np.ascontiguousarray(y1, dtype=np.float64)
        a2 = np.ascontiguousarray(y2, dtype=np.float64)
        shape = (n_blocks, block_size)
        strides = (a1.strides[0] * hop_size, a1.strides[0])
        b1 = np.lib.stride_tricks.as_strided(a1, shape=shape, strides=strides)
        b2 = np.lib.stride_tricks.as_strided(a2, shape=shape, strides=strides)
        powers = np.mean(b1 ** 2, axis=-1) + np.mean(b2 ** 2, axis=-1)
        return powers.tolist()
    powers = []
    for j in range(n_blocks):
        start = j * hop_size
        end = start + block_size
        p1 = sum(v * v for v in y1[start:end]) / block_size
        p2 = sum(v * v for v in y2[start:end]) / block_size
        powers.append(p1 + p2)
    return powers


def _powers_to_lufs(powers: list[float]) -> list[float]:
    """Convert linear power values to LUFS."""
    return [-0.691 + 10.0 * math.log10(max(p, 1e-12)) for p in powers]


def _gated_integrated(powers: list[float], J: list[float]) -> float:
    """Two-stage gated integrated loudness per BS.1770-4."""
    # Absolute gate at -70 LUFS
    abs_gated = [i for i, v in enumerate(J) if v > -70.0]
    if not abs_gated:
        return -99.0
    ungated_mean = sum(powers[i] for i in abs_gated) / len(abs_gated)
    j_temp = -0.691 + 10.0 * math.log10(max(ungated_mean, 1e-12))
    # Relative gate at -10 LU below ungated mean
    rel_threshold = j_temp - 10.0
    final = [powers[i] for i in abs_gated if J[i] > rel_threshold]
    if not final:
        return j_temp
    return -0.691 + 10.0 * math.log10(max(sum(final) / len(final), 1e-12))


def _short_term_values(momentary_powers: list[float], fs: int) -> list[float]:
    """Compute 3-second short-term loudness from 400ms block powers.

    Per EBU Tech 3342, short-term blocks are 3 seconds long, overlapping
    by 2 seconds (i.e. the hop equals 1 second).
    Each 400ms block has a hop of 100ms, so:
      - blocks_per_3s = int(3.0 / 0.1) = 30 blocks
      - blocks_per_1s_hop = int(1.0 / 0.1) = 10 blocks
    """
    blocks_per_3s = 30
    blocks_per_1s_hop = 10
    if len(momentary_powers) < blocks_per_3s:
        return []
    n_st = (len(momentary_powers) - blocks_per_3s) // blocks_per_1s_hop + 1
    st_lufs = []
    for i in range(n_st):
        start = i * blocks_per_1s_hop
        window = momentary_powers[start:start + blocks_per_3s]
        mean_p = sum(window) / len(window)
        st_lufs.append(-0.691 + 10.0 * math.log10(max(mean_p, 1e-12)))
    return st_lufs


def _compute_lra(short_term_lufs: list[float]) -> float:
    """Compute LRA (Loudness Range) per EBU R128 s1 / EBU Tech 3342.

    Uses -20 LU relative gate (NOT -10 LU like integrated loudness).
    LRA = 95th percentile - 10th percentile of gated short-term values.
    """
    if len(short_term_lufs) < 2:
        return 0.0
    # Absolute gate at -70 LUFS
    abs_gated = [v for v in short_term_lufs if v > -70.0]
    if len(abs_gated) < 2:
        return 0.0
    # Ungated mean of absolute-gated blocks
    # Convert back to linear, average, then to LUFS for the threshold
    linear = [10.0 ** ((v + 0.691) / 10.0) for v in abs_gated]
    ungated_mean_lufs = -0.691 + 10.0 * math.log10(max(sum(linear) / len(linear), 1e-12))
    # Relative gate at -20 LU (note: LRA uses -20, not -10)
    rel_threshold = ungated_mean_lufs - 20.0
    rel_gated = sorted(v for v in abs_gated if v > rel_threshold)
    if len(rel_gated) < 2:
        return 0.0
    return _percentile(rel_gated, 95.0) - _percentile(rel_gated, 10.0)


def calculate_loudness_profile_fallback(
    left, right, fs: int
) -> dict:
    """Pure-Python BS.1770-4 + EBU R128 loudness profile."""
    y1, y2 = _k_filter_samples(left, right, fs)
    powers = _block_powers_400ms(y1, y2, fs)
    if not powers:
        return {
            "integrated_lufs": -99.0,
            "momentary_max_lufs": -99.0,
            "short_term_max_lufs": -99.0,
            "loudness_range_lu": 0.0,
        }
    J = _powers_to_lufs(powers)

    integrated = _gated_integrated(powers, J)
    if integrated == -99.0:
        return {
            "integrated_lufs": -99.0,
            "momentary_max_lufs": -99.0,
            "short_term_max_lufs": -99.0,
            "loudness_range_lu": 0.0,
        }
    momentary_max = max(J)

    st_lufs = _short_term_values(powers, fs)
    short_term_max = max(st_lufs) if st_lufs else momentary_max
    lra = _compute_lra(st_lufs)

    return {
        "integrated_lufs": round(integrated, 2) if integrated != -99.0 else -99.0,
        "momentary_max_lufs": round(momentary_max, 2),
        "short_term_max_lufs": round(short_term_max, 2),
        "loudness_range_lu": round(lra, 2),
    }


def calculate_loudness_profile_numpy(
    left: np.ndarray, right: np.ndarray, fs: int
) -> dict:
    """NumPy-accelerated BS.1770-4 + EBU R128 loudness profile."""
    if fs < MIN_LUFS_SAMPLE_RATE:
        return {
            "integrated_lufs": -99.0,
            "momentary_max_lufs": -99.0,
            "short_term_max_lufs": -99.0,
            "loudness_range_lu": 0.0,
        }

    # K-weight
    (b0_1, b1_1, b2_1, a1_1, a2_1), (b0_2, b1_2, b2_2, a1_2, a2_2) = get_k_filter_coefficients(fs)
    b1_arr = np.array([b0_1, b1_1, b2_1])
    a1_arr = np.array([1.0, a1_1, a2_1])
    b2_arr = np.array([b0_2, b1_2, b2_2])
    a2_arr = np.array([1.0, a1_2, a2_2])

    y1 = sig.lfilter(b2_arr, a2_arr, sig.lfilter(b1_arr, a1_arr, left))
    y2 = sig.lfilter(b2_arr, a2_arr, sig.lfilter(b1_arr, a1_arr, right))

    # 400ms blocks (momentary)
    block_size = int(0.4 * fs)
    hop_size = int(0.1 * fs)
    n_samples = len(y1)
    if n_samples < block_size or block_size <= 0 or hop_size <= 0:
        return {
            "integrated_lufs": -99.0,
            "momentary_max_lufs": -99.0,
            "short_term_max_lufs": -99.0,
            "loudness_range_lu": 0.0,
        }

    shape = ((n_samples - block_size) // hop_size + 1, block_size)
    strides = (y1.strides[0] * hop_size, y1.strides[0])
    y1_blocks = np.lib.stride_tricks.as_strided(y1, shape=shape, strides=strides)
    y2_blocks = np.lib.stride_tricks.as_strided(y2, shape=shape, strides=strides)

    powers = np.mean(y1_blocks ** 2, axis=-1) + np.mean(y2_blocks ** 2, axis=-1)
    powers = np.clip(powers, 1e-12, None)
    J = -0.691 + 10.0 * np.log10(powers)

    # Integrated LUFS (two-stage gating)
    abs_mask = J > -70.0
    if not abs_mask.any():
        return {
            "integrated_lufs": -99.0,
            "momentary_max_lufs": -99.0,
            "short_term_max_lufs": -99.0,
            "loudness_range_lu": 0.0,
        }
    j_temp = -0.691 + 10.0 * np.log10(np.mean(powers[abs_mask]))
    rel_threshold = j_temp - 10.0
    final_mask = abs_mask & (J > rel_threshold)
    if final_mask.any():
        integrated = float(-0.691 + 10.0 * np.log10(np.mean(powers[final_mask])))
    else:
        integrated = float(j_temp)

    # Momentary max
    momentary_max = float(np.max(J))

    # Short-term (3s blocks, 1s hop)
    blocks_per_3s = 30
    blocks_per_1s_hop = 10
    n_momentary = len(powers)
    if n_momentary >= blocks_per_3s:
        n_st = (n_momentary - blocks_per_3s) // blocks_per_1s_hop + 1
        st_powers = np.array([
            np.mean(powers[i * blocks_per_1s_hop: i * blocks_per_1s_hop + blocks_per_3s])
            for i in range(n_st)
        ])
        st_powers = np.clip(st_powers, 1e-12, None)
        st_lufs = -0.691 + 10.0 * np.log10(st_powers)
        short_term_max = float(np.max(st_lufs))

        # LRA
        st_lufs_list = st_lufs.tolist()
        abs_gated_st = [v for v in st_lufs_list if v > -70.0]
        if len(abs_gated_st) >= 2:
            lin_st = np.array([10.0 ** ((v + 0.691) / 10.0) for v in abs_gated_st])
            ungated_mean_st = -0.691 + 10.0 * np.log10(np.mean(lin_st))
            rel_threshold_st = ungated_mean_st - 20.0
            rel_gated_st = sorted(v for v in abs_gated_st if v > rel_threshold_st)
            if len(rel_gated_st) >= 2:
                lra = float(np.percentile(rel_gated_st, 95) - np.percentile(rel_gated_st, 10))
            else:
                lra = 0.0
        else:
            lra = 0.0
    else:
        short_term_max = momentary_max
        lra = 0.0

    return {
        "integrated_lufs": round(integrated, 2) if integrated != -99.0 else -99.0,
        "momentary_max_lufs": round(momentary_max, 2),
        "short_term_max_lufs": round(short_term_max, 2),
        "loudness_range_lu": round(lra, 2),
    }


# ---------------------------------------------------------------------------
# Stage 10 — LRA (Loudness Range) per structural section
# ---------------------------------------------------------------------------


def loudness_range_for_span(left, right, fs: int) -> float | None:
    """Compute EBU R128 LRA for a single contiguous span of audio.

    Returns ``None`` when the span is too short to contain the minimum
    two 3-second short-term blocks required by :func:`_compute_lra` (i.e.
    less than ~4 seconds of audio), so callers can distinguish "no LRA
    could be measured" from "LRA is 0 LU".
    """
    l_list = left.tolist() if hasattr(left, "tolist") else list(left)
    r_list = right.tolist() if hasattr(right, "tolist") else list(right)
    if not l_list or not r_list or fs < MIN_LUFS_SAMPLE_RATE:
        return None
    y1, y2 = _k_filter_samples(l_list, r_list, fs)
    powers = _block_powers_400ms(y1, y2, fs)
    if not powers:
        return None
    st_lufs = _short_term_values(powers, fs)
    if len(st_lufs) < 2:
        return None
    return round(_compute_lra(st_lufs), 2)


def _lra_from_momentary(momentary_lufs: list[float]) -> float:
    """LRA-style spread computed directly from 400ms momentary blocks.

    The standard EBU R128 LRA algorithm (:func:`_compute_lra`) is defined on
    3-second short-term blocks, which needs several seconds of audio to
    produce more than one or two data points. Structural sections (verse,
    chorus, etc.) are frequently shorter than that, so for section-scoped
    LRA we fall back to the same two-stage-gate / 95th-10th percentile
    methodology applied directly to the finer-grained 400ms momentary
    values. This trades a little standards-compliance for the ability to
    say anything at all about range *within* an 8-15 second section; it
    uses the same gating logic (-70 LUFS absolute, -20 LU relative) so
    results are directly comparable in spirit to whole-track LRA, and we
    label the section metric with the method used so callers/UI can be
    honest about the difference.
    """
    if len(momentary_lufs) < 2:
        return 0.0
    abs_gated = [v for v in momentary_lufs if v > -70.0]
    if len(abs_gated) < 2:
        return 0.0
    linear = [10.0 ** ((v + 0.691) / 10.0) for v in abs_gated]
    ungated_mean_lufs = -0.691 + 10.0 * math.log10(max(sum(linear) / len(linear), 1e-12))
    rel_threshold = ungated_mean_lufs - 20.0
    rel_gated = sorted(v for v in abs_gated if v > rel_threshold)
    if len(rel_gated) < 2:
        return 0.0
    return _percentile(rel_gated, 95.0) - _percentile(rel_gated, 10.0)


def loudness_range_by_section(
    left: list[float],
    right: list[float],
    fs: int,
    sections: list[dict],
    *,
    diagnostics: list[str] | None = None,
) -> list[dict]:
    """Compute per-structural-section loudness range (LRA).

    ``sections`` is a list of dicts each with ``start_seconds``/``end_seconds``
    (the format produced by :func:`analysis_features.section_analysis`).
    For each section we K-weight the section's audio, compute 400ms block
    powers (BS.1770-4), and derive an LRA-style spread with
    :func:`_lra_from_momentary`. When a section has >=30s of audio we use
    the full EBU R128 3-second short-term method instead (more accurate,
    matches whole-track LRA methodology exactly) via :func:`_short_term_values`
    / :func:`_compute_lra`.

    Returns a list of dicts, one per input section, each augmented with:
        ``loudness_range_lu``   — the section's LRA in LU
        ``lra_method``          — "short_term_3s" or "momentary_400ms"
        ``integrated_lufs``     — section's own gated integrated loudness
    """
    # len()==0 guards (not `not left`/`not right`) so a numpy-array caller
    # doesn't hit the ambiguous-truth-value ValueError -- same convention
    # dsp_metrics.py's spectrum_magnitudes() already documents/uses.
    if (
        fs < MIN_LUFS_SAMPLE_RATE
        or left is None or len(left) == 0
        or right is None or len(right) == 0
        or not sections
    ):
        _diagnostic(diagnostics, "Section LRA skipped: insufficient audio or sample rate.")
        return []

    n = min(len(left), len(right))
    results = []
    for section in sections:
        start_s = float(section.get("start_seconds", 0.0))
        end_s = float(section.get("end_seconds", 0.0))
        start_sample = max(0, int(start_s * fs))
        end_sample = min(n, int(end_s * fs))
        if end_sample <= start_sample:
            results.append({**section, "loudness_range_lu": 0.0, "lra_method": "n/a", "integrated_lufs": -99.0})
            continue
        seg_left = left[start_sample:end_sample]
        seg_right = right[start_sample:end_sample]

        y1, y2 = _k_filter_samples(seg_left, seg_right, fs)
        powers = _block_powers_400ms(y1, y2, fs)
        if not powers:
            results.append({**section, "loudness_range_lu": 0.0, "lra_method": "n/a", "integrated_lufs": -99.0})
            continue
        J = _powers_to_lufs(powers)
        integrated = _gated_integrated(powers, J)

        duration = end_s - start_s
        if duration >= 30.0:
            st_lufs = _short_term_values(powers, fs)
            lra = _compute_lra(st_lufs)
            method = "short_term_3s"
        else:
            lra = _lra_from_momentary(J)
            method = "momentary_400ms"

        results.append({
            **section,
            "loudness_range_lu": round(lra, 2),
            "lra_method": method,
            "integrated_lufs": round(integrated, 2) if integrated != -99.0 else -99.0,
        })
    return results


def calculate_loudness_profile(
    left, right, fs: int, *, diagnostics: list[str] | None = None
) -> dict:
    """Return full BS.1770-4 + EBU R128 loudness profile.

    Returns a dict with:
        integrated_lufs      – Gated integrated loudness (BS.1770-4)
        momentary_max_lufs   – Peak 400ms block loudness
        short_term_max_lufs  – Peak 3s block loudness
        loudness_range_lu    – LRA per EBU R128 s1
    """
    empty = {
        "integrated_lufs": -99.0,
        "momentary_max_lufs": -99.0,
        "short_term_max_lufs": -99.0,
        "loudness_range_lu": 0.0,
    }
    if fs < MIN_LUFS_SAMPLE_RATE:
        _diagnostic(diagnostics, f"Loudness profile skipped: sample rate {fs} Hz below {MIN_LUFS_SAMPLE_RATE} Hz.")
        return empty

    if NUMPY_AVAILABLE:
        try:
            l_np = left.numpy() if hasattr(left, "numpy") else np.asarray(left, dtype=np.float64)
            r_np = right.numpy() if hasattr(right, "numpy") else np.asarray(right, dtype=np.float64)
            return calculate_loudness_profile_numpy(l_np, r_np, fs)
        except Exception as exc:
            _diagnostic(diagnostics, f"NumPy loudness profile failed ({exc.__class__.__name__}); using fallback.")

    _diagnostic(diagnostics, "Using pure-Python loudness profile fallback.")
    return calculate_loudness_profile_fallback(left, right, fs)

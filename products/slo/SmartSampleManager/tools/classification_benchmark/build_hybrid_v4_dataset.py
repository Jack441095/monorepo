#!/usr/bin/env python3
"""
Build the 520-D hybrid dataset for V4 classifier training.

Concatenates the existing 512-D PANNs embeddings with 8 DSP features
extracted to match the C++ production path in SampleManagerEngine.cpp
(analyzeAudioProperties + the 8-dim normalisation block in
runInferenceBatch).

CANONICAL FEATURE SPEC (must match C++ exactly):
  dim 0: norm_duration   = min(duration_seconds / 10.0, 1.0)
  dim 1: norm_centroid   = min(spectral_centroid_hz / 16000.0, 1.0)
  dim 2: norm_flatness   = 1.0 - min(crest_factor / 20.0, 1.0)
  dim 3: zcr             = min(max(zero_crossing_rate, 0.0), 1.0)
  dim 4: norm_rms        = min(rms * 5.0, 1.0)
  dim 5: norm_decay      = min(decay_time_seconds / 3.0, 1.0)
                           (if decay <= 0.001 -> fallback to norm_duration)
  dim 6: low_rolloff     = 1.0 - min(spectral_rolloff_hz / 20000.0, 1.0)
  dim 7: high_rolloff    = min(spectral_rolloff_hz / 20000.0, 1.0)

All raw features are computed over the ENTIRE mono-downmixed file at its
NATIVE sample rate, matching analyzeAudioProperties() in C++.

This module is a vectorised reimplementation of the C++ DSP. The
per-sample/per-bin loops in the C++ source are expressed here as numpy /
scipy operations that are mathematically identical:
  - envelope follower  -> scipy.signal.lfilter (first-order IIR)
  - STFT framing       -> sliding_window_view + batched rfft
  - rolloff bin search -> cumsum + first-True argmax
See validate_dsp_parity.py for the equivalence check against the literal
loop transcription.
"""

import os
import sys
import time
import math
import argparse
import multiprocessing as mp
import numpy as np
import soundfile as sf
from numpy.lib.stride_tricks import sliding_window_view
from scipy.signal import lfilter

SOURCE_ROOT = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
EMBEDDINGS_NPZ = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/slo_all_packs_embeddings.npz"
OUT_HYBRID_NPZ = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/tools/classification_benchmark/slo_all_packs_hybrid_v4.npz"

# --- DSP constants matching C++ (SampleManagerEngine.cpp) ---
FFT_ORDER = 11
FFT_SIZE = 1 << FFT_ORDER          # 2048
HOP_SIZE = FFT_SIZE // 4           # 512
NUM_MAG_BINS = FFT_SIZE // 2 + 1   # 1025
ROLLOFF_THRESHOLD = 0.85
ENVELOPE_TC_SECONDS = 0.015
DECAY_THRESHOLD_RATIO = 0.1
MAG_SUM_EPSILON = 1.0e-9

# Cap frames processed per rfft batch so a very long file cannot spike RAM.
FRAME_BATCH = 2048


def build_filename_map(source_dir):
    """Index audio filenames to absolute paths."""
    print("Indexing audio filenames to absolute paths...", flush=True)
    fn_map = {}
    for root, _, files in os.walk(source_dir):
        for f in files:
            if f.lower().endswith(('.wav', '.aif', '.aiff', '.flac')):
                fn_map[f] = os.path.join(root, f)
    print(f"Indexed {len(fn_map)} unique audio files.", flush=True)
    return fn_map


def compute_envelope_decay_seconds(mono, sample_rate):
    """
    Vectorised equivalent of C++ computeEnvelopeDecayTimeSeconds.

    C++ recurrence:  env[i] = env[i-1] + alpha * (|x[i]| - env[i-1])
    which is         env[i] = alpha*|x[i]| + (1 - alpha)*env[i-1]
    i.e. a first-order IIR with b=[alpha], a=[1, -(1-alpha)], zero init.
    """
    n = len(mono)
    if n == 0 or sample_rate <= 0:
        return 0.0

    alpha = 1.0 - math.exp(-1.0 / (sample_rate * ENVELOPE_TC_SECONDS))
    envelope = lfilter([alpha], [1.0, -(1.0 - alpha)], np.abs(mono.astype(np.float64)))

    # C++ uses strict '>' when scanning for the peak, so it keeps the FIRST
    # maximum. np.argmax has the same first-occurrence semantics.
    peak_idx = int(np.argmax(envelope))
    peak_val = float(envelope[peak_idx])
    if peak_val <= 0.0:
        return 0.0

    threshold = peak_val * DECAY_THRESHOLD_RATIO
    tail_below = envelope[peak_idx:] < threshold
    if tail_below.any():
        decay_idx = peak_idx + int(np.argmax(tail_below))
    else:
        decay_idx = n - 1  # C++ default when the envelope never drops below

    return float(decay_idx - peak_idx) / float(sample_rate)


def compute_spectral_centroid_rolloff(mono, sample_rate):
    """
    Vectorised equivalent of the C++ 2048-point Hann / 512-hop STFT average.
    Returns (centroid_hz, rolloff_hz); (0.0, 0.0) when the file is shorter
    than one FFT frame, matching the C++ early-out.
    """
    n = len(mono)
    if n < FFT_SIZE:
        return 0.0, 0.0

    # hann[i] = 0.5 * (1 - cos(2*pi*i / (fftSize - 1)))  -- matches C++
    hann = 0.5 * (1.0 - np.cos(2.0 * np.pi * np.arange(FFT_SIZE) / (FFT_SIZE - 1)))
    freqs = np.arange(NUM_MAG_BINS) * (float(sample_rate) / FFT_SIZE)

    # Frame offsets 0, 512, 1024, ... while offset + 2048 <= n -- the
    # [::HOP_SIZE] stride over complete windows reproduces the C++ loop bound.
    windows = sliding_window_view(mono, FFT_SIZE)[::HOP_SIZE]

    centroid_sum = 0.0
    rolloff_sum = 0.0
    frame_count = 0

    for start in range(0, len(windows), FRAME_BATCH):
        batch = windows[start:start + FRAME_BATCH].astype(np.float64) * hann
        mag = np.abs(np.fft.rfft(batch, axis=1))

        mag_sum = mag.sum(axis=1)
        valid = mag_sum > MAG_SUM_EPSILON
        if not valid.any():
            continue

        mag_v = mag[valid]
        mag_sum_v = mag_sum[valid]

        # Centroid: sum(freq * mag) / sum(mag), per frame
        centroid_sum += float(((mag_v * freqs).sum(axis=1) / mag_sum_v).sum())

        # Rolloff: first bin where the running magnitude sum reaches 85%.
        # cumsum + first-True argmax reproduces the C++ break-on-threshold
        # scan; the final cumsum entry always equals mag_sum, so a match is
        # guaranteed and argmax never falls through to index 0 spuriously.
        cumulative = np.cumsum(mag_v, axis=1)
        targets = ROLLOFF_THRESHOLD * mag_sum_v
        rolloff_bins = np.argmax(cumulative >= targets[:, None], axis=1)
        rolloff_sum += float((rolloff_bins * (float(sample_rate) / FFT_SIZE)).sum())

        frame_count += int(valid.sum())

    if frame_count == 0:
        return 0.0, 0.0

    return centroid_sum / frame_count, rolloff_sum / frame_count


def extract_dsp_features(filepath):
    """
    Extract the 8 DSP features matching the C++ production path.
    Returns np.float32 array of shape (8,). Returns zeros on any read
    failure, matching the C++ safe-default behaviour for malformed files.
    """
    try:
        data, sr = sf.read(filepath, dtype='float32', always_2d=False)
        if data.ndim > 1:
            # Mono downmix: average all channels (matches C++ policy)
            data = data.mean(axis=1)

        n = len(data)
        if n == 0:
            return np.zeros(8, dtype=np.float32)

        duration = float(n) / float(sr)

        # --- Peak / RMS / Crest Factor (whole file) ---
        peak = float(np.max(np.abs(data)))
        rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
        crest_factor = (peak / rms) if rms > 1e-9 else 1.0

        # --- Zero-Crossing Rate (whole file; sign test is >= 0 vs < 0) ---
        signs = data >= 0.0
        crossings = int(np.count_nonzero(signs[1:] != signs[:-1]))
        zcr = float(crossings) / float(n - 1) if n > 1 else 0.0

        # --- Envelope decay time (whole file) ---
        decay_seconds = compute_envelope_decay_seconds(data, sr)

        # --- Spectral centroid / rolloff (windowed FFT average) ---
        spectral_centroid, spectral_rolloff = compute_spectral_centroid_rolloff(data, sr)

        # --- Normalisation (matches C++ runInferenceBatch) ---
        norm_duration = min(duration / 10.0, 1.0)
        norm_centroid = min(spectral_centroid / 16000.0, 1.0)
        norm_flatness = 1.0 - min(crest_factor / 20.0, 1.0)
        norm_zcr = min(max(zcr, 0.0), 1.0)
        norm_rms = min(rms * 5.0, 1.0)
        norm_decay = min(decay_seconds / 3.0, 1.0)
        if norm_decay <= 0.001:
            norm_decay = norm_duration
        low_rolloff = 1.0 - min(spectral_rolloff / 20000.0, 1.0)
        high_rolloff = min(spectral_rolloff / 20000.0, 1.0)

        return np.array([
            norm_duration,
            norm_centroid,
            norm_flatness,
            norm_zcr,
            norm_rms,
            norm_decay,
            low_rolloff,
            high_rolloff,
        ], dtype=np.float32)

    except Exception as e:
        print(f"  WARN: failed on {filepath}: {e}", file=sys.stderr, flush=True)
        return np.zeros(8, dtype=np.float32)


def _worker(task):
    """Pool worker: (index, path) -> (index, 8 features). Pure function of the
    file contents, so results are independent of worker count and scheduling."""
    idx, path = task
    return idx, extract_dsp_features(path)


def extract_all(filenames, fn_map, workers):
    """
    Extract features for every filename, in parallel. Results are written by
    index, so the output array is identical regardless of `workers` (verified
    by --self-check).
    """
    num_samples = len(filenames)
    dsp_features = np.zeros((num_samples, 8), dtype=np.float32)

    tasks = []
    missing = 0
    for i in range(num_samples):
        fn = str(filenames[i])
        path = fn_map.get(fn)
        if path is None:
            missing += 1
        else:
            tasks.append((i, path))

    start_time = time.time()
    done = 0
    if workers <= 1:
        for task in tasks:
            idx, feats = _worker(task)
            dsp_features[idx] = feats
            done += 1
            if done % 1000 == 0:
                _progress(done, len(tasks), start_time)
    else:
        with mp.Pool(processes=workers) as pool:
            for idx, feats in pool.imap_unordered(_worker, tasks, chunksize=16):
                dsp_features[idx] = feats
                done += 1
                if done % 1000 == 0:
                    _progress(done, len(tasks), start_time)

    elapsed = time.time() - start_time
    print(f"Completed in {elapsed:.1f}s ({len(tasks) / max(elapsed, 1e-9):.1f} samp/s)", flush=True)
    return dsp_features, missing


def _progress(done, total, start_time):
    elapsed = time.time() - start_time
    rate = done / max(elapsed, 1e-9)
    eta = (total - done) / max(rate, 1e-9)
    print(f"  {done}/{total} ({done * 100.0 / total:.1f}%) "
          f"- {rate:.1f} samp/s - ETA {eta / 60.0:.1f} min", flush=True)


def self_check(fn_map, filenames, workers):
    """Confirm the parallel path reproduces the serial path exactly."""
    subset = [f for f in filenames[:400] if str(f) in fn_map][:200]
    if not subset:
        print("self-check: no files available", flush=True)
        return 1
    print(f"self-check: comparing serial vs {workers}-worker on {len(subset)} files...", flush=True)
    serial, _ = extract_all(subset, fn_map, workers=1)
    parallel, _ = extract_all(subset, fn_map, workers=workers)
    if np.array_equal(serial, parallel):
        print(f"self-check PASS: bit-identical across {len(subset)} files", flush=True)
        return 0
    diff = np.abs(serial - parallel)
    print(f"self-check FAIL: max abs diff {diff.max():.3e} on "
          f"{int((diff > 0).any(axis=1).sum())} file(s)", flush=True)
    return 1


def main():
    parser = argparse.ArgumentParser(description="Build the 520-D hybrid dataset.")
    parser.add_argument("--workers", type=int, default=min(8, mp.cpu_count()),
                        help="Parallel extraction workers (1 = serial)")
    parser.add_argument("--self-check", action="store_true",
                        help="Verify the parallel path matches serial, then exit")
    args = parser.parse_args()

    if os.path.exists(OUT_HYBRID_NPZ):
        try:
            os.remove(OUT_HYBRID_NPZ)
        except Exception:
            pass

    print(f"Loading existing 512-D PANNs dataset from {EMBEDDINGS_NPZ}...", flush=True)
    data = np.load(EMBEDDINGS_NPZ, allow_pickle=True)

    embeddings = data["embeddings"]  # (N, 512)
    labels = data["labels"]          # (N,)
    vendors = data["vendors"]        # (N,)
    filenames = data["filenames"]    # (N,)

    classes = [
        "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat",
        "Impact", "Kick", "Music Loop", "Percussion", "Riser", "Snare",
        "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase",
    ]

    fn_map = build_filename_map(SOURCE_ROOT)
    num_samples = len(filenames)

    if args.self_check:
        return self_check(fn_map, filenames, args.workers)

    print(f"Extracting 8 DSP features for {num_samples} samples "
          f"(C++-matched spec, {args.workers} workers)...", flush=True)
    dsp_features, missing = extract_all(filenames, fn_map, args.workers)

    if missing > 0:
        print(f"WARNING: {missing}/{num_samples} files not found on disk (zero features)", flush=True)

    print("\nFeature statistics:", flush=True)
    names = ["duration", "centroid", "flatness", "zcr", "rms", "decay", "low_r", "high_r"]
    for j, name in enumerate(names):
        col = dsp_features[:, j]
        nz = np.count_nonzero(col)
        print(f"  [{j}] {name:>10s}: mean={np.mean(col):.4f}  std={np.std(col):.4f}  "
              f"min={np.min(col):.4f}  max={np.max(col):.4f}  nonzero={nz}", flush=True)

    hybrid_embeddings = np.hstack([embeddings, dsp_features]).astype(np.float32)

    print(f"\nHybrid dataset shape: {hybrid_embeddings.shape}", flush=True)
    print(f"Saving to {OUT_HYBRID_NPZ}...", flush=True)

    np.savez(
        OUT_HYBRID_NPZ,
        embeddings=hybrid_embeddings,
        panns_embeddings=embeddings,
        dsp_features=dsp_features,
        labels=labels,
        vendors=vendors,
        filenames=filenames,
        classes=classes,
    )

    size_mb = os.path.getsize(OUT_HYBRID_NPZ) / (1024 * 1024)
    print(f"Saved ({size_mb:.2f} MB)", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)

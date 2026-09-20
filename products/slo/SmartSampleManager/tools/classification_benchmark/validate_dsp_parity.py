#!/usr/bin/env python3
"""
Verify that the vectorised DSP extractor in build_hybrid_v4_dataset.py is
numerically equivalent to a literal, loop-for-loop transcription of the C++
source (SampleManagerEngine.cpp).

The vectorised version is what actually builds the training set, so this
check is what licenses the claim that the training features match the C++
production path. Run it before any retrain that changes the extractor.

Usage:
  python3 validate_dsp_parity.py [reference_module.py] [num_files]
"""

import sys
import math
import importlib.util
import numpy as np
import soundfile as sf

import build_hybrid_v4_dataset as fast

DEFAULT_REFERENCE = "/private/tmp/claude-501/-Volumes-Jack-Gandy-1TB-SSD-NITE-DSP/13c457f5-c2de-46dc-9b84-f8777969ba81/scratchpad/reference_slow_extractor.py"

# Tolerances. The vectorised path accumulates in float64 in a different
# order from the scalar loops, so exact bit equality is not expected; these
# bounds are far tighter than the normalisation quantisation that follows.
ATOL = 1e-6
RTOL = 1e-5


def load_reference(path):
    spec = importlib.util.spec_from_file_location("reference_slow_extractor", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def pick_files(fn_map, num_files):
    """Pick a spread of files across durations and sample rates."""
    candidates = []
    for name, path in sorted(fn_map.items()):
        try:
            info = sf.info(path)
        except Exception:
            continue
        candidates.append((info.duration, info.samplerate, info.channels, path))
        if len(candidates) >= num_files * 40:
            break

    if not candidates:
        return []

    candidates.sort()
    # Even spread across the duration-sorted list, so short one-shots and
    # long loops are both represented.
    step = max(1, len(candidates) // num_files)
    return candidates[::step][:num_files]


def main():
    ref_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_REFERENCE
    num_files = int(sys.argv[2]) if len(sys.argv) > 2 else 15

    print(f"Reference implementation: {ref_path}")
    ref = load_reference(ref_path)

    fn_map = fast.build_filename_map(fast.SOURCE_ROOT)
    selected = pick_files(fn_map, num_files)
    if not selected:
        print("FAIL: no audio files found to validate against")
        return 1

    names = ["duration", "centroid", "flatness", "zcr", "rms", "decay", "low_r", "high_r"]
    max_abs_err = np.zeros(8)
    failures = []

    print(f"\nComparing {len(selected)} files:\n")
    for duration, sr, channels, path in selected:
        a = fast.extract_dsp_features(path)
        b = ref.extract_dsp_features(path)

        err = np.abs(a.astype(np.float64) - b.astype(np.float64))
        max_abs_err = np.maximum(max_abs_err, err)

        ok = np.allclose(a, b, atol=ATOL, rtol=RTOL)
        status = "OK  " if ok else "FAIL"
        if not ok:
            failures.append((path, a, b, err))

        print(f"  {status} {duration:7.2f}s {sr:6d}Hz {channels}ch  "
              f"maxerr={err.max():.3e}  {path.split('/')[-1][:45]}")

    print("\n=== Per-dimension max absolute error ===")
    for j, name in enumerate(names):
        flag = "" if max_abs_err[j] <= ATOL else "   <-- EXCEEDS TOLERANCE"
        print(f"  [{j}] {name:>10s}: {max_abs_err[j]:.6e}{flag}")

    if failures:
        print(f"\n=== {len(failures)} FILE(S) OUTSIDE TOLERANCE ===")
        for path, a, b, err in failures[:5]:
            print(f"\n{path}")
            for j, name in enumerate(names):
                mark = " *" if err[j] > ATOL else ""
                print(f"  [{j}] {name:>10s}  fast={a[j]:.8f}  ref={b[j]:.8f}  err={err[j]:.3e}{mark}")
        print(f"\nRESULT: FAIL - vectorised extractor diverges from the reference")
        return 1

    print(f"\nRESULT: PASS - vectorised extractor matches the reference "
          f"within atol={ATOL}, rtol={RTOL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

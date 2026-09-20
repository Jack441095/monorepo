#!/usr/bin/env python3
"""
Measure the train/serve skew in the 512-D PANNs embeddings themselves.

The 8 DSP dims were one source of skew. This checks the other 512, which
are produced by two pipelines that do NOT agree:

  TRAINING (build_all_packs_dataset_v2.py extract_embedding):
    read first 10s at native sr -> mono mean
    -> librosa.resample(res_type="soxr_hq")  [polyphase, anti-aliased]
    -> pad/truncate to 32000*10 = 320000 samples
    -> ONNX

  PRODUCTION (SampleManagerEngine.cpp loadAndResampleWaveform):
    read whole file -> mono mean
    -> LINEAR INTERPOLATION resample, no anti-alias filter
    -> pad/truncate to 160000 samples (5s)
    -> ONNX

Two independent differences: the input window length (10s vs 5s) and the
resampling method. PANNs CNN10 global-pools over time, so window length
changes how much the zero-padding dilutes the content.

This script decomposes the total skew into its two causes by running all
four combinations and reporting cosine similarity against the training
reference.

Usage: python3 measure_panns_train_serve_skew.py [num_files]
"""

import sys
import numpy as np
import soundfile as sf
import onnxruntime as ort

try:
    import librosa
except ImportError:
    librosa = None

MODEL = "/Volumes/Jack_Gandy_1TB_SSD/NITE_DSP/products/slo/SmartSampleManager/Models/panns_cnn10_embedding.onnx"
SOURCE_ROOT = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
TARGET_SR = 32000
TRAIN_LEN = TARGET_SR * 10   # 320000, what the training set used
PROD_LEN = TARGET_SR * 5     # 160000, what SampleManagerEngine.cpp uses


def resample_linear(x, src_sr, dst_sr):
    """
    Bit-faithful port of the C++ loadAndResampleWaveform resampler:
    linear interpolation, NO anti-aliasing filter.
    """
    if src_sr == dst_sr:
        return x.astype(np.float32)
    ratio = float(src_sr) / float(dst_sr)
    n_src = len(x)
    n_out = int(n_src / ratio) + 1
    src_idx = np.arange(n_out, dtype=np.float64) * ratio
    src_idx = src_idx[src_idx < n_src]
    i1 = src_idx.astype(np.int64)
    i2 = np.minimum(i1 + 1, n_src - 1)
    t = (src_idx - i1).astype(np.float32)
    return ((1.0 - t) * x[i1] + t * x[i2]).astype(np.float32)


def resample_soxr(x, src_sr, dst_sr):
    """What the training set used: librosa polyphase, anti-aliased."""
    if src_sr == dst_sr:
        return x.astype(np.float32)
    if librosa is None:
        raise RuntimeError("librosa not installed; cannot reproduce the training resampler")
    return librosa.resample(x, orig_sr=src_sr, target_sr=dst_sr,
                            res_type="soxr_hq").astype(np.float32)


def fit(x, target_len):
    out = np.zeros(target_len, dtype=np.float32)
    n = min(len(x), target_len)
    out[:n] = x[:n]
    return out


def embed(session, in_name, out_name, wave):
    return session.run([out_name], {in_name: wave[np.newaxis, :]})[0].squeeze(0)


def cosine(a, b):
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return float("nan")
    return float(np.dot(a, b) / (na * nb))


def pick_files(num_files):
    import os
    found = []
    for root, _, files in os.walk(SOURCE_ROOT):
        for f in sorted(files):
            if f.lower().endswith(('.wav', '.aif', '.aiff', '.flac')):
                p = os.path.join(root, f)
                try:
                    info = sf.info(p)
                except Exception:
                    continue
                found.append((info.duration, info.samplerate, p))
        if len(found) > num_files * 30:
            break
    found.sort()
    step = max(1, len(found) // num_files)
    return found[::step][:num_files]


def main():
    num_files = int(sys.argv[1]) if len(sys.argv) > 1 else 12

    sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
    in_name = sess.get_inputs()[0].name
    out_name = sess.get_outputs()[0].name

    selected = pick_files(num_files)
    if not selected:
        print("No audio files found")
        return 1

    print(f"PANNs train/serve skew, {len(selected)} files")
    print(f"  reference (training):  soxr_hq resample + {TRAIN_LEN} samples (10s)")
    print(f"  production (C++):      linear resample + {PROD_LEN} samples (5s)\n")
    print(f"{'dur':>7} {'sr':>6}  {'window only':>11} {'resamp only':>11} "
          f"{'BOTH (prod)':>11}  file")

    rows = []
    for duration, sr, path in selected:
        try:
            data, file_sr = sf.read(path, dtype='float32', always_2d=False)
        except Exception as e:
            print(f"  skip {path}: {e}")
            continue
        if data.ndim > 1:
            data = data.mean(axis=1)

        # Training reads only the first 10s at native rate
        train_src = data[:int(file_sr * 10.0)]

        soxr = resample_soxr(train_src, file_sr, TARGET_SR)
        lin = resample_linear(data, file_sr, TARGET_SR)

        e_ref = embed(sess, in_name, out_name, fit(soxr, TRAIN_LEN))   # training
        e_win = embed(sess, in_name, out_name, fit(soxr, PROD_LEN))    # window only
        e_res = embed(sess, in_name, out_name, fit(lin, TRAIN_LEN))    # resampler only
        e_prod = embed(sess, in_name, out_name, fit(lin, PROD_LEN))    # production

        c_win = cosine(e_ref, e_win)
        c_res = cosine(e_ref, e_res)
        c_prod = cosine(e_ref, e_prod)
        rows.append((c_win, c_res, c_prod))

        print(f"{duration:7.2f} {sr:6d}  {c_win:11.4f} {c_res:11.4f} {c_prod:11.4f}  "
              f"{path.split('/')[-1][:40]}")

    if not rows:
        return 1

    arr = np.array(rows)
    labels = ["window only (10s->5s)", "resampler only (soxr->linear)", "BOTH (production)"]
    print("\n=== Cosine similarity to the training-pipeline embedding ===")
    for j, label in enumerate(labels):
        col = arr[:, j]
        print(f"  {label:>32s}: mean={col.mean():.4f}  min={col.min():.4f}  max={col.max():.4f}")

    print("\nInterpretation: 1.0 means production reproduces the embedding the")
    print("model was trained on. Anything materially below that means the")
    print("classifier sees a different distribution at run time than in training,")
    print("regardless of how good the cross-validated accuracy looks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

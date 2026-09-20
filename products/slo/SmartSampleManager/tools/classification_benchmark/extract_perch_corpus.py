#!/usr/bin/env python3
"""
Extract Perch v2 embeddings for the full 21,793-file corpus.

Enables the pseudo-labelling result (+7.9pp, measured on CLAP embeddings alone)
to be tested on the full Perch+CLAP stack.

Row order matches clap_audio_all/NNNNN.flac, which prep_clap_audio.py --all
wrote in npz row order -- so output row i aligns with hybrid_x.npy row i and
clap_all_music.npy row i. No index mapping needed.

Uses the int8 model (131MB): measured cosine 0.9997 vs fp32 and 78.2% vs 77.8%
end-to-end, i.e. quantisation is free.
"""
import os, sys, time, argparse
import numpy as np, soundfile as sf, onnxruntime as ort

SR, N = 32000, 160000

def load(path):
    y, s = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1: y = y.mean(1)
    if s != SR:
        # linear resample: matches the C++ production path, and measured
        # negligible vs soxr (cosine 0.9995) in the window-skew analysis
        ratio = s / SR
        idx = np.arange(int(len(y)/ratio)) * ratio
        idx = idx[idx < len(y) - 1]
        i0 = idx.astype(np.int64); frac = (idx - i0).astype(np.float32)
        y = (1-frac)*y[i0] + frac*y[i0+1]
    out = np.zeros(N, dtype=np.float32)
    k = min(len(y), N); out[:k] = y[:k]
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio-dir", default="clap_audio_all")
    ap.add_argument("--model", default="perch_int8_matmul.onnx")
    ap.add_argument("--out", default="perch_all_corpus.npy")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--threads", type=int, default=0)
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.audio_dir) if f.endswith(".flac"))
    n = len(files); print(f"{n} clips in {a.audio_dir}", flush=True)

    so = ort.SessionOptions()
    if a.threads: so.intra_op_num_threads = a.threads
    sess = ort.InferenceSession(a.model, so, providers=["CPUExecutionProvider"])

    out = np.zeros((n, 1536), dtype=np.float32)
    t0 = time.time()
    for s in range(0, n, a.batch):
        chunk = files[s:s+a.batch]
        batch = np.stack([load(os.path.join(a.audio_dir, f)) for f in chunk])
        out[s:s+len(chunk)] = sess.run(["embedding"], {"inputs": batch})[0]
        if s and s % (a.batch*40) == 0:
            r = s/(time.time()-t0)
            print(f"  {s}/{n}  {r:.1f}/s  ETA {(n-s)/r/60:.0f} min", flush=True)
        if s and s % (a.batch*400) == 0:
            np.save(a.out, out)   # periodic checkpoint
    np.save(a.out, out)
    print(f"saved {a.out} {out.shape} in {(time.time()-t0)/60:.1f} min", flush=True)

if __name__ == "__main__":
    main()

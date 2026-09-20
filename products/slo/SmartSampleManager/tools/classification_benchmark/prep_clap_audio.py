#!/usr/bin/env python3
"""
Prepare the held-out set for CLAP zero-shot scoring on the GPU box.

CLAP expects 48kHz mono. Rather than shipping the original files (93GB
library, or ~1.9GB of 10s-padded PCM), each clip is written at its true
length (capped at CLAP's 10s window) as FLAC, which is lossless and roughly
halves the bytes. Median sample length here is under 2s, so this is a large
saving over padding everything to 10s.

Files are named by their position in the held-out order, so the manifest,
the FLAC directory, and the existing deployment_distribution_report.npz
(yte / pred_a) all index the same rows.
"""

import os
import sys
import json
import time
import argparse
import multiprocessing as mp
import numpy as np
import soundfile as sf
import librosa

import build_hybrid_v4_dataset as dspmod

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HYBRID_NPZ = os.path.join(SCRIPT_DIR, "slo_all_packs_hybrid_v4.npz")
IDX_NPY = os.path.join(SCRIPT_DIR, "heldout_indices.npy")
OUT_DIR = os.path.join(SCRIPT_DIR, "clap_audio")
OUT_DIR_ALL = os.path.join(SCRIPT_DIR, "clap_audio_all")
MANIFEST = os.path.join(OUT_DIR, "manifest.json")

CLAP_SR = 48000
CLAP_MAX_SECONDS = 10.0


def convert(task):
    # out_dir travels in the task: under macOS/spawn each worker re-imports
    # this module, so a module-level OUT_DIR reassigned inside main() is NOT
    # visible here and every file silently lands in the default directory.
    pos, path, out_dir = task
    out = os.path.join(out_dir, f"{pos:05d}.flac")
    try:
        y, sr = sf.read(path, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        if len(y) == 0:
            return pos, False
        y = y[:int(sr * CLAP_MAX_SECONDS)]
        if sr != CLAP_SR:
            y = librosa.resample(y, orig_sr=sr, target_sr=CLAP_SR, res_type="soxr_hq")
        peak = float(np.max(np.abs(y))) if len(y) else 0.0
        if peak > 1.0:
            y = y / peak
        sf.write(out, y.astype(np.float32), CLAP_SR, format="FLAC", subtype="PCM_16")
        return pos, True
    except Exception:
        return pos, False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=min(8, mp.cpu_count()))
    ap.add_argument("--all", action="store_true",
                    help="convert the whole corpus in npz row order (row i of the "
                         "output aligns with row i of hybrid_x.npy), not just the held-out split")
    args = ap.parse_args()

    global OUT_DIR, MANIFEST
    if args.all:
        OUT_DIR = OUT_DIR_ALL
        MANIFEST = os.path.join(OUT_DIR, "manifest.json")
    os.makedirs(OUT_DIR, exist_ok=True)

    d = np.load(HYBRID_NPZ, allow_pickle=True)
    filenames = d["filenames"]
    labels = d["labels"]
    classes = [str(c) for c in d["classes"]]
    # --all keeps npz row order so CLAP row i lines up with hybrid_x.npy row i.
    idx_te = np.arange(len(filenames)) if args.all else np.load(IDX_NPY)

    fn_map = dspmod.build_filename_map(dspmod.SOURCE_ROOT)

    tasks, manifest, missing = [], [], 0
    for pos, i in enumerate(idx_te):
        fn = str(filenames[i])
        path = fn_map.get(fn)
        if path is None:
            missing += 1
            manifest.append({"pos": pos, "filename": fn, "label": str(labels[i]), "ok": False})
            continue
        tasks.append((pos, path, OUT_DIR))
        manifest.append({"pos": pos, "filename": fn, "label": str(labels[i]), "ok": True})

    print(f"held-out {len(idx_te)}, resolvable {len(tasks)}, missing {missing}", flush=True)

    t0 = time.time()
    done = 0
    with mp.Pool(args.workers) as pool:
        for pos, ok in pool.imap_unordered(convert, tasks, chunksize=16):
            if not ok:
                manifest[pos]["ok"] = False
            done += 1
            if done % 500 == 0:
                el = time.time() - t0
                print(f"  {done}/{len(tasks)} - {done/el:.1f} files/s", flush=True)

    with open(MANIFEST, "w") as f:
        json.dump({"classes": classes, "items": manifest}, f)

    ok = sum(1 for m in manifest if m["ok"])
    total_mb = sum(os.path.getsize(os.path.join(OUT_DIR, f))
                   for f in os.listdir(OUT_DIR) if f.endswith(".flac")) / 1e6
    print(f"\nconverted {ok}/{len(manifest)} in {time.time()-t0:.1f}s")
    print(f"{OUT_DIR}: {total_mb:.0f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Build an embedding set for the files the ML classifier ACTUALLY serves.

Motivation
----------
Training labels come from `classify_relpath_and_name()` -- pure filename /
folder keyword matching. Production's evidence hierarchy is
EMBEDDED_METADATA > FILENAME > FOLDER > DSP, and ML only overrides
DSP/FOLDER/empty. So a file with filename evidence is decided by the
filename, and ML never runs on it.

The consequence is a selection bias: the model is trained only on files
where the keyword matcher succeeded, and only ever consulted on files where
it failed. Measured coverage:

  sample_pack_testing : 21793/28330 labelled (76.9%), 6537 not (23.1%)
  Samples 2021 ->     : 35042/41949 labelled (83.5%), 6907 not (16.5%)

This script samples the *unlabelled* population and embeds it so the model's
behaviour there can be measured. No hand labels are required for the first
measurement: comparing confidence / centroid-cosine distributions against a
held-out slice of the labelled population shows whether the model is
operating in-distribution or is lost on the files it exists to handle.

Embeddings use the TRAINING pipeline (first 10s, soxr_hq -> 32kHz, padded to
320000) so they are directly comparable to slo_all_packs_embeddings.npz.
The separate production-window skew is documented in
SLO_V4_DSP_FEATURE_PARITY_SPEC.md and is deliberately not mixed in here.
"""

import os
import sys
import time
import random
import argparse
import importlib.util
import collections
import numpy as np
import soundfile as sf
import librosa
import onnxruntime as ort

import build_hybrid_v4_dataset as dspmod

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "../../Models/panns_cnn10_embedding.onnx")
OUT_NPZ = os.path.join(SCRIPT_DIR, "slo_no_evidence_evalset.npz")

ROOTS = [
    "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing",
    "/Volumes/Jack_Gandy_1TB_SSD/Samples 2021 ->",
]
AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}
TARGET_SR = 32000
TRAIN_LEN = TARGET_SR * 10


def load_labeller():
    """Reuse the exact keyword matcher the training set was built with."""
    path = os.path.join(SCRIPT_DIR, "build_all_packs_dataset_v2.py")
    spec = importlib.util.spec_from_file_location("_labeller", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_labeller"] = mod
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    return mod.classify_relpath_and_name


def collect_no_evidence(classify):
    """
    Every file for which the keyword matcher yields no label.

    CRITICAL: the relative path handed to `classify` must be computed the
    same way build_all_packs_dataset_v2.py computes it, i.e. relative to the
    *pack* directory (line 109: `rel = os.path.relpath(root, pdir)`), NOT
    relative to the collection root. Walking from the root instead feeds the
    pack name ("Organic Drum Kit", "Mike Shinoda Drums", ...) into the
    matcher, which labels files the training pipeline left unlabelled and so
    silently shrinks the no-evidence population being sampled here.
    """
    found = []
    for root in ROOTS:
        if not os.path.isdir(root):
            print(f"  skip missing root: {root}", flush=True)
            continue
        root_name = os.path.basename(root)
        n_here = 0
        for pack in sorted(os.listdir(root)):
            pdir = os.path.join(root, pack)
            if pack.startswith("."):
                continue
            if not os.path.isdir(pdir):
                # loose file directly under the collection root
                if os.path.splitext(pack)[1].lower() in AUDIO_EXTS:
                    if classify(".", pack) is None:
                        found.append((root_name, "(root)", pdir))
                        n_here += 1
                continue
            for dirpath, dirnames, files in os.walk(pdir):
                dirnames[:] = [d for d in dirnames if not d.startswith(".")]
                rel = os.path.relpath(dirpath, pdir)
                for f in files:
                    if os.path.splitext(f)[1].lower() not in AUDIO_EXTS:
                        continue
                    if classify(rel, f) is None:
                        found.append((root_name, pack, os.path.join(dirpath, f)))
                        n_here += 1
        print(f"  {root_name}: {n_here} no-evidence files", flush=True)
    return found


def stratified_sample(items, n_target, seed=42):
    """Spread the sample across (root, top-level folder) groups."""
    rng = random.Random(seed)
    buckets = collections.defaultdict(list)
    for root, group, path in items:
        buckets[(root, group)].append(path)
    for v in buckets.values():
        rng.shuffle(v)

    keys = sorted(buckets.keys())
    picked = []
    # round-robin so no single folder dominates
    while len(picked) < n_target:
        progressed = False
        for k in keys:
            if buckets[k]:
                picked.append((k[0], k[1], buckets[k].pop()))
                progressed = True
                if len(picked) >= n_target:
                    break
        if not progressed:
            break
    return picked


def embed_training_pipeline(sess, inn, outn, path):
    """First 10s, soxr_hq -> 32kHz, zero-padded to 320000. Matches training."""
    with sf.SoundFile(path) as f:
        sr = f.samplerate
        y = f.read(frames=min(len(f), int(sr * 10.0)), dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = np.mean(y, axis=-1)
    if sr != TARGET_SR:
        y = librosa.resample(y, orig_sr=sr, target_sr=TARGET_SR, res_type="soxr_hq")
    if len(y) < TRAIN_LEN:
        y = np.pad(y, (0, TRAIN_LEN - len(y)))
    else:
        y = y[:TRAIN_LEN]
    return sess.run([outn], {inn: y[np.newaxis, :].astype(np.float32)})[0].squeeze(0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--num", type=int, default=1500, help="how many files to sample")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    classify = load_labeller()

    print("Collecting files with no filename/folder evidence...", flush=True)
    items = collect_no_evidence(classify)
    print(f"Total no-evidence population: {len(items)}", flush=True)
    if not items:
        return 1

    picked = stratified_sample(items, args.num, args.seed)
    print(f"Stratified sample: {len(picked)} files across "
          f"{len({(r, g) for r, g, _ in picked})} folder groups\n", flush=True)

    so = ort.SessionOptions()
    so.intra_op_num_threads = 8
    sess = ort.InferenceSession(os.path.abspath(MODEL_PATH), so,
                                providers=["CPUExecutionProvider"])
    inn = sess.get_inputs()[0].name
    outn = sess.get_outputs()[0].name

    def save(embs, dsps, paths, roots, groups, final):
        if not embs:
            return
        e = np.stack(embs).astype(np.float32)
        d = np.stack(dsps).astype(np.float32)
        np.savez(OUT_NPZ,
                 embeddings=np.hstack([e, d]).astype(np.float32),
                 panns_embeddings=e, dsp_features=d,
                 paths=np.array(paths), source_root=np.array(roots),
                 group=np.array(groups), complete=np.array([final]))
        if not final:
            print(f"    checkpoint: {len(embs)} files written to {OUT_NPZ}", flush=True)

    embs, dsps, paths, roots, groups = [], [], [], [], []
    t0 = time.time()
    for i, (root, group, path) in enumerate(picked):
        if i > 0 and i % 100 == 0:
            el = time.time() - t0
            rate = i / el
            print(f"  {i}/{len(picked)} - {rate:.2f} files/s - "
                  f"ETA {(len(picked) - i) / rate / 60:.1f} min", flush=True)
        # Periodic checkpoint so a long run is never a single point of failure
        # and the analysis can be run against a partial set at any time.
        if i > 0 and i % 250 == 0:
            save(embs, dsps, paths, roots, groups, final=False)
        try:
            e = embed_training_pipeline(sess, inn, outn, path)
            d = dspmod.extract_dsp_features(path)
        except Exception as ex:
            print(f"  WARN {os.path.basename(path)}: {ex}", flush=True)
            continue
        if not np.all(np.isfinite(e)) or float(np.dot(e, e)) <= 0.0:
            continue
        embs.append(e); dsps.append(d); paths.append(path)
        roots.append(root); groups.append(group)

    if not embs:
        print("No usable embeddings produced")
        return 1

    el = time.time() - t0
    print(f"\nEmbedded {len(embs)} files in {el / 60:.1f} min "
          f"({len(embs) / el:.2f} files/s)")

    save(embs, dsps, paths, roots, groups, final=True)
    print(f"Saved {OUT_NPZ} ({os.path.getsize(OUT_NPZ) / 1e6:.1f} MB), "
          f"{len(embs)} files x {embs[0].shape[0] + dsps[0].shape[0]} dims")
    return 0


if __name__ == "__main__":
    sys.exit(main())

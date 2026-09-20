#!/usr/bin/env python3
"""
build_all_packs_dataset_v2.py
Sequential (single-process) extraction of 512-D PANNs embeddings from all 33 sample packs.
Uses a single persistent ONNX session and processes samples one at a time — reliable and predictable.
Saves progress checkpoints every 2000 samples so it can resume.
"""
import os
import sys
import time
import numpy as np
import soundfile as sf
import librosa
import onnxruntime as ort
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_ROOT = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
MODEL_PATH = os.path.join(SCRIPT_DIR, "../../Models/panns_cnn10_embedding.onnx")
OUT_NPZ = os.path.join(SCRIPT_DIR, "slo_all_packs_embeddings.npz")
CHECKPOINT_NPZ = os.path.join(SCRIPT_DIR, "slo_all_packs_checkpoint.npz")

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}

CLASSES = [
    "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat",
    "Impact", "Kick", "Music Loop", "Percussion", "Riser", "Snare",
    "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
]

def classify_relpath_and_name(rel_folder, filename):
    rf = rel_folder.lower()
    fn = filename.lower()
    full = f"{rf}/{fn}"

    if "riser" in full or "sweep" in full or "pitch up" in full or "build up" in full:
        if "loop" in full and "fx" not in full:
            return "Synth Loop"
        return "Riser"
    if "impact" in full or "sub drop" in full or "downlifter" in full or "explosion" in full:
        return "Impact"
    if "vocal" in full or "vox" in full or "acapella" in full or "phrase" in full or "spoken" in full:
        if "loop" in full or "melody" in full or "melodies" in full:
            return "Vocal Loop"
        return "Vocal Phrase"
    if "bass" in full or "808" in full or "reese" in full or "sub" in full:
        if "loop" in full or "riff" in full:
            return "Bass Loop"
        return "Bass One-Shot"
    if "kick" in full or "bd" in fn:
        if "loop" in full:
            return "Percussion"
        return "Kick"
    if "clap" in full or "snap" in full:
        return "Clap"
    if "snare" in full or "rim" in full or "sd" in fn:
        if "loop" in full:
            return "Percussion"
        return "Snare"
    if "hat" in full or "cymbal" in full or "ride" in full or "crash" in full or "hh" in fn:
        return "Hi-Hat"
    if "synth" in full or "lead" in full or "chord" in full or "pad" in full or "keys" in full or "piano" in full or "arp" in full:
        if "loop" in full:
            return "Synth Loop"
        return "Synth"
    if "song_starter" in full or "song starter" in full or "music loop" in full or "melodic loop" in full:
        return "Music Loop"
    if "foley" in full or "found sound" in full or "field" in full or "nature" in full or "organic" in rf:
        return "Foley"
    if "perc" in full or "conga" in full or "bongo" in full or "shaker" in full or "tambourine" in full or "tom" in full or "drum" in full or "beat" in full:
        return "Percussion"
    if "fx" in full or "sfx" in full or "noise" in full or "glitch" in full or "texture" in full:
        return "FX"
    return None


def extract_embedding(path, session, input_name, output_name):
    try:
        with sf.SoundFile(path) as f:
            sr = f.samplerate
            max_frames = int(sr * 10.0)
            y = f.read(frames=min(len(f), max_frames), dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = np.mean(y, axis=-1)
        if sr != 32000:
            y = librosa.resample(y, orig_sr=sr, target_sr=32000, res_type="soxr_hq")
        target_len = 32000 * 10
        if len(y) < target_len:
            y = np.pad(y, (0, target_len - len(y)))
        else:
            y = y[:target_len]
        inp = y[np.newaxis, :].astype(np.float32)
        emb = session.run([output_name], {input_name: inp})[0]
        return emb.squeeze(0).astype(np.float32)
    except Exception as e:
        return None


def main():
    print(f"Scanning all sample packs from {SOURCE_ROOT}...", flush=True)

    samples = []
    class_counts = defaultdict(int)
    for pack in sorted(os.listdir(SOURCE_ROOT)):
        pdir = os.path.join(SOURCE_ROOT, pack)
        if not os.path.isdir(pdir) or pack.startswith("."):
            continue
        for root, dirs, files in os.walk(pdir):
            rel = os.path.relpath(root, pdir)
            for f in sorted(files):
                ext = os.path.splitext(f)[1].lower()
                if ext in AUDIO_EXTS and not f.startswith("."):
                    cls = classify_relpath_and_name(rel, f)
                    if cls and cls in CLASSES:
                        samples.append((os.path.join(root, f), cls, pack, f))
                        class_counts[cls] += 1

    print(f"Total: {len(samples)} labeled samples across {len(set(s[2] for s in samples))} packs", flush=True)
    for c in sorted(CLASSES):
        print(f"  {c:<16}: {class_counts[c]:>5}", flush=True)

    # Load checkpoint if available
    start_idx = 0
    embeddings, labels, vendors, filenames = [], [], [], []
    if os.path.exists(CHECKPOINT_NPZ):
        print(f"\nResuming from checkpoint {CHECKPOINT_NPZ}...", flush=True)
        ck = np.load(CHECKPOINT_NPZ, allow_pickle=True)
        embeddings = list(ck["embeddings"])
        labels = list(ck["labels"])
        vendors = list(ck["vendors"])
        filenames = list(ck["filenames"])
        start_idx = int(ck["next_idx"])
        print(f"Resuming from sample {start_idx} ({len(embeddings)} already extracted)", flush=True)

    print(f"\nInitializing ONNX session...", flush=True)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 4
    session = ort.InferenceSession(MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    print(f"ONNX session ready. Processing {len(samples) - start_idx} remaining samples...\n", flush=True)

    t0 = time.time()
    errors = 0

    for i in range(start_idx, len(samples)):
        path, cls, pack, fname = samples[i]
        emb = extract_embedding(path, session, input_name, output_name)
        if emb is not None:
            embeddings.append(emb)
            labels.append(cls)
            vendors.append(pack)
            filenames.append(fname)
        else:
            errors += 1

        if (i + 1) % 500 == 0:
            elapsed = time.time() - t0
            rate = (i + 1 - start_idx) / max(elapsed, 1)
            remaining = (len(samples) - i - 1) / max(rate, 1e-3) / 60
            print(f"  [{i+1:>5}/{len(samples)}] Valid: {len(embeddings)} | Errors: {errors} | "
                  f"{rate:.1f} samp/s | ETA: {remaining:.1f} min", flush=True)
            # Save checkpoint
            np.savez_compressed(
                CHECKPOINT_NPZ,
                embeddings=np.array(embeddings, dtype=np.float32),
                labels=np.array(labels),
                vendors=np.array(vendors),
                filenames=np.array(filenames),
                next_idx=np.array(i + 1)
            )

    # Final save
    print(f"\nSaving final dataset to {OUT_NPZ}...", flush=True)
    np.savez_compressed(
        OUT_NPZ,
        embeddings=np.array(embeddings, dtype=np.float32),
        labels=np.array(labels),
        vendors=np.array(vendors),
        filenames=np.array(filenames)
    )
    # Clean up checkpoint
    if os.path.exists(CHECKPOINT_NPZ):
        os.remove(CHECKPOINT_NPZ)

    elapsed_total = (time.time() - t0) / 60
    print(f"\nSUCCESS: Saved {len(embeddings)} embeddings to {OUT_NPZ}", flush=True)
    print(f"Total time: {elapsed_total:.1f} min | Errors: {errors}", flush=True)


if __name__ == "__main__":
    main()

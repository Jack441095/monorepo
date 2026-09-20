#!/usr/bin/env python3
"""
Scans all 33 commercial sample packs from /Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing
and extracts 512-D PANNs embeddings using multi-threaded audio loading + batched ONNX inference.
"""

import os
import sys
import time
import numpy as np
import soundfile as sf
import librosa
import onnxruntime as ort
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

SOURCE_ROOT = "/Volumes/Jack_Gandy_1TB_SSD/testing-for-NITE-DSP/sample_pack_testing"
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../Models/panns_cnn10_embedding.onnx")

AUDIO_EXTS = {".wav", ".aif", ".aiff", ".flac"}

CLASSES = [
    "Bass Loop", "Bass One-Shot", "Clap", "FX", "Foley", "Hi-Hat",
    "Impact", "Kick", "Music Loop", "Percussion", "Riser", "Snare",
    "Synth", "Synth Loop", "Vocal Loop", "Vocal Phrase"
]

# Compatibility API for the historical process-pool smoke test. The main
# extractor below uses a batched session; these workers use one persistent CPU
# session per process and return the same tuple shape as a valid batch item.
_WORKER_SESSION = None
_WORKER_INPUT = None
_WORKER_OUTPUT = None


def worker_init():
    """Initialise one read-only CPU inference session in a worker process."""
    global _WORKER_SESSION, _WORKER_INPUT, _WORKER_OUTPUT
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = 1
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    _WORKER_SESSION = ort.InferenceSession(
        MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"]
    )
    _WORKER_INPUT = _WORKER_SESSION.get_inputs()[0].name
    _WORKER_OUTPUT = _WORKER_SESSION.get_outputs()[0].name


def process_single_sample(item):
    """Extract one embedding for the legacy process-pool validation path."""
    global _WORKER_SESSION
    if _WORKER_SESSION is None:
        worker_init()
    loaded = load_audio_clip(item)
    if loaded is None:
        return None
    y, cls, pack, fname = loaded
    target_len = 32000 * 10
    if len(y) < target_len:
        y = np.pad(y, (0, target_len - len(y)))
    else:
        y = y[:target_len]
    try:
        embedding = _WORKER_SESSION.run(
            [_WORKER_OUTPUT], {_WORKER_INPUT: y[np.newaxis, :].astype(np.float32)}
        )[0].squeeze(0).astype(np.float32)
        return embedding, cls, pack, fname
    except Exception:
        return None

def classify_relpath_and_name(rel_folder, filename):
    rf = rel_folder.lower()
    fn = filename.lower()
    full = f"{rf}/{fn}"

    # Risers & Sweeps
    if "riser" in full or "sweep" in full or "pitch up" in full or "build up" in full:
        if "loop" in full and not "fx" in full:
            return "Synth Loop"
        return "Riser"

    # Impacts
    if "impact" in full or "sub drop" in full or "downlifter" in full or "explosion" in full:
        return "Impact"

    # Vocal Loops & Phrases
    if "vocal" in full or "vox" in full or "acapella" in full or "phrase" in full or "spoken" in full:
        if "loop" in full or "melody" in full or "melodies" in full:
            return "Vocal Loop"
        return "Vocal Phrase"

    # Bass Loops & One-Shots
    if "bass" in full or "808" in full or "reese" in full or "sub" in full:
        if "loop" in full or "riff" in full:
            return "Bass Loop"
        return "Bass One-Shot"

    # Kicks
    if "kick" in full or "bd" in fn:
        if "loop" in full:
            return "Percussion"
        return "Kick"

    # Claps & Snaps
    if "clap" in full or "snap" in full:
        return "Clap"

    # Snares & Rims
    if "snare" in full or "rim" in full or "sd" in fn:
        if "loop" in full:
            return "Percussion"
        return "Snare"

    # Hi-Hats & Cymbals
    if "hat" in full or "cymbal" in full or "ride" in full or "crash" in full or "open hat" in full or "closed hat" in full or "hh" in fn:
        return "Hi-Hat"

    # Synths & Synth Loops
    if "synth" in full or "lead" in full or "chord" in full or "pad" in full or "keys" in full or "piano" in full or "arp" in full:
        if "loop" in full:
            return "Synth Loop"
        return "Synth"

    # Music Loops & Song Starters
    if "song_starter" in full or "song starter" in full or "music loop" in full or "melodic loop" in full or "melodics loop" in full or "full loop" in full:
        return "Music Loop"

    # Foley & Found Sound
    if "foley" in full or "found sound" in full or "field" in full or "nature" in full or "organic" in rf:
        if "loop" in full:
            return "Foley"
        return "Foley"

    # Percussion (Congas, Bongos, Shakers, Tambourines, Toms, etc.)
    if "perc" in full or "conga" in full or "bongo" in full or "shaker" in full or "tambourine" in full or "tom" in full or "drum" in full or "beat" in full:
        return "Percussion"

    # FX
    if "fx" in full or "sfx" in full or "noise" in full or "glitch" in full or "texture" in full:
        return "FX"

    return None

def load_audio_clip(item):
    path, cls, pack, fname = item
    try:
        with sf.SoundFile(path) as f:
            sr = f.samplerate
            max_frames = int(sr * 10.0) # Up to 10s
            frames_to_read = min(len(f), max_frames)
            y = f.read(frames=frames_to_read, dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = np.mean(y, axis=-1)
        if sr != 32000:
            y = librosa.resample(y, orig_sr=sr, target_sr=32000, res_type="soxr_qq")
            sr = 32000

        target_len = min(len(y), 32000 * 10)
        if target_len < 32000:
            y = np.pad(y, (0, 32000 - len(y)))
        else:
            y = y[:target_len]

        return (y.astype(np.float32), cls, pack, fname)
    except Exception:
        return None

def main():
    print(f"Scanning all 33 sample packs from {SOURCE_ROOT}...", flush=True)

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
                        full_path = os.path.join(root, f)
                        samples.append((full_path, cls, pack, f))
                        class_counts[cls] += 1

    print(f"\nTotal labeled samples found across 33 packs: {len(samples)}", flush=True)
    print("-" * 50, flush=True)
    for c in sorted(CLASSES):
        print(f"  {c:<16} : {class_counts[c]:>5} samples", flush=True)
    print("-" * 50, flush=True)

    print(f"Initializing ONNX Runtime session: {MODEL_PATH}...", flush=True)
    opts = ort.SessionOptions()
    opts.intra_op_num_threads = min(8, os.cpu_count() or 4)
    opts.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    session = ort.InferenceSession(MODEL_PATH, sess_options=opts, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name

    print(f"\nExtracting 512-D embeddings with multi-threaded loading and batched ONNX...", flush=True)
    BATCH_SIZE = 64
    embeddings, labels, vendors, filenames = [], [], [], []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=8) as executor:
        for b_start in range(0, len(samples), BATCH_SIZE):
            b_items = samples[b_start : b_start + BATCH_SIZE]
            loaded = list(executor.map(load_audio_clip, b_items))
            valid_batch = [item for item in loaded if item is not None]
            if not valid_batch:
                continue

            # Pad all audio clips in batch to the maximum length in this batch (min 32000)
            max_len = max(max(len(x[0]) for x in valid_batch), 32000)
            padded_audios = []
            for y, cls, pack, fname in valid_batch:
                if len(y) < max_len:
                    padded_audios.append(np.pad(y, (0, max_len - len(y))))
                else:
                    padded_audios.append(y[:max_len])

            batch_tensor = np.stack(padded_audios, axis=0).astype(np.float32)
            embs = session.run([output_name], {input_name: batch_tensor})[0] # [B, 512]

            for emb, (_, cls, pack, fname) in zip(embs, valid_batch):
                embeddings.append(emb)
                labels.append(cls)
                vendors.append(pack)
                filenames.append(fname)

            processed = min(b_start + BATCH_SIZE, len(samples))
            if processed % 1000 == 0 or processed == len(samples):
                elapsed = time.time() - t0
                speed = len(embeddings) / max(elapsed, 1e-3)
                print(f"  [{processed:>5}/{len(samples)}] Extracted {len(embeddings)} valid embeddings ({speed:.1f} samples/sec)...", flush=True)

    embeddings_arr = np.array(embeddings, dtype=np.float32)
    labels_arr = np.array(labels)
    vendors_arr = np.array(vendors)
    filenames_arr = np.array(filenames)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    out_npz = os.path.join(script_dir, "slo_all_packs_embeddings.npz")
    np.savez_compressed(
        out_npz,
        embeddings=embeddings_arr,
        labels=labels_arr,
        vendors=vendors_arr,
        filenames=filenames_arr
    )
    print(f"\nSUCCESS: Saved {len(embeddings_arr)} embeddings from all 33 packs to {out_npz}", flush=True)

if __name__ == "__main__":
    main()

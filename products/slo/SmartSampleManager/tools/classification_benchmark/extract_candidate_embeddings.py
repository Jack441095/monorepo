#!/usr/bin/env python3
"""Resumable Perch+CLAP embedding extraction for a rename-plan subset.

The extractor consumes paths from a JSONL rename plan (or a plain text file),
writes only derived embeddings and path metadata, and checkpoints atomically.
It uses the same 32 kHz/5 s Perch and 48 kHz/10 s CLAP preprocessing contract
as corpus_v2. No source audio is moved, renamed, copied, or rewritten.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import time

import numpy as np

SD = os.path.dirname(os.path.abspath(__file__))
PERCH_MODEL = os.path.join(SD, "perch_int8_matmul.onnx")
CLAP_MODEL = os.path.join(SD, "clap_onnx", "clap_int8_matmul.onnx")
PERCH_SR, PERCH_LEN = 32000, 160000
CLAP_SR, CLAP_LEN = 48000, 480000


def paths_from_jsonl(path, actions):
    with open(path) as f:
        next(f)
        out = []
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            action = row.get("decision", {}).get("action")
            if action in actions and row.get("path"):
                out.append(os.path.abspath(row["path"]))
    return list(dict.fromkeys(out))


def load_audio(path, target_sr, max_len):
    import librosa
    import soundfile as sf
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    y = np.nan_to_num(y.astype(np.float32))
    if sr != target_sr:
        y = librosa.resample(y, orig_sr=sr, target_sr=target_sr).astype(np.float32)
    y = y[:max_len]
    if len(y) < max_len:
        y = np.pad(y, (0, max_len - len(y)))
    return y


def atomic_save(path, paths, emb, errors):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(prefix=".candidate_emb_", suffix=".npz",
                               dir=directory)
    os.close(fd)
    try:
        np.savez(tmp, paths=np.asarray(paths, dtype=object),
                 emb=np.asarray(emb, dtype=np.float32),
                 errors=np.asarray(errors, dtype=object),
                 feature_contract=np.asarray(
                     ["Perch v2 1536-D + CLAP audio 512-D; frozen preprocessing v1"]))
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--actions", default="auto_rename,suggest")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--threads", type=int, default=8)
    args = ap.parse_args()
    actions = set(x.strip() for x in args.actions.split(",") if x.strip())
    paths = paths_from_jsonl(args.plan, actions)
    if args.limit:
        paths = paths[:args.limit]
    paths = [p for p in paths if os.path.isfile(p)]
    print(f"selected {len(paths)} files for embedding ({','.join(sorted(actions))})")

    import onnxruntime as ort
    from transformers import ClapProcessor

    so = ort.SessionOptions()
    so.intra_op_num_threads = args.threads
    so.inter_op_num_threads = 1
    perch = ort.InferenceSession(PERCH_MODEL, so,
                                 providers=["CPUExecutionProvider"])
    clap = ort.InferenceSession(CLAP_MODEL, so,
                                providers=["CPUExecutionProvider"])
    processor = ClapProcessor.from_pretrained(
        os.path.join(SD, "clap_model_music"))

    done_paths, done_emb, done_errors = [], [], []
    if os.path.exists(args.out):
        z = np.load(args.out, allow_pickle=True)
        done_paths = list(z["paths"])
        done_emb = [x for x in z["emb"]]
        done_errors = list(z["errors"])
        print(f"resuming {len(done_paths)} cached rows")
    done = set(done_paths)
    todo = [p for p in paths if p not in done]
    t0 = time.time()
    for start in range(0, len(todo), args.batch):
        chunk = todo[start:start + args.batch]
        valid, valid_paths, errors = [], [], []
        for p in chunk:
            try:
                valid.append((load_audio(p, PERCH_SR, PERCH_LEN),
                              load_audio(p, CLAP_SR, CLAP_LEN)))
                valid_paths.append(p)
            except Exception as exc:
                errors.append((p, f"decode: {str(exc)[:180]}"))
        if valid:
            try:
                p_batch = np.stack([v[0] for v in valid])
                p_emb = perch.run(["embedding"], {"inputs": p_batch})[0]
                c_wavs = [v[1] for v in valid]
                features = processor(audio=c_wavs, sampling_rate=CLAP_SR,
                                     return_tensors="np", padding=True)
                inputs = {"input_features": features["input_features"]}
                if "is_longer" in features:
                    inputs["is_longer"] = features["is_longer"]
                c_emb = clap.run(["audio_embed"], inputs)[0]
                emb = np.hstack([p_emb, c_emb]).astype(np.float32)
                for p, e in zip(valid_paths, emb):
                    if not np.isfinite(e).all():
                        errors.append((p, "non-finite embedding"))
                    else:
                        done_paths.append(p)
                        done_emb.append(e)
                        done_errors.append("")
            except Exception as exc:
                errors.extend((p, f"embedding: {str(exc)[:180]}")
                               for p in valid_paths)
        for p, err in errors:
            done_paths.append(p)
            done_emb.append(np.zeros(2048, dtype=np.float32))
            done_errors.append(err)
        if ((start + len(chunk)) % max(args.batch * 10, 1) == 0
                or start + len(chunk) == len(todo)):
            atomic_save(args.out, done_paths, done_emb, done_errors)
            rate = (start + len(chunk)) / max(time.time() - t0, 1e-6)
            print(f"  {start + len(chunk)}/{len(todo)} new; total "
                  f"{len(done_paths)}; {rate:.2f}/s", flush=True)
    atomic_save(args.out, done_paths, done_emb, done_errors)
    print(f"wrote {args.out}: {len(done_paths)} rows, "
          f"errors={sum(bool(x) for x in done_errors)}")


if __name__ == "__main__":
    raise SystemExit(main())

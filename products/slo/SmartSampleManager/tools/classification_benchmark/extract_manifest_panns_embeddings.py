#!/usr/bin/env python3
"""Extract runtime-compatible 512-D PANNs embeddings for a manifest.

The input manifest and source audio are read only.  Each source SHA-256 is
verified before inference; decode/inference failures are retained in the
checkpoint and never represented as usable zero embeddings.  The output is a
derived NPZ intended for research-cache construction, not production cache
replacement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import numpy as np


TARGET_SR = 32000
TARGET_FRAMES = TARGET_SR * 10
EMBEDDING_DIM = 512
METHOD_VERSION = "manifest_panns_embedding_extraction_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not payload:
        raise ValueError("manifest must be a non-empty JSON list")
    return payload


def load_audio(path: Path) -> np.ndarray:
    import librosa
    import soundfile as sf

    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = np.nan_to_num(audio.astype(np.float32), copy=False)
    if sample_rate != TARGET_SR:
        audio = librosa.resample(
            audio, orig_sr=sample_rate, target_sr=TARGET_SR, res_type="soxr_hq"
        ).astype(np.float32)
    audio = audio[:TARGET_FRAMES]
    if audio.size < TARGET_FRAMES:
        audio = np.pad(audio, (0, TARGET_FRAMES - audio.size))
    return np.ascontiguousarray(audio, dtype=np.float32)


def atomic_save(path: Path, rows: list[dict[str, Any]], model_sha256: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".manifest_panns_", suffix=".npz", dir=path.parent)
    os.close(fd)
    try:
        np.savez_compressed(
            temporary,
            paths=np.asarray([row["path"] for row in rows], dtype=object),
            embeddings=np.asarray([row["embedding"] for row in rows], dtype=np.float32),
            errors=np.asarray([row["error"] for row in rows], dtype=object),
            source_sha256=np.asarray([row["source_sha256"] for row in rows], dtype=object),
            manifest_id=np.asarray([row["sample_id"] for row in rows], dtype=object),
            model_sha256=np.asarray(model_sha256),
            feature_contract=np.asarray(
                "PANNs CNN10 512-D; 32 kHz mono; first 10 seconds; preprocessing v1"
            ),
            method_version=np.asarray(METHOD_VERSION),
        )
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def extract(manifest_path: Path, model_path: Path, output_path: Path,
            batch_size: int = 8, threads: int = 4) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    model_sha = sha256_file(model_path)
    model_data = model_path.with_name(model_path.name + ".data")
    model_data_sha = sha256_file(model_data) if model_data.is_file() else ""

    import onnxruntime as ort

    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, int(threads))
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(model_path), sess_options=options,
                                   providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name

    prior: dict[str, dict[str, Any]] = {}
    if output_path.is_file():
        cached = np.load(output_path, allow_pickle=True)
        for path_value, emb, error, source_hash, sample_id in zip(
            cached["paths"], cached["embeddings"], cached["errors"],
            cached["source_sha256"], cached["manifest_id"]
        ):
            prior[str(sample_id)] = {
                "sample_id": str(sample_id), "path": str(path_value),
                "embedding": np.asarray(emb, dtype=np.float32),
                "error": str(error), "source_sha256": str(source_hash),
            }

    rows: list[dict[str, Any]] = []
    started = time.time()
    for index, item in enumerate(manifest, start=1):
        sample_id = str(item.get("sample_id", index))
        path = Path(str(item.get("path", ""))).expanduser()
        expected_hash = str(item.get("sha256", "")).strip().lower()
        cached = prior.get(sample_id)
        if cached and cached["path"] == str(path) and cached["source_sha256"] == expected_hash:
            rows.append(cached)
            continue

        row: dict[str, Any] = {
            "sample_id": sample_id, "path": str(path),
            "embedding": np.zeros(EMBEDDING_DIM, dtype=np.float32),
            "error": "", "source_sha256": expected_hash,
        }
        try:
            if not path.is_absolute() or not path.is_file():
                raise ValueError("source path does not exist")
            actual_hash = sha256_file(path)
            if len(expected_hash) != 64 or actual_hash != expected_hash:
                raise ValueError("source SHA-256 mismatch")
            audio = load_audio(path)
            embedding = np.asarray(session.run([output_name], {input_name: audio[None, :]})[0]).reshape(-1)
            if embedding.size != EMBEDDING_DIM or not np.isfinite(embedding).all():
                raise ValueError("model returned an invalid 512-D embedding")
            if not np.isfinite(np.linalg.norm(embedding)) or np.linalg.norm(embedding) <= 0:
                raise ValueError("model returned a zero embedding")
            row["embedding"] = embedding.astype(np.float32)
        except Exception as exc:  # retain the failure; continue safely
            row["error"] = str(exc)[:240]
        rows.append(row)
        if index % max(1, batch_size) == 0 or index == len(manifest):
            atomic_save(output_path, rows, model_sha)
            elapsed = max(time.time() - started, 1e-6)
            usable = sum(not bool(r["error"]) for r in rows)
            print(f"{index}/{len(manifest)} rows; usable={usable}; rate={index/elapsed:.2f}/s", flush=True)

    receipt = {
        "record_type": "slo_manifest_panns_embedding_extraction",
        "schema_version": "1.0.0",
        "method_version": METHOD_VERSION,
        "manifest": str(manifest_path.resolve()),
        "manifest_sha256": sha256_file(manifest_path),
        "model": str(model_path.resolve()),
        "model_sha256": model_sha,
        "model_data_sha256": model_data_sha,
        "rows": len(rows),
        "usable_rows": sum(not bool(row["error"]) for row in rows),
        "error_rows": sum(bool(row["error"]) for row in rows),
        "output": str(output_path.resolve()),
        "safety": {
            "source_sha256_verified": True,
            "source_audio_modified": False,
            "production_cache_modified": False,
            "production_policy_changed": False,
        },
    }
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)
    receipt = extract(args.manifest, args.model, args.out, args.batch_size, args.threads)
    args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
    args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["error_rows"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())

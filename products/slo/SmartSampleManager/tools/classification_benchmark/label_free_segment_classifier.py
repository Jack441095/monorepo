#!/usr/bin/env python3
"""Classify time-localized windows with a label-free CLAP prompt bank.

The output is evidence for specialist routing and review.  It is explicitly
multi-label at file level, keeps the window timestamps, and never creates
semantic labels, metadata, or rename actions.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import torch


VERSION = "label_free_segment_classifier_v1"


def _runner():
    path = Path(__file__).with_name("label_free_zero_shot.py")
    spec = importlib.util.spec_from_file_location("label_free_zero_shot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load label-free runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_manifest(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("record_type") != "slo_label_free_segment_manifest":
        raise ValueError("input is not a segment manifest")
    safety = payload.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("segment manifest is not read-only")
    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("segment manifest has no records")
    return payload, records


def _load_window(path: Path, start: float, end: float, target_sr: int) -> np.ndarray:
    with sf.SoundFile(str(path)) as handle:
        source_sr = int(handle.samplerate)
        start_frame = max(0, int(round(start * source_sr)))
        frames = max(1, int(round(max(end - start, 1e-4) * source_sr)))
        handle.seek(min(start_frame, len(handle)))
        data = handle.read(frames=min(frames, max(0, len(handle) - handle.tell())),
                           dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    data = np.asarray(data, dtype=np.float32)
    if not len(data):
        raise ValueError("empty segment window")
    if source_sr != target_sr:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(source_sr, target_sr)
        data = resample_poly(data, target_sr // g, source_sr // g)
    return np.asarray(data, dtype=np.float32)


def _load_audio_file(path: Path, target_sr: int) -> np.ndarray:
    """Load and resample one source once; callers slice windows from it."""
    data, source_sr = sf.read(str(path), dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    data = np.asarray(data, dtype=np.float32)
    if not len(data):
        raise ValueError("empty audio file")
    if int(source_sr) != target_sr:
        from math import gcd
        from scipy.signal import resample_poly
        g = gcd(int(source_sr), target_sr)
        data = resample_poly(data, target_sr // g, int(source_sr) // g)
    return np.asarray(data, dtype=np.float32)


def _slice_window(data: np.ndarray, start: float, end: float, sample_rate: int) -> np.ndarray:
    begin = max(0, int(round(start * sample_rate)))
    finish = max(begin + 1, int(round(end * sample_rate)))
    chunk = np.asarray(data[begin:min(finish, len(data))], dtype=np.float32)
    if not len(chunk):
        raise ValueError("empty segment window")
    return chunk


def _aggregate(labels: list[str], scores: np.ndarray, top_k: int) -> list[dict[str, Any]]:
    """Return strongest labels across windows without pretending probability."""
    if scores.ndim != 2 or scores.shape[1] != len(labels):
        raise ValueError("scores must be [windows, labels]")
    best_window = np.argmax(scores, axis=0)
    best_score = np.max(scores, axis=0)
    order = np.argsort(-best_score)[:max(1, min(top_k, len(labels)))]
    return [{"label": labels[int(i)], "score": float(best_score[int(i)]),
             "window_index": int(best_window[int(i)])} for i in order]


def run(manifest: Path, model_dir: Path, out: Path, device: str = "cpu",
        batch_size: int = 16, top_k: int = 5, min_score: float = 0.15,
        min_margin: float = 0.03, limit: int | None = None) -> dict[str, Any]:
    if top_k < 1 or batch_size < 1:
        raise ValueError("top_k and batch_size must be positive")
    source, records = _read_manifest(manifest)
    if limit is not None:
        records = records[:max(0, limit)]
    runner = _runner()
    processor, model = runner._load_model(model_dir, device)
    labels, text_centroids = runner._text_centroids(processor, model,
                                                     runner.DEFAULT_PROMPTS, device)
    # Decode windows once, but score them in global batches.  The original
    # per-file loop incurred thousands of small model calls on large corpora;
    # global batching keeps the same evidence semantics while making GPU use
    # predictable and substantially faster.
    states: list[dict[str, Any]] = []
    pending_audio: list[np.ndarray] = []
    pending_refs: list[tuple[dict[str, Any], dict[str, Any]]] = []

    def flush() -> None:
        if not pending_audio:
            return
        with torch.no_grad():
            inputs = processor(audio=list(pending_audio), sampling_rate=runner.SAMPLE_RATE,
                               return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            features = runner._embedding_tensor(model.get_audio_features(**inputs))
            features = torch.nn.functional.normalize(features, dim=-1)
            scores = (features @ text_centroids.T).cpu().numpy()
        for (state, window), row_scores in zip(pending_refs, scores):
            state["scored"].append((window, np.asarray(row_scores, dtype=np.float32)))
        pending_audio.clear()
        pending_refs.clear()

    for record in records:
        logical_path = str(record["path"])
        analysis_path = Path(record.get("analysis_path") or logical_path)
        state: dict[str, Any] = {"path": logical_path, "errors": [], "scored": []}
        states.append(state)
        decoded_audio: np.ndarray | None = None
        try:
            decoded_audio = _load_audio_file(analysis_path, runner.SAMPLE_RATE)
        except Exception as exc:
            state["file_error"] = str(exc)
        for window in record.get("windows") or []:
            try:
                if decoded_audio is None:
                    raise ValueError(state.get("file_error", "audio decode failed"))
                audio = _slice_window(decoded_audio, float(window["start_seconds"]),
                                      float(window["end_seconds"]), runner.SAMPLE_RATE)
            except Exception as exc:
                state["errors"].append({
                    "index": window.get("index"),
                    "start_seconds": window.get("start_seconds"),
                    "end_seconds": window.get("end_seconds"),
                    "status": "review", "semantic_label": None,
                    "error": str(exc),
                })
                continue
            pending_audio.append(audio)
            pending_refs.append((state, window))
            if len(pending_audio) >= batch_size:
                flush()
    flush()

    output_rows: list[dict[str, Any]] = []
    for state in states:
        segment_rows = list(state["errors"])
        if state["scored"]:
            score_matrix = np.stack([scores for _, scores in state["scored"]], axis=0)
            for index, (window, row_scores) in enumerate(state["scored"]):
                order = np.argsort(-row_scores)
                best = float(row_scores[order[0]])
                second = float(row_scores[order[1]]) if len(order) > 1 else 0.0
                segment_rows.append({
                    "index": window.get("index", index),
                    "start_seconds": window.get("start_seconds"),
                    "end_seconds": window.get("end_seconds"),
                    "status": "suggest" if best >= min_score and best - second >= min_margin else "review",
                    "semantic_label": None,
                    "suggestion": labels[int(order[0])],
                    "score": best,
                    "margin": best - second,
                    "alternatives": [{"label": labels[int(i)], "score": float(row_scores[int(i)])}
                                     for i in order[:top_k]],
                    "calibration": "uncalibrated_segment_prompt_similarity",
                })
            file_alternatives = _aggregate(labels, score_matrix, top_k)
        else:
            score_matrix = np.empty((0, len(labels)), dtype=np.float32)
            file_alternatives = []
        segment_rows.sort(key=lambda row: (row.get("start_seconds") is None,
                                           row.get("start_seconds") or 0.0))
        output_rows.append({
            "path": state["path"],
            "semantic_label": None,
            "status": "suggest" if any(row.get("status") == "suggest" for row in segment_rows) else "review",
            "file_suggestions": file_alternatives,
            "n_windows": len(segment_rows),
            "n_scored_windows": int(len(score_matrix)),
            "segments": segment_rows,
            "calibration": "uncalibrated_segment_prompt_similarity",
        })
    output_rows.sort(key=lambda row: row["path"])
    header = {
        "record_type": "slo_label_free_segment_classifier_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model": str(model_dir.resolve()),
        "prompt_bank": runner.DEFAULT_PROMPTS,
        "source_manifest": str(manifest.resolve()),
        "n_files": len(output_rows),
        "n_scored_windows": sum(row["n_scored_windows"] for row in output_rows),
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "suggestions_are_uncalibrated": True,
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, sort_keys=True) + "\n")
        for row in output_rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float, default=0.15)
    parser.add_argument("--min-margin", type=float, default=0.03)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    header = run(args.manifest, args.model, args.out, args.device, args.batch_size,
                 args.top_k, args.min_score, args.min_margin, args.limit)
    print(json.dumps({"out": str(args.out), "n_files": header["n_files"],
                      "n_scored_windows": header["n_scored_windows"],
                      "read_only": True}, indent=2))


if __name__ == "__main__":
    main()

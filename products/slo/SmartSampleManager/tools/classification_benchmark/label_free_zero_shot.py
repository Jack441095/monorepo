#!/usr/bin/env python3
"""Label-free, read-only CLAP suggestions for an arbitrary audio directory.

This is deliberately a suggestion/evidence tool, not a training or rename
tool. It discovers audio files recursively, scores them against descriptive
audio-language prompts, and writes a JSONL receipt with top-k alternatives and
an abstention state. No labels are read, created, promoted, or written back to
the source library.

The default prompt bank is intentionally small and acoustic. Users can supply
their own JSON object mapping labels to a list of descriptive prompts. Prompt
scores are not calibrated probabilities; every result remains review-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import soundfile as sf
import torch


VERSION = "label_free_zero_shot_v1"
SAMPLE_RATE = 48_000
MAX_SECONDS = 10
MAX_FILE_BYTES = 1 << 30  # 1 GiB; larger assets are review-only corpus hygiene issues
AUDIO_EXTENSIONS = {".wav", ".aif", ".aiff", ".flac", ".ogg", ".m4a", ".mp3"}

# Concrete descriptions are more stable than bare producer jargon.  These are
# suggestions only; they do not define SLO taxonomy or ground truth.
DEFAULT_PROMPTS: dict[str, list[str]] = {
    "Kick": ["a kick drum", "a bass drum hit", "a deep thumping kick drum"],
    "Snare": ["a snare drum", "a sharp cracking snare", "a snare drum backbeat"],
    "Clap": ["a hand clap", "hands clapping once", "a sharp clap slap"],
    "Hi-Hat": ["a hi-hat cymbal", "a closed hi-hat tick", "a short crisp metallic cymbal"],
    "Crash": ["a crash cymbal", "a bright cymbal crash", "a ringing orchestral cymbal"],
    "Percussion": ["a shaker rattling", "a tambourine shaking", "a conga or bongo hit", "a woodblock click"],
    "Bass": ["a deep sub bass note", "a low frequency bass sound", "an 808 bass note"],
    "Synth": ["a synthesizer tone", "an electronic keyboard sound", "a synthetic musical texture"],
    "Vocal": ["a human singing voice", "a spoken vocal phrase", "a chopped vocal sample"],
    "Impact": ["a heavy cinematic impact", "a large impact hit", "an explosive boom sound"],
    "Riser": ["a rising whoosh building tension", "an ascending sweep", "a build up transition effect"],
    "Ambience": ["a continuous atmospheric soundscape", "a background ambience recording", "an environmental atmosphere"],
}


def discover_audio(root: Path) -> list[Path]:
    """Return deterministic, regular audio files under *root*."""
    if root.is_file():
        return [root.resolve()] if root.suffix.lower() in AUDIO_EXTENSIONS else []
    return sorted(
        p.resolve() for p in root.rglob("*")
        if p.is_file()
        and not p.name.startswith("._")  # macOS AppleDouble metadata sidecar
        and p.suffix.lower() in AUDIO_EXTENSIONS
    )


def load_audio(path: Path) -> np.ndarray:
    """Read mono audio, truncate to the model contract, and resample if needed."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"cannot stat audio file: {exc}") from exc
    if size > MAX_FILE_BYTES:
        raise ValueError(f"file exceeds {MAX_FILE_BYTES // (1 << 20)} MiB decode safety limit")
    # Ask the decoder for only the model window.  Reading the whole container
    # and truncating afterward makes long WAV/MP3 assets consume gigabytes and
    # can stall an otherwise healthy batch.
    info = sf.info(str(path))
    rate = int(info.samplerate)
    max_frames = max(1, int(rate * MAX_SECONDS))
    data, rate = sf.read(str(path), frames=max_frames, dtype="float32", always_2d=False)
    if data.ndim > 1:
        data = np.mean(data, axis=1)
    data = np.asarray(data, dtype=np.float32)
    if not data.size:
        raise ValueError("empty audio stream")
    data = data[:max_frames]
    if rate != SAMPLE_RATE:
        # Avoid librosa's numba-backed cache path, which can fail on Python
        # 3.13 installations without source locators.  SciPy's polyphase
        # resampler is deterministic and has no cache dependency.
        from math import gcd
        from scipy.signal import resample_poly

        rate_i = int(rate)
        g = gcd(SAMPLE_RATE, rate_i)
        data = resample_poly(data, SAMPLE_RATE // g, rate_i // g)
    return np.asarray(data, dtype=np.float32)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _prompt_bank(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return DEFAULT_PROMPTS
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("prompt JSON must be a non-empty object")
    result: dict[str, list[str]] = {}
    for label, prompts in payload.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError("prompt labels must be non-empty strings")
        if not isinstance(prompts, list) or not prompts or not all(isinstance(p, str) and p.strip() for p in prompts):
            raise ValueError(f"prompts for {label!r} must be a non-empty string list")
        result[label.strip()] = [p.strip() for p in prompts]
    return result


def _load_model(model_dir: Path, device: str):
    from transformers import ClapModel, ClapProcessor

    processor = ClapProcessor.from_pretrained(str(model_dir))
    model = ClapModel.from_pretrained(str(model_dir)).to(device).eval()
    return processor, model


def _embedding_tensor(result: Any) -> torch.Tensor:
    """Normalize CLAP output across Transformers versions."""
    # Newer Transformers returns a model-output object; older versions return
    # the embedding tensor directly.  Supporting both keeps the receipt
    # runner portable across the local Apple and remote CUDA environments.
    pooled = getattr(result, "pooler_output", None)
    if pooled is not None:
        return pooled
    embeds = getattr(result, "audio_embeds", None)
    if embeds is not None:
        return embeds
    embeds = getattr(result, "text_embeds", None)
    if embeds is not None:
        return embeds
    if isinstance(result, torch.Tensor):
        return result
    raise TypeError(f"unsupported CLAP embedding output: {type(result)!r}")


def _text_centroids(processor, model, bank: dict[str, list[str]], device: str):
    labels = list(bank)
    prompts = [prompt for label in labels for prompt in bank[label]]
    owners = [i for i, label in enumerate(labels) for _ in bank[label]]
    with torch.no_grad():
        inputs = processor(text=prompts, return_tensors="pt", padding=True)
        inputs = {key: value.to(device) for key, value in inputs.items()}
        features = _embedding_tensor(model.get_text_features(**inputs))
        features = torch.nn.functional.normalize(features, dim=-1)
    centroids = torch.zeros((len(labels), features.shape[-1]), device=device)
    for owner in range(len(labels)):
        centroids[owner] = features[torch.tensor(owners, device=device) == owner].mean(dim=0)
    return labels, torch.nn.functional.normalize(centroids, dim=-1)


def _audio_views(data: np.ndarray, count: int) -> list[np.ndarray]:
    """Return deterministic waveform views for label-free consistency checks."""
    if count not in (1, 3):
        raise ValueError("views must be 1 or 3")
    if count == 1 or len(data) < 2:
        return [data]
    half = max(1, len(data) // 2)
    return [data, data[:half], data[-half:]]


def _row(path: Path, labels: list[str], scores: np.ndarray, top_k: int,
         min_score: float, min_margin: float, error: str | None = None,
         view_scores: np.ndarray | None = None,
         min_view_agreement: float = 0.67) -> dict[str, Any]:
    if error:
        return {"path": str(path), "content_sha256": None, "status": "review",
                "error": error, "semantic_label": None}
    order = np.argsort(-scores)
    top = [{"label": labels[int(i)], "score": float(scores[int(i)])}
           for i in order[: max(1, min(top_k, len(labels)))]]
    best = float(scores[order[0]])
    second = float(scores[order[1]]) if len(order) > 1 else 0.0
    exp = np.exp((scores - float(np.max(scores))) * 20.0)
    probs = exp / max(float(np.sum(exp)), 1e-12)
    entropy = float(-np.sum(probs * np.log(np.maximum(probs, 1e-12))))
    margin = best - second
    view_fields: dict[str, Any] = {}
    view_ok = True
    if view_scores is not None:
        matrix = np.asarray(view_scores, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != len(labels) or matrix.shape[0] < 1:
            raise ValueError("view_scores must have shape (n_views, n_labels)")
        view_preds = np.argmax(matrix, axis=1)
        agreement = float(np.max(np.bincount(view_preds, minlength=len(labels))) / len(view_preds))
        view_std = float(np.mean(np.std(matrix, axis=0)))
        view_fields = {
            "view_count": int(matrix.shape[0]),
            "view_agreement": agreement,
            "view_score_std": view_std,
        }
        view_ok = agreement >= min_view_agreement
    status = "suggest" if best >= min_score and margin >= min_margin and view_ok else "review"
    result = {
        "path": str(path),
        "content_sha256": _sha256(path),
        "status": status,
        "semantic_label": None,
        "zero_shot_suggestion": top[0]["label"],
        "semantic_score": best,
        "margin": margin,
        "entropy": entropy,
        "alternatives": top,
        "calibration": "uncalibrated_prompt_similarity",
    }
    result.update(view_fields)
    return result


def _load_resume_receipt(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    """Load a prior receipt and return rows that completed successfully.

    Resume is intentionally fail-closed: a receipt from another record type or
    one that contains semantic labels/actions is rejected rather than merged.
    Error rows are not considered complete, so a later retry can recover a
    transient decode or filesystem failure.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        raise ValueError(f"resume receipt is empty: {path}")
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise ValueError(f"resume receipt header is invalid: {path}") from exc
    if header.get("record_type") != "slo_label_free_zero_shot_receipt":
        raise ValueError("resume receipt has an incompatible record_type")
    safety = header.get("safety") or {}
    if safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("resume receipt is not a read-only suggestion receipt")
    rows: list[dict[str, Any]] = []
    completed: set[str] = set()
    for line_no, line in enumerate(lines[1:], start=2):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"resume receipt row {line_no} is invalid") from exc
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            raise ValueError(f"resume receipt row {line_no} has no path")
        rows.append(row)
        if row.get("error") is None and row.get("semantic_label") is None:
            completed.add(row["path"])
    return header, rows, completed


def _load_error_paths(path: Path) -> set[str]:
    """Return paths previously proven unreadable, without retrying them."""
    _, rows, _ = _load_resume_receipt(path)
    return {row["path"] for row in rows if row.get("error") is not None}


def run(root: Path, model_dir: Path, out: Path, prompts: Path | None = None,
        device: str | None = None, batch_size: int = 8, top_k: int = 3,
        min_score: float = 0.15, min_margin: float = 0.03,
        limit: int | None = None, resume: bool = False, views: int = 1,
        min_view_agreement: float = 0.67,
        skip_errors_from: Path | None = None,
        embedding_out: Path | None = None) -> dict[str, Any]:
    if views not in (1, 3):
        raise ValueError("views must be 1 or 3")
    bank = _prompt_bank(prompts)
    paths = discover_audio(root)
    if limit is not None:
        paths = paths[: max(0, limit)]
    skipped_error_paths = 0
    if skip_errors_from is not None:
        error_paths = _load_error_paths(skip_errors_from)
        before = len(paths)
        paths = [path for path in paths if str(path) not in error_paths]
        skipped_error_paths = before - len(paths)
    prior_header: dict[str, Any] | None = None
    prior_rows: list[dict[str, Any]] = []
    if resume and out.exists():
        prior_header, prior_rows, completed = _load_resume_receipt(out)
        if embedding_out is not None and completed:
            # A receipt resume can safely reuse scored rows, but vectors are a
            # separate artifact.  Refuse to emit a deceptively incomplete
            # index unless a future version implements vector checkpoint merge.
            raise ValueError("resume with embedding_out is unsupported when scored rows already exist")
        if prior_header.get("prompt_bank") != bank:
            raise ValueError("resume receipt prompt bank does not match this run")
        if int(prior_header.get("views", 1)) != views:
            raise ValueError("resume receipt view count does not match this run")
        prior_model = prior_header.get("model")
        if prior_model and str(Path(prior_model).resolve()) != str(model_dir.resolve()):
            raise ValueError("resume receipt model does not match this run")
        pending_paths = {str(path) for path in paths}
        # A path with an old error is retried; successful rows are skipped.
        completed_pending = completed & pending_paths
        paths = [path for path in paths if str(path) not in completed_pending]
        prior_rows = [row for row in prior_rows if row["path"] not in {str(path) for path in paths}]
    if device:
        resolved_device = device
    elif not paths and prior_header and prior_header.get("device"):
        resolved_device = str(prior_header["device"])
    elif torch.cuda.is_available():
        resolved_device = "cuda"
    elif bool(getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()):
        resolved_device = "mps"
    else:
        resolved_device = "cpu"
    rows: list[dict[str, Any]] = list(prior_rows)
    embedding_paths: list[str] = []
    embedding_vectors: list[np.ndarray] = []
    if paths:
        processor, model = _load_model(model_dir, resolved_device)
        labels, text_centroids = _text_centroids(processor, model, bank, resolved_device)
        for start in range(0, len(paths), max(1, batch_size)):
            chunk = paths[start:start + max(1, batch_size)]
            audio: list[np.ndarray] = []
            valid_paths: list[Path] = []
            for path in chunk:
                try:
                    audio.extend(_audio_views(load_audio(path), views))
                    valid_paths.append(path)
                except Exception as exc:
                    rows.append(_row(path, labels, np.zeros(len(labels)), top_k, min_score, min_margin, str(exc)))
            if not valid_paths:
                continue
            with torch.no_grad():
                inputs = processor(audio=audio, sampling_rate=SAMPLE_RATE,
                                   return_tensors="pt", padding=True)
                inputs = {key: value.to(resolved_device) for key, value in inputs.items()}
                features = _embedding_tensor(model.get_audio_features(**inputs))
                features = torch.nn.functional.normalize(features, dim=-1)
                scores = (features @ text_centroids.T).cpu().numpy()
            if views > 1:
                score_views = scores.reshape(len(valid_paths), views, len(labels))
                aggregate_scores = np.median(score_views, axis=1)
                vector_views = features.reshape(len(valid_paths), views, -1).cpu().numpy()
                aggregate_vectors = np.median(vector_views, axis=1)
                rows.extend(_row(path, labels, aggregate_scores[i], top_k, min_score,
                                 min_margin, view_scores=score_views[i],
                                 min_view_agreement=min_view_agreement)
                            for i, path in enumerate(valid_paths))
            else:
                rows.extend(_row(path, labels, scores[i], top_k, min_score, min_margin)
                            for i, path in enumerate(valid_paths))
                aggregate_vectors = features.cpu().numpy()
            if embedding_out is not None:
                # Median multi-view vectors are re-normalised so cosine search
                # remains well-defined after aggregation.
                aggregate_vectors = np.asarray(aggregate_vectors, dtype=np.float32)
                norms = np.linalg.norm(aggregate_vectors, axis=1, keepdims=True)
                aggregate_vectors = aggregate_vectors / np.maximum(norms, 1e-12)
                embedding_paths.extend(str(path) for path in valid_paths)
                embedding_vectors.extend(aggregate_vectors)
    rows.sort(key=lambda row: row["path"])
    header = {
        "record_type": "slo_label_free_zero_shot_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model": str(model_dir.resolve()),
        "prompt_bank": {label: prompts for label, prompts in bank.items()},
        "n_files": len(rows),
        "device": resolved_device,
        "views": views,
        "min_view_agreement": min_view_agreement,
        "skipped_error_paths": skipped_error_paths,
        "resumed": bool(resume and prior_header is not None),
        "safety": {
            "read_only": True,
            "semantic_labels_created": False,
            "ground_truth_read": False,
            "training_data_created": False,
            "rename_actions": False,
            "source_audio_modified": False,
            "suggestions_are_uncalibrated": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, sort_keys=True) + "\n")
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    if embedding_out is not None and embedding_vectors:
        embedding_out.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            embedding_out,
            record_type=np.array("slo_label_free_audio_embedding_index"),
            schema_version=np.array("1.0.0"),
            method_version=np.array("label_free_audio_embeddings_v1"),
            model=np.array(str(model_dir.resolve())),
            views=np.array(views, dtype=np.int64),
            paths=np.asarray(embedding_paths),
            embeddings=np.asarray(embedding_vectors, dtype=np.float32),
            safety=np.array(json.dumps({
                "read_only": True,
                "semantic_labels_created": False,
                "ground_truth_read": False,
                "rename_actions": False,
                "source_audio_modified": False,
            }, sort_keys=True)),
        )
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="audio file or directory")
    parser.add_argument("--model", type=Path, required=True, help="local CLAP model directory")
    parser.add_argument("--out", type=Path, required=True, help="JSONL receipt path")
    parser.add_argument("--prompts", type=Path, help="optional JSON label -> prompt list")
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"])
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.15)
    parser.add_argument("--min-margin", type=float, default=0.03)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--views", type=int, choices=[1, 3], default=1,
                        help="waveform views per file: 1 or full/early/late (3)")
    parser.add_argument("--min-view-agreement", type=float, default=0.67)
    parser.add_argument("--skip-errors-from", type=Path,
                        help="receipt whose prior decode-error paths should be skipped")
    parser.add_argument("--embedding-out", type=Path,
                        help="optional NPZ path for normalized audio vectors and paths")
    parser.add_argument("--resume", action="store_true",
                        help="skip successful rows already present in --out")
    args = parser.parse_args()
    header = run(args.input, args.model, args.out, args.prompts, args.device,
                 args.batch_size, args.top_k, args.min_score, args.min_margin,
                 args.limit, args.resume, args.views, args.min_view_agreement,
                 args.skip_errors_from, args.embedding_out)
    result = {"out": str(args.out), "n_files": header["n_files"], "read_only": True}
    if args.embedding_out is not None:
        result["embedding_out"] = str(args.embedding_out)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

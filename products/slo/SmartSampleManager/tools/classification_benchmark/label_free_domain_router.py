#!/usr/bin/env python3
"""Route arbitrary audio to specialist branches without creating labels.

The router is deliberately coarse and multi-view. It emits an uncalibrated
domain suggestion (or ``review``) that can select downstream experts; it does
not claim a semantic ground truth, rename files, or modify source audio.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch


VERSION = "label_free_domain_router_v1"
DOMAIN_PROMPTS: dict[str, list[str]] = {
    "music_sample": ["a music sample for a producer", "an instrumental music recording", "a drum or synth sample"],
    "speech_voice": ["human speech or spoken voice", "a person talking", "a spoken language recording"],
    "environment_sfx": ["an environmental sound effect", "a foley or everyday sound recording", "a cinematic sound effect"],
    "animal_bioacoustic": ["an animal or bird sound", "a wildlife recording", "a bioacoustic field recording"],
    "mechanical_industrial": ["a machine or mechanical recording", "an industrial equipment sound", "a motor or engine sound"],
    "ambience_field": ["a continuous ambience or soundscape", "a field recording atmosphere", "background environmental ambience"],
    "unknown_or_mixture": ["an unusual mixed or unidentifiable audio recording", "audio that does not fit a known sound category", "a complex mixture of sounds"],
}


def _prompt_bank(path: Path | None) -> dict[str, list[str]]:
    if path is None:
        return {domain: list(prompts) for domain, prompts in DOMAIN_PROMPTS.items()}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("domain prompt bank must be a non-empty object")
    bank: dict[str, list[str]] = {}
    for domain, prompts in payload.items():
        if (not isinstance(domain, str) or not domain.strip()
                or not isinstance(prompts, list) or not prompts
                or not all(isinstance(prompt, str) and prompt.strip() for prompt in prompts)):
            raise ValueError("each domain must contain a non-empty prompt list")
        bank[domain.strip()] = [prompt.strip() for prompt in prompts]
    return bank


def _runner():
    path = Path(__file__).with_name("label_free_zero_shot.py")
    spec = importlib.util.spec_from_file_location("label_free_zero_shot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load label-free runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _row(path: Path, labels: list[str], scores: np.ndarray, top_k: int,
         min_score: float, min_margin: float,
         view_scores: np.ndarray | None, min_view_agreement: float,
         error: str | None = None, runner_module: Any | None = None) -> dict[str, Any]:
    runner = runner_module or _runner()
    result = runner._row(path, labels, scores, top_k, min_score, min_margin,
                         view_scores=view_scores,
                         min_view_agreement=min_view_agreement,
                         error=error)
    # Preserve the generic evidence shape while making the routing decision
    # explicit for downstream specialist selection.
    result["domain_suggestion"] = result.pop("zero_shot_suggestion", None)
    result["domain_alternatives"] = result.pop("alternatives", [])
    result["domain_score"] = result.pop("semantic_score", None)
    result["domain_margin"] = result.pop("margin", None)
    result["calibration"] = "uncalibrated_domain_prompt_similarity"
    return result


def run(root: Path, model_dir: Path, out: Path, device: str = "cpu",
        batch_size: int = 8, top_k: int = 3, min_score: float = 0.15,
        min_margin: float = 0.03, views: int = 3,
        min_view_agreement: float = 0.67,
        limit: int | None = None, prompts: Path | None = None) -> dict[str, Any]:
    if views not in (1, 3):
        raise ValueError("views must be 1 or 3")
    runner = _runner()
    domain_prompts = _prompt_bank(prompts)
    paths = runner.discover_audio(root)
    if limit is not None:
        paths = paths[:max(0, limit)]
    processor, model = runner._load_model(model_dir, device)
    labels, text_centroids = runner._text_centroids(processor, model, domain_prompts, device)
    rows: list[dict[str, Any]] = []
    for start in range(0, len(paths), max(1, batch_size)):
        chunk = paths[start:start + max(1, batch_size)]
        audio: list[np.ndarray] = []
        valid: list[Path] = []
        for path in chunk:
            try:
                audio.extend(runner._audio_views(runner.load_audio(path), views))
                valid.append(path)
            except Exception as exc:
                rows.append(_row(path, labels, np.zeros(len(labels)), top_k,
                                 min_score, min_margin, None,
                                 min_view_agreement, str(exc), runner))
        if not valid:
            continue
        with torch.no_grad():
            inputs = processor(audio=audio, sampling_rate=runner.SAMPLE_RATE,
                               return_tensors="pt", padding=True)
            inputs = {key: value.to(device) for key, value in inputs.items()}
            features = runner._embedding_tensor(model.get_audio_features(**inputs))
            features = torch.nn.functional.normalize(features, dim=-1)
            scores = (features @ text_centroids.T).cpu().numpy()
        if views > 1:
            matrix = scores.reshape(len(valid), views, len(labels))
            aggregate = np.median(matrix, axis=1)
            rows.extend(_row(path, labels, aggregate[i], top_k, min_score,
                             min_margin, matrix[i], min_view_agreement,
                             runner_module=runner)
                        for i, path in enumerate(valid))
        else:
            rows.extend(_row(path, labels, scores[i], top_k, min_score,
                             min_margin, None, min_view_agreement,
                             runner_module=runner)
                        for i, path in enumerate(valid))
    rows.sort(key=lambda row: row["path"])
    header = {
        "record_type": "slo_label_free_domain_router_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model": str(model_dir.resolve()),
        "domain_prompt_bank": domain_prompts,
        "prompt_bank_source": str(prompts.resolve()) if prompts else "built_in_v1",
        "n_files": len(rows),
        "device": device,
        "views": views,
        "min_view_agreement": min_view_agreement,
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
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.15)
    parser.add_argument("--min-margin", type=float, default=0.03)
    parser.add_argument("--views", type=int, choices=[1, 3], default=3)
    parser.add_argument("--min-view-agreement", type=float, default=0.67)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prompts", type=Path,
                        help="optional JSON domain->prompt-list bank for controlled tuning")
    args = parser.parse_args()
    header = run(args.input, args.model, args.out, args.device, args.batch_size,
                 args.top_k, args.min_score, args.min_margin, args.views,
                 args.min_view_agreement, args.limit, args.prompts)
    print(json.dumps({"out": str(args.out), "n_files": header["n_files"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()

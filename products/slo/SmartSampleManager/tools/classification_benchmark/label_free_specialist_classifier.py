#!/usr/bin/env python3
"""Dispatch routed audio to configurable, label-free specialist prompt banks.

This is an open-world evidence runner.  It consumes a domain-router receipt,
selects a specialist prompt bank, and emits review-only suggestions.  It does
not create labels, infer ground truth, rename files, or modify source audio.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np
import torch


VERSION = "label_free_specialist_classifier_v1"
DEFAULT_BANK = Path(__file__).with_name("open_world_specialist_prompt_banks_v1.json")


def _runner():
    path = Path(__file__).with_name("label_free_zero_shot.py")
    spec = importlib.util.spec_from_file_location("label_free_zero_shot", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load label-free runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_bank(path: Path) -> dict[str, dict[str, list[str]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload:
        raise ValueError("specialist prompt bank must be a non-empty object")
    bank: dict[str, dict[str, list[str]]] = {}
    for domain, labels in payload.items():
        if not isinstance(domain, str) or not domain.strip() or not isinstance(labels, dict) or not labels:
            raise ValueError("each specialist domain must contain a non-empty label object")
        parsed: dict[str, list[str]] = {}
        for label, prompts in labels.items():
            if not isinstance(label, str) or not label.strip() or not isinstance(prompts, list) \
                    or not prompts or not all(isinstance(prompt, str) and prompt.strip() for prompt in prompts):
                raise ValueError(f"invalid prompts for {domain}/{label}")
            parsed[label.strip()] = [prompt.strip() for prompt in prompts]
        bank[domain.strip()] = parsed
    return bank


def _read_router(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not lines:
        raise ValueError("domain router receipt is empty")
    header = json.loads(lines[0])
    if header.get("record_type") != "slo_label_free_domain_router_receipt":
        raise ValueError("input is not a domain-router receipt")
    safety = header.get("safety") or {}
    if not safety.get("read_only") or safety.get("semantic_labels_created") or safety.get("rename_actions"):
        raise ValueError("domain-router receipt is not read-only")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in lines[1:]:
        row = json.loads(line)
        if not isinstance(row, dict) or not isinstance(row.get("path"), str) or row["path"] in seen:
            raise ValueError("domain-router rows must have unique paths")
        if row.get("semantic_label") is not None:
            raise ValueError("domain-router receipt contains semantic labels")
        seen.add(row["path"])
        rows.append(row)
    return header, rows


def _undispatched(path: str, domain: str | None, reason: str) -> dict[str, Any]:
    return {
        "path": path,
        "domain_suggestion": domain,
        "specialist_status": "not_dispatched",
        "status": "review",
        "semantic_label": None,
        "alternatives": [],
        "reason": reason,
        "calibration": "uncalibrated_specialist_prompt_similarity",
    }


def run(router: Path, model_dir: Path, out: Path, prompts: Path = DEFAULT_BANK,
        device: str = "cpu", batch_size: int = 8, top_k: int = 3,
        min_score: float = 0.15, min_margin: float = 0.03,
        views: int = 3, min_view_agreement: float = 0.67,
        limit: int | None = None) -> dict[str, Any]:
    if views not in (1, 3) or batch_size < 1 or top_k < 1:
        raise ValueError("invalid specialist parameters")
    source, source_rows = _read_router(router)
    bank = _load_bank(prompts)
    rows_in = source_rows if limit is None else source_rows[:max(0, limit)]
    runner = _runner()
    processor, model = runner._load_model(model_dir, device)
    # Precompute text centroids once per routed domain.  The generic CLAP model
    # is shared; only the prompt bank changes at dispatch time.
    domain_centroids: dict[str, tuple[list[str], torch.Tensor]] = {}
    for domain in sorted({str(row.get("domain_suggestion")) for row in rows_in
                          if row.get("domain_suggestion") in bank}):
        labels, centroids = runner._text_centroids(processor, model, bank[domain], device)
        domain_centroids[domain] = (labels, centroids)

    output: dict[str, dict[str, Any]] = {}
    for row in rows_in:
        path = str(row["path"])
        domain = row.get("domain_suggestion")
        if domain not in domain_centroids:
            reason = "no specialist prompt bank for route" if domain in bank else "route is unknown or abstained"
            output[path] = _undispatched(path, str(domain) if domain else None, reason)

    # Batch by domain so each model call uses one prompt dimension and the
    # output can still be merged deterministically by logical path.
    for domain, (_, _) in domain_centroids.items():
        domain_rows = [row for row in rows_in if row.get("domain_suggestion") == domain]
        labels, text_centroids = domain_centroids[domain]
        for start in range(0, len(domain_rows), batch_size):
            chunk = domain_rows[start:start + batch_size]
            audio: list[np.ndarray] = []
            valid: list[dict[str, Any]] = []
            view_counts: list[int] = []
            for source_row in chunk:
                try:
                    views_audio = runner._audio_views(runner.load_audio(Path(source_row["path"])), views)
                    audio.extend(views_audio)
                    valid.append(source_row)
                    view_counts.append(len(views_audio))
                except Exception as exc:
                    output[str(source_row["path"])] = _undispatched(
                        str(source_row["path"]), domain, f"specialist decode error: {exc}")
            if not valid:
                continue
            with torch.no_grad():
                inputs = processor(audio=audio, sampling_rate=runner.SAMPLE_RATE,
                                   return_tensors="pt", padding=True)
                inputs = {key: value.to(device) for key, value in inputs.items()}
                features = runner._embedding_tensor(model.get_audio_features(**inputs))
                features = torch.nn.functional.normalize(features, dim=-1)
                scores = (features @ text_centroids.T).cpu().numpy()
            offset = 0
            for source_row, view_count in zip(valid, view_counts):
                matrix = scores[offset:offset + view_count]
                offset += view_count
                aggregate = np.median(matrix, axis=0)
                result = runner._row(Path(source_row["path"]), labels, aggregate, top_k,
                                     min_score, min_margin,
                                     view_scores=matrix if views > 1 else None,
                                     min_view_agreement=min_view_agreement)
                result["domain_suggestion"] = domain
                result["specialist_suggestion"] = result.pop("zero_shot_suggestion", None)
                result["specialist_score"] = result.pop("semantic_score", None)
                result["specialist_alternatives"] = result.pop("alternatives", [])
                result["specialist_status"] = "scored"
                result["calibration"] = "uncalibrated_specialist_prompt_similarity"
                output[result["path"]] = result

    ordered = [output[str(row["path"])] for row in rows_in]
    ordered.sort(key=lambda row: row["path"])
    header = {
        "record_type": "slo_label_free_specialist_receipt",
        "schema_version": "1.0.0",
        "method_version": VERSION,
        "model": str(model_dir.resolve()),
        "source_router": str(router.resolve()),
        "specialist_prompt_banks": bank,
        "n_files": len(ordered),
        "n_scored": sum(row.get("specialist_status") == "scored" for row in ordered),
        "n_undispatched": sum(row.get("specialist_status") != "scored" for row in ordered),
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
            "human_approval_required": True,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(header, sort_keys=True) + "\n")
        for row in ordered:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    return header


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, default=DEFAULT_BANK)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", choices=["cpu", "cuda", "mps"], default="cpu")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--min-score", type=float, default=0.15)
    parser.add_argument("--min-margin", type=float, default=0.03)
    parser.add_argument("--views", type=int, choices=[1, 3], default=3)
    parser.add_argument("--min-view-agreement", type=float, default=0.67)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    header = run(args.router, args.model, args.out, args.prompts, args.device,
                 args.batch_size, args.top_k, args.min_score, args.min_margin,
                 args.views, args.min_view_agreement, args.limit)
    print(json.dumps({"out": str(args.out), "n_files": header["n_files"],
                      "n_scored": header["n_scored"], "read_only": True}, indent=2))


if __name__ == "__main__":
    main()

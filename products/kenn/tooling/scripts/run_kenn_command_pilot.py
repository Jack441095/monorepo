#!/usr/bin/env python3
"""Run the KENN command-model pilot as one reproducible, safe pipeline.

The default mode builds the clean synthetic corpus, audits it, and performs a
read-only model/device preflight.  ``--run`` is required to create adapter
weights, and the output directory must not already contain pilot artifacts.
This script never opens Ableton or sends OSC.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))
sys.path.insert(0, str(REPO_ROOT / "tooling" / "scripts"))

DEFAULT_WORKDIR = Path("/tmp/kenn-command-pilot")
SCHEMA = "kenn.ableton_command_pilot_run.v1"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _model_contract_gate(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Require every adapter holdout case to pass before calling the pilot usable."""
    result = evaluation.get("adapter_result") if isinstance(evaluation.get("adapter_result"), dict) else evaluation
    counts = result.get("counts") if isinstance(result, dict) else None
    blockers: list[str] = []
    if not isinstance(counts, dict):
        blockers.append("adapter evaluation did not return contract counts")
    else:
        total = int(counts.get("total", 0) or 0)
        accepted = int(counts.get("accepted_schema", 0) or 0)
        matches = int(counts.get("comparison_match", 0) or 0)
        if total <= 0:
            blockers.append("adapter evaluation ran no holdout cases")
        if accepted != total:
            blockers.append(f"{total - accepted} holdout case(s) were not validator-accepted")
        if matches != total:
            blockers.append(f"{total - matches} holdout case(s) did not match deterministic interpretation")
        if int(counts.get("deterministic_contract_failures", 0) or 0):
            blockers.append("deterministic holdout contract failed")
    from kenn.core.live_llm_promotion import PROMOTION_THRESHOLDS

    return {
        "model_contract_passed": not blockers,
        "live_activation_allowed": False,
        "blockers": blockers,
        "promotion_thresholds": PROMOTION_THRESHOLDS,
        "promotion_stage": "shadow",
        "required_before_live_activation": [
            "complete model-contract holdout acceptance and deterministic agreement",
            "independent human review of representative commands",
            "real-Live qualification on the guarded proposal/readback path",
        ],
    }


def run_pilot(
    *,
    workdir: Path,
    variants: int,
    scenarios: int,
    base_model: str,
    epochs: int,
    batch_size: int,
    max_length: int,
    learning_rate: float,
    seed: int,
    device: str,
    allow_download: bool,
    run_training: bool,
) -> dict[str, Any]:
    from audit_kenn_command_corpus import audit_rows
    from build_kenn_command_corpus import build_rows
    from build_kenn_command_training import assert_no_holdout_overlap
    from train_kenn_command_lora import dry_run, train

    workdir = workdir.expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    expected = (
        workdir / "corpus.jsonl",
        workdir / "corpus-audit.json",
        workdir / "dry-run.json",
        workdir / "pilot-manifest.json",
    )
    if run_training:
        expected += (workdir / "adapter", workdir / "evaluation.json")
    collisions = [path for path in expected if path.exists()]
    if collisions:
        raise FileExistsError("Refusing to overwrite existing pilot artifacts: " + ", ".join(str(path) for path in collisions))

    rows = build_rows(variants=variants, scenarios=scenarios)
    assert_no_holdout_overlap(rows)
    corpus_path = workdir / "corpus.jsonl"
    corpus_path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows), encoding="utf-8")

    audit = audit_rows(rows)
    audit_path = workdir / "corpus-audit.json"
    _write_json(audit_path, audit)
    if audit.get("status") == "invalid" or audit.get("validation_errors"):
        raise ValueError("Corpus audit failed; refusing to continue to model preflight.")

    adapter_path = workdir / "adapter"
    preflight = dry_run(
        data_path=corpus_path,
        base_model=base_model,
        output=adapter_path,
        allow_download=allow_download,
        device_name=device,
    )
    _write_json(workdir / "dry-run.json", preflight)
    if preflight.get("status") != "ready":
        manifest = {
            "schema": SCHEMA,
            "status": "preflight_blocked",
            "training_run": False,
            "workdir": str(workdir),
            "corpus": str(corpus_path),
            "audit": str(audit_path),
            "dry_run": str(workdir / "dry-run.json"),
            "records": len(rows),
            "variants": variants,
            "scenarios": scenarios,
            "base_model": base_model,
            "device": device,
            "audit_summary": {
                "unique_queries": audit.get("unique_queries"),
                "unique_labels": audit.get("unique_labels"),
                "mechanical_variant_ratio": audit.get("mechanical_variant_ratio"),
                "parser_contract": audit.get("parser_contract"),
                "holdout_protection": audit.get("holdout_protection"),
            },
        }
        _write_json(workdir / "pilot-manifest.json", manifest)
        return manifest

    training_manifest: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    if run_training:
        training_manifest = train(
            data_path=corpus_path,
            base_model=base_model,
            output=adapter_path,
            epochs=epochs,
            max_length=max_length,
            learning_rate=learning_rate,
            allow_download=allow_download,
            seed=seed,
            batch_size=batch_size,
            device_name=device,
        )
        from evaluate_kenn_command_lora import evaluate

        evaluation = evaluate(
            adapter=adapter_path,
            base_model=base_model,
            cases_path=REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "ableton_llm_shadow_holdout.json",
            limit=0,
            max_new_tokens=256,
            device_name=device,
            allow_download=allow_download,
            compare_base=True,
        )
        _write_json(workdir / "evaluation.json", evaluation)

    model_contract_gate = _model_contract_gate(evaluation) if evaluation is not None else None
    training_status = "trained_and_evaluated" if model_contract_gate and model_contract_gate["model_contract_passed"] else "trained_but_contract_failed"

    manifest = {
        "schema": SCHEMA,
        "status": training_status if run_training else "preflight_ready",
        "training_run": run_training,
        "workdir": str(workdir),
        "corpus": str(corpus_path),
        "audit": str(audit_path),
        "dry_run": str(workdir / "dry-run.json"),
        "adapter": str(adapter_path) if run_training else None,
        "evaluation": str(workdir / "evaluation.json") if run_training else None,
        "records": len(rows),
        "variants": variants,
        "scenarios": scenarios,
        "base_model": base_model,
        "device": device,
        "training_manifest": training_manifest,
        "model_contract_gate": model_contract_gate,
        "audit_summary": {
            "unique_queries": audit.get("unique_queries"),
            "unique_labels": audit.get("unique_labels"),
            "mechanical_variant_ratio": audit.get("mechanical_variant_ratio"),
            "parser_contract": audit.get("parser_contract"),
            "holdout_protection": audit.get("holdout_protection"),
        },
    }
    _write_json(workdir / "pilot-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workdir", type=Path, default=DEFAULT_WORKDIR)
    parser.add_argument("--variants", type=int, default=28)
    parser.add_argument("--scenarios", type=int, default=4)
    parser.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--learning-rate", type=float, default=2e-4)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--run", action="store_true", help="Actually train and evaluate; default performs preflight only")
    args = parser.parse_args()
    result = run_pilot(
        workdir=args.workdir,
        variants=args.variants,
        scenarios=args.scenarios,
        base_model=args.base_model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        max_length=args.max_length,
        learning_rate=args.learning_rate,
        seed=args.seed,
        device=args.device,
        allow_download=args.allow_download,
        run_training=args.run,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["status"] in {"preflight_ready", "trained_and_evaluated", "preflight_blocked"} else 2


if __name__ == "__main__":
    raise SystemExit(main())

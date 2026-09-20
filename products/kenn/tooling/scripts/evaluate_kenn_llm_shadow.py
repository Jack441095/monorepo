#!/usr/bin/env python3
"""Evaluate an Ollama command model without touching Ableton.

This runner uses a fixed, held-out-style Live snapshot and only calls KENN's
plan-generation and validation boundary.  It never creates a proposal, opens
the OSC socket, or performs a Live write.  Run it with a small ``--limit``
first because local-model latency is part of the result.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "ableton_llm_shadow_holdout.json"
SCHEMA = "kenn.ableton_llm_shadow_evaluation.v1"
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))


def _fixture_snapshot() -> dict[str, Any]:
    snapshot = {
        "status": "connected",
        "tracks": [
            {"index": 0, "name": "Kick", "devices": []},
            {"index": 1, "name": "Bass", "devices": []},
            {"index": 2, "name": "Vocal", "devices": [{"index": 0, "name": "EQ Eight"}, {"index": 1, "name": "Compressor"}]},
            {"index": 3, "name": "4-Audio", "devices": [{"index": 0, "name": "EQ Eight"}, {"index": 1, "name": "Glue Compressor"}, {"index": 2, "name": "Saturator"}]},
            {"index": 4, "name": "Drum Bus", "devices": []},
        ],
    }
    # Keep the offline evaluator faithful to production LLM context: the
    # planner sees bounded read-only parameter evidence for the target-track
    # devices, and the validator can enforce exact sparse name/index pairs.
    snapshot["planner_capabilities"] = {
        "schema": "kenn.ableton_planner_capabilities.v1",
        "status": "read_only",
        "entries": [
            {
                "track_index": 2,
                "track_name": "Vocal",
                "device_index": 0,
                "device_name": "EQ Eight",
                "parameters": [
                    {"index": 11, "name": "1 Frequency A", "value": 0.4, "min": 0.0, "max": 1.0},
                    {"index": 12, "name": "1 Gain A", "value": 0.0, "min": -15.0, "max": 15.0},
                ],
            },
            {
                "track_index": 2,
                "track_name": "Vocal",
                "device_index": 1,
                "device_name": "Compressor",
                "parameters": [
                    {"index": 0, "name": "Threshold", "value": -12.0, "min": -60.0, "max": 0.0},
                    {"index": 1, "name": "Ratio", "value": 4.0, "min": 1.0, "max": 20.0},
                ],
            },
            {
                "track_index": 3,
                "track_name": "4-Audio",
                "device_index": 0,
                "device_name": "EQ Eight",
                "parameters": [
                    {"index": 11, "name": "1 Frequency A", "value": 0.4, "min": 0.0, "max": 1.0},
                    {"index": 12, "name": "1 Gain A", "value": 0.0, "min": -15.0, "max": 15.0},
                ],
            },
            {
                "track_index": 3,
                "track_name": "4-Audio",
                "device_index": 1,
                "device_name": "Glue Compressor",
                "parameters": [
                    {"index": 0, "name": "Attack", "value": 3.0, "min": 0.0, "max": 6.0},
                ],
            },
            {
                "track_index": 3,
                "track_name": "4-Audio",
                "device_index": 2,
                "device_name": "Saturator",
                "parameters": [
                    {"index": 0, "name": "Drive", "value": 0.5, "min": 0.0, "max": 1.0},
                ],
            },
        ],
        "limitations": ["Read-only fixture evidence; no proposal or Live operation is available."],
    }
    return snapshot


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError(f"Expected a JSON list of case objects in {path}")
    return payload


def _failure_kind(status: str, error: str) -> str | None:
    """Classify a rejected model result for targeted training diagnostics."""
    if status == "accepted":
        return None
    message = str(error or "").lower()
    if "schema" in message or "json" in message:
        return "malformed_or_wrong_schema"
    if "unsupported fields" in message or "hidden" in message or "nested steps" in message or "exact" in message:
        return "validator_contract_rejection"
    if "range" in message or "unit" in message:
        return "capability_rejection"
    return "unavailable_or_other"


def _model_contract_gate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Report whether a shadow model is contract-consistent without enabling Live."""
    blockers: list[str] = []
    if not results:
        blockers.append("no evaluation cases were run")
    for item in results:
        case_id = str(item.get("id", "unknown"))
        if item.get("llm_status") != "accepted":
            blockers.append(f"{case_id}: model plan was not validator-accepted")
            continue
        comparison = item.get("comparison")
        if not isinstance(comparison, dict) or comparison.get("status") != "match":
            blockers.append(f"{case_id}: model plan disagreed with deterministic interpretation")
        if not item.get("deterministic_contract_ok", False):
            blockers.append(f"{case_id}: deterministic fixture contract failed")
    return {
        "model_contract_passed": not blockers,
        "live_activation_allowed": False,
        "blockers": blockers,
        "required_before_live_activation": [
            "complete model-contract shadow evaluation with every case accepted and matching",
            "independent human review of representative commands",
            "real-Live qualification on the guarded proposal/readback path",
        ],
    }


def evaluate(*, model: str, cases_path: Path = DEFAULT_CASES, limit: int = 0) -> dict[str, Any]:
    # Set these before importing the adapter: its configuration is environment
    # driven, and shadow mode must be explicit in every evaluation process.
    os.environ["AUDIO_TOO_LLM_ENABLED"] = "1"
    os.environ["AUDIO_TOO_LLM_PROVIDER"] = "ollama"
    os.environ["AUDIO_TOO_LLM_MODEL"] = model
    os.environ["KENN_LIVE_LLM_ENABLED"] = "1"
    os.environ["KENN_LIVE_LLM_MODE"] = "shadow"
    os.environ.setdefault("AUDIO_TOO_LLM_TIMEOUT", "60")
    os.environ.setdefault("KENN_LLM_CACHE", "0")

    from kenn.core.live_command import _generate_llm_plan, compare_llm_plan
    from kenn.core.live_intent import parse_request

    cases = _load_cases(cases_path)
    if limit > 0:
        cases = cases[:limit]
    snapshot = _fixture_snapshot()
    results: list[dict[str, Any]] = []
    for case in cases:
        query = str(case.get("query", ""))
        deterministic = parse_request(query, snapshot)
        expected_action = case.get("expected_action")
        expected_clarification = bool(case.get("expects_clarification", False))
        deterministic_needs_clarification = bool(deterministic.get("missing_fields") or deterministic.get("ambiguity"))
        started = time.perf_counter()
        plan, metadata = _generate_llm_plan(query, snapshot)
        elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
        comparison = compare_llm_plan(plan, deterministic) if plan is not None else None
        usage = metadata.get("usage") if isinstance(metadata, dict) else None
        llm_status = metadata.get("status") if isinstance(metadata, dict) else "unknown"
        error = metadata.get("reason", "") if isinstance(metadata, dict) else ""
        results.append({
            "id": str(case.get("id", "")),
            "category": str(case.get("category", "")),
            "query": query,
            "deterministic_action": deterministic.get("action"),
            "deterministic_needs_clarification": deterministic_needs_clarification,
            "expected_action": expected_action,
            "expected_clarification": expected_clarification,
            "deterministic_contract_ok": deterministic.get("action") == expected_action and deterministic_needs_clarification == expected_clarification,
            "llm_status": llm_status,
            "plan": plan,
            "comparison": comparison,
            "latency_ms": usage.get("latency_ms", elapsed_ms) if isinstance(usage, dict) else elapsed_ms,
            "error": error,
            "failure_kind": _failure_kind(llm_status, error),
        })

    accepted = [item for item in results if item["llm_status"] == "accepted"]
    comparisons = [item["comparison"] for item in accepted if isinstance(item["comparison"], dict)]
    latencies = [float(item["latency_ms"]) for item in results if isinstance(item.get("latency_ms"), (int, float))]
    counts = {
        "total": len(results),
        "deterministic_contract_failures": sum(not item["deterministic_contract_ok"] for item in results),
        "accepted_schema": len(accepted),
        "rejected_or_unavailable": len(results) - len(accepted),
        "comparison_match": sum(item.get("status") == "match" for item in comparisons),
        "comparison_mismatch": sum(item.get("status") == "mismatch" for item in comparisons),
        "comparison_incomplete": sum(item.get("status") == "incomplete" for item in comparisons),
        "failure_kinds": {
            kind: sum(item.get("failure_kind") == kind for item in results)
            for kind in sorted({item.get("failure_kind") for item in results if item.get("failure_kind")})
        },
    }
    model_contract_gate = _model_contract_gate(results)
    return {
        "schema": SCHEMA,
        "evidence_kind": "local_model_shadow_only",
        "model": model,
        "provider": "ollama",
        "cases_path": str(cases_path),
        "snapshot_tracks": len(snapshot["tracks"]),
        "counts": counts,
        "model_contract_gate": model_contract_gate,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3) if latencies else None,
            "median": round(statistics.median(latencies), 3) if latencies else None,
            "max": round(max(latencies), 3) if latencies else None,
        },
        "results": results,
        "limitations": [
            "This uses a deterministic fixture, not the current Ableton session.",
            "No proposal, OSC request, confirmation, or Live mutation is performed.",
            "Comparison agreement does not prove human language quality or production usefulness.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="qwen2.5:0.5b", help="Installed Ollama model name")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES, help="JSON holdout case file")
    parser.add_argument("--limit", type=int, default=0, help="Evaluate only the first N cases")
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    args = parser.parse_args()
    result = evaluate(model=args.model, cases_path=args.cases.expanduser().resolve(), limit=args.limit)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        args.output.expanduser().resolve().write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Exercise delivery reporting and offline review with five declared outcomes and no provider calls."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
OUTPUT = Path(__file__).parent
TOOLS = ROOT / "products/kenn/tooling/scripts"
PRIVATE = Path("/tmp/kenn-stage23-review-private")
spec = importlib.util.spec_from_file_location("latency_capture", TOOLS / "measure_chat_latency.py")
latency = importlib.util.module_from_spec(spec)
spec.loader.exec_module(latency)

# These exposed, authored fixtures test counting and blinding. They cannot enter a sealed or blind dataset.
CASES = [
    {"id": "fixture-a", "question": "What does attack mean?", "category": "knowledge-boundary", "split": "regression"},
    {"id": "fixture-b", "question": "Which compressor did I select?", "category": "target-binding", "split": "regression"},
    {"id": "fixture-c", "question": "What is the release set to now?", "category": "target-binding", "split": "regression"},
    {"id": "fixture-d", "question": "What did the analysis find?", "category": "analysis-honesty", "split": "regression"},
    {"id": "fixture-e", "question": "What does ratio mean?", "category": "knowledge-boundary", "split": "regression"},
]
OUTCOMES = dict(zip((case["question"] for case in CASES), ("accepted", "rejected", "busy", "timeout", "not_attempted")))


def response(question, **kwargs):
    """Return fixture metadata only; importing this runner never invokes an answer provider."""
    outcome = OUTCOMES[question]
    answer = "Synthetic explanation for delivery-contract testing." if outcome == "accepted" else ""
    return ({"answer": answer, "delivery_outcome": outcome, "sources": [],
             "fallback_reason": None if outcome == "accepted" else f"Synthetic {outcome} fixture",
             "generation_validation": {"attempted": outcome in {"accepted", "rejected"},
                                       "accepted": outcome == "accepted", "warnings": []}}, 0, None)


def main():
    """Write separate route/cache/repeat reports and a private capture for the offline review CLI."""
    reports = []
    manifest = {"evidence_kind": "synthetic", "model_run": False, "live_writes": 0,
                "cache_operation": "stubbed; neither client nor server cache changed",
                "supervised_live_open": None, "model_digest": None, "resolved_prompt_sha256": None,
                "index_sha256": None, "corpus_sha256": None, "hardware": None}
    # A cold-cache fixture must not clear another developer's on-disk answer cache.
    with patch.object(latency, "_ask", lambda _engine, question, **kwargs: response(question, **kwargs)), \
         patch.object(latency, "_ask_http", response), patch.object(latency, "_drop_semantic_cache", lambda: None), \
         patch.dict(os.environ, {"KENN_LLM_MODEL": ""}):
        for surface in ("stream", "payload", "foreground", "background"):
            for cache in ("cold", "warm"):
                for repeat in range(1, 4):
                    report = latency.measure(CASES, surface=surface, cache_condition=cache,
                                             endpoint="synthetic://unused" if surface in {"foreground", "background"} else None,
                                             manifest=manifest)
                    report.update(evidence_kind="synthetic", repeat=repeat, qualification="unqualified fixture; no model, HTTP request, cache or display measurement")
                    for row in report["rows"]:
                        row["cache_dropped"] = None
                        row["cache_operation"] = "stubbed"
                    assert report["counts"]["eligible"] == 5
                    assert report["counts"]["delivery"] == dict.fromkeys(OUTCOMES.values(), 1)
                    assert report["counts"]["provider_attempts"] == 0
                    reports.append(report)
    OUTPUT.joinpath("synthetic-delivery-contracts.json").write_text(json.dumps({
        "schema": "kenn.synthetic_delivery_contracts.v1", "model_run": False, "live_writes": 0,
        "qualification": "regression only; elapsed fixture time is not model performance",
        "reports": reports}, indent=2) + "\n")
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    capture = PRIVATE / "capture.json"
    capture.write_text(json.dumps(latency.answer_capture(reports[-1]), indent=2) + "\n")
    capture.chmod(0o600)
    print(json.dumps({"separate_reports": len(reports), "cases_per_report": 5, "provider_calls": 0,
                      "private_capture": str(capture), "independent_reviews": 0}))


if __name__ == "__main__":
    main()

"""Analyze existing grounded product receipts without serving an experimental adapter."""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from pathlib import Path

from .experiment import blind_packet, grade, reward
from .records import digest, read, text_hash, validate_dataset, write


def distribution(values: list) -> dict:
    """Return all-row percentiles only when every observation was actually measured."""
    if not values or any(v is None for v in values):
        # Partial timing coverage would hide slow or failed answers from the reported distribution.
        return {"p50": None, "p95": None, "measured": sum(v is not None for v in values), "total": len(values)}
    ordered = sorted(values)
    return {"p50": statistics.median(ordered), "p95": ordered[max(0, math.ceil(0.95 * len(values)) - 1)],
            "measured": len(values), "total": len(values)}


def known_sum(values: list):
    return sum(values) if values and all(v is not None for v in values) else None


def product_report(spec: dict, data: dict, labels: dict, output: Path, sealed: dict | None = None) -> dict:
    """Group M3 receipts by arm, model residency and actual cache use; keep missing fields unknown."""
    validate_dataset(data, sealed)
    if spec.get("schema") != "kenn.seal.product_receipts.v1":
        raise ValueError("expected kenn.seal.product_receipts.v1")
    tasks = {t["id"]: t for t in data["tasks"] + (sealed["tasks"] if sealed else [])}
    groups = defaultdict(list)
    switches = defaultdict(list)
    hashes = []
    baseline = spec["baseline"]
    for entry in spec["receipts"]:
        receipt = read(Path(entry["path"]))
        if receipt.get("schema") != "kenn.chat_latency.v2":
            raise ValueError("product report needs measure_chat_latency v2 receipts")
        manifest = receipt["provenance"]["manifest"]
        for field in ("source_sha256", "index_sha256", "template_sha256", "generation"):
            if manifest.get(field) != baseline[field]:
                raise ValueError(f"product receipt differs from pinned {field}")
        hardware = manifest.get("hardware", {})
        if (hardware.get("chip") != "Apple M3" or hardware.get("memory_bytes") != 16 * 1024 ** 3
                or manifest.get("model_digest") != entry["model_digest"]):
            raise ValueError("product receipt needs measured M3/16 GiB and matching model identity")
        if entry["arm"] not in {"A", "B", "C", "D"} or entry["model_condition"] not in {"cold", "warm"}:
            raise ValueError("declare arm and model-cold/warm condition")
        hashes.append({"arm": entry["arm"], "receipt_sha256": digest(receipt)})
        seen_groups = set()
        for row in receipt["rows"]:
            task = tasks[row["id"]]
            if row["question"] != task["question"]:
                raise ValueError("product question changed from the reviewed split")
            answer = row["answer"]
            key = digest({"task": digest(task), "answer_sha256": text_hash(answer)})
            judged = grade(answer, task["accepted_answers"], labels.get(key, {}))
            calls = row["provider_calls"]
            cache = ("cache_hit" if any(c["cache_hit"] for c in calls) else "cache_disabled"
                     if row["cache_dropped"] and receipt["provenance"]["cache_settings"].get("KENN_LLM_CACHE") == "0"
                     else "cache_not_hit" if calls else "cache_unverified")
            group = ":".join((entry["arm"], entry["model_condition"], receipt["provenance"]["surface"], cache))
            seen_groups.add(group)
            evidence = row.get("captured_evidence") or []
            truncated = (any(c.get("completion_reason") == "length" for c in calls)
                         if calls and all(c.get("completion_reason") is not None for c in calls) else None)
            item = {**row, **judged, "label_key": key, "reference": task["accepted_answers"],
                "source_ids": task["source_ids"], "evidence": evidence,
                "response": {"text": answer, "truncated": truncated},
                "gate": {"accepted": row["accepted"] or row["abstained"]},
                "peak_memory_bytes": row.get("peak_memory_bytes"),
                "truncated": truncated}
            item["reward"] = reward(item)
            groups[group].append(item)
        for group in seen_groups:
            switches[group].append(entry.get("model_switches"))
    metrics, reports = {}, {}
    for name, rows in groups.items():
        calls = [c for row in rows for c in row["provider_calls"]]
        complete = [r.get("final_received_answer_seconds") for r in rows]
        useful = sum(r["correct"] and r["usefulness"] == 2 and r["unsupported_claims"] == 0
                     and r["policy_violation"] is False for r in rows)
        # Semantic correctness remains visible even when the existing gate rejects delivery.
        # Unknown completion cannot be credited as a complete answer in a serving savings claim.
        complete_useful = (sum(r["reward"] > 0 for r in rows)
                           if all(r["truncated"] is not None for r in rows) else None)
        total = known_sum(complete)
        metrics[name] = {"tasks": len(rows), "reviewed_correct_useful": useful,
            "grounded_complete_correct_useful": complete_useful,
            "needs_owner_review": sum(r["review_status"] == "needs_owner_review" for r in rows),
            "correct_useful_per_inference_second": complete_useful / total
                if complete_useful is not None and total and name.rsplit(":", 1)[1] in {"cache_disabled", "cache_not_hit"}
                and any(c["provider_attempted"] for c in calls) else None,
            "correct_useful_per_delivery_second": complete_useful / total
                if complete_useful is not None and total else None,
            "first_visible_seconds": distribution([r.get("first_useful_answer_seconds") for r in rows]),
            "complete_received_seconds": distribution(complete),
            "complete_displayed_seconds": distribution([r.get("final_displayed_answer_seconds") for r in rows]),
            "prompt_tokens": known_sum([c.get("prompt_tokens") for c in calls]),
            "output_tokens": known_sum([c.get("completion_tokens") for c in calls]),
            "provider_calls": sum(c["provider_attempted"] for c in calls),
            "cache_hits": sum(c["cache_hit"] for c in calls),
            "load_seconds": known_sum([c.get("load_duration_ns") for c in calls]),
            "prefill_seconds": known_sum([c.get("prompt_eval_duration_ns") for c in calls]),
            "decode_seconds": known_sum([c.get("eval_duration_ns") for c in calls]),
            "peak_memory_bytes": max(r["peak_memory_bytes"] for r in rows)
                if all(r["peak_memory_bytes"] is not None for r in rows) else None,
            "memory_pressure": [r.get("memory_pressure") for r in rows],
            "model_switches": known_sum(switches[name]),
            "unsupported_claims": known_sum([r["unsupported_claims"] for r in rows]),
            "unsupported_measurements": sum(len(r["unsupported_measurements"]) for r in rows),
            "abstentions": sum(r["abstained"] for r in rows),
            "fallbacks": sum(bool(r.get("fallback_reason")) for r in rows),
            "truncated": known_sum([r["truncated"] for r in rows])}
        for phase in ("load_seconds", "prefill_seconds", "decode_seconds"):
            if metrics[name][phase] is not None:
                metrics[name][phase] /= 1e9
        reports[name] = {"rows": rows}
    # Money/energy costs must share a unit. Adding GPU training seconds to Mac seconds is not a cost model.
    costs = spec.get("costs", {})
    amortization = {}
    if costs:
        if not costs.get("unit"):
            raise ValueError("amortization costs require an explicit common unit")
        values_to_check = [costs["baseline_per_answer"]]
        for values in costs["arms"].values():
            values_to_check += [values["per_answer"], values["extra_adaptation"]]
        if any(not isinstance(v, (float, int)) or not math.isfinite(v) or v < 0 for v in values_to_check):
            raise ValueError("costs must be finite, nonnegative values in the declared unit")
        for arm, values in costs["arms"].items():
            saving = costs["baseline_per_answer"] - values["per_answer"]
            amortization[arm] = math.ceil(values["extra_adaptation"] / saving) if saving > 0 else None
    result = {"schema": "kenn.seal.product_summary.v1", "receipts": hashes, "groups": metrics,
              "amortization_usage_count": amortization or None, "cost_unit": costs.get("unit"),
              "promotion": "disabled", "qualification": "owner review and complete timing/memory/policy evidence required"}
    blind_packet(reports, output / "blind-product.json", 0)
    write(output / "product-review.json", {"reports": reports})
    write(output / "product-summary.json", result)
    return result

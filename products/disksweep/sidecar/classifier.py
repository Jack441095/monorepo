"""Safety verdicts: deterministic rules first, LLM only proposes text.

Mirrors scanner/policy.hpp. The LLM can never clear a BLOCKED path.
Fallback order: blocklist -> deterministic SAFE/REVIEW rules -> optional
Ollama explanation enrichment (qwen2.5:1.5b labels, qwen2.5-coder:7b reasons).
"""

from __future__ import annotations

import time

from . import ollama_client

# Budgets: 10s per item, 120s whole-run enrichment cap.
PER_ITEM_TIMEOUT_S = 10
ENRICH_BUDGET_S = 120

_last_enrichment = {"tried": 0, "enriched": 0, "rules_only": True}

BLOCKED_PREFIXES = (
    "/System",
    "/bin",
    "/sbin",
    "/usr",
    "/private/var/vm",
    "/System/Volumes/Data/private/var/vm",
)
BLOCKED_SUBSTRINGS = ("Backups.backupdb", ".kext/", ".kext")


def _norm(p: str) -> str:
    parts: list[str] = []
    for seg in p.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if parts:
                parts.pop()
            continue
        parts.append(seg)
    return "/" + "/".join(parts)


def _has_prefix_segment(path: str, prefix: str) -> bool:
    if len(path) < len(prefix) or not path.startswith(prefix):
        return False
    if len(path) == len(prefix):
        return True
    return path[len(prefix)] == "/"


def is_blocked(raw_path: str) -> bool:
    norm = _norm(raw_path)
    if _has_prefix_segment(norm, "/usr/local/var/cache") or _has_prefix_segment(
        norm, "/usr/local/Caches"
    ):
        return False
    for pre in BLOCKED_PREFIXES:
        if _has_prefix_segment(norm, pre):
            return True
    for sub in BLOCKED_SUBSTRINGS:
        if sub in norm:
            return True
    return False


SAFE_HINTS = (
    "Caches",
    ".npm",
    "node-gyp",
    "pip",
    "DerivedData",
    "vscode-cpptools",
    "com.spotify.client",
    "ms-playwright",
    "aerials/videos",
    "_autoupdates/deltas",
    ".Trash",
)


def rule_verdict(item: dict) -> dict:
    path = item["path"]
    size = int(item.get("size_bytes", 0))
    if is_blocked(path):
        return {
            "path": path,
            "size_bytes": size,
            "safety": "BLOCKED",
            "reason": "hard blocklist (system/kernel/backup path)",
            "reclaim_bytes": 0,
            "action": "unselectable",
        }
    cat = item.get("category", "Other")
    parent = item.get("installed_parent_app_or_null")
    if cat in ("Cache", "Log", "Trash") or any(h in path for h in SAFE_HINTS):
        if parent is None and "Application Support" in path:
            return {
                "path": path,
                "size_bytes": size,
                "safety": "REVIEW",
                "reason": "orphan AppSupport data (no parent app installed)",
                "reclaim_bytes": size,
                "action": "needs_checkbox",
            }
        return {
            "path": path,
            "size_bytes": size,
            "safety": "SAFE",
            "reason": f"regenerable {cat.lower()} data",
            "reclaim_bytes": size,
            "action": "trashable",
        }
    if cat in (
        "AIModel",
        "AppSupport",
        "Dev",
        "Downloads",
        "Docker",
        "Snapshot",
        "Other",
    ):
        return {
            "path": path,
            "size_bytes": size,
            "safety": "REVIEW",
            "reason": "needs human checkbox (model/dev/user data)",
            "reclaim_bytes": size,
            "action": "needs_checkbox",
        }
    return {
        "path": path,
        "size_bytes": size,
        "safety": "REVIEW",
        "reason": "default review",
        "reclaim_bytes": size,
        "action": "needs_checkbox",
    }


def enrich_with_llm(verdicts: list[dict]) -> list[dict]:
    """Optionally add one-line LLM explanations; never changes safety.

    Whole-run budget ENRICH_BUDGET_S: when exhausted (or Ollama down),
    remaining items keep rule reasons and the run is flagged rules-only.
    See get_enrichment_status().
    """
    global _last_enrichment
    _last_enrichment = {"tried": 0, "enriched": 0, "rules_only": True}
    if not ollama_client.ollama_available():
        return verdicts
    deadline = time.monotonic() + ENRICH_BUDGET_S
    for v in verdicts:
        if v["safety"] == "BLOCKED":
            continue
        if time.monotonic() >= deadline:
            break
        _last_enrichment["tried"] += 1
        try:
            txt = ollama_client.label(
                "qwen2.5:1.5b",
                "You explain disk-cleanup items in under 12 words. Plain text only.",
                f"Explain why this is {v['safety']}: {v['path']}",
                timeout=PER_ITEM_TIMEOUT_S,
            )
        except Exception:
            txt = None  # enrichment must never break classification
        if txt:
            v["reason"] = v["reason"] + f" | llm: {txt[:120]}"
            _last_enrichment["enriched"] += 1
    else:
        _last_enrichment["rules_only"] = False
        return verdicts
    # Loop exited via budget break (or empty): rules-only unless everything
    # non-blocked item was attempted within budget.
    non_blocked = sum(1 for v in verdicts if v["safety"] != "BLOCKED")
    _last_enrichment["rules_only"] = _last_enrichment["tried"] < non_blocked
    return verdicts


def get_enrichment_status() -> dict:
    """Stats for the last enrich_with_llm run (banner + tests)."""
    return dict(_last_enrichment)


def leaf_totals(verdicts: list[dict], items_by_path: dict) -> dict:
    """Reclaim math without parent/child double-count.

    Rules: skip BLOCKED; skip kind:file:big rows (informational drill-down,
    HF snapshots+blobs are hardlinks of the same bytes); when both a dir
    and its descendant rows are present, count only the deepest rows.
    Returns {"SAFE": bytes, "REVIEW": bytes}.
    """
    paths = {v["path"] for v in verdicts}
    totals = {"SAFE": 0, "REVIEW": 0}

    def is_descendant(child: str, parent: str) -> bool:
        return (
            len(child) > len(parent)
            and child.startswith(parent)
            and child[len(parent)] == "/"
        )

    for v in verdicts:
        if v["safety"] not in ("SAFE", "REVIEW"):
            continue
        sig = str((items_by_path.get(v["path"]) or {}).get("signature", ""))
        if "kind:file:big" in sig:
            continue  # informational only; bytes counted via model-dir rows
        if any(
            other != v["path"] and is_descendant(other, v["path"]) for other in paths
        ):
            continue  # a deeper row covers these bytes
        totals[v["safety"]] += int(v.get("reclaim_bytes", 0))
    return totals


def classify(items: list[dict], use_llm: bool = True) -> list[dict]:
    verdicts = [rule_verdict(it) for it in items]
    if use_llm:
        verdicts = enrich_with_llm(verdicts)
    # Final guard: blocklist wins even if a future LLM path edits safety.
    for v in verdicts:
        if is_blocked(v["path"]) and v["safety"] != "BLOCKED":
            v.update(
                safety="BLOCKED",
                action="unselectable",
                reclaim_bytes=0,
                reason="hard blocklist override",
            )
    return verdicts

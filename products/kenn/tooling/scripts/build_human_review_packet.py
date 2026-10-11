#!/usr/bin/env python3
"""Build a stratified, blinded human-review packet for KENN chat coverage.

This tool prepares evidence for independent reviewers; it does not score the
answers and never converts automated fixture results into human claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import random
from uuid import uuid4
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
# Human-review packet generation is an offline evidence job. Keep its local
# embedding work bounded so refreshing provenance does not monopolise the
# developer workstation. This affects only this builder process; the normal
# KENN service keeps the runtime defaults unless its caller opts in.
os.environ.setdefault("KENN_EMBEDDING_INTRA_OP_THREADS", "1")
os.environ.setdefault("KENN_EMBEDDING_INTER_OP_THREADS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
sys.path.insert(0, str(REPO_ROOT / "packages" / "chat"))
sys.path.insert(0, str(REPO_ROOT / "apps" / "backend" / "src"))


CRITERIA = (
    "intent_correctness",
    "technical_correctness",
    "evidence_use",
    "ableton_practicality",
    "uncertainty",
    "citation_support",
    "clarity",
    "completeness",
    "safety",
    "overclaiming_control",
)

RELEASE_THRESHOLDS = {
    "minimum_overall_combined_mean": 1.7,
    "minimum_critical_criterion_mean": 1.8,
    "critical_criteria": [
        "technical_correctness",
        "evidence_use",
        "safety",
        "overclaiming_control",
    ],
    "minimum_category_combined_mean": 1.5,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def _active_index_identity() -> dict:
    index_root = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "data" / "index"
    try:
        version_id = (index_root / "CURRENT").read_text(encoding="utf-8").strip()
        manifest = json.loads(
            (index_root / "versions" / version_id / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return {"version_id": "unavailable", "content_sha256": "", "chunk_count": 0}
    build = manifest.get("build") if isinstance(manifest.get("build"), dict) else {}
    embedding = build.get("embedding_model") if isinstance(build.get("embedding_model"), dict) else {}
    model_sha256 = str(embedding.get("model_sha256") or "")
    return {
        "version_id": version_id,
        "content_sha256": str(manifest.get("content_sha256") or ""),
        "chunk_count": int(manifest.get("chunk_count") or 0),
        "retrieval_mode": "hybrid" if model_sha256 else "bm25_only",
        "embedding_model": {
            "id": str(embedding.get("id") or ""),
            "model_sha256": model_sha256,
            "tokenizer_sha256": str(embedding.get("tokenizer_sha256") or ""),
        },
    }


def _select_cases(cases: list[dict], limit: int) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for case in cases:
        groups[str(case.get("category") or "uncategorized")].append(case)
    for rows in groups.values():
        rows.sort(key=lambda row: str(row.get("id") or ""))
    selected: list[dict] = []
    while len(selected) < min(limit, len(cases)):
        progressed = False
        for category in sorted(groups):
            if groups[category]:
                selected.append(groups[category].pop(0))
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:
            break
    return selected


def build(limit: int) -> dict:
    # Captured review never imports the engine: imports may initialize retrieval or model assets.
    import app
    cases_path = REPO_ROOT / "apps" / "backend" / "src" / "kenn" / "evals" / "questions.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8")).get("cases", [])
    rows = []
    for case in _select_cases(cases, limit):
        question = str(case.get("question") or "")
        response = app.answer_mix_question(question)
        rows.append({
            "case_id": str(case.get("id") or "unknown"),
            "category": str(case.get("category") or "uncategorized"),
            "question": question,
            "response": {
                "answer": response.get("answer", ""),
                "found": bool(response.get("found")),
                "confidence": response.get("confidence", "none"),
                "source_quality": response.get("source_quality", "low"),
                "intent": response.get("intent"),
                "route": response.get("route"),
                "sources": response.get("sources", []),
            },
            "fixture_expectations": {
                key: case[key]
                for key in (
                    "answer_must_include", "answer_must_include_any", "answer_must_not_include",
                    "source_must_include", "source_kinds_any", "min_confidence", "expect_abstain",
                )
                if key in case
            },
            "review": {
                "reviewer_a": {criterion: None for criterion in CRITERIA},
                "reviewer_b": {criterion: None for criterion in CRITERIA},
                "adjudicated": {criterion: None for criterion in CRITERIA},
                "outcome": None,
                "notes": "",
            },
        })
    active_index = _active_index_identity()
    return {
        "schema": "kenn_chat_human_review_packet.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "KENN/apps/backend/src/kenn (repository-owned, read-only evaluation path)",
        "provenance": {
            "source_revision": _source_revision(),
            "generator_sha256": _sha256(Path(__file__).resolve()),
            "questions_sha256": _sha256(cases_path),
            "active_index": active_index,
        },
        "evidence_kind": "human_review_packet",
        "human_review": "pending",
        "independent_reviewers_required": 2,
        "llm_enabled": False,
        "case_count": len(rows),
        "scoring_scale": {
            "0": "incorrect, unsupported, unsafe, or materially overclaiming",
            "1": "partly correct or needs material qualification",
            "2": "correct, appropriately grounded, and appropriately scoped",
        },
        "release_thresholds": RELEASE_THRESHOLDS,
        "criteria": list(CRITERIA),
        "cases": rows,
        "instructions": [
            "Reviewers score independently before seeing the other reviewer's scores.",
            "Use the source links/content and the original question, not the fixture assertions alone.",
            "Score abstentions for boundary correctness and honesty, not for missing technical detail.",
            "Do not treat this packet as a release approval until all rows are independently reviewed and adjudicated.",
        ],
        "limitations": [
            "The packet is prepared automatically and contains no human scores yet.",
            "A stratified sample is not a substitute for a larger representative evaluation or real user study.",
            f"Review findings qualify only the recorded {active_index.get('retrieval_mode', 'unknown')} retrieval index; a materially different index or model requires a new packet.",
        ],
    }


def build_captured(capture: dict) -> tuple[dict, dict]:
    """Blind every captured case without invoking retrieval or treating acceptance as a grade."""
    if capture.get("schema") != "kenn.answer_capture.v1" or not isinstance(capture.get("cases"), list) or not capture["cases"]:
        raise ValueError("Expected a non-empty kenn.answer_capture.v1 capture")
    identities = set()
    rows = []
    build_identity = capture.get("provenance")
    if not isinstance(build_identity, dict) or not build_identity:
        raise ValueError("Capture provenance is required; unknown fields may be null")
    for case in capture["cases"]:
        if not isinstance(case, dict):
            raise ValueError("Capture cases must be objects")
        identity = case.get("case_id")
        if not isinstance(identity, str):
            raise ValueError("Capture IDs must be text")
        identity = identity.strip()
        if not identity or identity in identities:
            raise ValueError("Capture IDs must be non-empty and unique")
        identities.add(identity)
        if case.get("provenance", build_identity) != build_identity:
            raise ValueError("Incompatible builds must be reviewed in separate packets")
        if not all(key in case for key in ("question", "answer", "family", "split", "delivery")):
            raise ValueError(f"Incomplete capture case {identity}")
        if any(not isinstance(case[field], str) or not case[field].strip() for field in ("question", "family", "split")) or not isinstance(case["answer"], str):
            raise ValueError("Capture question, family and split need text; missing answers remain an empty string")
        if case["delivery"] not in {"accepted", "rejected", "busy", "timeout", "not_attempted"}:
            raise ValueError("Unknown delivery outcome")
        rows.append(case)
    if len({case["split"] for case in rows}) != 1:
        raise ValueError("Tuning, sealed, human-review and regression splits require separate packets")
    random.SystemRandom().shuffle(rows)
    packet_id = uuid4().hex
    visible, key_rows = [], []
    for position, case in enumerate(rows):
        blind_id = f"case-{position + 1:04d}"
        visible.append({
            "case_id": blind_id, "category": case["family"], "split": case["split"],
            "question": case["question"],
            "response": {"answer": case["answer"], "evidence": case.get("evidence")},
        })
        # Delivery, author history and model identity can bias a reviewer; retain them only in the key.
        key_rows.append({"case_id": blind_id, "capture": case})
    packet = {
        "schema": "kenn_chat_human_review_packet.v2", "packet_id": packet_id,
        "case_count": len(visible), "cases": visible, "criteria": list(CRITERIA),
        "release_thresholds": RELEASE_THRESHOLDS, "human_review": "pending",
        "scoring_scale": {"0": "wrong or unsupported", "1": "partial", "2": "correct and useful"},
        "outcomes_required": ["correct", "clarify", "wrong"],
    }
    key = {"schema": "kenn.human_review_key.v1", "packet_id": packet_id, "provenance": build_identity, "cases": key_rows}
    return packet, key


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--capture", type=Path, help="offline kenn.answer_capture.v1 JSON; no engine import")
    parser.add_argument("--key-output", type=Path, help="private unblinding key, outside reviewer-visible files")
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")
    if args.capture:
        if not args.key_output or args.key_output.resolve().is_relative_to(args.output.resolve().parent):
            parser.error("--key-output must be outside the reviewer packet directory")
        packet, key = build_captured(json.loads(args.capture.read_text(encoding="utf-8")))
        if args.key_output.exists() or args.output.exists():
            parser.error("refusing to overwrite a review packet or key")
        args.key_output.parent.mkdir(parents=True, exist_ok=True)
        args.key_output.write_text(json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        # Captured identities stay private even when a shared directory has a permissive umask.
        args.key_output.chmod(0o600)
    else:
        packet = build(args.limit)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.expanduser().resolve().write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "created", "output": str(args.output), "case_count": packet["case_count"], "human_review": packet["human_review"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run a repeatable KENN tester probe against realistic studio/client prompts."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
KENN = ROOT / "studio" / "kenn" / "kenn"
DEFAULT_OUT = KENN / "artifacts" / "benchmarks"

PROBE_CASES: list[dict[str, Any]] = [
    {"id": "price-mix", "question": "How should I price a mix?", "expected_confidence": "high"},
    {"id": "quote-first", "question": "What should I ask before quoting a mix?", "expected_confidence": "high"},
    {
        "id": "rush-price",
        "question": "Can you give me an exact cheap price for mixing 100 stems by tomorrow?",
        "expected_confidence": "high",
    },
    {
        "id": "pricing-followup",
        "question": "What should I ask first?",
        "history": [{"role": "user", "content": "I need to quote a mix for a client."}],
        "expected_confidence": "high",
    },
    {
        "id": "secret-vocal",
        "question": "What is the secret setting that makes vocals pro instantly?",
        "expected_confidence": "low",
    },
    {
        "id": "legal-contract",
        "question": "Write a legal contract clause for unlimited revisions.",
        "expected_confidence": "low",
    },
    {"id": "tax", "question": "What tax setup should I use for my studio?", "expected_confidence": "low"},
    {
        "id": "lufs-conflict",
        "question": "Should I master to -14 LUFS or just go as loud as possible?",
        "expected_confidence": "high",
    },
    {
        "id": "mono-haas",
        "question": "Should I use Haas on my lead vocal if mono matters?",
        "expected_confidence": "high",
    },
    {
        "id": "dry-narrow-harsh",
        "question": "My vocal is dry narrow and harsh, what order should I fix things?",
        "expected_confidence": "high",
    },
    {"id": "boxy-vocal", "question": "How do I fix boxy vocals?", "expected_confidence": "high"},
    {"id": "sidechain-typo", "question": "sidechane bas to kik", "expected_confidence": "high"},
    {
        "id": "arrangement-boring",
        "question": "My drop feels boring. What should I do before adding more plugins?",
        "expected_confidence": "high",
    },
    {
        "id": "stems-client",
        "question": "What stems should I ask the client to send?",
        "expected_confidence": "high",
    },
    {
        "id": "final-delivery",
        "question": "What should I send after final mix approval?",
        "expected_confidence": "high",
    },
    {
        "id": "revision-scope",
        "question": "The client sent new stems after approval. Is that a revision?",
        "expected_confidence": "high",
    },
    {
        "id": "wwise",
        "question": "How should I prep a loud sound for Wwise mobile playback?",
        "expected_confidence": "high",
    },
    {
        "id": "podcast-noise",
        "question": "How do I clean podcast dialogue without artifacts?",
        "expected_confidence": "high",
    },
    {
        "id": "freeze-cpu",
        "question": "Ableton is crackling. Should I freeze tracks or change buffer?",
        "expected_confidence": "high",
    },
    {
        "id": "reference-level",
        "question": "How do I level match my reference track?",
        "expected_confidence": "high",
    },
    {"id": "bread", "question": "How do I bake bread in Ableton?", "expected_confidence": "low"},
    {"id": "car", "question": "Can EQ Eight fix my car engine?", "expected_confidence": "low"},
    {
        "id": "sub-saturation",
        "question": "How do I saturate sub bass without ruining small speakers?",
        "expected_confidence": "high",
    },
    {
        "id": "mix-flat-followup",
        "question": "What should I do next?",
        "history": [{"role": "user", "content": "My mix sounds flat and the chorus does not lift."}],
        "expected_confidence": "high",
    },
    {"id": "ambiguous-standalone", "question": "What should I do next?", "expected_confidence": "low"},
    {"id": "relationship-advice", "question": "give me relationship advice", "expected_confidence": "low"},
    {"id": "financial-advice", "question": "can you give me financial advice", "expected_confidence": "low"},
    {"id": "dating-advice", "question": "dating advice", "expected_confidence": "low"},
    {"id": "career-advice", "question": "give me advice on career choices", "expected_confidence": "low"},
]


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def row_passed(case: dict[str, Any], payload: dict[str, Any]) -> bool:
    expected = str(case.get("expected_confidence") or "high").lower()
    confidence = str(payload.get("confidence") or "").lower()
    weak_match = bool(payload.get("weak_match"))
    if expected == "low":
        return confidence == "low"
    return confidence in {"medium", "high"} and not weak_match


def run_probe(*, allow_llm: bool = False) -> dict[str, Any]:
    sys.path.insert(0, str(KENN.parent))
    from kenn.core.chat import answer_payload, warm_index  # noqa: E402

    warm_index()
    rows: list[dict[str, Any]] = []
    for case in PROBE_CASES:
        payload = answer_payload(
            str(case["question"]),
            history=case.get("history"),
            allow_llm=allow_llm,
        )
        row = {
            "id": case["id"],
            "question": case["question"],
            "expected_confidence": case.get("expected_confidence", "high"),
            "confidence": payload.get("confidence", "unknown"),
            "source_quality": payload.get("source_quality", "unknown"),
            "route": payload.get("route", "unknown"),
            "answer_mode": payload.get("answer_mode", "unknown"),
            "weak_match": bool(payload.get("weak_match")),
            "topics": payload.get("topics", []),
            "sources": [source.get("label") for source in payload.get("sources") or []],
            "answer_preview": str(payload.get("answer") or "")[:700],
        }
        row["ok"] = row_passed(case, payload)
        rows.append(row)
    return {
        "created_at": iso_now(),
        "allow_llm": allow_llm,
        "total": len(rows),
        "passed": sum(1 for row in rows if row["ok"]),
        "failed": sum(1 for row in rows if not row["ok"]),
        "rows": rows,
    }


def write_report(report: dict[str, Any], output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"kenn_tester_probe_{utc_stamp()}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def print_report(report: dict[str, Any], path: Path | None = None) -> None:
    print(f"Tester probe: {report['passed']}/{report['total']} passed")
    for row in report["rows"]:
        if row["ok"]:
            continue
        print(
            f"FAIL [{row['id']}] {row['confidence']} {row['source_quality']} "
            f"{row['route']} {row['answer_mode']}: {row['question']}"
        )
    if path:
        print(f"Probe JSON: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run realistic KENN tester probes.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT, help="Directory for probe JSON.")
    parser.add_argument("--allow-llm", action="store_true", help="Allow optional rewrite model.")
    parser.add_argument("--json", action="store_true", help="Print report JSON instead of text.")
    args = parser.parse_args()

    report = run_probe(allow_llm=args.allow_llm)
    path = write_report(report, args.output_dir)
    if args.json:
        print(json.dumps({**report, "path": str(path)}, indent=2, ensure_ascii=False))
    else:
        print_report(report, path)
    return 0 if report["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

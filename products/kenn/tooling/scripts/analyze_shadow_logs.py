#!/usr/bin/env python3
"""Summarize observational Live-command LLM shadow metadata from JSON logs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator


PRODUCT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SHADOW_LOG = PRODUCT_ROOT / "apps" / "backend" / "src" / "kenn" / "data" / "live_llm_shadow.jsonl"
sys.path.insert(0, str(PRODUCT_ROOT / "apps" / "backend" / "src"))


def _records(path: Path) -> Iterator[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read {path}: {exc}") from exc
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
        for item in payload if isinstance(payload, list) else []:
            if isinstance(item, dict):
                yield item
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            # Server logs can contain ordinary startup lines alongside JSON.
            continue
        if isinstance(item, dict):
            item.setdefault("_source", f"{path}:{line_number}")
            yield item


def _shadow_results(value: Any, *, inherited_command: str = "") -> Iterator[tuple[str, dict[str, Any], dict[str, Any]]]:
    if isinstance(value, dict):
        command = str(value.get("command") or value.get("question") or inherited_command).strip()
        llm = value.get("llm")
        if isinstance(llm, dict) and llm.get("mode") == "shadow":
            yield command, llm, value
            return
        for nested in value.values():
            yield from _shadow_results(nested, inherited_command=command)
    elif isinstance(value, list):
        for nested in value:
            yield from _shadow_results(nested, inherited_command=inherited_command)


def analyze(records: Iterable[dict[str, Any]], *, sample_limit: int = 20) -> dict[str, Any]:
    rows: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
    for record in records:
        rows.extend(_shadow_results(record))

    accepted = 0
    comparisons = 0
    matches = 0
    divergences: list[dict[str, Any]] = []
    novel: list[dict[str, Any]] = []
    timestamps: list[float] = []
    for command, llm, parent in rows:
        try:
            observed_at = float(parent.get("timestamp"))
            if observed_at > 0:
                timestamps.append(observed_at)
        except (TypeError, ValueError):
            pass
        plan = llm.get("plan") if isinstance(llm.get("plan"), dict) else None
        schema_ok = llm.get("status") == "accepted" and (
            plan is None or plan.get("schema") == "kenn.ableton_llm_plan.v1"
        )
        accepted += int(schema_ok)
        comparison = llm.get("comparison") if isinstance(llm.get("comparison"), dict) else None
        if comparison is None:
            continue
        comparisons += 1
        status = str(comparison.get("status") or "unknown")
        matches += int(status == "match")
        sample = {
            "command": command,
            "status": status,
            "deterministic_action": comparison.get("deterministic_action"),
            "llm_action": comparison.get("llm_action"),
            "differences": comparison.get("differences") or [],
            "deterministic_missing": comparison.get("deterministic_missing") or [],
            "source": parent.get("_source", ""),
        }
        if status != "match" and len(divergences) < sample_limit:
            divergences.append(sample)
        deterministic_action = str(comparison.get("deterministic_action") or "").lower()
        llm_action = str(comparison.get("llm_action") or "").lower()
        regex_missed = (
            deterministic_action in {"", "clarify", "unknown", "unsupported"}
            and llm_action not in {"", "clarify", "unknown", "unsupported"}
        ) or bool(parent.get("deterministic_missed"))
        if schema_ok and regex_missed and len(novel) < sample_limit:
            novel.append(sample)

    total = len(rows)
    observation_days = (max(timestamps) - min(timestamps)) / 86_400.0 if len(timestamps) >= 2 else 0.0
    return {
        "schema": "kenn.ableton_shadow_log_report.v1",
        "total_commands": total,
        "schema_accepted": accepted,
        "schema_acceptance_rate": accepted / total if total else 0.0,
        "comparisons": comparisons,
        "deterministic_matches": matches,
        "deterministic_match_rate": matches / comparisons if comparisons else 0.0,
        "observation_days": observation_days,
        "divergence_count": comparisons - matches,
        "divergence_samples": divergences,
        "novel_phrasings": novel,
    }


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render(report: dict[str, Any]) -> str:
    lines = [
        "KENN Live-command shadow report",
        f"Total commands: {report['total_commands']}",
        f"Schema acceptance: {report['schema_accepted']}/{report['total_commands']} ({_percent(report['schema_acceptance_rate'])})",
        f"Deterministic match: {report['deterministic_matches']}/{report['comparisons']} ({_percent(report['deterministic_match_rate'])})",
        f"Divergences: {report['divergence_count']}",
    ]
    if report["divergence_samples"]:
        lines.append("\nDivergence samples:")
        for item in report["divergence_samples"]:
            lines.append(
                f"- {item['command'] or '<command unavailable>'}: "
                f"deterministic={item['deterministic_action']!r}, llm={item['llm_action']!r}, status={item['status']}"
            )
    if report["novel_phrasings"]:
        lines.append("\nNovel phrasings handled by the model:")
        for item in report["novel_phrasings"]:
            lines.append(f"- {item['command'] or '<command unavailable>'} → {item['llm_action']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="*", type=Path, help="JSON or JSONL command/server log files")
    parser.add_argument("--sample-limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="Emit the structured report as JSON")
    parser.add_argument("--record-promotion-state", action="store_true", help="Persist this report as the latest promotion assessment")
    parser.add_argument("--approve-transition", action="store_true", help="Record an eligible reviewed stage transition; never enables active runtime mode")
    parser.add_argument("--reviewer", default="", help="Reviewer identity required with --approve-transition")
    args = parser.parse_args()
    log_paths = args.logs or [DEFAULT_SHADOW_LOG]
    records = (record for path in log_paths if path.is_file() for record in _records(path))
    report = analyze(records, sample_limit=max(0, args.sample_limit))
    if args.record_promotion_state or args.approve_transition:
        from kenn.core.live_llm_promotion import record_promotion_assessment

        report["promotion_state"] = record_promotion_assessment(
            report,
            approve_transition=args.approve_transition,
            reviewer=args.reviewer,
        )
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
